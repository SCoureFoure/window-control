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
  human sees it, but capture never does. It therefore coexists with `--grid`,
  which is burned into the captured image instead.
- The window is frameless, translucent, always-on-top, and click-through, so
  it blocks neither the human nor the agent's own synthesized clicks.

PyQt6 is imported lazily inside `start()` so the rest of the project (tests,
headless runs, `--list-lenses`) works without a display or PyQt6 installed.
The Qt event loop runs on a dedicated daemon thread that owns the
QApplication; the orchestrator only ever calls `set_state()` / `stop()`, which
touch a plain attribute (atomic in CPython) and never a Qt object.
"""

from __future__ import annotations

import threading

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


class AccessBorder:
    """Run-scoped status border driven from the orchestrator loop."""

    def __init__(self, lens: Lens, thickness: int = BAND_THICKNESS):
        self.lens = lens
        self.thickness = thickness
        self._state = "watching"
        self._thread: threading.Thread | None = None
        self._app = None
        self._widget = None
        self._ready = threading.Event()

    def set_state(self, state: str) -> None:
        """Switch the band color. Safe to call from any thread."""
        self._state = state

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="access-border", daemon=True)
        self._thread.start()
        # Wait briefly for the window to appear so it's up before step 1.
        self._ready.wait(timeout=2.0)

    def stop(self) -> None:
        app = self._app
        if app is not None:
            # quit() is thread-safe; it unblocks exec() on the border thread.
            app.quit()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    # ----- border thread -----

    def _run(self) -> None:
        # Any failure in the border thread (missing display, PyQt6 not
        # installed, Qt refusing a QApplication off the main thread) must
        # degrade to "no border" — never an unhandled thread exception that
        # crashes the host process. _ready is always released so start()'s
        # bounded wait never blocks the full timeout on failure.
        try:
            self._run_qt()
        except Exception as exc:  # noqa: BLE001 - UX aid must never crash the run
            print(f"  [border] disabled (thread error: {exc})")
        finally:
            self._ready.set()

    def _run_qt(self) -> None:
        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtGui import QColor, QPainter
        from PyQt6.QtWidgets import QApplication, QWidget

        thickness = self.thickness
        get_state = lambda: self._state  # noqa: E731

        class Border(QWidget):
            def __init__(self, lens: Lens):
                super().__init__()
                self.setWindowFlags(
                    Qt.WindowType.FramelessWindowHint
                    | Qt.WindowType.WindowStaysOnTopHint
                    | Qt.WindowType.Tool
                    | Qt.WindowType.WindowTransparentForInput
                )
                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseInput, True)
                vg = QApplication.primaryScreen().virtualGeometry()
                self.setGeometry(vg)
                self._origin = (vg.x(), vg.y())
                self._lens_rect = (lens.x, lens.y, lens.w, lens.h)
                self._last_state: str | None = None

            def paintEvent(self, _e) -> None:  # noqa: N802
                p = QPainter(self)
                p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                r, g, b, a = _COLORS.get(get_state(), _COLORS["watching"])
                color = QColor(r, g, b, a)
                for bx, by, bw, bh in band_rects(self._lens_rect, thickness, self._origin):
                    p.fillRect(bx, by, bw, bh, color)

            def poll(self) -> None:
                s = get_state()
                if s != self._last_state:
                    self._last_state = s
                    self.update()

        self._app = QApplication.instance() or QApplication([])
        self._widget = Border(self.lens)
        self._widget.show()
        self._widget.raise_()

        timer = QTimer()
        timer.timeout.connect(self._widget.poll)
        timer.start(40)

        self._ready.set()
        self._app.exec()
