import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from analytics_engine import AnalyticsEngine
from data_store import ArticleStore
from dashboard_api import create_app
from sentiment_analyzer import SentimentAnalyzer
from summarizer import NewsSummarizer


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = ArticleStore(Path(self.temp_dir.name) / "test.db")
        self.client = create_app(self.store).test_client()
        published = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with self.store._connect() as conn:
            conn.executemany(
                """
                INSERT INTO articles
                    (uid, title, url, domain, source_name, lang, country_ar,
                     published_at, tier, topic, source_score, relevance_score, origin)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    ("1", "Saudi growth success", "https://example.com/1", "example.com",
                     "Example", "en", "US", published, "intl", "economy", 80, 70, "test"),
                    ("2", "أزمة وتراجع في الأسواق", "https://example.com/2", "example.com",
                     "Example", "ar", "US", published, "intl", "economy", 80, 70, "test"),
                    ("3", "Saudi news update", "https://other.example/3", "other.example",
                     "Other", "en", "GB", published, "intl", "politics", 60, 50, "test"),
                ],
            )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sentiment_handles_english_and_arabic(self):
        analyzer = SentimentAnalyzer()
        self.assertEqual(analyzer.analyze("Saudi growth success")["label"], "positive")
        self.assertEqual(analyzer.analyze("أزمة وتراجع")["label"], "negative")
        self.assertEqual(analyzer.analyze("Saudi news update")["label"], "neutral")

    def test_summarizer_extracts_sentences_and_keywords(self):
        result = NewsSummarizer().summarize("Saudi growth continues. Investment rises.")
        self.assertEqual(result["summary"], "Saudi growth continues. Investment rises.")
        self.assertEqual(len(result["key_points"]), 2)
        self.assertIn("growth", result["keywords"])

    def test_analytics_counts_and_sentiment_percentages(self):
        analytics = AnalyticsEngine(self.store)
        stats = analytics.get_stats()
        sentiment = analytics.get_sentiment()
        self.assertEqual(stats["total_articles"], 3)
        self.assertEqual(stats["active_sources"], 2)
        self.assertEqual(stats["languages_covered"], 2)
        self.assertEqual(sentiment["total"], 3)
        self.assertEqual(sum(item["percentage"] for item in sentiment["distribution"].values()), 100)
        self.assertGreater(sentiment["distribution"]["positive"]["average_confidence"], 0.5)

    def test_api_search_filters_and_validation(self):
        response = self.client.get("/api/search?q=Saudi&sentiment=positive")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["total"], 1)
        self.assertEqual(response.json["results"][0]["sentiment"]["label"], "positive")
        quality = self.client.get("/api/search?min_source_score=70")
        self.assertEqual(quality.json["total"], 2)
        self.assertEqual(self.client.get("/api/search?min_source_score=121").status_code, 400)
        self.assertEqual(self.client.get("/api/search?start_date=bad").status_code, 400)
        self.assertEqual(self.client.get("/api/search?start_date=20260101").status_code, 400)
        self.assertEqual(self.client.get("/api/search?q=%25").json["total"], 0)
        self.assertEqual(self.client.get("/api/trends?period=invalid").status_code, 400)

    def test_dashboard_and_distribution_routes(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/dashboard").status_code, 200)
        self.assertIn(b"world-map", self.client.get("/map").data)
        countries = self.client.get("/api/countries")
        self.assertEqual(countries.status_code, 200)
        self.assertEqual(countries.json[0]["label"], "US")
        self.assertEqual(len(self.client.get("/api/topics").json), 2)
        self.assertEqual(len(self.client.get("/api/languages").json), 2)
        self.assertEqual(countries.headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(self.client.get("/api/trends?period=weekly").status_code, 200)


if __name__ == "__main__":
    unittest.main()
