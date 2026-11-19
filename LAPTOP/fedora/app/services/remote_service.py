"""Remote screen / input adapters for the phone server (Fedora/Linux).

Only the Fedora app imports this module. `custom.server` stays headless and
talks to these adapters through the ports in `custom.server.contracts`.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
from typing import Any

from custom.server.contracts import ScreenFrame


class ScreenAdapter:
    """Capture the Linux desktop as a resized JPEG frame using maim or scrot."""

    @staticmethod
    def available() -> bool:
        return sys.platform == "linux"

    def capture(self, *, max_width: int = 1280, quality: int = 60) -> ScreenFrame:
        if sys.platform != "linux":
            raise RuntimeError("Screen capture is Linux-only right now")

        try:
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - shipped with the app
            raise RuntimeError("Pillow is not installed") from exc

        # Try maim first (preferred for Wayland/X11), fall back to scrot
        screenshot_bytes = self._capture_screenshot()

        image = Image.open(io.BytesIO(screenshot_bytes))
        if image.width > max_width:
            height = max(1, round(image.height * max_width / image.width))
            resample = getattr(Image, "Resampling", Image).LANCZOS
            image = image.resize((max_width, height), resample)

        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)

        return ScreenFrame(
            data=buffer.getvalue(),
            media_type="image/jpeg",
            width=image.width,
            height=image.height,
        )

    def _capture_screenshot(self) -> bytes:
        """Capture screenshot using maim or scrot."""
        # Try maim first (supports Wayland via wlroots, and X11)
        maim_path = shutil.which("maim")
        if maim_path:
            try:
                result = subprocess.run(
                    [maim_path, "-f", "png", "-u"],  # -u = include cursor
                    capture_output=True,
                    check=True,
                    timeout=5,
                )
                return result.stdout
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass

        # Fall back to scrot (X11 only)
        scrot_path = shutil.which("scrot")
        if scrot_path:
            try:
                result = subprocess.run(
                    [scrot_path, "-z", "-o", "-"],  # -z = silent, -o = stdout, - = stdout
                    capture_output=True,
                    check=True,
                    timeout=5,
                )
                return result.stdout
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass

        raise RuntimeError(
            "No screenshot tool found. Install 'maim' (preferred, supports Wayland) "
            "or 'scrot' (X11 only)."
        )


# -- Linux input injection ----------------------------------------------------


class InputAdapter:
    """Mouse + keyboard injection for REMOTE/HYBRID mode using xdotool."""

    @staticmethod
    def available() -> bool:
        return sys.platform == "linux"

    def _require_linux(self) -> None:
        if sys.platform != "linux":
            raise RuntimeError("Remote input is Linux-only right now")

    def _require_xdotool(self) -> str:
        xdotool_path = shutil.which("xdotool")
        if not xdotool_path:
            raise RuntimeError("xdotool not found. Install it: sudo dnf install xdotool")
        return xdotool_path

    def _screen_size(self) -> tuple[int, int]:
        """Get screen resolution using xrandr or xdotool."""
        # Try xrandr first
        xrandr_path = shutil.which("xrandr")
        if xrandr_path:
            try:
                result = subprocess.run(
                    [xrandr_path, "--current"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=3,
                )
                for line in result.stdout.splitlines():
                    if " connected" in line and "*" in line:
                        # Example: "1920x1080    60.00*+"
                        parts = line.split()
                        for part in parts:
                            if "x" in part and "*" in part:
                                res = part.replace("*", "")
                                width, height = res.split("x")
                                return int(width), int(height)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
                pass

        # Fallback: use xdotool getdisplaygeometry
        xdotool = self._require_xdotool()
        try:
            result = subprocess.run(
                [xdotool, "getdisplaygeometry"],
                capture_output=True,
                text=True,
                check=True,
                timeout=3,
            )
            width, height = result.stdout.strip().split()
            return int(width), int(height)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
            pass

        # Last resort: assume 1920x1080
        return 1920, 1080

    def _run_xdotool(self, *args: str) -> None:
        xdotool = self._require_xdotool()
        subprocess.run(
            [xdotool, *args],
            check=True,
            timeout=3,
            capture_output=True,
        )

    def apply(self, events: list[dict[str, Any]]) -> int:
        self._require_linux()
        applied = 0

        for event in events:
            kind = event.get("type")

            if kind == "move":
                width, height = self._screen_size()
                x = int(float(event["x"]) * (width - 1))
                y = int(float(event["y"]) * (height - 1))
                self._run_xdotool("mousemove", str(x), str(y))

            elif kind == "click":
                button = event.get("button", "left")
                button_map = {"left": "1", "right": "3", "middle": "2"}
                btn = button_map.get(button, "1")
                self._run_xdotool("click", btn)

            elif kind == "scroll":
                dy = int(event.get("dy", 0))
                # xdotool scroll: 4 = up, 5 = down
                button = "4" if dy > 0 else "5"
                clicks = abs(dy)
                for _ in range(clicks):
                    self._run_xdotool("click", button)

            elif kind == "text":
                text = str(event.get("text", ""))
                # xdotool type handles Unicode and special chars
                self._run_xdotool("type", "--clearmodifiers", text)

            elif kind == "key":
                key = str(event.get("key", ""))
                # xdotool key handles combos like "ctrl+c", "alt+tab"
                self._run_xdotool("key", "--clearmodifiers", key)

            else:
                raise RuntimeError(f"Unsupported input event: {kind}")

            applied += 1

        return applied


__all__ = ["InputAdapter", "ScreenAdapter"]