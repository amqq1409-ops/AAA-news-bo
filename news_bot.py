from __future__ import annotations

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
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

import requests
import yaml

from data_store import ArticleStore

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "data" / "state.json"
DB_PATH = ROOT / "data" / "news.db"
RIYADH = dt.timezone(dt.timedelta(hours=3))
UA = "Mozilla/5.0 (compatible; SaudiNewsWatch/3.0; +https://github.com)"

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
BREAKING_KEYWORDS = [
    "saudi", "riyadh", "jeddah", "neom", "aramco", "pif", "vision 2030",
    "الرياض", "السعودية", "نيوم", "أرامكو", "رؤية 2030", "مكة", "جدة",
    "الاستثمار", "طاقة", "نفط", "توسع", "قرار", "عقود", "توقيع", "مبادرة"
]
SOURCE_PRIORITY = {"reuters.com": 120, "apnews.com": 115, "bbc.com": 110, "bbc.co.uk": 108, "nytimes.com": 110,
    "washingtonpost.com": 105, "ft.com": 110, "bloomberg.com": 112, "aljazeera.com": 105, "arabnews.com": 100,
    "spa.gov.sa": 100, "saudigazette.com.sa": 98, "alriyadh.com": 96, "sabq.org": 96, "alwatan.com.sa": 95,
    "gulfnews.com": 94, "thenationalnews.com": 94, "skynewsarabia.com": 94, "okaz.com.sa": 94,
    "aawsat.com": 92, "alarabiya.net": 90, "asharqbusiness.com": 90, "theguardian.com": 100,
    "cnn.com": 98, "cnbc.com": 95, "economist.com": 98, "france24.com": 90, "dw.com": 88,
    "lemonde.fr": 88, "elpais.com": 88, "thehindu.com": 84, "timesofisrael.com": 82,
    "haaretz.com": 82, "scmp.com": 84, "nikkei.com": 82, "koreaherald.com": 80,
    "thejakartapost.com": 78, "dawn.com": 78, "xinhuanet.com": 70, "cgtn.com": 68,
    "tass.com": 67, "rt.com": 66}


class Article:
    def __init__(self, title, url, domain, source_name, lang, country_ar, published, origin, direct=False):
        self.title = title.strip()
        self.url = canonical_url(url)
        self.domain = domain.lower()
        self.source_name = source_name or self.domain or "News"
        self.lang = lang or "en"
        self.country_ar = country_ar or ""
        self.published = published
        self.origin = origin
        self.direct = direct
        self.tier = "other"
        self.uid = ""
        self.topic = "general"
        self.source_score = source_priority(self.domain)
        self.relevance_score = 0
        self.breaking_score = 0


def canonical_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
        q = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in TRACKING]
        return urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", urlencode(q), ""))
    except Exception:
        return url.strip()


def host_of(url: str) -> str:
    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def norm_title(t: str) -> str:
    return re.sub(r"[\W_]+", " ", t.lower(), flags=re.U).strip()


def h(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]


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


def compile_terms(terms):
    out = []
    for t in terms or []:
        t = (t or "").strip().lower()
        if not t:
            continue
        if t.startswith("="):
            base = re.escape(t[1:])
            out.append(re.compile(r"(?<!\w)" + base + r"(?!\w)", re.U))
        else:
            out.append(re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)", re.U))
    return out


def title_matches(title: str, pats) -> bool:
    txt = title.lower()
    return any(p.search(txt) for p in pats)


def compute_relevance(article: Article, cfg: dict) -> int:
    text = article.title.lower()
    score = 0
    pats = compile_terms(cfg.get("title_must_match_any", []))
    if title_matches(article.title, pats):
        score += 45
    if any(k.lower() in text for k in ["saudi", "riyadh", "jeddah", "makkah", "ramco", "aramco", "neom", "vision 2030", "السعودية", "الرياض", "أرامكو", "نيوم", "بن سلمان", "رؤية 2030"]):
        score += 18
    score += article.source_score // 10
    score += 8 if article.tier in {"intl", "saudi_arab"} else 0
    score += 5 if article.lang in {"ar", "en"} else 0
    return score


