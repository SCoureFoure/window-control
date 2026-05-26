"""DPI awareness setup.

We set the process to per-monitor v2 DPI-aware at startup so that:
  - `GetWindowRect` and `mss.grab` agree on physical pixels.
  - pyautogui input coordinates match the same physical pixel space.

After this is called once, no further scaling is needed in coordinate math.
A lens stores screen-absolute physical pixels and screen↔lens conversion is
pure addition.
"""

from __future__ import annotations

import ctypes

PROCESS_PER_MONITOR_DPI_AWARE = 2
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

_already_set = False


def set_per_monitor_dpi_aware() -> None:
    """Make this process per-monitor DPI-aware. Safe to call multiple times."""
    global _already_set
    if _already_set:
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
        _already_set = True
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)
        _already_set = True
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        _already_set = True
    except (AttributeError, OSError):
        pass
