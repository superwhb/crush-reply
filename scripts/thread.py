#!/usr/bin/env python3
"""多轮链检索。卡片解决「这一条怎么回」，多轮链解决「回完她再说什么，你怎么接」。

索引跟 query.py 共用 scripts/index.py，不再各自实现一套。

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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from index import SCENES, Index  # noqa: E402

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


def thread_text(thread: dict) -> str:
    turns = thread.get("turns") or []
    parts = [
        str(thread.get("title", "")) * 3,
        " ".join(thread.get("tags") or []) * 3,
        str(thread.get("premise", "")) * 2,
        " ".join(str(t.get("her", "")) for t in turns),
        " ".join(str(t.get("you", "")) for t in turns),
        str(thread.get("exit", "")),
    ]
    return " ".join(parts)


def render(thread: dict, rank: int) -> str:
    lines = [
        f"[{rank}] {thread['id']}  {thread['title']}   难度{thread.get('difficulty', 1)}",
        f"    前提: {thread['premise']}",
    ]
    for i, turn in enumerate(thread.get("turns") or [], 1):
        lines.append(f"    {i}. 她: {turn.get('her', '')}")
        lines.append(f"       你: {turn.get('you', '')}（{turn.get('why', '')}）")
    lines.append(f"    收尾: {thread['exit']}")
    return "\n".join(lines)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="多轮链检索")
    parser.add_argument("query", nargs="*")
    parser.add_argument("--scene", choices=sorted(SCENES))
    parser.add_argument("--top", type=int, default=2)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--list", action="store_true", help="只列出有哪些链")
    args = parser.parse_args()

    if args.list:
        for thread in load_threads():
            turns = len(thread.get("turns") or [])
            print(f"{thread['id']:<24} {thread['title']:<16} {turns} 轮  难度{thread.get('difficulty', 1)}")
        return

    query = " ".join(args.query).strip()
    if not query:
        parser.error("给一句她说的话，或者描述聊到哪一步卡住了")

    index = Index(load_threads(), text_fn=thread_text)
    top = index.search(query, top=args.top, scene=args.scene)
    if not top:
        print("没有匹配的多轮链。换个说法，或者先看 scripts/query.py --list。", file=sys.stderr)
        sys.exit(3)

    if args.json:
        print(json.dumps([{"score": round(s, 3), **t} for s, t in top], ensure_ascii=False, indent=2))
        return

    for i, (_, thread) in enumerate(top, 1):
        print(render(thread, i))
        print()
    print("提醒: 链是节奏参考，不是台词。看她回的长短再决定下一句，别一次把四轮都说完。")


if __name__ == "__main__":
    main()