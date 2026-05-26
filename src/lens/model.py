"""Lens — a screen-absolute rectangle the agent operates on.

A lens is not tied to a process, window handle, or window class. It is just an
(x, y, w, h) region in screen-absolute pixel coordinates. The capture zone grabs
pixels from it, the model returns lens-relative coordinates, the action zone
translates those back to screen-absolute before emitting OS input.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Lens:
    name: str
    x: int
    y: int
    w: int
    h: int

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.w, self.h

    @property
    def origin(self) -> tuple[int, int]:
        return self.x, self.y

    @property
    def size(self) -> tuple[int, int]:
        return self.w, self.h

    def contains_rel(self, rx: int, ry: int) -> bool:
        return 0 <= rx < self.w and 0 <= ry < self.h

    def to_screen(self, rx: int, ry: int) -> tuple[int, int]:
        if not self.contains_rel(rx, ry):
            raise ValueError(
                f"Lens-relative coordinate ({rx}, {ry}) is outside lens "
                f"{self.name!r} of size {self.w}x{self.h}."
            )
        return self.x + rx, self.y + ry

    def to_dict(self) -> dict:
        return {"name": self.name, "x": self.x, "y": self.y, "w": self.w, "h": self.h}

    @classmethod
    def from_dict(cls, d: dict) -> "Lens":
        return cls(name=d["name"], x=int(d["x"]), y=int(d["y"]), w=int(d["w"]), h=int(d["h"]))
