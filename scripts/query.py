#!/usr/bin/env python3
"""crush-reply 情境检索。

零依赖：中文按字符二元组建索引，BM25 排序。
用法:
    python scripts/query.py "她说明天来例假，肚子疼得起不来"
    python scripts/query.py --scene period --top 3 "肚子疼"
    python scripts/query.py --json "她生我气了"
    python scripts/query.py --list
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENE_DIR = ROOT / "data" / "scenes"

SCENES = {
    "daily": "分享日常",
    "period": "生理期",
    "conflict": "闹矛盾",
    "jealousy": "吃醋",
    "latenight": "深夜情绪",
    "meetup": "约出来",
    "family": "家人与家庭",
    "distance": "异地",
    "friends": "朋友与社交",
    "anniversary": "生日与纪念日",
}

# 场景先验：命中这些词时给对应场景加一点分
SCENE_HINTS = {
    "period": "生理期 大姨妈 例假 月经 痛经 肚子疼 腰酸 经期 推迟 提前 血 卫生巾",
    "conflict": "生气 吵架 冷战 道歉 惹 不高兴 闹 误会 责怪 委屈 和好 不理我",
    "jealousy": "吃醋 前任 异性 别的男生 别的女生 追他 追她 谁 合照 点赞 占有欲",
    "latenight": "凌晨 半夜 深夜 睡不着 失眠 emo 丧 压力 想哭 崩溃 撑不住 焦虑 想家",
    "meetup": "约 见面 出来 周末 去哪 吃饭 看电影 咖啡 表白 拒绝 改期 爽约 异地",
    "daily": "日常 分享 照片 猫 狗 歌 天气 食堂 外卖 累 无聊 干嘛 在吗",
    "family": "家里 爸妈 父亲 母亲 父母 催婚 相亲 亲戚 弟弟 妹妹 姐姐 哥哥 奶奶 爷爷 回家 过年",
    "distance": "异地 火车 高铁 机票 车票 时差 见面 视频 手机 距离 城市 搬家 调岗",
    "friends": "朋友 闺蜜 兄弟 聚会 同学 同事 介绍 见朋友 一起玩 圈子 聊天记录",
    "anniversary": "生日 纪念日 礼物 一周年 一百天 惊喜 蛋糕 花 情人节 520 圣诞 跨年 忘了",
}

_CJK = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z]+|\d+")


def tokenize(text: str) -> list[str]:
    """中文取二元组（单字串取单字），英文和数字整体保留。"""
    out: list[str] = []
    for run in _CJK.findall(text or ""):
        if runisascii(run):
            out.append(run.lower())
        elif len(run) == 1:
            out.append(run)
        else:
            out.append(run)
            out.extend(run[i:i + 2] for i in range(len(run) - 1))
    return out


def runisascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def load_cards() -> list[dict]:
    if not SCENE_DIR.is_dir():
        sys.exit(f"找不到数据目录: {SCENE_DIR}")
    cards: list[dict] = []
    for path in sorted(SCENE_DIR.glob("*.jsonl")):
        if path.name.startswith("_"):
            continue
        with path.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    card = json.loads(line)
                except json.JSONDecodeError as exc:
                    sys.exit(f"{path.name}:{lineno} JSON 解析失败: {exc}")
                card["_file"] = path.name
                cards.append(card)
    if not cards:
        sys.exit("数据目录里没有卡片，先跑 scripts/lint_data.py 看看是不是格式错了")
    return cards


def index_text(card: dict) -> str:
    """标题和标签权重最高，靠重复次数实现。"""
    parts = [
        str(card.get("title", "")) * 3,
        " ".join(card.get("tags", [])) * 3,
        str(card.get("signal", "")) * 2,
        str(card.get("goal", "")),
        " ".join(card.get("moves", [])),
        " ".join(e.get("text", "") for e in card.get("examples", [])),
    ]
    return " ".join(parts)


def build_index(cards: list[dict]):
    tfs = []
    df: Counter = Counter()
    for card in cards:
        tokens = tokenize(index_text(card))
        tf = Counter(tokens)
        tfs.append(tf)
        for token in tf:
            df[token] += 1
    lens = [sum(tf.values()) for tf in tfs]
    avgdl = sum(lens) / len(lens) if lens else 1.0
    return tfs, df, avgdl


def bm25(qtokens, tf, df, avgdl, n_docs, k1=1.5, b=0.75) -> float:
    dl = sum(tf.values()) or 1
    score = 0.0
    for token in qtokens:
        freq = tf.get(token)
        if not freq:
            continue
        idf = math.log(1 + (n_docs - df[token] + 0.5) / (df[token] + 0.5))
        score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / avgdl))
    return score


def scene_boost(query: str, card: dict) -> float:
    scene = card.get("scene", "")
    hints = SCENE_HINTS.get(scene, "")
    hits = sum(1 for word in hints.split() if word in query)
    return min(hits, 3) * 0.45


def explain_terms(qtokens, tf, df, avgdl, n_docs, limit=6) -> list[tuple[str, int, int, float]]:
    """返回 [(token, 在卡里出现次数, 文档频率, 贡献分)]，按贡献从大到小。"""
    dl = sum(tf.values()) or 1
    rows = []
    seen = set()
    for token in qtokens:
        if token in seen:
            continue
        seen.add(token)
        freq = tf.get(token)
        if not freq:
            continue
        idf = math.log(1 + (n_docs - df[token] + 0.5) / (df[token] + 0.5))
        contrib = idf * (freq * (1.5 + 1)) / (freq + 1.5 * (1 - 0.75 + 0.75 * dl / avgdl))
        rows.append((token, freq, df[token], contrib))
    rows.sort(key=lambda r: -r[3])
    return rows[:limit]


def render(card: dict, rank: int) -> str:
    lines = [
        f"[{rank}] {card['id']}  {card['title']}   难度{card['difficulty']}  阶段:{'/'.join(card['stage'])}",
        f"    现场: {card['signal']}",
        f"    目标: {card['goal']}",
        f"    手法: {' / '.join(card['moves'])}",
        "    示例:",
    ]
    for ex in card["examples"]:
        lines.append(f"      - {ex['style']}  {ex['text']}")
    lines.append(f"    别说: {'；'.join(card['taboo'])}")
    lines.append(f"    续法: {card['followup']}")
    return "\n".join(lines)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="crush-reply 情境检索")
    parser.add_argument("query", nargs="*", help="对方说了什么，或者你想问什么")
    parser.add_argument("--scene", choices=sorted(SCENES), help="只看某个场景")
    parser.add_argument("--top", type=int, default=5, help="返回几张卡，默认 5")
    parser.add_argument("--json", action="store_true", help="输出 JSON，方便别的程序接")
    parser.add_argument("--explain", action="store_true",
                        help="打印命中了哪些词、场景加了多少分，看排名是怎么来的")
    parser.add_argument("--list", action="store_true", help="列出全部卡片")
    parser.add_argument("--stats", action="store_true", help="看看数据分布")
    args = parser.parse_args()

    cards = load_cards()

    if args.list:
        for card in cards:
            print(f"{card['id']:<14} {card['title']:<12} 难度{card['difficulty']}  {'/'.join(card['stage'])}")
        return

    if args.stats:
        print(f"卡片总数: {len(cards)}")
        for scene, label in SCENES.items():
            subset = [c for c in cards if c["scene"] == scene]
            if subset:
                hard = sum(1 for c in subset if c["difficulty"] == 3)
                print(f"  {scene:<10} {label:<8} {len(subset):>3} 张  其中高危 {hard} 张")
        return

    query = " ".join(args.query).strip()
    if not query:
        parser.error("给一句对方说的话，或者用 --list 看全部卡片")

    pool = [c for c in cards if not args.scene or c["scene"] == args.scene]
    if not pool:
        sys.exit(f"场景 {args.scene} 下没有卡片")

    tfs, df, avgdl = build_index(pool)
    qtokens = tokenize(query)
    scored = []
    for card, tf in zip(pool, tfs):
        s = bm25(qtokens, tf, df, avgdl, len(pool)) + scene_boost(query, card)
        scored.append((s, card))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    top = [(s, c) for s, c in scored if s > 0][: args.top]
    tf_by_id = {c["id"]: tf for c, tf in zip(pool, tfs)}

    if not top:
        print("没有匹配的卡片。可以换个说法，或者用 --list 找相近的情境。", file=sys.stderr)
        sys.exit(3)

    if args.json:
        payload = [{"score": round(s, 3), **c} for s, c in top]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"查询: {query}    命中 {len(top)} 张\n")

    if args.explain:
        print("— 为什么是这几张（前 3 名）—")
        for i, (score, card) in enumerate(top[:3], 1):
            boost = scene_boost(query, card)
            hits = [w for w in SCENE_HINTS.get(card["scene"], "").split() if w in query]
            rows = explain_terms(qtokens, tf_by_id[card["id"]], df, avgdl, len(pool))
            print(f"[{i}] {card['id']}  总分 {score:.2f} = 文本 {score - boost:.2f} + 场景 {boost:.2f}")
            if hits:
                print(f"    场景词: {' / '.join(hits[:5])}  （每个 +0.45，最多三个）")
            if rows:
                parts = [f"{tok}×{freq}(df{dfreq},{contrib:.2f})" for tok, freq, dfreq, contrib in rows]
                print("    命中词: " + "；".join(parts))
            else:
                print("    命中词: 无（只靠场景加成进来的，说明这句话和卡里的措辞差得远）")
        print()

    for i, (score, card) in enumerate(top, 1):
        print(render(card, i))
        print()
    print("提醒: 卡片给的是方向，不要照抄。用你自己的话、按对方的画像重写成一句能直接发出去的微信。")


if __name__ == "__main__":
    main()