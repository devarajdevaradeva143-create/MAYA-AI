"""Maya AI Language Intelligence tools.

Provides translation, language detection, and pronunciation guidance.

Translation uses the LOCAL engine only (``custom.engine.bridge``) — no cloud
APIs and no network calls beyond the configured localhost engine. Per
AGENTS.md: Language Intelligence module for Tamil/English/Tanglish support.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Protocol


# ── Language normalization ───────────────────────────────────────────────

TAMIL = "tamil"
ENGLISH = "english"
TANGLISH = "tanglish"

#: Accepted aliases for language arguments (ISO codes + full names).
_LANG_ALIASES: Dict[str, str] = {
    "ta": TAMIL,
    "tam": TAMIL,
    "tamil": TAMIL,
    "en": ENGLISH,
    "eng": ENGLISH,
    "english": ENGLISH,
    "tanglish": TANGLISH,
    "romanized": TANGLISH,
}

#: Display names used inside translation prompts.
_LANG_DISPLAY: Dict[str, str] = {
    TAMIL: "Tamil",
    ENGLISH: "English",
    TANGLISH: "Tanglish (Tamil written in Latin script)",
}

#: Prefix for honest failure replies. Callers can check this prefix instead
#: of handling exceptions, and the text always explains why.
UNAVAILABLE_PREFIX = "[translation unavailable]"

#: Common romanised-Tamil (Tanglish) words used by the detection heuristic.
#: Not a dictionary — just enough signal to separate Tanglish from English.
_TANGLISH_HINTS = frozenset(
    {
        "vanakkam", "vanakam", "enna", "epdi", "eppadi", "irukku", "irukkingu",
        "irukkinga", "nalla", "romba", "seri", "sari", "illa", "ille", "thambi",
        "thangachi", "akka", "anna", "machan", "machi", "poda", "podi", "sollu",
        "sollunga", "sonna", "vandhu", "poitu", "poga", "inge", "ange", "yaaru",
        "yaar", "enge", "enga", "aama", "aamaa", "appo", "ippo", "ipdi", "adhu",
        "idhu", "avaru", "ivaru", "avan", "ival", "enakku", "unakku", "unga",
        "ungaluku", "thala", "thalaiva", "da", "di", "pannu", "pannunga",
        "venum", "vendum", "mudiyala", "theriyala", "puriyala", "pesu",
        "pesunga", "sapadu", "saapta", "thoongu", "velai", "veedu", "ooru",
        "pasikuthu", "kovam", "sandhosham",
    }
)


class ChatEngine(Protocol):
    """Minimal engine interface used for translation.

    ``custom.engine.bridge.EngineBridge`` satisfies this protocol; tests use
    small fakes exposing the same ``chat`` method.
    """

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return the model reply for ``messages``."""
        ...


# ── Language detection ─────────────────────────────────────────────────────

def detect_language(text: str) -> Dict[str, str]:
    """Detect if text is Tamil, English, or Tanglish.

    Heuristic (no model, no network):
    - Tamil Unicode letters (U+0B80–U+0BFF) dominate → Tamil
    - Romanised-Tamil marker words dominate → Tanglish
    - Other Latin words dominate → English
    - No letters at all → unknown
    """
    if not text or not text.strip():
        return {"primary": "unknown", "confidence": "0%"}

    # Measure Tamil script against letters only, so punctuation/spaces do not
    # water down the ratio for short Tamil sentences.
    letters = [ch for ch in text if ch.isalpha()]
    tamil_chars = sum(1 for ch in letters if "\u0B80" <= ch <= "\u0BFF")
    tamil_ratio = tamil_chars / max(len(letters), 1)

    latin_tokens = re.findall(r"[a-zA-Z]+", text.lower())
    hint_tokens = sum(1 for token in latin_tokens if token in _TANGLISH_HINTS)
    tanglish_ratio = hint_tokens / len(latin_tokens) if latin_tokens else 0.0

    english_words = len(re.findall(r"\b[a-zA-Z]+\b", text))
    total_words = len(text.split())
    english_ratio = english_words / max(total_words, 1) if total_words else 0.0

    if tamil_ratio >= 0.3:
        return {"primary": TAMIL, "confidence": f"{round(tamil_ratio * 100)}%"}
    if tanglish_ratio >= 0.5:
        return {"primary": TANGLISH, "confidence": "mix of Tamil + English"}
    if english_ratio > 0.5:
        return {"primary": ENGLISH, "confidence": f"{round(english_ratio * 100)}%"}
    if not letters:
        return {"primary": "unknown", "confidence": "0%"}
    return {"primary": TANGLISH, "confidence": "mix of Tamil + English"}


# ── Translation core (LOCAL engine only) ─────────────────────────────────

_PROMPT_TEMPLATE = (
    "You are a precise translation engine. Translate the {source} text below "
    "into {target}.\n"
    "Return ONLY the translation, no notes, no quotes, no transliteration.\n\n"
    "--- BEGIN {delimiter} TEXT ---\n"
    "{text}\n"
    "--- END {delimiter} TEXT ---"
)

