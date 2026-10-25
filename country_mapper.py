import re

try:
    import pycountry
except ImportError:
    pycountry = None


ARABIC_NAMES = {
    "AF": "أفغانستان", "AL": "ألبانيا", "DZ": "الجزائر", "AR": "الأرجنتين",
    "AU": "أستراليا", "AT": "النمسا", "BH": "البحرين", "BD": "بنغلاديش",
    "BE": "بلجيكا", "BR": "البرازيل", "CA": "كندا", "CN": "الصين",
    "CO": "كولومبيا", "CU": "كوبا", "CY": "قبرص", "CZ": "التشيك",
    "DK": "الدنمارك", "EG": "مصر", "ET": "إثيوبيا", "FI": "فنلندا",
    "FR": "فرنسا", "DE": "ألمانيا", "GH": "غانا", "GR": "اليونان",
    "IN": "الهند", "ID": "إندونيسيا", "IR": "إيران", "IQ": "العراق",
    "IE": "أيرلندا", "IL": "إسرائيل", "IT": "إيطاليا", "JP": "اليابان",
    "JO": "الأردن", "KE": "كينيا", "KW": "الكويت", "LB": "لبنان",
    "LY": "ليبيا", "MY": "ماليزيا", "MX": "المكسيك", "MA": "المغرب",
    "NP": "نيبال", "NL": "هولندا", "NZ": "نيوزيلندا", "NG": "نيجيريا",
    "KP": "كوريا الشمالية", "NO": "النرويج", "OM": "عُمان", "PK": "باكستان",
    "PS": "فلسطين", "PH": "الفلبين", "PL": "بولندا", "PT": "البرتغال",
    "QA": "قطر", "RO": "رومانيا", "RU": "روسيا", "SA": "السعودية",
    "SN": "السنغال", "SG": "سنغافورة", "SO": "الصومال", "ZA": "جنوب أفريقيا",
    "KR": "كوريا الجنوبية", "ES": "إسبانيا", "LK": "سريلانكا", "SD": "السودان",
    "SE": "السويد", "CH": "سويسرا", "SY": "سوريا", "TW": "تايوان",
    "TH": "تايلاند", "TN": "تونس", "TR": "تركيا", "UA": "أوكرانيا",
    "AE": "الإمارات العربية المتحدة", "GB": "المملكة المتحدة",
    "US": "الولايات المتحدة", "VE": "فنزويلا", "VN": "فيتنام", "YE": "اليمن",
}

