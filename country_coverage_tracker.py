"""Descriptive country-level coverage analysis for collected article metadata."""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone


COUNTRIES = {
    "US": ("United States", "الولايات المتحدة", "🇺🇸"),
    "GB": ("United Kingdom", "المملكة المتحدة", "🇬🇧"),
    "SA": ("Saudi Arabia", "السعودية", "🇸🇦"),
    "FR": ("France", "فرنسا", "🇫🇷"),
    "DE": ("Germany", "ألمانيا", "🇩🇪"),
    "ES": ("Spain", "إسبانيا", "🇪🇸"),
    "RU": ("Russia", "روسيا", "🇷🇺"),
    "CN": ("China", "الصين", "🇨🇳"),
    "JP": ("Japan", "اليابان", "🇯🇵"),
    "KR": ("South Korea", "كوريا الجنوبية", "🇰🇷"),
    "TR": ("Turkey", "تركيا", "🇹🇷"),
    "BR": ("Brazil", "البرازيل", "🇧🇷"),
    "IT": ("Italy", "إيطاليا", "🇮🇹"),
    "IN": ("India", "الهند", "🇮🇳"),
    "ID": ("Indonesia", "إندونيسيا", "🇮🇩"),
    "CA": ("Canada", "كندا", "🇨🇦"),
    "AU": ("Australia", "أستراليا", "🇦🇺"),
    "NZ": ("New Zealand", "نيوزيلندا", "🇳🇿"),
    "SG": ("Singapore", "سنغافورة", "🇸🇬"),
    "PH": ("Philippines", "الفلبين", "🇵🇭"),
    "MY": ("Malaysia", "ماليزيا", "🇲🇾"),
    "PK": ("Pakistan", "باكستان", "🇵🇰"),
    "ZA": ("South Africa", "جنوب أفريقيا", "🇿🇦"),
    "NG": ("Nigeria", "نيجيريا", "🇳🇬"),
    "KE": ("Kenya", "كينيا", "🇰🇪"),
    "GH": ("Ghana", "غانا", "🇬🇭"),
    "IE": ("Ireland", "أيرلندا", "🇮🇪"),
    "SN": ("Senegal", "السنغال", "🇸🇳"),
    "MA": ("Morocco", "المغرب", "🇲🇦"),
    "CI": ("Côte d'Ivoire", "ساحل العاج", "🇨🇮"),
    "BE": ("Belgium", "بلجيكا", "🇧🇪"),
    "MX": ("Mexico", "المكسيك", "🇲🇽"),
    "AR": ("Argentina", "الأرجنتين", "🇦🇷"),
    "CO": ("Colombia", "كولومبيا", "🇨🇴"),
    "CL": ("Chile", "تشيلي", "🇨🇱"),
    "EG": ("Egypt", "مصر", "🇪🇬"),
    "AE": ("United Arab Emirates", "الإمارات", "🇦🇪"),
    "ET": ("Ethiopia", "إثيوبيا", "🇪🇹"),
    "TH": ("Thailand", "تايلاند", "🇹🇭"),
    "VN": ("Vietnam", "فيتنام", "🇻🇳"),
    "BD": ("Bangladesh", "بنغلاديش", "🇧🇩"),
    "TW": ("Taiwan", "تايوان", "🇹🇼"),
    "HK": ("Hong Kong", "هونغ كونغ", "🇭🇰"),
    "PL": ("Poland", "بولندا", "🇵🇱"),
    "NL": ("Netherlands", "هولندا", "🇳🇱"),
    "UA": ("Ukraine", "أوكرانيا", "🇺🇦"),
    "GR": ("Greece", "اليونان", "🇬🇷"),
    "SE": ("Sweden", "السويد", "🇸🇪"),
    "CZ": ("Czechia", "التشيك", "🇨🇿"),
    "RO": ("Romania", "رومانيا", "🇷🇴"),
    "HU": ("Hungary", "المجر", "🇭🇺"),
    "BG": ("Bulgaria", "بلغاريا", "🇧🇬"),
    "RS": ("Serbia", "صربيا", "🇷🇸"),
    "NO": ("Norway", "النرويج", "🇳🇴"),
    "DK": ("Denmark", "الدنمارك", "🇩🇰"),
    "FI": ("Finland", "فنلندا", "🇫🇮"),
    "IL": ("Israel", "إسرائيل", "🇮🇱"),
    "PT": ("Portugal", "البرتغال", "🇵🇹"),
    "AT": ("Austria", "النمسا", "🇦🇹"),
    "CH": ("Switzerland", "سويسرا", "🇨🇭"),
}
COUNTRY_LOOKUP = {
    value.casefold(): code
    for code, country_info in COUNTRIES.items()
    for value in (code, country_info[0], country_info[1])
}
COUNTRY_LOOKUP.update(
    {
        "أمريكا": "US",
        "بريطانيا": "GB",
        "روسيا الاتحادية": "RU",
        "كوريا": "KR",
        "تركيا": "TR",
        "الهند (التاميل)": "IN",
        "كندا (فرنسي)": "CA",
    }
)
POSITIVE_TERMS = {
    "success", "growth", "agreement", "cooperation", "investment", "record", "win",
    "نجاح", "نمو", "اتفاق", "تعاون", "استثمار", "إنجاز", "فوز", "ازدهار",
}
NEGATIVE_TERMS = {
    "crisis", "attack", "war", "sanction", "scandal", "controversy", "decline",
    "أزمة", "هجوم", "حرب", "عقوبات", "فضيحة", "جدل", "تراجع",
}


