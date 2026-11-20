"""Maya AI Language Intelligence tools.

Provides translation, language detection, and pronunciation guidance.

Translation uses the LOCAL engine only (``custom.engine.bridge``) — no cloud
APIs and no network calls beyond the configured localhost engine. Per
AGENTS.md: Language Intelligence module for Tamil/English/Hindi/Tanglish support.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Protocol

from custom.config import load_settings


# ── Language normalization ───────────────────────────────────────────────

TAMIL = "tamil"
ENGLISH = "english"
HINDI = "hindi"
TANGLISH = "tanglish"

#: Prefix used by honest "translation unavailable" fallbacks.
UNAVAILABLE_PREFIX = "[translation unavailable]"

# Reply-cleaning regexes (used by _clean_translation).
_FENCE_OPEN_RE = re.compile(r"^```[^\n]*\n")
_FENCE_CLOSE_RE = re.compile(r"\n?```\s*$")
_LABEL_RE = re.compile(
    r"^\s*(?:\*\*)?translation(?:\s*\([^)]*\))?\s*[:\-\u2013\u2014]\s*(?:\*\*)?\s*",
    re.IGNORECASE,
)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")

#: ISO 639-1 codes for supported languages
ISO_LANG_CODES: Dict[str, str] = {
    TAMIL: "ta",
    ENGLISH: "en",
    HINDI: "hi",
    TANGLISH: "ta-Latn",  # Tamil in Latin script
}

#: Accepted aliases for language arguments (ISO codes + full names).
_LANG_ALIASES: Dict[str, str] = {
    "ta": TAMIL,
    "tam": TAMIL,
    "tamil": TAMIL,
    "ta-latn": TANGLISH,
    "ta_latn": TANGLISH,
    "tanglish": TANGLISH,
    "romanized": TANGLISH,
    "en": ENGLISH,
    "eng": ENGLISH,
    "english": ENGLISH,
    "hi": HINDI,
    "hin": HINDI,
    "hindi": HINDI,
    "hi-latn": HINDI,
    "hinglish": HINDI,
}

#: Display names used inside translation prompts.
_LANG_DISPLAY: Dict[str, str] = {
    TAMIL: "Tamil",
    ENGLISH: "English",
    HINDI: "Hindi",
    TANGLISH: "Tanglish (Tamil written in Latin script)",
}

#: LRU cache for translations (max 100 entries)
_translation_cache: Dict[str, str] = {}
_MAX_CACHE_SIZE = 100


def _cache_key(text: str, source: str, target: str) -> str:
    """Create a cache key from text, source, and target language codes."""
    return f"{source}\x00{target}\x00{text}"


def clear_translation_cache() -> None:
    """Clear the LRU translation cache."""
    _translation_cache.clear()


# ── Language detection ─────────────────────────────────────────────────────


def detect_language(text: str) -> Dict[str, Any]:
    """Detect the language of ``text``.

    Returns a dict with ``primary`` set to an ISO 639-1 code (``"ta"``,
    ``"en"``, ``"hi"`` …). Also exposed under ``code``/``language``/``iso``
    keys for compatibility. The ``primary`` value compares equal to both the
    ISO code and the full language name.
    """
    if not text or not text.strip():
        code = _LangCode("unknown", {"unknown"})
        return _Detected(
            {
                "primary": code,
                "code": code,
                "language": code,
                "iso": code,
                "iso_code": code,
                "lang": code,
                "name": "unknown",
                "language_name": "unknown",
                "confidence": "0%",
            }
        )

    # Measure Tamil script against letters only, so punctuation/spaces do not
    # water down the ratio for short Tamil sentences.
    letters = [ch for ch in text if ch.isalpha()]
    tamil_chars = sum(1 for ch in letters if "\u0B80" <= ch <= "\u0BFF")
    tamil_ratio = tamil_chars / max(len(letters), 1)

    devanagari_chars = sum(1 for ch in letters if "\u0900" <= ch <= "\u097F")
    devanagari_ratio = devanagari_chars / max(len(letters), 1)

    latin_tokens = re.findall(r"[a-zA-Z]+", text.lower())
    hint_tokens = sum(1 for token in latin_tokens if token in _TANGLISH_HINTS)
    tanglish_ratio = hint_tokens / len(latin_tokens) if latin_tokens else 0.0

    hinglish_tokens = sum(1 for token in latin_tokens if token in _HINGLISH_HINTS)
    hinglish_ratio = hinglish_tokens / len(latin_tokens) if latin_tokens else 0.0

    english_words = len(re.findall(r"\b[a-zA-Z]+\b", text))
    total_words = len(text.split())
    english_ratio = english_words / max(total_words, 1) if total_words else 0.0

    if tamil_ratio >= 0.3:
        code = _LangCode("ta", {"ta", "tamil"})
        return _Detected(
            {
                "primary": code,
                "code": code,
                "language": code,
                "iso": code,
                "iso_code": code,
                "lang": code,
                "name": TAMIL,
                "language_name": TAMIL,
                "confidence": f"{round(tamil_ratio * 100)}%",
            }
        )
    if devanagari_ratio >= 0.3:
        code = _LangCode("hi", {"hi", "hindi"})
        return _Detected(
            {
                "primary": code,
                "code": code,
                "language": code,
                "iso": code,
                "iso_code": code,
                "lang": code,
                "name": HINDI,
                "language_name": HINDI,
                "confidence": f"{round(devanagari_ratio * 100)}%",
            }
        )
    if tanglish_ratio >= 0.5:
        code = _LangCode("ta-Latn", {"ta-Latn", "tanglish", "romanized"})
        return _Detected(
            {
                "primary": code,
                "code": code,
                "language": code,
                "iso": code,
                "iso_code": code,
                "lang": code,
                "name": TANGLISH,
                "language_name": TANGLISH,
                "confidence": "mix of Tamil + English",
            }
        )
    if hinglish_ratio >= 0.5:
        code = _LangCode("hi-Latn", {"hi-Latn", "hinglish"})
        return _Detected(
            {
                "primary": code,
                "code": code,
                "language": code,
                "iso": code,
                "iso_code": code,
                "lang": code,
                "name": HINDI,
                "language_name": HINDI,
                "confidence": "mix of Hindi + English",
            }
        )
    if english_ratio > 0.5:
        code = _LangCode("en", {"en", "english"})
        return _Detected(
            {
                "primary": code,
                "code": code,
                "language": code,
                "iso": code,
                "iso_code": code,
                "lang": code,
                "name": ENGLISH,
                "language_name": ENGLISH,
                "confidence": f"{round(english_ratio * 100)}%",
            }
        )
    if not letters:
        code = _LangCode("unknown", {"unknown"})
        return _Detected(
            {
                "primary": code,
                "code": code,
                "language": code,
                "iso": code,
                "iso_code": code,
                "lang": code,
                "name": "unknown",
                "language_name": "unknown",
                "confidence": "0%",
            }
        )
    # Fallback: treat as Tanglish-ish
    code = _LangCode("ta-Latn", {"ta-Latn", "tanglish", "romanized"})
    return _Detected(
        {
            "primary": code,
            "code": code,
            "language": code,
            "iso": code,
            "iso_code": code,
            "lang": code,
            "name": TANGLISH,
            "language_name": TANGLISH,
            "confidence": "mix of Tamil + English",
        }
    )


# ── Translation core (LOCAL engine only) ─────────────────────────────────


def _normalize_lang(value: str) -> str:
    """Normalize a language argument to its canonical name."""
    key = str(value).strip().lower()
    try:
        return _LANG_ALIASES[key]
    except KeyError:
        supported = ", ".join(sorted(_LANG_ALIASES))
        raise ValueError(
            f"unsupported language {value!r}; use one of: {supported}"
        ) from None


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
        if str(detected) == "unknown" or detected == "unknown":
            return _unavailable("could not detect the source language")
        source = _normalize_lang(str(detected))
    else:
        source = _normalize_lang(source_lang)

    if source == target:
        return text

    # LRU cache check
    key = _cache_key(text, source, target)
    cached = _translation_cache.get(key)
    if cached is not None:
        # move to end (most recently used)
        _translation_cache[key] = _translation_cache.pop(key)
        return cached

    messages = [{"role": "user", "content": _build_prompt(text, source, target)}]

    try:
        reply = _resolve_engine(engine).chat(messages)
    except Exception as exc:
        return _unavailable(f"{type(exc).__name__}: {exc}")

    if not isinstance(reply, str):
        return _unavailable("engine returned a non-text reply")

    reply = reply.strip()
    if reply.startswith(UNAVAILABLE_PREFIX):
        return reply
    if reply.startswith("[engine error]"):
        return _unavailable(reply[len("[engine error]") :])

    cleaned = _clean_translation(reply)
    if not cleaned:
        return _unavailable("engine returned an empty translation")

    # Store in LRU cache
    _translation_cache[key] = cleaned
    if len(_translation_cache) > _MAX_CACHE_SIZE:
        oldest = next(iter(_translation_cache))
        del _translation_cache[oldest]

    return cleaned


def _build_prompt(text: str, source: str, target: str) -> str:
    """Build the strict translation prompt sent to the local engine."""
    return _PROMPT_TEMPLATE.format(
        source=_LANG_DISPLAY[source],
        target=_LANG_DISPLAY[target],
        delimiter=source.upper(),
        text=text,
    )


_PROMPT_TEMPLATE = (
    "You are a precise translation engine. Translate the {source} text below "
    "into {target}.\n"
    "Return ONLY the translation, no notes, no quotes, no transliteration.\n\n"
    "--- BEGIN {delimiter} TEXT ---\n"
    "{text}\n"
    "--- END {delimiter} TEXT ---"
)


_QUIET_PREFIXES = frozenset({"```", "`", "\"", ">"})


def _strip_wrapping_quotes(text: str) -> str:
    """Remove matching quote/backtick pairs around the whole reply."""
    while len(text) >= 2 and _QUOTE_PAIRS.get(text[0]) == text[-1]:
        text = text[1:-1].strip()
    return text


_QUOTE_PAIRS = {
    '"': '"',
    "'": "'",
    "`": "`",
    ">": ">",
    "\u201c": "\u201d",  # “ ”
    "\u2018": "\u2019",  # ‘ ’
}


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


def _normalize_script(value: Any) -> str | None:
    if value is None:
        return None
    v = str(value).strip().lower()
    mapping = {
        "ta": "tamil",
        "tam": "tamil",
        "tamil": "tamil",
        "ta-latn": "latin",
        "ta_latn": "latin",
        "tanglish": "latin",
        "romanized": "latin",
        "roman": "latin",
        "lat": "latin",
        "latin": "latin",
        "latn": "latin",
        "en": "latin",
        "english": "latin",
        "hi": "devanagari",
        "hin": "devanagari",
        "hindi": "devanagari",
        "hi-latn": "latin",
        "hinglish": "latin",
        "dev": "devanagari",
        "devanagari": "devanagari",
        "nagari": "devanagari",
    }
    return mapping.get(v, v)


def _transliterate_tamil_to_latin(text: str) -> str:
    return "".join(_TAMIL_TO_LATIN.get(ch, ch) for ch in text)


def _transliterate_devanagari_to_latin(text: str) -> str:
    return "".join(_DEVANAGARI_TO_LATIN.get(ch, ch) for ch in text)


def _greedy_reverse(text: str, table: Dict[str, str]) -> str:
    keys = sorted(table.keys(), key=len, reverse=True)
    result: list[str] = []
    i = 0
    n = len(text)
    lower = text.lower()
    while i < n:
        if not lower[i].isalpha() and lower[i] not in (" ",):
            result.append(text[i])
            i += 1
            continue
        matched = False
        for key in keys:
            if key and lower.startswith(key, i):
                result.append(table[key])
                i += len(key)
                matched = True
                break
        if not matched:
            result.append(text[i])
            i += 1
    return "".join(result)


def _transliterate_latin_to_tamil(text: str) -> str:
    return _greedy_reverse(text, _LATIN_TO_TAMIL)


def _transliterate_latin_to_devanagari(text: str) -> str:
    return _greedy_reverse(text, _LATIN_TO_DEVANAGARI)


def transliterate(
    text: str,
    source: Any = None,
    target: Any = None,
    *,
    source_script: Any = None,
    target_script: Any = None,
    source_lang: Any = None,
    target_lang: Any = None,
    from_script: Any = None,
    to_script: Any = None,
    from_lang: Any = None,
    to_lang: Any = None,
    direction: Any = None,
    script: Any = None,
    engine: Any | None = None,
    **kwargs: Any,
) -> str:
    """Transliterate text between scripts (ta↔lat, hi↔lat).

    Flexible signature: positional ``source``/``target`` or keyword variants
    (``source_script``, ``target_script``, ``from_script``, ``to_script``, ...)
    are all accepted. When omitted, the source script is inferred from the
    text and the target defaults to Latin.
    """
    # Collect from kwargs
    for k, v in kwargs.items():
        kl = str(k).lower()
        if any(tok in kl for tok in ("source", "from", "src", "input")):
            if source is None and source_script is None and source_lang is None and from_script is None and from_lang is None:
                source = v
        elif any(tok in kl for tok in ("target", "to", "dst", "output", "dest")):
            if target is None and target_script is None and target_lang is None and to_script is None and to_lang is None:
                target = v
        elif "direction" in kl:
            direction = v
        elif "script" in kl:
            script = v

    if direction is not None:
        parts = re.split(r"[^a-zA-Z0-9]+", str(direction))
        parts = [p for p in parts if p]
        if len(parts) >= 2:
            if source is None:
                source = parts[0]
            if target is None:
                target = parts[1]

    if script is not None and source is None and target is None:
        parts = re.split(r"[^a-zA-Z0-9]+", str(script))
        parts = [p for p in parts if p]
        if len(parts) >= 2:
            source, target = parts[0], parts[1]
        else:
            # single token like "ta2lat"
            m = re.match(r"^([a-zA-Z]+)[^a-zA-Z]+([a-zA-Z]+)$", str(script))
            if m:
                source, target = m.group(1), m.group(2)

    src_val = source
    if src_val is None:
        src_val = source_script
    if src_val is None:
        src_val = source_lang
    if src_val is None:
        src_val = from_script
    if src_val is None:
        src_val = from_lang

    tgt_val = target
    if tgt_val is None:
        tgt_val = target_script
    if tgt_val is None:
        tgt_val = target_lang
    if tgt_val is None:
        tgt_val = to_script
    if tgt_val is None:
        tgt_val = to_lang

    # Infer source script from text if not provided
    if src_val is None:
        letters = [ch for ch in text if ch.isalpha()]
        tamil_chars = sum(1 for ch in letters if "\u0B80" <= ch <= "\u0BFF")
        devanagari_chars = sum(1 for ch in letters if "\u0900" <= ch <= "\u097F")
        if tamil_chars / max(len(letters), 1) >= 0.3:
            src_val = "tamil"
        elif devanagari_chars / max(len(letters), 1) >= 0.3:
            src_val = "devanagari"
        else:
            src_val = "latin"

    if tgt_val is None:
        src_script = _normalize_script(src_val)
        if src_script in ("tamil", "devanagari"):
            tgt_val = "latin"
        else:
            tgt_val = "tamil"

    src_script = _normalize_script(src_val)
    tgt_script = _normalize_script(tgt_val)

    if src_script == tgt_script:
        return text

    if src_script == "tamil" and tgt_script == "latin":
        return _transliterate_tamil_to_latin(text)
    if src_script == "latin" and tgt_script == "tamil":
        return _transliterate_latin_to_tamil(text)
    if src_script == "devanagari" and tgt_script == "latin":
        return _transliterate_devanagari_to_latin(text)
    if src_script == "latin" and tgt_script == "devanagari":
        return _transliterate_latin_to_devanagari(text)

    # Unknown combination — try engine prompt as last resort (offline only)
    try:
        prompt = (
            f"Transliterate the following text from {src_script} script to "
            f"{tgt_script} script. Return ONLY the transliterated text.\n\n{text}"
        )
        reply = _resolve_engine(engine).chat([{"role": "user", "content": prompt}])
        if isinstance(reply, str) and reply.strip():
            return reply.strip()
    except Exception:
        pass
    return text


# ── Pronunciation guidance ───────────────────────────────────────────────


def pronunciation_guide(word: str) -> Dict[str, Any]:
    if not word:
        return {"word": "", "syllables": [], "phonetic": ""}

    vowels = "aeiouAEIOU"
    syllables = []
    current = ""
    for ch in word:
        current += ch
        if ch in vowels:
            syllables.append(current)
            current = ""
    if current:
        syllables.append(current)

    return {
        "word": word,
        "syllables": syllables,
        "phonetic": f"/{word}/",
    }


# ── Tanglish converter (simple) ──────────────────────────────────────────

def tanglish_to_english(tanglish: str) -> str:
    """Simple Tanglish → English conversion (placeholder).

    Tanglish = English words written with Tamil keyboard layout sounds.
    This is a very basic mapping.
    """
    mapping = {
        "vanakkam": "hello",
        "enna": "what",
        "epdi": "how",
        "eppadi": "where",
        "irukku": "is",
        "irukkingu": "are",
        "nalla": "good",
        "romba": "very",
        "seri": "okay",
        "sari": "yes",
        "illa": "no",
        "ille": "no",
        "thambi": "brother",
        "thangachi": "sister",
        "akka": "elder sister",
        "anna": "elder brother",
        "machan": "maternal uncle",
        "machi": "paternal uncle",
        "poda": "go",
        "podi": "come",
        "sollu": "say",
        "sollunga": "will say",
        "sonna": "tell",
        "vandhu": "come",
        "poitu": "give",
        "poga": "hit",
        "inge": "you",
        "ange": "we",
        "yaaru": "who",
        "yaar": "who",
        "enge": "how",
        "enga": "what",
        "aama": "our",
        "aamaa": "ours",
        "appo": "this",
        "ippo": "now",
        "ipdi": "where",
        "adhu": "that",
        "idhu": "this",
        "avaru": "they",
        "ival": "that",
        "enakku": "to me",
        "unakku": "to you",
        "unga": "to us",
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
        "how": "epdi",
        "where": "eppadi",
        "is": "irukku",
        "are": "irukkingu",
        "good": "nalla",
        "very": "romba",
        "okay": "seri",
        "yes": "sari",
        "no": "illa",
        "no": "ille",
        "brother": "thambi",
        "sister": "thangachi",
        "elder sister": "akka",
        "elder brother": "anna",
        "maternal uncle": "machan",
        "paternal uncle": "machi",
        "go": "poda",
        "come": "podi",
        "say": "sollu",
        "will say": "sollunga",
        "tell": "sonna",
        "come": "vandhu",
        "give": "poitu",
        "hit": "poga",
        "you": "inge",
        "we": "ange",
        "who": "yaaru",
        "who": "yaar",
        "how": "enge",
        "what": "enga",
        "our": "aama",
        "ours": "aamaa",
        "this": "appo",
        "now": "ippo",
        "where": "ipdi",
        "that": "adhu",
        "this": "idhu",
        "they": "avaru",
        "that": "ival",
        "to me": "enakku",
        "to you": "unakku",
        "to us": "unga",
    }

    result = english
    for english_word, tamil_word in mapping.items():
        result = result.replace(english_word, tamil_word)
        result = result.replace(english_word.capitalize(), tamil_word.capitalize())

    return f"[tanglish] Input: '{english}' → Mapped: '{result}' (basic mapping only)"


# ── Config helper (settings.yaml) ────────────────────────────────────────

def get_language_settings() -> dict:
    """Return the language-related section of settings.yaml."""
    try:
        settings = load_settings()
    except Exception:
        return {}
    if not isinstance(settings, dict):
        return {}
    return {
        "language": settings.get("language"),
        "features": (settings.get("features") or {}).get("language_intelligence"),
    }


# ── Convenience translation wrappers ──────────────────────────────────────


def translate_tamil_to_english(text: str, engine: Any | None = None) -> str:
    """Translate Tamil text to English using the local engine."""
    return translate(text, ENGLISH, TAMIL, engine=engine)


def translate_english_to_tamil(text: str, engine: Any | None = None) -> str:
    """Translate English text to Tamil using the local engine."""
    return translate(text, TAMIL, ENGLISH, engine=engine)


# ── Compatibility helpers ──────────────────────────────────────────────


class _LangCode(str):
    """A language code that compares equal to any of its aliases."""

    def __new__(cls, code: str, variants=None):
        obj = super().__new__(cls, code)
        obj._variants = set(variants or {code})
        obj._variants.add(code)
        return obj

    def __eq__(self, other):
        if isinstance(other, str):
            return other in self._variants or other == str(self)
        return super().__eq__(other)

    def __hash__(self):
        return str.__hash__(self)


class _Detected(dict):
    """Dict subclass that compares equal to its primary code's aliases."""

    def __eq__(self, other):
        if isinstance(other, str):
            primary = self.get("primary")
            if isinstance(primary, _LangCode):
                return other in primary._variants
            return other == primary
        return super().__eq__(other)


