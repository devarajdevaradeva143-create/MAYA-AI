"""Session watchdog tests — idle, session expiry and voice re-check.

All stores are temporary; the real offline memory is never touched.
"""

import time

import pytest
from click.testing import CliRunner

from custom import cli as cli_module
from custom.cli import main
from custom.tools import watchdog
from custom.tools.security import SecurityManager
from custom.tools.watchdog import SessionWatchdog

PIN = "1234"


def cfg(**overrides):
    base = {
        "idle_lock_minutes": 5.0,
        "max_session_minutes": 0.0,
        "voice_check_minutes": 0.0,
        "check_seconds": 15.0,
        "voice_seconds": 5.0,
    }
    base.update(overrides)
    return base


@pytest.fixture()
def manager(tmp_path):
    fresh = SecurityManager(tmp_path / "security.json")
    fresh.set_pin(PIN)
    fresh.verify_pin(PIN)
    return fresh


@pytest.fixture()
def cli_store(tmp_path, monkeypatch):
    fresh = SecurityManager(tmp_path / "security.json")
    monkeypatch.setattr(cli_module, "security_manager", fresh)
    monkeypatch.setenv("MAYA_BIOMETRICS_STORE", str(tmp_path / "biometrics.json"))
    return fresh


def invoke(*args: str, input: str | None = None):
    return CliRunner().invoke(main, list(args), input=input)


# ── Config ────────────────────────────────────────────────────────────

def test_config_reads_settings_and_clamps(monkeypatch):
    monkeypatch.setattr(
        watchdog,
        "load_settings",
        lambda: {
            "security": {
                "watchdog": {
                    "idle_lock_minutes": 7,
                    "max_session_minutes": 30,
                    "voice_check_minutes": 20,
                    "check_seconds": 0.1,
                    "voice_seconds": 99,
                }
            }
        },
    )
    result = watchdog.watchdog_config()
    assert result["idle_lock_minutes"] == 7
    assert result["max_session_minutes"] == 30
    assert result["voice_check_minutes"] == 20
    assert result["check_seconds"] == 1
    assert result["voice_seconds"] == 30


def test_config_overrides_and_bad_values(monkeypatch):
    monkeypatch.setattr(watchdog, "load_settings", lambda: {})
    result = watchdog.watchdog_config(
        {
            "idle_lock_minutes": 0,
            "max_session_minutes": -5,
            "voice_check_minutes": "nan",
            "check_seconds": "x",
            "voice_seconds": 1,
        }
    )
    assert result["idle_lock_minutes"] == 0
    assert result["max_session_minutes"] == 0
    assert result["voice_check_minutes"] == 0
    assert result["check_seconds"] == 15
    assert result["voice_seconds"] == 2


# ── Idle detection ────────────────────────────────────────────────────

def test_idle_seconds_is_known_or_none():
    value = watchdog.idle_seconds()
    assert value is None or value >= 0


def test_idle_lock_triggers_and_alerts(manager):
    dog = SessionWatchdog(
        manager, cfg(), idle_provider=lambda: 301.0, clock=lambda: time.time()
    )
    result = dog.tick()
    assert result["action"] == "locked"
    assert result["reason"] == "idle"
    assert "5 min without input" in result["message"]
    manager.reload()
    assert manager.is_session_locked() is True
    alerts = manager.get_unauthorized_alerts()
    assert alerts and "Watchdog" in alerts[-1]["detail"]


def test_idle_below_limit_does_nothing(manager):
    dog = SessionWatchdog(
        manager, cfg(), idle_provider=lambda: 10.0, clock=lambda: time.time()
    )
    result = dog.tick()
    assert result["action"] == "ok"
    assert manager.is_session_locked() is False


def test_idle_zero_disables_the_check(manager):
    dog = SessionWatchdog(
        manager,
        cfg(idle_lock_minutes=0),
        idle_provider=lambda: 10**9,
        clock=lambda: time.time(),
    )
    assert dog.tick()["action"] == "ok"
    assert manager.is_session_locked() is False


def test_unknown_idle_never_locks(manager):
    dog = SessionWatchdog(
        manager, cfg(), idle_provider=lambda: None, clock=lambda: time.time()
    )
    assert dog.tick()["action"] == "ok"
    assert manager.is_session_locked() is False


