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

import geo
from ai import TONE_EMOJI, TONES, AIEnricher
from archive import Archive, build_digest

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "data" / "state.json"
ARCHIVE_DIR = ROOT / "data" / "archive"
RIYADH = dt.timezone(dt.timedelta(hours=3))
UA = "Mozilla/5.0 (compatible; SaudiNewsWatch/4.0; +https://github.com)"

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

# كلمات الموضوعات: تُطابَق ككلمات كاملة (لا كأجزاء من كلمات) على العنوان الأصلي والعنوان المترجم معًا.
# النجمة في آخر الكلمة الإنجليزية تعني "وما يبدأ بها".
TOPIC_KEYWORDS = {
    "sports": ["رياضة", "رياضي", "كرة القدم", "كرة", "دوري", "مباراة", "بطولة", "كأس", "نادي", "لاعب", "مدرب",
               "مونديال", "كأس العالم", "فورمولا", "ملاكمة", "غولف", "تنس", "رونالدو", "الهلال", "أولمبي",
               "football", "soccer", "league", "match", "cup", "club", "player", "coach", "fifa", "world cup",
               "formula 1", "f1", "grand prix", "boxing", "golf", "tennis", "ronaldo", "al hilal", "al nassr",
               "al ittihad", "esports", "wwe", "olympic*", "sport", "sports"],
    "religion": ["حج", "حاج", "حجاج", "عمرة", "معتمر", "المسجد الحرام", "المسجد النبوي", "الحرمين", "مكة",
                 "المدينة المنورة", "إسلام", "إسلامي", "مسلم", "رمضان", "عيد الفطر", "عيد الأضحى", "كعبة", "مسجد",
                 "hajj", "umrah", "pilgrim*", "mecca", "makkah", "medina", "madinah", "islam*", "muslim*",
                 "ramadan", "eid", "mosque*", "kaaba"],
    "energy": ["طاقة", "نفط", "نفطي", "غاز", "أرامكو", "أوبك", "بترول", "كهرباء", "هيدروجين", "متجددة", "شمسية",
               "برميل", "خام", "oil", "gas", "energy", "aramco", "opec", "crude", "petrol*", "hydrogen", "solar",
               "renewable*", "lng", "barrel*", "refiner*"],
    "tourism": ["سياحة", "سياحي", "سائح", "سياح", "سفر", "فندق", "فنادق", "طيران", "وجهة", "تأشيرة", "منتجع",
                "العلا", "البحر الأحمر", "رحلات", "tourism", "tourist*", "travel", "hotel*", "resort*",
                "airline*", "visa", "visas", "alula", "red sea", "flight*", "cruise*"],
    "technology": ["تقنية", "تقني", "ذكاء اصطناعي", "الذكاء الاصطناعي", "تكنولوجيا", "رقمي", "رقمنة", "برمجيات",
                   "ابتكار", "بيانات", "سيبراني", "روبوت", "ناشئة", "رقائق", "ai", "artificial intelligence",
                   "tech", "technology", "digital", "software", "data center*", "datacenter*", "cyber*",
                   "startup*", "chip", "chips", "semiconductor*", "robot*", "humain"],
    "culture": ["ثقافة", "ثقافي", "فن", "فنون", "فنان", "سينما", "فيلم", "مهرجان", "موسيقى", "معرض", "تراث",
                "مسرح", "ترفيه", "موسم الرياض", "حفل", "culture", "cultural", "art", "arts", "film*", "cinema",
                "festival*", "music", "heritage", "museum*", "concert*", "entertainment", "riyadh season"],
    "security": ["أمن", "أمني", "دفاع", "دفاعي", "عسكري", "جيش", "صاروخ", "صواريخ", "سلاح", "أسلحة", "هجوم",
                 "إرهاب", "إرهابي", "قوات", "مناورات", "مسيرة", "إعدام", "اعتقال", "security", "defense",
                 "defence", "military", "army", "missile*", "weapon*", "arms", "attack*", "terror*", "troops",
                 "drone*", "execution*", "executed", "arrest*", "fighter jet*"],
    "economy": ["اقتصاد", "اقتصادي", "استثمار", "مستثمر", "سوق", "أسواق", "أسهم", "بورصة", "تمويل", "صادرات",
                "واردات", "ميزانية", "صندوق الاستثمارات", "تجارة", "تجاري", "بنك", "مصرف", "تضخم", "سندات",
                "صفقة", "مليار", "مليون", "شركة", "أرباح", "عمالة", "عمال", "وظائف", "توظيف", "econom*", "invest*", "market*", "stock*", "shares",
                "ipo", "bank*", "trade", "budget", "pif", "billion*", "fund", "funds", "inflation", "bond",
                "bonds", "deal", "deals", "gdp", "profit*", "revenue*", "labor", "labour", "worker*", "jobs", "public investment fund"],
    "real_estate": ["عقار", "عقاري", "مشروع", "مشاريع", "إسكان", "بناء", "نيوم", "ذا لاين", "القدية", "الدرعية",
                    "مطار", "مترو", "بنية تحتية", "إنشاء", "برج", "real estate", "property", "construction",
                    "housing", "megaproject*", "giga-project*", "gigaproject*", "neom", "the line", "qiddiya",
                    "diriyah", "airport*", "metro", "infrastructure", "skyscraper*", "tower*", "stadium*"],
    "politics": ["سياسة", "سياسي", "دبلوماسي", "دبلوماسية", "وزير", "وزراء", "رئيس", "قمة", "مفاوضات", "مباحثات",
                 "سفير", "سفارة", "خارجية", "ولي العهد", "الملك", "اتفاق", "اتفاقية", "تطبيع", "عقوبات", "برلمان",
                 "انتخابات", "بن سلمان", "minister*", "diplomat*", "summit", "talks", "ambassador*", "embassy",
                 "crown prince", "king", "president*", "normali*", "sanction*", "treaty", "foreign policy",
                 "bilateral", "bin salman", "mbs", "white house", "trump", "putin", "xi jinping"],
    "regional": ["الخليج", "خليجي", "مجلس التعاون", "اليمن", "إيران", "غزة", "فلسطين", "سوريا", "لبنان", "السودان",
                 "قطر", "الإمارات", "مصر", "العراق", "إقليمي", "الحوثي", "إسرائيل", "gulf", "gcc", "yemen*", "iran*",
                 "gaza", "palestin*", "syria*", "lebanon", "sudan", "qatar*", "uae", "emirates", "egypt*",
                 "iraq*", "regional", "houthi*", "israel*"],
}
TOPIC_LABELS = {"politics": "سياسة", "economy": "اقتصاد", "energy": "طاقة", "tourism": "سياحة", "sports": "رياضة",
                "technology": "تقنية", "culture": "ثقافة", "religion": "دين/حج", "real_estate": "مشاريع/عقار",
                "regional": "منطقة/شراكات", "security": "أمن", "general": "عام"}