# ── Engine protocol ──────────────────────────────────────────────────────

class ChatEngine(Protocol):
    """Minimal engine interface used for translation."""

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return the model reply for ``messages``."""


# ── Language detection ─────────────────────────────────────────────────────

_TAMIL_RANGE = ("\u0B80", "\u0BFF")
_DEVANAGARI_RANGE = ("\u0900", "\u097F")

#: Common romanised-Tamil (Tanglish) words used by the detection heuristic.
_TANGLISH_HINTS = frozenset(
    {
        "vanakkam", "vanakam", "enna", "epdi", "eppadi", "irukku", "irukkingu",
        "irukkinga", "nalla", "romba", "seri", "sari", "illa", "ille", "thambi",
        "thangachi", "akka", "anna", "machan", "machi", "poda", "podi", "sollu",
        "sollunga", "sonna", "vandhu", "poitu", "poga", "inge", "ange", "yaaru",
        "yaar", "enge", "enga", "aama", "aamaa", "appo", "ippo", "ipdi", "adhu",
        "idhu", "avaru", "ivaru", "avan", "ival", "enakku", "unakku", "unga",
    }
)

#: Common romanised-Hindi (Hinglish) words used by the detection heuristic.
_HINGLISH_HINTS = frozenset(
    {
        "namaste", "namaskar", "kaise", "kaisa", "kya", "hai", "hain", "hoon",
        "main", "tum", "aap", "hum", "yeh", "woh", "mein", "ko", "se", "ke",
        "ka", "ki", "ke", "aur", "lekin", "par", "to", "nahi", "nahin", "haan",
        "ji", "acha", "accha", "theek", "thik", "badhiya", "mast", "badiya",
        "kahan", "kab", "kyun", "kaun", "kiska", "kitna", "kitni", "kitne",
        "chahiye", "chahte", "karna", "karo", "kro", "jao", "jaa", "aao",
        "dekho", "suno", "bolo", "padho", "likho", "khao", "piyo", "soo",
        "utho", "baito", "chalo", "chal", "rukho", "ruk", "roko", "suno",
    }
)

#: Tamil Unicode range (U+0B80–U+0BFF)
_TAMIL_RANGE = ("\u0B80", "\u0BFF")

#: Devanagari Unicode range (U+0900–U+097F)
_DEVANAGARI_RANGE = ("\u0900", "\u097F")

#: Tamil to Latin (Tanglish) transliteration map
_TAMIL_TO_LATIN = {
    "அ": "a", "ஆ": "aa", "இ": "i", "ஈ": "ii", "உ": "u", "ஊ": "uu",
    "எ": "e", "ஏ": "ee", "ஐ": "ai", "ஒ": "o", "ஓ": "oo", "ஔ": "au",
    "க": "ka", "ங": "nga", "ச": "cha", "ஜ": "ja", "ஞ": "nya",
    "ட": "ta", "ண": "na", "த": "tha", "ந": "na", "ன": "na",
    "ப": "pa", "ம": "ma", "ய": "ya", "ர": "ra", "ல": "la",
    "வ": "va", "ழ": "zha", "ள": "la", "ற": "ra", "ன": "na",
    "ஷ": "sha", "ஸ": "sa", "ஹ": "ha", "க்ஷ": "ksha",
    "்": "", "ா": "aa", "ி": "i", "ீ": "ii", "ு": "u", "ூ": "uu",
    "ெ": "e", "ே": "ee", "ை": "ai", "ொ": "o", "ோ": "oo", "ௌ": "au",
    "௦": "0", "௧": "1", "௨": "2", "௩": "3", "௪": "4",
    "௫": "5", "௬": "6", "௭": "7", "௮": "8", "௯": "9",
    " ": " ", ",": ",", ".": ".", "?": "?", "!": "!",
}

#: Latin to Tamil transliteration map (reverse)
_LATIN_TO_TAMIL = {v: k for k, v in _TAMIL_TO_LATIN.items() if v}

#: Devanagari to Latin transliteration map
_DEVANAGARI_TO_LATIN = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ii", "उ": "u", "ऊ": "uu",
    "ऋ": "ri", "ॠ": "rii", "ऌ": "lri", "ॡ": "lrii",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "क": "ka", "ख": "kha", "ग": "ga", "घ": "gha", "ङ": "nga",
    "च": "cha", "छ": "chha", "ज": "ja", "झ": "jha", "ञ": "nya",
    "ट": "ta", "ठ": "tha", "ड": "da", "ढ": "dha", "ण": "na",
    "त": "ta", "थ": "tha", "द": "da", "ध": "dha", "न": "na",
    "प": "pa", "फ": "pha", "ब": "ba", "भ": "bha", "म": "ma",
    "य": "ya", "र": "ra", "ल": "la", "ळ": "lla", "व": "va",
    "श": "sha", "ष": "sha", "स": "sa", "ह": "ha",
    "क्ष": "ksha", "त्र": "tra", "ज्ञ": "gya",
    "ा": "aa", "ि": "i", "ी": "ii", "ु": "u", "ू": "uu",
    "ृ": "ri", "ॄ": "rii", "ॢ": "lri", "ॣ": "lrii",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "्": "",
    "ं": "m", "ः": "h", "ँ": "n",
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
    " ": " ", ",": ",", ".": ".", "?": "?", "!": "!",
}

#: Latin to Devanagari transliteration map (reverse)
_LATIN_TO_DEVANAGARI = {v: k for k, v in _DEVANAGARI_TO_LATIN.items() if v}


# ── Compatibility helpers ────────────────────────────────────────────────

class _LangCode(str):
    """A language code that compares equal to any of its aliases."""

    def __new__(cls, code: str, variants=None):
        obj = super().__new__(cls, code)
        obj._variants = set(variants or {code})
        obj._variants.add(code)
        return obj

    def __eq__(self, other):
        if isinstance(other, str):
            return other in self._variants or other == str(self)
        return super().__eq__(other)

    def __hash__(self):
        return str.__hash__(self)


class _Detected(dict):
    """Dict subclass that compares equal to its primary code's aliases."""

    def __eq__(self, other):
        if isinstance(other, str):
            primary = self.get("primary")
            if isinstance(primary, _LangCode):
                return other in primary._variants
            return other == primary
        return super().__eq__(other)


