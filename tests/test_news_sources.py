import os
import unittest
from unittest.mock import patch

from news_sources import fetch_bing_news, fetch_newsapi, fetch_sources, parse_feed


class NewsSourceTests(unittest.TestCase):
    def test_parse_feed_normalizes_rss_items(self):
        content = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><item>
          <title>Saudi Arabia news</title>
          <link>https://example.com/saudi</link>
          <pubDate>Sun, 25 Oct 2026 14:00:00 GMT</pubDate>
          <source url="https://example.com">Example News</source>
        </item></channel></rss>"""

        articles = parse_feed(content, {"lang": "ar", "country_ar": "السعودية"}, "rss")

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["domain"], "example.com")
        self.assertEqual(articles[0]["source_name"], "Example News")
        self.assertEqual(articles[0]["lang"], "ar")
        self.assertEqual(articles[0]["origin"], "rss")
        self.assertIsNotNone(articles[0]["published"])

    def test_paid_sources_skip_without_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(fetch_newsapi({"enabled": True}, float("inf")), [])
            self.assertEqual(fetch_bing_news({"enabled": True}, float("inf")), [])

    def test_sources_can_all_be_disabled(self):
        config = {
            "gdelt": {"enabled": False},
            "google_news": {"enabled": False},
            "rss": {"enabled": False, "feeds": [{"url": "https://example.com/feed"}]},
            "newsapi": {"enabled": False},
            "bing_news": {"enabled": False},
        }

        self.assertEqual(fetch_sources(config, float("inf")), ([], {}))


if __name__ == "__main__":
    unittest.main()
