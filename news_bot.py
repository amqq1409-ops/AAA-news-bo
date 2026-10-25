from __future__ import annotations

# مراقب أخبار السعودية — نسخة محسنة
# GDELT + Google News + فلترة ذكية + تقييم جودة المصدر + ترتيب حسب الأهمية + تحجيم التكرار

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

import requests
import yaml

log = logging.getLogger("newsbot")
ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "data" / "state.json"
RIYADH = dt.timezone(dt.timedelta(hours=3))
UA = "Mozilla/5.0 (compatible; SaudiNewsWatch/2.1; +https://github.com)"

GDELT_LANG_CODES = {
    "english": "en", "arabic": "ar", "french": "fr", "german": "de", "spanish": "es", "russian": "ru",
    "chinese": "zh", "japanese": "ja", "korean": "ko", "turkish": "tr", "persian": "fa", "urdu": "ur",
    "hindi": "hi", "indonesian": "id", "portuguese": "pt", "italian": "it", "hebrew": "he",
    "thai": "th", "vietnamese": "vi", "malay": "ms", "bengali": "bn", "tamil": "ta", "polish": "pl",
    "dutch": "nl", "ukrainian": "uk", "greek": "el", "swedish": "sv", "czech": "cs", "romanian": "ro",
    "hungarian": "hu", "bulgarian": "bg", "serbian": "sr", "kazakh": "kk", "uzbek": "uz", "swahili": "sw",
    "amharic": "am", "somali": "so", "hausa": "ha", "nepali": "ne", "norwegian": "no", "danish": "da",
    "finnish": "fi",
}
TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref", "cmpid"}

TOPIC_KEYWORDS = {
    "politics": ["سياسة", "دبلوماسية", "وزير", "رئيس", "مفاوضات", "تعاون", "أمن", "خارجية", "مبادرة"],
    "economy": ["اقتصاد", "استثمار", "سوق", "أسهم", "عملة", "تمويل", "صادرات", "ميزانية", "أرامكو", "pif", "الاستثمار"],
    "energy": ["طاقة", "نفط", "غاز", "أرامكو", "الطاقة", "oil", "gas", "energy"],
    "tourism": ["سياحة", "السياحة", "tourism", "travel", "مقصد", "زيارة"],
    "sports": ["كرة قدم", "رياضة", "مشجع", "دوري", "مباراة", "league", "sport", "football"],
    "technology": ["تقنية", "ذكاء", "AI", "تكنولوجيا", "software", "tech", "ابتكار", "digital"],
    "culture": ["ثقافة", "فن", "سينما", "فنون", "مهرجان", "ثقافي", "art"],
    "religion": ["حج", "عمرة", "إسلام", "مكة", "جدة", "مقدسات", "hajj", "umrah"],
    "real_estate": ["عقار", "مشاريع", "تطوير", "عقارات", "مدينة", "project", "real estate"],
    "regional": ["الخليج", "الدول", "المنطقة", "تعاون", "شراكات", "إقليمي"],
    "security": ["أمن", "مخابرات", "دفاع", "حظر", "تدابير", "security"],
}

SOURCE_PRIORITY = {
    "reuters.com": 120,
    "apnews.com": 115,
    "bbc.com": 110,
    "bbc.co.uk": 108,
    "nytimes.com": 110,
    "washingtonpost.com": 105,
    "ft.com": 110,
    "bloomberg.com": 112,
    "aljazeera.com": 105,
    "arabnews.com": 100,
    "spa.gov.sa": 100,
    "saudigazette.com.sa": 98,
    "alriyadh.com": 96,
    "sabq.org": 96,
    "alwatan.com.sa": 95,
    "gulfnews.com": 94,
    "thenationalnews.com": 94,
    "skynewsarabia.com": 94,
    "okaz.com.sa": 94,
    "aawsat.com": 92,
    "alarabiya.net": 90,
    "asharqbusiness.com": 90,
    "theguardian.com": 100,
    "cnn.com": 98,
    "cnbc.com": 95,
    "economist.com": 98,
    "france24.com": 90,
    "dw.com": 88,
    "lemonde.fr": 88,
    "elpais.com": 88,
    "thehindu.com": 84,
    "timesofisrael.com": 82,
    "haaretz.com": 82,
    "scmp.com": 84,
    "nikkei.com": 82,
    "koreaherald.com": 80,
    "thejakartapost.com": 78,
    "dawn.com": 78,
    "xinhuanet.com": 70,
    "cgtn.com": 68,
    "tass.com": 67,
    "rt.com": 66,
}