TOPIC_TAGS = {"politics": "سياسة", "economy": "اقتصاد", "energy": "طاقة", "tourism": "سياحة", "sports": "رياضة",
              "technology": "تقنية", "culture": "ثقافة", "religion": "حج_وعمرة", "real_estate": "مشاريع",
              "regional": "شؤون_إقليمية", "security": "أمن", "general": "عام"}

BREAKING_KEYWORDS = [
    "saudi", "riyadh", "jeddah", "neom", "aramco", "pif", "vision 2030",
    "الرياض", "السعودية", "نيوم", "أرامكو", "رؤية 2030", "مكة", "جدة",
    "الاستثمار", "طاقة", "نفط", "توسع", "قرار", "عقود", "توقيع", "مبادرة"
]
FOCUS_KEYWORDS = ["saudi", "riyadh", "السعودية", "السعودي", "الرياض", "أرامكو", "نيوم", "رؤية 2030", "بن سلمان"]
# كلمات قد ترد في أخبار لا تخص السعودية؛ لا تكفي وحدها إلا إذا كان الخبر عالي النقاط أو ذُكرت السعودية صراحة
DEFAULT_WEAK_TERMS = ["hajj", "umrah", "=ksa", "makkah", "jeddah", "=حج", "=عمرة", "=مكة", "=جدة"]
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
SOURCE_NAMES_AR = {"x": "منصة X", "gnews": "أخبار Google", "gdelt": "قاعدة GDELT"}
DEFAULT_REGION_PRIORITY = ["east_asia", "southeast_asia", "south_asia", "central_asia", "africa", "latin_america",
                           "oceania", "mideast", "europe", "north_america", "arab"]
NO_SPACE_LANGS = {"zh", "ja", "ko", "th"}

_TASHKEEL = re.compile(r"[ً-ٰٟـ]")
_ALEF = str.maketrans("أإآٱ", "اااا")
_TOKEN_FOLD = str.maketrans("ىة", "يه")
_ARABIC = re.compile(r"[؀-ۿ]")
_AR_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال")
STOPWORDS = {
    "في", "من", "علي", "الي", "عن", "مع", "هذا", "هذه", "التي", "الذي", "ان", "كان", "قد", "بعد", "قبل", "بين",
    "حول", "خلال", "عند", "كما", "لدي", "ما", "لا", "لم", "هو", "هي", "او", "ثم", "حتي", "منذ", "ضد", "نحو", "ذلك", "تم",
    "the", "a", "an", "of", "in", "on", "to", "for", "and", "or", "at", "by", "with", "as", "is", "are", "was", "be",
    "from", "its", "it", "that", "this", "after", "over", "amid", "says", "said", "will", "has", "have", "new",
    "de", "la", "le", "les", "el", "en", "du", "des", "un", "une", "y", "e", "o", "que", "der", "die", "das", "und",
}


def norm_ar(text: str) -> str:
    return _TASHKEEL.sub("", text).translate(_ALEF)


class Article:
    def __init__(self, title, url, domain, source_name, lang, country_ar, published, origin, direct=False):
        self.title = title.strip()
        self.url = canonical_url(url)
        self.domain = (domain or "").lower()
        self.source_name = source_name or self.domain or "News"
        self.lang = lang or "en"
        self.country_ar = country_ar or ""
        self.published = published
        self.origin = origin
        self.direct = direct
        self.tier = "other"
        self.uid = "u" + h(self.url)
        self.topic = "general"
        self.source_score = source_priority(self.domain)
        self.relevance_score = 0
        self.breaking_score = 0
        self.title_ar = None       # العنوان بالعربية (الأصل إن كان عربيًا، أو الترجمة)
        self.translated = False
        self.summary = ""
        self.tone = ""
        self.iso = ""
        self.country_tag = ""
        self.region = "unknown"
        self.also = []             # مصادر أخرى نشرت الخبر نفسه
        self.tok_ar = None
        self.tok_orig = set()

    def all_text(self) -> str:
        return (self.title + " " + (self.title_ar or "")).strip()


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


def title_key(title: str) -> str:
    return "t" + h(norm_title(title))


