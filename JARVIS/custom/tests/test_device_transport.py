"""LAN transport smoke tests."""

from __future__ import annotations

import threading

import pytest

from custom.tools import devices, transport


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    store = tmp_path / "devices.json"
    nonces = tmp_path / "nonces.json"
    monkeypatch.setenv("MAYA_DEVICES_STORE", str(store))
    monkeypatch.setenv("MAYA_BUNDLE_NONCES", str(nonces))
    return tmp_path


def test_roundtrip_and_replay(isolated_store, tmp_path) -> None:
    code = "secretcode1234567890"
    devices.pair_device("phone", code)
    src = tmp_path / "src.txt"
    src.write_text("hello maya", encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    exp = devices.export_bundle("phone", code, [str(src)], str(bundle))
    assert exp["ok"]

    dest = tmp_path / "dest"
    dest.mkdir()
    box = {}

    def worker():
        box["r"] = transport.receive_once(code, str(dest), host="127.0.0.1", port=8791, timeout=30, allow_public=True)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    import time

    time.sleep(0.5)
    send = transport.send_bundle(str(bundle), "127.0.0.1", port=8791, timeout=30)
    t.join(timeout=30)
    assert send["ok"]
    assert box["r"]["ok"]
    assert (dest / "src.txt").read_text() == "hello maya"

    # replay rejected
    dest2 = tmp_path / "dest2"
    dest2.mkdir()
    replay = devices.import_bundle(str(bundle), str(dest2), code, overwrite=True, allow_replay=False)
    assert replay.get("code") == "replay"


def test_is_private_ip() -> None:
    assert transport.is_private_ip("127.0.0.1") is True
    assert transport.is_private_ip("192.168.1.5") is True
    assert transport.is_private_ip("8.8.8.8") is False


def test_old_bundle_without_nonce_imports_twice(isolated_store, tmp_path) -> None:
    import base64
    import json
    import secrets

    code = "secretcode1234567890"
    devices.pair_device("phone", code)
    record = devices._device_record("phone")
    src = tmp_path / "src.txt"
    src.write_text("hi", encoding="utf-8")
    raw = src.read_bytes()
    kdf_salt = secrets.token_bytes(16)
    fields = {
        "format": devices.BUNDLE_FORMAT,
        "version": devices.BUNDLE_VERSION,
        "device": record["name"],
        "created": int(__import__("time").time()),
        "kdf": {
            "algo": "pbkdf2_sha256",
            "iterations": devices.BUNDLE_ITERATIONS,
            "salt": kdf_salt.hex(),
        },
        "files": [
            {
                "path": "src.txt",
                "size": len(raw),
                "sha256": __import__("hashlib").sha256(raw).hexdigest(),
                "data": base64.b64encode(raw).decode("ascii"),
            }
        ],
    }
    key = devices._bundle_key(code, kdf_salt, devices.BUNDLE_ITERATIONS)
    fields["hmac"] = devices._sign_bundle(fields, key)
    bundle = tmp_path / "old_bundle.json"
    bundle.write_text(json.dumps(fields), encoding="utf-8")

    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()
    r1 = devices.import_bundle(str(bundle), str(d1), code)
    r2 = devices.import_bundle(str(bundle), str(d2), code)
    assert r1["ok"] and r2["ok"], (r1, r2)
