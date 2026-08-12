#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from typing import Any

# 万 1-9，条 17-25，筒 33-41，字 49-55（东南西北中发白）
TILE_NAMES: dict[int, str] = {
    1: "一万", 2: "二万", 3: "三万", 4: "四万", 5: "五万",
    6: "六万", 7: "七万", 8: "八万", 9: "九万",
    17: "一条", 18: "二条", 19: "三条", 20: "四条", 21: "五条",
    22: "六条", 23: "七条", 24: "八条", 25: "九条",
    33: "一筒", 34: "二筒", 35: "三筒", 36: "四筒", 37: "五筒",
    38: "六筒", 39: "七筒", 40: "八筒", 41: "九筒",
    49: "东风", 50: "南风", 51: "西风", 52: "北风",
    53: "红中", 54: "发财", 55: "白板",
}

# 动作类型编码 → 中文
ACTION_TYPE = {7: "出牌", 2: "碰", 3: "明杠", 4: "吃"}

GAME_AREA_NAMES = {9990: "南昌麻将", 300: "南昌麻将"}
DEFAULT_GAME_NAME = "麻将"


# ── 基础工具 ──

def tile_name(code: int) -> str:
    """编码 → 中文牌名；未知编码返回 '?'。"""
    return TILE_NAMES.get(code, "?")


def fmt_tiles(codes: list[int]) -> str:
    """编码列表 → 中文牌名列表。"""
    return " ".join(tile_name(c) for c in codes)


def player_melds(state: dict[str, Any], seat: int) -> list[tuple[str, list[int]]]:
    """某玩家的全部副露，带类型标签：[(吃/碰/明杠/补杠/暗杠, 牌编码列表), ...]。"""
    result: list[tuple[str, list[int]]] = []
    for tag, key in (
        ("吃", "player_chi_cards"),
        ("碰", "player_peng_cards"),
        ("明杠", "player_gang_cards"),
        ("补杠", "player_bugang_cards"),
        ("暗杠", "player_angang_cards"),
    ):
        groups = state.get(key, [])
        if isinstance(groups, list) and len(groups) > seat:
            for group in groups[seat]:
                if isinstance(group, list) and group:
                    result.append((tag, sorted(group)))
    return result


def resolve_seat(state: dict[str, Any], override: int | None) -> int:
    """
    本方座位判定：
    - 优先使用 override（手动指定）
    - 根据 action_cards 的键判断当前阶段：
      - 键 "7"：出牌阶段，当前操作者是 acting_player_position
      - 其他键（"0"-"3"）：吃碰杠阶段，当前操作者是 acting_do_player_position
    """
    if override is not None:
        return override
    
    action_cards = state.get("action_cards")
    if isinstance(action_cards, dict):
        # 检查是否是出牌阶段（键 "7"）
        if "7" in action_cards or 7 in action_cards:
            # 出牌阶段：acting_player_position
            acting_player = state.get("acting_player_position")
            if isinstance(acting_player, int) and 0 <= acting_player <= 3:
                return acting_player
        else:
            # 吃碰杠阶段：acting_do_player_position
            do_player = state.get("acting_do_player_position")
            if isinstance(do_player, int) and 0 <= do_player <= 3:
                return do_player
    
    # 默认回退到 acting_player_position
    acting_player = state.get("acting_player_position")
    if isinstance(acting_player, int) and 0 <= acting_player <= 3:
        return acting_player
    return 0


def get_action_seat(state: dict[str, Any]) -> int | None:
    """
    获取当前需要操作的用户座位：
    - 吃碰杠阶段：acting_do_player_position
    - 出牌阶段：acting_player_position
    """
    # 吃碰杠阶段
    do_player = state.get("acting_do_player_position")
    if isinstance(do_player, int) and 0 <= do_player <= 3:
        return do_player
    # 出牌阶段
    acting_player = state.get("acting_player_position")
    if isinstance(acting_player, int) and 0 <= acting_player <= 3:
        return acting_player
    return None