def source_priority(domain: str) -> int:
    d = (domain or "").lower()
    for key, score in SOURCE_PRIORITY.items():
        if d == key or d.endswith("." + key):
            return score
    return 40


# ---------------------------------------------------------------- الموضوعات
def _keyword_regex(keyword: str) -> str:
    kw = norm_ar(keyword.lower().strip())
    if _ARABIC.search(kw):
        # يسمح بحروف العطف والجر و"ال" قبل الكلمة، وبلواحق الجمع والنسبة بعدها
        return r"(?<!\w)[وف]?(?:ال|لل|بال|كال|[بلك])?" + re.escape(kw) + r"(?:ات|ين|ون|ان|ية|ي|ة|ه|ا)?(?!\w)"
    if kw.endswith("*"):
        return r"(?<!\w)" + re.escape(kw[:-1]) + r"\w*"
    return r"(?<!\w)" + re.escape(kw) + r"(?!\w)"


_TOPIC_PATTERNS = {
    topic: re.compile("|".join(_keyword_regex(k) for k in sorted(kws, key=len, reverse=True)), re.U)
    for topic, kws in TOPIC_KEYWORDS.items()
}


def classify_topic(text: str) -> str:
    text = norm_ar(text.lower())
    best, best_hits = "general", 0
    for topic, pattern in _TOPIC_PATTERNS.items():
        hits = len(pattern.findall(text))
        if hits > best_hits:
            best, best_hits = topic, hits
    return best


# ---------------------------------------------------------------- المطابقة والنقاط
_BOUNDARY_SCRIPTS = re.compile(r"[a-z\u00c0-\u024f\u0370-\u03ff\u0400-\u04ff\u0530-\u058f\u10a0-\u10ff]")


def compile_terms(terms):
    """يحوّل كلمات المطابقة إلى أنماط.

    "=كلمة"  : الكلمة كاملة فقط (مثل =جدة، وتُقبل معها "ال" وحروف الجر: الرياض، بجدة).
    غير ذلك  : جذر يُقبل ما بعده (saudi تطابق saudis، و"سعودي" تطابق "السعودية").
    واللغات التي لا تفصل الكلمات بمسافات (الصينية واليابانية والكورية والتايلاندية وغيرها) تُطابَق في أي موضع.
    """
    out = []
    for t in terms or []:
        t = (t or "").strip().lower()
        if not t:
            continue
        if t.startswith("="):
            lead = r"(?<!\w)[وف]?(?:ال|لل|بال|كال|[بلك])?" if _ARABIC.search(t) else r"(?<!\w)"
            out.append(re.compile(lead + re.escape(t[1:]) + r"(?!\w)", re.U))
        elif _ARABIC.search(t):
            out.append(re.compile(r"(?<!\w)[وف]?(?:ال|لل|بال|كال|[بلك])?" + re.escape(t), re.U))
        elif _BOUNDARY_SCRIPTS.search(t):
            out.append(re.compile(r"(?<!\w)" + re.escape(t), re.U))
        else:
            out.append(re.compile(re.escape(t), re.U))
    return out


def title_matches(title: str, pats) -> bool:
    txt = title.lower()
    return any(p.search(txt) for p in pats)


def compute_relevance(article: Article, pats) -> int:
    text = article.all_text().lower()
    score = 0
    if title_matches(article.title, pats):
        score += 45
    if any(k in text for k in ["saudi", "riyadh", "jeddah", "makkah", "aramco", "neom", "vision 2030", "السعودية", "الرياض", "أرامكو", "نيوم", "بن سلمان", "رؤية 2030"]):
        score += 18
    score += article.source_score // 10
    score += 8 if article.tier in {"intl", "saudi_arab"} else 0
    score += 5 if article.lang in {"ar", "en"} else 0
    return score


