import logging
import os
import re

from country_mapper import CountryMapper

TOPIC_KEYWORDS = {
    "politics": ["سياسة", "دبلوماسية", "وزير", "رئيس", "مفاوضات", "تعاون", "أمن", "خارجية", "مبادرة", "government", "minister", "diplomacy"],
    "economy": ["اقتصاد", "استثمار", "سوق", "أسهم", "عملة", "تمويل", "صادرات", "ميزانية", "أرامكو", "pif", "الاستثمار", "investment", "economy", "market"],
    "energy": ["طاقة", "نفط", "غاز", "أرامكو", "الطاقة", "oil", "gas", "energy"],
    "tourism": ["سياحة", "السياحة", "tourism", "travel", "مقصد", "زيارة"],
    "sports": ["كرة قدم", "رياضة", "مشجع", "دوري", "مباراة", "league", "sport", "football"],
    "technology": ["تقنية", "ذكاء", "AI", "تكنولوجيا", "software", "tech", "ابتكار", "digital"],
    "culture": ["ثقافة", "فن", "سينما", "فنون", "مهرجان", "ثقافي", "art"],
    "religion": ["حج", "عمرة", "إسلام", "مكة", "جدة", "مقدسات", "hajj", "umrah"],
    "real_estate": ["عقار", "مشاريع", "تطوير", "عقارات", "مدينة", "project", "real estate"],
    "regional": ["الخليج", "الدول", "المنطقة", "تعاون", "شراكات", "إقليمي", "regional"],
    "security": ["أمن", "مخابرات", "دفاع", "حظر", "تدابير", "security", "defense"],
}

SAUDI_TERMS = [
    "riyadh", "riyad", "jeddah", "makkah", "mecca", "medina", "madinah",
    "neom", "aramco", "saudi arabia", "saudi", "vision 2030",
    "mohammed bin salman", "mohammad bin salman", "prince mohammed bin salman",
    "الرياض", "جدة", "مكة", "المدينة المنورة", "نيوم", "أرامكو",
    "رؤية 2030", "بن سلمان", "محمد بن سلمان", "صندوق الاستثمارات العامة",
    "pif", "red sea project", "مشروع البحر الأحمر",
]

KNOWN_ENTITIES = {
    "PERSON": ["محمد بن سلمان", "بن سلمان", "Mohammed bin Salman", "Mohammad bin Salman", "MBS"],
    "LOCATION": ["الرياض", "جدة", "مكة", "المدينة المنورة", "نيوم", "العلا", "Riyadh", "Jeddah", "Mecca", "Makkah", "NEOM", "AlUla"],
    "ORGANIZATION": ["أرامكو", "صندوق الاستثمارات العامة", "وزارة الخارجية", "Saudi Aramco", "Aramco", "PIF", "Ministry of Foreign Affairs"],
}


def classify_topic_details(text: str, keywords=None) -> tuple[str, float]:
    normalized = (text or "").casefold()
    scores = {
        topic: sum(
            1 for keyword in terms
            if re.search(r"(?<!\w)" + re.escape(keyword.casefold()) + r"(?!\w)", normalized)
        )
        for topic, terms in (keywords or TOPIC_KEYWORDS).items()
    }
    topic, best = max(scores.items(), key=lambda item: item[1])
    if not best:
        return "general", 0.5
    total = sum(scores.values())
    confidence = min(0.97, 0.5 + 0.12 * best) * (0.75 + 0.25 * best / total)
    return topic, round(confidence, 3)


def classify_topic(text: str) -> str:
    return classify_topic_details(text)[0]