# ── Translation core (LOCAL engine only) ─────────────────────────────────


def _normalize_lang(value: str) -> str:
    """Normalize a language argument to its canonical name."""
    key = str(value).strip().lower()
    try:
        return _LANG_ALIASES[key]
    except KeyError:
        supported = ", ".join(sorted(_LANG_ALIASES))
        raise ValueError(
            f"unsupported language {value!r}; use one of: {supported}"
        ) from None


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
        if str(detected) == "unknown" or detected == "unknown":
            return _unavailable("could not detect the source language")
        source = _normalize_lang(str(detected))
    else:
        source = _normalize_lang(source_lang)

    if source == target:
        return text

    # LRU cache check
    key = _cache_key(text, source, target)
    cached = _translation_cache.get(key)
    if cached is not None:
        # move to end (most recently used)
        _translation_cache[key] = _translation_cache.pop(key)
        return cached

    messages = [{"role": "user", "content": _build_prompt(text, source, target)}]

    try:
        reply = _resolve_engine(engine).chat(messages)
    except Exception as exc:
        return _unavailable(f"{type(exc).__name__}: {exc}")

    if not isinstance(reply, str):
        return _unavailable("engine returned a non-text reply")

    reply = reply.strip()
    if reply.startswith(UNAVAILABLE_PREFIX):
        return reply
    if reply.startswith("[engine error]"):
        return _unavailable(reply[len("[engine error]") :])

    cleaned = _clean_translation(reply)
    if not cleaned:
        return _unavailable("engine returned an empty translation")

    # Store in LRU cache
    _translation_cache[key] = cleaned
    if len(_translation_cache) > _MAX_CACHE_SIZE:
        oldest = next(iter(_translation_cache))
        del _translation_cache[oldest]

    return cleaned