def breaking_score(article: Article) -> int:
    score = 0
    text = article.title.lower()
    score += min(max(0, article.source_score // 3), 45)
    score += min(max(0, article.relevance_score), 35)
    if any(k.lower() in text for k in BREAKING_KEYWORDS):
        score += 25
    if article.topic in {"economy", "energy", "politics", "security", "real_estate", "religion"}:
        score += 15
    if article.tier in {"saudi_arab", "intl", "state"}:
        score += 10
    if article.published:
        age_minutes = (dt.datetime.now(dt.timezone.utc) - article.published.astimezone(dt.timezone.utc)).total_seconds() / 60
        if age_minutes <= 30:
            score += 20
        elif age_minutes <= 120:
            score += 8
    return min(score, 100)


def assign_tier(article: Article, cfg: dict) -> str:
    dom = article.domain
    for tier_name, tier_cfg in cfg.get("tiers", {}).items():
        for d in tier_cfg.get("domains", []):
            if dom == d or dom.endswith("." + d):
                article.tier = tier_name
                return tier_name
    article.tier = "other"
    return "other"


def http_get(url: str, timeout: int = 20, **kwargs):
    try:
        return requests.get(url, headers={"User-Agent": UA}, timeout=timeout, **kwargs)
    except requests.RequestException as e:
        logging.warning("HTTP error: %s", e)
        return None


def needs_arabic_translation(article: Article) -> bool:
    letters = [char for char in article.title if char.isalpha()]
    if not letters:
        return False
    arabic_letters = sum(
        "\u0600" <= char <= "\u06ff" or "\u0750" <= char <= "\u077f" for char in letters
    )
    return arabic_letters / len(letters) < 0.35


def translate_to_arabic(text: str, timeout: int = 10) -> str | None:
    if not text.strip():
        return None
    params = {"client": "gtx", "sl": "auto", "tl": "ar", "dt": "t", "q": text[:5000]}
    for endpoint in (
        "https://translate.googleapis.com/translate_a/single",
        "https://translate.google.com/translate_a/single",
    ):
        response = http_get(endpoint, timeout=timeout, params=params)
        if response is None:
            continue
        if response.status_code != 200:
            logging.warning("Translation endpoint returned HTTP %s", response.status_code)
            continue
        try:
            segments = response.json()[0]
            translated = "".join(segment[0] for segment in segments if segment and segment[0])
            if translated.strip():
                return translated
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            logging.warning("Translation response could not be parsed: %s", exc)
    logging.warning("Arabic translation unavailable")
    return None


def parse_gdelt_items(items, cfg):
    out = []
    for it in items or []:
        title = (it.get("title") or "").strip()
        url = (it.get("url") or "").strip()
        if not title or not url:
            continue
        lang_name = (it.get("language") or "").strip().lower()
        lang = GDELT_LANG_CODES.get(lang_name, lang_name or "en")
        pub = None
        sd = it.get("seendate") or ""
        try:
            pub = dt.datetime.strptime(sd, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
        except Exception:
            pass
        domain = (it.get("domain") or host_of(url)).lower()
        article = Article(title, url, domain, domain, lang, it.get("sourcecountry", ""), pub, "gdelt", True)
        article.topic = classify_topic(article.title)
        article.relevance_score = compute_relevance(article, cfg)
        article.breaking_score = breaking_score(article)
        assign_tier(article, cfg)
        out.append(article)
    return out


def fetch_gdelt(cfg, deadline):
    gd = cfg.get("gdelt", {})
    if not gd.get("enabled", True):
        return [], {}
    out = []
    counts = {}
    for lang in gd.get("languages", ["english", "arabic"]):
        if time.monotonic() > deadline:
            break
        query = gd.get("query_terms", '"Saudi Arabia" OR Riyadh')
        url = "https://api.gdeltproject.org/api/v2/doc/doc?query=" + quote_plus(f'{query} sourcelang:{lang}') + f'&mode=artlist&format=json&maxrecords={gd.get("maxrecords", 60)}&sort=datedesc&timespan={gd.get("timespan", "2h")}'
        r = http_get(url, timeout=30)
        if r is None or r.status_code != 200:
            counts[f"gdelt:{lang}"] = 0
            continue
        try:
            data = r.json()
            items = (data or {}).get("articles") or []
            counts[f"gdelt:{lang}"] = len(items)
            out.extend(parse_gdelt_items(items, cfg))
        except Exception as e:
            logging.warning("GDELT parse error %s: %s", lang, e)
            counts[f"gdelt:{lang}"] = 0
    return out, counts


def x_search_queries(accounts, terms, max_length=512):
    term_query = "(" + " OR ".join(f'"{term}"' if " " in term else term for term in terms) + ") -is:retweet"
    prefix = f" {term_query}"
    groups = []
    current = []
    for account in accounts:
        if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", account):
            logging.warning("Skipping invalid X username: %s", account)
            continue
        candidate = current + [account]
        account_query = "(" + " OR ".join(f"from:{handle}" for handle in candidate) + ")"
        if current and len(account_query + prefix) > max_length:
            groups.append("(" + " OR ".join(f"from:{handle}" for handle in current) + ")" + prefix)
            current = [account]
        else:
            current = candidate
    if current:
        groups.append("(" + " OR ".join(f"from:{handle}" for handle in current) + ")" + prefix)
    return groups


def parse_x_items(payload):
    users = {user.get("id"): user for user in payload.get("includes", {}).get("users", [])}
    out = []
    for item in payload.get("data", []):
        author = users.get(item.get("author_id"), {})
        username = author.get("username")
        post_id = item.get("id")
        text = (item.get("text") or "").strip()
        if not username or not post_id or not text:
            continue
        published = None
        try:
            published = dt.datetime.fromisoformat(item.get("created_at", "").replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            pass
        article = Article(
            text,
            f"https://x.com/{username}/status/{post_id}",
            "x.com",
            f'{author.get("name") or username} (@{username})',
            item.get("lang", "en"),
            "X",
            published,
            "x",
            True,
        )
        out.append(article)
    return out


def fetch_x(cfg, deadline):
    x_cfg = cfg.get("x", {})
    token = os.getenv("X_BEARER_TOKEN")
    if not x_cfg.get("enabled", True) or not token:
        if x_cfg.get("enabled", True):
            logging.info("X collection skipped: X_BEARER_TOKEN is not configured")
        return [], {"x": 0}

    terms = x_cfg.get(
        "query_terms",
        ["Saudi Arabia", "Saudi", "SaudiArabia", "Riyadh", "Jeddah", "Aramco", "NEOM", "KSA", "Vision 2030",
         "السعودية", "الرياض", "نيوم", "أرامكو"],
    )
    queries = x_search_queries(x_cfg.get("accounts", []), terms)
    start_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=x_cfg.get("lookback_minutes", 180))
    params_base = {
        "max_results": min(max(int(x_cfg.get("max_results", 100)), 10), 100),
        "tweet.fields": "created_at,lang,author_id",
        "expansions": "author_id",
        "user.fields": "name,username",
        "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sort_order": "recency",
    }
    articles = []
    counts = {}
    for index, query in enumerate(queries, start=1):
        if time.monotonic() > deadline:
            break
        try:
            response = requests.get(
                "https://api.x.com/2/tweets/search/recent",
                headers={"Authorization": "Bearer " + token, "User-Agent": UA},
                params={**params_base, "query": query},
                timeout=20,
            )
        except requests.RequestException as exc:
            logging.warning("X API request failed: %s", exc)
            counts[f"x:{index}"] = 0
            continue
        if response.status_code != 200:
            logging.warning("X API returned HTTP %s: %s", response.status_code, response.text[:300])
            counts[f"x:{index}"] = 0
            continue
        try:
            payload = response.json()
            items = parse_x_items(payload)
            counts[f"x:{index}"] = len(items)
            articles.extend(items)
        except (ValueError, TypeError, AttributeError) as exc:
            logging.warning("X API response parse failed: %s", exc)
            counts[f"x:{index}"] = 0
    return articles, counts


def parse_gnews_rss(xml_bytes, edition):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        src = item.find("source")
        source_name = (src.text or "").strip() if src is not None and src is not None else ""
        pub = None
        try:
            pub = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "")
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=dt.timezone.utc)
        except Exception:
            pub = None
        domain = host_of(link) or (src.get("url", "") if src is not None else "")
        article = Article(title, link, domain, source_name or domain or "Google News", edition.get("lang", "en"), edition.get("country_ar", ""), pub, "gnews", False)
        article.topic = classify_topic(article.title)
        article.relevance_score = compute_relevance(article, edition)
        article.breaking_score = breaking_score(article)
        assign_tier(article, edition)
        out.append(article)
    return out


def fetch_gnews(cfg, deadline):
    gn = cfg.get("google_news", {})
    if not gn.get("enabled", True):
        return [], {}
    out = []
    counts = {}
    editions = gn.get("editions", [])
    for ed in editions:
        if time.monotonic() > deadline:
            break
        q = ed.get("query", '"Saudi Arabia"')
        url = f'https://news.google.com/rss/search?q={quote_plus(q)}&hl={ed.get("hl", "en-US")}&gl={ed.get("gl", "US")}&ceid={quote_plus(ed.get("ceid", "US:en"))}'
        r = http_get(url)
        if r is None or r.status_code != 200:
            counts[f'gnews:{ed.get("lang")}-{ed.get("gl")}'] = 0
            continue
        items = parse_gnews_rss(r.content, ed)
        counts[f'gnews:{ed.get("lang")}-{ed.get("gl")}'] = len(items)
        out.extend(items)
    return out, counts


class State:
    def __init__(self, path=STATE_PATH):
        self.path = Path(path)
        self.data = {"sent": {}, "warned": {}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text("utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except Exception:
                pass
        self.data.setdefault("sent", {})
        self.data.setdefault("warned", {})

    def seen(self, key: str) -> bool:
        return key in self.data["sent"]

    def mark(self, article: Article):
        self.data["sent"][article.uid] = int(time.time())
        self.data["sent"]["t" + h(norm_title(article.title))] = int(time.time())

    def should_warn(self, key: str) -> bool:
        today = dt.datetime.now().strftime("%Y-%m-%d")
        if self.data["warned"].get(key) == today:
            return False
        self.data["warned"][key] = today
        return True

    def save(self):
        cutoff = time.time() - 21 * 86400
        self.data["sent"] = {k: v for k, v in self.data["sent"].items() if v > cutoff}
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")


class Telegram:
    def __init__(self, dry_run=False):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.dry_run = dry_run or not (self.token and self.chat_id)
        if self.dry_run:
            logging.warning("Telegram dry-run enabled")

    def send_text(self, text: str, preview: bool = False) -> bool:
        if self.dry_run:
            print("-----\n" + text + "\n-----")
            return True
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": not preview}
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 429:
                wait = 5
                try:
                    wait = int(r.json().get("parameters", {}).get("retry_after", 5))
                except Exception:
                    pass
                time.sleep(min(wait + 1, 60))
                r = requests.post(url, json=payload, timeout=20)
            return r.status_code == 200
        except requests.RequestException as e:
            logging.error("Telegram send failed: %s", e)
            return False


def topic_label(topic: str) -> str:
    mapping = {"politics": "سياسة", "economy": "اقتصاد", "energy": "طاقة", "tourism": "سياحة", "sports": "رياضة",
        "technology": "تقنية", "culture": "ثقافة", "religion": "دين/حج", "real_estate": "مشاريع/عقار",
        "regional": "منطقة/شراكات", "security": "أمن", "general": "عام"}
    return mapping.get(topic, "عام")


def format_message(article: Article, cfg: dict, translated_title=None) -> str:
    if article.origin == "x":
        lines = ["𝕏 منشور جديد"]
        if translated_title:
            lines.append(f"🔁 <i>{html.escape(translated_title[:1000])}</i>")
            lines.append(f"🔤 <b>{html.escape(article.title[:1000])}</b>")
        else:
            lines.append(f"<b>{html.escape(article.title[:1000])}</b>")
        lines.append(f"👤 {html.escape(article.source_name)}")
        if article.published:
            lines.append("🕒 " + article.published.astimezone(RIYADH).strftime("%Y-%m-%d %H:%M") + " (الرياض)")
        lines.append(f'🔗 <a href="{html.escape(article.url, quote=True)}">عرض المنشور</a>')
        return "\n".join(lines)
    topic = topic_label(article.topic)
    breaking = cfg.get("breaking_mode", False) and getattr(article, "breaking_score", 0) >= cfg.get("breaking_threshold", 78)
    source = article.source_name or article.domain
    label = cfg.get("tiers", {}).get(article.tier, {}).get("label", "⚪ مصدر آخر")
    if translated_title:
        title_line = f"<b>{html.escape(translated_title[:200])}</b>\n🔤 <i>{html.escape(article.title[:200])}</i>"
    else:
        title_line = f"<b>{html.escape(article.title[:200])}</b>"
    lines = ["🚨 BREAKING NEWS" if breaking else "📰 خبر جديد"]
    lines.append(title_line)
    lines.append(f"📌 <b>{topic}</b> • {getattr(article, 'breaking_score', article.relevance_score)} نقطة • {label}")
    lines.append(f"🏛 {html.escape(source)}")
    if article.country_ar:
        lines.append(f"🌐 {html.escape(article.country_ar)}")
    if article.published:
        lines.append("🕒 " + article.published.astimezone(RIYADH).strftime("%Y-%m-%d %H:%M") + " (الرياض)")
    lines.append(f'🔗 <a href="{html.escape(article.url, quote=True)}">اقرأ الخبر</a>')
    return "\n".join(lines)


def apply_saudi_focus(cfg: dict) -> dict:
    cfg = dict(cfg)
    cfg["saudi_focus"] = True
    cfg["strict_title_filter"] = True
    cfg["breaking_mode"] = cfg.get("breaking_mode", False)
    cfg["breaking_threshold"] = cfg.get("breaking_threshold", 78)
    cfg["max_messages_per_run"] = cfg.get("max_messages_per_run", 12)
    cfg["max_per_language"] = cfg.get("max_per_language", 2)
    existing = list(cfg.get("title_must_match_any", []))
    extra = list(cfg.get("saudi_focus_terms", []))
    cfg["title_must_match_any"] = list(dict.fromkeys(existing + extra))
    if cfg.get("google_news"):
        cfg["google_news"]["when"] = cfg.get("breaking_when", "30m") if cfg.get("breaking_mode") else cfg.get("fast_when", "1h")
    return cfg


def select_articles(articles, cfg, state):
    pats = compile_terms(cfg.get("title_must_match_any", []))
    selected = []
    seen = set()
    for article in articles:
        article.topic = classify_topic(article.title)
        article.relevance_score = compute_relevance(article, cfg)
        article.breaking_score = breaking_score(article)
        assign_tier(article, cfg)
        if cfg.get("strict_title_filter", True) and not title_matches(article.title, pats):
            continue
        article.uid = "u" + h(article.url)
        dedupe1 = "d" + h(norm_title(article.title)[:180])
        if article.uid in seen or dedupe1 in seen or state.seen(article.uid):
            continue
        seen.add(article.uid)
        seen.add(dedupe1)
        if cfg.get("saudi_focus", False) and article.breaking_score < cfg.get("breaking_threshold", 78):
            # keep only high-score items in Saudi-focus mode
            if not any(k.lower() in article.title.lower() for k in ["saudi", "riyadh", "السعودية", "الرياض", "أرامكو", "نيوم", "رؤية 2030", "بن سلمان"]):
                continue
        selected.append(article)
    selected.sort(key=lambda a: (a.origin != "x", -(getattr(a, "breaking_score", 0) if cfg.get("breaking_mode") else a.relevance_score), -(a.source_score), -((a.published.timestamp() if a.published else 0))))
    max_per_lang = cfg.get("breaking_per_language", 2) if cfg.get("breaking_mode") else cfg.get("max_per_language", 2)
    out, counts = [], {}
    for a in selected:
        counts[a.lang] = counts.get(a.lang, 0) + 1
        if counts[a.lang] > max_per_lang:
            continue
        out.append(a)
        if len(out) >= cfg.get("max_messages_per_run", 12):
            break
    return out


def run(cfg: dict, state: State, tg: Telegram, fast=False, breaking=False, store=None) -> int:
    cfg = dict(cfg)
    if breaking:
        cfg["breaking_mode"] = True
        cfg["breaking_threshold"] = cfg.get("breaking_threshold", 78)
        cfg["strict_title_filter"] = True
        cfg["max_messages_per_run"] = cfg.get("breaking_max_messages", 4)
        cfg["max_per_language"] = cfg.get("breaking_per_language", 2)
        cfg["google_news"] = {**cfg.get("google_news", {}), "when": cfg.get("breaking_when", "30m")}
        cfg["gdelt"] = {**cfg.get("gdelt", {}), "timespan": "1h", "maxrecords": 80}
    if fast:
        cfg["max_messages_per_run"] = cfg.get("fast_max_messages", 10)
        cfg["max_per_language"] = cfg.get("max_per_language", 2)
        cfg["google_news"] = {**cfg.get("google_news", {}), "when": cfg.get("fast_when", "1h")}
    cfg = apply_saudi_focus(cfg)

    deadline = time.monotonic() + cfg.get("total_time_budget_sec", 900)
    articles = []
    counts = {}
    x_articles, x_counts = fetch_x(cfg, deadline)
    articles.extend(x_articles)
    counts.update(x_counts)
    arts, c = fetch_gnews(cfg, deadline)
    articles.extend(arts)
    counts.update(c)
    arts2, c2 = fetch_gdelt(cfg, deadline)
    articles.extend(arts2)
    counts.update(c2)

    chosen = select_articles(articles, cfg, state)
    sent = 0
    for article in chosen:
        if store is not None:
            store.upsert_article(article)
        translated = None
        if cfg.get("translate_titles", True) and needs_arabic_translation(article):
            translated = translate_to_arabic(article.title)
        msg = format_message(article, cfg, translated)
        if tg.send_text(msg):
            state.mark(article)
            if store is not None:
                store.record_sent(article)
            sent += 1
        time.sleep(2)
    stats = {"total": len(articles), "relevant": len(chosen), "new": len(chosen), "sent": sent}
    if store is not None:
        store.log_run(stats, counts, sent)
    return sent


def main():
    ap = argparse.ArgumentParser(description="Saudi News Watch")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--breaking", action="store_true")
    ap.add_argument("--saudi", action="store_true", help="Saudi-focused mode")
    ap.add_argument("--test-telegram", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = yaml.safe_load(Path(args.config).read_text("utf-8")) or {}
    if args.saudi:
        cfg["saudi_focus"] = True
    if args.breaking:
        cfg["breaking_mode"] = True
    cfg = apply_saudi_focus(cfg)
    tg = Telegram(dry_run=args.dry_run)
    if args.test_telegram:
        tg.send_text("✅ القناة جاهزة! يتم رصد ما يكتب عن السعودية في العالم.")
        return
    state = State()
    store = ArticleStore(DB_PATH)
    run(cfg, state, tg, fast=args.fast, breaking=args.breaking, store=store)
    state.save()


if __name__ == "__main__":
    main()
