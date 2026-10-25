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
                    countries TEXT NOT NULL DEFAULT '[]',
                    entities TEXT NOT NULL DEFAULT '[]',
                    languages TEXT NOT NULL DEFAULT '[]',
                    confidence_score REAL NOT NULL DEFAULT 0,
                    topic_confidence REAL NOT NULL DEFAULT 0,
                    origin TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(articles)")}
            migrations = {
                "countries": "TEXT NOT NULL DEFAULT '[]'",
                "entities": "TEXT NOT NULL DEFAULT '[]'",
                "languages": "TEXT NOT NULL DEFAULT '[]'",
                "confidence_score": "REAL NOT NULL DEFAULT 0",
                "topic_confidence": "REAL NOT NULL DEFAULT 0",
            }
            for name, definition in migrations.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE articles ADD COLUMN {name} {definition}")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS countries (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    name_ar TEXT,
                    flag TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    label TEXT NOT NULL,
                    UNIQUE(name, label)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS article_countries (
                    article_id INTEGER NOT NULL,
                    country_code TEXT NOT NULL,
                    PRIMARY KEY(article_id, country_code)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS article_entities (
                    article_id INTEGER NOT NULL,
                    entity_id INTEGER NOT NULL,
                    PRIMARY KEY(article_id, entity_id)
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
        uid = getattr(article_obj, "uid", "") or ""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO articles (
                    uid, title, url, domain, source_name, lang, country_ar,
                    published_at, tier, topic, source_score, relevance_score,
                    countries, entities, languages, confidence_score, topic_confidence, origin
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    countries = excluded.countries,
                    entities = excluded.entities,
                    languages = excluded.languages,
                    confidence_score = excluded.confidence_score,
                    topic_confidence = excluded.topic_confidence,
                    origin = excluded.origin
                """,
                (
                    uid,
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
                    json.dumps(getattr(article_obj, "countries", []), ensure_ascii=False),
                    json.dumps(getattr(article_obj, "entities", []), ensure_ascii=False),
                    json.dumps(getattr(article_obj, "languages", [article_obj.lang]), ensure_ascii=False),
                    getattr(article_obj, "confidence_score", 0.0),
                    getattr(article_obj, "topic_confidence", 0.0),
                    article_obj.origin,
                ),
            )
            article_id = conn.execute(
                "SELECT id FROM articles WHERE uid = ?",
                (uid,),
            ).fetchone()["id"]
            conn.execute("DELETE FROM article_countries WHERE article_id = ?", (article_id,))
            conn.execute("DELETE FROM article_entities WHERE article_id = ?", (article_id,))
            for country in getattr(article_obj, "countries", []):
                if not isinstance(country, dict) or not country.get("code"):
                    continue
                conn.execute(
                    """
                    INSERT INTO countries (code, name, name_ar, flag) VALUES (?, ?, ?, ?)
                    ON CONFLICT(code) DO UPDATE SET
                        name = excluded.name, name_ar = excluded.name_ar, flag = excluded.flag
                    """,
                    (country["code"], country.get("name", country["code"]), country.get("name_ar", ""), country.get("flag", "")),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO article_countries (article_id, country_code) VALUES (?, ?)",
                    (article_id, country["code"]),
                )
            for entity in getattr(article_obj, "entities", []):
                if not isinstance(entity, dict) or not entity.get("text") or not entity.get("label"):
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO entities (name, label) VALUES (?, ?)",
                    (entity["text"], entity["label"]),
                )
                entity_id = conn.execute(
                    "SELECT id FROM entities WHERE name = ? AND label = ?",
                    (entity["text"], entity["label"]),
                ).fetchone()["id"]
                conn.execute(
                    "INSERT OR IGNORE INTO article_entities (article_id, entity_id) VALUES (?, ?)",
                    (article_id, entity_id),
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
