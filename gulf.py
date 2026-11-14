"""أخبار دول الخليج (الإمارات، قطر، البحرين، الكويت، عُمان): كلمات المطابقة وصيغ البحث بكل لغة.

صيغة الكلمات مثل config.yaml:  "=كلمة" كلمة كاملة فقط، وغير ذلك جذر يُقبل ما بعده.
"""
from __future__ import annotations

ORDER = ["AE", "QA", "KW", "BH", "OM"]
NAMES_AR = {"AE": "الإمارات", "QA": "قطر", "KW": "الكويت", "BH": "البحرين", "OM": "عُمان"}

TERMS = {
    "AE": [
        "=uae", "u.a.e", "arab emirates", "emirati", "emiratos", "emirados", "émirats", "emiraten", "emiraty", "emiráty",
        "arabische emirate", "arabiemiraat", "arabemirat", "dubai", "dubaï", "dubái", "dubaj", "abu dhabi",
        "abou dhabi", "abu dabi", "abú dabi", "sharjah",
        "إمارات", "امارات", "=دبي", "أبوظبي", "أبو ظبي", "ابوظبي", "ابو ظبي", "الشارقة", "دبئی",
        "=оаэ", "=оае", "=уае", "эмират", "емірат", "емират", "дубай", "дубаи", "абу-даби",
        "阿联酋", "阿聯", "迪拜", "杜拜", "阿布扎比", "アラブ首長国", "ドバイ", "アブダビ", "아랍에미리트", "두바이", "아부다비",
        "=bae", "birleşik arap emirlikleri", "यूएई", "दुबई", "अमीरात", "איחוד האמירויות", "דובאי", "אבו דאבי",
        "ยูเออี", "ดูไบ", "เอมิเรตส์", "εμιράτ", "ντουμπάι", "=ηαε", "আমিরাত", "দুবাই", "துபாய்",
    ],
    "QA": [
        "qatar", "=catar", "=catarí", "=catari", "=katar", "=katars", "katarsk", "doha",
        "=قطر", "قطري", "الدوحة", "=катар", "=катара", "=катаре", "=катару", "катарск",
        "卡塔尔", "卡塔爾", "卡達", "多哈", "カタール", "ドーハ", "카타르", "קטאר", "דוחא", "क़तर", "กาตาร์", "=κατάρ", "கத்தார்",
    ],
    "KW": [
        "kuwait", "koweit", "koweït", "kuveyt", "kuwejt", "kuvajt", "koeweit", "kuweit",
        "كويت", "کویت", "кувейт", "кувајт", "科威特", "クウェート", "쿠웨이트", "כווית", "कुवैत", "คูเวต", "κουβέιτ",
        "কুয়েত", "குவைத்",
    ],
    "BH": [
        "bahrain", "bahrein", "bahreïn", "bahreyn", "bahrajn", "baréin", "manama",
        "بحرين", "بحرین", "المنامة", "бахрейн", "бахреин", "巴林", "バーレーン", "바레인", "בחריין", "बहरीन", "บาห์เรน",
        "μπαχρέιν", "বাহরাইন", "பஹ்ரைன்",
    ],
    "OM": [
        "=oman", "omani", "=omán", "=omã", "=umman", "sultanate of oman",
        "سلطنة عمان", "سلطنة عُمان", "عماني", "=оман", "=омана", "=омане", "оманск",
        "阿曼", "オマーン", "עומאן", "ओमान", "โอมาน", "=ομάν", "ওমান", "ஓமன்",
    ],
}
# كلمات لها معنى آخر في بعض اللغات: تُستثنى في تلك اللغات
EXCLUDE_LANGS = {"=oman": {"fi"}, "omani": {"fi"}, "=katar": {"pl"}, "=قطر": {"fa"}}
# كلمات تخص لغة بعينها فقط
ONLY_LANGS = {"=bae": {"tr"}, "=umman": {"tr"}}

