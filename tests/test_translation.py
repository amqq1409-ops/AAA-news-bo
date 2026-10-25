import unittest
from unittest.mock import Mock, patch

import news_bot


class TranslationTests(unittest.TestCase):
    @patch("news_bot.http_get")
    def test_translate_title_joins_api_segments(self, http_get):
        response = Mock(status_code=200)
        response.json.return_value = [[["الرياض", "Riyadh"], [" اليوم", " today"]], None, "en"]
        http_get.return_value = response

        self.assertEqual(news_bot.translate_title("Riyadh today"), "الرياض اليوم")
        self.assertIn("tl=ar", http_get.call_args.args[0])

    @patch("news_bot.http_get")
    def test_translate_title_returns_none_for_failed_or_invalid_response(self, http_get):
        http_get.return_value = None
        self.assertIsNone(news_bot.translate_title("Riyadh today"))

        response = Mock(status_code=200)
        response.json.return_value = {"unexpected": "payload"}
        http_get.return_value = response
        self.assertIsNone(news_bot.translate_title("Riyadh today"))

    @patch("news_bot.time.sleep")
    @patch("news_bot.translate_title", return_value="الرياض اليوم")
    @patch("news_bot.select_articles")
    @patch("news_bot.fetch_gdelt", return_value=([], {}))
    @patch("news_bot.fetch_gnews")
    def test_run_sends_translated_title_when_enabled(
        self, fetch_gnews, fetch_gdelt, select_articles, translate_title, _sleep
    ):
        article = news_bot.Article(
            "Riyadh today", "https://example.com/news", "example.com", "Example",
            "en", "", None, "gnews"
        )
        fetch_gnews.return_value = ([article], {})
        select_articles.return_value = [article]
        telegram = Mock()
        telegram.send_text.return_value = True
        state = Mock()

        news_bot.run({"translate_titles": True}, state, telegram)

        translate_title.assert_called_once_with("Riyadh today")
        self.assertIn("الرياض اليوم", telegram.send_text.call_args.args[0])

    @patch("news_bot.time.sleep")
    @patch("news_bot.translate_title")
    @patch("news_bot.select_articles")
    @patch("news_bot.fetch_gdelt", return_value=([], {}))
    @patch("news_bot.fetch_gnews")
    def test_run_respects_disabled_translation(
        self, fetch_gnews, fetch_gdelt, select_articles, translate_title, _sleep
    ):
        article = news_bot.Article(
            "Riyadh today", "https://example.com/news", "example.com", "Example",
            "en", "", None, "gnews"
        )
        fetch_gnews.return_value = ([article], {})
        select_articles.return_value = [article]
        telegram = Mock()
        telegram.send_text.return_value = True

        news_bot.run({"translate_titles": False}, Mock(), telegram)

        translate_title.assert_not_called()
        self.assertNotIn("🔁", telegram.send_text.call_args.args[0])

    @patch("news_bot.time.sleep")
    @patch("news_bot.translate_title")
    @patch("news_bot.select_articles")
    @patch("news_bot.fetch_gdelt", return_value=([], {}))
    @patch("news_bot.fetch_gnews")
    def test_run_skips_translation_for_arabic_titles(
        self, fetch_gnews, fetch_gdelt, select_articles, translate_title, _sleep
    ):
        article = news_bot.Article(
            "الرياض اليوم", "https://example.com/news", "example.com", "Example",
            "ar", "", None, "gnews"
        )
        fetch_gnews.return_value = ([article], {})
        select_articles.return_value = [article]
        telegram = Mock()
        telegram.send_text.return_value = True

        news_bot.run({"translate_titles": True}, Mock(), telegram)

        translate_title.assert_not_called()
        self.assertNotIn("🔁", telegram.send_text.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
