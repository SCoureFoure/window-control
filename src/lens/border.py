"""Access-status border — a persistent frame around the lens during a run.

Shows the human when the agent has access to the screen and when it is
actively synthesizing input:

    watching  -> amber band   (run active, observing the lens between steps)
    acting    -> red band     (emitting a click / type / drag right now)

Design constraints (mirror CLAUDE.md invariants):

- The band is a UX aid, not functional. Like the grid (#4), it never changes
  what the agent can do.
- It must NOT pollute the screenshot. `mss` grabs exactly the lens rect
  (x, y, w, h); the band is drawn as four rects that lie entirely OUTSIDE that
  rect (inner edge flush with the lens boundary, extending outward). So the
  human sees it, but capture never does. It coexists with `--grid`, which is
  burned into the captured image instead.
- The window is frameless, translucent, always-on-top, and click-through, so
  it blocks neither the human nor the agent's own synthesized clicks.

Why a subprocess, not a thread: PyQt6's QApplication must run on the process's
main thread. Running it on a background thread segfaults the interpreter at
shutdown on Windows. So the border lives in a **child process** that owns its
own QApplication on its own main thread; the orchestrator (parent) signals
state by writing a tiny state file the child polls, and terminates the child on
exit. Process teardown is clean — no in-process Qt state to crash on.

The child is this same module run as `python -m src.lens.border <statefile>
<x> <y> <w> <h> <thickness>`. PyQt6 is imported only in the child entry point,
so importing this module (tests, headless runs) never needs a display.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time

from src.lens.model import Lens

BAND_THICKNESS = 8

# state -> RGBA
_COLORS = {
    "watching": (255, 176, 0, 235),   # amber
    "acting": (230, 30, 30, 245),     # red
}


def band_rects(
    lens_rect: tuple[int, int, int, int],
    thickness: int,
    origin: tuple[int, int] = (0, 0),
) -> list[tuple[int, int, int, int]]:
    """Four rects forming a frame just OUTSIDE the lens rect.

    Every returned rect is disjoint from ``lens_rect`` — the inner edge sits on
    the lens boundary and the band extends outward by ``thickness``. ``origin``
    (the top-left of the drawing surface, e.g. the virtual-desktop origin) is
    subtracted so the result is in surface-local coordinates.

    Returned as (x, y, w, h) tuples, matching the project's rect convention.
    """
    x, y, w, h = lens_rect
    ox, oy = origin
    x -= ox
    y -= oy
    t = thickness
    return [
        (x - t, y - t, w + 2 * t, t),   # top
        (x - t, y + h, w + 2 * t, t),   # bottom
        (x - t, y, t, h),               # left
        (x + w, y, t, h),               # right
    ]


def _write_state(path: str, state: str) -> None:
    """Write the current state atomically-enough for a 40ms poller."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(state)


def _read_state(path: str, default: str = "watching") -> str:
    """Read the state file; return ``default`` on any read error (mid-write)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            s = f.read().strip()
        return s or default
    except OSError:
        return default


class AccessBorder:
    """Run-scoped status border driven from the orchestrator loop.

    Owns a child process; every method is a no-op-safe wrapper so a failure to
    launch (no display, PyQt6 missing) degrades to "no border" and never
    interferes with the run.
    """

    def __init__(self, lens: Lens, thickness: int = BAND_THICKNESS):
        self.lens = lens
        self.thickness = thickness
        self._proc: subprocess.Popen | None = None
        self._state_path: str | None = None

    def start(self) -> None:
        try:
            fd, path = tempfile.mkstemp(prefix="wc-border-", suffix=".state")
            os.close(fd)
            self._state_path = path
            _write_state(path, "watching")
            args = [
                sys.executable, "-m", "src.lens.border",
                path,
                str(self.lens.x), str(self.lens.y), str(self.lens.w), str(self.lens.h),
                str(self.thickness),
            ]
            kwargs: dict = {}
            # Suppress the child's console window on Windows.
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            self._proc = subprocess.Popen(args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - UX aid must never break the run
            print(f"  [border] disabled (spawn error: {exc})")
            self._cleanup_state()

    def set_state(self, state: str) -> None:
        """Switch the band color. Safe to call any time; no-op if not running."""
        if self._state_path is None:
            return
        try:
            _write_state(self._state_path, state)
        except OSError:
            pass

    def stop(self) -> None:
        proc = self._proc
        if proc is not None:
            self.set_state("stop")
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self._cleanup_state()

    def _cleanup_state(self) -> None:
        if self._state_path is not None:
            try:
                os.remove(self._state_path)
            except OSError:
                pass
            self._state_path = None


def _child_main(argv: list[str]) -> int:
    """Child entry point: draw the band, poll the state file on the main thread."""
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QColor, QPainter
    from PyQt6.QtWidgets import QApplication, QWidget

    state_path = argv[0]
    x, y, w, h, thickness = (int(v) for v in argv[1:6])
    lens_rect = (x, y, w, h)

    class Border(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowTransparentForInput
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            vg = QApplication.primaryScreen().virtualGeometry()
            self.setGeometry(vg)
            self._origin = (vg.x(), vg.y())
            self._state = "watching"

        def paintEvent(self, _e) -> None:  # noqa: N802
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            r, g, b, a = _COLORS.get(self._state, _COLORS["watching"])
            color = QColor(r, g, b, a)
            for bx, by, bw, bh in band_rects(lens_rect, thickness, self._origin):
                p.fillRect(bx, by, bw, bh, color)

        def poll(self) -> None:
            s = _read_state(state_path)
            if s == "stop":
                QApplication.quit()
                return
            if s != self._state:
                self._state = s
                self.update()

    app = QApplication.instance() or QApplication([])
    widget = Border()
    widget.show()
    widget.raise_()

    timer = QTimer()
    timer.timeout.connect(widget.poll)
    timer.start(40)

    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(_child_main(sys.argv[1:]))
    except Exception as exc:  # noqa: BLE001 - child failure must not surface as a crash
        # Parent tolerates the child dying; exit quietly.
        print(f"[border-child] {exc}", file=sys.stderr)
        sys.exit(1)
