#!/usr/bin/env python3
"""crush-reply 概念参照。

情境卡告诉你怎么回，这个文件告诉你为什么这么回。
用法:
    python scripts/psych.py --scene conflict
    python scripts/psych.py "她以前不回我，现在一直追问"
    python scripts/psych.py --list
    python scripts/psych.py --concept 四骑士

说明：这里存的是公开研究里的概念，用来解释判断，不用来给对方贴标签。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PSYCH_FILE = ROOT / "data" / "psych.jsonl"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from index import token_weight, tokenize  # noqa: E402


def load() -> list[dict]:
    if not PSYCH_FILE.exists():
        sys.exit(f"找不到 {PSYCH_FILE}，先跑 scripts/lint_psych.py 看看")
    out = []
    with PSYCH_FILE.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                sys.exit(f"psych.jsonl:{lineno} 解析失败: {exc}")
    return out


def score(query_tokens: list[str], item: dict) -> float:
    hay = " ".join([
        item.get("concept", ""),
        " ".join(item.get("tags", [])),
        item.get("when", ""),
        item.get("say", ""),
        item.get("do", ""),
    ])
    hay_tokens = set(tokenize(hay))
    # 单字也放进来（以前会把长度 1 的词全丢掉，「她说疼」这类的概念就一条都搜不到），
    # 但按 index 里的单字权重打折。
    return sum(token_weight(t) for t in set(query_tokens) if t in hay_tokens)


def render(item: dict) -> str:
    return "\n".join([
        f"{item['id']}  {item['concept']}   [{item['source']}]",
        f"  用在哪: {item['when']}",
        f"  一句话: {item['say']}",
        f"  怎么做: {item['do']}",
        f"  别用成: {item['dont']}",
    ])


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="crush-reply 概念参照")
    ap.add_argument("query", nargs="*", help="描述你的处境，或者你担心的点")
    ap.add_argument("--scene", help="只看某类场景，比如 conflict / period / jealousy")
    ap.add_argument("--concept", help="按概念名找，比如 四骑士 / 情绪确认")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    items = load()

    if args.list:
        for item in items:
            print(f"{item['id']}  {item['concept']:<12} {'/'.join(item.get('scenes', []))}")
        return

    pool = items
    if args.scene:
        pool = [i for i in items if args.scene in i.get("scenes", [])]
        if not pool:
            sys.exit(f"场景 {args.scene} 下没有概念，先看 --list")
    if args.concept:
        kw = args.concept.strip()
        pool = [i for i in pool if kw in i["concept"] or kw in " ".join(i.get("tags", []))]
        if not pool:
            sys.exit(f"没找到概念 {kw}")

    query = " ".join(args.query).strip()
    if not query:
        picked = pool[: args.top]
    else:
        qtokens = tokenize(query)
        scored = sorted(((score(qtokens, i), i) for i in pool), key=lambda p: (-p[0], p[1]["id"]))
        picked = [i for s, i in scored if s > 0][: args.top]
        if not picked:
            picked = pool[: args.top]
            print("没匹配到具体概念，先看这几条通用的：\n")

    if args.json:
        print(json.dumps(picked, ensure_ascii=False, indent=2))
        return

    for item in picked:
        print(render(item))
        print()
    print("提醒: 概念是用来解释判断的，不要说成「你就是回避型」。人不是标签，贴上去她只会关门。")
    print("出处都是公开出版物，没有逐条附链接；真要引用前按书名核对一遍，别把概念名说给对方听。")


if __name__ == "__main__":
    main()