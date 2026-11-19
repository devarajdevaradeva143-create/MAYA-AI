"""Maya AI Hybrid Mode Controller.

Implements HYBRID MODE (spec: docs/REQUIREMENTS.md):
    - User (remote/mobile) and MAYA AI work simultaneously.
    - Direct user control + AI autonomous work.
    - User can take over control at any time.
    - No control conflicts: user always wins; AI yields.
    - Live monitoring of AI work.

This module is the laptop-side control bus. It is LOCAL only.
It coordinates who currently "owns" control (user vs ai) and queues AI
tasks so they never fight the user for input.

Design:
    - Thread-safe (RLock).
    - Controller ids: "user" (remote human) and "ai" (Maya).
    - Priority: user > ai. AI can only act when it holds control OR when
      no user control is active (opportunistic).
    - Takeover: user can force-acquire instantly; pending AI tasks pause.
    - Tasks: AI queues tasks; they execute only when AI holds control.
    - Events: listeners notified on control change / task state.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class Controller(str, Enum):
    NONE = "none"
    USER = "user"
    AI = "ai"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Task:
    id: str
    description: str
    status: TaskStatus = TaskStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class HybridStatus:
    controller: Controller
    ai_busy: bool
    queued_tasks: int
    running_task: Optional[str]
    conflicts: int
    last_takeover: Optional[float]
    uptime_s: float

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["controller"] = self.controller.value
        return d


class HybridController:
    """Control bus for hybrid mode."""

    def __init__(self, sleep_fn: Callable[[float], None] = time.sleep) -> None:
        self._lock = threading.RLock()
        self._sleep = sleep_fn
        self._controller: Controller = Controller.NONE
        self._controller_since: float = time.time()
        self._tasks: Dict[str, Task] = {}
        self._task_order: List[str] = []
        self._running: Optional[str] = None
        self._conflicts: int = 0
        self._last_takeover: Optional[float] = None
        self._started: float = time.time()
        self._listeners: List[Callable[[HybridStatus], None]] = []
        self._ai_paused: bool = False

    # -- events --

    def on_status_change(self, fn: Callable[[HybridStatus], None]) -> None:
        with self._lock:
            self._listeners.append(fn)

    def _emit(self) -> None:
        snap = self.status()
        for fn in list(self._listeners):
            try:
                fn(snap)
            except Exception:
                pass

    # -- control --

    def acquire(self, controller: Controller, timeout: float = 0.0) -> bool:
        """Request control. Returns True if granted."""
        if controller == Controller.NONE:
            return False
        with self._lock:
            # user always wins
            if controller == Controller.USER:
                if self._controller == Controller.AI:
                    self._conflicts += 1
                    # pause AI
                    self._ai_paused = True
                    if self._running:
                        t = self._tasks.get(self._running)
                        if t:
                            t.status = TaskStatus.CANCELLED
                            t.finished_at = time.time()
                        self._running = None
                self._controller = Controller.USER
                self._controller_since = time.time()
                self._last_takeover = time.time()
                self._emit()
                return True
            # AI requests control
            if self._controller in (Controller.NONE,):
                self._controller = Controller.AI
                self._controller_since = time.time()
                self._ai_paused = False
                self._emit()
                return True
            if self._controller == Controller.AI:
                return True  # already
            # user holds control -> AI cannot acquire
            self._conflicts += 1
            return False

    def release(self, controller: Controller) -> bool:
        with self._lock:
            if self._controller != controller:
                return False
            self._controller = Controller.NONE
            self._controller_since = time.time()
            if controller == Controller.AI:
                self._ai_paused = False
            self._emit()
            return True

    def takeover(self, controller: Controller = Controller.USER) -> bool:
        """Force takeover (default user)."""
        return self.acquire(controller)

    def current_controller(self) -> Controller:
        with self._lock:
            return self._controller

    def is_controlled_by(self, controller: Controller) -> bool:
        with self._lock:
            return self._controller == controller

    # -- tasks (AI side) --

    def queue_task(self, description: str) -> str:
        """Queue an AI task. Returns task id."""
        tid = "t_" + uuid.uuid4().hex[:8]
        with self._lock:
            self._tasks[tid] = Task(id=tid, description=description)
            self._task_order.append(tid)
        self._emit()
        return tid

    def next_task(self) -> Optional[Task]:
        """Pop next queued task for AI execution (only if AI holds control)."""
        with self._lock:
            if self._controller != Controller.AI or self._ai_paused:
                return None
            if self._running is not None:
                return None
            for tid in self._task_order:
                t = self._tasks.get(tid)
                if t and t.status == TaskStatus.QUEUED:
                    t.status = TaskStatus.RUNNING
                    t.started_at = time.time()
                    self._running = tid
                    self._emit()
                    return t
            return None

    def complete_task(self, task_id: str, result: str = "", ok: bool = True) -> bool:
        with self._lock:
            t = self._tasks.get(task_id)
            if not t:
                return False
            t.status = TaskStatus.DONE if ok else TaskStatus.FAILED
            if not ok:
                t.error = result
            else:
                t.result = result
            t.finished_at = time.time()
            if self._running == task_id:
                self._running = None
            self._emit()
            return True

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            t = self._tasks.get(task_id)
            if not t:
                return False
            if t.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return False
            t.status = TaskStatus.CANCELLED
            t.finished_at = time.time()
            if self._running == task_id:
                self._running = None
            self._emit()
            return True

    def cancel_all_ai(self) -> int:
        """Cancel all queued/running AI tasks (user takeover)."""
        n = 0
        with self._lock:
            for tid, t in self._tasks.items():
                if t.status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
                    t.status = TaskStatus.CANCELLED
                    t.finished_at = time.time()
                    n += 1
            self._running = None
            self._ai_paused = True
        self._emit()
        return n

    def list_tasks(self) -> List[Task]:
        with self._lock:
            return [self._tasks[tid] for tid in self._task_order if tid in self._tasks]

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    # -- monitoring --

    def status(self) -> HybridStatus:
        with self._lock:
            running_id = self._running
            return HybridStatus(
                controller=self._controller,
                ai_busy=self._running is not None,
                queued_tasks=sum(1 for t in self._tasks.values()
                                if t.status == TaskStatus.QUEUED),
                running_task=running_id,
                conflicts=self._conflicts,
                last_takeover=self._last_takeover,
                uptime_s=time.time() - self._started,
            )

    def summary(self) -> Dict[str, Any]:
        s = self.status()
        return {
            "status": s.to_dict(),
            "tasks": [t.to_dict() for t in self.list_tasks()],
        }

    # -- helpers for AI opportunistic work --

    def ai_can_act(self) -> bool:
        """True if AI is allowed to perform an action right now."""
        with self._lock:
            if self._ai_paused:
                return False
            if self._controller == Controller.USER:
                return False
            return True

    def reset(self) -> None:
        with self._lock:
            self._controller = Controller.NONE
            self._tasks.clear()
            self._task_order.clear()
            self._running = None
            self._conflicts = 0
            self._ai_paused = False
            self._started = time.time()
        self._emit()
