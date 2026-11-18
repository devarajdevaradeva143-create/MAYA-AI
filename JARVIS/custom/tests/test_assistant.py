"""Tests for Maya AI personal assistant tools.

Every test points the JSON store at a tmp path via ``MAYA_ASSISTANT_STORE``
(see ``custom/tools/store.py``) so the real
``MAYA AI/memory/offline/assistant.json`` is never touched.
"""

import pytest

from custom.tools.assistant import (
    PersonalAssistant,
    add_todo,
    complete_todo,
    get_daily_schedule,
    list_reminders,
    list_todos,
    set_reminder,
)
from custom.tools.store import ENV_STORE_PATH


@pytest.fixture()
def store_file(tmp_path, monkeypatch):
    """Redirect the assistant store to a tmp JSON file."""
    path = tmp_path / "assistant.json"
    monkeypatch.setenv(ENV_STORE_PATH, str(path))
    return path


def test_assistant_init(store_file):
    """Assistant should initialize with empty reminders and todos."""
    fresh = PersonalAssistant()
    assert len(fresh.reminders) == 0, "Expected empty reminders on init"
    assert len(fresh.todos) == 0, "Expected empty todos on init"
    assert not store_file.exists(), "Init must not create the store file"


def test_set_reminder(store_file):
    """Setting a reminder should store it and return a confirmation."""
    msg = set_reminder("Drink water", "09:00")
    assert "Reminder set" in msg, f"Expected confirmation, got: {msg}"

    reminders = list_reminders()
    assert len(reminders) == 1, f"Expected 1 reminder, got {len(reminders)}"
    assert reminders[0]["text"] == "Drink water"
    assert reminders[0]["time"] == "09:00"
    assert reminders[0]["id"], "Expected a reminder id"
    assert reminders[0]["created"], "Expected a created timestamp"
    assert store_file.is_file(), "Expected the reminder to be saved on disk"


def test_list_reminders(store_file):
    """Listing reminders should return the stored ones."""
    set_reminder("Drink water", "09:00")
    set_reminder("Sleep early", "22:00")
    assert len(list_reminders()) == 2


def test_add_todo(store_file):
    """Adding a todo should work and keep the old dict keys."""
    msg = add_todo("Review AGENTS.md")
    assert "To-do added" in msg, f"Expected confirmation, got: {msg}"

    todos = list_todos()
    assert len(todos) == 1, f"Expected 1 todo, got {len(todos)}"
    assert todos[0]["task"] == "Review AGENTS.md"
    assert todos[0]["done"] is False
    assert todos[0]["id"], "Expected a to-do id"
    assert todos[0]["created"], "Expected a created timestamp"


def test_list_todos(store_file):
    """Listing todos should return stored ones."""
    add_todo("Review AGENTS.md")
    add_todo("Test knowledge search")
    assert len(list_todos()) == 2


def test_complete_todo(store_file):
    """Completing a todo by index should mark it done."""
    add_todo("Review AGENTS.md")
    add_todo("Test knowledge search")

    msg = complete_todo(1)
    assert "complete" in msg.lower()
    assert "Invalid" not in msg

    todos = list_todos()
    assert todos[0]["done"] is True, "Expected first todo to be marked done"
    assert todos[1]["done"] is False, "Second todo must stay open"


def test_complete_todo_invalid(store_file):
    """Invalid index should give an error message, not crash."""
    add_todo("Review AGENTS.md")
    msg = complete_todo(999)
    assert isinstance(msg, str), f"Expected string, got {type(msg)}"
    assert "Invalid to-do index" in msg


def test_get_daily_schedule(store_file):
    """Daily schedule placeholder."""
    schedule = get_daily_schedule()
    assert isinstance(schedule, str), f"Expected string, got {type(schedule)}"
    assert "No schedule set yet" in schedule


def test_tool_layer_is_silent(store_file, capsys):
    """Tool functions must not print — the CLI prints once only."""
    set_reminder("Drink water", "09:00")
    add_todo("Review AGENTS.md")
    complete_todo(1)
    captured = capsys.readouterr()
    assert captured.out == "", f"Tool layer printed: {captured.out!r}"
    assert captured.err == "", f"Tool layer wrote stderr: {captured.err!r}"


def test_persistence_across_instances(store_file):
    """A brand-new assistant instance must see the saved data."""
    first = PersonalAssistant()
    first.set_reminder("Drink water", "09:00")
    first.add_todo("Review AGENTS.md")
    first.complete_todo(1)

    second = PersonalAssistant()
    assert len(second.list_reminders()) == 1
    todos = second.list_todos()
    assert len(todos) == 1
    assert todos[0]["task"] == "Review AGENTS.md"
    assert todos[0]["done"] is True


def test_corrupt_store_recovers(store_file):
    """Corrupt JSON should read as empty and still allow new writes."""
    store_file.parent.mkdir(parents=True, exist_ok=True)
    store_file.write_text("{ this is not json", encoding="utf-8")

    assert list_reminders() == []
    assert list_todos() == []

    msg = add_todo("Review AGENTS.md")
    assert "To-do added" in msg
    assert len(list_todos()) == 1
