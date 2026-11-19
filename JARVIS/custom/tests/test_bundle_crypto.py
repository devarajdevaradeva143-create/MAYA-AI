"""AES-GCM bundle envelope + anti-replay tests."""

from __future__ import annotations

import base64
import json

import pytest

from custom.tools import bundle_crypto


@pytest.fixture(autouse=True)
def seq_path(tmp_path, monkeypatch):
    path = tmp_path / "bundle_seq.json"
    monkeypatch.setenv("MAYA_BUNDLE_SEQ", str(path))
    return path


def test_encrypt_decrypt_roundtrip() -> None:
    plaintext = b'{"format":"maya-device-bundle","version":1,"files":[]}'
    env = bundle_crypto.encrypt_envelope(plaintext, "secret-code", seq=7)
    assert env["format"] == bundle_crypto.FORMAT
    assert env["enc"]["seq"] == 7
    assert bundle_crypto.decrypt_envelope(env, "secret-code") == plaintext


def test_wrong_code_fails() -> None:
    env = bundle_crypto.encrypt_envelope(b"hello", "right", seq=1)
    with pytest.raises(ValueError):
        bundle_crypto.decrypt_envelope(env, "wrong", allow_replay=True)


def test_tampered_payload_fails() -> None:
    env = bundle_crypto.encrypt_envelope(b"hello", "code", seq=1)
    env["payload"] = base64.b64encode(b"tampered").decode("ascii")
    with pytest.raises(ValueError):
        bundle_crypto.decrypt_envelope(env, "code", allow_replay=True)


def test_replay_rejected_then_commit_allows() -> None:
    env = bundle_crypto.encrypt_envelope(b"hello", "code", seq=5)
    assert bundle_crypto.decrypt_envelope(env, "code") == b"hello"
    bundle_crypto.commit_sequence(5)
    # Same seq again is a replay.
    with pytest.raises(ValueError, match="replay"):
        bundle_crypto.decrypt_envelope(env, "code")
    # allow_replay bypasses the check.
    assert bundle_crypto.decrypt_envelope(env, "code", allow_replay=True) == b"hello"
    # Newer seq is accepted.
    newer = bundle_crypto.encrypt_envelope(b"next", "code", seq=6)
    assert bundle_crypto.decrypt_envelope(newer, "code") == b"next"


def test_is_envelope() -> None:
    env = bundle_crypto.encrypt_envelope(b"x", "code", seq=1)
    assert bundle_crypto.is_envelope(json.dumps(env).encode()) is True
    assert bundle_crypto.is_envelope(b"plain json") is False