def infer_action_type(codes: list[int]) -> str:
    """action_cards 候选组 → 动作类型：4 张=杠，3 张相同=碰，否则吃。"""
    if len(codes) == 4:
        return "杠"
    if len(codes) >= 2 and len(set(codes)) == 1:
        return "碰"
    return "吃"


def render_action_cards(state: dict[str, Any], seat: int) -> str:
    """
    本方座位的可响应操作 → 中文。
    action_cards 的键说明：
    - "7" 或其他数字字符串：代表动作类型编码（7=出牌），数组中的每个元素是一张可出的牌
    - 座位号字符串（"0"-"3"）：代表该座位的可响应操作
    """
    action_cards = state.get("action_cards")
    if not isinstance(action_cards, dict):
        return "无"

    # 检查是否有出牌操作（键 "7" 代表出牌）
    discard_cands = action_cards.get("7")
    if discard_cands and isinstance(discard_cands, list):
        # 出牌阶段：数组中的每个元素是一张可出的牌
        playable_tiles = []
        for item in discard_cands:
            if isinstance(item, list) and len(item) == 1:
                playable_tiles.append(item[0])
            elif isinstance(item, int):
                playable_tiles.append(item)
        if playable_tiles:
            return f"出牌：{fmt_tiles(sorted(playable_tiles))}"

    # 检查是否有该座位的响应操作
    cands = action_cards.get(str(seat))
    if cands is None:
        cands = action_cards.get(seat)  # 兼容 int 键
    if not cands:
        return "无"

    parts = []
    for group in cands:
        if isinstance(group, list) and group:
            act = infer_action_type(group)
            parts.append(f"{act} {fmt_tiles(sorted(group))}")
    return "；".join(parts) if parts else "无"


def fmt_action_seq(seq: Any) -> str:
    """action_seq / last_action 单条 [玩家, 动作类型, 牌] → '玩家3 出牌 六条'。"""
    if not isinstance(seq, list) or len(seq) < 3:
        return "（无效动作记录）"
    seat, act, code = seq[0], seq[1], seq[2]
    who = f"玩家{seat}" if isinstance(seat, int) and 0 <= seat <= 3 else f"座位{seat}"
    act_name = ACTION_TYPE.get(act, f"动作{act}")
    tile = tile_name(code) if isinstance(code, int) else str(code)
    return f"{who} {act_name} {tile}"

def render_scene(state: dict[str, Any], seat: int) -> str:
    lines: list[str] = []

    # 头部信息：当前操作的用户
    acting_player = state.get("acting_player_position")
    do_player = state.get("acting_do_player_position")

    if do_player is not None and isinstance(do_player, int) and 0 <= do_player <= 3:
        lines.append(f"当前操作：玩家{do_player}（吃碰杠）")
    elif acting_player is not None and isinstance(acting_player, int) and 0 <= acting_player <= 3:
        lines.append(f"当前操作：玩家{acting_player}（出牌）")
    else:
        lines.append("当前操作：未知")

    lines.append(f"本方座位：玩家{seat}")
    # 精牌（缺省宽容）
    king = state.get("king_cards")
    if isinstance(king, list) and king:
        parts = [f"正精 {tile_name(king[0])}"]
        if len(king) > 1 and king[1] is not None:
            parts.append(f"副精 {tile_name(king[1])}")
        lines.append(f"【精牌】{'，'.join(parts)}")
    else:
        lines.append("【精牌】无（未提供）")

    # 本方手牌（只渲染本方，绝不输出其他玩家手牌）
    hands = state.get("player_hand_cards", [])
    own_hand: list[int] = []
    if isinstance(hands, list) and len(hands) > seat and isinstance(hands[seat], list):
        own_hand = sorted(hands[seat])
    lines.append("【本方手牌】" + (fmt_tiles(own_hand) if own_hand else "无"))

    # 本方副露
    own_melds = player_melds(state, seat)
    if own_melds:
        lines.append("【本方副露】" + "；".join(f"{tag}：{fmt_tiles(codes)}" for tag, codes in own_melds))
    else:
        lines.append("【本方副露】无")

    # 四家弃牌（明牌，公开信息）
    played = state.get("played_cards", [])
    lines.append("【四家弃牌】")
    for s in range(4):
        pile: list[int] = []
        if isinstance(played, list) and len(played) > s and isinstance(played[s], list):
            pile = played[s]
        lines.append(f"  玩家{s}：{fmt_tiles(pile) if pile else '无'}")

    # 四家副露（明牌，公开信息）
    lines.append("【四家副露】")
    for s in range(4):
        melds = player_melds(state, s)
        if melds:
            lines.append(f"  玩家{s}：" + "；".join(f"{tag} {fmt_tiles(codes)}" for tag, codes in melds))
        else:
            lines.append(f"  玩家{s}：无")

    # 可响应操作（只本方座位）
    lines.append("【可响应操作】" + render_action_cards(state, seat))

    # 最近动作
    last = state.get("last_action")
    if not last and isinstance(state.get("action_seq"), list) and state["action_seq"]:
        last = state["action_seq"][-1]
    lines.append("【最近动作】" + (fmt_action_seq(last) if last else "无"))

    # 剩余牌
    remain = state.get("remain_card_stack", [])
    remain_count = len(remain) if isinstance(remain, list) else 0
    lines.append(f"【剩余牌】{remain_count} 张")

    return "\n".join(lines)