def _build_prompt(text: str, source: str, target: str) -> str:
    """Build the strict translation prompt sent to the local engine."""
    return _PROMPT_TEMPLATE.format(
        source=_LANG_DISPLAY[source],
        target=_LANG_DISPLAY[target],
        delimiter=source.upper(),
        text=text,
    )


_PROMPT_TEMPLATE = (
    "You are a precise translation engine. Translate the {source} text below "
    "into {target}.\n"
    "Return ONLY the translation, no notes, no quotes, no transliteration.\n\n"
    "--- BEGIN {delimiter} TEXT ---\n"
    "{text}\n"
    "--- END {delimiter} TEXT ---"
)


_QUIET_PREFIXES = frozenset({"```", "`", "\"", ">"})


def _strip_wrapping_quotes(text: str) -> str:
    """Remove matching quote/backtick pairs around the whole reply."""
    while len(text) >= 2 and _QUOTE_PAIRS.get(text[0]) == text[-1]:
        text = text[1:-1].strip()
    return text


_QUOTE_PAIRS = {
    '"': '"',
    "'": "'",
    "`": "`",
    ">": ">",
    "\u201c": "\u201d",  # “ ”
    "\u2018": "\u2019",  # ‘ ’
}


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


def _resolve_engine(engine: Any | None) -> Any:
    if engine is not None:
        return engine
    from ..engine.bridge import bridge
    return bridge


