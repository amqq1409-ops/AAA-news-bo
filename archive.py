"""أرشيف الأخبار المرسلة (ملف نصي لكل شهر) والموجز اليومي والأسبوعي."""
from __future__ import annotations

import collections
import datetime as dt
import html
import json
from pathlib import Path

RIYADH = dt.timezone(dt.timedelta(hours=3))


class Archive:
    def __init__(self, folder: str | Path):
        self.folder = Path(folder)
        self.pending = []

    def add(self, record: dict):
        self.pending.append(record)

    def save(self):
        if not self.pending:
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        by_month = collections.defaultdict(list)
        for rec in self.pending:
            month = dt.datetime.fromtimestamp(rec["ts"], RIYADH).strftime("%Y-%m")
            by_month[month].append(rec)
        for month, records in by_month.items():
            with (self.folder / f"{month}.jsonl").open("a", encoding="utf-8") as fh:
                for rec in records:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.pending = []

    def load_since(self, start: dt.datetime) -> list[dict]:
        """كل السجلات منذ لحظة معيّنة (من الملفات ومن غير المحفوظ بعد)."""
        start_ts = start.timestamp()
        months = set()
        cursor = start.astimezone(RIYADH).replace(day=1)
        now = dt.datetime.now(RIYADH)
        while (cursor.year, cursor.month) <= (now.year, now.month):
            months.add(cursor.strftime("%Y-%m"))
            cursor = (cursor.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        out = []
        for month in sorted(months):
            path = self.folder / f"{month}.jsonl"
            if not path.exists():
                continue
            for line in path.read_text("utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict) and rec.get("ts", 0) >= start_ts:
                    out.append(rec)
        out.extend(r for r in self.pending if r.get("ts", 0) >= start_ts)
        return out


def _count_lines(title: str, counter: collections.Counter, labels: dict | None = None, top: int = 6) -> list[str]:
    if not counter:
        return []
    items = " • ".join(f"{html.escape((labels or {}).get(k, k))} {v}" for k, v in counter.most_common(top))
    return ["", f"<b>{title}</b>", items]


def build_digest(records: list[dict], heading: str, top_n: int, topic_labels: dict, region_labels: dict,
                 tone_labels: dict, subject_labels: dict | None = None) -> str | None:
    news = [r for r in records if r.get("origin") != "x"]
    if not records:
        return None
    lines = [f"🗞 <b>{html.escape(heading)}</b>", f"عدد ما نُشر: {len(records)} (منها {len(records) - len(news)} من X)"]

    ranked = sorted(news, key=lambda r: (r.get("score", 0) + 6 * min(r.get("also", 0), 5), r.get("ts", 0)), reverse=True)
    if ranked:
        lines += ["", "<b>أهم الأخبار</b>"]
    for i, rec in enumerate(ranked[:top_n], start=1):
        title = (rec.get("title_ar") or rec.get("title") or "")[:110]
        tail = html.escape(rec.get("source") or rec.get("domain") or "")
        if rec.get("also"):
            tail += f" +{rec['also']}"
        lines.append(f'{i}. <a href="{html.escape(rec.get("url", ""), quote=True)}">{html.escape(title)}</a> — {tail}')

    subjects = collections.Counter(r["subject"] for r in news if r.get("subject"))
    lines += _count_lines("حسب الدولة", subjects, subject_labels)
    lines += _count_lines("حسب المنطقة", collections.Counter(r.get("region") or "unknown" for r in news), region_labels, top=11)
    lines += _count_lines("حسب الموضوع", collections.Counter(r.get("topic") or "general" for r in news), topic_labels)
    tones = collections.Counter(r["tone"] for r in news if r.get("tone"))
    lines += _count_lines("حسب النبرة", tones, tone_labels)
    if tones:
        critical_by_region = collections.Counter(r.get("region") or "unknown" for r in news if r.get("tone") == "critical")
        lines += _count_lines("أكثر المناطق نقدًا", critical_by_region, region_labels, top=3)
    lines += _count_lines("أكثر الدول تغطية", collections.Counter(r["country"] for r in news if r.get("country")), top=8)
    text = "\n".join(lines)
    while len(text) > 3900 and len(lines) > 4:  # حد تلقرام 4096 حرفًا
        lines.pop()
        text = "\n".join(lines)
    return text