@dataclass
class Article:
    title: str
    url: str
    domain: str
    source_name: str
    lang: str
    country_ar: str
    published: Optional[dt.datetime]
    origin: str
    direct: bool
    tier: str = "other"
    uid: str = ""
    topic: str = "general"
    source_score: int = 0
    relevance_score: int = 0


def canonical_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
        q = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in TRACKING]
        return urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", urlencode(q), ""))
    except ValueError:
        return url.strip()


def norm_title(t: str) -> str:
    return re.sub(r"[\W_]+", " ", t.lower(), flags=re.U).strip()


def h(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


def host_of(url: str) -> str:
    try:
        host = (urlparse(url).netloc or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def http_get(url: str, timeout: int = 20, **kw) -> Optional[requests.Response]:
    try:
        return requests.get(url, headers={"User-Agent": UA}, timeout=timeout, **kw)
    except requests.RequestException as e:
        log.warning("خطأ شبكة: %s", e)
        return None


def source_priority(domain: str) -> int:
    d = (domain or "").lower()
    for key, score in SOURCE_PRIORITY.items():
        if d == key or d.endswith("." + key):
            return score
    return 40


def classify_topic(title: str) -> str:
    text = title.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(k.lower() in text for k in keywords):
            return topic
    return "general"


def compile_terms(terms: List[str]):
    pats = []
    for t in terms:
        t = t.strip().lower()
        if not t:
            continue
        if t.startswith("="):
            base = re.escape(t[1:])
            pats.append(re.compile(r"(?<!\w)(?:[وفبلك]?(?:ال)?)" + base + r"(?!\w)", re.U))
        elif re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", t):
            pats.append(re.compile(re.escape(t)))
        else:
            pats.append(re.compile(r"(?<!\w)" + re.escape(t), re.U))
    return pats


def title_matches(title: str, pats) -> bool:
    return any(p.search(title.lower()) for p in pats)


def compute_relevance(a: Article, cfg: dict) -> int:
    title = (a.title or "").lower()
    pats = compile_terms(cfg.get("title_must_match_any", []))
    score = 0

    if title_matches(title, pats):
        score += 40

    for kw in [
        "saudi", "riyadh", "riyad", "jeddah", "neom", "aramco", "vision 2030", "hajj", "umrah",
        "pif", "مكة", "جدة", "نيوم", "أرامكو", "رؤية 2030", "سعود", "السعود", "الرياض"
    ]:
        if kw.lower() in title:
            score += 18

    score += a.source_score // 10
    score += 8 if a.tier in {"intl", "saudi_arab"} else 0
    score += 5 if a.lang in {"ar", "en"} else 0

    if title.count("saudi") + title.count("السعود") + title.count("riyadh") > 0:
        score += 10

    return max(0, score)


def fetch_gdelt(cfg: dict, deadline: float) -> tuple[List[Article], Dict[str, int]]:
    g = cfg["gdelt"]
    out: List[Article] = []
    counts: Dict[str, int] = {}
    for lang in g["languages"]:
        if time.monotonic() > deadline:
            log.warning("GDELT: انتهت الميزانية الزمنية")
            break
        query = f'{g["query_terms"]} sourcelang:{lang}'
        url = ("https://api.gdeltproject.org/api/v2/doc/doc?query=" + quote_plus(query) +
               f'&mode=artlist&format=json&sort=datedesc&maxrecords={g.get("maxrecords", 60)}'
               f'&timespan={g.get("timespan", "3h")}')
        data = None
        for attempt in range(2):
            time.sleep(9)
            r = http_get(url, timeout=30)
            if r is None:
                continue
            if r.status_code == 429:
                log.warning("GDELT: 429 (تمهّل)")
                time.sleep(25)
                continue
            try:
                data = r.json()
                break
            except ValueError:
                log.warning("GDELT %s: رد غير JSON: %s", lang, r.text[:120].replace("\n", " "))
        items = (data or {}).get("articles") or []
        counts[f"gdelt:{lang}"] = len(items)
        log.info("gdelt | %s -> %d", lang, len(items))
        out.extend(parse_gdelt_items(items, cfg))
    return out, counts


def parse_gdelt_items(items: list, cfg: dict) -> List[Article]:
    res = []
    countries = cfg.get("countries_ar", {})
    for it in items:
        title, url = (it.get("title") or "").strip(), (it.get("url") or "").strip()
        if not title or not url:
            continue
        pub = None
        sd = it.get("seendate") or ""
        try:
            pub = dt.datetime.strptime(sd, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            pass
        lang_name = (it.get("language") or "").strip().lower()
        country = (it.get("sourcecountry") or "").strip()
        domain = (it.get("domain") or host_of(url)).lower()
        article = Article(
            title=title,
            url=url,
            domain=domain[4:] if domain.startswith("www.") else domain,
            source_name=domain,
            lang=GDELT_LANG_CODES.get(lang_name, lang_name or "?"),
            country_ar=countries.get(country.lower(), country),
            published=pub,
            origin="gdelt",
            direct=True,
        )
        article.source_score = source_priority(article.domain)
        article.topic = classify_topic(article.title)
        res.append(article)
    return res


def fetch_gnews(cfg: dict, deadline: float) -> tuple[List[Article], Dict[str, int]]:
    g = cfg["google_news"]
    out: List[Article] = []
    counts: Dict[str, int] = {}
    for ed in g["editions"]:
        if time.monotonic() > deadline:
            log.warning("Google News: انتهت الميزانية الزمنية")
            break
        q = f'{ed["query"]} when:{g.get("when", "3h")}'
        url = (f'https://news.google.com/rss/search?q={quote_plus(q)}'
               f'&hl={ed["hl"]}&gl={ed["gl"]}&ceid={quote_plus(ed["ceid"])}')
        time.sleep(1.5)
        r = http_get(url)
        key = f'gnews:{ed["lang"]}-{ed["gl"]}'
        if r is None or r.status_code != 200:
            log.warning("gnews %s: HTTP %s", key, getattr(r, "status_code", "-"))
            counts[key] = 0
            continue
        arts = parse_gnews_rss(r.content, ed)
        counts[key] = len(arts)
        log.info("gnews | %s -> %d", key, len(arts))
        out.extend(arts)
    return out, counts


def parse_gnews_rss(xml_bytes: bytes, ed: dict) -> List[Article]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    res = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        src = item.find("source")
        src_name = (src.text or "").strip() if src is not None and src.text else ""
        src_url = src.get("url", "") if src is not None else ""
        if src_name and title.endswith(" - " + src_name):
            title = title[: -len(" - " + src_name)].strip()
        pub = None
        try:
            pub = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "")
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=dt.timezone.utc)
        except (TypeError, ValueError):
            pass
        domain = host_of(src_url) if src_url else ""
        article = Article(
            title=title,
            url=link,
            domain=domain,
            source_name=src_name or domain or "Google News",
            lang=ed["lang"],
            country_ar=ed.get("country_ar", ""),
            published=pub,
            origin="gnews",
            direct=False,
        )
        article.source_score = source_priority(article.domain)
        article.topic = classify_topic(article.title)
        res.append(article)
    return res


class Translator:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.fails = 0

    def title_ar(self, text: str) -> Optional[str]:
        if not self.enabled or self.fails >= 4:
            return None
        r = http_get("https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ar&dt=t&q="
                     + quote_plus(text[:300]), timeout=10)
        try:
            if r is not None and r.status_code == 200:
                out = "".join(seg[0] for seg in r.json()[0] if seg and seg[0])
                if out.strip():
                    return out.strip()
        except (ValueError, IndexError, TypeError):
            pass
        self.fails += 1
        return None


def assign_tier(a: Article, cfg: dict) -> str:
    dom = a.domain
    for tier in ("intl", "saudi_arab", "state"):
        for d in cfg["tiers"][tier]["domains"]:
            if dom == d or dom.endswith("." + d):
                a.tier = tier
                return tier
    a.tier = "other"
    return "other"


TIER_RANK = {"intl": 0, "saudi_arab": 1, "state": 2, "other": 3}


class State:
    KEEP_DAYS = 21

    def __init__(self, path: Path = STATE_PATH):
        self.path = path
        self.data: Dict = {"sent": {}, "warned": {}}
        if path.exists():
            try:
                loaded = json.loads(path.read_text("utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except json.JSONDecodeError:
                pass
        self.data.setdefault("sent", {})
        self.data.setdefault("warned", {})

    def seen(self, key: str) -> bool:
        return key in self.data["sent"]

    def mark(self, a: Article) -> None:
        now = int(time.time())
        self.data["sent"][a.uid] = now
        self.data["sent"]["t" + h(norm_title(a.title))] = now

    def should_warn(self, key: str) -> bool:
        today = time.strftime("%Y-%m-%d")
        if self.data["warned"].get(key) == today:
            return False
        self.data["warned"][key] = today
        return True

    def save(self) -> None:
        cutoff = time.time() - self.KEEP_DAYS * 86400
        self.data["sent"] = {k: v for k, v in self.data["sent"].items() if v > cutoff}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, separators=(",", ":")), "utf-8")


def strong_topic_priority(topic: str) -> int:
    weights = {
        "politics": 18,
        "economy": 18,
        "energy": 22,
        "tourism": 16,
        "sports": 12,
        "technology": 10,
        "culture": 8,
        "religion": 18,
        "real_estate": 16,
        "regional": 14,
        "security": 20,
        "general": 10,
    }
    return weights.get(topic, 10)


def select(arts: List[Article], cfg: dict, state: State):
    pats = compile_terms(cfg.get("title_must_match_any", []))
    strict = cfg.get("strict_title_filter", True)
    stats = {"total": len(arts), "relevant": 0, "new": 0}
    seen_batch: Set[str] = set()
    cands: List[Article] = []

    for a in arts:
        if a.domain:
            a.source_score = source_priority(a.domain)
        a.topic = classify_topic(a.title)
        assign_tier(a, cfg)
        a.relevance_score = compute_relevance(a, cfg) + strong_topic_priority(a.topic)
        if strict and not title_matches(a.title, pats):
            continue
        stats["relevant"] += 1

        a.uid = "u" + h(canonical_url(a.url))
        tkey = "t" + h(norm_title(a.title))
        dedupe_key = "d" + h(norm_title(a.title)[:180])

        if a.uid in seen_batch or tkey in seen_batch or dedupe_key in seen_batch:
            continue
        seen_batch.update([a.uid, tkey, dedupe_key])

        if state.seen(a.uid) or state.seen(tkey):
            continue

        if a.tier == "other" and not cfg.get("include_other_tier", True):
            continue

        cands.append(a)

    stats["new"] = len(cands)
    epoch = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    cands.sort(key=lambda a: (
        -(a.relevance_score + (100 if a.tier == "saudi_arab" else 0) + (60 if a.tier == "intl" else 0)),
        -((a.published or epoch).timestamp()),
        -a.source_score,
    ))

    per_lang: Dict[str, int] = {}
    chosen: List[Article] = []
    cap_lang = cfg.get("max_per_language", 3)
    for a in cands:
        if per_lang.get(a.lang, 0) >= cap_lang:
            continue
        per_lang[a.lang] = per_lang.get(a.lang, 0) + 1
        chosen.append(a)
        if len(chosen) >= cfg.get("max_messages_per_run", 12):
            break
    return chosen, stats


def topic_label(topic: str) -> str:
    mapping = {
        "politics": "سياسة",
        "economy": "اقتصاد",
        "energy": "طاقة",
        "tourism": "سياحة",
        "sports": "رياضة",
        "technology": "تقنية",
        "culture": "ثقافة",
        "religion": "دين/حج",
        "real_estate": "مشاريع/عقار",
        "regional": "منطقة/شراكات",
        "security": "أمن",
        "general": "عام",
    }
    return mapping.get(topic, "عام")


def format_message(a: Article, cfg: dict, tr_title: Optional[str] = None) -> str:
    e = html.escape
    tier_label = cfg["tiers"][a.tier]["label"]
    lang_ar = cfg.get("languages_ar", {}).get(a.lang, a.lang)
    topic = topic_label(a.topic)

    lines = [f"📰 <b>{e(a.title[:220])}</b>"]
    if tr_title and norm_title(tr_title) != norm_title(a.title):
        lines.append(f"🔁 <i>{e(tr_title[:220])}</i>")
    lines += ["", f"📌 <b>{topic}</b> • <b>{a.relevance_score}</b> نقطة", tier_label]

    src = e(a.source_name)
    if a.domain and a.domain != a.source_name:
        src += f" ({e(a.domain)})"
    lines.append(f"🏛 {src}")

    where = " · ".join(x for x in [lang_ar, a.country_ar] if x)
    lines.append(f"🌐 {where}")
    if a.published:
        lines.append("🕒 " + a.published.astimezone(RIYADH).strftime("%Y-%m-%d %H:%M") + " (الرياض)")
    if a.relevance_score >= 80:
        lines.append("🚨 خبر مهم جدًا")
    if a.lang != "ar" and a.direct:
        tr = "https://translate.google.com/translate?sl=auto&tl=ar&u=" + quote_plus(a.url)
        lines.append(f'🔤 <a href="{e(tr, quote=True)}">ترجمة الصفحة للعربية</a>')
    lines.append(f'🔗 <a href="{e(a.url, quote=True)}">اقرأ الخبر</a>')
    return "\n".join(lines)


class Telegram:
    def __init__(self, dry_run: bool = False):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.dry_run = dry_run or not (self.token and self.chat_id)
        if self.dry_run:
            log.warning("وضع تجريبي: لن يُرسل شيء لتلقرام")

    def send_text(self, text: str, preview: bool = False) -> bool:
        if self.dry_run:
            print("-----\n" + text + "\n-----")
            return True
        try:
            payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
                       "disable_web_page_preview": not preview}
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 429:
                try:
                    wait = int(r.json().get("parameters", {}).get("retry_after", 5))
                except (ValueError, AttributeError):
                    wait = 5
                time.sleep(min(wait + 1, 60))
                r = requests.post(url, json=payload, timeout=20)
            if r.status_code != 200:
                log.error("Telegram فشل: %s %s", r.status_code, r.text[:200])
            return r.status_code == 200
        except requests.RequestException as ex:
            log.error("Telegram خطأ شبكة: %s", ex)
            return False


