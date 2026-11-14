"""الدول والمناطق: تحويل اسم الدولة أو رمزها أو نطاق الموقع إلى اسم عربي ومنطقة."""
from __future__ import annotations

REGIONS_AR = {
    "arab": "العالم العربي",
    "mideast": "الشرق الأوسط",
    "east_asia": "شرق آسيا",
    "southeast_asia": "جنوب شرق آسيا",
    "south_asia": "جنوب آسيا",
    "central_asia": "آسيا الوسطى والقوقاز",
    "africa": "أفريقيا",
    "europe": "أوروبا",
    "north_america": "أمريكا الشمالية",
    "latin_america": "أمريكا اللاتينية",
    "oceania": "أوقيانوسيا",
    "unknown": "غير محدد",
}

# الرمز: (الأسماء الإنجليزية كما ترد من المصادر، الاسم العربي، المنطقة)
_COUNTRIES = {
    # العالم العربي
    "SA": (["saudi arabia"], "السعودية", "arab"),
    "AE": (["united arab emirates", "uae"], "الإمارات", "arab"),
    "QA": (["qatar"], "قطر", "arab"),
    "KW": (["kuwait"], "الكويت", "arab"),
    "BH": (["bahrain"], "البحرين", "arab"),
    "OM": (["oman"], "عُمان", "arab"),
    "YE": (["yemen"], "اليمن", "arab"),
    "JO": (["jordan"], "الأردن", "arab"),
    "LB": (["lebanon"], "لبنان", "arab"),
    "SY": (["syria"], "سوريا", "arab"),
    "IQ": (["iraq"], "العراق", "arab"),
    "PS": (["palestine", "west bank", "gaza strip", "palestinian territories"], "فلسطين", "arab"),
    "EG": (["egypt"], "مصر", "arab"),
    "SD": (["sudan"], "السودان", "arab"),
    "LY": (["libya"], "ليبيا", "arab"),
    "TN": (["tunisia"], "تونس", "arab"),
    "DZ": (["algeria"], "الجزائر", "arab"),
    "MA": (["morocco"], "المغرب", "arab"),
    "MR": (["mauritania"], "موريتانيا", "arab"),
    # الشرق الأوسط غير العربي
    "TR": (["turkey", "turkiye", "türkiye"], "تركيا", "mideast"),
    "IR": (["iran"], "إيران", "mideast"),
    "IL": (["israel"], "إسرائيل", "mideast"),
    "CY": (["cyprus"], "قبرص", "mideast"),
    # شرق آسيا
    "CN": (["china"], "الصين", "east_asia"),
    "JP": (["japan"], "اليابان", "east_asia"),
    "KR": (["south korea", "korea, republic of", "republic of korea"], "كوريا الجنوبية", "east_asia"),
    "KP": (["north korea"], "كوريا الشمالية", "east_asia"),
    "TW": (["taiwan"], "تايوان", "east_asia"),
    "HK": (["hong kong"], "هونغ كونغ", "east_asia"),
    "MO": (["macau", "macao"], "ماكاو", "east_asia"),
    "MN": (["mongolia"], "منغوليا", "east_asia"),
    # جنوب شرق آسيا
    "ID": (["indonesia"], "إندونيسيا", "southeast_asia"),
    "MY": (["malaysia"], "ماليزيا", "southeast_asia"),
    "SG": (["singapore"], "سنغافورة", "southeast_asia"),
    "TH": (["thailand"], "تايلاند", "southeast_asia"),
    "VN": (["vietnam", "viet nam"], "فيتنام", "southeast_asia"),
    "PH": (["philippines"], "الفلبين", "southeast_asia"),
    "MM": (["myanmar", "burma"], "ميانمار", "southeast_asia"),
    "KH": (["cambodia"], "كمبوديا", "southeast_asia"),
    "LA": (["laos"], "لاوس", "southeast_asia"),
    "BN": (["brunei"], "بروناي", "southeast_asia"),
    # جنوب آسيا
    "IN": (["india"], "الهند", "south_asia"),
    "PK": (["pakistan"], "باكستان", "south_asia"),
    "BD": (["bangladesh"], "بنغلاديش", "south_asia"),
    "LK": (["sri lanka"], "سريلانكا", "south_asia"),
    "NP": (["nepal"], "نيبال", "south_asia"),
    "AF": (["afghanistan"], "أفغانستان", "south_asia"),
    "MV": (["maldives"], "المالديف", "south_asia"),
    "BT": (["bhutan"], "بوتان", "south_asia"),
    # آسيا الوسطى والقوقاز
    "KZ": (["kazakhstan"], "كازاخستان", "central_asia"),
    "UZ": (["uzbekistan"], "أوزبكستان", "central_asia"),
    "KG": (["kyrgyzstan"], "قيرغيزستان", "central_asia"),
    "TJ": (["tajikistan"], "طاجيكستان", "central_asia"),
    "TM": (["turkmenistan"], "تركمانستان", "central_asia"),
    "AZ": (["azerbaijan"], "أذربيجان", "central_asia"),
    "AM": (["armenia"], "أرمينيا", "central_asia"),
    "GE": (["georgia"], "جورجيا", "central_asia"),
    # أفريقيا
    "NG": (["nigeria"], "نيجيريا", "africa"),
    "KE": (["kenya"], "كينيا", "africa"),
    "ZA": (["south africa"], "جنوب أفريقيا", "africa"),
    "ET": (["ethiopia"], "إثيوبيا", "africa"),
    "SO": (["somalia"], "الصومال", "africa"),
    "GH": (["ghana"], "غانا", "africa"),
    "SN": (["senegal"], "السنغال", "africa"),
    "CI": (["ivory coast", "cote d'ivoire", "côte d'ivoire"], "ساحل العاج", "africa"),
    "TZ": (["tanzania"], "تنزانيا", "africa"),
    "UG": (["uganda"], "أوغندا", "africa"),
    "RW": (["rwanda"], "رواندا", "africa"),
    "CM": (["cameroon"], "الكاميرون", "africa"),
    "ML": (["mali"], "مالي", "africa"),
    "NE": (["niger"], "النيجر", "africa"),
    "TD": (["chad"], "تشاد", "africa"),
    "DJ": (["djibouti"], "جيبوتي", "africa"),
    "ER": (["eritrea"], "إريتريا", "africa"),
    "SS": (["south sudan"], "جنوب السودان", "africa"),
    "ZW": (["zimbabwe"], "زيمبابوي", "africa"),
    "ZM": (["zambia"], "زامبيا", "africa"),
    "MZ": (["mozambique"], "موزمبيق", "africa"),
    "AO": (["angola"], "أنغولا", "africa"),
    "CD": (["democratic republic of the congo", "dr congo", "congo, democratic republic of the"], "الكونغو الديمقراطية", "africa"),
    "CG": (["congo", "republic of the congo"], "الكونغو", "africa"),
    "GM": (["gambia"], "غامبيا", "africa"),
    "GN": (["guinea"], "غينيا", "africa"),
    "SL": (["sierra leone"], "سيراليون", "africa"),
    "LR": (["liberia"], "ليبيريا", "africa"),
    "BF": (["burkina faso"], "بوركينا فاسو", "africa"),
    "BJ": (["benin"], "بنين", "africa"),
    "TG": (["togo"], "توغو", "africa"),
    "MW": (["malawi"], "ملاوي", "africa"),
    "NA": (["namibia"], "ناميبيا", "africa"),
    "BW": (["botswana"], "بوتسوانا", "africa"),
    "MG": (["madagascar"], "مدغشقر", "africa"),
    "MU": (["mauritius"], "موريشيوس", "africa"),
    "KM": (["comoros"], "جزر القمر", "africa"),
    # أوروبا
    "GB": (["united kingdom", "uk", "great britain", "britain"], "بريطانيا", "europe"),
    "FR": (["france"], "فرنسا", "europe"),
    "DE": (["germany"], "ألمانيا", "europe"),
    "ES": (["spain"], "إسبانيا", "europe"),
    "IT": (["italy"], "إيطاليا", "europe"),
    "PT": (["portugal"], "البرتغال", "europe"),
    "NL": (["netherlands"], "هولندا", "europe"),
    "BE": (["belgium"], "بلجيكا", "europe"),
    "CH": (["switzerland"], "سويسرا", "europe"),
    "AT": (["austria"], "النمسا", "europe"),
    "IE": (["ireland"], "أيرلندا", "europe"),
    "SE": (["sweden"], "السويد", "europe"),
    "NO": (["norway"], "النرويج", "europe"),
    "DK": (["denmark"], "الدنمارك", "europe"),
    "FI": (["finland"], "فنلندا", "europe"),
    "IS": (["iceland"], "آيسلندا", "europe"),
    "PL": (["poland"], "بولندا", "europe"),
    "CZ": (["czechia", "czech republic"], "التشيك", "europe"),
    "SK": (["slovakia", "slovak republic"], "سلوفاكيا", "europe"),
    "HU": (["hungary"], "المجر", "europe"),
    "RO": (["romania"], "رومانيا", "europe"),
    "BG": (["bulgaria"], "بلغاريا", "europe"),
    "GR": (["greece"], "اليونان", "europe"),
    "RS": (["serbia"], "صربيا", "europe"),
    "HR": (["croatia"], "كرواتيا", "europe"),
    "SI": (["slovenia"], "سلوفينيا", "europe"),
    "BA": (["bosnia and herzegovina", "bosnia-herzegovina", "bosnia"], "البوسنة والهرسك", "europe"),
    "AL": (["albania"], "ألبانيا", "europe"),
    "MK": (["north macedonia", "macedonia"], "مقدونيا الشمالية", "europe"),
    "ME": (["montenegro"], "الجبل الأسود", "europe"),
    "XK": (["kosovo"], "كوسوفو", "europe"),
    "UA": (["ukraine"], "أوكرانيا", "europe"),
    "BY": (["belarus"], "بيلاروسيا", "europe"),
    "MD": (["moldova"], "مولدوفا", "europe"),
    "RU": (["russia", "russian federation"], "روسيا", "europe"),
    "LT": (["lithuania"], "ليتوانيا", "europe"),
    "LV": (["latvia"], "لاتفيا", "europe"),
    "EE": (["estonia"], "إستونيا", "europe"),
    "LU": (["luxembourg"], "لوكسمبورغ", "europe"),
    "MT": (["malta"], "مالطا", "europe"),
    # أمريكا الشمالية
    "US": (["united states", "united states of america", "usa"], "أمريكا", "north_america"),
    "CA": (["canada"], "كندا", "north_america"),
    # أمريكا اللاتينية
    "MX": (["mexico"], "المكسيك", "latin_america"),
    "BR": (["brazil"], "البرازيل", "latin_america"),
    "AR": (["argentina"], "الأرجنتين", "latin_america"),
    "CO": (["colombia"], "كولومبيا", "latin_america"),
    "CL": (["chile"], "تشيلي", "latin_america"),
    "PE": (["peru"], "بيرو", "latin_america"),
    "VE": (["venezuela"], "فنزويلا", "latin_america"),
    "EC": (["ecuador"], "الإكوادور", "latin_america"),
    "BO": (["bolivia"], "بوليفيا", "latin_america"),
    "UY": (["uruguay"], "أوروغواي", "latin_america"),
    "PY": (["paraguay"], "باراغواي", "latin_america"),
    "CU": (["cuba"], "كوبا", "latin_america"),
    "DO": (["dominican republic"], "الدومينيكان", "latin_america"),
    "GT": (["guatemala"], "غواتيمالا", "latin_america"),
    "CR": (["costa rica"], "كوستاريكا", "latin_america"),
    "PA": (["panama"], "بنما", "latin_america"),
    "HN": (["honduras"], "هندوراس", "latin_america"),
    "SV": (["el salvador"], "السلفادور", "latin_america"),
    "NI": (["nicaragua"], "نيكاراغوا", "latin_america"),
    "JM": (["jamaica"], "جامايكا", "latin_america"),
    "TT": (["trinidad and tobago"], "ترينيداد وتوباغو", "latin_america"),
    # أوقيانوسيا
    "AU": (["australia"], "أستراليا", "oceania"),
    "NZ": (["new zealand"], "نيوزيلندا", "oceania"),
    "FJ": (["fiji"], "فيجي", "oceania"),
    "PG": (["papua new guinea"], "بابوا غينيا الجديدة", "oceania"),
}

