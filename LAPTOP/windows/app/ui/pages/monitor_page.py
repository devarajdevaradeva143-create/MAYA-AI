"""Monitoring page — CPU / RAM / GPU / NPU / battery cards + sparklines + disk usage (Phase 6)."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.monitor_service import MonitorAdapter


class MonitorCard(QFrame):
    """A single stats card: label + value + small sparkline spark."""

    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { border-radius: 8px; background-color: #14141c; margin: 4px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self._title = QLabel(title)
        self._title.setObjectName("cardLabel")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title)

        self._value = QLabel(subtitle)
        self._value.setObjectName("cardValue")
        self._value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._value)

        self._spark = QLabel("—")
        self._spark.setObjectName("cardSpark")
        self._spark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._spark)

    def update_values(self, title: str, value: str, spark: str) -> None:
        self._title.setText(title)
        self._value.setText(value)
        self._spark.setText(spark)


class MonitorPage(QWidget):
    """Maya monitoring page: live system stats cards + disk list + uptime."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._monitor = MonitorAdapter()

        # History for tiny sparklines (last 30 readings)
        self._history: dict[str, deque[float]] = {
            "cpu": deque(maxlen=30),
            "ram": deque(maxlen=30),
        }
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        # timer started in showEvent; stopped in hideEvent (no polling when hidden)

        self._build_ui()
        self._refresh()

    # -- ui -----------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 8)
        layout.setSpacing(12)

        # --- Stats grid ---
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        self._cards: dict[str, MonitorCard] = {}
        card_defs = [
            ("CPU", "0%", "0%"),
            ("RAM", "0/0 GB", "0%"),
            ("GPU", "Unknown GPU", "—"),
            ("NPU", "Unknown NPU", "—"),
            ("Battery", "0%", "—"),
            ("Uptime", "0 s", "—"),
        ]
        for i, (title, value, _) in enumerate(card_defs):
            row, col = divmod(i, 3)
            card = MonitorCard(title, value)
            grid.addWidget(card, row, col)
            self._cards[title] = card

        layout.addLayout(grid, 1)

        # --- Disk usage list ---
        left = QVBoxLayout()
        left.setContentsMargins(24, 0, 12, 0)
        left.setSpacing(6)

        self._disk_label = QLabel("Disk usage")
        self._disk_label.setObjectName("emptyHint")
        left.addWidget(self._disk_label)

        self._disk_view = QPlainTextEdit()
        self._disk_view.setReadOnly(True)
        self._disk_view.setMaximumHeight(120)
        self._disk_view.setPlainText("")
        left.addWidget(self._disk_view)

        left.addStretch(1)
        layout.addLayout(left, 0)

        # Connect signal
        self._update_cards_from_snapshot()

    # -- lifecycle ----------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt signature
        if not self._timer.isActive():
            self._timer.start(2000)
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt signature
        self._timer.stop()
        super().hideEvent(event)

    # -- refresh ------------------------------------------------------

    def _refresh(self) -> None:
        snap = self._monitor.snapshot()

        # --- Cards ---
        cpu_pct = snap.get("cpu", {}).get("percent")
        cpu_str = f"{cpu_pct}%" if cpu_pct is not None else "—"
        if cpu_pct is not None:
            self._cards["CPU"].update_values("CPU", cpu_str, "█" * int(float(cpu_pct) / 5))
            self._history["cpu"].append(float(cpu_pct))

        ram_pct = snap.get("ram", {}).get("percent")
        ram_total = snap.get("ram", {}).get("total_gb")
        ram_used = snap.get("ram", {}).get("used_gb")
        ram_str = f"{ram_used}/{ram_total} GB" if ram_total is not None else "—"
        if ram_pct is not None:
            self._cards["RAM"].update_values("RAM", ram_str, "█" * int(float(ram_pct) / 5))
            self._history["ram"].append(float(ram_pct))

        # --- GPU ---
        gpu_name = snap.get("gpu", {}).get("name") or "Unknown GPU"
        gpu_util = snap.get("gpu", {}).get("percent")
        gpu_str = gpu_name if gpu_util is None else f"{gpu_name} ({gpu_util}%)"

        # --- NPU ---
        npu_name = snap.get("npu", {}).get("name") or "Unknown NPU"
        npu_util = snap.get("npu", {}).get("percent")
        npu_str = npu_name if npu_util is None else f"{npu_name} ({npu_util}%)"

        # --- Battery ---
        bat_pct = snap.get("battery", {}).get("percent")
        bat_str = f"{bat_pct}%" if bat_pct is not None else "—"
        bat_plugged = snap.get("battery", {}).get("plugged")
        if bat_plugged is not None:
            bat_str += " ⚡" if bat_plugged else " 🔋"

        # --- Uptime ---
        uptime_s = snap.get("uptime_s", 0)
        try:
            uptime_str = f"{int(uptime_s)} s"
        except (TypeError, ValueError):
            uptime_str = "—"

        # --- Disks ---
        disks = snap.get("disks", [])
        disk_lines = []
        for d in disks:
            disk_lines.append(
                f"{d.get('mount', '?')}: {d.get('used_gb', '?')}/{d.get('total_gb', '?')} GB ({d.get('percent', '?')}%)"
            )
        disk_text = "\n".join(disk_lines) if disk_lines else "No disk info"

        # Update cards
        cpu_bar = "█" * int(float(cpu_pct or 0) / 5) if cpu_pct is not None else "—"
        ram_bar = "█" * int(float(ram_pct or 0) / 5) if ram_pct is not None else "—"
        self._cards["CPU"].update_values("CPU", cpu_str, cpu_bar)
        self._cards["RAM"].update_values("RAM", ram_str, ram_bar)
        self._cards["GPU"].update_values("GPU", gpu_str, "—")
        self._cards["NPU"].update_values("NPU", npu_str, "—")
        self._cards["Battery"].update_values("Battery", bat_str, "—")
        self._cards["Uptime"].update_values("Uptime", uptime_str, "—")

        # Disk list
        self._disk_view.setPlainText(disk_text)

    def _update_cards_from_snapshot(self) -> None:
        """Initial populating from a first snapshot."""
        try:
            self._refresh()
        except Exception:
            pass