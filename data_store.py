import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any


class ArticleStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        analytics_tables = {
            "country_statistics",
            "campaigns",
            "media_outlets_by_country",
            "country_topics_matrix",
        }
        if self.db_path.is_file() and self.db_path.stat().st_size:
            source = sqlite3.connect(self.db_path)
            try:
                existing = {
                    row[0]
                    for row in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                }
                if not analytics_tables.issubset(existing):
                    backup_path = self.db_path.with_suffix(self.db_path.suffix + ".bak")
                    backup = sqlite3.connect(backup_path)
                    try:
                        source.backup(backup)
                    finally:
                        backup.close()
            finally:
                source.close()
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT UNIQUE,
                    title TEXT,
                    url TEXT,
                    domain TEXT,
                    source_name TEXT,
                    lang TEXT,
                    country_ar TEXT,
                    published_at TEXT,
                    tier TEXT,
                    topic TEXT,
                    source_score INTEGER,
                    relevance_score INTEGER,
                    origin TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sent_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT,
                    title TEXT,
                    source_name TEXT,
                    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_collected INTEGER,
                    relevant INTEGER,
                    new INTEGER,
                    sent INTEGER,
                    counts_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS country_statistics (
                    id INTEGER PRIMARY KEY,
                    country_code TEXT UNIQUE,
                    country_name TEXT,
                    country_name_ar TEXT,
                    flag TEXT,
                    article_count INTEGER,
                    sentiment_positive INTEGER,
                    sentiment_negative INTEGER,
                    sentiment_neutral INTEGER,
                    trend TEXT,
                    last_updated TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY,
                    campaign_id TEXT UNIQUE,
                    detected_date TIMESTAMP,
                    campaign_type TEXT,
                    severity REAL,
                    countries_involved TEXT,
                    articles_count INTEGER,
                    confidence_score REAL,
                    status TEXT,
                    timeline_json TEXT,
                    common_keywords TEXT,
                    sentiment_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media_outlets_by_country (
                    id INTEGER PRIMARY KEY,
                    country_code TEXT,
                    outlet_name TEXT,
                    outlet_domain TEXT,
                    article_count INTEGER,
                    average_sentiment REAL,
                    credibility_score REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS country_topics_matrix (
                    id INTEGER PRIMARY KEY,
                    country_code TEXT,
                    topic TEXT,
                    article_count INTEGER,
                    percentage REAL,
                    sentiment REAL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_uid ON articles(uid)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_created_at ON articles(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sent_uid ON sent_articles(uid)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_severity ON campaigns(severity)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outlets_country ON media_outlets_by_country(country_code)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_topics_country ON country_topics_matrix(country_code)")

    def upsert_article(self, article_obj) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO articles (
                    uid, title, url, domain, source_name, lang, country_ar,
                    published_at, tier, topic, source_score, relevance_score, origin
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uid) DO UPDATE SET
                    title = excluded.title,
                    url = excluded.url,
                    domain = excluded.domain,
                    source_name = excluded.source_name,
                    lang = excluded.lang,
                    country_ar = excluded.country_ar,
                    published_at = excluded.published_at,
                    tier = excluded.tier,
                    topic = excluded.topic,
                    source_score = excluded.source_score,
                    relevance_score = excluded.relevance_score,
                    origin = excluded.origin
                """,
                (
                    getattr(article_obj, "uid", ""),
                    article_obj.title,
                    article_obj.url,
                    article_obj.domain,
                    article_obj.source_name,
                    article_obj.lang,
                    article_obj.country_ar,
                    article_obj.published.isoformat() if article_obj.published else None,
                    article_obj.tier,
                    article_obj.topic,
                    article_obj.source_score,
                    article_obj.relevance_score,
                    article_obj.origin,
                ),
            )

    def record_sent(self, article_obj) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sent_articles (uid, title, source_name, sent_at) VALUES (?, ?, ?, ?)",
                (
                    getattr(article_obj, "uid", ""),
                    article_obj.title,
                    article_obj.source_name,
                    datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                ),
            )

    def log_run(self, stats: Dict[str, int], counts: Dict[str, int], sent: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO run_logs (total_collected, relevant, new, sent, counts_json) VALUES (?, ?, ?, ?, ?)",
                (
                    stats.get("total", 0),
                    stats.get("relevant", 0),
                    stats.get("new", 0),
                    sent,
                    __import__("json").dumps(counts, ensure_ascii=False),
                ),
            )

    def get_stats_summary(self, hours: int = 24) -> Dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM articles").fetchone()["c"]
            recent = conn.execute(
                "SELECT COUNT(*) AS c FROM articles WHERE published_at IS NOT NULL AND datetime(published_at) >= datetime('now', ?) ",
                (f'-{hours} hours',),
            ).fetchone()["c"]
            by_lang = conn.execute(
                "SELECT lang, COUNT(*) AS c FROM articles GROUP BY lang ORDER BY c DESC LIMIT 10"
            ).fetchall()
            by_topic = conn.execute(
                "SELECT topic, COUNT(*) AS c FROM articles GROUP BY topic ORDER BY c DESC LIMIT 10"
            ).fetchall()
            by_source = conn.execute(
                "SELECT source_name, COUNT(*) AS c FROM articles GROUP BY source_name ORDER BY c DESC LIMIT 10"
            ).fetchall()
            sent_count = conn.execute(
                "SELECT COUNT(*) AS c FROM sent_articles WHERE sent_at >= datetime('now', ?) ",
                (f'-{hours} hours',),
            ).fetchone()["c"]

        return {
            "total_articles": total,
            "recent_articles": recent,
            "sent_last_period": sent_count,
            "by_lang": [{"label": row["lang"], "count": row["c"]} for row in by_lang],
            "by_topic": [{"label": row["topic"], "count": row["c"]} for row in by_topic],
            "by_source": [{"label": row["source_name"], "count": row["c"]} for row in by_source],
            "cutoff_hours": hours,
        }

    def stats_text(self, hours: int = 24) -> str:
        stats = self.get_stats_summary(hours=hours)
        lines = [
            f"📊 <b>إحصاءات البوت</b>",
            f"• إجمالي المقالات: {stats['total_articles']}",
            f"• خلال {hours} ساعة: {stats['recent_articles']}",
            f"• أرسلت خلال {hours} ساعة: {stats['sent_last_period']}",
            "",
            "🧠 حسب اللغة:",
        ]
        for item in stats["by_lang"][:5]:
            lines.append(f"   - {item['label']}: {item['count']}")
        lines += ["", "🗂️ حسب الموضوع:"]
        for item in stats["by_topic"][:5]:
            lines.append(f"   - {item['label']}: {item['count']}")
        lines += ["", "📡 أفضل المصادر:"]
        for item in stats["by_source"][:5]:
            lines.append(f"   - {item['label']}: {item['count']}")
        return "\n".join(lines)

    def get_analysis_articles(self):
        """Read article metadata for separate analysis modules."""
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(
                """
                SELECT title, domain, source_name, lang, country_ar, published_at, topic, origin
                FROM articles
                ORDER BY published_at DESC
                """
            ).fetchall()]

    def save_country_statistics(self, country):
        sentiment = country.get("sentiment", {})
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO country_statistics (
                    country_code, country_name, country_name_ar, flag, article_count,
                    sentiment_positive, sentiment_negative, sentiment_neutral, trend, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(country_code) DO UPDATE SET
                    country_name = excluded.country_name,
                    country_name_ar = excluded.country_name_ar,
                    flag = excluded.flag,
                    article_count = excluded.article_count,
                    sentiment_positive = excluded.sentiment_positive,
                    sentiment_negative = excluded.sentiment_negative,
                    sentiment_neutral = excluded.sentiment_neutral,
                    trend = excluded.trend,
                    last_updated = excluded.last_updated
                """,
                (
                    country.get("country_code"), country.get("country"), country.get("country_ar"),
                    country.get("flag"), country.get("article_count", 0),
                    round(country.get("article_count", 0) * sentiment.get("positive", 0) / 100),
                    round(country.get("article_count", 0) * sentiment.get("negative", 0) / 100),
                    round(country.get("article_count", 0) * sentiment.get("neutral", 0) / 100),
                    country.get("trend"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def save_campaign(self, campaign, status="observed"):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO campaigns (
                    campaign_id, detected_date, campaign_type, severity, countries_involved,
                    articles_count, confidence_score, status, timeline_json, common_keywords, sentiment_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(campaign_id) DO UPDATE SET
                    detected_date = excluded.detected_date,
                    campaign_type = excluded.campaign_type,
                    severity = excluded.severity,
                    countries_involved = excluded.countries_involved,
                    articles_count = excluded.articles_count,
                    confidence_score = excluded.confidence_score,
                    status = excluded.status,
                    timeline_json = excluded.timeline_json,
                    common_keywords = excluded.common_keywords,
                    sentiment_json = excluded.sentiment_json
                """,
                (
                    campaign.get("campaign_id"), campaign.get("detected_date"),
                    campaign.get("type"), campaign.get("severity", 0),
                    json.dumps(campaign.get("countries_involved", []), ensure_ascii=False),
                    campaign.get("articles_count", 0), campaign.get("confidence_score", 0), status,
                    json.dumps(campaign.get("timeline", {}), ensure_ascii=False),
                    json.dumps(campaign.get("common_keywords", []), ensure_ascii=False),
                    json.dumps(campaign.get("sentiment", {}), ensure_ascii=False),
                ),
            )

    @staticmethod
    def _rows_as_dicts(rows):
        return [dict(row) for row in rows]

    def query_country_stats(self, country_code):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM country_statistics WHERE country_code = ?",
                (country_code.upper(),),
            ).fetchone()
        return dict(row) if row else None

    def query_campaigns_by_severity(self, minimum_severity=0):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM campaigns WHERE severity >= ? ORDER BY severity DESC, detected_date DESC",
                (minimum_severity,),
            ).fetchall()
        return self._rows_as_dicts(rows)

    def query_country_comparison(self, country1, country2):
        first, second = self.query_country_stats(country1), self.query_country_stats(country2)
        if first is None or second is None:
            return None
        return {
            "countries": [first, second],
            "article_count_difference": first["article_count"] - second["article_count"],
            "sentiment_differences": {
                field: first[field] - second[field]
                for field in ("sentiment_positive", "sentiment_negative", "sentiment_neutral")
            },
            "topic_differences": {
                first["country_code"]: self.query_topic_distribution_by_country(first["country_code"]),
                second["country_code"]: self.query_topic_distribution_by_country(second["country_code"]),
            },
            "source_differences": {
                first["country_code"]: self.query_media_outlets_by_country(first["country_code"]),
                second["country_code"]: self.query_media_outlets_by_country(second["country_code"]),
            },
        }

    def query_campaign_timeline(self, campaign_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT campaign_id, detected_date, campaign_type, status, timeline_json FROM campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["timeline"] = json.loads(result.pop("timeline_json") or "{}")
        return result

    def query_media_outlets_by_country(self, country_code):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM media_outlets_by_country
                WHERE country_code = ? ORDER BY article_count DESC, outlet_name
                """,
                (country_code.upper(),),
            ).fetchall()
        return self._rows_as_dicts(rows)

    def query_topic_distribution_by_country(self, country_code):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM country_topics_matrix
                WHERE country_code = ? ORDER BY article_count DESC, topic
                """,
                (country_code.upper(),),
            ).fetchall()
        return self._rows_as_dicts(rows)

    def save_country_analysis(self, country, topics=(), outlets=()):
        self.save_country_statistics(country)
        country_code = country.get("country_code")
        with self._connect() as conn:
            conn.execute("DELETE FROM country_topics_matrix WHERE country_code = ?", (country_code,))
            conn.execute("DELETE FROM media_outlets_by_country WHERE country_code = ?", (country_code,))
            for topic in topics:
                conn.execute(
                    """
                    INSERT INTO country_topics_matrix
                    (country_code, topic, article_count, percentage, sentiment)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        country_code, topic.get("topic"), topic.get("article_count", 0),
                        topic.get("percentage", 0), topic.get("sentiment", 0),
                    ),
                )
            for outlet in outlets:
                conn.execute(
                    """
                    INSERT INTO media_outlets_by_country
                    (country_code, outlet_name, outlet_domain, article_count, average_sentiment, credibility_score)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        country_code, outlet.get("outlet_name"), outlet.get("outlet_domain"),
                        outlet.get("article_count", 0), outlet.get("average_sentiment", 0),
                        outlet.get("credibility_score", 0),
                    ),
                )
