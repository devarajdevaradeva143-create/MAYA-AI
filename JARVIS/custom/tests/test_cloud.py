"""Cloud (Gemini) tests — no network, no real key."""

import json

import httpx
import pytest
from click.testing import CliRunner

from custom import cloud_cli
from custom.tools import cloud

KEY = "test-key-1234"


@pytest.fixture()
def keyed(monkeypatch, tmp_path):
    """Provide a fake key + isolated online log."""
    monkeypatch.setenv(cloud.ENV_KEY, KEY)
    monkeypatch.setenv("MAYA_ENV_FILE", str(tmp_path / "missing.env"))
    return tmp_path


# ── Config / key handling ─────────────────────────────────────────────

def test_status_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv(cloud.ENV_KEY, raising=False)
    monkeypatch.setenv("MAYA_ENV_FILE", str(tmp_path / "nope.env"))
    st = cloud.status()
    assert st["configured"] is False
    assert st["key_preview"] is None


def test_status_with_key_hides_it(keyed):
    st = cloud.status()
    assert st["configured"] is True
    assert KEY not in st["key_preview"]
    assert st["key_preview"].endswith("1234")


def test_env_file_parsing(tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"# comment\n{cloud.ENV_KEY}=\"{KEY}\"\n", encoding="utf-8")
    assert cloud.load_env_file(env)[cloud.ENV_KEY] == KEY


def test_missing_key_is_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.delenv(cloud.ENV_KEY, raising=False)
    monkeypatch.setenv("MAYA_ENV_FILE", str(tmp_path / "nope.env"))
    with pytest.raises(cloud.CloudError) as exc:
        cloud.ask("hello")
    assert "GEMINI_API_KEY" in str(exc.value)


# ── Request / response ────────────────────────────────────────────────

def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ask_sends_expected_request_and_parses_reply(keyed):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "pong"}]}}]},
        )

    with _mock_client(handler) as client:
        reply = cloud.ask("ping", client=client)

    assert reply == "pong"
    assert "gemini" in seen["url"]
    assert ":generateContent" in seen["url"]
    assert seen["body"]["contents"][0]["parts"][0]["text"] == "ping"
    # The key must travel as a query param, never in the body.
    assert KEY not in json.dumps(seen["body"])


def test_ask_includes_system_instruction(keyed):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    with _mock_client(handler) as client:
        cloud.ask("hi", system="be terse", client=client)

    assert captured["body"]["systemInstruction"]["parts"][0]["text"] == "be terse"


def test_bad_key_reports_clearly(keyed):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "API key not valid"}})

    with _mock_client(handler) as client:
        with pytest.raises(cloud.CloudError) as exc:
            cloud.ask("hi", client=client)
    assert "rejected" in str(exc.value).lower()


def test_blocked_prompt_explains_reason(keyed):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})

    with _mock_client(handler) as client:
        with pytest.raises(cloud.CloudError) as exc:
            cloud.ask("hi", client=client)
    assert "SAFETY" in str(exc.value)


def test_network_failure_is_wrapped(keyed):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with _mock_client(handler) as client:
        with pytest.raises(cloud.CloudError) as exc:
            cloud.ask("hi", client=client)
    assert "Cannot reach Gemini" in str(exc.value)


# ── Privacy guard: confirmation before sending ────────────────────────

def test_cli_refuses_when_confirmation_declined(keyed, monkeypatch):
    called = {"sent": False}

    def fake_ask(*args, **kwargs):
        called["sent"] = True
        return "reply"

    monkeypatch.setattr(cloud, "ask", fake_ask)
    runner = CliRunner()
    result = runner.invoke(cloud_cli.main, ["ask", "hello"], input="n\n")

    assert result.exit_code != 0
    assert called["sent"] is False
    assert "About to send" in result.output


