"""Interactive lens editor — PyQt6 frameless transparent always-on-top window.

Usage:
    from src.lens.overlay import edit_lens
    lens = edit_lens(existing_lens_or_none, name="default")

The window shows a red border around the lens rect with eight drag handles
(four corners, four edge midpoints). Drag a handle to resize. Drag the body
to move. Press Enter to confirm and save. Press Esc to cancel.

This module imports PyQt6 lazily so the rest of the project can be used
(tests, headless runs) without PyQt6 installed.
"""

from __future__ import annotations

from src.lens.model import Lens

HANDLE_SIZE = 12
BORDER_WIDTH = 2
MIN_DIMENSION = 50
DEFAULT_RECT = (200, 200, 800, 600)


def edit_lens(existing: Lens | None, name: str = "default") -> Lens | None:
    """Open the overlay editor. Returns the new Lens or None if cancelled."""
    import os

    # coords.set_per_monitor_dpi_aware() already made the process
    # PER_MONITOR_AWARE_V2 before Qt starts, so Qt's own attempt to set the
    # same context returns "Access is denied" and logs a warning. The result
    # is identical (our awareness stands), so silence just that log category.
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.window.warning=false")

    from PyQt6.QtCore import Qt, QRect, QPoint
    from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QKeyEvent, QMouseEvent
    from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QPushButton

    class LensOverlay(QWidget):
        def __init__(self, rect: QRect, label: str):
            super().__init__()
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            screen = QApplication.primaryScreen().virtualGeometry()
            self.setGeometry(screen)
            self.rect_ = rect
            self.label = label
            self.dragging: str | None = None
            self.drag_start: QPoint | None = None
            self.rect_start: QRect | None = None
            self.confirmed: bool = False
            self.help = QLabel(
                "Drag the box or its handles to position the lens. "
                "Enter = save  ·  Esc = cancel",
                self,
            )
            self.help.setStyleSheet(
                "background: rgba(0,0,0,180); color: white; padding: 6px 10px; "
                "font: 12pt 'Segoe UI'; border-radius: 4px;"
            )
            self.help.adjustSize()
            self.help.move(20, 20)
            # Clickable Save / Cancel buttons. A frameless translucent Tool
            # window does not reliably take keyboard focus on Windows, so
            # Enter/Esc may never fire — the buttons are the dependable path.
            btn_css = (
                "QPushButton {{ background: {bg}; color: white; border: none; "
                "padding: 8px 18px; font: 12pt 'Segoe UI'; border-radius: 4px; }}"
                "QPushButton:hover {{ background: {hov}; }}"
            )
            self.save_btn = QPushButton("Save (Enter)", self)
            self.save_btn.setStyleSheet(btn_css.format(bg="#1e7e34", hov="#28a745"))
            self.save_btn.adjustSize()
            self.save_btn.move(20, 20 + self.help.height() + 8)
            self.save_btn.clicked.connect(self._confirm)
            self.cancel_btn = QPushButton("Cancel (Esc)", self)
            self.cancel_btn.setStyleSheet(btn_css.format(bg="#a71d2a", hov="#dc3545"))
            self.cancel_btn.adjustSize()
            self.cancel_btn.move(
                20 + self.save_btn.width() + 8, 20 + self.help.height() + 8
            )
            self.cancel_btn.clicked.connect(self._cancel)
            self.setMouseTracking(True)
            # Still try for keyboard focus so Enter/Esc work when they can.
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.show()
            self.raise_()
            self.activateWindow()
            self.setFocus(Qt.FocusReason.OtherFocusReason)

        def _finish(self, confirmed: bool) -> None:
            # A Qt.Tool window is excluded from Qt's "last window closed" count,
            # so close() alone never returns from app.exec(). Quit explicitly.
            self.confirmed = confirmed
            self.close()
            QApplication.quit()

        def _confirm(self) -> None:
            self._finish(True)

        def _cancel(self) -> None:
            self._finish(False)

        # ----- handle geometry -----

        def _handle_rects(self) -> dict[str, QRect]:
            r = self.rect_
            s = HANDLE_SIZE
            half = s // 2
            cx, cy = r.left() + r.width() // 2, r.top() + r.height() // 2
            return {
                "nw": QRect(r.left() - half, r.top() - half, s, s),
                "n":  QRect(cx - half,        r.top() - half, s, s),
                "ne": QRect(r.right() - half, r.top() - half, s, s),
                "e":  QRect(r.right() - half, cy - half,       s, s),
                "se": QRect(r.right() - half, r.bottom() - half, s, s),
                "s":  QRect(cx - half,        r.bottom() - half, s, s),
                "sw": QRect(r.left() - half,  r.bottom() - half, s, s),
                "w":  QRect(r.left() - half,  cy - half,       s, s),
            }

        def _hit_test(self, pos: QPoint) -> str | None:
            for name_, hr in self._handle_rects().items():
                if hr.contains(pos):
                    return name_
            if self.rect_.contains(pos):
                return "body"
            return None

        # ----- paint -----

        def paintEvent(self, _event) -> None:  # noqa: N802
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            dim = QColor(0, 0, 0, 110)
            p.fillRect(self.rect(), dim)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(self.rect_, Qt.GlobalColor.transparent)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen = QPen(QColor(220, 30, 30), BORDER_WIDTH)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(self.rect_)
            p.setBrush(QBrush(QColor(220, 30, 30)))
            for hr in self._handle_rects().values():
                p.fillRect(hr, QColor(220, 30, 30))
            p.setPen(QColor(255, 255, 255))
            r = self.rect_
            label = f"{self.label}  {r.width()}×{r.height()}  @ ({r.left()},{r.top()})"
            p.drawText(r.left() + 6, r.top() - 6, label)

        # ----- mouse -----

        def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
            if e.button() != Qt.MouseButton.LeftButton:
                return
            self.dragging = self._hit_test(e.pos())
            self.drag_start = e.pos()
            self.rect_start = QRect(self.rect_)

        def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
            if not self.dragging or self.drag_start is None or self.rect_start is None:
                self._update_cursor(self._hit_test(e.pos()))
                return
            dx = e.pos().x() - self.drag_start.x()
            dy = e.pos().y() - self.drag_start.y()
            r = QRect(self.rect_start)
            if self.dragging == "body":
                r.translate(dx, dy)
            else:
                if "n" in self.dragging:
                    r.setTop(min(r.top() + dy, r.bottom() - MIN_DIMENSION))
                if "s" in self.dragging:
                    r.setBottom(max(r.bottom() + dy, r.top() + MIN_DIMENSION))
                if "w" in self.dragging:
                    r.setLeft(min(r.left() + dx, r.right() - MIN_DIMENSION))
                if "e" in self.dragging:
                    r.setRight(max(r.right() + dx, r.left() + MIN_DIMENSION))
            self.rect_ = r
            self.update()

        def mouseReleaseEvent(self, _e: QMouseEvent) -> None:  # noqa: N802
            self.dragging = None
            self.drag_start = None
            self.rect_start = None

        def _update_cursor(self, target: str | None) -> None:
            cursor_map = {
                "body": Qt.CursorShape.SizeAllCursor,
                "n": Qt.CursorShape.SizeVerCursor, "s": Qt.CursorShape.SizeVerCursor,
                "e": Qt.CursorShape.SizeHorCursor, "w": Qt.CursorShape.SizeHorCursor,
                "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
                "nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
            }
            self.setCursor(cursor_map.get(target, Qt.CursorShape.ArrowCursor))

        # ----- keyboard -----

        def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
            if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._finish(True)
            elif e.key() == Qt.Key.Key_Escape:
                self._finish(False)

    app = QApplication.instance() or QApplication([])
    if existing is not None:
        rect = QRect(existing.x, existing.y, existing.w, existing.h)
    else:
        rect = QRect(*DEFAULT_RECT)
    overlay = LensOverlay(rect, name)
    app.exec()
    if not overlay.confirmed:
        return None
    r = overlay.rect_
    return Lens(name=name, x=r.left(), y=r.top(), w=r.width(), h=r.height())
