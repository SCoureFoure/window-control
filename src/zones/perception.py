"""Perception zone — send a lens screenshot to Claude, parse the next action.

Conventions:
- Stateless. The orchestrator owns the message history.
- All content blocks are stored as plain dicts so they round-trip safely
  through the SDK on subsequent turns.
- Uses Anthropic Computer Use beta (`computer-use-2025-11-24`).
- The system prompt is marked for prompt caching.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import anthropic

MODEL = "claude-opus-4-8"
COMPUTER_USE_BETA = "computer-use-2025-11-24"
MAX_TOKENS = 2048

DONE_PREFIX = "DONE"
IMPOSSIBLE_PREFIX = "IMPOSSIBLE"


@dataclass
class ParsedAction:
    """A single computer-use tool call returned by Claude."""
    tool_use_id: str
    action: str
    coordinate: tuple[int, int] | None = None
    start_coordinate: tuple[int, int] | None = None
    text: str | None = None
    keys: list[str] = field(default_factory=list)
    scroll_direction: str | None = None
    scroll_distance: int = 3
    duration: float | None = None
    raw_input: dict = field(default_factory=dict)


@dataclass
class TerminalResult:
    """Claude finished without a tool call."""
    message: str
    done: bool


def build_system_prompt(goal: str, lens_name: str, lens_w: int, lens_h: int) -> str:
    return (
        "You are an agent that controls a rectangular region of the user's screen.\n\n"
        f"Lens: {lens_name}  ({lens_w} x {lens_h} pixels)\n"
        f"Goal: {goal}\n\n"
        "What you see\n"
        "------------\n"
        "Each turn you receive a screenshot of the lens region. Coordinates you\n"
        "return are LENS-RELATIVE: (0, 0) is the top-left of the screenshot,\n"
        f"({lens_w - 1}, {lens_h - 1}) is the bottom-right. Never return\n"
        "coordinates outside that range.\n\n"
        "How you act\n"
        "-----------\n"
        "Use the computer tool. One action per turn. After each action you get a\n"
        "fresh screenshot.\n\n"
        "The target may be a touch-style UI (mobile game, tablet app). Treat\n"
        "left_click as a tap. Use left_click_drag for swipes. For a long press,\n"
        "use left_mouse_down, then wait, then left_mouse_up on subsequent turns.\n\n"
        "Termination\n"
        "-----------\n"
        "When the goal is complete, respond with plain text only (no tool call):\n"
        "  DONE: <one-line summary>\n"
        "If the goal cannot be achieved from what you can see, respond with:\n"
        "  IMPOSSIBLE: <reason>\n\n"
        "Safety\n"
        "------\n"
        "Do not act outside the lens. Do not type sensitive data unless the goal\n"
        "explicitly requires it. Prefer small, verifiable steps over large jumps."
    )


def _make_computer_tool(width: int, height: int) -> dict:
    return {
        "type": "computer_20251124",
        "name": "computer",
        "display_width_px": width,
        "display_height_px": height,
    }


def _image_block(b64: str) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": b64},
    }


def _content_to_dicts(content: list) -> list[dict]:
    result: list[dict] = []
    for block in content:
        if hasattr(block, "type"):
            if block.type == "tool_use":
                result.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": dict(block.input),
                })
            elif block.type == "text":
                result.append({"type": "text", "text": block.text})
        elif isinstance(block, dict):
            result.append(block)
    return result


def _coord(value: Any) -> tuple[int, int] | None:
    if value is None:
        return None
    return int(value[0]), int(value[1])


_OMITTED_BLOCK: dict = {"type": "text", "text": "(old screenshot omitted)"}


def _has_image(user_msg: dict) -> bool:
    for block in user_msg.get("content", []):
        if block.get("type") == "image":
            return True
        if block.get("type") == "tool_result":
            for inner in block.get("content", []):
                if inner.get("type") == "image":
                    return True
    return False


def _drop_images(user_msg: dict) -> dict:
    msg = copy.deepcopy(user_msg)
    new_content = []
    for block in msg.get("content", []):
        if block.get("type") == "image":
            new_content.append(_OMITTED_BLOCK)
        elif block.get("type") == "tool_result":
            block["content"] = [
                _OMITTED_BLOCK if b.get("type") == "image" else b
                for b in block.get("content", [])
            ]
            new_content.append(block)
        else:
            new_content.append(block)
    msg["content"] = new_content
    return msg


def _prune_old_screenshots(messages: list[dict], history_window: int) -> list[dict]:
    """Replace image blocks in old user messages, keeping last history_window images intact."""
    user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user" and _has_image(m)]
    to_drop = user_indices[:-history_window] if history_window > 0 else user_indices
    result = list(messages)
    for i in to_drop:
        result[i] = _drop_images(result[i])
    return result


def _parse_tool_use(tool_use: dict) -> ParsedAction:
    inp: dict[str, Any] = tool_use["input"]
    return ParsedAction(
        tool_use_id=tool_use["id"],
        action=str(inp.get("action", "")),
        coordinate=_coord(inp.get("coordinate")),
        start_coordinate=_coord(inp.get("start_coordinate")),
        text=inp.get("text"),
        keys=list(inp.get("keys", []) or []),
        scroll_direction=inp.get("scroll_direction"),
        scroll_distance=int(inp.get("scroll_amount", inp.get("scroll_distance", 3))),
        duration=float(inp["duration"]) if "duration" in inp else None,
        raw_input=inp,
    )


def ask_claude(
    client: anthropic.Anthropic,
    system: str,
    messages: list[dict],
    screenshot_b64: str,
    width: int,
    height: int,
    prev_tool_use_id: str | None = None,
    history_window: int = 4,
) -> tuple[ParsedAction | TerminalResult, list[dict], str | None]:
    """Call Claude with the latest screenshot, return (result, history, next_id)."""
    if prev_tool_use_id:
        user_content: list[dict] = [{
            "type": "tool_result",
            "tool_use_id": prev_tool_use_id,
            "content": [_image_block(screenshot_b64)],
        }]
    else:
        user_content = [
            {"type": "text", "text": "Current state of the lens:"},
            _image_block(screenshot_b64),
        ]

    new_messages = messages + [{"role": "user", "content": user_content}]
    pruned_messages = _prune_old_screenshots(new_messages, history_window)

    cached_system = [{
        "type": "text",
        "text": system,
        "cache_control": {"type": "ephemeral"},
    }]

    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=cached_system,
        messages=pruned_messages,
        tools=[_make_computer_tool(width, height)],
        betas=[COMPUTER_USE_BETA],
    )

    assistant_dicts = _content_to_dicts(response.content)
    new_messages.append({"role": "assistant", "content": assistant_dicts})

    tool_use: dict | None = None
    text_parts: list[str] = []
    for block in assistant_dicts:
        if block.get("type") == "tool_use":
            tool_use = block
        elif block.get("type") == "text":
            text_parts.append(block["text"])

    if tool_use is None:
        full_text = " ".join(text_parts).strip()
        upper = full_text.upper()
        done = upper.startswith(DONE_PREFIX)
        return TerminalResult(message=full_text, done=done), new_messages, None

    return _parse_tool_use(tool_use), new_messages, tool_use["id"]
