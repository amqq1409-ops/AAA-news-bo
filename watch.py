"""قسم "دول ورؤساء": منشورات المصادر المتابَعة التي تذكر دولة أو رئيسًا.

المصادر مجانية كلها (بديل عن متابعة حسابات X المدفوعة):
  - قنوات تيليجرام العامة (صفحة المعاينة t.me/s/…)
  - حسابات Bluesky للصحفيين الموجودين في قائمة X (واجهة عامة بلا مفتاح)
  - خلاصات المواقع الرسمية والمؤسسات الإخبارية (تُقرأ بقارئ الخلاصات في news_bot)

صيغة الكلمات مثل config.yaml:  "=كلمة" كلمة كاملة فقط، وغير ذلك جذر يُقبل ما بعده.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

POST_ORIGINS = {"tg", "bsky"}
BSKY_API = "https://public.api.bsky.app/xrpc/"

_TASHKEEL = re.compile(r"[ً-ٰٟـ]")
_ALEF = str.maketrans("أإآٱ", "اااا")


_ARTICLE = re.compile(r"^(=?)ال(?=\S{3,})")


def norm(text: str) -> str:
    return _TASHKEEL.sub("", text or "").translate(_ALEF).lower()


# الرمز: (الاسم العربي، كلمات المطابقة، أنماط حساسة لحالة الأحرف مثل US و UK)
COUNTRIES = {
    "US": ("أمريكا", ["united states", "u.s.", "america", "white house", "pentagon",
                      "أمريك", "أميرك", "الولايات المتحدة", "واشنطن", "البيت الأبيض", "البنتاغون"], [r"\bUSA?\b"]),
    "RU": ("روسيا", ["russia", "kremlin", "moscow", "روسي", "موسكو", "الكرملين"], []),
    "CN": ("الصين", ["china", "chinese", "beijing", "=الصين", "=صيني", "=صينية", "=بكين"], []),
    "IR": ("إيران", ["iran", "tehran", "إيران", "=طهران"], []),
    "IL": ("إسرائيل", ["israel", "=idf", "tel aviv", "إسرائيل", "تل أبيب"], []),
    "PS": ("فلسطين", ["gaza", "palestin", "hamas", "west bank", "=غزة", "فلسطين", "=حماس", "الضفة الغربية"], []),
    "UA": ("أوكرانيا", ["ukrain", "kyiv", "kiev", "أوكراني", "=كييف"], []),
    "GB": ("بريطانيا", ["britain", "british", "united kingdom", "u.k.", "downing street", "بريطاني", "=لندن"], [r"\bUK\b"]),
    "FR": ("فرنسا", ["=france", "=french", "=paris", "فرنس", "=باريس"], []),
    "DE": ("ألمانيا", ["german", "=berlin", "ألماني", "=برلين"], []),
    "IT": ("إيطاليا", ["italy", "italian", "=rome", "إيطالي", "=روما"], []),
    "ES": ("إسبانيا", ["spain", "spanish", "إسباني"], []),
    "TR": ("تركيا", ["=turkey", "turkish", "türkiye", "turkiye", "ankara", "=تركيا", "=تركي", "=تركية", "=أنقرة"], []),
    "SY": ("سوريا", ["syria", "damascus", "سوري", "=دمشق"], []),
    "IQ": ("العراق", ["iraq", "baghdad", "=العراق", "=عراقي", "=عراقية", "=بغداد"], []),
    "LB": ("لبنان", ["leban", "beirut", "hezbollah", "لبنان", "=بيروت", "حزب الله"], []),
    "EG": ("مصر", ["egypt", "cairo", "=مصر", "=مصري", "=مصرية", "=القاهرة"], []),
    "JO": ("الأردن", ["=jordanian", "=amman", "أردن"], []),
    "YE": ("اليمن", ["yemen", "houthi", "=اليمن", "=يمني", "=يمنية", "حوثي", "=صنعاء"], []),
    "SD": ("السودان", ["sudan", "khartoum", "سودان", "الخرطوم"], []),
    "LY": ("ليبيا", ["libya", "=ليبيا", "=ليبي", "=ليبية", "=طرابلس"], []),
    "TN": ("تونس", ["tunisia", "=تونس", "=تونسي", "=تونسية"], []),
    "DZ": ("الجزائر", ["algeria", "جزائر"], []),
    "MA": ("المغرب", ["morocc", "=المغرب", "=مغربي", "=مغربية"], []),
    "IN": ("الهند", ["=india", "=indian", "=indians", "new delhi", "=الهند", "=هندي", "=هندية", "نيودلهي"], []),
    "PK": ("باكستان", ["pakistan", "islamabad", "باكستان", "إسلام آباد"], []),
    "AF": ("أفغانستان", ["afghan", "taliban", "kabul", "أفغان", "طالبان"], []),
    "JP": ("اليابان", ["japan", "tokyo", "يابان", "=طوكيو"], []),
    "KR": ("كوريا الجنوبية", ["south korea", "seoul", "كوريا الجنوبية", "=سيول"], []),
    "KP": ("كوريا الشمالية", ["north korea", "pyongyang", "كوريا الشمالية", "بيونغ يانغ"], []),
    "TW": ("تايوان", ["taiwan", "taipei", "تايوان"], []),
    "CA": ("كندا", ["canad", "ottawa", "=كندا", "=كندي", "=كندية"], []),
    "MX": ("المكسيك", ["mexic", "المكسيك"], []),
    "BR": ("البرازيل", ["brazil", "برازيل"], []),
    "VE": ("فنزويلا", ["venezuel", "caracas", "فنزويل"], []),
    "CU": ("كوبا", ["=cuba", "cuban", "havana", "=كوبا"], []),
    "CO": ("كولومبيا", ["colombia", "كولومبيا"], []),
    "AR": ("الأرجنتين", ["argentin", "الأرجنتين"], []),
    "PA": ("بنما", ["panama", "=بنما"], []),
    "ET": ("إثيوبيا", ["ethiopia", "إثيوبي"], []),
    "SO": ("الصومال", ["somali", "صومال"], []),
    "NG": ("نيجيريا", ["nigeria", "نيجيري"], []),
    "ZA": ("جنوب أفريقيا", ["south africa", "جنوب أفريقيا", "جنوب إفريقيا"], []),
    "KE": ("كينيا", ["kenya", "=كينيا"], []),
    "GR": ("اليونان", ["greece", "=greek", "=اليونان", "=يوناني"], []),
    "PL": ("بولندا", ["poland", "warsaw", "بولندا"], []),
    "HU": ("المجر", ["hungar", "=المجر", "=مجري"], []),
    "RS": ("صربيا", ["serbia", "صربيا"], []),
    "SE": ("السويد", ["sweden", "swedish", "السويد"], []),
    "NO": ("النرويج", ["norway", "norwegian", "النرويج"], []),
    "DK": ("الدنمارك", ["denmark", "danish", "greenland", "الدنمارك", "غرينلاند"], []),
    "NL": ("هولندا", ["netherlands", "=dutch", "هولندا"], []),
    "BE": ("بلجيكا", ["belgi", "بلجيكا"], []),
    "CH": ("سويسرا", ["switzerland", "=swiss", "سويسرا"], []),
    "AT": ("النمسا", ["austria", "النمسا"], []),
    "BY": ("بيلاروسيا", ["belarus", "بيلاروسيا"], []),
    "AM": ("أرمينيا", ["armenia", "أرمينيا"], []),
    "AZ": ("أذربيجان", ["azerbaijan", "أذربيجان"], []),
    "KZ": ("كازاخستان", ["kazakh", "كازاخستان"], []),
    "UZ": ("أوزبكستان", ["uzbek", "أوزبكستان"], []),
    "AU": ("أستراليا", ["australia", "أستراليا"], []),
    "NZ": ("نيوزيلندا", ["new zealand", "نيوزيلندا"], []),
    "ID": ("إندونيسيا", ["indonesia", "إندونيسيا"], []),
    "MY": ("ماليزيا", ["malaysia", "ماليزيا"], []),
    "PH": ("الفلبين", ["philippin", "الفلبين"], []),
    "VN": ("فيتنام", ["vietnam", "فيتنام"], []),
    "TH": ("تايلاند", ["thailand", "=thai", "تايلاند"], []),
    "SG": ("سنغافورة", ["singapore", "سنغافورة"], []),
    "BD": ("بنغلاديش", ["bangladesh", "بنغلاديش"], []),
    "EU": ("الاتحاد الأوروبي", ["european union", "brussels", "الاتحاد الأوروبي", "=بروكسل"], [r"\bEU\b"]),
}


class Matcher:
    """يستخرج الدول المذكورة في نص (بأسمائها أو بأسماء رؤسائها) مرتبة بحسب موضع أول ورود."""

    def __init__(self, compile_terms, leaders: dict | None = None):
        self.rules = []   # (الرمز، النمط، يُطابق على النص الأصلي بحالة أحرفه؟)
        for iso, (_, terms, cased) in COUNTRIES.items():
            # "ال" التعريف تُحذف من الكلمة العربية لأن النمط يقبلها هي و"لل" و"بال" تلقائيًا
            for pattern in compile_terms([norm(_ARTICLE.sub(r"\1", t)) for t in terms]):
                self.rules.append((iso, pattern, False))
            for raw in cased:
                self.rules.append((iso, re.compile(raw), True))
        for iso, names in (leaders or {}).items():
            iso = str(iso).upper()
            if iso not in COUNTRIES and iso != "XX":
                continue
            for pattern in compile_terms([norm(str(n)) for n in names or []]):
                self.rules.append((iso, pattern, False))
        self.patterns = [rule[1] for rule in self.rules if not rule[2]]

    def subjects(self, text: str) -> list:
        lowered = norm(text)
        first = {}
        for iso, pattern, cased in self.rules:
            match = pattern.search(text if cased else lowered)
            if match and (iso not in first or match.start() < first[iso]):
                first[iso] = match.start()
        return [iso for iso, _ in sorted(first.items(), key=lambda kv: kv[1])]


def name_ar(iso: str) -> str:
    return COUNTRIES[iso][0] if iso in COUNTRIES else ""


# ---------------------------------------------------------------- قائمة الحسابات
def load_handles(path) -> list:
    """معرّفات X من ملف القائمة (معرّف في كل سطر؛ ما بعد # تعليق)."""
    out, seen = [], set()
    try:
        lines = Path(path).read_text("utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        handle = line.split("#", 1)[0].strip().lstrip("@")
        if handle and re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle) and handle.lower() not in seen:
            seen.add(handle.lower())
            out.append(handle)
    return out


# ---------------------------------------------------------------- تيليجرام
_TG_SPLIT = re.compile(r'<div class="tgme_widget_message_wrap')
_TG_POST = re.compile(r'data-post="([^"/]+)/(\d+)"')
_TG_TEXT = re.compile(r'<div class="tgme_widget_message_text[^"]*js-message_text[^"]*"[^>]*>(.*?)</div>', re.S)
_TG_TIME = re.compile(r'<time[^>]*datetime="([^"]+)"')
_TAGS = re.compile(r"<[^>]+>")


def clean_html(fragment: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", fragment or "", flags=re.I)
    return re.sub(r"\s+", " ", html.unescape(_TAGS.sub("", text))).strip()


def parse_telegram(page: str, channel: dict) -> list:
    """منشورات قناة تيليجرام من صفحة المعاينة العامة. يعيد قائمة قواميس: text, url, published."""
    out = []
    for block in _TG_SPLIT.split(page or "")[1:]:
        post = _TG_POST.search(block)
        body = _TG_TEXT.search(block)
        if not post or not body:
            continue
        text = clean_html(body.group(1))
        if len(text) < 15:
            continue
        published = None
        stamp = _TG_TIME.search(block)
        if stamp:
            try:
                published = dt.datetime.fromisoformat(stamp.group(1).replace("Z", "+00:00"))
                if published.tzinfo is None:
                    published = published.replace(tzinfo=dt.timezone.utc)
            except ValueError:
                published = None
        out.append({"text": text, "url": f"https://t.me/{post.group(1)}/{post.group(2)}", "published": published,
                    "source": channel.get("name") or post.group(1), "lang": channel.get("lang", "ar")})
    return out


def fetch_telegram(wcfg: dict, deadline: float, http_get, log) -> tuple:
    tc = wcfg.get("telegram", {}) or {}
    channels = [c for c in tc.get("channels", []) if c.get("id")]
    if not tc.get("enabled", True) or not channels:
        return [], {}, ("skip", "")

    def fetch_one(channel):
        if time.monotonic() > deadline:
            return None
        return http_get(f'https://t.me/s/{channel["id"]}', timeout=int(tc.get("timeout_sec", 10)))

    with ThreadPoolExecutor(max_workers=max(1, min(8, len(channels)))) as pool:
        responses = list(pool.map(fetch_one, channels))
    rows, counts, ok, detail = [], {}, 0, ""
    for channel, response in zip(channels, responses):
        key = "tg:" + channel["id"]
        counts[key] = 0
        if response is None or response.status_code != 200:
            detail = "تعذر الاتصال" if response is None else f"HTTP {response.status_code}"
            log("telegram %-26s %s", channel["id"], detail)
            continue
        items = parse_telegram(response.text, channel)
        log("telegram %-26s items=%d", channel["id"], len(items))
        if not items:
            detail = "لا منشورات (اسم القناة قد يكون خطأ)"
            continue
        ok += 1
        counts[key] = len(items)
        rows.extend(items)
    return rows, counts, ("ok", "") if ok else ("fail", detail)


# ---------------------------------------------------------------- Bluesky
def bsky_candidate(x_handle: str) -> str:
    """الاسم المحتمل للحساب نفسه على Bluesky (كثير من الصحفيين يحتفظون بالمعرّف نفسه)."""
    return re.sub(r"[^a-z0-9-]", "", x_handle.lower().replace("_", "")) + ".bsky.social"


def trusted_profile(profile: dict, min_followers: int) -> bool:
    """حساب موثّق أو له متابعون كُثُر: حماية من الحسابات المنتحِلة للاسم نفسه."""
    verified = ((profile.get("verification") or {}).get("verifiedStatus") == "valid")
    return verified or (int(profile.get("followersCount") or 0) >= min_followers and int(profile.get("postsCount") or 0) >= 20)


def resolve_bluesky(handles: list, store: dict, bc: dict, deadline: float, http_get, log, now_ts=None) -> int:
    """يبحث عن حسابات القائمة على Bluesky على دفعات صغيرة، ويحفظ النتيجة في store["map"]."""
    now_ts = now_ts or time.time()
    known = store.setdefault("map", {})
    retry_after = float(bc.get("retry_days", 14)) * 86400
    pending = [h for h in handles if h.lower() not in known
               or (not known[h.lower()].get("h") and now_ts - known[h.lower()].get("t", 0) > retry_after)]
    found = 0
    for start in range(0, min(len(pending), int(bc.get("resolve_per_run", 50))), 25):
        if time.monotonic() > deadline:
            break
        batch = pending[start:start + 25]
        wanted = {bsky_candidate(h): h.lower() for h in batch}
        wanted = {cand: key for cand, key in wanted.items() if len(cand) > len(".bsky.social") + 2}
        response = http_get(BSKY_API + "app.bsky.actor.getProfiles", timeout=10, params=[("actors", c) for c in wanted])
        profiles = None
        if response is not None and response.status_code == 200:
            try:
                profiles = response.json().get("profiles", [])
            except ValueError:
                profiles = None
        if profiles is None:
            # الطلب المجمّع رُفض (قد يحدث إن كان أحد الأسماء غير موجود): نسأل عن كل اسم وحده
            profiles = []
            for cand in wanted:
                if time.monotonic() > deadline:
                    return found
                single = http_get(BSKY_API + "app.bsky.actor.getProfile", timeout=8, params={"actor": cand})
                if single is None:
                    return found  # الخدمة لا ترد: نعيد المحاولة في فحص لاحق دون تسجيل "غير موجود"
                if single.status_code == 200:
                    try:
                        profiles.append(single.json())
                    except ValueError:
                        pass
        by_handle = {(p.get("handle") or "").lower(): p for p in profiles}
        for cand, key in wanted.items():
            profile = by_handle.get(cand)
            if profile and trusted_profile(profile, int(bc.get("min_followers", 1000))):
                known[key] = {"h": cand, "d": profile.get("did", ""), "n": (profile.get("displayName") or "")[:60], "t": int(now_ts)}
                found += 1
            else:
                known[key] = {"t": int(now_ts)}
        for h in batch:
            known.setdefault(h.lower(), {"t": int(now_ts)})
    if pending:
        log("bluesky resolve: checked=%d found=%d known_accounts=%d", min(len(pending), int(bc.get("resolve_per_run", 50))),
            found, sum(1 for v in known.values() if v.get("h")))
    return found


def parse_bluesky_feed(payload: dict) -> list:
    out = []
    for item in (payload or {}).get("feed", []):
        if item.get("reason"):
            continue  # إعادة نشر لمنشور غيره
        post = item.get("post") or {}
        record = post.get("record") or {}
        author = post.get("author") or {}
        text = re.sub(r"\s+", " ", record.get("text") or "").strip()
        handle = author.get("handle") or ""
        uri = post.get("uri") or ""
        if len(text) < 15 or not handle or "/app.bsky.feed.post/" not in uri or record.get("reply"):
            continue
        published = None
        try:
            published = dt.datetime.fromisoformat((record.get("createdAt") or "").replace("Z", "+00:00"))
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            published = None
        langs = record.get("langs") or ["en"]
        out.append({"text": text, "url": f'https://bsky.app/profile/{handle}/post/{uri.rsplit("/", 1)[-1]}',
                    "published": published, "source": f'{author.get("displayName") or handle} (@{handle})',
                    "lang": str(langs[0])[:2].lower() or "en"})
    return out


def fetch_bluesky(wcfg: dict, store: dict, handles: list, deadline: float, http_get, log, resolve: bool = True) -> tuple:
    bc = wcfg.get("bluesky", {}) or {}
    if not bc.get("enabled", True):
        return [], {}, ("skip", "")
    if resolve:
        resolve_bluesky(handles, store, bc, deadline, http_get, log)
    actors = [str(h).lower() for h in bc.get("handles", []) if h]
    actors += sorted(v["h"] for v in store.get("map", {}).values() if v.get("h") and v["h"] not in actors)
    if not actors:
        return [], {}, ("skip", "")
    # كل فحص يقرأ جزءًا من الحسابات بالتناوب، فتُقرأ كلها خلال دقائق دون إثقال على الخدمة
    per_run = max(1, int(bc.get("per_run", 30)))
    cursor = int(store.get("cur", 0)) % len(actors)
    chosen = [actors[(cursor + i) % len(actors)] for i in range(min(per_run, len(actors)))]
    store["cur"] = (cursor + len(chosen)) % len(actors)

    def fetch_one(actor):
        if time.monotonic() > deadline:
            return None
        return http_get(BSKY_API + "app.bsky.feed.getAuthorFeed", timeout=int(bc.get("timeout_sec", 8)),
                        params={"actor": actor, "limit": 5, "filter": "posts_no_replies"})

    with ThreadPoolExecutor(max_workers=max(1, int(bc.get("parallel", 10)))) as pool:
        responses = list(pool.map(fetch_one, chosen))
    rows, ok, detail = [], 0, ""
    for actor, response in zip(chosen, responses):
        if response is None or response.status_code != 200:
            detail = "تعذر الاتصال" if response is None else f"HTTP {response.status_code}"
            continue
        try:
            rows.extend(parse_bluesky_feed(response.json()))
            ok += 1
        except ValueError:
            detail = "رد غير مفهوم"
    log("bluesky accounts=%d read=%d ok=%d posts=%d", len(actors), len(chosen), ok, len(rows))
    return rows, {"bsky": len(rows)}, ("ok", "") if ok else ("fail", detail)
