import re
from collections import Counter
from typing import Any


class NewsSummarizer:
    """Create a concise, extractive summary from the text available for an article."""

    def summarize(self, text: str | None, max_keywords: int = 5) -> dict[str, Any]:
        text = re.sub(r"\s+", " ", (text or "")).strip()
        sentences = [part.strip() for part in re.split(r"(?<=[.!?؟])\s+", text) if part.strip()]
        keywords = Counter(
            token.casefold()
            for token in re.findall(r"[\w\u0600-\u06ff]{3,}", text)
        )
        ranked = sorted(keywords, key=lambda word: (-keywords[word], word))[:max(0, max_keywords)]
        return {
            "summary": " ".join(sentences[:2]),
            "key_points": sentences[:2],
            "keywords": ranked,
        }
