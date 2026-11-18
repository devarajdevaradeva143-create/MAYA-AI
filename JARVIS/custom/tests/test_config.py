"""Tests for Maya AI config loading and offline-memory path resolution."""

from custom.config import load_settings
from custom.tools.store import ENV_STORE_PATH, default_store_path


def test_load_settings_returns_dict():
    """Config file should load as a dict."""
    settings = load_settings()
    assert isinstance(settings, dict), f"Expected dict, got {type(settings)}"


def test_settings_have_key_mode():
    """Settings should have a 'mode' key."""
    settings = load_settings()
    assert "mode" in settings, "Expected 'mode' key in settings"


def test_mode_is_offline():
    """Default mode should be offline."""
    settings = load_settings()
    assert settings.get("mode") == "offline", f"Expected mode=offline, got {settings.get('mode')}"


def test_settings_have_persona():
    """Settings should have a persona key."""
    settings = load_settings()
    assert "persona" in settings, "Expected 'persona' key in settings"


def test_settings_have_offline_memory_key():
    """Settings must define memory.offline (source of the store path)."""
    settings = load_settings()
    memory = settings.get("memory")
    assert isinstance(memory, dict), "Expected nested 'memory' settings"
    assert memory.get("offline"), "Expected memory.offline to be set"
    assert "online" in memory, "Expected memory.online to stay separate"


def test_assistant_store_is_offline_only(monkeypatch):
    """Default store path must be inside MAYA AI/memory/offline."""
    monkeypatch.delenv(ENV_STORE_PATH, raising=False)
    path = default_store_path()
    assert path.name == "assistant.json"
    assert path.parent.name == "offline"
    assert "online" not in str(path).replace("\\", "/").split("/")
    assert "MAYA AI" in path.parts
