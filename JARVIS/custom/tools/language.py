"""Maya AI Language Intelligence tools.

Provides translation, language detection, and pronunciation guidance.
All operations are LOCAL only — no cloud APIs.

Per AGENTS.md: Language Intelligence module for Tamil/English/Tanglish support.
"""

import re
from typing import Any, Dict, Optional


# ── Language detection ─────────────────────────────────────────────────────

def detect_language(text: str) -> Dict[str, str]:
    """Detect if text is Tamil, English, or Tanglish.

    Heuristic:
    - If Tamil characters (U+0B80–U+0BFF) are present → Tamil
    - If English words dominate → English
    - Mix → Tanglish
    """
    if not text or not text.strip():
        return {"primary": "unknown", "confidence": "0%"}

    # Check for Tamil characters
    tamil_chars = re.findall(r"[\u0B80-\u0BFF]", text)
    tamil_ratio = len(tamil_chars) / max(len(text), 1)

    # Check for English words (simple: ASCII letters / common words)
    english_words = len(re.findall(r"\b[a-zA-Z]+\b", text))
    total_words = len(text.split())
    english_ratio = english_words / max(total_words, 1) if total_words else 0

    # Heuristic thresholds
    if tamil_ratio > 0.3:
        return {"primary": "tamil", "confidence": f"{round(tamil_ratio * 100)}%"}
    elif english_ratio > 0.5:
        return {"primary": "english", "confidence": f"{round(english_ratio * 100)}%"}
    else:
        return {"primary": "tanglish", "confidence": "mix of Tamil + English"}


# ── Tamil ↔ English translation (placeholders) ────────────────────────────

def translate_tamil_to_english(text: str) -> str:
    """Translate Tamil text to English (placeholder).

    Full translation needs a model. This just notes the translation.
    """
    if not text:
        return ""
    # Note: actual translation would use a model or API
    return f"[translation] Tamil: '{text}' → English: (model needed for full translation)"


def translate_english_to_tamil(text: str) -> str:
    """Translate English text to Tamil (placeholder).

    Full translation needs a model. This just notes the translation.
    """
    if not text:
        return ""
    # Note: actual translation would use a model or API
    return f"[translation] English: '{text}' → Tamil: (model needed for full translation)"


# ── Pronunciation guidance ───────────────────────────────────────────────

def pronunciation_guide(word: str) -> Dict[str, Any]:
    """Return pronunciation hints for an English word.

    Simple approach: provide syllable breakdown and a simple phonetic hint.
    """
    if not word:
        return {"word": "", "syllables": [], "phonetic": ""}

    # Simple syllable split on vowel groups
    # This is very basic — real pronunciation needs a dictionary
    vowels = "aeiouAEIOU"
    syllables = []
    current = ""
    for ch in word:
        current += ch
        if ch in vowels:
            # End of a potential syllable
            syllables.append(current)
            current = ""
    if current:
        syllables.append(current)

    # Simple phonetic (just the word itself as fallback)
    return {
        "word": word,
        "syllables": syllables,
        "phonetic": f"/{word}/",  # Very basic placeholder
    }


# ── Tanglish converter (simple) ──────────────────────────────────────────

def tanglish_to_english(tanglish: str) -> str:
    """Simple Tanglish → English conversion (placeholder).

    Tanglish = English words written with Tamil keyboard layout sounds.
    This is a very basic mapping.
    """
    # Basic common Tanglish → English mappings
    mapping = {
        "vanakkam": "hello",
        "enna": "what",
        "kanna": "eyes",
        "appa": "father",
        "akka": "elder sister",
        "anna": "elder brother",
        "tanglish": "tanglish",
        "maya": "maya",
    }

    tl = tanglish.lower()
    result = tanglish
    for tamil_word, english_word in mapping.items():
        result = result.replace(tamil_word, english_word)
        result = result.replace(tamil_word.capitalize(), english_word.capitalize())

    return f"[tanglish] Input: '{tanglish}' → Mapped: '{result}' (basic mapping only)"


def english_to_tanglish(english: str) -> str:
    """Simple English → Tanglish conversion (placeholder).

    Maps common English words to their Tamil-sounding versions.
    """
    mapping = {
        "hello": "vanakkam",
        "what": "enna",
        "eyes": "kanna",
        "father": "appa",
        "elder sister": "akka",
        "elder brother": "anna",
        "maya": "maya",
    }

    el = english.lower()
    result = english
    for english_word, tamil_word in mapping.items():
        result = result.replace(english_word, tamil_word)
        result = result.replace(english_word.capitalize(), tamil_word.capitalize())

    return f"[tanglish] Input: '{english}' → Mapped: '{result}' (basic mapping only)"