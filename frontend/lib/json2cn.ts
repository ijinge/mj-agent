/**
 * game_state JSON → 中文场面描述
 * 与后端 app/worker/json2cn.py 逻辑保持一致
 */

// 万 1-9，条 17-25，筒 33-41，字 49-55（东南西北中发白）
const TILE_NAMES: Record<number, string> = {
  1: "一万", 2: "二万", 3: "三万", 4: "四万", 5: "五万",
  6: "六万", 7: "七万", 8: "八万", 9: "九万",
  17: "一条", 18: "二条", 19: "三条", 20: "四条", 21: "五条",
  22: "六条", 23: "七条", 24: "八条", 25: "九条",
  33: "一筒", 34: "二筒", 35: "三筒", 36: "四筒", 37: "五筒",
  38: "六筒", 39: "七筒", 40: "八筒", 41: "九筒",
  49: "东风", 50: "南风", 51: "西风", 52: "北风",
  53: "红中", 54: "发财", 55: "白板",
};

// 动作类型编码 → 中文
const ACTION_TYPE: Record<number, string> = { 7: "出牌", 2: "碰", 3: "明杠", 4: "吃" };

const GAME_AREA_NAMES: Record<number, string> = { 9990: "南昌麻将", 300: "南昌麻将" };
const DEFAULT_GAME_NAME = "麻将";

function tileName(code: number): string {
  return TILE_NAMES[code] ?? "?";
}

function fmtTiles(codes: number[]): string {
  return codes.map(tileName).join(" ");
}

type Meld = [string, number[]];

function playerMelds(state: Record<string, any>, seat: number): Meld[] {
  const result: Meld[] = [];
  const entries: [string, string][] = [
    ["吃", "player_chi_cards"],
    ["碰", "player_peng_cards"],
    ["明杠", "player_gang_cards"],
    ["补杠", "player_bugang_cards"],
    ["暗杠", "player_angang_cards"],
  ];
  for (const [tag, key] of entries) {
    const groups = state[key];
    if (Array.isArray(groups) && groups.length > seat) {
      const seatGroups = groups[seat];
      if (Array.isArray(seatGroups)) {
        for (const group of seatGroups) {
          if (Array.isArray(group) && group.length > 0) {
            result.push([tag, [...group].sort((a, b) => a - b)]);
          }
        }
      }
    }
  }
  return result;
}

function resolveSeat(state: Record<string, any>, override?: number): number {
  /**
   * 本方座位判定：
   * - 优先使用 override（手动指定）
   * - 根据 action_cards 的键判断当前阶段：
   *   - 键 "7"：出牌阶段，当前操作者是 acting_player_position
   *   - 其他键（"0"-"3"）：吃碰杠阶段，当前操作者是 acting_do_player_position
   */
  if (override !== undefined) return override;
  
  const actionCards = state.action_cards;
  if (actionCards && typeof actionCards === "object") {
    // 检查是否是出牌阶段（键 "7"）
    if ("7" in actionCards) {
      // 出牌阶段：acting_player_position
      const actingPlayer = state.acting_player_position;
      if (typeof actingPlayer === "number" && actingPlayer >= 0 && actingPlayer <= 3) {
        return actingPlayer;
      }
    } else {
      // 吃碰杠阶段：acting_do_player_position
      const doPlayer = state.acting_do_player_position;
      if (typeof doPlayer === "number" && doPlayer >= 0 && doPlayer <= 3) {
        return doPlayer;
      }
    }
  }
  
  // 默认回退到 acting_player_position
  const actingPlayer = state.acting_player_position;
  if (typeof actingPlayer === "number" && actingPlayer >= 0 && actingPlayer <= 3) {
    return actingPlayer;
  }
  return 0;
}

function inferActionType(codes: number[]): string {
  if (codes.length === 4) return "杠";
  if (codes.length >= 2 && new Set(codes).size === 1) return "碰";
  return "吃";
}

function renderActionCards(state: Record<string, any>, seat: number): string {
  /**
   * 本方座位的可响应操作 → 中文。
   * action_cards 的键说明：
   * - "7" 或其他数字字符串：代表动作类型编码（7=出牌），数组中的每个元素是一张可出的牌
   * - 座位号字符串（"0"-"3"）：代表该座位的可响应操作
   */
  const actionCards = state.action_cards;
  if (!actionCards || typeof actionCards !== "object") return "无";

  // 检查是否有出牌操作（键 "7" 代表出牌）
  const discardCands = actionCards["7"];
  if (discardCands && Array.isArray(discardCands)) {
    // 出牌阶段：数组中的每个元素是一张可出的牌
    const playableTiles: number[] = [];
    for (const item of discardCands) {
      if (Array.isArray(item) && item.length === 1) {
        playableTiles.push(item[0]);
      } else if (typeof item === "number") {
        playableTiles.push(item);
      }
    }
    if (playableTiles.length > 0) {
      return `出牌：${fmtTiles(playableTiles.sort((a, b) => a - b))}`;
    }
  }

  // 检查是否有该座位的响应操作
  let cands = actionCards[String(seat)] ?? actionCards[seat];
  if (!cands || !Array.isArray(cands) || cands.length === 0) return "无";

  const parts: string[] = [];
  for (const group of cands) {
    if (Array.isArray(group) && group.length > 0) {
      const act = inferActionType(group);
      parts.push(`${act} ${fmtTiles([...group].sort((a, b) => a - b))}`);
    }
  }
  return parts.length > 0 ? parts.join("；") : "无";
}