def test_idle_available_flag(manager):
    assert SessionWatchdog(manager, cfg(idle_lock_minutes=0), idle_provider=lambda: None).idle_available() is True
    assert SessionWatchdog(manager, cfg(), idle_provider=lambda: None).idle_available() is False
    assert SessionWatchdog(manager, cfg(), idle_provider=lambda: 1.0).idle_available() is True


# ── Session expiry ────────────────────────────────────────────────────

def test_session_expiry_locks(manager):
    unlocked_at = manager.status()["last_unlock"]["time"]
    dog = SessionWatchdog(
        manager,
        cfg(idle_lock_minutes=0, max_session_minutes=5),
        idle_provider=lambda: 0.0,
        clock=lambda: unlocked_at + 301,
    )
    result = dog.tick()
    assert result["action"] == "locked"
    assert result["reason"] == "session"
    assert "session expired" in result["message"]
    manager.reload()
    assert manager.is_session_locked() is True


def test_session_not_expired_before_limit(manager):
    unlocked_at = manager.status()["last_unlock"]["time"]
    dog = SessionWatchdog(
        manager,
        cfg(idle_lock_minutes=0, max_session_minutes=5),
        idle_provider=lambda: 0.0,
        clock=lambda: unlocked_at + 299,
    )
    assert dog.tick()["action"] == "ok"
    assert manager.is_session_locked() is False


def test_session_expiry_disabled(manager):
    unlocked_at = manager.status()["last_unlock"]["time"]
    dog = SessionWatchdog(
        manager,
        cfg(idle_lock_minutes=0, max_session_minutes=0),
        idle_provider=lambda: 0.0,
        clock=lambda: unlocked_at + 10**6,
    )
    assert dog.tick()["action"] == "ok"


# ── No PIN / already locked ───────────────────────────────────────────

def test_no_pin_does_nothing(tmp_path):
    fresh = SecurityManager(tmp_path / "security.json")
    dog = SessionWatchdog(
        fresh, cfg(), idle_provider=lambda: 10**9, clock=lambda: time.time()
    )
    result = dog.tick()
    assert result["action"] == "idle"
    assert result["reason"] == "no_pin"
    assert fresh.is_locked() is False


def test_already_locked_does_nothing(manager):
    manager.lock()
    dog = SessionWatchdog(
        manager, cfg(), idle_provider=lambda: 10**9, clock=lambda: time.time()
    )
    result = dog.tick()
    assert result["action"] == "idle"
    assert result["reason"] == "already_locked"
    assert manager.get_unauthorized_alerts() == []


def test_tick_reloads_external_lock(manager, tmp_path):
    """A lock from another process is noticed on the next tick."""
    other = SecurityManager(tmp_path / "security.json")
    other.lock()
    dog = SessionWatchdog(
        manager, cfg(), idle_provider=lambda: 10**9, clock=lambda: time.time()
    )
    assert dog.tick()["reason"] == "already_locked"


# ── Voice re-check ────────────────────────────────────────────────────

def test_voice_check_runs_after_interval(manager, monkeypatch):
    monkeypatch.setattr(watchdog, "voice_ready", lambda: {"ok": True, "error": None})
    calls = []

    def provider(seconds):
        calls.append(seconds)
        return {"ok": True, "error": None}

    now = [1000.0]
    dog = SessionWatchdog(
        manager,
        cfg(idle_lock_minutes=0, voice_check_minutes=1),
        idle_provider=lambda: 0.0,
        voice_provider=provider,
        clock=lambda: now[0],
    )
    assert dog.tick()["action"] == "ok"  # starts the timer, no prompt
    assert calls == []

    now[0] += 61
    result = dog.tick()
    assert result["action"] == "voice_ok"
    assert calls == [5.0]
    assert manager.is_session_locked() is False


def test_voice_failure_locks_and_alerts(manager, monkeypatch):
    monkeypatch.setattr(watchdog, "voice_ready", lambda: {"ok": True, "error": None})
    now = [1000.0]
    dog = SessionWatchdog(
        manager,
        cfg(idle_lock_minutes=0, voice_check_minutes=1),
        idle_provider=lambda: 0.0,
        voice_provider=lambda seconds: {"ok": False, "error": "mismatch"},
        clock=lambda: now[0],
    )
    dog.tick()
    now[0] += 61
    result = dog.tick()
    assert result["action"] == "locked"
    assert result["reason"] == "voice"
    manager.reload()
    assert manager.is_session_locked() is True
    assert "voice re-check failed" in manager.get_unauthorized_alerts()[-1]["detail"]


