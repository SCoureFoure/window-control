"""Session reporter — saves screenshots and a per-step trace to runs/.

Layout:
    runs/<YYYYMMDD_HHMMSS>/
        step_01.png, step_02.png, ...
        trace.jsonl
        session.log
"""

from __future__ import annotations

import base64
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from src.lens.model import Lens
from src.zones.perception import ParsedAction, TerminalResult

RUNS_DIR = Path("runs")


class Reporter:
    def __init__(self, goal: str, lens: Lens):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = RUNS_DIR / ts
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self._log_path = self.run_dir / "session.log"
        self._trace_path = self.run_dir / "trace.jsonl"

        self._logger = logging.getLogger(f"reporter.{ts}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        fmt = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")
        fh = logging.FileHandler(self._log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        self._logger.addHandler(fh)
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        self._logger.addHandler(ch)

        self._logger.info("=== window-control session ===")
        self._logger.info(f"Run dir : {self.run_dir}")
        self._logger.info(f"Lens    : {lens.name!r}  rect={lens.rect}")
        self._logger.info(f"Goal    : {goal!r}")
        self._logger.info("")

    def on_capture(self, step: int, b64: str, width: int, height: int) -> None:
        img_path = self.run_dir / f"step_{step:02d}.png"
        img_path.write_bytes(base64.standard_b64decode(b64))
        self._logger.info(f"[step {step}] capture  {width}x{height}px -> {img_path.name}")

    def on_action(self, step: int, action: ParsedAction) -> None:
        bits = [action.action]
        if action.coordinate:
            bits.append(f"coord={action.coordinate}")
        if action.start_coordinate:
            bits.append(f"start={action.start_coordinate}")
        if action.text:
            bits.append(f"text={action.text!r}")
        if action.keys:
            bits.append(f"keys={action.keys}")
        if action.scroll_direction:
            bits.append(f"scroll={action.scroll_direction}/{action.scroll_distance}")
        if action.duration is not None:
            bits.append(f"dur={action.duration}")
        self._logger.info(f"[step {step}] action   {' '.join(bits)}")
        self._write_trace(step, "action", {
            "action": action.action,
            "coordinate": list(action.coordinate) if action.coordinate else None,
            "start_coordinate": list(action.start_coordinate) if action.start_coordinate else None,
            "text": action.text,
            "keys": action.keys,
            "scroll_direction": action.scroll_direction,
            "scroll_distance": action.scroll_distance,
            "duration": action.duration,
            "tool_use_id": action.tool_use_id,
        })

    def on_terminal(self, step: int, result: TerminalResult) -> None:
        tag = "DONE" if result.done else "IMPOSSIBLE"
        self._logger.info(f"[step {step}] {tag}     {result.message}")
        self._write_trace(step, tag.lower(), {"message": result.message, "done": result.done})

    def on_screenshot_request(self, step: int) -> None:
        self._logger.info(f"[step {step}] screenshot requested - recapturing")

    def on_error(self, step: int, exc: Exception) -> None:
        self._logger.error(f"[step {step}] ERROR    {type(exc).__name__}: {exc}")
        self._write_trace(step, "error", {"type": type(exc).__name__, "message": str(exc)})

    def on_max_steps(self, max_steps: int) -> None:
        self._logger.warning(f"[stopped] reached max_steps={max_steps}")
        self._write_trace(max_steps, "max_steps", {})

    def summary(self) -> str:
        return f"Run saved to: {self.run_dir.resolve()}"

    def _write_trace(self, step: int, event: str, data: dict[str, Any]) -> None:
        record = {"step": step, "event": event, **data}
        with self._trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