_BY_NAME = {}
for _iso, (_names, _ar, _region) in _COUNTRIES.items():
    for _n in _names:
        _BY_NAME[_n] = _iso
    _BY_NAME[_ar] = _iso

# نطاقات عامة لا تدل على دولة
_GENERIC_TLDS = {"com", "org", "net", "info", "news", "tv", "co", "io", "me", "ai", "app", "int", "edu", "gov", "biz", "online", "site", "world", "media", "press", "today", "live", "asia", "africa", "eu"}
_TLD_FIX = {"uk": "GB"}


def by_iso(code: str):
    """يعيد (الرمز، الاسم العربي، المنطقة) أو None."""
    code = (code or "").strip().upper()
    if code in _COUNTRIES:
        _, ar, region = _COUNTRIES[code]
        return code, ar, region
    return None


def by_name(name: str):
    key = (name or "").strip().lower()
    iso = _BY_NAME.get(key) or _BY_NAME.get((name or "").strip())
    return by_iso(iso) if iso else None


def by_domain(domain: str):
    """يستنتج الدولة من نهاية النطاق مثل .jp أو .co.uk (لا يعمل مع .com وأمثاله)."""
    parts = (domain or "").lower().strip(".").split(".")
    if len(parts) < 2:
        return None
    tld = parts[-1]
    if tld in _GENERIC_TLDS or len(tld) != 2:
        return None
    return by_iso(_TLD_FIX.get(tld, tld.upper()))


def region_label(region: str) -> str:
    return REGIONS_AR.get(region or "unknown", REGIONS_AR["unknown"])


def flag(code: str) -> str:
    """علم الدولة (إيموجي) من رمزها المكوّن من حرفين، أو نص فارغ."""
    code = (code or "").strip().upper()
    if len(code) != 2 or not code.isalpha() or not code.isascii():
        return ""
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in code)


def flag_for_name(name: str) -> str:
    info = by_name(name)
    return flag(info[0]) if info else ""
