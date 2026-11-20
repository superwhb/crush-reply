#!/usr/bin/env python3
"""结果回写：她到底接没接住。

没有这一步，500 张卡的排序永远只按词面走，「越用越准」就是句空话。
每条记录只存卡片 id、反应、一句备注，存在 ~/.crush-reply/outcomes.jsonl，
不进仓库，也不写对方真名。

用法:
    python scripts/outcome.py log period-004 --reaction 回了 --note "她笑了，接着聊了两句"
    python scripts/outcome.py log conflict-011 --reaction 没回
    python scripts/outcome.py stats            # 全部
    python scripts/outcome.py stats period-004
    python scripts/outcome.py list --last 20
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import paths

REACTIONS = {
    "回了": 1, "热": 1, "接住": 1, "笑了": 1,
    "一般": 0, "敷衍": 0, "中性": 0, "看不出来": 0,
    "没回": -1, "冷": -1, "已读不回": -1, "更冷": -1,
}


def _rows() -> list[dict]:
    path = paths.outcomes_file()
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def cmd_log(args) -> int:
    reaction = args.reaction
    if reaction not in REACTIONS:
        sys.exit(f"反应只能是 {' / '.join(REACTIONS)} 里的一个，收到的是 {reaction!r}")
    paths.data_home().mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "id": args.card_id,
        "reaction": reaction,
        "score": REACTIONS[reaction],
    }
    if args.note:
        row["note"] = args.note
    if args.profile:
        row["profile"] = args.profile
    with paths.outcomes_file().open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"记下了: {args.card_id} -> {reaction}（共 {len(_rows())} 条）")
    print("下次检索会自动给这张卡加减分，加减幅度很小，不会因为一次偶然就翻盘。")
    return 0


def _summary(rows: list[dict]) -> dict[str, dict]:
    agg: dict[str, dict] = defaultdict(lambda: {"n": 0, "sum": 0, "last": None})
    for row in rows:
        cid = row.get("id")
        if not cid:
            continue
        agg[cid]["n"] += 1
        agg[cid]["sum"] += int(row.get("score") or 0)
        agg[cid]["last"] = row
    return agg


def cmd_stats(args) -> int:
    rows = _rows()
    if not rows:
        print("还没有记录。回答完之后跑一次 `python scripts/outcome.py log <卡片id> --reaction 回了`。")
        return 0
    agg = _summary(rows)
    if args.card_id:
        if args.card_id not in agg:
            sys.exit(f"没有 {args.card_id} 的记录")
        item = agg[args.card_id]
        print(f"{args.card_id}: {item['n']} 次，净分 {item['sum']:+d}")
        for row in rows:
            if row.get("id") == args.card_id:
                print(f"  {row.get('ts', '')}  {row.get('reaction')}  {row.get('note', '')}")
        return 0

    print(f"共 {len(rows)} 条记录，覆盖 {len(agg)} 张卡")
    ranked = sorted(agg.items(), key=lambda kv: (-(kv[1]["sum"] / kv[1]["n"]), -kv[1]["n"]))
    print("\n最有效（净分/次数）：")
    for cid, item in ranked[:5]:
        print(f"  {cid:<16} {item['n']:>2} 次  净分 {item['sum']:+d}  最近 {item['last'].get('reaction')}")

    # 只有一张卡时，两栏内容完全一样，没信息量。攒到两张再分高低。
    if len(ranked) >= 2 and ranked[-1][1]["sum"] < ranked[0][1]["sum"]:
        print("\n最没效：")
        for cid, item in reversed(ranked[-5:]):
            print(f"  {cid:<16} {item['n']:>2} 次  净分 {item['sum']:+d}  最近 {item['last'].get('reaction')}")
    elif len(ranked) < 2:
        print("\n只有一张卡有记录，还看不出高低。多记几次再来。")
    else:
        print("\n目前没有哪张卡明显失灵。")
    print("\n这说明不了因果：她回不回还看当天心情、关系、你平时怎么聊。只用来看哪类卡在你这儿失灵。")
    return 0


def cmd_list(args) -> int:
    rows = _rows()[-args.last:]
    if not rows:
        print("还没有记录")
        return 0
    for row in rows:
        print(f"{row.get('ts', '')}  {row.get('id', ''):<16} {row.get('reaction'):<6} {row.get('note', '')}")
    return 0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="结果回写")
    sub = parser.add_subparsers(dest="action", required=True)

    log = sub.add_parser("log", help="记一条结果")
    log.add_argument("card_id")
    log.add_argument("--reaction", required=True, help=" / ".join(REACTIONS))
    log.add_argument("--note", default="", help="一句备注，别写对方真名")
    log.add_argument("--profile", default="", help="画像代号，可选")
    log.set_defaults(func=cmd_log)

    stats = sub.add_parser("stats", help="看哪张卡在你这里有效")
    stats.add_argument("card_id", nargs="?")
    stats.set_defaults(func=cmd_stats)

    listing = sub.add_parser("list", help="最近的记录")
    listing.add_argument("--last", type=int, default=20)
    listing.set_defaults(func=cmd_list)

    args = parser.parse_args()
    paths.ensure()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()