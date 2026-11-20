#!/usr/bin/env python3
"""今日情报：把「今天该搜什么」和「库里现在有什么」对齐成一份简报。

harvest.py plan 只给检索词，得自己一条条去库里查。这个脚本把两件事合起来：
每个检索词跑一遍检索，命中的卡列出来，命不中的单独列成「可能的数据缺口」。

日报里全是 open 的 issue 没人看，是因为它只提出问题、不给对照。这份简报的
每一行都对应库里现成的卡，扫一眼就知道该补哪。

用法:
    python scripts/intel.py                 # 今天的
    python scripts/intel.py --day 2026-11-20 -n 3
    python scripts/intel.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from harvest import parse_day, plan_groups  # noqa: E402
from index import WEAK_SCORE, Index, load_cards  # noqa: E402


def build(day, n: int, avoid_days: int, per_query: int = 2) -> dict:
    picked, hot = plan_groups(day, n, avoid_days)
    index = Index(load_cards())
    groups = []
    gaps = []
    for group in picked:
        rows = []
        for query in group["queries"]:
            top = index.search(query, top=per_query, scene=group["scene"], use_outcomes=False)
            hits = [{"id": c["id"], "title": c["title"], "score": round(s, 1)} for s, c in top]
            rows.append({"query": query, "hits": hits})
            if not hits or hits[0]["score"] < WEAK_SCORE:
                gaps.append({
                    "topic": group["topic"],
                    "scene": group["scene"],
                    "query": query,
                    "best": hits[0] if hits else None,
                })
        groups.append({"topic": group["topic"], "scene": group["scene"],
                       "watch": group["watch"], "queries": rows})
    return {"date": day.isoformat(), "hot": hot, "groups": groups, "gaps": gaps}


def render(report: dict) -> str:
    out = [f"# 今日情报 {report['date']}", ""]
    if report["hot"]:
        out += [f"> 这几组最近搜过，重点看上次没看完的部分：{'、'.join(report['hot'])}", ""]

    out += ["## 今天的检索计划（每条都已对过库里现有的卡）", ""]
    for group in report["groups"]:
        out += [f"### {group['topic']} → `{group['scene']}`", ""]
        for row in group["queries"]:
            if row["hits"]:
                line = "；".join(f"{h['id']} {h['title']}（{h['score']}）" for h in row["hits"])
                out.append(f"- `{row['query']}` → {line}")
            else:
                out.append(f"- `{row['query']}` → 库里没有")
        out += ["", f"提防：{group['watch']}", ""]

    out += ["## 库里可能缺的", ""]
    if not report["gaps"]:
        out.append("这轮没有明显缺口。")
    else:
        for gap in report["gaps"]:
            best = gap["best"]
            tail = f"最高分 {best['score']}，{best['id']} 也只是沾边" if best else "一条都没沾上"
            out.append(f"- [{gap['scene']}] `{gap['query']}` —— {tail}")
        out += ["", "这些是候选，不是结论：先看 research/README.md 的收卡口径，"
                    "确认是「库里真没有」而不是「说法不一样」，再决定要不要收。"]
    out += ["", "---", "",
            "看完把值得收的写进 `research/inbox/<日期>.jsonl`，跑 `python scripts/harvest.py check`。"]
    return "\n".join(out)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="今日情报简报")
    parser.add_argument("--day", help="YYYY-MM-DD，默认今天")
    parser.add_argument("-n", type=int, default=3, help="今天搜几组")
    parser.add_argument("--avoid-days", type=int, default=14)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build(parse_day(args.day), args.n, args.avoid_days)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))


if __name__ == "__main__":
    main()