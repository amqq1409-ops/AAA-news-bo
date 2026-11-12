import re
from typing import Any


POSITIVE_WORDS = {
    "success", "successful", "growth", "gain", "improve", "positive", "agreement",
    "opportunity", "support", "record", "prosperity", "نجاح", "ناجح", "نمو",
    "ارتفاع", "إيجابي", "ايجابي", "اتفاق", "فرصة", "دعم", "ازدهار",
}
NEGATIVE_WORDS = {
    "crisis", "decline", "loss", "fall", "attack", "war", "risk", "concern",
    "negative", "failure", "threat", "أزمة", "تراجع", "انخفاض", "خسارة",
    "هجوم", "حرب", "مخاطر", "قلق", "سلبي", "فشل", "تهديد",
}


class SentimentAnalyzer:
    """Lightweight bilingual sentiment estimates for stored article titles."""

    def analyze(self, text: str | None) -> dict[str, Any]:
        words = set(re.findall(r"[\w\u0600-\u06ff]+", (text or "").casefold()))
        positive = len(words & POSITIVE_WORDS)
        negative = len(words & NEGATIVE_WORDS)
        if positive == negative:
            label = "neutral"
            confidence = 0.5 if positive else 0.55
        else:
            label = "positive" if positive > negative else "negative"
            confidence = min(0.95, 0.6 + 0.1 * abs(positive - negative))
        return {"label": label, "confidence": round(confidence, 2)}
