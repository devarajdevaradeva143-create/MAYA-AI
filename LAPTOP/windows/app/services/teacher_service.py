"""AI English Teacher service — lesson generation, checking, progress.

Qt-free and testable. Uses the LOCAL engine only.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from custom.config import PROJECT_ROOT

TOPICS = ("Vocabulary", "Grammar", "Pronunciation", "Idioms")
LEVELS = ("Beginner", "Intermediate", "Advanced")

_FALLBACK: dict[tuple[str, str], dict[str, Any]] = {
    ("Vocabulary", "Beginner"): {
        "prompt": "What does 'serendipity' mean?\nA) Sadness  B) Chance joy  C) Anger  D) Boredom",
        "answer": "b",
        "explanation": "'Serendipity' = a happy accidental discovery.",
    },
    ("Grammar", "Beginner"): {
        "prompt": "Convert to Present Perfect:\n'I saw that movie last year.'",
        "answer": "i have seen that movie last year",
        "explanation": "Use have/has + past participle for unspecified past time.",
    },
    ("Pronunciation", "Beginner"): {
        "prompt": "Word: serendipity  /ˌserənˈdipədɪ/\nListen, then type what you heard.",
        "answer": None,
        "explanation": "Stress on the third syllable: ser-en-DIP-i-ty.",
    },
    ("Idioms", "Beginner"): {
        "prompt": "What does 'break the ice' mean?",
        "answer": "to start a conversation",
        "explanation": "'Break the ice' = to ease tension and start talking.",
    },
}


def _default_progress_path() -> Path:
    return PROJECT_ROOT / "MAYA AI" / "memory" / "offline" / "teacher_progress.json"


def _atomic_write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _empty_progress() -> dict[str, Any]:
    return {
        "version": 1,
        "totals": {"attempts": 0, "correct": 0},
        "streak": 0,
        "best_streak": 0,
        "topics": {topic: {"attempts": 0, "correct": 0} for topic in TOPICS},
        "recent": [],
    }


def _normalize_answer(text: str | None) -> str:
    if text is None:
        return ""
    text = str(text).strip().lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fallback_lesson(topic: str, level: str) -> dict[str, Any]:
    base = _FALLBACK.get((topic, level)) or _FALLBACK.get((topic, "Beginner")) or {
        "prompt": f"Practice {topic} at {level} level.",
        "answer": None,
        "explanation": "Keep practising.",
    }
    return {
        "id": f"fallback-{topic}-{level}-{int(time.time())}",
        "topic": topic,
        "level": level,
        "prompt": base["prompt"],
        "answer": base["answer"],
        "explanation": base["explanation"],
        "source": "fallback",
        "created": time.time(),
    }


def _parse_lesson_json(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    # strip code fences
    if text.startswith("```"):
        text = re.sub(r"^```[^\n]*\n", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    # find first {...}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    prompt = data.get("prompt")
    explanation = data.get("explanation")
    answer = data.get("answer")
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    if not isinstance(explanation, str):
        explanation = str(explanation) if explanation is not None else ""
    if isinstance(answer, list):
        answer = " / ".join(str(x) for x in answer) if answer else None
    if answer is not None and not isinstance(answer, str):
        answer = str(answer)
    if answer is not None and len(answer) > 120:
        return None
    # ensure English focus
    lowered = (prompt + " " + explanation).lower()
    if "spanish" in lowered or "french" in lowered or "german" in lowered:
        return None
    return {"prompt": prompt.strip(), "answer": answer, "explanation": explanation.strip()}


class TeacherService:
    def __init__(self, engine: Any = None, progress_path: str | Path | None = None) -> None:
        self._engine = engine
        self._progress_path = Path(progress_path) if progress_path is not None else _default_progress_path()
        self._progress: dict[str, Any] | None = None
        self._load_progress()

    def _load_progress(self) -> None:
        try:
            if self._progress_path.is_file():
                with self._progress_path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict) and data.get("version") == 1:
                    self._progress = data
                    return
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        self._progress = _empty_progress()

    def progress(self) -> dict[str, Any]:
        if self._progress is None:
            self._load_progress()
        return json.loads(json.dumps(self._progress))

    def reset_progress(self) -> None:
        self._progress = _empty_progress()
        _atomic_write(self._progress_path, self._progress)

    def _save_progress(self) -> None:
        if self._progress is not None:
            _atomic_write(self._progress_path, self._progress)

    def generate_lesson(self, topic: str, level: str) -> dict[str, Any]:
        topic = topic if topic in TOPICS else "Vocabulary"
        level = level if level in LEVELS else "Beginner"

        raw = None
        if self._engine is not None:
            try:
                engine = self._engine
                chat = getattr(engine, "chat", None)
                if chat is None:
                    # allow passing a raw bridge-like object
                    chat = engine
                prompt = (
                    "You are an English teacher. Create ONE English-learning exercise "
                    f"for a {level} learner on the topic '{topic}'. "
                    "This is an English-learning exercise; do not translate into Spanish "
                    "or any other language. Return compact JSON only with keys: "
                    "prompt, answer, explanation. For Pronunciation the answer may be null."
                )
                messages = [{"role": "user", "content": prompt}]
                raw = chat(messages) if callable(chat) else None
            except Exception:
                raw = None

        parsed = _parse_lesson_json(raw) if isinstance(raw, str) else None
        if parsed is None:
            return _fallback_lesson(topic, level)

        return {
            "id": f"ai-{topic}-{level}-{int(time.time())}",
            "topic": topic,
            "level": level,
            "prompt": parsed["prompt"],
            "answer": parsed["answer"],
            "explanation": parsed["explanation"],
            "source": "ai",
            "created": time.time(),
        }

    def check_answer(self, lesson: dict[str, Any], text: str) -> dict[str, Any]:
        answer = lesson.get("answer")
        if answer is None:
            result = {"correct": None, "feedback": lesson.get("explanation", "")}
            self._record_attempt(lesson, None)
            return result

        user_norm = _normalize_answer(text)
        answer_norm = _normalize_answer(answer)
        correct = bool(user_norm) and user_norm == answer_norm
        if correct:
            feedback = "Correct! " + str(lesson.get("explanation", ""))
        else:
            feedback = f"Not quite. Correct answer: {answer}. {lesson.get('explanation', '')}"

        # optional short feedback from engine (only if available and wrong)
        if (not correct) and self._engine is not None:
            try:
                engine = self._engine
                chat = getattr(engine, "chat", None) or engine
                if callable(chat):
                    fb_prompt = (
                        "A student answered an English exercise incorrectly. "
                        f"Question: {lesson.get('prompt')}\n"
                        f"Student answer: {text}\nCorrect answer: {answer}\n"
                        "Give one short friendly sentence of feedback (no markdown)."
                    )
                    extra = chat([{"role": "user", "content": fb_prompt}])
                    if isinstance(extra, str) and extra.strip():
                        feedback = extra.strip()[:200]
            except Exception:
                pass

        self._record_attempt(lesson, correct)
        return {"correct": correct, "feedback": feedback}

    def _record_attempt(self, lesson: dict[str, Any], correct: bool | None) -> None:
        if self._progress is None:
            self._load_progress()
        prog = self._progress
        if prog is None:
            return
        topic = lesson.get("topic", "Vocabulary")
        if topic not in prog["topics"]:
            prog["topics"][topic] = {"attempts": 0, "correct": 0}
        prog["topics"][topic]["attempts"] += 1
        prog["totals"]["attempts"] += 1
        if correct is True:
            prog["topics"][topic]["correct"] += 1
            prog["totals"]["correct"] += 1
            prog["streak"] = int(prog.get("streak", 0)) + 1
            prog["best_streak"] = max(int(prog.get("best_streak", 0)), prog["streak"])
        elif correct is False:
            prog["streak"] = 0
        prog["recent"].append(
            {"ts": time.time(), "topic": topic, "level": lesson.get("level"), "correct": correct}
        )
        prog["recent"] = prog["recent"][-50:]
        _atomic_write(self._progress_path, prog)
