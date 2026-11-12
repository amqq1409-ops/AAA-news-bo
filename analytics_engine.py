from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from sentiment_analyzer import SentimentAnalyzer


class AnalyticsEngine:
    def __init__(self, store):
        self.store = store
        self.sentiment_analyzer = SentimentAnalyzer()

    def get_stats(self, hours: int = 24) -> dict[str, Any]:
        stats = self.store.get_stats_summary(hours=hours)
        stats["active_sources"] = len(self.store.get_source_performance())
        stats["countries_covered"] = len(self.store.get_country_distribution())
        stats["by_country"] = self.store.get_country_distribution()[:10]
        return stats

    def get_sentiment(self) -> dict[str, Any]:
        articles = self.store.search_articles()
        counts = Counter()
        confidence_totals = Counter()
        by_topic = defaultdict(Counter)
        by_country = defaultdict(Counter)
        for article in articles:
            analysis = self.sentiment_analyzer.analyze(article.get("title"))
            label = analysis["label"]
            counts[label] += 1
            confidence_totals[label] += analysis["confidence"]
            by_topic[article.get("topic") or "general"][label] += 1
            country = article.get("country_ar")
            if country:
                by_country[country][label] += 1

        total = sum(counts.values())
        distribution = {
            label: {
                "count": counts[label],
                "percentage": round(counts[label] * 100 / total, 1) if total else 0,
                "average_confidence": round(confidence_totals[label] / counts[label], 2)
                if counts[label] else 0,
            }
            for label in ("positive", "negative", "neutral")
        }
        if total:
            largest_group = max(distribution, key=lambda label: counts[label])
            rounded_total = sum(item["percentage"] for item in distribution.values())
            distribution[largest_group]["percentage"] = round(
                distribution[largest_group]["percentage"] + 100 - rounded_total, 1
            )
        return {
            "total": total,
            "distribution": distribution,
            "by_topic": {key: dict(value) for key, value in by_topic.items()},
            "by_country": {key: dict(value) for key, value in by_country.items()},
        }

    def get_sources(self) -> list[dict[str, Any]]:
        return self.store.get_source_performance()

    def get_trends(self, days: int = 30, period: str = "daily") -> dict[str, Any]:
        values = self.store.get_daily_trends(days, period)
        daily = values if period == "daily" else self.store.get_daily_trends(days, "daily")
        daily_counts = {item["date"]: item["count"] for item in daily}
        today = date.today()
        recent = [
            daily_counts.get((today - timedelta(days=offset)).isoformat(), 0)
            for offset in range(6, -1, -1)
        ]
        forecast = round(sum(recent) / len(recent), 1) if recent else 0
        return {
            "period_days": days,
            "period": period,
            "data": values,
            "forecast_next_day": forecast,
        }

    def search(self, filters: dict[str, Any]) -> dict[str, Any]:
        articles = self.store.search_articles(filters)
        sentiment = filters.get("sentiment")
        results = []
        for article in articles:
            analysis = self.sentiment_analyzer.analyze(article.get("title"))
            if sentiment and analysis["label"] != sentiment:
                continue
            article["sentiment"] = analysis
            results.append(article)
        try:
            limit = max(1, min(int(filters.get("limit", 50)), 100))
            offset = max(0, int(filters.get("offset", 0)))
        except (TypeError, ValueError):
            limit, offset = 50, 0
        return {
            "total": len(results),
            "limit": limit,
            "offset": offset,
            "results": results[offset:offset + limit],
        }
