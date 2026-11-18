"""Tests for Maya AI persona loader."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom.persona.loader import load_persona, list_personas


def test_list_personas():
    """Should list available persona names."""
    names = list_personas()
    assert "girlfriend" in names, f"Expected 'girlfriend' in {names}"
    assert "english_teacher" in names, f"Expected 'english_teacher' in {names}"


def test_load_girlfriend_persona():
    """Should load girlfriend persona content."""
    content = load_persona("girlfriend")
    assert isinstance(content, str), f"Expected string, got {type(content)}"
    assert len(content) > 0, "Expected non-empty girlfriend persona"
    # Check key persona traits
    assert "girlfriend" in content.lower() or "sweet" in content.lower() or "caring" in content.lower()


def test_load_english_teacher_persona():
    """Should load english teacher persona content."""
    content = load_persona("english_teacher")
    assert isinstance(content, str), f"Expected string, got {type(content)}"
    assert len(content) > 0, "Expected non-empty english teacher persona"
    # Check key teacher traits
    assert "teacher" in content.lower() or "teach" in content.lower() or "grammar" in content.lower()


def test_load_unknown_persona():
    """Should return empty string for unknown persona."""
    content = load_persona("unknown_persona")
    assert content == "", f"Expected empty string, got: {content!r}"


if __name__ == "__main__":
    test_list_personas()
    print("✓ test_list_personas passed")
    test_load_girlfriend_persona()
    print("✓ test_load_girlfriend_persona passed")
    test_load_english_teacher_persona()
    print("✓ test_load_english_teacher_persona passed")
    test_load_unknown_persona()
    print("✓ test_load_unknown_persona passed")
    print("\nAll persona tests passed!")