def breaking_score(article: Article, now: dt.datetime | None = None) -> int:
    score = 0
    text = article.all_text().lower()
    score += min(max(0, article.source_score // 3), 45)
    score += min(max(0, article.relevance_score), 35)
    if any(k.lower() in text for k in BREAKING_KEYWORDS):
        score += 25
    if article.topic in {"economy", "energy", "politics", "security", "real_estate", "religion"}:
        score += 15
    if article.tier in {"saudi_arab", "intl", "state"}:
        score += 10
    if article.published:
        now = now or dt.datetime.now(dt.timezone.utc)
        age_minutes = (now - article.published.astimezone(dt.timezone.utc)).total_seconds() / 60
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


def resolve_geo(article: Article, hint_iso: str = "", hint_name: str = "", prefer_domain: bool = True):
    """يحدد دولة المصدر ومنطقته من نطاق الموقع أو من تلميح المصدر."""
    hint = (geo.by_iso(hint_iso) if hint_iso else None) or (geo.by_name(hint_name) if hint_name else None)
    from_domain = geo.by_domain(article.domain)
    info = (from_domain or hint) if prefer_domain else (hint or from_domain)
    if not info:
        if hint_name and not article.country_ar:
            article.country_ar = hint_name
        return
    article.iso, article.country_tag, article.region = info
    if not article.country_ar or info is not hint:
        article.country_ar = article.country_tag


# ---------------------------------------------------------------- الشبكة والترجمة
def http_get(url: str, timeout: int = 20, **kwargs):
    try:
        headers = {"User-Agent": UA, **kwargs.pop("headers", {})}
        return requests.get(url, headers=headers, timeout=timeout, **kwargs)
    except requests.RequestException as e:
        logging.warning("HTTP error: %s", e)
        return None


def is_mostly_arabic(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return True
    arabic_letters = sum("؀" <= char <= "ۿ" or "ݐ" <= char <= "ݿ" for char in letters)
    return arabic_letters / len(letters) >= 0.35


def needs_arabic_translation(article: Article) -> bool:
    # الأردية والفارسية تُكتبان بحروف عربية لكنهما تحتاجان ترجمة
    return article.lang in {"ur", "fa"} or not is_mostly_arabic(article.title)


def translate_to_arabic(text: str, timeout: int = 10) -> str | None:
    if not text.strip():
        return None
    api_key = os.getenv("GOOGLE_TRANSLATE_API_KEY")
    if api_key:
        response = http_get(
            "https://translation.googleapis.com/language/translate/v2",
            timeout=timeout,
            headers={"x-goog-api-key": api_key},
            params={"q": text[:5000], "target": "ar", "format": "text"},
        )
        if response is not None and response.status_code == 200:
            try:
                translated = response.json()["data"]["translations"][0]["translatedText"]
                if translated.strip():
                    return html.unescape(translated)
            except (IndexError, KeyError, TypeError, ValueError) as exc:
                logging.warning("Google Cloud Translation response could not be parsed: %s", exc)
        elif response is not None:
            logging.warning("Google Cloud Translation returned HTTP %s", response.status_code)
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


# ---------------------------------------------------------------- المصادر
def _status(ok: int, attempted: int, detail: str = ""):
    if attempted == 0:
        return ("skip", "")
    return ("ok", "") if ok else ("fail", detail)


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
        if domain.startswith("www."):
            domain = domain[4:]
        article = Article(title, url, domain, domain, lang, "", pub, "gdelt", True)
        resolve_geo(article, hint_name=it.get("sourcecountry", ""), prefer_domain=False)
        out.append(article)
    return out


def fetch_gdelt(cfg, deadline):
    gd = cfg.get("gdelt", {})
    if not gd.get("enabled", True):
        return [], {}, ("skip", "")
    out, counts = [], {}
    ok = attempted = 0
    detail = ""
    for lang in gd.get("languages", ["english", "arabic"]):
        if time.monotonic() > deadline:
            break
        attempted += 1
        query = gd.get("query_terms", '"Saudi Arabia" OR Riyadh')
        url = "https://api.gdeltproject.org/api/v2/doc/doc?query=" + quote_plus(f'{query} sourcelang:{lang}') + f'&mode=artlist&format=json&maxrecords={gd.get("maxrecords", 60)}&sort=datedesc&timespan={gd.get("timespan", "2h")}'
        r = http_get(url, timeout=30)
        counts[f"gdelt:{lang}"] = 0
        if r is None or r.status_code != 200:
            detail = "تعذر الاتصال" if r is None else f"HTTP {r.status_code}"
            continue
        try:
            data = r.json() if r.text.strip() else {}
            items = (data or {}).get("articles") or []
            counts[f"gdelt:{lang}"] = len(items)
            out.extend(parse_gdelt_items(items, cfg))
            ok += 1
        except Exception as e:
            logging.warning("GDELT parse error %s: %s", lang, e)
            detail = "رد غير مفهوم: " + r.text[:80].strip()
    return out, counts, _status(ok, attempted, detail)


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
        return [], {"x": 0}, ("skip", "")

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
    articles, counts = [], {}
    ok = attempted = 0
    detail = ""
    for index, query in enumerate(queries, start=1):
        if time.monotonic() > deadline:
            break
        attempted += 1
        counts[f"x:{index}"] = 0
        try:
            response = requests.get(
                "https://api.x.com/2/tweets/search/recent",
                headers={"Authorization": "Bearer " + token, "User-Agent": UA},
                params={**params_base, "query": query},
                timeout=20,
            )
        except requests.RequestException as exc:
            logging.warning("X API request failed: %s", exc)
            detail = "تعذر الاتصال"
            continue
        if response.status_code != 200:
            logging.warning("X API returned HTTP %s: %s", response.status_code, response.text[:300])
            detail = f"HTTP {response.status_code}"
            continue
        try:
            items = parse_x_items(response.json())
            counts[f"x:{index}"] = len(items)
            articles.extend(items)
            ok += 1
        except (ValueError, TypeError, AttributeError) as exc:
            logging.warning("X API response parse failed: %s", exc)
            detail = "رد غير مفهوم"
    return articles, counts, _status(ok, attempted, detail)


def parse_gnews_rss(xml_bytes, edition):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        src = item.find("source")
        source_name = (src.text or "").strip() if src is not None else ""
        source_url = src.get("url", "") if src is not None else ""
        # أخبار Google تلحق اسم المصدر بالعنوان: "العنوان - المصدر"
        if source_name and title.endswith(" - " + source_name):
            title = title[: -len(" - " + source_name)].strip()
        pub = None
        try:
            pub = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "")
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=dt.timezone.utc)
        except Exception:
            pub = None
        # الرابط نفسه يمر عبر news.google.com، فنطاق المصدر الحقيقي يؤخذ من وسم المصدر
        domain = host_of(source_url) or host_of(link)
        article = Article(title, link, domain, source_name or domain or "Google News", edition.get("lang", "en"), edition.get("country_ar", ""), pub, "gnews", False)
        resolve_geo(article, hint_iso=edition.get("gl", ""), prefer_domain=True)
        out.append(article)
    return out


def fetch_gnews(cfg, deadline):
    gn = cfg.get("google_news", {})
    if not gn.get("enabled", True):
        return [], {}, ("skip", "")
    out, counts = [], {}
    ok = attempted = 0
    detail = ""
    recency = (gn.get("recency") or "").strip()
    for ed in gn.get("editions", []):
        if time.monotonic() > deadline:
            break
        attempted += 1
        key = f'gnews:{ed.get("lang")}-{ed.get("gl")}'
        counts[key] = 0
        q = ed.get("query", '"Saudi Arabia"')
        if recency:
            q = f"{q} when:{recency}"
        url = f'https://news.google.com/rss/search?q={quote_plus(q)}&hl={ed.get("hl", "en-US")}&gl={ed.get("gl", "US")}&ceid={quote_plus(ed.get("ceid", "US:en"))}'
        r = http_get(url)
        if r is None or r.status_code != 200:
            detail = "تعذر الاتصال" if r is None else f"HTTP {r.status_code}"
            continue
        items = parse_gnews_rss(r.content, ed)
        if items is None:
            detail = "رد غير مفهوم"
            continue
        ok += 1
        counts[key] = len(items)
        out.extend(items)
    return out, counts, _status(ok, attempted, detail)


# ---------------------------------------------------------------- الحالة
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
        for key, default in (("sent", {}), ("warned", {}), ("tr", {}), ("stories", []), ("health", {}), ("digest", {}), ("ai", {})):
            if not isinstance(self.data.get(key), type(default)):
                self.data[key] = default

    def seen(self, key: str) -> bool:
        return key in self.data["sent"]

    def seen_article(self, article: Article) -> bool:
        return self.seen(article.uid) or self.seen(title_key(article.title))

    def mark(self, article: Article):
        now = int(time.time())
        self.data["sent"][article.uid] = now
        self.data["sent"][title_key(article.title)] = now

    def cached_translation(self, title: str):
        entry = self.data["tr"].get(h(title))
        return entry[0] if entry else None

    def cache_translation(self, title: str, translated: str):
        self.data["tr"][h(title)] = [translated, int(time.time())]

    def add_story(self, tokens):
        if tokens:
            self.data["stories"].append({"t": int(time.time()), "k": sorted(tokens)})

    def recent_stories(self, hours: float):
        cutoff = time.time() - hours * 3600
        return [set(s["k"]) for s in self.data["stories"] if s.get("t", 0) > cutoff]

    def save(self):
        now = time.time()
        self.data["sent"] = {k: v for k, v in self.data["sent"].items() if v > now - 21 * 86400}
        self.data["tr"] = {k: v for k, v in self.data["tr"].items() if v[1] > now - 3 * 86400}
        self.data["stories"] = [s for s in self.data["stories"] if s.get("t", 0) > now - 4 * 86400][-800:]
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
            if r.status_code != 200:
                logging.error("Telegram returned HTTP %s: %s", r.status_code, r.text[:200])
            return r.status_code == 200
        except requests.RequestException as e:
            logging.error("Telegram send failed: %s", e)
            return False


# ---------------------------------------------------------------- كشف التكرار
def story_tokens(text: str, lang: str = "ar") -> set:
    """كلمات العنوان المميِّزة بعد التوحيد، لمقارنة خبرين."""
    text = norm_ar(text.lower()).translate(_TOKEN_FOLD)
    if lang in NO_SPACE_LANGS and not _ARABIC.search(text):
        compact = re.sub(r"[\W_]+", "", text, flags=re.U)
        return {compact[i:i + 2] for i in range(len(compact) - 1)}
    tokens = set()
    for word in re.findall(r"\w+", text, flags=re.U):
        if _ARABIC.search(word):
            for prefix in _AR_PREFIXES:
                if word.startswith(prefix) and len(word) - len(prefix) >= 3:
                    word = word[len(prefix):]
                    break
        if len(word) < 2 or word in STOPWORDS:
            continue
        tokens.add(word)
    return tokens


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    if min(len(a), len(b)) < 3:
        return 1.0 if a == b else 0.0
    return len(a & b) / len(a | b)


def similarity(a: Article, b: Article) -> float:
    best = 0.0
    if a.tok_ar and b.tok_ar:
        best = jaccard(a.tok_ar, b.tok_ar)
    if a.lang == b.lang:
        best = max(best, jaccard(a.tok_orig, b.tok_orig))
    return best


def cluster_articles(articles: list, threshold: float) -> list:
    """يجمع المقالات المتشابهة؛ أول مقال في كل مجموعة (الأعلى ترتيبًا) يمثّلها والبقية في also."""
    reps = []
    for article in articles:
        if article.origin != "x":
            for rep in reps:
                if rep.origin != "x" and similarity(article, rep) >= threshold:
                    rep.also.append(article)
                    break
            else:
                reps.append(article)
        else:
            reps.append(article)
    return reps


# ---------------------------------------------------------------- الرسائل
def publication_datetime_riyadh(article: Article):
    published = article.published
    if published is None:
        return None
    if published.tzinfo is None:
        published = published.replace(tzinfo=dt.timezone.utc)
    return published.astimezone(RIYADH)


def is_recent(article: Article, max_age_hours: float, now: dt.datetime | None = None) -> bool:
    """خبر نُشر خلال آخر max_age_hours ساعة (بدل "نفس اليوم" الذي كان يُضيع أخبار منتصف الليل)."""
    published = publication_datetime_riyadh(article)
    if published is None:
        return False
    now = now or dt.datetime.now(RIYADH)
    age = (now - published).total_seconds() / 3600
    return -1 <= age <= max_age_hours


def hashtag(text: str) -> str:
    tag = re.sub(r"[\W]+", "_", _TASHKEEL.sub("", text or ""), flags=re.U).strip("_")
    return "#" + tag if tag else ""


def unique_sources(article: Article) -> list:
    """المصادر الأخرى التي نشرت الخبر نفسه، بلا تكرار للمصدر الواحد."""
    seen = {article.source_name.lower(), article.domain}
    out = []
    for other in sorted(article.also, key=lambda a: -a.source_score):
        if other.source_name.lower() in seen or (other.domain in seen and other.domain != "news.google.com"):
            continue
        seen.update({other.source_name.lower(), other.domain})
        out.append(other)
    return out


def format_message(article: Article, cfg: dict) -> str:
    published_riyadh = publication_datetime_riyadh(article)
    shown_ar = article.title_ar if article.translated else None
    lines = []
    if published_riyadh:
        lines.append("📅 تاريخ النشر: " + published_riyadh.strftime("%Y-%m-%d"))
    if article.origin == "x":
        lines.append("𝕏 منشور جديد")
        if shown_ar:
            lines.append(f"🔁 <i>{html.escape(shown_ar[:1000])}</i>")
            lines.append(f"🔤 <b>{html.escape(article.title[:1000])}</b>")
        else:
            lines.append(f"<b>{html.escape(article.title[:1000])}</b>")
        lines.append(f"👤 {html.escape(article.source_name)}")
        if published_riyadh:
            lines.append("🕒 " + published_riyadh.strftime("%H:%M") + " (الرياض)")
        lines.append(f'🔗 <a href="{html.escape(article.url, quote=True)}">عرض المنشور</a>')
        lines.append("#إكس")
        return "\n".join(lines)

    breaking = cfg.get("breaking_mode", False) and article.breaking_score >= cfg.get("breaking_threshold", 78)
    label = cfg.get("tiers", {}).get(article.tier, {}).get("label", "⚪ مصدر آخر")
    lines.append("🚨 BREAKING NEWS" if breaking else "📰 خبر جديد")
    if shown_ar:
        lines.append(f"🔁 <b>{html.escape(shown_ar[:200])}</b>")
    if article.summary:
        lines.append(f"📝 {html.escape(article.summary)}")
    lines.append(f'🔗 <a href="{html.escape(article.url, quote=True)}">اقرأ الخبر</a>')
    original_title = html.escape(article.title[:200])
    lines.append(f"🔤 <i>{original_title}</i>" if shown_ar else f"<b>{original_title}</b>")
    lines.append(f"📌 <b>{TOPIC_LABELS.get(article.topic, 'عام')}</b> • {article.breaking_score} نقطة • {label}")
    if article.tone in TONES:
        lines.append(f"{TONE_EMOJI[article.tone]} النبرة: {TONES[article.tone]}")
    lines.append(f"🏛 {html.escape(article.source_name or article.domain)}")
    if article.country_ar:
        place = html.escape(article.country_ar)
        if article.region != "unknown":
            place += " — " + geo.region_label(article.region)
        lines.append(f"🌐 {place}")
    if published_riyadh:
        lines.append("🕒 " + published_riyadh.strftime("%H:%M") + " (الرياض)")
    others = unique_sources(article)
    if others:
        links = [f'<a href="{html.escape(o.url, quote=True)}">{html.escape(o.source_name[:40])}</a>' for o in others[:4]]
        extra = f" و{len(others) - 4} غيرها" if len(others) > 4 else ""
        lines.append("📎 نشره أيضًا: " + "، ".join(links) + extra)
    tags = [hashtag(TOPIC_TAGS.get(article.topic, "عام")), hashtag(article.country_tag)]
    if article.region != "unknown":
        tags.append(hashtag(geo.region_label(article.region)))
    lines.append(" ".join(t for t in tags if t))
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
    return cfg


# ---------------------------------------------------------------- الاختيار
def prefilter(articles, cfg, state, pats, now=None):
    """يبقي الحديث، المطابق للكلمات السعودية، غير المرسل سابقًا، بلا تكرار حرفي."""
    max_age = cfg.get("max_age_hours", 24)
    out, seen = [], set()
    for article in articles:
        if not is_recent(article, max_age, now):
            continue
        if cfg.get("strict_title_filter", True) and not title_matches(article.title, pats):
            continue
        dedupe = "d" + h(norm_title(article.title)[:180])
        if article.uid in seen or dedupe in seen or state.seen_article(article):
            continue
        seen.update({article.uid, dedupe})
        assign_tier(article, cfg)
        out.append(article)
    out.sort(key=lambda a: (a.origin != "x", -a.source_score, -(a.published.timestamp() if a.published else 0)))
    return out[: cfg.get("max_candidates", 80)]


def add_arabic_titles(candidates, cfg, state, deadline, translate=translate_to_arabic):
    failures = 0
    for article in candidates:
        if not needs_arabic_translation(article):
            article.title_ar = article.title
            continue
        if not cfg.get("translate_titles", True):
            continue
        cached = state.cached_translation(article.title)
        if cached is None and failures < 3 and time.monotonic() < deadline:
            cached = translate(article.title)
            if cached:
                state.cache_translation(article.title, cached)
                failures = 0
            else:
                failures += 1  # خدمة الترجمة متعثرة: نكفّ عن المحاولة في هذا الفحص
        if cached:
            article.title_ar = cached
            article.translated = True


def score_and_focus(candidates, cfg, pats, now=None):
    """التصنيف والنقاط بعد الترجمة، ثم استبعاد ما لا يخص السعودية فعلًا."""
    weak = compile_terms(cfg.get("weak_terms", DEFAULT_WEAK_TERMS))
    weak_sources = {p.pattern for p in weak}
    strong = [p for p in pats if p.pattern not in weak_sources]
    now_utc = now.astimezone(dt.timezone.utc) if now else None
    out = []
    for article in candidates:
        text = article.all_text()
        article.topic = classify_topic(text)
        article.relevance_score = compute_relevance(article, pats)
        article.breaking_score = breaking_score(article, now_utc)
        article.tok_orig = story_tokens(article.title, article.lang)
        article.tok_ar = story_tokens(article.title_ar, "ar") if article.title_ar else None
        if cfg.get("saudi_focus", False) and article.breaking_score < cfg.get("breaking_threshold", 78):
            lowered = text.lower()
            explicit = any(k in lowered for k in FOCUS_KEYWORDS) or title_matches(article.title, strong)
            if not explicit:
                continue
        out.append(article)
    return out


def sort_key(article: Article, cfg: dict):
    main = article.breaking_score if cfg.get("breaking_mode") else article.relevance_score
    bonus = 3 * min(len(unique_sources(article)), 5)
    return (-(main + bonus), -article.source_score, -(article.published.timestamp() if article.published else 0))


def select_clusters(clusters, cfg):
    """منشورات X أولًا بحدّها، ثم حصة لكل منطقة، ثم الأعلى نقاطًا مع حدود اللغات."""
    max_total = cfg.get("max_messages_per_run", 12)
    if cfg.get("test_latest"):
        # إرسال تجريبي: أحدث الأخبار نشرًا فقط، بلا حصص ولا حدود لغات
        news = [c for c in clusters if c.origin != "x"]
        news.sort(key=lambda a: -(a.published.timestamp() if a.published else 0))
        return news[:max_total]
    x_posts = [c for c in clusters if c.origin == "x"][: cfg.get("x", {}).get("max_per_run", 5)]
    news = sorted((c for c in clusters if c.origin != "x"), key=lambda a: sort_key(a, cfg))
    slots = max(0, max_total - len(x_posts))
    default_cap = cfg.get("max_per_language", 2)
    caps = cfg.get("max_per_language_overrides", {}) or {}
    lang_counts, picked = {}, []

    def take(article):
        picked.append(article)
        lang_counts[article.lang] = lang_counts.get(article.lang, 0) + 1

    regions_cfg = cfg.get("regions", {}) or {}
    per_region = int(regions_cfg.get("min_per_run", 1))
    quota = int(slots * float(regions_cfg.get("quota_share", 0.5)))
    if per_region > 0:
        for region in regions_cfg.get("priority", DEFAULT_REGION_PRIORITY):
            got = 0
            for article in news:
                if quota <= 0 or got >= per_region:
                    break
                if article.region == region and article not in picked:
                    take(article)
                    got += 1
                    quota -= 1
    for article in news:
        if len(picked) >= slots:
            break
        if article in picked:
            continue
        if lang_counts.get(article.lang, 0) >= caps.get(article.lang, default_cap):
            continue
        take(article)
    picked.sort(key=lambda a: sort_key(a, cfg))
    return x_posts + picked[:slots]


# ---------------------------------------------------------------- التنبيهات والموجز
def check_health(statuses: dict, cfg: dict, state: State, tg: Telegram, now_ts: float | None = None):
    """رسالة واحدة إذا تعطل مصدر عدة ساعات متواصلة، ورسالة عند عودته."""
    now_ts = now_ts or time.time()
    after = float((cfg.get("health", {}) or {}).get("alert_after_hours", 3))
    health = state.data["health"]
    for source, (status, detail) in statuses.items():
        name = SOURCE_NAMES_AR.get(source, source)
        entry = health.setdefault(source, {})
        if status == "skip":
            continue
        if status == "ok":
            if entry.get("alerted"):
                tg.send_text(f"✅ عاد المصدر إلى العمل: <b>{name}</b>")
            entry.clear()
            continue
        entry.setdefault("fail_since", int(now_ts))
        hours = (now_ts - entry["fail_since"]) / 3600
        if hours >= after and not entry.get("alerted"):
            reason = f"\nالسبب الظاهر: {html.escape(detail)}" if detail else ""
            if tg.send_text(f"⚠️ <b>تنبيه:</b> المصدر <b>{name}</b> متوقف منذ {int(hours)} ساعات.{reason}\nباقي المصادر تعمل، وسأخبرك عند عودته."):
                entry["alerted"] = True


def maybe_send_digests(cfg: dict, state: State, tg: Telegram, archive: Archive, now: dt.datetime | None = None):
    d = cfg.get("digest", {}) or {}
    if not d.get("enabled", True):
        return
    now = now or dt.datetime.now(RIYADH)
    if now.hour < int(d.get("hour", 21)):
        return
    today = now.date().isoformat()
    done = state.data["digest"]
    region_labels = dict(geo.REGIONS_AR)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if done.get("daily") != today:
        text = build_digest(archive.load_since(midnight), f"موجز اليوم — {today}", int(d.get("top_n", 10)),
                            TOPIC_LABELS, region_labels, TONES)
        if text is None or tg.send_text(text):
            done["daily"] = today
    if now.weekday() == int(d.get("weekly_day", 4)) and done.get("weekly") != today:
        start = midnight - dt.timedelta(days=6)
        week = archive.load_since(start)
        if not week or min(r.get("ts", 0) for r in week) > (midnight - dt.timedelta(days=3)).timestamp():
            week = []  # الأرشيف لم يغطِّ أسبوعًا بعد (أول أيام التشغيل): لا موجز أسبوعي
        text = build_digest(week, f"الموجز الأسبوعي — {start.date().isoformat()} إلى {today}",
                            int(d.get("top_n", 10)), TOPIC_LABELS, region_labels, TONES)
        if text is None or tg.send_text(text):
            done["weekly"] = today


def archive_record(article: Article) -> dict:
    return {
        "ts": int(time.time()),
        "title": article.title[:300],
        "title_ar": (article.title_ar or "")[:300],
        "url": article.url,
        "domain": article.domain,
        "source": article.source_name,
        "lang": article.lang,
        "country": article.country_tag or article.country_ar,
        "region": article.region,
        "topic": article.topic,
        "tone": article.tone,
        "score": article.breaking_score,
        "origin": article.origin,
        "also": len(unique_sources(article)),
    }


# ---------------------------------------------------------------- التشغيل
def run(cfg: dict, state: State, tg: Telegram, fast=False, breaking=False, archive: Archive | None = None,
        now: dt.datetime | None = None, fetchers=None, limit: int = 0) -> int:
    cfg = dict(cfg)
    if breaking:
        cfg["breaking_mode"] = True
        cfg["breaking_threshold"] = cfg.get("breaking_threshold", 78)
        cfg["strict_title_filter"] = True
        cfg["max_messages_per_run"] = cfg.get("breaking_max_messages", 4)
        cfg["max_per_language"] = cfg.get("breaking_per_language", 2)
        cfg["gdelt"] = {**cfg.get("gdelt", {}), "timespan": "1h", "maxrecords": 80}
    if fast:
        cfg["max_messages_per_run"] = cfg.get("fast_max_messages", 10)
    if limit:
        cfg["max_messages_per_run"] = int(limit)
        cfg["test_latest"] = True
    cfg = apply_saudi_focus(cfg)
    archive = archive or Archive(ARCHIVE_DIR)
    now = now or dt.datetime.now(RIYADH)

    deadline = time.monotonic() + cfg.get("total_time_budget_sec", 900)
    articles, counts, statuses = [], {}, {}
    for name, fetch in (fetchers or {"x": fetch_x, "gnews": fetch_gnews, "gdelt": fetch_gdelt}).items():
        found, c, status = fetch(cfg, deadline)
        articles.extend(found)
        counts.update(c)
        statuses[name] = status

    pats = compile_terms(cfg.get("title_must_match_any", []))
    candidates = prefilter(articles, cfg, state, pats, now)
    add_arabic_titles(candidates, cfg, state, deadline)
    candidates = score_and_focus(candidates, cfg, pats, now)
    candidates.sort(key=lambda a: (a.origin != "x",) + sort_key(a, cfg))

    dedupe_cfg = cfg.get("dedupe", {}) or {}
    threshold = float(dedupe_cfg.get("similarity", 0.6))
    clusters = cluster_articles(candidates, threshold)

    # خبر سبق نشره من مصدر آخر خلال اليومين الماضيين: لا يُعاد
    known = state.recent_stories(float(dedupe_cfg.get("memory_hours", 48)))
    fresh = []
    for rep in clusters:
        tokens = rep.tok_ar or set()
        if rep.origin != "x" and tokens and any(jaccard(tokens, old) >= threshold for old in known):
            for member in [rep] + rep.also:
                state.mark(member)
            continue
        fresh.append(rep)

    chosen = select_clusters(fresh, cfg)
    ai = AIEnricher(cfg, state.data, now.date().isoformat(), [t for t in TOPIC_LABELS])
    sent = 0
    for article in chosen:
        if article.origin != "x" and ai.available() and time.monotonic() < deadline:
            info = ai.enrich(article.title, article.source_name, article.url, article.domain)
            if info:
                if info["title_ar"] and needs_arabic_translation(article):
                    article.title_ar, article.translated = info["title_ar"], True
                article.summary = info["summary_ar"]
                article.tone = info["tone"]
                if info["topic"]:
                    article.topic = info["topic"]
        if tg.send_text(format_message(article, cfg)):
            for member in [article] + article.also:
                state.mark(member)
            if article.origin != "x":
                state.add_story(article.tok_ar)
            archive.add(archive_record(article))
            sent += 1
        if not tg.dry_run:
            time.sleep(2)

    if not cfg.get("test_latest"):
        check_health(statuses, cfg, state, tg)
        maybe_send_digests(cfg, state, tg, archive, now)
    logging.info("collected=%d candidates=%d stories=%d sent=%d sources=%s ai_calls_today=%s",
                 len(articles), len(candidates), len(fresh), sent,
                 {k: v[0] for k, v in statuses.items()}, state.data["ai"].get("calls", 0))
    return sent


def main():
    ap = argparse.ArgumentParser(description="Saudi News Watch")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--breaking", action="store_true")
    ap.add_argument("--saudi", action="store_true", help="Saudi-focused mode")
    ap.add_argument("--test-telegram", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="إرسال تجريبي: أحدث N أخبار فقط")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = yaml.safe_load(Path(args.config).read_text("utf-8")) or {}
    if args.breaking:
        cfg["breaking_mode"] = True
    tg = Telegram(dry_run=args.dry_run)
    if args.test_telegram:
        tg.send_text("✅ القناة جاهزة! يتم رصد ما يكتب عن السعودية في العالم.")
        return
    state = State()
    archive = Archive(ARCHIVE_DIR)
    run(cfg, state, tg, fast=args.fast, breaking=args.breaking, archive=archive, limit=args.limit)
    if tg.dry_run:
        logging.info("Dry run: nothing was saved")
        return
    state.save()
    archive.save()


if __name__ == "__main__":
    main()
