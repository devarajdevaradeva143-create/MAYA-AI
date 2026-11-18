"""Tests for the Maya AI CLI (click.testing.CliRunner).

The assistant JSON store is redirected to a tmp path for every test
(``MAYA_ASSISTANT_STORE``), so real offline memory stays clean.
"""

import pytest
from click.testing import CliRunner

from custom.cli import main
from custom.tools.store import ENV_STORE_PATH


@pytest.fixture()
def cli(tmp_path, monkeypatch):
    """CliRunner pointed at a throw-away assistant store."""
    monkeypatch.setenv(ENV_STORE_PATH, str(tmp_path / "assistant.json"))
    # Keep the knowledge index out of the real offline memory too.
    monkeypatch.setenv("MAYA_KNOWLEDGE_INDEX", str(tmp_path / "knowledge_index.json"))
    return CliRunner()


def invoke(cli: CliRunner, *args: str):
    return cli.invoke(main, list(args))


# ── Basic commands ────────────────────────────────────────────────────

def test_help(cli):
    result = invoke(cli, "--help")
    assert result.exit_code == 0, result.output
    for command in ("config", "wake", "version", "chat", "todo", "reminder", "devices"):
        assert command in result.output


def test_config(cli):
    result = invoke(cli, "config")
    assert result.exit_code == 0, result.output
    assert "Maya AI Settings:" in result.output
    assert "mode" in result.output


def test_wake(cli):
    result = invoke(cli, "wake")
    assert result.exit_code == 0, result.output
    assert "Sollu da, enna venum?" in result.output


def test_version(cli):
    result = invoke(cli, "version")
    assert result.exit_code == 0, result.output
    assert "Maya AI version" in result.output


# ── To-dos ────────────────────────────────────────────────────────────

def test_todo_add_list_complete(cli):
    added = invoke(cli, "todo", "add", "phase1 test")
    assert added.exit_code == 0, added.output
    assert "To-do added: 'phase1 test'" in added.output
    # Regression: message must appear exactly once (no tool-layer print).
    assert added.output.count("To-do added") == 1

    listed = invoke(cli, "todo", "list")
    assert listed.exit_code == 0, listed.output
    assert "1." in listed.output
    assert "phase1 test" in listed.output

    done = invoke(cli, "todo", "complete", "1")
    assert done.exit_code == 0, done.output
    assert "To-do marked complete" in done.output
    assert "Invalid to-do index" not in done.output

    listed_after = invoke(cli, "todo", "list")
    assert "✅" in listed_after.output


def test_todo_complete_persists_across_invocations(cli):
    invoke(cli, "todo", "add", "first")
    invoke(cli, "todo", "add", "second")
    invoke(cli, "todo", "complete", "2")

    result = invoke(cli, "todo", "list")
    lines = [line for line in result.output.splitlines() if "second" in line]
    assert lines and "✅" in lines[0], result.output


def test_todo_complete_requires_integer(cli):
    result = invoke(cli, "todo", "complete", "not-a-number")
    assert result.exit_code != 0


# ── Reminders ─────────────────────────────────────────────────────────

def test_reminder_set_two_positional_args(cli):
    """Regression test: `reminder set TIME TEXT` must not error."""
    result = invoke(cli, "reminder", "set", "09:00", "Drink water")
    assert result.exit_code == 0, result.output
    assert "Got unexpected extra arguments" not in result.output
    assert "Reminder set: 'Drink water' at 09:00" in result.output
    assert result.output.count("Reminder set") == 1


def test_reminder_list(cli):
    invoke(cli, "reminder", "set", "09:00", "Drink water")
    result = invoke(cli, "reminder", "list")
    assert result.exit_code == 0, result.output
    assert "09:00" in result.output
    assert "Drink water" in result.output


def test_reminder_set_requires_arguments(cli):
    result = invoke(cli, "reminder", "set", "09:00")
    assert result.exit_code != 0


# ── Knowledge base ────────────────────────────────────────────────────

def test_knowledge_index_and_search(cli, tmp_path):
    docs = tmp_path / "kb"
    docs.mkdir()
    (docs / "note.txt").write_text("Maya runs Qwen on the NPU.", encoding="utf-8")

    indexed = invoke(cli, "knowledge", "index", str(docs))
    assert indexed.exit_code == 0, indexed.output
    assert "Indexed 1 file(s)" in indexed.output

    found = invoke(cli, "knowledge", "search", "npu")
    assert found.exit_code == 0, found.output
    assert "note.txt" in found.output

    # Index must record an absolute base so search works from any cwd.
    status = invoke(cli, "knowledge", "status")
    assert str(docs) in status.output


def test_knowledge_search_without_index(cli):
    result = invoke(cli, "knowledge", "search", "anything")
    assert result.exit_code == 0, result.output
    assert "No index yet" in result.output
