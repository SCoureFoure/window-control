"""Optional helper: snap a lens to a visible top-level window's rect.

Never required per CLAUDE.md invariant #1 — the lens is a screen rect, not
bound to a HWND. This is a convenience for computing an initial lens; nothing
in the run loop depends on it.
"""

from __future__ import annotations

import win32gui

from src.lens.model import Lens


def snap_lens_to_window(title_substring: str, name: str = "default") -> Lens:
    needle = title_substring.lower()
    candidates: list[tuple[int, str]] = []

    def _on_window(hwnd, _extra) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if needle in title.lower():
            candidates.append((hwnd, title))

    win32gui.EnumWindows(_on_window, None)

    if len(candidates) == 0:
        raise ValueError(
            f"no visible window found with title containing {title_substring!r}"
        )
    if len(candidates) > 1:
        titles = ", ".join(repr(t) for _, t in candidates)
        raise ValueError(
            f"multiple windows match title {title_substring!r}: {titles}"
        )

    hwnd, _title = candidates[0]
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return Lens(name=name, x=left, y=top, w=right - left, h=bottom - top)
