# Saudi News Watch

A Saudi-focused news collection bot with an optional local analytics dashboard.

## Dashboard

Install the project requirements, run the news bot to populate `data/news.db`, then start the dashboard:

```bash
pip install -r requirements.txt
python dashboard_api.py
```

Open `http://127.0.0.1:5000`. The dashboard includes headline statistics, source-country and topic distribution, bilingual keyword-based sentiment estimates, trends, source performance, and filtered article search. See [API_DOCS.md](API_DOCS.md) and [DASHBOARD_GUIDE.md](DASHBOARD_GUIDE.md) for details and limitations.

The dashboard is read-only. Sentiment and extractive summary functionality operate on stored article titles because full article text is not part of the existing database schema.