def test_voice_exception_fails_closed(manager, monkeypatch):
    monkeypatch.setattr(watchdog, "voice_ready", lambda: {"ok": True, "error": None})
    now = [1000.0]

    def boom(seconds):
        raise RuntimeError("mic disconnected")

    dog = SessionWatchdog(
        manager,
        cfg(idle_lock_minutes=0, voice_check_minutes=1),
        idle_provider=lambda: 0.0,
        voice_provider=boom,
        clock=lambda: now[0],
    )
    dog.tick()
    now[0] += 61
    result = dog.tick()
    assert result["action"] == "locked"
    assert "mic disconnected" in result["message"]


def test_voice_skipped_when_not_enrolled(manager, monkeypatch):
    monkeypatch.setattr(watchdog, "voice_ready", lambda: {"ok": False, "error": "No voice password is set up."})
    now = [1000.0]
    dog = SessionWatchdog(
        manager,
        cfg(idle_lock_minutes=0, voice_check_minutes=1),
        idle_provider=lambda: 0.0,
        voice_provider=lambda seconds: pytest.fail("must not record without enrollment"),
        clock=lambda: now[0],
    )
    dog.tick()
    now[0] += 61
    result = dog.tick()
    assert result["action"] == "skipped"
    assert result["error"] == "No voice password is set up."
    assert manager.is_session_locked() is False


def test_voice_disabled_by_default(manager):
    now = [1000.0]
    dog = SessionWatchdog(
        manager,
        cfg(idle_lock_minutes=0),
        idle_provider=lambda: 0.0,
        voice_provider=lambda seconds: pytest.fail("voice must stay off"),
        clock=lambda: now[0],
    )
    dog.tick()
    now[0] += 10**6
    assert dog.tick()["action"] == "ok"


def test_voice_ready_reports_not_enrolled(tmp_path, monkeypatch):
    monkeypatch.setenv("MAYA_BIOMETRICS_STORE", str(tmp_path / "biometrics.json"))
    result = watchdog.voice_ready()
    assert result["ok"] is False
    assert result["code"] == "not_enrolled"


def test_summary_mentions_settings(manager):
    dog = SessionWatchdog(
        manager,
        cfg(idle_lock_minutes=5, max_session_minutes=30, voice_check_minutes=20, check_seconds=15),
    )
    text = dog.summary()
    assert "idle lock 5 min" in text
    assert "session 30 min" in text
    assert "voice every 20 min" in text
    assert "every 15s" in text


# ── CLI ───────────────────────────────────────────────────────────────

def test_cli_watchdog_once_without_pin(cli_store):
    result = invoke("security", "watchdog", "--once")
    assert result.exit_code == 0, result.output
    assert "No PIN set" in result.output


def test_cli_watchdog_blocked_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("security", "watchdog", "--once")
    assert result.exit_code != 0
    assert "Maya is locked" in result.output


def test_cli_watchdog_once_locks_on_idle(cli_store, monkeypatch):
    cli_store.set_pin(PIN)
    cli_store.verify_pin(PIN)
    monkeypatch.setattr(watchdog, "idle_seconds", lambda: 9999.0)

    result = invoke(
        "security", "watchdog", "--once", "--idle-minutes", "1"
    )
    assert result.exit_code == 0, result.output
    assert "locked after 1 min without input" in result.output

    cli_store.reload()
    assert cli_store.is_session_locked() is True
    assert "Watchdog" in cli_store.get_unauthorized_alerts()[-1]["detail"]


def test_cli_watchdog_once_reports_no_action(cli_store, monkeypatch):
    cli_store.set_pin(PIN)
    cli_store.verify_pin(PIN)
    monkeypatch.setattr(watchdog, "idle_seconds", lambda: 1.0)

    result = invoke("security", "watchdog", "--once", "--idle-minutes", "5")
    assert result.exit_code == 0, result.output
    assert "No action needed" in result.output
    cli_store.reload()
    assert cli_store.is_session_locked() is False
