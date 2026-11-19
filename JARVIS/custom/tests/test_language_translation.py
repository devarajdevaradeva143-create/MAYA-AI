"""Tests for local-engine translation in ``custom/tools/language.py``.

Every test uses a fake engine — no network and no model required. The one
default-engine test monkeypatches the local bridge, so it never connects.
"""

from __future__ import annotations

import pytest

from custom.tools.language import (
    UNAVAILABLE_PREFIX,
    _translation_cache,
    clear_translation_cache,
    detect_language,
    transliterate,
    translate,
    translate_english_to_tamil,
    translate_tamil_to_english,
)


class FakeEngine:
    """Minimal stand-in for ``EngineBridge.chat()``."""

    def __init__(self, reply: str = "", error: Exception | None = None) -> None:
        self.reply = reply
        self.error = error
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return self.reply


def _only_prompt(engine: FakeEngine) -> str:
    """Assert the engine was called exactly once and return its prompt."""
    assert len(engine.calls) == 1, f"expected 1 engine call, got {len(engine.calls)}"
    return engine.calls[0][0]["content"]


TAMIL_TEXT = "காலை வணக்கம்"


# ── Core translation ────────────────────────────────────────────────

def test_translate_returns_reply_and_builds_strict_prompt() -> None:
    """A clean engine reply is returned and the prompt is explicit."""
    engine = FakeEngine("Good morning")

    result = translate(TAMIL_TEXT, "en", source_lang="ta", engine=engine)

    assert result == "Good morning"
    prompt = _only_prompt(engine)
    assert "Tamil" in prompt
    assert "English" in prompt
    assert TAMIL_TEXT in prompt
    assert "Return ONLY the translation" in prompt
    assert "no notes" in prompt
    assert "no transliteration" in prompt


def test_translate_detects_source_when_none() -> None:
    """source_lang=None detects pure Tamil Unicode as Tamil."""
    engine = FakeEngine("Hello")

    translate("வணக்கம்", "english", engine=engine)

    prompt = _only_prompt(engine)
    assert "Tamil text" in prompt
    assert "into English" in prompt


@pytest.mark.parametrize(
    "reply",
    [
        '"Good morning"',
        "'Good morning'",
        "`Good morning`",
        "\u201cGood morning\u201d",
        "Translation: Good morning",
        'Translation: "Good morning"',
        "**Translation:** Good morning",
        "```\nGood morning\n```",
        "```ta\nGood morning\n```",
        "  Good morning  \n\n\n",
    ],
)
def test_translate_cleans_engine_noise(reply: str) -> None:
    """Quotes, backticks, labels, fences, and blank lines are cleaned."""
    engine = FakeEngine(reply)

    assert translate(TAMIL_TEXT, "en", "tamil", engine) == "Good morning"


def test_translate_engine_exception_returns_honest_fallback() -> None:
    """A raising engine yields a clear string, never an exception."""
    engine = FakeEngine(error=RuntimeError("model offline"))

    result = translate(TAMIL_TEXT, "en", "tamil", engine)

    assert result.startswith(UNAVAILABLE_PREFIX)
    assert "model offline" in result


def test_translate_bridge_error_string_is_not_pretended() -> None:
    """The bridge's '[engine error]' string becomes an honest fallback."""
    engine = FakeEngine("[engine error] connection refused")

    result = translate(TAMIL_TEXT, "en", "tamil", engine)

    assert result.startswith(UNAVAILABLE_PREFIX)
    assert "connection refused" in result
    assert "[engine error]" not in result


def test_translate_empty_reply_is_unavailable() -> None:
    """An empty/whitespace reply is rejected instead of returned."""
    result = translate(TAMIL_TEXT, "en", "tamil", FakeEngine("   \n "))

    assert result.startswith(UNAVAILABLE_PREFIX)
    assert "empty" in result


def test_translate_same_language_returns_input_without_engine() -> None:
    """source == target short-circuits with no engine call."""
    engine = FakeEngine("should not be used")

    assert translate("Hello there", "english", "en", engine) == "Hello there"
    assert engine.calls == []


def test_translate_empty_input_returns_empty_without_engine() -> None:
    """Empty or whitespace-only input returns '' and does not call the engine."""
    engine = FakeEngine("should not be used")

    assert translate("", "ta", engine=engine) == ""
    assert translate("   \n\t", "ta", engine=engine) == ""
    assert engine.calls == []