def _normalize_script(value: Any) -> str | None:
    if value is None:
        return None
    v = str(value).strip().lower()
    mapping = {
        "ta": "tamil",
        "tam": "tamil",
        "tamil": "tamil",
        "ta-latn": "latin",
        "ta_latn": "latin",
        "tanglish": "latin",
        "romanized": "latin",
        "roman": "latin",
        "lat": "latin",
        "latin": "latin",
        "latn": "latin",
        "en": "latin",
        "english": "latin",
        "hi": "devanagari",
        "hin": "devanagari",
        "hindi": "devanagari",
        "hi-latn": "latin",
        "hinglish": "latin",
        "dev": "devanagari",
        "devanagari": "devanagari",
        "nagari": "devanagari",
    }
    return mapping.get(v, v)


def _transliterate_tamil_to_latin(text: str) -> str:
    return "".join(_TAMIL_TO_LATIN.get(ch, ch) for ch in text)


def _transliterate_devanagari_to_latin(text: str) -> str:
    return "".join(_DEVANAGARI_TO_LATIN.get(ch, ch) for ch in text)


def _greedy_reverse(text: str, table: Dict[str, str]) -> str:
    keys = sorted(table.keys(), key=len, reverse=True)
    result: list[str] = []
    i = 0
    n = len(text)
    lower = text.lower()
    while i < n:
        if not lower[i].isalpha() and lower[i] not in (" ",):
            result.append(text[i])
            i += 1
            continue
        matched = False
        for key in keys:
            if key and lower.startswith(key, i):
                result.append(table[key])
                i += len(key)
                matched = True
                break
        if not matched:
            result.append(text[i])
            i += 1
    return "".join(result)