class NLPProcessor:
    def __init__(self, country_mapper=None, spacy_model=None, transformer_model=None):
        self.country_mapper = country_mapper or CountryMapper()
        self.spacy_model = os.getenv("NEWS_SPACY_MODEL", "en_core_web_sm") if spacy_model is None else spacy_model
        self.transformer_model = os.getenv("NEWS_ZERO_SHOT_MODEL") if transformer_model is None else transformer_model
        self._nlp = self._load_spacy()
        self._classifier = None
        self._transformer_attempted = False

    def _load_spacy(self):
        if not self.spacy_model:
            return None
        try:
            import spacy
            return spacy.load(self.spacy_model)
        except (ImportError, OSError) as exc:
            logging.debug("spaCy model unavailable (%s): %s", self.spacy_model, exc)
            return None

    def _load_transformer(self):
        if self._transformer_attempted or not self.transformer_model:
            return self._classifier
        self._transformer_attempted = True
        try:
            from transformers import pipeline
            self._classifier = pipeline(
                "zero-shot-classification",
                model=self.transformer_model,
                trust_remote_code=False,
            )
        except Exception as exc:
            logging.warning("Hugging Face classifier unavailable: %s", exc)
        return self._classifier

    def _zero_shot(self, text, labels):
        classifier = self._load_transformer()
        if not classifier or not text.strip():
            return None
        try:
            result = classifier(text[:2000], candidate_labels=labels, multi_label=False)
            return result["labels"][0], float(result["scores"][0])
        except Exception as exc:
            logging.warning("Hugging Face classification failed: %s", exc)
            return None

    def _topic(self, text):
        result = self._zero_shot(text, list(TOPIC_KEYWORDS))
        return result if result else classify_topic_details(text)

    def _languages(self, text, source_language):
        detected = []
        try:
            from langdetect import detect_langs

            segments = [
                part.strip()
                for part in re.split(r"(?<=[.!?؟؛])\s+", text)
                if len(part.strip()) >= 20
            ]
            if len(text.strip()) >= 20:
                segments.insert(0, text.strip())
            for segment in segments:
                for candidate in detect_langs(segment):
                    if candidate.prob >= 0.2 and candidate.lang not in detected:
                        detected.append(candidate.lang)
        except Exception:
            pass

        if not detected and text:
            if re.search(r"[\u0600-\u06ff]", text):
                detected.append("ar")
            elif re.search(r"[A-Za-z]", text):
                detected.append(source_language or "en")
        if source_language and source_language not in detected:
            detected.append(source_language)

        primary = source_language or (detected[0] if detected else "en")
        try:
            from langdetect import detect_langs

            candidates = detect_langs(text) if len(text.strip()) >= 25 else []
            if candidates and candidates[0].prob >= 0.85:
                primary = candidates[0].lang
        except Exception:
            pass
        return primary, detected or [primary]

    def _entities(self, text):
        entities = {}
        if self._nlp and text:
            try:
                for entity in self._nlp(text[:10000]).ents:
                    label = {
                        "PERSON": "PERSON",
                        "ORG": "ORGANIZATION",
                        "GPE": "LOCATION",
                        "LOC": "LOCATION",
                        "FAC": "LOCATION",
                    }.get(entity.label_)
                    if label and entity.text.strip():
                        entities[(entity.text.strip(), label)] = {
                            "text": entity.text.strip(),
                            "label": label,
                        }
            except Exception as exc:
                logging.debug("spaCy entity extraction failed: %s", exc)

        for label, names in KNOWN_ENTITIES.items():
            for name in names:
                if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text or "", re.IGNORECASE):
                    entities[(name, label)] = {"text": name, "label": label}
        return list(entities.values())

    def analyze(self, text, source_language="en", extra_saudi_terms=None):
        text = (text or "").strip()
        topic, topic_confidence = self._topic(text)
        countries = self.country_mapper.extract(text)
        entities = self._entities(text)
        language, languages = self._languages(text, source_language)

        terms = SAUDI_TERMS + list(extra_saudi_terms or [])
        mentions_saudi = any(
            re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.IGNORECASE)
            for term in terms
            if term
        )
        saudi_country = any(country["code"] == "SA" for country in countries)
        relevance_result = self._zero_shot(text, ["about Saudi Arabia", "not about Saudi Arabia"])
        if relevance_result:
            label, confidence = relevance_result
            saudi_relevance = confidence if label == "about Saudi Arabia" else 1 - confidence
        elif saudi_country:
            saudi_relevance = 0.99
        elif mentions_saudi:
            saudi_relevance = 0.82
        else:
            saudi_relevance = 0.05

        return {
            "topic": topic,
            "topic_confidence": topic_confidence,
            "countries": countries,
            "entities": entities,
            "language": language,
            "languages": languages,
            "confidence_score": round(saudi_relevance, 3),
        }