def article_value(article, key, default=None):
    if isinstance(article, dict):
        return article.get(key, default)
    try:
        return article[key]
    except (TypeError, KeyError, IndexError):
        return getattr(article, key, default)


def article_country(article):
    code = str(article_value(article, "country_code", "") or "").upper()
    label = str(
        article_value(article, "country")
        or article_value(article, "country_ar")
        or article_value(article, "sourcecountry")
        or ""
    ).strip()
    if code not in COUNTRIES:
        code = COUNTRY_LOOKUP.get(label.casefold(), "")
    if not code and len(label) == 2 and label.isalpha():
        code = label.upper()
    if code in COUNTRIES:
        return code, COUNTRIES[code][0], COUNTRIES[code][1]
    return code or "UNKNOWN", label or "Unknown", ""


def article_date(article):
    value = article_value(article, "published_at") or article_value(article, "published")
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def headline_sentiment(article):
    """A transparent keyword signal, not a language-aware sentiment model."""
    text = str(article_value(article, "title", "") or "").casefold()
    positive = sum(term in text for term in POSITIVE_TERMS)
    negative = sum(term in text for term in NEGATIVE_TERMS)
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


class CountryCoverageTracker:
    def __init__(self, articles=None, store=None, now=None):
        self.articles = list(articles) if articles is not None else None
        self.store = store
        self.now = now or datetime.now(timezone.utc)
        if self.now.tzinfo is None:
            self.now = self.now.replace(tzinfo=timezone.utc)
        self.now = self.now.astimezone(timezone.utc)

    def _articles(self):
        if self.articles is not None:
            return self.articles
        if self.store is not None and hasattr(self.store, "get_analysis_articles"):
            return self.store.get_analysis_articles()
        return []

    def analyze_coverage_by_country(self):
        articles = self._articles()
        groups = defaultdict(list)
        for article in articles:
            code, name, name_ar = article_country(article)
            groups[code].append((article, name, name_ar))
        total = len(articles)
        results = []
        for code, entries in groups.items():
            topics = Counter(str(article_value(a, "topic", "general") or "general") for a, _, _ in entries)
            sources = Counter(str(article_value(a, "source_name", "") or article_value(a, "domain", "") or "Unknown") for a, _, _ in entries)
            sentiments = Counter(headline_sentiment(a) for a, _, _ in entries)
            dated = [(a, article_date(a)) for a, _, _ in entries]
            dated = [(a, date) for a, date in dated if date]
            recent_start = self.now - timedelta(days=30)
            recent = [(a, date) for a, date in dated if recent_start <= date <= self.now]
            previous = [(a, date) for a, date in dated if self.now - timedelta(days=60) <= date < recent_start]
            recent_half = [headline_sentiment(a) for a, date in recent if date >= self.now - timedelta(days=15)]
            old_half = [headline_sentiment(a) for a, date in recent if date < self.now - timedelta(days=15)]
            recent_neg = sum(s == "negative" for s in recent_half) / len(recent_half) if recent_half else 0
            old_neg = sum(s == "negative" for s in old_half) / len(old_half) if old_half else 0
            if not recent or not previous:
                trend = "⚪ insufficient data"
            else:
                trend = "↗️ increasing" if len(recent) > len(previous) else "↘️ decreasing" if len(recent) < len(previous) else "➡️ stable"
            name = entries[0][1]
            name_ar = entries[0][2]
            flag = COUNTRIES.get(code, ("", "", ""))[2]
            results.append(
                {
                    "country": name,
                    "country_ar": name_ar,
                    "country_code": code,
                    "flag": flag,
                    "article_count": len(entries),
                    "percentage": round(len(entries) * 100 / total, 2) if total else 0.0,
                    "top_topics": [topic for topic, _ in topics.most_common(5)],
                    "top_sources": [source for source, _ in sources.most_common(5)],
                    "sentiment": {
                        label: round(sentiments[label] * 100 / len(entries), 2)
                        for label in ("positive", "negative", "neutral")
                    },
                    "trend": trend,
                    "last_30_days": {
                        "daily_average": round(len(recent) / 30, 2),
                        "sentiment_trend": (
                            "insufficient_data"
                            if not recent_half or not old_half
                            else "more_negative"
                            if recent_neg > old_neg
                            else "less_negative"
                            if recent_neg < old_neg
                            else "stable"
                        ),
                    },
                }
            )
        return sorted(results, key=lambda item: (-item["article_count"], item["country_code"]))

    def compare_countries(self, country1, country2):
        coverage = self.analyze_coverage_by_country()
        index = {row["country_code"]: row for row in coverage}

        def lookup(value):
            code = COUNTRY_LOOKUP.get(str(value).casefold(), str(value).upper())
            return index.get(code)

        first, second = lookup(country1), lookup(country2)
        if first is None or second is None:
            raise ValueError("Both countries must have coverage data")
        return {
            "countries": [first["country_code"], second["country_code"]],
            "article_count_difference": first["article_count"] - second["article_count"],
            "topic_differences": {
                code: sorted(set(row["top_topics"]) - set(other["top_topics"]))
                for code, row, other in (
                    (first["country_code"], first, second),
                    (second["country_code"], second, first),
                )
            },
            "sentiment_differences": {
                label: round(first["sentiment"][label] - second["sentiment"][label], 2)
                for label in ("positive", "negative", "neutral")
            },
            "source_differences": {
                code: sorted(set(row["top_sources"]) - set(other["top_sources"]))
                for code, row, other in (
                    (first["country_code"], first, second),
                    (second["country_code"], second, first),
                )
            },
        }

    def get_sensitive_countries(self, minimum_articles=3, threshold=50):
        """Return countries grouped by observed headline wording, not political stance."""
        groups = {"negative_focus": [], "positive_focus": [], "neutral": []}
        for row in self.analyze_coverage_by_country():
            if row["article_count"] < minimum_articles:
                continue
            sentiment = row["sentiment"]
            category = (
                "negative_focus"
                if sentiment["negative"] >= threshold
                else "positive_focus"
                if sentiment["positive"] >= threshold
                else "neutral"
            )
            groups[category].append(row)
        return groups