ALIASES = {
    "SA": [
        "KSA", "Saudi", "Saudi Arabia", "Kingdom of Saudi Arabia",
        "Arabie saoudite", "Arabia Saudita", "Saudi-Arabien",
        "السعودية", "السعوديه", "السعودي", "المملكة العربية السعودية",
    ],
    "US": ["USA", "U.S.", "United States", "United States of America", "États-Unis", "Estados Unidos", "Vereinigte Staaten", "أمريكا", "الولايات المتحدة"],
    "GB": ["UK", "U.K.", "Britain", "Great Britain", "United Kingdom", "Royaume-Uni", "Reino Unido", "بريطانيا", "المملكة المتحدة"],
    "AE": ["UAE", "U.A.E.", "United Arab Emirates", "Émirats arabes unis", "الإمارات", "الامارات", "الإمارات العربية المتحدة"],
    "KR": ["South Korea", "Republic of Korea", "Corée du Sud", "Corea del Sur", "كوريا الجنوبية"],
    "KP": ["North Korea", "كوريا الشمالية"],
    "RU": ["Russia", "Russian Federation", "Russie", "Rusia", "روسيا"],
    "IR": ["Iran", "Islamic Republic of Iran", "إيران"],
    "TR": ["Turkey", "Türkiye", "Turquie", "Turquía", "تركيا"],
    "CZ": ["Czech Republic", "Czechia", "التشيك"],
    "NL": ["The Netherlands", "Netherlands", "Pays-Bas", "Países Bajos", "هولندا"],
    "PS": ["Palestine", "State of Palestine", "فلسطين"],
    "EG": ["Egypt", "Égypte", "Egipto", "مصر"],
    "FR": ["France", "فرنسا"],
    "DE": ["Germany", "Allemagne", "Alemania", "Deutschland", "ألمانيا"],
    "CN": ["China", "People's Republic of China", "Chine", "الصين"],
    "JP": ["Japan", "Japon", "Japón", "اليابان"],
    "IN": ["India", "Inde", "الهند"],
    "PK": ["Pakistan", "باكستان"],
    "QA": ["Qatar", "قطر"],
    "KW": ["Kuwait", "الكويت"],
    "BH": ["Bahrain", "البحرين"],
    "OM": ["Oman", "عمان", "سلطنة عمان"],
    "IQ": ["Iraq", "العراق"],
    "JO": ["Jordan", "الأردن"],
    "LB": ["Lebanon", "لبنان"],
    "SY": ["Syria", "سوريا"],
    "YE": ["Yemen", "اليمن"],
    "MA": ["Morocco", "المغرب"],
    "TN": ["Tunisia", "تونس"],
    "DZ": ["Algeria", "الجزائر"],
    "BR": ["Brazil", "Brésil", "Brasil", "البرازيل"],
    "ES": ["Spain", "Espagne", "España", "إسبانيا"],
    "IT": ["Italy", "Italie", "Italia", "إيطاليا"],
    "UA": ["Ukraine", "أوكرانيا"],
    "AU": ["Australia", "أستراليا"],
    "CA": ["Canada", "كندا"],
    "CH": ["Switzerland", "Suisse", "Suiza", "سويسرا"],
    "ZA": ["South Africa", "جنوب أفريقيا"],
}


def _flag(alpha_2: str) -> str:
    if not re.fullmatch(r"[A-Z]{2}", alpha_2 or ""):
        return ""
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in alpha_2)


class CountryMapper:
    def __init__(self):
        self.countries = {}
        aliases_by_code = {}

        if pycountry is not None:
            for item in pycountry.countries:
                code = item.alpha_2
                country = {
                    "code": code,
                    "name": item.name,
                    "name_ar": ARABIC_NAMES.get(code, ""),
                    "flag": _flag(code),
                }
                self.countries[code] = country
                aliases_by_code[code] = {
                    item.name,
                    getattr(item, "official_name", ""),
                    getattr(item, "common_name", ""),
                }

        for code, name_ar in ARABIC_NAMES.items():
            if code not in self.countries:
                aliases = ALIASES.get(code, [])
                self.countries[code] = {
                    "code": code,
                    "name": aliases[1] if len(aliases) > 1 else name_ar,
                    "name_ar": name_ar,
                    "flag": _flag(code),
                }
            aliases_by_code.setdefault(code, set()).add(name_ar)

        for code, aliases in ALIASES.items():
            if code not in self.countries:
                name = aliases[1] if len(aliases) > 1 else aliases[0]
                self.countries[code] = {
                    "code": code,
                    "name": name,
                    "name_ar": ARABIC_NAMES.get(code, ""),
                    "flag": _flag(code),
                }
            aliases_by_code.setdefault(code, set()).update(aliases)
            if ARABIC_NAMES.get(code):
                aliases_by_code[code].add(ARABIC_NAMES[code])

        self._patterns = []
        for code, aliases in aliases_by_code.items():
            for alias in sorted(aliases, key=len, reverse=True):
                if not alias:
                    continue
                pattern = re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", re.IGNORECASE | re.UNICODE)
                self._patterns.append((pattern, code))
        self._patterns.sort(key=lambda entry: len(entry[0].pattern), reverse=True)

    def extract(self, text: str) -> list[dict]:
        found = {}
        for pattern, code in self._patterns:
            match = pattern.search(text or "")
            if match and code not in found:
                found[code] = (match.start(), self.countries[code])
        return [country for _, country in sorted(found.values(), key=lambda item: item[0])]

    def get(self, code: str) -> dict | None:
        return self.countries.get((code or "").upper())
