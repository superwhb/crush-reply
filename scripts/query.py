#!/usr/bin/env python3
"""crush-reply 情境检索。

零依赖：中文按整段 + 二元组 + 单字建索引，BM25 排序。索引实现在 scripts/index.py，
demo.py / eval.py / thread.py 跟这里共用同一份，不再各写一套。

用法:
    python scripts/query.py "她说明天来例假，肚子疼得起不来"
    python scripts/query.py --scene period --top 3 "肚子疼"
    python scripts/query.py "她还在生气" --min-difficulty 3     # 只看高难度的卡
    python scripts/query.py "她生日忘了" --stage 暧昧
    python scripts/query.py --json "她生我气了"
    python scripts/query.py --explain "她说疼"
    python scripts/query.py --list
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from index import SCENES, SCENE_BOOST, WEAK_SCORE, Index, load_cards, render, scene_hits


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="crush-reply 情境检索")
    parser.add_argument("query", nargs="*", help="对方说了什么，或者你想问什么")
    parser.add_argument("--scene", choices=sorted(SCENES), help="只看某个场景")
    parser.add_argument("--stage", choices=["初识", "聊得来", "暧昧", "已在恋爱"],
                        help="只看适用于某个关系阶段的卡")
    parser.add_argument("--difficulty", type=int, choices=[1, 2, 3], help="只看某个难度")
    parser.add_argument("--min-difficulty", type=int, choices=[1, 2, 3],
                        help="只看难度大于等于这个值的卡（冲突这类场合用 3）")
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

    index = Index(cards)
    top = index.search(
        query,
        top=args.top,
        scene=args.scene,
        stage=args.stage,
        difficulty=args.difficulty,
        min_difficulty=args.min_difficulty,
    )

    if not top:
        print("没有匹配的卡片。可以换个说法，去掉阶段/难度限制，或者用 --list 找相近的情境。",
              file=sys.stderr)
        sys.exit(3)

    if args.json:
        payload = [{"score": round(s, 3), **c} for s, c in top]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"查询: {query}    命中 {len(top)} 张\n")

    if args.explain:
        print("== 为什么是这几张（前 3 名）==")
        for i, (score, card) in enumerate(top[:3], 1):
            boost = SCENE_BOOST * len(scene_hits(query, card["scene"]))
            rows = index.explain(query, card)
            print(f"[{i}] {card['id']}  总分 {score:.2f} = 文本 {score - boost:.2f} + 场景 {boost:.2f}")
            hits = scene_hits(query, card["scene"])
            if hits:
                print(f"    场景词: {' / '.join(hits[:5])}  （每个 +{SCENE_BOOST}，最多三个）")
            if rows:
                parts = [f"{tok}×{freq}(df{dfreq},{contrib:.2f})" for tok, freq, dfreq, contrib in rows]
                print("    命中词: " + "；".join(parts))
            else:
                print("    命中词: 无（只靠场景加成进来的，说明这句话和卡里的措辞差得远）")
        print()

    for i, (score, card) in enumerate(top, 1):
        print(render(card, i))
        print()
    if top[0][0] < WEAK_SCORE:
        print(f"注意: 最高分只有 {top[0][0]:.1f}（低于 {WEAK_SCORE:.0f}），这几张可能只是词对上了，"
              "情境不一定对。换个说法，或者走「库里没有怎么办」。", file=sys.stderr)
    print("提醒: 卡片给的是方向，不要照抄。用你自己的话、按对方的画像重写成一句能直接发出去的微信。")


if __name__ == "__main__":
    main()