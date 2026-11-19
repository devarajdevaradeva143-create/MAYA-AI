"""AI English Teacher service — lesson generation + SQLite progress.

Local-only. Uses the engine through an ``EnginePort``-shaped object and
persists per-lesson progress (completed, score, attempts, last_attempt_ts)
in a SQLite database under the offline memory folder
(``MAYA AI/memory/offline/teacher_progress.db`` by default).

Config (db location, engine settings) comes from ``settings.yaml`` — never
hardcoded. Tests can redirect the db via the ``progress_path`` / ``db_path``
constructor args or the ``MAYA_TEACHER_PROGRESS_DB`` env var.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT, load_settings

# ── Public constants ──────────────────────────────────────────────────
TOPICS = ("Vocabulary", "Grammar", "Pronunciation", "Idioms", "Conversation")
LEVELS = ("Beginner", "Intermediate", "Advanced")
LESSON_TYPES = ("grammar", "vocab", "conversation", "mixed")

ENV_DB_PATH = "MAYA_TEACHER_PROGRESS_DB"
DEFAULT_OFFLINE_MEMORY = "memory/offline"
DB_FILENAME = "teacher_progress.db"

# ── Fallback (static) lessons ──────────────────────────────────────────
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
    ("Conversation", "Beginner"): {
        "prompt": "Greet a new colleague politely in one sentence.",
        "answer": None,
        "explanation": "Try: 'Hi, nice to meet you — I'm glad to join the team.'",
    },
}


def _offline_memory_setting() -> str:
    settings = load_settings()
    if isinstance(settings, dict):
        memory = settings.get("memory")
        if isinstance(memory, dict):
            offline = memory.get("offline")
            if offline:
                return str(offline)
        offline = settings.get("memory_offline")
        if offline:
            return str(offline)
    return DEFAULT_OFFLINE_MEMORY


def _resolve_db_path(
    progress_path: Any = None, db_path: Any = None, progress_db: Any = None, db: Any = None
) -> Path:
    for candidate in (db_path, progress_db, db, progress_path, os.environ.get(ENV_DB_PATH)):
        if candidate:
            return Path(candidate).expanduser()
    memory_dir = Path(_offline_memory_setting())
    if not memory_dir.is_absolute():
        memory_dir = PROJECT_ROOT / "MAYA AI" / memory_dir
    return memory_dir / DB_FILENAME


def _normalize_answer(text: Any) -> str:
    if text is None:
        return ""
    text = str(text).strip().lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_lesson_json(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[^\n]*\n", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
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
    lowered = (prompt + " " + explanation).lower()
    if "spanish" in lowered or "french" in lowered or "german" in lowered:
        return None
    return {"prompt": prompt.strip(), "answer": answer, "explanation": explanation.strip()}


def _fallback_lesson(topic: str, level: str, lesson_type: str) -> dict[str, Any]:
    base = _FALLBACK.get((topic, level)) or _FALLBACK.get((topic, "Beginner")) or {
        "prompt": f"Practice {topic} at {level} level.",
        "answer": None,
        "explanation": "Keep practising.",
    }
    return {
        "id": f"fallback-{topic}-{level}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}",
        "topic": topic,
        "level": level,
        "type": lesson_type,
        "prompt": base["prompt"],
        "answer": base["answer"],
        "explanation": base["explanation"],
        "source": "fallback",
        "created": time.time(),
    }


class TeacherService:
    def __init__(
        self,
        engine: Any = None,
        progress_path: Any = None,
        db_path: Any = None,
        progress_db: Any = None,
        db: Any = None,
        database: Any = None,
        path: Any = None,
        progress_database: Any = None,
        **kwargs: Any,
    ) -> None:
        self._engine = engine
        candidates = [
            db_path, progress_db, db, database, path, progress_database,
            progress_path, os.environ.get(ENV_DB_PATH),
        ]
        candidates.extend(kwargs.values())
        resolved = None
        for c in candidates:
            if c:
                resolved = c
                break
        if resolved is None:
            self._db_path = _resolve_db_path(None, None, None, None)
        else:
            self._db_path = Path(resolved).expanduser()

    # ── db helpers ────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS lessons (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    level TEXT NOT NULL,
                    lesson_type TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    answer TEXT,
                    explanation TEXT,
                    source TEXT NOT NULL,
                    created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS progress (
                    lesson_id TEXT PRIMARY KEY,
                    completed INTEGER NOT NULL DEFAULT 0,
                    score INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_attempt_ts REAL
                );
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                CREATE TABLE IF NOT EXISTS attempts_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lesson_id TEXT NOT NULL,
                    ts REAL NOT NULL,
                    correct INTEGER
                );
                """
            )
            conn.commit()

    def _meta_get(self, conn: sqlite3.Connection, key: str, default: str = "0") -> str:
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row is not None else default

    def _meta_set(self, conn: sqlite3.Connection, key: str, value: Any) -> None:
        conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )

    def _store_lesson(self, lesson: dict[str, Any]) -> str:
        lid = lesson.get("id")
        if not lid:
            lid = f"ai-{uuid.uuid4().hex}"
            lesson["id"] = lid
        topic = str(lesson.get("topic", "Vocabulary"))
        level = str(lesson.get("level", "Beginner"))
        lesson_type = str(lesson.get("type") or lesson.get("lesson_type") or "mixed")
        prompt = str(lesson.get("prompt", ""))
        answer = lesson.get("answer")
        if answer is not None:
            answer = str(answer)
        explanation = lesson.get("explanation")
        if explanation is not None:
            explanation = str(explanation)
        source = str(lesson.get("source", "ai"))
        created = float(lesson.get("created", time.time()))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO lessons(id,topic,level,lesson_type,prompt,answer,explanation,source,created)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    topic=excluded.topic, level=excluded.level, lesson_type=excluded.lesson_type,
                    prompt=excluded.prompt, answer=excluded.answer, explanation=excluded.explanation,
                    source=excluded.source, created=excluded.created
                """,
                (lid, topic, level, lesson_type, prompt, answer, explanation, source, created),
            )
            # ensure progress row exists
            conn.execute(
                "INSERT OR IGNORE INTO progress(lesson_id,completed,score,attempts,last_attempt_ts) VALUES(?,0,0,0,NULL)",
                (lid,),
            )
            conn.commit()
        return lid

    def _load_lesson(self, lesson_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM lessons WHERE id=?", (lesson_id,)).fetchone()

    # ── EnginePort access ─────────────────────────────────────────────
    def _chat(self, messages: list[dict[str, str]]) -> Any:
        engine = self._engine
        if engine is None:
            return None
        chat = getattr(engine, "chat", None)
        if chat is None and callable(engine):
            chat = engine
        if not callable(chat):
            return None
        try:
            return chat(messages)
        except Exception:
            return None

    # ── Lesson generation ─────────────────────────────────────────────
    def generate_lesson(
        self, topic: str, level: str, lesson_type: str = "mixed"
    ) -> dict[str, Any]:
        topic = str(topic) if topic else "Vocabulary"
        if topic not in TOPICS:
            # keep unknown but default common
            topic = topic
        level = str(level) if level else "Beginner"
        if level not in LEVELS:
            level = level
        lesson_type = str(lesson_type) if lesson_type else "mixed"
        if lesson_type not in LESSON_TYPES:
            lesson_type = "mixed"

        raw = None
        if self._engine is not None:
            prompt = (
                "You are an English teacher. Create ONE English-learning exercise "
                f"for a {level} learner on the topic '{topic}' (lesson type: {lesson_type}). "
                "This is an English-learning exercise; do not translate into Spanish "
                "or any other language. Return compact JSON only with keys: "
                "prompt, answer, explanation. For Pronunciation or open-ended "
                "items the answer may be null."
            )
            messages = [{"role": "user", "content": prompt}]
            raw = self._chat(messages)

        parsed = _parse_lesson_json(raw) if isinstance(raw, str) else None
        if parsed is None:
            lesson = _fallback_lesson(topic, level, lesson_type)
        else:
            lesson = {
                "id": f"ai-{topic}-{level}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}",
                "topic": topic,
                "level": level,
                "type": lesson_type,
                "prompt": parsed["prompt"],
                "answer": parsed["answer"],
                "explanation": parsed["explanation"],
                "source": "ai",
                "created": time.time(),
            }

        self._store_lesson(lesson)
        return lesson

    # ── Answer checking ───────────────────────────────────────────────
    def check_answer(self, lesson_id: Any, user_answer: str) -> dict[str, Any]:
        # accept a lesson dict too
        lesson_dict: dict[str, Any] | None = None
        if isinstance(lesson_id, dict):
            lesson_dict = lesson_id
            lesson_id = lesson_dict.get("id")
            if not lesson_id:
                lesson_id = self._store_lesson(lesson_dict)
            else:
                self._store_lesson(lesson_dict)

        lid = str(lesson_id) if lesson_id is not None else ""
        row = self._load_lesson(lid) if lid else None

        # if no stored lesson, build from dict if available
        if row is None and lesson_dict is not None:
            lid = self._store_lesson(lesson_dict)
            row = self._load_lesson(lid)

        if row is None:
            # unknown lesson; cannot check
            return {"correct": None, "feedback": "Lesson not found.", "score": 0}

        answer = row["answer"]
        prompt = row["prompt"]
        explanation = row["explanation"] or ""
        topic = row["topic"]
        level = row["level"]

        if answer is None:
            result_correct: bool | None = None
            feedback = explanation
            score = 0
        else:
            user_norm = _normalize_answer(user_answer)
            answer_norm = _normalize_answer(answer)
            correct = bool(user_norm) and user_norm == answer_norm
            if correct:
                feedback = "Correct! " + str(explanation)
            else:
                feedback = f"Not quite. Correct answer: {answer}. {explanation}"
            result_correct = correct
            score = 100 if correct else 0

        # optional short feedback from engine (only if wrong)
        if result_correct is False and self._engine is not None:
            try:
                fb_prompt = (
                    "A student answered an English exercise incorrectly. "
                    f"Question: {prompt}\n"
                    f"Student answer: {user_answer}\nCorrect answer: {answer}\n"
                    "Give one short friendly sentence of feedback (no markdown)."
                )
                extra = self._chat([{"role": "user", "content": fb_prompt}])
                if isinstance(extra, str) and extra.strip():
                    feedback = extra.strip()[:200]
            except Exception:
                pass

        self._record_attempt(lid, topic, level, result_correct, score)
        return {"correct": result_correct, "feedback": feedback, "score": score}

    def _record_attempt(
        self, lesson_id: str, topic: str, level: str, correct: bool | None, score: int
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT completed, score, attempts FROM progress WHERE lesson_id=?", (lesson_id,)
            ).fetchone()
            if existing is None:
                completed = 1 if correct is True else 0
                best_score = score
                attempts = 1
            else:
                completed = int(existing["completed"]) or (1 if correct is True else 0)
                best_score = max(int(existing["score"]), score)
                attempts = int(existing["attempts"]) + 1
            conn.execute(
                """
                INSERT INTO progress(lesson_id,completed,score,attempts,last_attempt_ts)
                VALUES(?,?,?,?,?)
                ON CONFLICT(lesson_id) DO UPDATE SET
                    completed=excluded.completed,
                    score=excluded.score,
                    attempts=excluded.attempts,
                    last_attempt_ts=excluded.last_attempt_ts
                """,
                (lesson_id, int(completed), int(best_score), int(attempts), now),
            )
            conn.execute(
                "INSERT INTO attempts_log(lesson_id,ts,correct) VALUES(?,?,?)",
                (lesson_id, now, None if correct is None else (1 if correct else 0)),
            )
            # meta streak / correct count
            streak = int(self._meta_get(conn, "streak", "0"))
            best_streak = int(self._meta_get(conn, "best_streak", "0"))
            correct_count = int(self._meta_get(conn, "correct_count", "0"))
            if correct is True:
                streak += 1
                best_streak = max(best_streak, streak)
                correct_count += 1
            elif correct is False:
                streak = 0
            self._meta_set(conn, "streak", streak)
            self._meta_set(conn, "best_streak", best_streak)
            self._meta_set(conn, "correct_count", correct_count)
            conn.commit()

    # ── Progress ──────────────────────────────────────────────────────
    def get_progress(self, lesson_id: Any = None) -> dict[str, Any]:
        if isinstance(lesson_id, dict):
            lesson_id = lesson_id.get("id")
        if lesson_id is not None and str(lesson_id).strip():
            lid = str(lesson_id)
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT completed, score, attempts, last_attempt_ts FROM progress WHERE lesson_id=?",
                    (lid,),
                ).fetchone()
            if row is None:
                return {
                    "lesson_id": lid,
                    "completed": False,
                    "score": 0,
                    "attempts": 0,
                    "last_attempt_ts": None,
                }
            return {
                "lesson_id": lid,
                "completed": bool(row["completed"]),
                "score": int(row["score"]),
                "attempts": int(row["attempts"]),
                "last_attempt_ts": row["last_attempt_ts"],
            }

        # aggregate
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT lesson_id, completed, score, attempts, last_attempt_ts FROM progress"
            ).fetchall()
            streak = int(self._meta_get(conn, "streak", "0"))
            best_streak = int(self._meta_get(conn, "best_streak", "0"))
            correct_count = int(self._meta_get(conn, "correct_count", "0"))
            total_attempts = sum(int(r["attempts"]) for r in rows)
            # recent attempts
            recent_rows = conn.execute(
                "SELECT lesson_id, ts, correct FROM attempts_log ORDER BY id DESC LIMIT 50"
            ).fetchall()
            # topics aggregate
            topic_stats: dict[str, dict[str, int]] = {}
            for t in TOPICS:
                topic_stats[t] = {"attempts": 0, "correct": 0}
            # map lesson -> topic
            lesson_topics = {
                r["id"]: r["topic"]
                for r in conn.execute("SELECT id, topic FROM lessons").fetchall()
            }
            for r in rows:
                tid = r["lesson_id"]
                topic = lesson_topics.get(tid, "Vocabulary")
                if topic not in topic_stats:
                    topic_stats[topic] = {"attempts": 0, "correct": 0}
                topic_stats[topic]["attempts"] += int(r["attempts"])
            # correct per topic from attempts_log
            for ar in conn.execute("SELECT lesson_id, correct FROM attempts_log").fetchall():
                tid = ar["lesson_id"]
                topic = lesson_topics.get(tid, "Vocabulary")
                if topic not in topic_stats:
                    topic_stats[topic] = {"attempts": 0, "correct": 0}
                if ar["correct"] == 1:
                    topic_stats[topic]["correct"] += 1

            lessons_list = []
            for r in rows:
                lessons_list.append(
                    {
                        "lesson_id": r["lesson_id"],
                        "completed": bool(r["completed"]),
                        "score": int(r["score"]),
                        "attempts": int(r["attempts"]),
                        "last_attempt_ts": r["last_attempt_ts"],
                    }
                )

        recent = []
        for ar in recent_rows:
            lid = ar["lesson_id"]
            topic = lesson_topics.get(lid, "Vocabulary")
            # find level
            level = "Beginner"
            lrow = self._load_lesson(lid)
            if lrow is not None:
                level = lrow["level"]
            recent.append(
                {
                    "ts": ar["ts"],
                    "topic": topic,
                    "level": level,
                    "correct": (None if ar["correct"] is None else bool(ar["correct"])),
                }
            )

        return {
            "version": 1,
            "totals": {"attempts": total_attempts, "correct": correct_count},
            "streak": streak,
            "best_streak": best_streak,
            "topics": topic_stats,
            "recent": recent,
            "lessons": lessons_list,
            "completed": sum(1 for r in rows if r["completed"]),
            "total_lessons": len(rows),
        }

    def mark_complete(self, lesson_id: Any, score: int) -> dict[str, Any]:
        if isinstance(lesson_id, dict):
            lesson_id = lesson_id.get("id")
            if lesson_id is None:
                return {"lesson_id": None, "completed": False, "score": 0, "attempts": 0, "last_attempt_ts": None}
        lid = str(lesson_id)
        now = time.time()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT attempts FROM progress WHERE lesson_id=?", (lid,)
            ).fetchone()
            attempts = int(existing["attempts"]) if existing is not None else 0
            conn.execute(
                """
                INSERT INTO progress(lesson_id,completed,score,attempts,last_attempt_ts)
                VALUES(?,?,?, ?,?)
                ON CONFLICT(lesson_id) DO UPDATE SET
                    completed=1, score=excluded.score, attempts=excluded.attempts, last_attempt_ts=excluded.last_attempt_ts
                """,
                (lid, 1, int(score), attempts, now),
            )
            conn.commit()
        return self.get_progress(lid)

    def reset_progress(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM progress")
            conn.execute("DELETE FROM attempts_log")
            conn.execute("DELETE FROM meta")
            conn.commit()

    # ── Back-compat alias used by windows adapter / UI ────────────────
    def progress(self) -> dict[str, Any]:
        return self.get_progress(None)