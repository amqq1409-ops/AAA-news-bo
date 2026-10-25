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