def test_translate_rejects_unsupported_language() -> None:
    """Unknown language names fail loudly (programming error)."""
    with pytest.raises(ValueError):
        translate("hello", "klingon", engine=FakeEngine("x"))


def test_translate_uses_local_bridge_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no engine argument the local bridge is imported and used lazily."""
    import custom.engine.bridge as bridge_module

    fake = FakeEngine("Hello")
    monkeypatch.setattr(bridge_module, "bridge", fake)

    assert translate("வணக்கம்", "en", "tamil") == "Hello"
    assert len(fake.calls) == 1


# ── Backward-compatible wrappers ────────────────────────────────────

def test_tamil_to_english_wrapper_delegates() -> None:
    """translate_tamil_to_english uses the shared core with ta→en."""
    engine = FakeEngine("Hello")

    assert translate_tamil_to_english("வணக்கம்", engine=engine) == "Hello"
    prompt = _only_prompt(engine)
    assert "Tamil text" in prompt
    assert "into English" in prompt
    assert "வணக்கம்" in prompt


def test_english_to_tamil_wrapper_delegates() -> None:
    """translate_english_to_tamil uses the shared core with en→ta."""
    engine = FakeEngine("வணக்கம்")

    assert translate_english_to_tamil("Hello", engine=engine) == "வணக்கம்"
    prompt = _only_prompt(engine)
    assert "English text" in prompt
    assert "into Tamil" in prompt
    assert "Hello" in prompt


# ── Language detection ──────────────────────────────────────────────

def test_detect_pure_tamil_unicode() -> None:
    assert detect_language("காலை வணக்கம்")["primary"] == "tamil"


def test_detect_english() -> None:
    assert detect_language("Hello, how are you today?")["primary"] == "english"


def test_detect_tanglish() -> None:
    assert detect_language("Vanakkam da, epdi irukku?")["primary"] == "tanglish"


def test_detect_blank_or_symbol_only_is_unknown() -> None:
    assert detect_language("   ")["primary"] == "unknown"
    assert detect_language("12345 !!!")["primary"] == "unknown"


# ── Hindi support ────────────────────────────────────────────────────────

def test_translate_hindi_to_english() -> None:
    engine = FakeEngine("Hello")
    result = translate("नमस्ते", "en", source_lang="hi", engine=engine)
    assert result == "Hello"
    prompt = _only_prompt(engine)
    assert "Hindi" in prompt
    assert "English" in prompt


def test_detect_hindi() -> None:
    assert detect_language("नमस्ते दुनिया")["primary"] == "hi"


# ── Transliteration ──────────────────────────────────────────────────────

def test_transliterate_tamil_to_latin() -> None:
    out = transliterate("வணக்கம்", "tamil", "latin")
    assert isinstance(out, str)
    assert out.isascii()
    assert len(out) > 0


def test_transliterate_latin_to_tamil() -> None:
    out = transliterate("vanakkam", "latin", "tamil")
    assert isinstance(out, str)
    assert len(out) > 0


def test_transliterate_hindi_to_latin() -> None:
    out = transliterate("नमस्ते", "hi", "lat")
    assert isinstance(out, str)
    assert out.isascii()


def test_transliterate_flexible_kwargs() -> None:
    out = transliterate("வணக்கம்", source_script="tamil", target_script="latin")
    assert isinstance(out, str) and out.isascii()
    out2 = transliterate("வணக்கம்", from_script="ta", to_script="lat")
    assert isinstance(out2, str) and out2.isascii()


def test_transliterate_infer_source() -> None:
    out = transliterate("வணக்கம்")
    assert isinstance(out, str) and out.isascii()


# ── LRU cache ────────────────────────────────────────────────────────────

def test_translation_cache_hit_avoids_engine() -> None:
    clear_translation_cache()
    engine = FakeEngine("Hello")
    assert translate("வணக்கம்", "en", "tamil", engine=engine) == "Hello"
    assert len(engine.calls) == 1
    # second call should use cache
    assert translate("வணக்கம்", "en", "tamil", engine=engine) == "Hello"
    assert len(engine.calls) == 1


def test_translation_cache_eviction() -> None:
    clear_translation_cache()
    for i in range(105):
        engine = FakeEngine(f"out{i}")
        translate(f"text{i}", "en", "tamil", engine=engine)
    assert len(_translation_cache) <= 100
