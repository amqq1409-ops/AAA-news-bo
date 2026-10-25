import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from country_mapper import CountryMapper
from data_store import ArticleStore
from news_bot import Article, parse_gnews_rss, select_articles
from nlp_processor import NLPProcessor, classify_topic_details


class CountryMapperTests(unittest.TestCase):
    def test_extracts_country_names_and_flags(self):
        countries = CountryMapper().extract("Saudi Arabia and الولايات المتحدة")

        self.assertEqual([country["code"] for country in countries], ["SA", "US"])
        self.assertEqual(countries[0]["name_ar"], "السعودية")
        self.assertEqual(countries[0]["flag"], "🇸🇦")


class NLPProcessorTests(unittest.TestCase):
    def test_extracts_entities_and_topic_confidence(self):
        result = NLPProcessor(spacy_model="").analyze(
            "Mohammed bin Salman visits Riyadh for an investment announcement",
            "en",
        )

        self.assertEqual(result["topic"], "economy")
        self.assertGreater(result["topic_confidence"], 0.5)
        self.assertGreaterEqual(result["confidence_score"], 0.65)
        self.assertIn({"text": "Riyadh", "label": "LOCATION"}, result["entities"])
        self.assertIn({"text": "Mohammed bin Salman", "label": "PERSON"}, result["entities"])

    def test_topic_classifier_uses_multiple_keyword_evidence(self):
        topic, confidence = classify_topic_details("Saudi investment and economic market growth")

        self.assertEqual(topic, "economy")
        self.assertGreater(confidence, 0.5)
        self.assertEqual(classify_topic_details("A party met with local officials")[0], "general")

    def test_analyzes_country_mentions_from_rss_description(self):
        articles = parse_gnews_rss(
            b"""<rss><channel><item>
            <title>Investment plans announced</title>
            <link>https://example.com/article</link>
            <description>Saudi Arabia and France discuss a new investment partnership.</description>
            </item></channel></rss>""",
            {"lang": "en"},
        )
        analysis = NLPProcessor(spacy_model="").analyze(articles[0].text, "en")

        self.assertEqual(
            [country["code"] for country in analysis["countries"]],
            ["SA", "FR"],
        )

    def test_nlp_relevance_can_keep_non_keyword_title(self):
        article = Article(
            "Prince Mohammed bin Salman outlines an investment plan",
            "https://reuters.com/article",
            "reuters.com",
            "Reuters",
            "en",
            "",
            None,
            "test",
        )
        state = SimpleNamespace(seen=lambda _uid: False)

        selected = select_articles(
            [article],
            {
                "title_must_match_any": ["Saudi Arabia"],
                "strict_title_filter": True,
                "max_per_language": 2,
                "max_messages_per_run": 2,
            },
            state,
            NLPProcessor(spacy_model=""),
        )

        self.assertEqual(selected, [article])
        self.assertGreaterEqual(article.confidence_score, 0.65)


class ArticleStoreTests(unittest.TestCase):
    def test_persists_enrichment_and_normalized_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ArticleStore(Path(tmp) / "news.db")
            article = Article(
                "Saudi Arabia investment",
                "https://example.com/news",
                "example.com",
                "Example",
                "en",
                "",
                None,
                "test",
            )
            article.uid = "article-1"
            article.countries = [{
                "code": "SA",
                "name": "Saudi Arabia",
                "name_ar": "السعودية",
                "flag": "🇸🇦",
            }]
            article.entities = [{"text": "Riyadh", "label": "LOCATION"}]
            article.languages = ["en", "ar"]
            article.confidence_score = 0.9
            article.topic_confidence = 0.8
            store.upsert_article(article)

            with sqlite3.connect(store.db_path) as conn:
                saved = conn.execute(
                    "SELECT countries, entities, languages, confidence_score, topic_confidence FROM articles WHERE uid = ?",
                    (article.uid,),
                ).fetchone()
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM countries").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM article_countries").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM article_entities").fetchone()[0], 1)

            self.assertIn('"code": "SA"', saved[0])
            self.assertIn('"label": "LOCATION"', saved[1])
            self.assertEqual(saved[2], '["en", "ar"]')
            self.assertEqual(saved[3:], (0.9, 0.8))

    def test_migrates_existing_articles_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "old.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE articles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT UNIQUE, title TEXT,
                        url TEXT, domain TEXT, source_name TEXT, lang TEXT, country_ar TEXT,
                        published_at TEXT, tier TEXT, topic TEXT, source_score INTEGER,
                        relevance_score INTEGER, origin TEXT,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            ArticleStore(db_path)

            with sqlite3.connect(db_path) as conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}

            self.assertTrue({"countries", "entities", "confidence_score", "topic_confidence"} <= columns)


if __name__ == "__main__":
    unittest.main()
