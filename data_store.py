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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_uid ON articles(uid)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_created_at ON articles(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sent_uid ON sent_articles(uid)")

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
            languages_covered = conn.execute(
                "SELECT COUNT(DISTINCT lang) AS c FROM articles WHERE lang IS NOT NULL AND trim(lang) != ''"
            ).fetchone()["c"]
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
            "languages_covered": languages_covered,
            "recent_articles": recent,
            "sent_last_period": sent_count,
            "by_lang": [{"label": row["lang"], "count": row["c"]} for row in by_lang],
            "by_topic": [{"label": row["topic"], "count": row["c"]} for row in by_topic],
            "by_source": [{"label": row["source_name"], "count": row["c"]} for row in by_source],
            "cutoff_hours": hours,
        }

    def get_country_distribution(self) -> list[Dict[str, Any]]:
        return self.get_distribution("country")

    def get_topic_distribution(self) -> list[Dict[str, Any]]:
        return self.get_distribution("topic")

    def get_language_distribution(self) -> list[Dict[str, Any]]:
        return self.get_distribution("language")

    def get_distribution(self, dimension: str) -> list[Dict[str, Any]]:
        columns = {"country": "country_ar", "topic": "topic", "language": "lang"}
        column = columns.get(dimension)
        if column is None:
            raise ValueError("unsupported article distribution")
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {column} AS label, COUNT(*) AS count
                FROM articles
                WHERE {column} IS NOT NULL AND trim({column}) != ''
                GROUP BY {column}
                ORDER BY count DESC, label
                """
            ).fetchall()
        return [{"label": row["label"], "count": row["count"]} for row in rows]

    def get_source_performance(self) -> list[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_name AS label, COUNT(*) AS count,
                       ROUND(AVG(source_score), 1) AS average_score
                FROM articles
                WHERE source_name IS NOT NULL AND trim(source_name) != ''
                GROUP BY source_name
                ORDER BY count DESC, label
                """
            ).fetchall()
        return [
            {"label": row["label"], "count": row["count"], "average_score": row["average_score"]}
            for row in rows
        ]

    def get_daily_trends(self, days: int = 30, period: str = "daily") -> list[Dict[str, Any]]:
        days = max(1, min(int(days), 365))
        date_expression = {
            "daily": "date(published_at)",
            "weekly": "strftime('%Y-W%W', published_at)",
            "monthly": "strftime('%Y-%m', published_at)",
        }.get(period)
        if date_expression is None:
            raise ValueError("period must be daily, weekly, or monthly")
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {date_expression} AS date, COUNT(*) AS count
                FROM articles
                WHERE published_at IS NOT NULL
                  AND datetime(published_at) >= datetime('now', ?)
                GROUP BY date
                ORDER BY date
                """,
                (f"-{days} days",),
            ).fetchall()
        return [{"date": row["date"], "count": row["count"]} for row in rows]

    def search_articles(self, filters: Dict[str, Any] | None = None) -> list[Dict[str, Any]]:
        filters = filters or {}
        clauses = []
        values = []
        for parameter, column in (
            ("country", "country_ar"),
            ("language", "lang"),
            ("topic", "topic"),
            ("source", "source_name"),
        ):
            value = filters.get(parameter)
            if value:
                clauses.append(f"{column} = ?")
                values.append(value)
        start_date = filters.get("start_date")
        if start_date:
            clauses.append("date(published_at) >= date(?)")
            values.append(start_date)
        end_date = filters.get("end_date")
        if end_date:
            clauses.append("date(published_at) <= date(?)")
            values.append(end_date)
        min_source_score = filters.get("min_source_score")
        if min_source_score is not None:
            clauses.append("source_score >= ?")
            values.append(min_source_score)
        query = filters.get("q")
        if query:
            clauses.append(
                "(title LIKE ? ESCAPE '\\' OR source_name LIKE ? ESCAPE '\\' "
                "OR domain LIKE ? ESCAPE '\\')"
            )
            escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped_query}%"
            values.extend((pattern, pattern, pattern))

        sql = "SELECT * FROM articles"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY datetime(published_at) DESC, id DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, values).fetchall()
        return [dict(row) for row in rows]

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
