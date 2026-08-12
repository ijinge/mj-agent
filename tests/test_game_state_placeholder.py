"""测试 game_state 占位符替换逻辑。"""
from __future__ import annotations

from app.worker.mcp.tool_node import (
    GAME_STATE_PLACEHOLDER,
    _replace_game_state_placeholder,
)


def test_replace_placeholder_in_dict_tool_calls() -> None:
    """LLM 传 dict 形式的 tool_calls 时，占位符应被替换为真实 game_state。"""
    real_state = {"room_id": "101", "cards": [1, 2, 3]}
    state = {
        "messages": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "name": "nanchang_mahjong_discard_decision",
                        "args": {
                            "consult_hand_cards": [1, 2, 3],
                            "game_state": GAME_STATE_PLACEHOLDER,
                        },
                        "id": "tc_1",
                    }
                ],
            }
        ],
        "game_state": real_state,
    }

    result = _replace_game_state_placeholder(state)
    msgs = result["messages"]
    tc = msgs[-1]["tool_calls"][0]
    assert tc["args"]["game_state"] == real_state
    assert tc["args"]["consult_hand_cards"] == [1, 2, 3]


def test_no_placeholder_returns_original() -> None:
    """tool_calls 中没有占位符时，应返回原 state。"""
    state = {
        "messages": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "name": "some_tool",
                        "args": {"foo": "bar"},
                        "id": "tc_1",
                    }
                ],
            }
        ],
        "game_state": {"real": True},
    }

    result = _replace_game_state_placeholder(state)
    assert result is state  # 同一个对象，未修改


def test_no_game_state_returns_original() -> None:
    """state 中没有 game_state 时，应返回原 state。"""
    state = {
        "messages": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "name": "some_tool",
                        "args": {"game_state": GAME_STATE_PLACEHOLDER},
                        "id": "tc_1",
                    }
                ],
            }
        ],
    }

    result = _replace_game_state_placeholder(state)
    assert result is state


def test_placeholder_only_replaces_matching_key() -> None:
    """只替换值为占位符的 key，其他 key 保持不变。"""
    real_state = {"room_id": "101"}
    state = {
        "messages": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "name": "tool",
                        "args": {
                            "game_state": GAME_STATE_PLACEHOLDER,
                            "other_param": "__GAME_STATE__",  # 值恰好相同
                            "name": "not_placeholder",
                        },
                        "id": "tc_1",
                    }
                ],
            }
        ],
        "game_state": real_state,
    }

    result = _replace_game_state_placeholder(state)
    args = result["messages"][-1]["tool_calls"][0]["args"]
    assert args["game_state"] is real_state
    assert args["other_param"] is real_state  # 值相同也会被替换（符合预期）
    assert args["name"] == "not_placeholder"
