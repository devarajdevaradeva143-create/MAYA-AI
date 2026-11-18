"""Security tests — session lock/unlock and CLI integration.

Every test uses a throw-away ``security.json``; the real offline memory is
never touched.
"""

import json
import time

import pytest
from click.testing import CliRunner

from custom import cli as cli_module
from custom.cli import main
from custom.tools import biometrics
from custom.tools.security import SecurityManager

PIN = "1234"


@pytest.fixture()
def store_path(tmp_path):
    return tmp_path / "security.json"


@pytest.fixture()
def manager(store_path):
    return SecurityManager(store_path)


@pytest.fixture()
def locked(manager):
    manager.set_pin(PIN)
    return manager


@pytest.fixture()
def cli_store(store_path, tmp_path, monkeypatch):
    """Point the CLI at an isolated store and return its manager."""
    fresh = SecurityManager(store_path)
    monkeypatch.setattr(cli_module, "security_manager", fresh)
    monkeypatch.setenv("MAYA_CHAT_HISTORY", str(tmp_path / "chat.json"))
    monkeypatch.setenv("MAYA_BIOMETRICS_STORE", str(tmp_path / "biometrics.json"))
    monkeypatch.setenv("MAYA_ASSISTANT_STORE", str(tmp_path / "assistant.json"))
    return fresh


def invoke(*args: str, input: str | None = None):
    return CliRunner().invoke(main, list(args), input=input)


# ── Session state ─────────────────────────────────────────────────────

def test_no_pin_means_never_locked(manager):
    assert manager.is_locked() is False
    assert manager.is_session_locked() is False


def test_setting_pin_locks_the_session(locked):
    assert locked.is_locked() is True
    assert locked.is_session_locked() is True
    assert locked.status()["last_unlock"] is None


def test_correct_pin_unlocks_and_records_method(locked):
    message = locked.verify_pin(PIN)
    assert "Unlocked" in message
    assert locked.is_session_locked() is False
    last = locked.status()["last_unlock"]
    assert last["method"] == "pin"
    assert last["time"] > 0


def test_wrong_pin_keeps_session_locked(locked):
    message = locked.verify_pin("9999")
    assert "Wrong PIN" in message
    assert locked.is_session_locked() is True


def test_lock_relocks_after_unlock(locked):
    locked.verify_pin(PIN)
    assert "locked" in locked.lock().lower()
    assert locked.is_session_locked() is True


def test_lock_without_pin_is_refused(manager):
    message = manager.lock()
    assert "No PIN" in message
    assert manager.is_session_locked() is False


def test_unlock_without_pin_is_refused(manager):
    message = manager.unlock("face")
    assert "No PIN" in message


def test_session_state_survives_reload(locked, store_path):
    locked.verify_pin(PIN)
    fresh = SecurityManager(store_path)
    assert fresh.is_session_locked() is False
    assert fresh.status()["last_unlock"]["method"] == "pin"

    fresh.lock()
    again = SecurityManager(store_path)
    assert again.is_session_locked() is True


def test_backup_code_unlocks_the_session(locked):
    locked.set_backup_unlock_code("backup-123")
    message = locked.verify_backup_unlock("backup-123")
    assert "successful" in message.lower()
    assert locked.is_session_locked() is False
    assert locked.status()["last_unlock"]["method"] == "backup_code"


def test_explicit_unlock_marks_method(locked):
    message = locked.unlock("face")
    assert "via face" in message
    assert locked.is_session_locked() is False
    assert locked.status()["last_unlock"]["method"] == "face"


# ── Failure counters / lockout ────────────────────────────────────────

def test_failed_attempts_survive_a_restart(locked, store_path):
    locked.verify_pin("0001")
    locked.verify_pin("0002")
    fresh = SecurityManager(store_path)
    assert fresh.status()["failed_attempts"] == 2

    # Three more failures reach the 5-attempt lockout — proof the count
    # was not silently reset to zero by the new process.
    for _ in range(3):
        fresh.verify_pin("0003")
    assert fresh.status()["locked_out"] is True


def test_expired_lockout_resets_the_counter(locked):
    locked.verify_pin("0001")
    locked._data["failed_attempts"] = 5
    locked._data["lockout_until"] = time.time() - 1
    locked._save()

    message = locked.verify_pin("0002")
    assert "4 attempt(s) remaining" in message


def test_legacy_store_without_session_key_is_locked(locked, store_path):
    data = json.loads(store_path.read_text(encoding="utf-8"))
    data.pop("session_locked", None)
    data.pop("last_unlock", None)
    store_path.write_text(json.dumps(data), encoding="utf-8")

    fresh = SecurityManager(store_path)
    assert fresh.is_session_locked() is True


def test_status_exposes_session_fields(locked):
    st = locked.status()
    assert st["pin_set"] is True
    assert st["locked"] is True
    assert st["session_locked"] is True
    assert st["last_unlock"] is None
    # No secret material in the public status.
    assert "pin_hash" not in st
    assert "salt" not in st


# ── CLI: lock / unlock ────────────────────────────────────────────────