function fmtActionSeq(seq: any): string {
  if (!Array.isArray(seq) || seq.length < 3) return "（无效动作记录）";
  const [seat, act, code] = seq;
  const who = typeof seat === "number" && seat >= 0 && seat <= 3 ? `玩家${seat}` : `座位${seat}`;
  const actName = ACTION_TYPE[act] ?? `动作${act}`;
  const tile = typeof code === "number" ? tileName(code) : String(code);
  return `${who} ${actName} ${tile}`;
}

function renderScene(state: Record<string, any>, seat: number): string {
  const lines: string[] = [];

  // 头部
  const room = state.room_id ?? "";
  const gid = state.game_area_id;
  const gname = typeof gid === "number" ? GAME_AREA_NAMES[gid] : undefined;
  let gidStr: string;
  if (typeof gid === "number") {
    gidStr = gname ? `${gid}（${gname}）` : `${gid}（未知玩法，按${DEFAULT_GAME_NAME}处理）`;
  } else {
    gidStr = "未知";
  }
  const doSeat = state.acting_do_player_position;
  const role = doSeat === seat ? "被咨询方" : "出牌方";
  lines.push(
    `房间号：${room}  玩法ID：${gidStr}  本方座位：玩家${seat}（0=庄家，${role}）`
  );

  // 精牌
  const king = state.king_cards;
  if (Array.isArray(king) && king.length > 0) {
    const parts = [`正精 ${tileName(king[0])}`];
    if (king.length > 1 && king[1] !== null && king[1] !== undefined) {
      parts.push(`副精 ${tileName(king[1])}`);
    }
    lines.push(`【精牌】${parts.join("，")}`);
  } else {
    lines.push("【精牌】无（未提供）");
  }

  // 本方手牌
  const hands = state.player_hand_cards ?? [];
  let ownHand: number[] = [];
  if (Array.isArray(hands) && hands.length > seat && Array.isArray(hands[seat])) {
    ownHand = [...hands[seat]].sort((a, b) => a - b);
  }
  lines.push(`【本方手牌】${ownHand.length > 0 ? fmtTiles(ownHand) : "无"}`);

  // 本方副露
  const ownMelds = playerMelds(state, seat);
  if (ownMelds.length > 0) {
    lines.push(`【本方副露】${ownMelds.map(([tag, codes]) => `${tag}：${fmtTiles(codes)}`).join("；")}`);
  } else {
    lines.push("【本方副露】无");
  }

  // 四家弃牌
  const played = state.played_cards ?? [];
  lines.push("【四家弃牌】");
  for (let s = 0; s < 4; s++) {
    const pile: number[] = Array.isArray(played) && played.length > s && Array.isArray(played[s]) ? played[s] : [];
    lines.push(`  玩家${s}：${pile.length > 0 ? fmtTiles(pile) : "无"}`);
  }

  // 四家副露
  lines.push("【四家副露】");
  for (let s = 0; s < 4; s++) {
    const melds = playerMelds(state, s);
    if (melds.length > 0) {
      lines.push(`  玩家${s}：${melds.map(([tag, codes]) => `${tag} ${fmtTiles(codes)}`).join("；")}`);
    } else {
      lines.push(`  玩家${s}：无`);
    }
  }

  // 可响应操作
  lines.push(`【可响应操作】${renderActionCards(state, seat)}`);

  // 最近动作
  let last = state.last_action;
  if (!last && Array.isArray(state.action_seq) && state.action_seq.length > 0) {
    last = state.action_seq[state.action_seq.length - 1];
  }
  lines.push(`【最近动作】${last ? fmtActionSeq(last) : "无"}`);

  // 剩余牌
  const remain = state.remain_card_stack ?? [];
  const remainCount = Array.isArray(remain) ? remain.length : 0;
  lines.push(`【剩余牌】${remainCount} 张`);

  return lines.join("\n");
}

/**
 * 将 game_state JSON 渲染为中文场面描述
 */
export function renderGameState(state: Record<string, any>, seat?: number): string {
  const resolvedSeat = resolveSeat(state, seat);
  return renderScene(state, resolvedSeat);
}