_FENCE_OPEN_RE = re.compile(r"^```[^\n]*\n")
_FENCE_CLOSE_RE = re.compile(r"\n?```\s*$")
_LABEL_RE = re.compile(
    r"^\s*(?:\*\*)?translation(?:\s*\([^)]*\))?\s*[:\-\u2013\u2014]\s*(?:\*\*)?\s*",
    re.IGNORECASE,
)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_QUOTE_PAIRS = {'"': '"', "'": "'", "`": "`", "\u201c": "\u201d", "\u2018": "\u2019"}


def _normalize_lang(value: str) -> str:
    """Map an ISO code or language name to its canonical name."""
    key = str(value).strip().lower()
    try:
        return _LANG_ALIASES[key]
    except KeyError:
        supported = ", ".join(sorted(_LANG_ALIASES))
        raise ValueError(
            f"unsupported language {value!r}; use one of: {supported}"
        ) from None


def _resolve_engine(engine: Any | None) -> Any:
    """Return the caller's engine, or lazily import the local bridge.

    The import stays inside the function so passing a fake engine never
    builds the bridge (settings + HTTP client) at all.
    """
    if engine is not None:
        return engine
    from ..engine.bridge import bridge

    return bridge


def _build_prompt(text: str, source: str, target: str) -> str:
    """Build the strict translation prompt sent to the local engine."""
    return _PROMPT_TEMPLATE.format(
        source=_LANG_DISPLAY[source],
        target=_LANG_DISPLAY[target],
        delimiter=source.upper(),
        text=text,
    )


def _strip_wrapping_quotes(text: str) -> str:
    """Remove matching quote/backtick pairs around the whole reply."""
    while len(text) >= 2 and _QUOTE_PAIRS.get(text[0]) == text[-1]:
        text = text[1:-1].strip()
    return text


def _clean_translation(reply: str) -> str:
    """Clean a raw engine reply into plain translated text."""
    text = reply.strip()

    # Model may wrap the answer in a Markdown code fence.
    if text.startswith("```"):
        text = _FENCE_OPEN_RE.sub("", text, count=1)
        text = _FENCE_CLOSE_RE.sub("", text, count=1)
        text = text.strip()

    # Peel decoration layers (label → quotes → bold) until stable.
    for _ in range(3):
        before = text
        text = _LABEL_RE.sub("", text, count=1).strip()
        text = _strip_wrapping_quotes(text)
        if len(text) >= 4 and text.startswith("**") and text.endswith("**"):
            text = text[2:-2].strip()
        if text == before:
            break

    text = _MULTI_BLANK_RE.sub("\n\n", text)
    return text.strip()


def _unavailable(reason: str) -> str:
    """Build an honest, single-line ``[translation unavailable]`` reply."""
    reason = " ".join(str(reason).split()) or "local engine is not available"
    if len(reason) > 200:
        reason = reason[:197] + "..."
    return f"{UNAVAILABLE_PREFIX} {reason}"


def translate(
    text: str,
    target_lang: str,
    source_lang: str | None = None,
    engine: Any | None = None,
) -> str:
    """Translate ``text`` with the LOCAL engine.

    Args:
        text: Text to translate.
        target_lang: ``"ta"``/``"tamil"``, ``"en"``/``"english"`` or
            ``"tanglish"``.
        source_lang: Same accepted values, or ``None`` to auto-detect with
            :func:`detect_language`.
        engine: Optional object with ``chat(messages) -> str``. When omitted,
            the local bridge (``custom.engine.bridge.bridge``) is used lazily.

    Returns:
        The translated text, or a string starting with
        ``"[translation unavailable]"`` when the local engine is unreachable,
        errors, or returns an unusable reply. Failures are returned instead of
        raised so callers always have something safe to show the user.

    Raises:
        ValueError: If a language argument is not supported.

    Empty input returns ``""``. When source and target are the same language,
    the text is returned unchanged and the engine is never called.
    """
    target = _normalize_lang(target_lang)
    if not text or not text.strip():
        return ""

    if source_lang is None:
        detected = detect_language(text)["primary"]
        if detected == "unknown":
            return _unavailable("could not detect the source language")
        source = detected
    else:
        source = _normalize_lang(source_lang)

    if source == target:
        return text

    messages = [{"role": "user", "content": _build_prompt(text, source, target)}]

    try:
        reply = _resolve_engine(engine).chat(messages)
    except Exception as exc:  # engine down, timeout, bad config, ...
        return _unavailable(f"{type(exc).__name__}: {exc}")

    if not isinstance(reply, str):
        return _unavailable("engine returned a non-text reply")

    reply = reply.strip()
    if reply.startswith(UNAVAILABLE_PREFIX):
        return reply
    if reply.startswith("[engine error]"):
        return _unavailable(reply[len("[engine error]"):])

    cleaned = _clean_translation(reply)
    if not cleaned:
        return _unavailable("engine returned an empty translation")
    return cleaned


def translate_tamil_to_english(text: str, engine: Any | None = None) -> str:
    """Translate Tamil text to English using the local engine."""
    return translate(text, ENGLISH, TAMIL, engine=engine)


def translate_english_to_tamil(text: str, engine: Any | None = None) -> str:
    """Translate English text to Tamil using the local engine."""
    return translate(text, TAMIL, ENGLISH, engine=engine)


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

    result = english
    for english_word, tamil_word in mapping.items():
        result = result.replace(english_word, tamil_word)
        result = result.replace(english_word.capitalize(), tamil_word.capitalize())

    return f"[tanglish] Input: '{english}' → Mapped: '{result}' (basic mapping only)"