def test_cli_dry_run_sends_nothing(keyed, monkeypatch):
    called = {"sent": False}
    monkeypatch.setattr(cloud, "ask", lambda *a, **k: called.update(sent=True) or "x")

    result = CliRunner().invoke(cloud_cli.main, ["ask", "hello", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "nothing was sent" in result.output.lower()
    assert called["sent"] is False


def test_cli_ask_with_yes_sends_and_logs(keyed, monkeypatch):
    monkeypatch.setattr(cloud, "ask", lambda *a, **k: "the answer")

    result = CliRunner().invoke(cloud_cli.main, ["ask", "hello", "--yes"])

    assert result.exit_code == 0, result.output
    assert "the answer" in result.output
    assert cloud.log_path().is_file()


def test_cli_status_reports_missing_key(monkeypatch, tmp_path):
    monkeypatch.delenv(cloud.ENV_KEY, raising=False)
    monkeypatch.setenv("MAYA_ENV_FILE", str(tmp_path / "nope.env"))

    result = CliRunner().invoke(cloud_cli.main, ["status"])

    assert result.exit_code == 0, result.output
    assert "configured: no" in result.output


# ── Session lock guard ────────────────────────────────────────────────

@pytest.fixture()
def locked_cloud(tmp_path, monkeypatch):
    from custom.tools.security import SecurityManager

    manager = SecurityManager(tmp_path / "security.json")
    manager.set_pin("1234")
    monkeypatch.setattr(cloud_cli, "security_manager", manager)
    return manager


def test_cli_ask_blocked_while_locked(locked_cloud, keyed, monkeypatch):
    called = {"sent": False}
    monkeypatch.setattr(cloud, "ask", lambda *a, **k: called.update(sent=True) or "x")

    result = CliRunner().invoke(cloud_cli.main, ["ask", "hello", "--yes"])

    assert result.exit_code != 0
    assert "locked" in result.output.lower()
    assert called["sent"] is False


def test_cli_chat_blocked_while_locked(locked_cloud, keyed):
    result = CliRunner().invoke(cloud_cli.main, ["chat"], input="exit\n")

    assert result.exit_code != 0
    assert "locked" in result.output.lower()


def test_cli_status_allowed_while_locked(locked_cloud, keyed):
    result = CliRunner().invoke(cloud_cli.main, ["status"])

    assert result.exit_code == 0, result.output
    assert "configured: yes" in result.output


def test_cli_help_allowed_while_locked(locked_cloud):
    result = CliRunner().invoke(cloud_cli.main, ["--help"])

    assert result.exit_code == 0, result.output
    assert "ask" in result.output


# ── Setting the key (.env) ────────────────────────────────────────────

@pytest.fixture()
def env_file(tmp_path, monkeypatch):
    from custom.tools.security import SecurityManager

    path = tmp_path / ".env"
    monkeypatch.setenv("MAYA_ENV_FILE", str(path))
    monkeypatch.delenv(cloud.ENV_KEY, raising=False)
    monkeypatch.setattr(
        cloud_cli, "security_manager", SecurityManager(tmp_path / "security.json")
    )
    return path


def test_save_api_key_creates_env_and_preserves_lines(env_file):
    env_file.write_text("# my settings\nOTHER=1\n", encoding="utf-8")
    key = "AIza" + "x" * 35

    result = cloud.save_api_key(key)

    assert result["ok"] is True
    assert result["looks_google"] is True
    assert env_file.read_text(encoding="utf-8") == (
        f"# my settings\nOTHER=1\n\n{cloud.ENV_KEY}={key}\n"
    )
    assert cloud.load_env_file(env_file)[cloud.ENV_KEY] == key


def test_save_api_key_replaces_existing(env_file):
    env_file.write_text(
        f"{cloud.ENV_KEY}=old-key-old-key-old-key\nOTHER=1\n", encoding="utf-8"
    )
    key = "new-key-" + "y" * 20

    assert cloud.save_api_key(key)["ok"] is True

    text = env_file.read_text(encoding="utf-8")
    assert text.count(cloud.ENV_KEY + "=") == 1
    assert "old-key" not in text
    assert "OTHER=1" in text


@pytest.mark.parametrize("key", ["", "short", "has space " + "x" * 20])
def test_save_api_key_rejects_bad_values(env_file, key):
    result = cloud.save_api_key(key)
    assert result["ok"] is False
    assert not env_file.exists()


def test_cli_set_key_hidden_prompt(env_file):
    key = "AIza" + "z" * 35

    result = CliRunner().invoke(
        cloud_cli.main, ["set-key"], input=f"{key}\n{key}\n"
    )

    assert result.exit_code == 0, result.output
    assert key not in result.output
    assert "Saved" in result.output
    assert cloud.load_env_file(env_file)[cloud.ENV_KEY] == key


def test_cli_set_key_from_env(env_file, monkeypatch):
    key = "env-key-" + "q" * 20
    monkeypatch.setenv(cloud.ENV_KEY, key)

    result = CliRunner().invoke(cloud_cli.main, ["set-key", "--from-env", "--force"])

    assert result.exit_code == 0, result.output
    assert key not in result.output
    assert cloud.load_env_file(env_file)[cloud.ENV_KEY] == key


def test_cli_set_key_asks_before_replacing(env_file):
    old = "a" * 30
    env_file.write_text(f"{cloud.ENV_KEY}={old}\n", encoding="utf-8")

    result = CliRunner().invoke(cloud_cli.main, ["set-key"], input="n\n")

    assert result.exit_code != 0
    assert cloud.load_env_file(env_file)[cloud.ENV_KEY] == old


def test_cli_set_key_blocked_while_locked(tmp_path, monkeypatch):
    from custom.tools.security import SecurityManager

    manager = SecurityManager(tmp_path / "security.json")
    manager.set_pin("1234")
    monkeypatch.setattr(cloud_cli, "security_manager", manager)
    path = tmp_path / ".env"
    monkeypatch.setenv("MAYA_ENV_FILE", str(path))
    monkeypatch.delenv(cloud.ENV_KEY, raising=False)
    key = "AIza" + "x" * 35

    result = CliRunner().invoke(
        cloud_cli.main, ["set-key"], input=f"{key}\n{key}\n"
    )

    assert result.exit_code != 0
    assert "locked" in result.output.lower()
    assert not path.exists()