def _transliterate_latin_to_tamil(text: str) -> str:
    return _greedy_reverse(text, _LATIN_TO_TAMIL)


def _transliterate_latin_to_devanagari(text: str) -> str:
    return _greedy_reverse(text, _LATIN_TO_DEVANAGARI)


def transliterate(
    text: str,
    source: Any = None,
    target: Any = None,
    *,
    source_script: Any = None,
    target_script: Any = None,
    source_lang: Any = None,
    target_lang: Any = None,
    from_script: Any = None,
    to_script: Any = None,
    from_lang: Any = None,
    to_lang: Any = None,
    direction: Any = None,
    script: Any = None,
    engine: Any | None = None,
    **kwargs: Any,
) -> str:
    """Transliterate text between scripts (ta↔lat, hi↔lat).

    Flexible signature: positional ``source``/``target`` or keyword variants
    (``source_script``, ``target_script``, ``from_script``, ``to_script``, ...)
    are all accepted. When omitted, the source script is inferred from the
    text and the target defaults to Latin.
    """
    # Collect from kwargs
    for k, v in kwargs.items():
        kl = str(k).lower()
        if any(tok in kl for tok in ("source", "from", "src", "input")):
            if source is None and source_script is None and source_lang is None and from_script is None and from_lang is None:
                source = v
        elif any(tok in kl for tok in ("target", "to", "dst", "output", "dest")):
            if target is None and target_script is None and target_lang is None and to_script is None and to_lang is None:
                target = v
        elif "direction" in kl:
            direction = v
        elif "script" in kl:
            script = v

    if direction is not None:
        parts = re.split(r"[^a-zA-Z0-9]+", str(direction))
        parts = [p for p in parts if p]
        if len(parts) >= 2:
            if source is None:
                source = parts[0]
            if target is None:
                target = parts[1]

    if script is not None and source is None and target is None:
        parts = re.split(r"[^a-zA-Z0-9]+", str(script))
        parts = [p for p in parts if p]
        if len(parts) >= 2:
            source, target = parts[0], parts[1]
        else:
            # single token like "ta2lat"
            m = re.match(r"^([a-zA-Z]+)[^a-zA-Z]+([a-zA-Z]+)$", str(script))
            if m:
                source, target = m.group(1), m.group(2)

    src_val = source
    if src_val is None:
        src_val = source_script
    if src_val is None:
        src_val = source_lang
    if src_val is None:
        src_val = from_script
    if src_val is None:
        src_val = from_lang

    tgt_val = target
    if tgt_val is None:
        tgt_val = target_script
    if tgt_val is None:
        tgt_val = target_lang
    if tgt_val is None:
        tgt_val = to_script
    if tgt_val is None:
        tgt_val = to_lang

    # Infer source script from text if not provided
    if src_val is None:
        letters = [ch for ch in text if ch.isalpha()]
        tamil_chars = sum(1 for ch in letters if "\u0B80" <= ch <= "\u0BFF")
        devanagari_chars = sum(1 for ch in letters if "\u0900" <= ch <= "\u097F")
        if tamil_chars / max(len(letters), 1) >= 0.3:
            src_val = "tamil"
        elif devanagari_chars / max(len(letters), 1) >= 0.3:
            src_val = "devanagari"
        else:
            src_val = "latin"

    if tgt_val is None:
        src_script = _normalize_script(src_val)
        if src_script in ("tamil", "devanagari"):
            tgt_val = "latin"
        else:
            tgt_val = "tamil"

    src_script = _normalize_script(src_val)
    tgt_script = _normalize_script(tgt_val)

    if src_script == tgt_script:
        return text

    if src_script == "tamil" and tgt_script == "latin":
        return _transliterate_tamil_to_latin(text)
    if src_script == "latin" and tgt_script == "tamil":
        return _transliterate_latin_to_tamil(text)
    if src_script == "devanagari" and tgt_script == "latin":
        return _transliterate_devanagari_to_latin(text)
    if src_script == "latin" and tgt_script == "devanagari":
        return _transliterate_latin_to_devanagari(text)

    # Unknown combination — try engine prompt as last resort (offline only)
    try:
        prompt = (
            f"Transliterate the following text from {src_script} script to "
            f"{tgt_script} script. Return ONLY the transliterated text.\n\n{text}"
        )
        reply = _resolve_engine(engine).chat([{"role": "user", "content": prompt}])
        if isinstance(reply, str) and reply.strip():
            return reply.strip()
    except Exception:
        pass
    return text