def render(state: dict[str, Any], seat: int | None = None) -> str:
    """
    将 game_state JSON 渲染为中文场面描述。

    Args:
        state: game_state 字典
        seat: 本方座位（0-3，0=庄家）。为 None 时自动判定。

    Returns:
        中文场面描述字符串
    """
    if not isinstance(state, dict):
        raise ValueError("state 必须是 dict")
    resolved_seat = resolve_seat(state, seat)
    return render_scene(state, resolved_seat)

# # ── 示例调用 ──

# if __name__ == "__main__":
#     sample_json = '''{"room_id": 297000, "acting_player_position": 0, "acting_do_player_position": 0, "game_area_id": 603, "played_cards": [[25, 2, 21, 24], [3, 36, 20, 1], [19, 39, 2, 36], [33, 7, 18, 37]], "player_hand_cards": [[33, 34, 34, 51, 52, 54, 54, 55], [8, 38, 38, 38, 50, 51, 53, 54, 55, 40], [3, 5, 7, 8, 9, 22, 23, 49, 50, 21], [6, 6, 8, 22, 40, 40, 49, 51, 24, 22]], "action_seq": [[2, 7, 19], [3, 7, 33], [0, 7, 25], [1, 7, 3], [2, 7, 39], [3, 7, 7], [0, 7, 2], [1, 7, 36], [2, 7, 2], [3, 7, 18], [0, 7, 21], [1, 7, 20], [0, 7, 24], [1, 7, 1], [2, 7, 36], [3, 7, 37]], "last_action": [3, 7, 37], "player_chi_cards": [[], [[21, 20, 19]], [[3, 4, 5]], [[36, 35, 37]]], "player_peng_cards": [[[7, 7, 7], [20, 20, 20]], [], [], []], "player_gang_cards": [[], [], [], []], "player_bugang_cards": [[], [], [], []], "player_angang_cards": [[], [], [], []], "player_bu_cards": [[], [], [], []], "action_cards": {"7": [[33], [34], [34], [51], [52], [54], [54], [55]]}, "remain_card_stack": [40, 4, 52, 1, 1, 41, 24, 52, 41, 38, 35, 53, 21, 4, 36, 4, 49, 53, 9, 3, 34, 1, 18, 6, 17, 17, 54, 9, 35, 39, 37, 21, 52, 39, 33, 18, 2, 23, 49, 2, 53, 36, 51, 41, 55, 17, 22, 25, 18, 41, 33, 23, 17, 5, 19, 50, 37, 39, 24, 6, 35, 34, 23, 3, 55, 25, 25, 50, 5, 9, 19, 8], "king_cards": [8, 9]}'''

#     state = json.loads(sample_json)
#     result = render(state)
#     print(result)
