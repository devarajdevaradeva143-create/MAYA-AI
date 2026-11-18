"""Multi-device tests — pairing registry and HMAC-signed sync bundles.

Every test uses a throw-away ``devices.json`` under ``tmp_path``; the real
offline memory is never touched and nothing goes over the network.
"""

import base64
import json
import os
import subprocess

import pytest
from click.testing import CliRunner

from custom import cli as cli_module
from custom.cli import main
from custom.tools import devices
from custom.tools.security import SecurityManager

CODE = "super-secret-pairing-code"


@pytest.fixture()
def store_path(tmp_path, monkeypatch):
    path = tmp_path / "memory" / "offline" / "devices.json"
    monkeypatch.setenv("MAYA_DEVICES_STORE", str(path))
    return path


@pytest.fixture()
def paired(store_path):
    result = devices.pair_device("phone", CODE)
    assert result["ok"] is True
    return result


@pytest.fixture()
def cli_store(store_path, tmp_path, monkeypatch):
    """Point the CLI at isolated stores and make sure the session is unlocked."""
    monkeypatch.setattr(
        cli_module, "security_manager", SecurityManager(tmp_path / "security.json")
    )
    monkeypatch.setenv("MAYA_CHAT_HISTORY", str(tmp_path / "chat.json"))
    monkeypatch.setenv("MAYA_BIOMETRICS_STORE", str(tmp_path / "biometrics.json"))
    monkeypatch.setenv("MAYA_ASSISTANT_STORE", str(tmp_path / "assistant.json"))
    return store_path


def invoke(*args: str, input: str | None = None):
    return CliRunner().invoke(main, list(args), input=input)


def write_bundle(path, bundle):
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")


def read_bundle(path):
    return json.loads(path.read_text(encoding="utf-8"))


def resign(bundle, code=CODE):
    """Re-sign a mutated bundle so tests reach the check they target."""
    key = devices._bundle_key(
        code, bytes.fromhex(bundle["kdf"]["salt"]), bundle["kdf"]["iterations"]
    )
    bundle["hmac"] = devices._sign_bundle(bundle, key)
    return bundle


# ── Pairing registry ──────────────────────────────────────────────────────

def test_pair_generates_code_and_stores_only_hash(store_path):
    result = devices.pair_device("  Phone  ")
    assert result["ok"] is True
    assert result["name"] == "phone"
    assert result["generated"] is True
    assert len(result["code"]) == 32

    raw = store_path.read_text(encoding="utf-8")
    record = json.loads(raw)["devices"]["phone"]
    assert result["code"] not in raw
    assert record["code_hash"] != result["code"]
    assert record["code_salt"]
    assert record["code_algo"] == "pbkdf2_sha256"


def test_pair_with_explicit_code_does_not_echo_it(paired):
    assert paired["generated"] is False
    assert "code" not in paired
    assert paired["id"]


def test_pair_strips_whitespace_code(store_path):
    result = devices.pair_device("phone", f"  {CODE}  ")
    assert result["ok"] is True
    assert devices.verify_pair_code("phone", CODE) is True


def test_pair_rejects_whitespace_only_code(store_path):
    result = devices.pair_device("phone", " " * 20)
    assert result["ok"] is False
    assert result["code"] == "weak_code"


def test_pair_rejects_duplicate(paired):
    again = devices.pair_device("phone", "another-long-code")
    assert again["ok"] is False
    assert again["code"] == "already_paired"


@pytest.mark.parametrize("name", ["", "   ", "phone/../x", "phone name", "-bad", "x" * 33])
def test_pair_rejects_bad_names(store_path, name):
    result = devices.pair_device(name, CODE)
    assert result["ok"] is False
    assert result["code"] == "bad_name"


def test_pair_rejects_short_code(store_path):
    result = devices.pair_device("phone", "short")
    assert result["ok"] is False
    assert result["code"] == "weak_code"


