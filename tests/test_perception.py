"""Tests for src/zones/perception.py — anthropic client is mocked."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.zones.perception import (
    ParsedAction,
    TerminalResult,
    _prune_old_screenshots,
    ask_claude,
    build_system_prompt,
)


def _tool_use_block(action: dict, tool_id: str = "tu_1"):
    return SimpleNamespace(type="tool_use", id=tool_id, name="computer", input=action)


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _mock_client(content_blocks: list) -> MagicMock:
    client = MagicMock()
    client.beta.messages.create.return_value = SimpleNamespace(content=content_blocks)
    return client


def test_build_system_prompt_includes_goal_and_dims():
    prompt = build_system_prompt("tap menu", "default", 800, 600)
    assert "tap menu" in prompt
    assert "default" in prompt
    assert "800 x 600" in prompt
    assert "DONE" in prompt
    assert "IMPOSSIBLE" in prompt


def test_first_turn_wraps_screenshot_as_text_plus_image():
    client = _mock_client([_tool_use_block({"action": "screenshot"})])
    result, msgs, next_id = ask_claude(
        client=client,
        system="sys",
        messages=[],
        screenshot_b64="abc",
        width=100,
        height=100,
        prev_tool_use_id=None,
    )
    assert next_id == "tu_1"
    user_msg = msgs[0]
    assert user_msg["role"] == "user"
    assert user_msg["content"][0]["type"] == "text"
    assert user_msg["content"][1]["type"] == "image"


def test_subsequent_turn_wraps_screenshot_as_tool_result():
    client = _mock_client([_tool_use_block({"action": "left_click", "coordinate": [10, 20]})])
    result, msgs, next_id = ask_claude(
        client=client,
        system="sys",
        messages=[{"role": "assistant", "content": []}],
        screenshot_b64="abc",
        width=100,
        height=100,
        prev_tool_use_id="prev_tu",
    )
    user_msg = msgs[-2]
    assert user_msg["content"][0]["type"] == "tool_result"
    assert user_msg["content"][0]["tool_use_id"] == "prev_tu"


def test_parse_left_click():
    client = _mock_client([_tool_use_block({"action": "left_click", "coordinate": [30, 40]})])
    result, _, _ = ask_claude(client, "sys", [], "b64", 100, 100)
    assert isinstance(result, ParsedAction)
    assert result.action == "left_click"
    assert result.coordinate == (30, 40)


def test_parse_drag():
    client = _mock_client([_tool_use_block({
        "action": "left_click_drag",
        "start_coordinate": [10, 10],
        "coordinate": [80, 80],
        "duration": 0.4,
    })])
    result, _, _ = ask_claude(client, "sys", [], "b64", 100, 100)
    assert isinstance(result, ParsedAction)
    assert result.start_coordinate == (10, 10)
    assert result.coordinate == (80, 80)
    assert result.duration == 0.4


def test_parse_type():
    client = _mock_client([_tool_use_block({"action": "type", "text": "hi"})])
    result, _, _ = ask_claude(client, "sys", [], "b64", 100, 100)
    assert result.action == "type"
    assert result.text == "hi"


def test_done_terminal():
    client = _mock_client([_text_block("DONE: opened the menu")])
    result, _, next_id = ask_claude(client, "sys", [], "b64", 100, 100)
    assert isinstance(result, TerminalResult)
    assert result.done is True
    assert "opened the menu" in result.message
    assert next_id is None


def test_impossible_terminal():
    client = _mock_client([_text_block("IMPOSSIBLE: target not visible")])
    result, _, _ = ask_claude(client, "sys", [], "b64", 100, 100)
    assert isinstance(result, TerminalResult)
    assert result.done is False


def test_system_prompt_has_cache_control():
    client = _mock_client([_tool_use_block({"action": "screenshot"})])
    ask_claude(client, "sys", [], "b64", 100, 100)
    call_kwargs = client.beta.messages.create.call_args.kwargs
    assert call_kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# History image pruning (_prune_old_screenshots)
# ---------------------------------------------------------------------------

def _user_msg_with_image(b64: str = "img") -> dict:
    return {"role": "user", "content": [{"type": "image", "source": {"data": b64}}]}


def _user_msg_tool_result_with_image(tool_id: str = "tu_1", b64: str = "img") -> dict:
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": [{"type": "image", "source": {"data": b64}}]}]}


def _assistant_msg() -> dict:
    return {"role": "assistant", "content": [{"type": "tool_use", "id": "tu_1", "name": "computer", "input": {}}]}


def _count_images_in_msg(msg: dict) -> int:
    count = 0
    for block in msg.get("content", []):
        if block.get("type") == "image":
            count += 1
        if block.get("type") == "tool_result":
            for inner in block.get("content", []):
                if inner.get("type") == "image":
                    count += 1
    return count


def test_prune_keeps_last_k_images():
    msgs = []
    for i in range(6):
        msgs.append(_user_msg_with_image(f"img{i}"))
        msgs.append(_assistant_msg())

    pruned = _prune_old_screenshots(msgs, history_window=3)

    user_msgs = [m for m in pruned if m.get("role") == "user"]
    images_per = [_count_images_in_msg(m) for m in user_msgs]
    # Last 3 user messages keep images, older 3 are stripped
    assert images_per[-3:] == [1, 1, 1]
    assert images_per[:-3] == [0, 0, 0]


def test_prune_tool_result_images():
    msgs = [_user_msg_tool_result_with_image(f"tu_{i}") for i in range(5)]
    pruned = _prune_old_screenshots(msgs, history_window=2)
    user_msgs = [m for m in pruned if m.get("role") == "user"]
    images_per = [_count_images_in_msg(m) for m in user_msgs]
    assert images_per[-2:] == [1, 1]
    assert images_per[:-2] == [0, 0, 0]


def test_prune_does_not_mutate_original():
    msgs = [_user_msg_with_image("img0"), _user_msg_with_image("img1")]
    _ = _prune_old_screenshots(msgs, history_window=1)
    # original still has images
    assert _count_images_in_msg(msgs[0]) == 1


def test_prune_history_window_larger_than_history_keeps_all():
    msgs = [_user_msg_with_image(f"img{i}") for i in range(3)]
    pruned = _prune_old_screenshots(msgs, history_window=10)
    for m in pruned:
        assert _count_images_in_msg(m) == 1


def test_ask_claude_sends_pruned_messages_to_api():
    # Build a history with 5 user+assistant pairs (images in each user msg)
    history: list[dict] = []
    for i in range(5):
        history.append(_user_msg_with_image(f"old{i}"))
        history.append(_assistant_msg())

    client = _mock_client([_tool_use_block({"action": "screenshot"})])
    ask_claude(client, "sys", history, "new_b64", 100, 100, history_window=2)

    sent_messages = client.beta.messages.create.call_args.kwargs["messages"]
    # The 6th user message is the new one (screenshot). Count images in sent history.
    sent_user = [m for m in sent_messages if m.get("role") == "user"]
    images_per = [_count_images_in_msg(m) for m in sent_user]
    # Last 2 should have images (window=2), older ones stripped
    assert images_per[-2:] == [1, 1]
    assert all(c == 0 for c in images_per[:-2])
