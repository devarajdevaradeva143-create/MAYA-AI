"""Tests for AI English Teacher lesson generation + SQLite progress."""

from __future__ import annotations

from pathlib import Path

from custom.tools.teacher_service import TeacherService


class FakeEngine:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_messages = None

    def chat(self, messages):
        self.last_messages = messages
        return self.reply


def test_fallback_when_no_engine(tmp_path: Path) -> None:
    svc = TeacherService(engine=None, progress_path=tmp_path / "t.db")
    lesson = svc.generate_lesson("Vocabulary", "Beginner")
    assert lesson["source"] == "fallback"
    assert lesson["topic"] == "Vocabulary"
    assert lesson["type"] == "mixed"
    assert "id" in lesson


def test_ai_lesson_with_fake_engine(tmp_path: Path) -> None:
    svc = TeacherService(
        engine=FakeEngine('{"prompt": "What is 2+2?", "answer": "4", "explanation": "basic math"}'),
        db_path=tmp_path / "t.db",
    )
    lesson = svc.generate_lesson("Vocabulary", "Beginner", "vocab")
    assert lesson["source"] == "ai"
    assert lesson["answer"] == "4"
    assert lesson["type"] == "vocab"


def test_check_answer_and_progress(tmp_path: Path) -> None:
    svc = TeacherService(engine=None, progress_path=tmp_path / "t.db")
    lesson = svc.generate_lesson("Vocabulary", "Beginner")
    # fallback answer is "b"
    res = svc.check_answer(lesson, "b")
    assert res["correct"] is True
    assert res["score"] == 100
    prog = svc.get_progress(lesson["id"])
    assert prog["attempts"] == 1
    assert prog["completed"] is True
    agg = svc.get_progress()
    assert agg["totals"]["attempts"] == 1
    assert agg["totals"]["correct"] == 1
    assert agg["streak"] == 1


def test_wrong_answer_progress(tmp_path: Path) -> None:
    svc = TeacherService(engine=None, progress_path=tmp_path / "t.db")
    lesson = svc.generate_lesson("Vocabulary", "Beginner")
    res = svc.check_answer(lesson["id"], "z")
    assert res["correct"] is False
    assert res["score"] == 0
    prog = svc.get_progress(lesson["id"])
    assert prog["attempts"] == 1
    assert prog["completed"] is False


def test_progress_persists(tmp_path: Path) -> None:
    p = tmp_path / "t.db"
    svc = TeacherService(engine=None, progress_path=p)
    lesson = svc.generate_lesson("Grammar", "Beginner")
    svc.check_answer(lesson, "wrong")
    svc2 = TeacherService(engine=None, progress_path=p)
    assert svc2.get_progress()["totals"]["attempts"] == 1


def test_mark_complete_and_reset(tmp_path: Path) -> None:
    svc = TeacherService(engine=None, progress_path=tmp_path / "t.db")
    lesson = svc.generate_lesson("Vocabulary", "Beginner")
    updated = svc.mark_complete(lesson["id"], 85)
    assert updated["completed"] is True
    assert updated["score"] == 85
    svc.reset_progress()
    agg = svc.get_progress()
    assert agg["totals"]["attempts"] == 0
    assert agg["lessons"] == []


def test_get_progress_unknown_lesson(tmp_path: Path) -> None:
    svc = TeacherService(engine=None, progress_path=tmp_path / "t.db")
    prog = svc.get_progress("nope")
    assert prog["attempts"] == 0
    assert prog["completed"] is False