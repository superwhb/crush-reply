#!/usr/bin/env python3
"""开场白检索。以前只能翻 data/openers.jsonl，现在按由头和关系阶段挑。

由头五种：她提过的事 / 共同经历 / 当下时空 / 轻话题 / 求助请教。
优先级不是固定的：她提过的事最像「你在听」，当下时空最容易显得在追。

用法:
    python scripts/openers.py "想找个话题开口"
    python scripts/openers.py --anchor 她提过的事 --stage 暧昧 --n 3
    python scripts/openers.py --json
    python scripts/openers.py --list
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPENERS = ROOT / "data" / "openers.jsonl"

ANCHORS = ["她提过的事", "共同经历", "轻话题", "求助请教", "当下时空"]


def load() -> list[dict]:
    if not OPENERS.exists():
        sys.exit(f"找不到 {OPENERS}")
    rows = []
    for lineno, line in enumerate(OPENERS.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            sys.exit(f"openers.jsonl:{lineno} 解析失败 {exc}")
    return rows


def _has_event(profile: str) -> bool:
    """画像里「近期事件」有值，就优先用她提过的事。"""
    for line in (profile or "").splitlines():
        line = line.strip()
        if line.startswith("近期事件"):
            _, _, value = line.replace("：", ":", 1).partition(":")
            return bool(value.strip())
    return False


def pick(profile: str = "", n: int = 3, anchor: str | None = None,
         stage: str | None = None) -> list[dict]:
    rows = load()
    if stage:
        rows = [r for r in rows if stage in (r.get("stage") or [])]
    if anchor:
        rows = [r for r in rows if r.get("anchor") == anchor]
    if not rows:
        return []

    order = {name: i for i, name in enumerate(ANCHORS)}
    # 画像里有近期事件，说明「她提过的事」有料可用，优先它；否则按默认顺序。
    rank = dict(order)
    if not _has_event(profile):
        rank["她提过的事"] = rank.get("她提过的事", 0) + 0.5
    rows.sort(key=lambda r: (rank.get(r.get("anchor"), 9), r.get("difficulty", 1), r["id"]))
    return rows[:n]


def render(row: dict, rank: int) -> str:
    return "\n".join([
        f"[{rank}] {row['id']}  {row['title']}   {row['anchor']}  难度{row.get('difficulty', 1)}",
        f"    可以这样发: {row['example']}",
        f"    她接得住因为: {row['why']}",
        f"    她回了之后: {row['followup']}",
    ])


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="开场白检索")
    parser.add_argument("query", nargs="*", help="你的处境，比如「三天没聊了想开口」")
    parser.add_argument("--anchor", choices=ANCHORS, help="只挑某一种由头")
    parser.add_argument("--stage", choices=["初识", "聊得来", "暧昧", "已在恋爱"], help="只看适合某阶段的")
    parser.add_argument("-n", "--n", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    if args.list:
        for row in load():
            print(f"{row['id']}  {row['anchor']:<8} {row['title']:<14} 难度{row.get('difficulty', 1)}")
        return

    query = " ".join(args.query)
    # 问到「她提过的事」这类原词时直接尊重它
    anchor = args.anchor or next((a for a in ANCHORS if a in query), None)
    rows = pick(profile="", n=args.n, anchor=anchor, stage=args.stage)
    if not rows:
        sys.exit("没有符合条件的开场白，去掉 --anchor 或 --stage 再试")

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    for i, row in enumerate(rows, 1):
        print(render(row, i))
        print()
    print("提醒: 开场是给你一个由头，不要照念。挑一条改成你自己的说法，别一次把三个问题都问出去。")


if __name__ == "__main__":
    main()