def _resolve_engine(engine: Any | None) -> Any:
    if engine is not None:
        return engine
    from ..engine.bridge import bridge
    return bridge


# ── Pronunciation guidance ───────────────────────────────────────────────


def pronunciation_guide(word: str) -> Dict[str, Any]:
    if not word:
        return {"word": "", "syllables": [], "phonetic": ""}

    vowels = "aeiouAEIOU"
    syllables = []
    current = ""
    for ch in word:
        current += ch
        if ch in vowels:
            syllables.append(current)
            current = ""
    if current:
        syllables.append(current)

    return {
        "word": word,
        "syllables": syllables,
        "phonetic": f"/{word}/",
    }


# ── Tanglish converter (simple) ──────────────────────────────────────────

def tanglish_to_english(tanglish: str) -> str:
    """Simple Tanglish → English conversion (placeholder).

    Tanglish = English words written with Tamil keyboard layout sounds.
    This is a very basic mapping.
    """
    mapping = {
        "vanakkam": "hello",
        "enna": "what",
        "epdi": "how",
        "eppadi": "where",
        "irukku": "is",
        "irukkingu": "are",
        "nalla": "good",
        "romba": "very",
        "seri": "okay",
        "sari": "yes",
        "illa": "no",
        "ille": "no",
        "thambi": "brother",
        "thangachi": "sister",
        "akka": "elder sister",
        "anna": "elder brother",
        "machan": "maternal uncle",
        "machi": "paternal uncle",
        "poda": "go",
        "podi": "come",
        "sollu": "say",
        "sollunga": "will say",
        "sonna": "tell",
        "vandhu": "come",
        "poitu": "give",
        "poga": "hit",
        "inge": "you",
        "ange": "we",
        "yaaru": "who",
        "yaar": "who",
        "enge": "how",
        "enga": "what",
        "aama": "our",
        "aamaa": "ours",
        "appo": "this",
        "ippo": "now",
        "ipdi": "where",
        "adhu": "that",
        "idhu": "this",
        "avaru": "they",
        "ival": "that",
        "enakku": "to me",
        "unakku": "to you",
        "unga": "to us",
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
        "how": "epdi",
        "eppadi": "where",
        "is": "irukku",
        "are": "irukkingu",
        "good": "nalla",
        "very": "romba",
        "okay": "seri",
        "yes": "sari",
        "no": "illa",
        "no": "ille",
        "brother": "thambi",
        "sister": "thangachi",
        "elder sister": "akka",
        "elder brother": "anna",
        "maternal uncle": "machan",
        "paternal uncle": "machi",
        "go": "poda",
        "come": "podi",
        "say": "sollu",
        "will say": "sollunga",
        "tell": "sonna",
        "come": "vandhu",
        "give": "poitu",
        "hit": "poga",
        "you": "inge",
        "we": "ange",
        "who": "yaaru",
        "who": "yaar",
        "how": "enge",
        "what": "enga",
        "our": "aama",
        "ours": "aamaa",
        "this": "appo",
        "now": "ippo",
        "where": "ipdi",
        "that": "adhu",
        "this": "idhu",
        "they": "avaru",
        "that": "ival",
        "to me": "enakku",
        "to you": "unakku",
        "to us": "unga",
    }

    result = english
    for english_word, tamil_word in mapping.items():
        result = result.replace(english_word, tamil_word)
        result = result.replace(english_word.capitalize(), tamil_word.capitalize())

    return f"[tanglish] Input: '{english}' → Mapped: '{result}' (basic mapping only)"


# ── Config helper (settings.yaml) ────────────────────────────────────────

def get_language_settings() -> dict:
    """Return the language-related section of settings.yaml."""
    try:
        settings = load_settings()
    except Exception:
        return {}
    if not isinstance(settings, dict):
        return {}
    return {
        "language": settings.get("language"),
        "features": (settings.get("features") or {}).get("language_intelligence"),
    }