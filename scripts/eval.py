#!/usr/bin/env python3
"""检索回归测试：拿真人会问的句子，看能不能搜到对的卡。

在仓库根目录跑:
    python scripts/eval.py            跑全部用例
    python scripts/eval.py -v         打印每条命中的是什么

用例在 evals/cases.jsonl，一行一个：
    {"query": "...", "scene": "period", "expect_any": ["第一天", "疼得厉害"], "note": "..."}

判定：卡片渲染出来的文字里出现 expect_any 里任意一个关键词，就算这一条命中了。
hit@1 看第一条卡，hit@3 看前三张。CI 要求 hit@3 >= 0.9，改了检索参数要重跑。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from query import bm25, load_cards, render, scene_boost, tokenize  # noqa: E402

CASES = ROOT / "evals" / "cases.jsonl"


def search(query: str, pool: list[dict], top: int) -> list[tuple[float, dict]]:
    from collections import Counter

    tfs, df = [], Counter()
    for card in pool:
        tf = Counter(tokenize(
            str(card.get("title", "")) * 3 + " " + " ".join(card.get("tags", [])) * 3 + " "
            + str(card.get("signal", "")) * 2 + " " + " ".join(e.get("text", "") for e in card.get("examples", []))
        ))
        tfs.append(tf)
        for token in tf:
            df[token] += 1
    lens = [sum(tf.values()) for tf in tfs]
    avgdl = sum(lens) / len(lens) if lens else 1.0
    qtokens = tokenize(query)
    scored = [(bm25(qtokens, tf, df, avgdl, len(pool)) + scene_boost(query, c), c) for tf, c in zip(tfs, pool)]
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [(s, c) for s, c in scored if s > 0][:top]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if not CASES.exists():
        sys.exit(f"找不到用例文件: {CASES}")

    root_cards = load_cards()
    cases = []
    for lineno, line in enumerate(CASES.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as exc:
            sys.exit(f"cases.jsonl:{lineno} 解析失败 {exc}")

    hit1 = hit3 = 0
    misses = []
    for case in cases:
        pool = [c for c in root_cards if not case.get("scene") or c["scene"] == case["scene"]]
        top = search(case["query"], pool, 3)
        texts = [render(c, i + 1) for i, (_, c) in enumerate(top)]
        keys = case["expect_any"]
        first = any(k in texts[0] for k in keys) if texts else False
        among3 = any(any(k in t for k in keys) for t in texts)
        hit1 += first
        hit3 += among3
        if not among3:
            misses.append((case, [c["id"] for _, c in top]))
        if args.verbose:
            mark = "OK1" if first else ("OK3" if among3 else "MISS")
            ids = ",".join(c["id"] for _, c in top)
            print(f"{mark} {case['query'][:26]:<28} -> {ids}")

    n = len(cases)
    print(f"\n用例 {n} 条")
    print(f"hit@1 {hit1}/{n} = {hit1 / n:.0%}")
    print(f"hit@3 {hit3}/{n} = {hit3 / n:.0%}")

    if misses:
        print("\n没命中:")
        for case, ids in misses:
            print(f"  x {case['query']}  (期望含 {case['expect_any']}，实际 {ids})")

    sys.exit(0 if hit3 / n >= 0.9 else 1)


if __name__ == "__main__":
    main()