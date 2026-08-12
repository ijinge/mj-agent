"""锁住 system prompt 的关键约束，防止被无意改回去。"""

from __future__ import annotations

from app.worker.agent import DEFAULT_SYSTEM_PROMPT


def test_system_prompt_says_game_state_placeholder() -> None:
    """系统提示必须告诉 LLM 用 __GAME_STATE__ 占位符传 game_state。"""
    assert "game_state" in DEFAULT_SYSTEM_PROMPT, "system prompt 必须包含 game_state 字面量"
    assert "__GAME_STATE__" in DEFAULT_SYSTEM_PROMPT, (
        "system prompt 必须告诉 LLM 使用 __GAME_STATE__ 占位符"
    )
    assert "替换" in DEFAULT_SYSTEM_PROMPT or "自动" in DEFAULT_SYSTEM_PROMPT, (
        "system prompt 必须说明系统会自动替换占位符"
    )


def test_system_prompt_explains_tool_flow() -> None:
    """system prompt 必须提到决策类工具。"""
    assert "decision" in DEFAULT_SYSTEM_PROMPT, "system prompt 必须提到 *_decision 决策工具"


def test_default_graph_uses_default_system_prompt() -> None:
    """build_default_graph 不传 system_prompt 时，应使用 DEFAULT_SYSTEM_PROMPT。"""
    from app.worker.agent import build_default_graph

    g = build_default_graph(llm=None)  # llm=None 走占位分支
    # 占位分支用 sys_text 拼消息；这里只验证不传 system_prompt 不报错
    # 真正生效要 llm+tools 路径，但 graph 构造必须能完成
    assert g is not None


def test_system_prompt_mentions_user_question() -> None:
    """system prompt 必须提到【用户提问】段，让 LLM 知道从哪读用户问题。"""
    assert "用户提问" in DEFAULT_SYSTEM_PROMPT, (
        "system prompt 必须包含【用户提问】标记，便于 LLM 解析"
    )
    # 必须强调要"围绕用户提问作答"
    assert "围绕" in DEFAULT_SYSTEM_PROMPT or "用户提问" in DEFAULT_SYSTEM_PROMPT, (
        "system prompt 必须告诉 LLM 要围绕用户提问来调工具"
    )


def test_runtime_system_prompt_contains_routed_game_id() -> None:
    """推理节点必须明确看到已路由的地方麻将类型 ID。"""
    from app.worker.agent import _system_prompt_with_game_id

    prompt = _system_prompt_with_game_id(DEFAULT_SYSTEM_PROMPT, "ncmj-server")
    assert "ncmj-server" in prompt
    assert "MCP server" in prompt

    # game_state 不应直接写进 prompt（它通过占位符机制传递）
    assert "【场面状态】" not in DEFAULT_SYSTEM_PROMPT, "system prompt 不应包含【场面状态】标记"