_EN = '"United Arab Emirates" OR UAE OR Dubai OR "Abu Dhabi" OR Qatar OR Bahrain OR Kuwait OR Oman'
# صيغة البحث في أخبار Google لكل لغة (المفتاح: رمز الواجهة hl أو رمز اللغة)
QUERIES = {
    "en": _EN,
    "ar": 'الإمارات OR قطر OR البحرين OR الكويت OR "سلطنة عمان"',
    "fr": '"Émirats arabes unis" OR Dubaï OR Qatar OR Bahreïn OR Koweït OR Oman',
    "de": '"Vereinigte Arabische Emirate" OR Dubai OR Katar OR Bahrain OR Kuwait OR Oman',
    "es": '"Emiratos Árabes Unidos" OR Dubái OR Catar OR Qatar OR Baréin OR Kuwait OR Omán',
    "ru": 'ОАЭ OR Дубай OR Катар OR Бахрейн OR Кувейт OR Оман',
    "zh-CN": '阿联酋 OR 迪拜 OR 卡塔尔 OR 巴林 OR 科威特 OR 阿曼',
    "zh-TW": '阿聯 OR 杜拜 OR 卡達 OR 巴林 OR 科威特 OR 阿曼',
    "zh-HK": '阿聯酋 OR 迪拜 OR 卡塔爾 OR 巴林 OR 科威特 OR 阿曼',
    "ja": 'UAE OR ドバイ OR カタール OR バーレーン OR クウェート OR オマーン',
    "ko": '아랍에미리트 OR 두바이 OR 카타르 OR 바레인 OR 쿠웨이트',
    "tr": 'BAE OR Dubai OR Katar OR Bahreyn OR Kuveyt OR Umman',
    "pt": '"Emirados Árabes Unidos" OR Dubai OR Catar OR Qatar OR Bahrein OR Kuwait OR Omã',
    "it": '"Emirati Arabi Uniti" OR Dubai OR Qatar OR Bahrein OR Kuwait OR Oman',
    "hi": 'यूएई OR दुबई OR क़तर OR बहरीन OR कुवैत OR ओमान',
    "id": '"Uni Emirat Arab" OR Dubai OR Qatar OR Bahrain OR Kuwait OR Oman',
    "ms": '"Emiriah Arab Bersatu" OR UAE OR Dubai OR Qatar OR Bahrain OR Kuwait OR Oman',
    "sw": 'UAE OR Dubai OR Qatar OR Bahrain OR Kuwait OR Oman',
    "th": 'ยูเออี OR ดูไบ OR กาตาร์ OR บาห์เรน OR คูเวต OR โอมาน',
    "vi": 'UAE OR Dubai OR Qatar OR Bahrain OR Kuwait OR Oman',
    "bn": 'আমিরাত OR দুবাই OR বাহরাইন OR কুয়েত OR ওমান',
    "ur": 'امارات OR دبئی OR قطر OR بحرین OR کویت',
    "ta": 'துபாய் OR கத்தார் OR குவைத் OR பஹ்ரைன் OR ஓமன்',
    "pl": '"Zjednoczone Emiraty Arabskie" OR Dubaj OR Doha OR Bahrajn OR Kuwejt OR Oman',
    "nl": '"Verenigde Arabische Emiraten" OR Dubai OR Qatar OR Bahrein OR Koeweit OR Oman',
    "uk": 'ОАЕ OR Дубай OR Катар OR Бахрейн OR Кувейт OR Оман',
    "el": 'ΗΑΕ OR Ντουμπάι OR Κατάρ OR Μπαχρέιν OR Κουβέιτ OR Ομάν',
    "sv": 'Arabemiraten OR Dubai OR Qatar OR Bahrain OR Kuwait OR Oman',
    "cs": '"Spojené arabské emiráty" OR Dubaj OR Katar OR Bahrajn OR Kuvajt OR Omán',
    "ro": '"Emiratele Arabe Unite" OR Dubai OR Qatar OR Bahrain OR Kuweit OR Oman',
    "hu": '"Egyesült Arab Emírségek" OR Dubaj OR Katar OR Bahrein OR Kuvait OR Omán',
    "bg": 'ОАЕ OR Дубай OR Катар OR Бахрейн OR Кувейт OR Оман',
    "sr": 'УАЕ OR Дубаи OR Катар OR Бахреин OR Кувајт OR Оман',
    "no": '"De forente arabiske emirater" OR Dubai OR Qatar OR Bahrain OR Kuwait OR Oman',
    "da": '"Forenede Arabiske Emirater" OR Dubai OR Qatar OR Bahrain OR Kuwait OR Oman',
    "fi": 'Arabiemiraatit OR Dubai OR Qatar OR Bahrain OR Kuwait',
    "he": 'איחוד האמירויות OR דובאי OR קטאר OR בחריין OR כווית OR עומאן',
}
# استعلامات GDELT: طلب واحد لكل دولة بكل اللغات (خفيف على الخدمة)
GDELT_QUERIES = {
    "AE": '("United Arab Emirates" OR UAE OR Dubai OR "Abu Dhabi")',
    "QA": '(Qatar OR Doha)',
    "KW": 'Kuwait',
    "BH": '(Bahrain OR Manama)',
    "OM": '(Oman OR Muscat)',
}


def query_for(edition: dict):
    """صيغة البحث الخليجية المناسبة لنسخة أخبار Google، أو None إن لم تتوفر لغتها."""
    return QUERIES.get(edition.get("hl", "")) or QUERIES.get(edition.get("lang", ""))


class Matcher:
    def __init__(self, compile_terms):
        self.rules = []
        for iso in ORDER:
            for term in TERMS[iso]:
                key = term.lower()
                pattern = compile_terms([term])[0]
                self.rules.append((iso, pattern, ONLY_LANGS.get(key), EXCLUDE_LANGS.get(key, ())))
        self.patterns = [rule[1] for rule in self.rules]

    def subjects(self, title: str, lang: str) -> list:
        """رموز الدول الخليجية المذكورة في العنوان، بترتيب ثابت."""
        text = title.lower()
        found = []
        for iso, pattern, only, exclude in self.rules:
            if iso in found or lang in exclude or (only and lang not in only):
                continue
            if pattern.search(text):
                found.append(iso)
        return found
