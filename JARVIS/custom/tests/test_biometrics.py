"""Biometrics tests — no camera, no mic, no real model."""

import json

import pytest
from click.testing import CliRunner

from custom.cli import main
from custom.tools import biometrics

PHRASE = "maya open the door"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Isolated store with the speaker factor enabled and available."""
    path = tmp_path / "biometrics.json"
    monkeypatch.setenv(biometrics.ENV_BIOMETRICS_STORE, str(path))
    monkeypatch.delenv(biometrics.ENV_MAYA_EXE, raising=False)
    monkeypatch.setattr(biometrics, "speaker_available", lambda: True)
    monkeypatch.setattr(biometrics, "require_speaker", lambda: True)
    monkeypatch.setattr(biometrics, "speaker_threshold", lambda: 0.65)
    return path


@pytest.fixture()
def enrolled(store, monkeypatch):
    monkeypatch.setattr(biometrics, "require_speaker", lambda: True)
    result = biometrics.voice_enroll(
        [PHRASE, PHRASE, PHRASE],
        [[1.0, 0.0, 0.0], [0.95, 0.05, 0.0], [1.0, 0.02, 0.0]],
    )
    assert result["ok"], result
    return store


# ── Face helper ───────────────────────────────────────────────────────

class FakeRun:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_run(monkeypatch, result):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return result

    monkeypatch.setattr(biometrics.subprocess, "run", fake_run)
    monkeypatch.setattr(biometrics, "maya_exe", lambda: biometrics.DEFAULT_EXE)
    return calls


def test_face_check_available(monkeypatch):
    _patch_run(monkeypatch, FakeRun(0, "AVAILABILITY=Available\n"))
    assert biometrics.face_status(force=True)["available"] is True


def test_face_check_unavailable(monkeypatch):
    _patch_run(monkeypatch, FakeRun(2, "AVAILABILITY=NotConfiguredForUser\n"))
    result = biometrics.face_status(force=True)
    assert result["available"] is False
    assert result["code"] == "unavailable"


def test_face_check_old_helper_is_not_mistaken_for_success(monkeypatch):
    _patch_run(monkeypatch, FakeRun(0, "launcher started\n"))
    result = biometrics.face_status(force=True)
    assert result["available"] is False
    assert result["code"] == "helper_outdated"


def test_face_verify_success(monkeypatch):
    calls = _patch_run(monkeypatch, FakeRun(0, "RESULT=Verified\n"))
    result = biometrics.face_verify(30)
    assert result["ok"] is True
    assert any("--face-auth" in part for part in calls[0])
    assert "30" in calls[0]


def test_face_verify_cancelled(monkeypatch):
    _patch_run(monkeypatch, FakeRun(2, "RESULT=Canceled\n"))
    result = biometrics.face_verify(30)
    assert result["ok"] is False
    assert result["code"] == "not_verified"


def test_face_verify_timeout_code(monkeypatch):
    _patch_run(monkeypatch, FakeRun(4, "ERROR=timeout\n"))
    assert biometrics.face_verify(30)["code"] == "timeout"


def test_face_helper_missing(monkeypatch, tmp_path):
    monkeypatch.setenv(biometrics.ENV_MAYA_EXE, str(tmp_path / "nope.exe"))
    monkeypatch.setattr(biometrics, "DEFAULT_EXE", tmp_path / "nope.exe")
    result = biometrics.face_status(force=True)
    assert result["available"] is False
    assert result["code"] == "helper_missing"


def test_face_status_is_cached(monkeypatch):
    calls = {"n": 0}

    def fake_run(mode, timeout):
        calls["n"] += 1
        return {"ok": True, "code": "available", "error": None}

    monkeypatch.setattr(biometrics, "_run_face", fake_run)
    biometrics._face_cache["value"] = None
    biometrics.face_status(force=True)
    biometrics.face_status()
    assert calls["n"] == 1


# ── Phrase helpers ───────────────────────────────────────────────────

def test_normalize_phrase():
    assert biometrics.normalize_phrase("  Maya,  OPEN the door!! ") == "maya open the door"


def test_phrase_problem_rejects_weak_phrases():
    assert biometrics.phrase_problem("maya") is not None
    assert biometrics.phrase_problem("open the door") is None


# ── Voice enrollment / verification ─────────────────────────────────

def test_enroll_stores_hash_and_centroid(enrolled):
    data = json.loads(enrolled.read_text(encoding="utf-8"))
    voice = data["voice"]
    assert voice["algo"] == "pbkdf2_sha256"
    assert len(voice["hashes"]) == 1          # identical transcript deduped
    assert voice["speaker"]["dim"] == 3
    assert PHRASE not in enrolled.read_text(encoding="utf-8")


def test_correct_phrase_and_voice_verifies(enrolled):
    result = biometrics.voice_verify(PHRASE, [1.0, 0.0, 0.0])
    assert result["ok"] is True
    assert result["speaker_score"] > 0.65


def test_wrong_phrase_fails(enrolled):
    result = biometrics.voice_verify("maya close the window", [1.0, 0.0, 0.0])
    assert result["ok"] is False
    assert result["passphrase_ok"] is False


def test_wrong_voice_fails(enrolled):
    result = biometrics.voice_verify(PHRASE, [0.0, 1.0, 0.0])
    assert result["ok"] is False
    assert result["passphrase_ok"] is True
    assert result["speaker_score"] < 0.65


def test_missing_voiceprint_fails_when_required(enrolled):
    result = biometrics.voice_verify(PHRASE, None)
    assert result["ok"] is False
    assert result["passphrase_ok"] is True


def test_diagnostic_phrase_only_mode(enrolled):
    result = biometrics.voice_verify(PHRASE, None, enforce_speaker=False)
    assert result["ok"] is True


def test_disabled_speaker_ignores_a_bad_vector(enrolled, monkeypatch):
    monkeypatch.setattr(biometrics, "require_speaker", lambda: False)
    result = biometrics.voice_verify(PHRASE, [0.0, 1.0, 0.0])
    assert result["ok"] is True


def test_speaker_disabled_allows_phrase_only(store, monkeypatch):
    monkeypatch.setattr(biometrics, "require_speaker", lambda: False)
    result = biometrics.voice_enroll([PHRASE, PHRASE], [])
    assert result["ok"] is True
    verified = biometrics.voice_verify(PHRASE)
    assert verified["ok"] is True


def test_enroll_rejects_different_phrases(store):
    result = biometrics.voice_enroll(
        [PHRASE, "completely different sentence"],
        [[1.0, 0.0], [1.0, 0.0]],
    )
    assert result["ok"] is False
    assert result["code"] == "mismatch"


def test_enroll_needs_two_samples(store):
    result = biometrics.voice_enroll([PHRASE], [[1.0, 0.0]])
    assert result["ok"] is False
    assert result["code"] == "few_samples"


def test_enroll_requires_vectors_when_speaker_on(store):
    result = biometrics.voice_enroll([PHRASE, PHRASE], [])
    assert result["ok"] is False
    assert result["code"] == "speaker_missing"


def test_failed_attempts_lock_out(enrolled):
    for _ in range(biometrics._max_attempts()):
        biometrics.voice_verify("wrong phrase", [1.0, 0.0, 0.0])
    blocked = biometrics.voice_verify(PHRASE, [1.0, 0.0, 0.0])
    assert blocked["ok"] is False
    assert blocked["code"] == "locked"
    assert blocked["remaining"] > 0


def test_success_resets_failure_count(enrolled):
    biometrics.voice_verify("wrong", [1.0, 0.0, 0.0])
    biometrics.voice_verify(PHRASE, [1.0, 0.0, 0.0])
    assert biometrics.voice_status()["attempts_left"] == biometrics._max_attempts()


def test_voice_reset(enrolled):
    assert biometrics.voice_reset()["ok"] is True
    status = biometrics.voice_status()
    assert status["enrolled"] is False
    assert status["speaker"] is False


# ── CLI ──────────────────────────────────────────────────────────────

def test_cli_status_without_enrollment(store):
    result = CliRunner().invoke(main, ["biometrics", "status", "--no-face"])
    assert result.exit_code == 0, result.output
    assert "voice enrolled: False" in result.output
    assert "speaker model: found" in result.output


def test_cli_face_check(monkeypatch, store):
    monkeypatch.setattr(
        biometrics, "face_status", lambda force=False: {"available": True, "code": "available"}
    )
    result = CliRunner().invoke(main, ["biometrics", "face-check"])
    assert result.exit_code == 0, result.output
    assert "available" in result.output


def test_cli_voice_verify_diagnostic(enrolled):
    result = CliRunner().invoke(main, ["biometrics", "voice-verify", "--text", PHRASE])
    assert result.exit_code == 0, result.output
    assert "Voice verified" in result.output


def test_cli_voice_verify_wrong_text(enrolled):
    result = CliRunner().invoke(
        main, ["biometrics", "voice-verify", "--text", "wrong words", "--explain"]
    )
    assert result.exit_code == 0, result.output
    assert "not verified" in result.output
    assert "phrase match: False" in result.output


def test_cli_voice_enroll_from_wavs(store, tmp_path, monkeypatch):
    first = tmp_path / "a.wav"
    second = tmp_path / "b.wav"
    first.write_bytes(b"RIFF")
    second.write_bytes(b"RIFF")
    monkeypatch.setattr(biometrics, "transcribe_wav", lambda path: PHRASE)
    monkeypatch.setattr(biometrics, "speaker_vector", lambda path: [1.0, 0.0, 0.0])

    result = CliRunner().invoke(
        main,
        ["biometrics", "voice-enroll", "--wav", str(first), "--wav", str(second)],
    )
    assert result.exit_code == 0, result.output
    assert "Voice enrolled" in result.output
    assert biometrics.voice_status()["enrolled"] is True


def test_cli_voice_reset(enrolled):
    result = CliRunner().invoke(main, ["biometrics", "voice-reset", "--yes"])
    assert result.exit_code == 0, result.output
    assert "deleted" in result.output.lower()
