"""Desktop input backend — mouse + keyboard via pyautogui.

Coordinates are screen-absolute. Touch-style gestures are synthesized as
mouse drags. Failsafe is enabled (mouse-to-corner aborts).
"""

from __future__ import annotations

import time

import pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

# A click holds the button briefly, like a finger tap. Unity-based targets poll
# input per frame and can miss a zero-duration down/up (observed live 2026-07-23:
# Umamusume ignored pyautogui.click but registered press-and-hold).
CLICK_HOLD_S = 0.08


class DesktopBackend:
    def click(self, x: int, y: int, button: str = "left") -> None:
        pyautogui.moveTo(x, y)
        pyautogui.mouseDown(button=button)
        try:
            time.sleep(CLICK_HOLD_S)
        finally:
            pyautogui.mouseUp(button=button)

    def double_click(self, x: int, y: int) -> None:
        pyautogui.doubleClick(x=x, y=y)

    def triple_click(self, x: int, y: int) -> None:
        pyautogui.tripleClick(x=x, y=y)

    def long_press(self, x: int, y: int, duration: float = 1.0) -> None:
        pyautogui.moveTo(x, y)
        pyautogui.mouseDown(button="left")
        try:
            time.sleep(duration)
        finally:
            pyautogui.mouseUp(button="left")

    def swipe(
        self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.3
    ) -> None:
        pyautogui.moveTo(x1, y1)
        pyautogui.mouseDown(button="left")
        try:
            pyautogui.moveTo(x2, y2, duration=duration)
        finally:
            pyautogui.mouseUp(button="left")

    def mouse_move(self, x: int, y: int) -> None:
        pyautogui.moveTo(x, y)

    def mouse_down(self, x: int, y: int, button: str = "left") -> None:
        pyautogui.moveTo(x, y)
        pyautogui.mouseDown(button=button)

    def mouse_up(self, x: int, y: int, button: str = "left") -> None:
        pyautogui.moveTo(x, y)
        pyautogui.mouseUp(button=button)

    def scroll(self, x: int, y: int, direction: str, amount: int) -> None:
        clicks = amount if direction == "up" else -amount
        pyautogui.moveTo(x, y)
        pyautogui.scroll(clicks)

    def type_text(self, text: str) -> None:
        pyautogui.typewrite(text, interval=0.03)

    def key(self, keys: list[str]) -> None:
        if not keys:
            return
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)

    def hold_key(self, key: str, duration: float) -> None:
        pyautogui.keyDown(key)
        try:
            time.sleep(duration)
        finally:
            pyautogui.keyUp(key)

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)