def test_verify_pair_code(paired):
    assert devices.verify_pair_code("phone", CODE) is True
    assert devices.verify_pair_code("phone", "wrong-code") is False
    assert devices.verify_pair_code("unknown", CODE) is False


def test_verify_pair_code_survives_corrupt_salt(store_path, paired):
    data = json.loads(store_path.read_text(encoding="utf-8"))
    data["devices"]["phone"]["code_salt"] = "not-hex"
    write_bundle(store_path, data)
    assert devices.verify_pair_code("phone", CODE) is False


def test_list_paired_devices_hides_secrets(paired):
    listed = devices.list_paired_devices()
    assert [item["name"] for item in listed] == ["phone"]
    assert "code_hash" not in listed[0]
    assert "code_salt" not in listed[0]


def test_revoke_removes_device(paired):
    result = devices.revoke_device("phone")
    assert result["ok"] is True
    assert devices.list_paired_devices() == []
    assert devices.verify_pair_code("phone", CODE) is False
    assert devices.revoke_device("phone")["code"] == "not_paired"


def test_default_store_path_follows_offline_memory(tmp_path, monkeypatch):
    monkeypatch.delenv("MAYA_DEVICES_STORE", raising=False)
    monkeypatch.setattr(
        devices, "load_settings", lambda: {"memory": {"offline": str(tmp_path / "offline")}}
    )
    assert devices._devices_store_path() == tmp_path / "offline" / "devices.json"


