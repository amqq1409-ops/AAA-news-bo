import tempfile
import unittest
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from campaign_detector import CampaignDetector
from country_coverage_tracker import CountryCoverageTracker
from data_store import ArticleStore
from intelligence_analyzer import MediaIntelligenceAnalyzer
from news_bot import alert_coordinated_campaign


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.articles = [
            {
                "title": "Saudi Arabia investment growth agreement",
                "country_code": "US",
                "country_ar": "أمريكا",
                "topic": "economy",
                "source_name": "Example US",
                "published_at": "2026-10-24T10:00:00+00:00",
            },
            {
                "title": "Saudi Arabia investment growth agreement",
                "country_code": "GB",
                "country_ar": "بريطانيا",
                "topic": "economy",
                "source_name": "Example UK",
                "published_at": "2026-10-24T11:00:00+00:00",
            },
            {
                "title": "Saudi Arabia crisis sanctions controversy",
                "country_code": "US",
                "country_ar": "أمريكا",
                "topic": "politics",
                "source_name": "Example US",
                "published_at": "2026-10-23T10:00:00+00:00",
            },
        ]

    def test_country_coverage_and_comparison(self):
        tracker = CountryCoverageTracker(
            self.articles,
            now=datetime(2026, 10, 25, tzinfo=timezone.utc),
        )
        rows = tracker.analyze_coverage_by_country()
        self.assertEqual({row["country_code"]: row["article_count"] for row in rows}, {"US": 2, "GB": 1})
        self.assertEqual(sum(row["percentage"] for row in rows), 100)
        self.assertEqual(tracker.compare_countries("US", "GB")["article_count_difference"], 1)
        self.assertEqual(rows[0]["sentiment"]["negative"], 50)
        self.assertEqual(set(tracker.get_sensitive_countries()), {"negative_focus", "positive_focus", "neutral"})

    def test_cross_country_similarity_is_only_a_candidate(self):
        candidates = CampaignDetector(self.articles).detect_coordinated_campaigns()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["countries_involved"], ["GB", "US"])
        self.assertIn("not established", candidates[0]["interpretation"])
        self.assertTrue(CampaignDetector(self.articles).detect_narrative_shifts())

        concentrated = self.articles + [
            {**self.articles[0], "topic": "economy"} for _ in range(4)
        ]
        signals = CampaignDetector(concentrated).detect_bias_patterns()
        us_signal = next(signal for signal in signals if signal["country_code"] == "US")
        self.assertEqual(us_signal["coverage_signal"], "topic_concentrated")

    def test_intelligence_report_discloses_limitations(self):
        analyzer = MediaIntelligenceAnalyzer(self.articles)
        report = analyzer.generate_intelligence_report()
        self.assertEqual(report["executive_summary"]["articles_analyzed"], 3)
        self.assertIsNone(report["near_term_outlook"]["forecast"])
        self.assertEqual(analyzer.pattern_detection()["funding"]["status"], "not_assessed")
        self.assertIn("groups", analyzer.comparative_analysis())

    def test_new_storage_tables_and_queries_leave_article_schema_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "news.db"
            store = ArticleStore(db_path)
            with store._connect() as conn:
                conn.execute("INSERT INTO articles (uid, title) VALUES (?, ?)", ("existing", "Existing article"))
            store = ArticleStore(db_path)
            with store._connect() as conn:
                self.assertEqual(conn.execute("SELECT title FROM articles WHERE uid = 'existing'").fetchone()["title"], "Existing article")
            coverage = CountryCoverageTracker(self.articles).analyze_coverage_by_country()[0]
            store.save_country_analysis(
                coverage,
                topics=[{"topic": "economy", "article_count": 2, "percentage": 100, "sentiment": 1}],
                outlets=[{"outlet_name": "Example US", "outlet_domain": "example.com", "article_count": 2}],
            )
            campaign = CampaignDetector(self.articles).detect_coordinated_campaigns()[0]
            store.save_campaign(campaign)
            self.assertEqual(store.query_country_stats("US")["article_count"], 2)
            self.assertEqual(len(store.query_campaigns_by_severity(0)), 1)
            self.assertEqual(store.query_campaign_timeline(campaign["campaign_id"])["timeline"], campaign["timeline"])
            self.assertEqual(store.query_topic_distribution_by_country("US")[0]["topic"], "economy")
            self.assertEqual(store.query_media_outlets_by_country("US")[0]["outlet_name"], "Example US")
            self.assertEqual(store.query_country_comparison("US", "US")["article_count_difference"], 0)
            store.save_country_analysis(coverage)
            self.assertEqual(store.query_topic_distribution_by_country("US"), [])
            with store._connect() as conn:
                tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                columns = {row["name"] for row in conn.execute("PRAGMA table_info(articles)")}
            self.assertTrue({"country_statistics", "campaigns", "media_outlets_by_country", "country_topics_matrix"} <= tables)
            self.assertNotIn("country_code", columns)

    def test_existing_database_is_backed_up_before_additive_schema_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "legacy.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "CREATE TABLE articles (id INTEGER PRIMARY KEY, uid TEXT UNIQUE, title TEXT, created_at TEXT)"
                )
                conn.execute(
                    "INSERT INTO articles (uid, title, created_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    ("legacy", "legacy article"),
                )

            ArticleStore(db_path)

            backup_path = db_path.with_suffix(".db.bak")
            with sqlite3.connect(backup_path) as backup:
                self.assertEqual(backup.execute("SELECT title FROM articles").fetchone()[0], "legacy article")
                tables = {row[0] for row in backup.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn("campaigns", tables)

    def test_alert_requires_threshold_and_escapes_content(self):
        class Telegram:
            message = None

            def send_text(self, message):
                self.message = message
                return True

        telegram = Telegram()
        self.assertFalse(alert_coordinated_campaign(telegram, {"severity": 0.2, "confidence_score": 0.8}))
        self.assertTrue(alert_coordinated_campaign(telegram, {
            "severity": 0.9,
            "confidence_score": 0.8,
            "campaign_id": "<test>",
            "countries_involved": ["US"],
        }))
        self.assertIn("&lt;test&gt;", telegram.message)

    def test_remaining_alert_helpers_respect_thresholds(self):
        from news_bot import (
            alert_bias_escalation,
            alert_country_anomaly,
            alert_media_concentration,
            alert_narrative_shift,
            alert_negative_surge,
        )

        class Telegram:
            def send_text(self, message):
                return True

        telegram = Telegram()
        self.assertFalse(alert_narrative_shift(telegram, {"shift_score": 0.2}))
        self.assertTrue(alert_narrative_shift(telegram, {"shift_score": 0.8}))
        self.assertTrue(alert_bias_escalation(telegram, {"bias_delta": 0.2}))
        self.assertTrue(alert_negative_surge(telegram, {"negative_share": 0.8, "baseline_delta": 0.3}))
        self.assertTrue(alert_country_anomaly(telegram, {"anomaly_score": 0.9}))
        self.assertTrue(alert_media_concentration(telegram, {"source_share": 0.8, "articles_count": 20}))


if __name__ == "__main__":
    unittest.main()
