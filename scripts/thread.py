#!/usr/bin/env python3
"""crush-reply 多轮链检索。

卡片解决「这一条怎么回」，多轮链解决「回完她再说什么，你怎么接」。
用法:
    python scripts/thread.py "她说食堂难吃，我回完她说那你去给我做"
    python scripts/thread.py --scene conflict --top 2 "她还在生气"
    python scripts/thread.py --json "她已读不回"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from query import bm25, scene_boost, tokenize

ROOT = Path(__file__).resolve().parent.parent
THREAD_DIR = ROOT / "data" / "threads"


def load_threads() -> list[dict]:
    if not THREAD_DIR.is_dir():
        sys.exit(f"找不到多轮链目录: {THREAD_DIR}")
    threads: list[dict] = []
    for path in sorted(THREAD_DIR.glob("*.jsonl")):
        with path.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    thread = json.loads(line)
                except json.JSONDecodeError as exc:
                    sys.exit(f"{path.name}:{lineno} JSON 解析失败: {exc}")
                thread["_file"] = path.name
                threads.append(thread)
    if not threads:
        sys.exit("多轮链目录是空的")
    return threads


def index_text(thread: dict) -> str:
    turns = thread.get("turns", [])
    parts = [
        str(thread.get("title", "")) * 3,
        " ".join(thread.get("tags", [])) * 3,
        str(thread.get("premise", "")) * 2,
        " ".join(str(t.get("her", "")) for t in turns),
        " ".join(str(t.get("you", "")) for t in turns),
        str(thread.get("exit", "")),
    ]
    return " ".join(parts)


def render(thread: dict, rank: int) -> str:
    lines = [
        f"[{rank}] {thread['id']}  {thread['title']}   难度{thread['difficulty']}",
        f"    前提: {thread['premise']}",
        "    走向:",
    ]
    for i, turn in enumerate(thread["turns"], 1):
        lines.append(f"      {i}. 她: {turn['her']}")
        lines.append(f"         你: {turn['you']}   ({turn['why']})")
    lines.append(f"    收尾: {thread['exit']}")
    return "\n".join(lines)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="crush-reply 多轮链检索")
    parser.add_argument("query", nargs="*", help="当前聊到哪儿了")
    parser.add_argument("--scene", help="只看某个场景")
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    threads = load_threads()

    if args.list:
        for t in threads:
            print(f"{t['id']:<16} {t['title']:<14} {len(t['turns'])} 轮  难度{t['difficulty']}")
        return

    query = " ".join(args.query).strip()
    if not query:
        parser.error("给一句现在的情况，或者用 --list 看全部")

    pool = [t for t in threads if not args.scene or t["scene"] == args.scene]
    if not pool:
        sys.exit(f"场景 {args.scene} 下没有多轮链")

    tfs, df, avgdl = _reindex(pool)
    qtokens = tokenize(query)
    scored = []
    for thread, tf in zip(pool, tfs):
        s = bm25(qtokens, tf, df, avgdl, len(pool)) + scene_boost(query, thread)
        scored.append((s, thread))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    top = [(s, t) for s, t in scored if s > 0][: args.top]

    if not top:
        print("没有匹配的多轮链，换个说法，或者用 --list。", file=sys.stderr)
        sys.exit(3)

    if args.json:
        print(json.dumps([{"score": round(s, 3), **t} for s, t in top], ensure_ascii=False, indent=2))
        return

    print(f"查询: {query}    命中 {len(top)} 条\n")
    for i, (_, thread) in enumerate(top, 1):
        print(render(thread, i))
        print()
    print("提醒: 多轮链给的是走向和节奏。台词要按你自己的说法重写，别照念。")


def _reindex(pool: list[dict]):
    """按 index_text 建索引，工整一点单独放开。"""
    from collections import Counter
    tfs, df = [], Counter()
    for thread in pool:
        tf = Counter(tokenize(index_text(thread)))
        tfs.append(tf)
        for token in tf:
            df[token] += 1
    lens = [sum(tf.values()) for tf in tfs]
    avgdl = sum(lens) / len(lens) if lens else 1.0
    return tfs, df, avgdl


if __name__ == "__main__":
    main()