def run(cfg: dict, state: State, tg: Telegram, fast: bool = False) -> int:
    if fast:
        keys = set(cfg.get("fast_editions", []))
        cfg = dict(cfg)
        cfg["google_news"] = dict(cfg["google_news"], when=cfg.get("fast_when", "1h"),
                                  editions=[e for e in cfg["google_news"]["editions"]
                                            if f'{e["lang"]}-{e["gl"]}' in keys])
        cfg["gdelt"] = dict(cfg["gdelt"], enabled=False)
        cfg["max_messages_per_run"] = cfg.get("fast_max_messages", 10)
        cfg["total_time_budget_sec"] = 240
    deadline = time.monotonic() + cfg.get("total_time_budget_sec", 600)
    arts: List[Article] = []
    counts: Dict[str, int] = {}
    if cfg.get("google_news", {}).get("enabled", True):
        a, c = fetch_gnews(cfg, deadline)
        arts += a
        counts.update(c)
    if cfg.get("gdelt", {}).get("enabled", True):
        a, c = fetch_gdelt(cfg, deadline)
        arts += a
        counts.update(c)

    chosen, stats = select(arts, cfg, state)
    sent = 0
    translator = Translator(cfg.get("translate_titles", False))
    for a in chosen:
        tr = translator.title_ar(a.title) if a.lang != "ar" else None
        if tg.send_text(format_message(a, cfg, tr)):
            state.mark(a)
            sent += 1
        time.sleep(3.2)
    log.info("جُمع %d | مطابق %d | جديد %d | أُرسل %d", stats["total"], stats["relevant"], stats["new"], sent)

    g_total = sum(v for k, v in counts.items() if k.startswith("gdelt:"))
    n_total = sum(v for k, v in counts.items() if k.startswith("gnews:"))
    manual = os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch" and not fast

    if manual:
        lines = ["📊 <b>تقرير التشغيل اليدوي — مراقب أخبار السعودية</b>", "",
                 f"• Google News: {n_total} خبر من {sum(1 for k in counts if k.startswith('gnews:'))} نسخة"
                 + ("  ⚠️ لا نتائج" if n_total == 0 else ""),
                 f"• GDELT: {g_total} خبر من {sum(1 for k in counts if k.startswith('gdelt:'))} لغة"
                 + ("  ⚠️ لا نتائج" if g_total == 0 else ""),
                 f"✅ مطابق لمصطلحات السعودية: {stats['relevant']} من {stats['total']}",
                 f"🆕 جديد: {stats['new']} | 📨 أُرسل: {sent}"]
        zero = [k for k, v in counts.items() if v == 0]
        if zero:
            lines.append("بلا نتائج: " + "، ".join(zero[:12]))
        tg.send_text("\n".join(lines))
    elif sent == 0 and not fast and state.should_warn("heartbeat"):
        tg.send_text(f"💤 <b>المراقب يعمل</b> — لا أخبار جديدة تستحق الإرسال الآن.\n"
                     f"فحصت {stats['total']} خبراً، منها {stats['relevant']} مطابقاً للسعودية.")

    if (n_total + g_total) == 0 and state.should_warn("noresults"):
        tg.send_text("⚠️ لم أحصل على أي أخبار من المصدرين. راجع سجل التشغيل في GitHub Actions.")
    return sent


def main() -> None:
    ap = argparse.ArgumentParser(description="مراقب أخبار السعودية")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fast", action="store_true", help="تشغيل سريع: أهم النسخ فقط، آخر ساعة")
    ap.add_argument("--test-telegram", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = yaml.safe_load(Path(args.config).read_text("utf-8"))
    tg = Telegram(dry_run=args.dry_run)
    if args.test_telegram:
        tg.send_text("✅ القناة جاهزة! سيصلك هنا ما يُنشر عن السعودية في إعلام العالم.")
        return
    state = State()
    run(cfg, state, tg, fast=args.fast)
    state.save()


if __name__ == "__main__":
    main()
