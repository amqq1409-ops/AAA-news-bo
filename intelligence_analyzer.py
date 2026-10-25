"""Evidence-limited summaries of observed international news coverage."""

from collections import Counter, defaultdict
from datetime import datetime, timezone

from campaign_detector import CampaignDetector
from country_coverage_tracker import (
    CountryCoverageTracker,
    article_country,
    article_date,
    article_value,
    headline_sentiment,
)


COUNTRY_GROUPS = {
    "developed_markets": {"US", "GB", "CA", "AU", "NZ", "JP", "KR", "SG"},
    "middle_east": {"SA", "AE", "EG", "MA", "TR", "IL"},
    "brics": {"BR", "RU", "IN", "CN", "EG", "AE"},
    "european_union": {"FR", "DE", "ES", "IT", "BE", "PL", "NL", "GR", "SE", "CZ", "RO", "HU", "BG", "AT", "PT"},
}


class MediaIntelligenceAnalyzer:
    def __init__(self, articles=None, store=None):
        self.articles = list(articles) if articles is not None else None
        self.store = store

    def _articles(self):
        if self.articles is not None:
            return self.articles
        if self.store is not None and hasattr(self.store, "get_analysis_articles"):
            return self.store.get_analysis_articles()
        return []

    def comparative_analysis(self):
        articles = self._articles()
        rows = CountryCoverageTracker(articles).analyze_coverage_by_country()
        by_code = {row["country_code"]: row for row in rows}
        groups = {}
        for group_name, codes in COUNTRY_GROUPS.items():
            members = [by_code[code] for code in sorted(codes) if code in by_code]
            count = sum(row["article_count"] for row in members)
            topic_counts = Counter()
            for article in articles:
                code, _, _ = article_country(article)
                if code in codes:
                    topic_counts[str(article_value(article, "topic", "general") or "general")] += 1
            groups[group_name] = {
                "countries_observed": [row["country_code"] for row in members],
                "article_count": count,
                "top_topics": [topic for topic, _ in topic_counts.most_common(5)],
                "average_negative_headline_share": round(
                    sum(row["sentiment"]["negative"] for row in members) / len(members), 2
                ) if members else 0,
            }
        country_topic_counts = defaultdict(Counter)
        for article in articles:
            code, _, _ = article_country(article)
            country_topic_counts[code][str(article_value(article, "topic", "general") or "general")] += 1
        notable_differences = []
        for topic in sorted({topic for counts in country_topic_counts.values() for topic in counts}):
            distribution = [
                {"country_code": code, "count": counts[topic]}
                for code, counts in country_topic_counts.items()
                if counts[topic]
            ]
            if len(distribution) >= 2:
                distribution.sort(key=lambda item: item["count"])
                notable_differences.append(
                    {"topic": topic, "highest_country": distribution[-1], "lowest_country": distribution[0]}
                )
        return {
            "groups": groups,
            "notable_differences": notable_differences,
            "caveat": "Groups are analytical conveniences and reflect available collection markets, not national consensus.",
        }

    def pattern_detection(self):
        articles = self._articles()
        by_day, by_country, topics, sources = Counter(), Counter(), Counter(), Counter()
        for article in articles:
            date = article_date(article)
            if date:
                by_day[date.date().isoformat()] += 1
            code, _, _ = article_country(article)
            by_country[code] += 1
            topics[str(article_value(article, "topic", "general") or "general")] += 1
            sources[str(article_value(article, "source_name", "") or article_value(article, "domain", "") or "Unknown")] += 1
        return {
            "temporal": [{"date": day, "count": count} for day, count in sorted(by_day.items())],
            "geographic": [{"country_code": code, "count": count} for code, count in by_country.most_common()],
            "topics": [{"topic": topic, "count": count} for topic, count in topics.most_common()],
            "sources": [{"source": source, "count": count} for source, count in sources.most_common()],
            "funding": {
                "status": "not_assessed",
                "reason": "The collected article metadata contains no verified funding or ownership evidence.",
            },
            "cross_country_clusters": CampaignDetector(articles).detect_coordinated_campaigns(),
        }

    def generate_intelligence_report(self):
        articles = self._articles()
        coverage = CountryCoverageTracker(articles).analyze_coverage_by_country()
        campaigns = CampaignDetector(articles)
        candidates = campaigns.detect_coordinated_campaigns()
        bias_signals = campaigns.detect_bias_patterns()
        negative_articles = sum(headline_sentiment(article) == "negative" for article in articles)
        count = len(articles)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "executive_summary": {
                "articles_analyzed": count,
                "countries_observed": len(coverage),
                "negative_headline_share": round(negative_articles * 100 / count, 2) if count else 0,
                "interpretation": "Descriptive analysis of collected headlines and metadata; not a measure of public opinion.",
            },
            "key_threats": [
                {"type": "negative_headline_cluster", "campaign_id": item["campaign_id"], "severity": item["severity"]}
                for item in candidates if item["sentiment"]["overall"] == "negative"
            ],
            "opportunities": [
                {"country_code": row["country_code"], "positive_headline_share": row["sentiment"]["positive"]}
                for row in coverage if row["sentiment"]["positive"] > row["sentiment"]["negative"]
            ],
            "near_term_outlook": {
                "status": "insufficient_time_series" if len({article_date(a).date() for a in articles if article_date(a)}) < 7 else "descriptive_only",
                "forecast": None,
                "note": "No predictive model is fitted; short or incomplete collection windows do not support reliable forecasts.",
            },
            "recommendations": [
                "Review source and language coverage before interpreting country comparisons.",
                "Treat keyword sentiment and similarity clusters as leads for human review, not verified findings.",
                "Do not infer coordination, editorial intent, or funding from headline patterns alone.",
            ],
            "bias_signals": bias_signals,
            "coverage": coverage,
        }
