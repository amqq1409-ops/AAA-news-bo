import os
import threading
import time
import unittest
from unittest.mock import Mock, patch

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

    def test_newsapi_all_languages_omits_language_parameter(self):
        response = Mock()
        response.json.return_value = {
            "status": "ok",
            "articles": [{
                "title": "Saudi Arabia investment",
                "url": "https://example.com/news",
                "source": {"name": "Example"},
                "publishedAt": "2026-10-25T14:00:00Z",
            }],
        }
        with patch.dict(os.environ, {"NEWSAPI_API_KEY": "test-key"}), patch(
            "news_sources._request", return_value=response
        ) as request:
            articles = fetch_newsapi({"enabled": True, "language": "all"}, float("inf"))

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["origin"], "newsapi")
        self.assertNotIn("language", request.call_args.kwargs["params"])

    def test_bing_source_requires_configured_endpoint(self):
        with patch.dict(os.environ, {"BING_NEWS_API_KEY": "test-key"}), patch(
            "news_sources._request"
        ) as request:
            self.assertEqual(fetch_bing_news({"enabled": True}, float("inf")), [])

        request.assert_not_called()

    def test_sources_can_all_be_disabled(self):
        config = {
            "gdelt": {"enabled": False},
            "google_news": {"enabled": False},
            "rss": {"enabled": False, "feeds": [{"url": "https://example.com/feed"}]},
            "newsapi": {"enabled": False},
            "bing_news": {"enabled": False},
        }

        self.assertEqual(fetch_sources(config, float("inf")), ([], {}))

    def test_enabled_sources_are_fetched_in_parallel(self):
        barrier = threading.Barrier(3)

        def fetch(*args):
            barrier.wait(timeout=2)
            return [{"title": "parallel"}]

        config = {
            "gdelt": {"enabled": True, "languages": ["english"]},
            "google_news": {"enabled": True, "editions": [{"lang": "en", "gl": "US"}]},
            "rss": {"enabled": True, "feeds": [{"name": "feed", "url": "https://example.com/rss"}]},
            "source_workers": 3,
        }
        with patch("news_sources.fetch_gdelt_language", side_effect=fetch), patch(
            "news_sources.fetch_gnews_edition", side_effect=fetch
        ), patch("news_sources.fetch_rss", side_effect=fetch):
            articles, counts = fetch_sources(config, time.monotonic() + 10)

        self.assertEqual(len(articles), 3)
        self.assertEqual(len(counts), 3)


if __name__ == "__main__":
    unittest.main()