def test_cli_lock_then_pin_unlock(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("lock")
    assert result.exit_code == 0, result.output
    assert "Maya is locked" in result.output

    result = invoke("security", "status")
    assert "Session locked: True" in result.output

    result = invoke("security", "unlock", PIN)
    assert result.exit_code == 0, result.output
    assert "Unlocked" in result.output
    assert cli_store.is_session_locked() is False


def test_cli_lock_is_not_an_unauthorized_alert(cli_store):
    cli_store.set_pin(PIN)
    before = len(cli_store.get_unauthorized_alerts())
    invoke("lock")
    assert len(cli_store.get_unauthorized_alerts()) == before


def test_cli_unlock_requires_a_method(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("security", "unlock")
    assert result.exit_code != 0
    assert "Give a PIN" in result.output


def test_cli_unlock_rejects_pin_and_biometrics_together(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("security", "unlock", PIN, "--face")
    assert result.exit_code != 0
    assert "not both" in result.output


def test_cli_unlock_reports_already_open(cli_store, monkeypatch):
    cli_store.set_pin(PIN)
    cli_store.verify_pin(PIN)

    def boom(timeout):
        raise AssertionError("face prompt must not open when already unlocked")

    monkeypatch.setattr(biometrics, "face_verify", boom)
    result = invoke("security", "unlock", "--face")
    assert result.exit_code == 0, result.output
    assert "already unlocked" in result.output


def test_cli_unlock_with_face(cli_store, monkeypatch):
    cli_store.set_pin(PIN)
    monkeypatch.setattr(
        biometrics, "face_verify", lambda timeout: {"ok": True, "code": "verified", "error": None}
    )
    result = invoke("security", "unlock", "--face")
    assert result.exit_code == 0, result.output
    assert "Unlocked via face" in result.output
    assert cli_store.is_session_locked() is False


def test_cli_failed_face_unlock_records_alert(cli_store, monkeypatch):
    cli_store.set_pin(PIN)
    monkeypatch.setattr(
        biometrics,
        "face_verify",
        lambda timeout: {"ok": False, "code": "not_verified", "error": "no face"},
    )
    result = invoke("security", "unlock", "--face")
    assert result.exit_code != 0
    assert "Face not verified" in result.output
    assert cli_store.is_session_locked() is True
    alerts = cli_store.get_unauthorized_alerts()
    assert alerts and alerts[-1]["detail"] == "Face unlock failed"


def test_cli_unlock_with_voice(cli_store, monkeypatch):
    cli_store.set_pin(PIN)
    monkeypatch.setattr(
        cli_module, "_voice_attempt", lambda **kwargs: {"ok": True, "speaker_score": 0.9}
    )
    result = invoke("security", "unlock", "--voice")
    assert result.exit_code == 0, result.output
    assert "Unlocked via voice" in result.output
    assert cli_store.is_session_locked() is False


def test_cli_failed_voice_unlock_records_alert(cli_store, monkeypatch):
    cli_store.set_pin(PIN)
    monkeypatch.setattr(
        cli_module,
        "_voice_attempt",
        lambda **kwargs: {"ok": False, "error": "mismatch"},
    )
    result = invoke("security", "unlock", "--voice")
    assert result.exit_code != 0
    assert "Voice not verified" in result.output
    assert cli_store.get_unauthorized_alerts()[-1]["detail"] == "Voice unlock failed"


# ── CLI: chat guard ───────────────────────────────────────────────────

def test_cli_chat_is_blocked_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("chat", input="/quit\n")
    assert result.exit_code != 0
    assert "Maya is locked" in result.output
    assert "maya security unlock --face" in result.output


def test_cli_chat_runs_after_unlock(cli_store, monkeypatch):
    cli_store.set_pin(PIN)
    cli_store.verify_pin(PIN)
    monkeypatch.setattr(cli_module.engine_bridge, "chat", lambda messages: "hello")
    result = invoke("chat", input="/quit\n")
    assert result.exit_code == 0, result.output
    assert "Maya is locked" not in result.output
    assert "Maya AI Chat" in result.output


# ── CLI: biometrics --unlock ──────────────────────────────────────────

def test_cli_face_verify_unlock_flag(cli_store, monkeypatch):
    cli_store.set_pin(PIN)
    monkeypatch.setattr(
        biometrics, "face_verify", lambda timeout: {"ok": True, "code": "verified", "error": None}
    )
    result = invoke("biometrics", "face-verify", "--unlock")
    assert result.exit_code == 0, result.output
    assert "Unlocked via face" in result.output
    assert cli_store.is_session_locked() is False


def test_cli_voice_verify_unlock_flag(cli_store, monkeypatch):
    cli_store.set_pin(PIN)
    monkeypatch.setattr(
        cli_module, "_voice_attempt", lambda **kwargs: {"ok": True, "speaker_score": 0.9}
    )
    result = invoke("biometrics", "voice-verify", "--unlock")
    assert result.exit_code == 0, result.output
    assert "Unlocked via voice" in result.output
    assert cli_store.is_session_locked() is False


def test_cli_voice_text_cannot_unlock(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("biometrics", "voice-verify", "--text", "maya open the door", "--unlock")
    assert result.exit_code != 0
    assert "cannot unlock" in result.output
    assert cli_store.is_session_locked() is True


def test_cli_failed_biometric_unlock_records_alert(cli_store, monkeypatch):
    cli_store.set_pin(PIN)
    monkeypatch.setattr(
        cli_module, "_voice_attempt", lambda **kwargs: {"ok": False, "error": "mismatch"}
    )
    result = invoke("biometrics", "voice-verify", "--unlock")
    assert result.exit_code == 0, result.output  # verify itself still exits 0
    assert "Voice not verified" in result.output
    assert cli_store.is_session_locked() is True
    assert cli_store.get_unauthorized_alerts()[-1]["detail"] == "Voice unlock failed"


# ── CLI: full command guard ───────────────────────────────────────────

def test_cli_todo_blocked_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("todo", "add", "secret task")
    assert result.exit_code != 0
    assert "Maya is locked" in result.output
    assert "maya security unlock --face" in result.output


def test_cli_monitor_blocked_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("monitor", "status")
    assert result.exit_code != 0
    assert "Maya is locked" in result.output


def test_cli_knowledge_blocked_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("knowledge", "search", "anything")
    assert result.exit_code != 0
    assert "Maya is locked" in result.output


def test_cli_devices_blocked_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("devices", "list")
    assert result.exit_code != 0
    assert "Maya is locked" in result.output


def test_cli_config_blocked_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("config")
    assert result.exit_code != 0
    assert "Maya is locked" in result.output


def test_cli_version_allowed_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("version")
    assert result.exit_code == 0, result.output
    assert "Maya AI version" in result.output


def test_cli_lock_allowed_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("lock")
    assert result.exit_code == 0, result.output
    assert "Maya is locked" in result.output


def test_cli_security_status_allowed_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("security", "status")
    assert result.exit_code == 0, result.output
    assert "Session locked: True" in result.output


def test_cli_security_set_pin_blocked_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("security", "set-pin", "5678", "--old-pin", PIN)
    assert result.exit_code != 0
    assert "Maya is locked" in result.output
    assert cli_store.verify_pin(PIN) == "Unlocked. Maya is ready."


def test_cli_security_backup_code_blocked_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("security", "backup-code", "attacker-code")
    assert result.exit_code != 0
    assert "Maya is locked" in result.output
    assert cli_store.status()["backup_code_set"] is False


def test_cli_security_alerts_blocked_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("security", "alerts")
    assert result.exit_code != 0
    assert "Maya is locked" in result.output


def test_cli_biometrics_status_allowed_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("biometrics", "status", "--no-face")
    assert result.exit_code == 0, result.output
    assert "Biometrics Status" in result.output


def test_cli_biometrics_voice_enroll_blocked_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("biometrics", "voice-enroll", "--wav", "a.wav")
    assert result.exit_code != 0
    assert "Maya is locked" in result.output


def test_cli_biometrics_voice_reset_blocked_while_locked(cli_store):
    cli_store.set_pin(PIN)
    result = invoke("biometrics", "voice-reset", "--yes")
    assert result.exit_code != 0
    assert "Maya is locked" in result.output


def test_cli_help_still_works_while_locked(cli_store):
    cli_store.set_pin(PIN)
    for args in (
        ("--help",),
        ("todo", "--help"),
        ("biometrics", "voice-enroll", "--help"),
    ):
        result = invoke(*args)
        assert result.exit_code == 0, (args, result.output)
        assert "Maya is locked" not in result.output


def test_cli_help_after_separator_does_not_bypass_lock(cli_store):
    """`todo add -- --help` must not sneak a write past the guard."""
    cli_store.set_pin(PIN)
    result = invoke("todo", "add", "--", "--help")
    assert result.exit_code != 0
    assert "Maya is locked" in result.output


def test_cli_help_flag_on_a_command_does_not_execute_it(cli_store):
    """`todo add -h` shows help and never adds a to-do while locked."""
    cli_store.set_pin(PIN)
    result = invoke("todo", "add", "-h")
    assert result.exit_code == 0, result.output
    assert "Add a to-do item" in result.output

    cli_store.verify_pin(PIN)
    listed = invoke("todo", "list")
    assert "-h" not in listed.output


def test_cli_blocked_commands_are_not_alerts(cli_store):
    cli_store.set_pin(PIN)
    invoke("todo", "list")
    invoke("config")
    assert cli_store.status()["unauthorized_alerts"] == 0


def test_cli_unlock_restores_blocked_commands(cli_store):
    cli_store.set_pin(PIN)
    blocked = invoke("todo", "add", "secret task")
    assert blocked.exit_code != 0

    unlock = invoke("security", "unlock", PIN)
    assert unlock.exit_code == 0, unlock.output

    added = invoke("todo", "add", "visible task")
    assert added.exit_code == 0, added.output
    listed = invoke("todo", "list")
    assert "visible task" in listed.output
    assert "secret task" not in listed.output

