"""Shared pytest fixtures for the Maya AI test suite.

The translation module keeps a module-level LRU cache. Tests inject different
fake engines for the same input text, so the cache must be reset between tests
to keep them independent. Production behaviour is unaffected.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_translation_cache() -> None:
    """Clear the translation LRU cache before every test."""
    from custom.tools.language import clear_translation_cache

    clear_translation_cache()
