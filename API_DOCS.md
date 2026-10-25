# Dashboard API

Run `python dashboard_api.py` and open `http://127.0.0.1:5000`. The API reads the existing SQLite database at `data/news.db`; set `NEWS_DB_PATH` to use another database.

All endpoints return JSON, allow cross-origin GET requests, and cache analytical responses for 30 seconds.

| Endpoint | Description |
| --- | --- |
| `GET /api/stats?hours=24` | Article totals, recent articles, languages, topics, sources, and coverage counts. `hours` is 1–8760. |
| `GET /api/countries` | Article counts grouped by the stored source-country value (`country_ar`). |
| `GET /api/languages` | Full language distribution. |
| `GET /api/topics` | Full topic distribution. |
| `GET /api/sentiment` | Positive/negative/neutral counts and percentages, confidence, and topic/country breakdowns. |
| `GET /api/trends?days=30&period=daily` | Daily, weekly, or monthly article counts and a seven-day-average next-day estimate. |
| `GET /api/sources` | Article count and average source score per source. |
| `GET /api/search?q=&country=&language=&topic=&source=&start_date=&end_date=&sentiment=&min_source_score=&limit=50&offset=0` | Filtered article search; dates use `YYYY-MM-DD`, source score is 0–120, and limit is capped at 100. |
| `GET /api/summarize?text=...` | Extractive two-sentence summary and keywords for supplied text (maximum 5000 characters). |

Search terms are matched against the stored title, source name, and domain. Sentiment and dashboard summary analysis use stored titles because the current article schema does not store article bodies. Sentiment is a lightweight English/Arabic keyword estimate, not a trained classifier. Country grouping represents the country value supplied by the news source and is not necessarily the geographic subject of a story.

Invalid parameters return HTTP 400 with an `error` field. Unexpected server errors return HTTP 500 without exposing internal exception details. The API is read-only and is intended for trusted/local use; set `DASHBOARD_HOST` explicitly before exposing it on a network.