def test_corrupt_store_is_preserved(store_path):
    store_path.parent.mkdir(parents=True)
    store_path.write_text("{not valid json", encoding="utf-8")
    assert devices.list_paired_devices() == []
    backups = list(store_path.parent.glob("devices.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{not valid json"


# ── Export ────────────────────────────────────────────────────────────────

def test_export_single_file(store_path, paired, tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("hello maya", encoding="utf-8")
    out = tmp_path / "bundle.json"

    result = devices.export_bundle("phone", CODE, [str(source)], str(out))
    assert result["ok"] is True
    assert result["files"] == 1
    assert result["bytes"] == len(b"hello maya")
    assert out.is_file()

    bundle = read_bundle(out)
    assert bundle["format"] == devices.BUNDLE_FORMAT
    assert bundle["version"] == devices.BUNDLE_VERSION
    assert bundle["device"] == "phone"
    assert "device_id" not in bundle
    assert bundle["files"][0]["path"] == "note.txt"
    assert bundle["hmac"]
    assert devices.list_paired_devices()[0]["last_sync"] > 0


def test_export_folder_preserves_prefix_and_skips_caches(paired, tmp_path):
    folder = tmp_path / "notes"
    (folder / "__pycache__").mkdir(parents=True)
    (folder / "a.txt").write_text("a", encoding="utf-8")
    (folder / "sub").mkdir()
    (folder / "sub" / "b.txt").write_text("b", encoding="utf-8")
    (folder / "__pycache__" / "junk.pyc").write_bytes(b"junk")

    out = tmp_path / "bundle.json"
    result = devices.export_bundle("phone", CODE, [str(folder)], str(out))
    assert result["ok"] is True
    paths = sorted(entry["path"] for entry in read_bundle(out)["files"])
    assert paths == ["notes/a.txt", "notes/sub/b.txt"]


def test_export_wrong_code(paired, tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("x", encoding="utf-8")
    result = devices.export_bundle("phone", "wrong-code", [str(source)], str(tmp_path / "b.json"))
    assert result["ok"] is False
    assert result["code"] == "bad_code"


def test_export_unpaired_device(store_path, tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("x", encoding="utf-8")
    result = devices.export_bundle("ghost", CODE, [str(source)], str(tmp_path / "b.json"))
    assert result["ok"] is False
    assert result["code"] == "not_paired"


def test_export_missing_source(paired, tmp_path):
    result = devices.export_bundle(
        "phone", CODE, [str(tmp_path / "missing.txt")], str(tmp_path / "b.json")
    )
    assert result["ok"] is False
    assert result["code"] == "source_not_found"


def test_export_empty_folder(paired, tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    result = devices.export_bundle("phone", CODE, [str(folder)], str(tmp_path / "b.json"))
    assert result["ok"] is False
    assert result["code"] == "empty"


def test_export_duplicate_bundle_paths(paired, tmp_path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    (one / "same.txt").write_text("1", encoding="utf-8")
    (two / "same.txt").write_text("2", encoding="utf-8")

    result = devices.export_bundle(
        "phone", CODE, [str(one / "same.txt"), str(two / "same.txt")], str(tmp_path / "b.json")
    )
    assert result["ok"] is False
    assert result["code"] == "duplicate_path"


def test_export_refuses_sensitive_files_by_default(paired, tmp_path):
    folder = tmp_path / "project"
    folder.mkdir()
    (folder / ".env").write_text("SECRET=1", encoding="utf-8")
    (folder / "ok.txt").write_text("ok", encoding="utf-8")

    blocked = devices.export_bundle("phone", CODE, [str(folder)], str(tmp_path / "b.json"))
    assert blocked["ok"] is False
    assert blocked["code"] == "sensitive_file"
    assert not (tmp_path / "b.json").exists()

    allowed = devices.export_bundle(
        "phone", CODE, [str(folder)], str(tmp_path / "b.json"), allow_sensitive=True
    )
    assert allowed["ok"] is True


def test_export_refuses_devaraj_folder_by_default(paired, tmp_path):
    folder = tmp_path / "DEVARAJ"
    folder.mkdir()
    (folder / "details.md").write_text("private", encoding="utf-8")

    blocked = devices.export_bundle("phone", CODE, [str(folder)], str(tmp_path / "b.json"))
    assert blocked["ok"] is False
    assert blocked["code"] == "sensitive_file"


@pytest.mark.skipif(os.name != "nt", reason="directory junctions are Windows-only")
def test_export_skips_directory_junction(paired, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside", encoding="utf-8")
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "ok.txt").write_text("inside", encoding="utf-8")

    link = folder / "link"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        pytest.skip(f"could not create junction: {created.stderr or created.stdout}")

    out = tmp_path / "bundle.json"
    result = devices.export_bundle("phone", CODE, [str(folder)], str(out))
    assert result["ok"] is True
    paths = [entry["path"] for entry in read_bundle(out)["files"]]
    assert paths == ["notes/ok.txt"]


def test_export_refuses_symlink_source(paired, tmp_path):
    target = tmp_path / "real.txt"
    target.write_text("real", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink not permitted: {exc}")

    result = devices.export_bundle("phone", CODE, [str(link)], str(tmp_path / "b.json"))
    assert result["ok"] is False
    assert result["code"] == "symlink_refused"


def test_export_honours_file_limit(paired, tmp_path, monkeypatch):
    folder = tmp_path / "many"
    folder.mkdir()
    for index in range(2):
        (folder / f"{index}.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        devices,
        "load_settings",
        lambda: {"devices": {"bundle": {"max_files": 1, "max_mb": 25}}},
    )
    result = devices.export_bundle("phone", CODE, [str(folder)], str(tmp_path / "b.json"))
    assert result["ok"] is False
    assert result["code"] == "too_many_files"


def test_export_honours_size_limit(paired, tmp_path, monkeypatch):
    source = tmp_path / "big.bin"
    source.write_bytes(b"x" * 4096)
    monkeypatch.setattr(
        devices,
        "load_settings",
        lambda: {"devices": {"bundle": {"max_files": 10, "max_mb": 0.001}}},
    )
    result = devices.export_bundle("phone", CODE, [str(source)], str(tmp_path / "b.json"))
    assert result["ok"] is False
    assert result["code"] == "too_large"


# ── Import ────────────────────────────────────────────────────────────────

def test_import_roundtrip(paired, tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("hello maya", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(source)], str(out))["ok"] is True
    source.unlink()

    dest = tmp_path / "dest"
    result = devices.import_bundle(str(out), str(dest), CODE)
    assert result["ok"] is True
    assert result["files"] == 1
    assert (dest / "note.txt").read_text(encoding="utf-8") == "hello maya"
    assert devices.list_paired_devices()[0]["last_sync"] > 0


def test_import_folder_roundtrip(paired, tmp_path):
    folder = tmp_path / "notes"
    (folder / "sub").mkdir(parents=True)
    (folder / "a.txt").write_text("a", encoding="utf-8")
    (folder / "sub" / "b.txt").write_text("b", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(folder)], str(out))["ok"] is True

    dest = tmp_path / "dest"
    result = devices.import_bundle(str(out), str(dest), CODE)
    assert result["ok"] is True
    assert (dest / "notes" / "a.txt").read_text(encoding="utf-8") == "a"
    assert (dest / "notes" / "sub" / "b.txt").read_text(encoding="utf-8") == "b"


def test_import_wrong_code(paired, tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("x", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(source)], str(out))["ok"] is True

    result = devices.import_bundle(str(out), str(tmp_path / "dest"), "wrong-code")
    assert result["ok"] is False
    assert result["code"] == "bad_code"
    assert not (tmp_path / "dest").exists()


def test_import_unpaired_sender(paired, tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("x", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(source)], str(out))["ok"] is True

    devices.revoke_device("phone")
    result = devices.import_bundle(str(out), str(tmp_path / "dest"), CODE)
    assert result["ok"] is False
    assert result["code"] == "not_paired"


def test_import_across_two_installs(paired, tmp_path, monkeypatch):
    """The real workflow: export here, pair the same name+code there, import."""
    source = tmp_path / "note.txt"
    source.write_text("from the other laptop", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(source)], str(out))["ok"] is True

    receiver_store = tmp_path / "receiver" / "devices.json"
    monkeypatch.setenv("MAYA_DEVICES_STORE", str(receiver_store))
    receiver = devices.pair_device("phone", CODE)
    assert receiver["ok"] is True

    dest = tmp_path / "dest"
    result = devices.import_bundle(str(out), str(dest), CODE)
    assert result["ok"] is True
    assert (dest / "note.txt").read_text(encoding="utf-8") == "from the other laptop"


def test_import_after_repair_with_new_code_fails(paired, tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("x", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(source)], str(out))["ok"] is True

    new_code = "a-completely-new-code"
    devices.revoke_device("phone")
    assert devices.pair_device("phone", new_code)["ok"] is True
    result = devices.import_bundle(str(out), str(tmp_path / "dest"), new_code)
    assert result["ok"] is False
    assert result["code"] == "tampered"


def test_import_detects_tampering(paired, tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("real", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(source)], str(out))["ok"] is True

    bundle = read_bundle(out)
    bundle["files"][0]["data"] = base64.b64encode(b"evil").decode("ascii")
    write_bundle(out, bundle)

    result = devices.import_bundle(str(out), str(tmp_path / "dest"), CODE)
    assert result["ok"] is False
    assert result["code"] == "tampered"
    assert not (tmp_path / "dest" / "note.txt").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("iterations", 0),
        ("iterations", 10**9),
        ("iterations", 1.5e999),
        ("algo", "md5"),
        ("salt", "zz"),
        ("salt", ""),
    ],
)
def test_import_rejects_bad_kdf(paired, tmp_path, field, value):
    source = tmp_path / "note.txt"
    source.write_text("x", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(source)], str(out))["ok"] is True

    bundle = read_bundle(out)
    bundle["kdf"][field] = value
    write_bundle(out, bundle)

    result = devices.import_bundle(str(out), str(tmp_path / "dest"), CODE)
    assert result["ok"] is False
    assert result["code"] == "bad_bundle"


def test_import_rejects_oversized_bundle_file(paired, tmp_path, monkeypatch):
    monkeypatch.setattr(
        devices,
        "load_settings",
        lambda: {"devices": {"bundle": {"max_files": 10, "max_mb": 0.001}}},
    )
    big = tmp_path / "big.json"
    big.write_bytes(b"x" * 1_100_000)
    result = devices.import_bundle(str(big), str(tmp_path / "dest"), CODE)
    assert result["ok"] is False
    assert result["code"] == "too_large"
    assert not (tmp_path / "dest").exists()


def test_import_rejects_duplicate_paths(paired, tmp_path):
    one = tmp_path / "a.txt"
    two = tmp_path / "b.txt"
    one.write_text("a", encoding="utf-8")
    two.write_text("b", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(one), str(two)], str(out))["ok"] is True

    bundle = read_bundle(out)
    bundle["files"][1]["path"] = bundle["files"][0]["path"]
    write_bundle(out, resign(bundle))

    result = devices.import_bundle(str(out), str(tmp_path / "dest"), CODE)
    assert result["ok"] is False
    assert result["code"] == "duplicate_path"


def test_import_rejects_file_folder_path_conflict(paired, tmp_path):
    one = tmp_path / "a.txt"
    two = tmp_path / "b.txt"
    one.write_text("a", encoding="utf-8")
    two.write_text("b", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(one), str(two)], str(out))["ok"] is True

    bundle = read_bundle(out)
    bundle["files"][1]["path"] = bundle["files"][0]["path"] + "/child.txt"
    write_bundle(out, resign(bundle))

    result = devices.import_bundle(str(out), str(tmp_path / "dest"), CODE)
    assert result["ok"] is False
    assert result["code"] == "path_conflict"


def test_import_rejects_path_traversal(paired, tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("x", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(source)], str(out))["ok"] is True

    bundle = read_bundle(out)
    bundle["files"][0]["path"] = "../evil.txt"
    write_bundle(out, resign(bundle))

    dest = tmp_path / "dest"
    result = devices.import_bundle(str(out), str(dest), CODE)
    assert result["ok"] is False
    assert result["code"] == "invalid_path"
    assert not (tmp_path / "evil.txt").exists()


def test_import_detects_size_mismatch(paired, tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("x", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(source)], str(out))["ok"] is True

    bundle = read_bundle(out)
    bundle["files"][0]["size"] = 999
    write_bundle(out, resign(bundle))

    result = devices.import_bundle(str(out), str(tmp_path / "dest"), CODE)
    assert result["ok"] is False
    assert result["code"] == "corrupt"


def test_import_detects_hash_mismatch(paired, tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("x", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(source)], str(out))["ok"] is True

    bundle = read_bundle(out)
    bundle["files"][0]["sha256"] = "0" * 64
    write_bundle(out, resign(bundle))

    result = devices.import_bundle(str(out), str(tmp_path / "dest"), CODE)
    assert result["ok"] is False
    assert result["code"] == "corrupt"


def test_import_refuses_existing_files_then_overwrites(paired, tmp_path):
    source = tmp_path / "note.txt"
    out = tmp_path / "bundle.json"
    source.write_text("one", encoding="utf-8")
    assert devices.export_bundle("phone", CODE, [str(source)], str(out))["ok"] is True

    dest = tmp_path / "dest"
    assert devices.import_bundle(str(out), str(dest), CODE)["ok"] is True

    source.write_text("two", encoding="utf-8")
    out_two = tmp_path / "bundle2.json"
    assert devices.export_bundle("phone", CODE, [str(source)], str(out_two))["ok"] is True

    blocked = devices.import_bundle(str(out_two), str(dest), CODE)
    assert blocked["ok"] is False
    assert blocked["code"] == "exists"
    assert blocked["conflicts"] == ["note.txt"]
    assert (dest / "note.txt").read_text(encoding="utf-8") == "one"

    replaced = devices.import_bundle(str(out_two), str(dest), CODE, overwrite=True)
    assert replaced["ok"] is True
    assert (dest / "note.txt").read_text(encoding="utf-8") == "two"


def test_import_refuses_folder_at_file_target(paired, tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("x", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(source)], str(out))["ok"] is True

    dest = tmp_path / "dest"
    (dest / "note.txt").mkdir(parents=True)
    result = devices.import_bundle(str(out), str(dest), CODE)
    assert result["ok"] is False
    assert result["code"] == "invalid_target"


def test_import_missing_and_invalid_bundles(tmp_path):
    missing = devices.import_bundle(str(tmp_path / "nope.json"), str(tmp_path / "d"), CODE)
    assert missing["ok"] is False
    assert missing["code"] == "bundle_not_found"

    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    result = devices.import_bundle(str(bad), str(tmp_path / "d"), CODE)
    assert result["ok"] is False
    assert result["code"] == "bad_bundle"

    wrong = tmp_path / "wrong.json"
    write_bundle(wrong, {"format": "other", "version": 1})
    result = devices.import_bundle(str(wrong), str(tmp_path / "d"), CODE)
    assert result["ok"] is False
    assert result["code"] == "bad_bundle"


def test_import_rolls_back_on_write_failure(paired, tmp_path, monkeypatch):
    one = tmp_path / "a.txt"
    two = tmp_path / "b.txt"
    one.write_text("a", encoding="utf-8")
    two.write_text("b", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert devices.export_bundle("phone", CODE, [str(one), str(two)], str(out))["ok"] is True

    real_replace = devices.os.replace

    def flaky(src, dst):
        if str(src).endswith("file-1"):
            raise OSError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(devices.os, "replace", flaky)
    dest = tmp_path / "dest"
    result = devices.import_bundle(str(out), str(dest), CODE)
    assert result["ok"] is False
    assert result["code"] == "write_failed"
    assert not (dest / "a.txt").exists()
    assert not (dest / "b.txt").exists()
    assert list(dest.iterdir()) == []


def test_import_error_sanitizes_control_chars(tmp_path):
    evil = tmp_path / "evil.json"
    write_bundle(
        evil,
        {
            "format": devices.BUNDLE_FORMAT,
            "version": devices.BUNDLE_VERSION,
            "device": "\x1b]0;pwn\x07",
        },
    )
    result = devices.import_bundle(str(evil), str(tmp_path / "dest"), CODE)
    assert result["ok"] is False
    assert result["code"] == "not_paired"
    assert "\x1b" not in result["error"]


@pytest.mark.parametrize(
    "path",
    [
        "", "   ", "/etc/passwd", "..\\evil.txt", "../evil.txt", "a/../../b", ".",
        "C:\\evil.txt", "C:/evil.txt", "notes/a.txt:stream", "a\x00b", "CON",
        "con.txt", "AUX", "COM1", "a./b", "notes/ a", "a/D:/evil.txt",
    ],
)
def test_safe_relative_rejects_unsafe_paths(path):
    with pytest.raises(ValueError):
        devices._safe_relative(path)


def test_safe_relative_accepts_nested_path():
    rel = devices._safe_relative("notes/sub/a.txt")
    assert rel.as_posix() == "notes/sub/a.txt"


# ── CLI ───────────────────────────────────────────────────────────────────

def test_cli_pair_list_revoke(cli_store):
    paired = invoke("devices", "pair", "phone", "--code", CODE)
    assert paired.exit_code == 0, paired.output
    assert "paired device: phone" in paired.output.lower()

    listed = invoke("devices", "list")
    assert listed.exit_code == 0
    assert "phone" in listed.output
    assert CODE not in listed.output

    revoked = invoke("devices", "revoke", "phone", "--yes")
    assert revoked.exit_code == 0
    assert "revoked device: phone" in revoked.output.lower()
    assert devices.list_paired_devices() == []


def test_cli_pair_generates_and_prints_code(cli_store):
    result = invoke("devices", "pair", "tablet")
    assert result.exit_code == 0
    assert "Pairing code (shown once" in result.output
    assert "tablet" in devices._load_store()["devices"]


def test_cli_pair_ask_code(cli_store):
    result = invoke(
        "devices", "pair", "phone", "--ask-code", input=f"{CODE}\n{CODE}\n"
    )
    assert result.exit_code == 0, result.output
    assert devices.verify_pair_code("phone", CODE) is True
    assert CODE not in result.output


def test_cli_export_refuses_sensitive_by_default(cli_store, tmp_path):
    assert invoke("devices", "pair", "phone", "--code", CODE).exit_code == 0
    folder = tmp_path / "project"
    folder.mkdir()
    (folder / ".env").write_text("SECRET=1", encoding="utf-8")
    (folder / "ok.txt").write_text("ok", encoding="utf-8")

    blocked = invoke(
        "devices", "export", "phone", "--source", str(folder),
        "--out", str(tmp_path / "b.json"), "--code", CODE,
    )
    assert blocked.exit_code == 1
    assert "Refusing to bundle" in blocked.output

    allowed = invoke(
        "devices", "export", "phone", "--source", str(folder),
        "--out", str(tmp_path / "b.json"), "--code", CODE, "--allow-sensitive",
    )
    assert allowed.exit_code == 0, allowed.output


def test_cli_import_error_has_no_terminal_escape(cli_store, tmp_path):
    evil = tmp_path / "evil.json"
    write_bundle(
        evil,
        {
            "format": devices.BUNDLE_FORMAT,
            "version": devices.BUNDLE_VERSION,
            "device": "\x1b]0;pwn\x07",
        },
    )
    result = invoke(
        "devices", "import", str(evil),
        "--dest", str(tmp_path / "dest"), "--code", CODE,
    )
    assert result.exit_code == 1
    assert "\x1b" not in result.output


def test_cli_pair_rejects_short_code(cli_store):
    result = invoke("devices", "pair", "phone", "--code", "short")
    assert result.exit_code == 1
    assert "at least 16" in result.output


def test_cli_revoke_confirmation(cli_store):
    assert invoke("devices", "pair", "phone", "--code", CODE).exit_code == 0

    aborted = invoke("devices", "revoke", "phone", input="n\n")
    assert aborted.exit_code == 1
    assert devices.list_paired_devices()

    confirmed = invoke("devices", "revoke", "phone", input="y\n")
    assert confirmed.exit_code == 0
    assert devices.list_paired_devices() == []


def test_cli_export_import_roundtrip(cli_store, tmp_path):
    assert invoke("devices", "pair", "phone", "--code", CODE).exit_code == 0

    source = tmp_path / "note.txt"
    source.write_text("through the cli", encoding="utf-8")
    out = tmp_path / "bundle.json"

    exported = invoke(
        "devices", "export", "phone",
        "--source", str(source),
        "--out", str(out),
        "--code", CODE,
    )
    assert exported.exit_code == 0, exported.output
    assert "signed, not encrypted" in exported.output

    dest = tmp_path / "dest"
    imported = invoke(
        "devices", "import", str(out),
        "--dest", str(dest),
        "--code", CODE,
    )
    assert imported.exit_code == 0, imported.output
    assert (dest / "note.txt").read_text(encoding="utf-8") == "through the cli"


def test_cli_import_wrong_code(cli_store, tmp_path):
    assert invoke("devices", "pair", "phone", "--code", CODE).exit_code == 0
    source = tmp_path / "note.txt"
    source.write_text("x", encoding="utf-8")
    out = tmp_path / "bundle.json"
    assert invoke(
        "devices", "export", "phone", "--source", str(source), "--out", str(out), "--code", CODE
    ).exit_code == 0

    result = invoke(
        "devices", "import", str(out), "--dest", str(tmp_path / "dest"), "--code", "wrong-code"
    )
    assert result.exit_code == 1
    assert "wrong" in result.output.lower()
    assert not (tmp_path / "dest").exists()
