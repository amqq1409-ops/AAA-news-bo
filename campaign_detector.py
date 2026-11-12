"""Heuristic detection of cross-market coverage patterns.

Signals indicate similarity in collected headlines; they do not establish intent,
coordination, factuality, or the identity of an actor.
"""

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations

from country_coverage_tracker import article_country, article_date, article_value, headline_sentiment


STOP_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "about", "after", "into",
    "saudi", "arabia", "kingdom", "السعودية", "السعوديه", "عن", "في", "من", "إلى", "على",
}


def _tokens(article):
    title = str(article_value(article, "title", "") or "").casefold()
    return {
        token for token in re.findall(r"[^\W_]+", title, flags=re.UNICODE)
        if len(token) > 2 and token not in STOP_WORDS
    }


def _similarity(left, right):
    first, second = _tokens(left), _tokens(right)
    return len(first & second) / len(first | second) if first and second else 0.0


class CampaignDetector:
    def __init__(self, articles, similarity_threshold=0.45, max_time_gap_days=7):
        self.articles = list(articles)
        self.similarity_threshold = similarity_threshold
        self.max_time_gap_days = max_time_gap_days

    def _clusters(self):
        count = len(self.articles)
        parents = list(range(count))

        def find(index):
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def union(left, right):
            root_left, root_right = find(left), find(right)
            if root_left != root_right:
                parents[root_right] = root_left

        for left, right in combinations(range(count), 2):
            first_date, second_date = article_date(self.articles[left]), article_date(self.articles[right])
            if first_date and second_date and abs((first_date - second_date).days) > self.max_time_gap_days:
                continue
            if _similarity(self.articles[left], self.articles[right]) >= self.similarity_threshold:
                union(left, right)
        clusters = defaultdict(list)
        for index, article in enumerate(self.articles):
            clusters[find(index)].append(article)
        return [cluster for cluster in clusters.values() if len(cluster) >= 2]

    def detect_coordinated_campaigns(self):
        """Return potential cross-country headline clusters without causal attribution."""
        results = []
        today = datetime.now(timezone.utc).date().isoformat()
        for sequence, cluster in enumerate(self._clusters(), 1):
            by_country = defaultdict(list)
            for article in cluster:
                code, _, _ = article_country(article)
                by_country[code].append(article)
            if len(by_country) < 2 or "UNKNOWN" in by_country:
                continue
            dates = [date for date in (article_date(a) for a in cluster) if date]
            if not dates:
                continue
            all_tokens = Counter(token for article in cluster for token in _tokens(article))
            common_keywords = [word for word, count in all_tokens.most_common(8) if count >= 2]
            sentiments = Counter(headline_sentiment(article) for article in cluster)
            majority = sentiments.most_common(1)[0][0]
            similarity = sum(
                _similarity(left, right)
                for left, right in combinations(cluster, 2)
            ) / max(1, len(cluster) * (len(cluster) - 1) / 2)
            country_factor = min(len(by_country) / 4, 1)
            severity = round(min(1.0, similarity * 0.6 + country_factor * 0.2 + (0.2 if majority == "negative" else 0)), 2)
            campaign_id = f"cluster_{today.replace('-', '')}_{sequence:03d}"
            country_sentiment = {
                code: Counter(headline_sentiment(article) for article in items).most_common(1)[0][0]
                for code, items in sorted(by_country.items())
            }
            start, end = min(dates), max(dates)
            results.append(
                {
                    "campaign_id": campaign_id,
                    "detected_date": today,
                    "type": "cross_country_negative_cluster" if majority == "negative" else "cross_country_similar_coverage",
                    "severity": severity,
                    "countries_involved": sorted(by_country),
                    "countries_count": len(by_country),
                    "articles_count": len(cluster),
                    "common_keywords": common_keywords,
                    "common_sources": [
                        source for source, _ in Counter(
                            str(article_value(a, "source_name", "") or article_value(a, "domain", "") or "Unknown")
                            for a in cluster
                        ).most_common(5)
                    ],
                    "timeline": {
                        "start_date": start.date().isoformat(),
                        "peak_date": Counter(date.date().isoformat() for date in dates).most_common(1)[0][0],
                        "end_date": end.date().isoformat(),
                    },
                    "sentiment": {"overall": majority, "by_country": country_sentiment},
                    "bias_level": "unassessed",
                    "confidence_score": round(similarity * country_factor, 2),
                    "interpretation": "similar cross-country coverage; coordination is not established",
                }
            )
        return sorted(results, key=lambda item: (-item["severity"], item["campaign_id"]))

    def detect_bias_patterns(self, minimum_articles=5, concentration_threshold=0.6):
        by_country = defaultdict(list)
        for article in self.articles:
            code, _, _ = article_country(article)
            by_country[code].append(article)
        results = []
        for code, articles in sorted(by_country.items()):
            if len(articles) < minimum_articles:
                continue
            topics = Counter(str(article_value(a, "topic", "general") or "general") for a in articles)
            top_topic, top_count = topics.most_common(1)[0]
            share = top_count / len(articles)
            all_topics = {str(article_value(a, "topic", "general") or "general") for a in self.articles}
            country_topics = set(topics)
            results.append(
                {
                    "country_code": code,
                    "articles_count": len(articles),
                    "topic_shares": {topic: round(count / len(articles), 3) for topic, count in topics.items()},
                    "dominant_topic": top_topic if share >= concentration_threshold else None,
                    "concentration_ratio": round(share, 3),
                    "topics_not_observed": sorted(all_topics - country_topics),
                    "coverage_signal": "topic_concentrated" if share >= concentration_threshold else "diverse",
                    "interpretation": "coverage distribution only; editorial bias cannot be inferred from headline counts",
                }
            )
        return results

    def detect_narrative_shifts(self, minimum_articles=2):
        by_country = defaultdict(list)
        for article in self.articles:
            date = article_date(article)
            if date:
                code, _, _ = article_country(article)
                by_country[code].append((date, article))
        shifts = []
        for code, dated_articles in sorted(by_country.items()):
            if len(dated_articles) < minimum_articles:
                continue
            dated_articles.sort(key=lambda item: item[0])
            midpoint = len(dated_articles) // 2
            earlier = Counter(token for _, article in dated_articles[:midpoint] for token in _tokens(article))
            later = Counter(token for _, article in dated_articles[midpoint:] for token in _tokens(article))
            earlier_top = {word for word, _ in earlier.most_common(5)}
            later_top = {word for word, _ in later.most_common(5)}
            added, dropped = sorted(later_top - earlier_top), sorted(earlier_top - later_top)
            if added or dropped:
                shifts.append(
                    {
                        "country_code": code,
                        "earlier_keywords": sorted(earlier_top),
                        "later_keywords": sorted(later_top),
                        "added_keywords": added,
                        "dropped_keywords": dropped,
                        "observed_from": dated_articles[0][0].date().isoformat(),
                        "observed_to": dated_articles[-1][0].date().isoformat(),
                        "interpretation": "headline vocabulary changed; a change in official narrative is not established",
                    }
                )
        return shifts
