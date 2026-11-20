"""Structural tests for the Fedora remote adapters.

These run on any OS with the JARVIS venv: hardware-specific calls are guarded by
``sys.platform`` and are asserted to fail closed off Linux. Real screen/input
behaviour must still be validated on Fedora hardware.
"""

from __future__ import annotations

import sys

import pytest

from app.services.remote_service import HybridAdapter, InputAdapter, ScreenAdapter


class FakeController:
    def status(self):  # noqa: ANN201
        return {"mode": "user"}

    def list_tasks(self):  # noqa: ANN201
        return [{"id": "t1"}]

    def takeover(self, who):  # noqa: ANN001, ANN201
        return who == "user"

    def release(self, who):  # noqa: ANN001, ANN201
        return who == "user"


def test_hybrid_adapter_delegates_to_controller() -> None:
    adapter = HybridAdapter(FakeController())  # type: ignore[arg-type]

    assert adapter.status() == {"mode": "user"}
    assert adapter.list_tasks() == [{"id": "t1"}]
    assert adapter.takeover() is True
    assert adapter.release() is True


def test_hybrid_adapter_builds_default_controller() -> None:
    adapter = HybridAdapter()
    assert adapter.controller is not None
    status = adapter.status()
    assert hasattr(status, "controller")
    assert adapter.list_tasks() == []


def test_availability_reflects_platform() -> None:
    expected = sys.platform == "linux"
    assert ScreenAdapter.available() is expected
    assert InputAdapter.available() is expected


@pytest.mark.skipif(sys.platform == "linux", reason="Linux-only capture")
def test_screen_capture_fails_closed_off_linux() -> None:
    with pytest.raises(RuntimeError):
        ScreenAdapter().capture()


@pytest.mark.skipif(sys.platform == "linux", reason="Linux-only input")
def test_input_apply_fails_closed_off_linux() -> None:
    with pytest.raises(RuntimeError):
        InputAdapter().apply([{"type": "move", "x": 0.5, "y": 0.5}])
