#!/usr/bin/env python3
"""检索回归测试：看能不能把对的那张卡排上去，而不是看关键词在不在。

两套用例：
- evals/cases/       用户会怎么问（会带上原话里的词），测基本盘
- evals/paraphrase/  换个说法问（故意避开卡里的关键词），测泛化

一行一条，判定用卡 id，不用关键词：
    {"query": "她说的原话或你的转述", "scene": "period", "expect": ["period-004"]}

四项指标：
- hit@1 / hit@3  对的那张卡在不在第一 / 前三
- MRR            第一次命中的排名倒数，越接近 1 越好
- route@1        第一张卡的场景对不对（模型常常不带 --scene，这一项是兜底）

门槛在 evals/gate.json，按场景卡，任何一个场景掉线 CI 就红。

    python scripts/eval.py              跑两套
    python scripts/eval.py -v           每条都打印
    python scripts/eval.py --calibrate  看「对得上」和「完全不相关」的分数重叠多少
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from index import Index, load_cards  # noqa: E402

TRACKS = [
    ("直接问法", ROOT / "evals" / "cases", "min_", "scene_min_hit3"),
    ("换个说法", ROOT / "evals" / "paraphrase", "para_min_", "para_scene_min_hit3"),
]
GATE_FILE = ROOT / "evals" / "gate.json"
OFFTOPIC = ROOT / "evals" / "offtopic.txt"

DEFAULT_GATE = {
    "min_hit1": 0.80,
    "min_hit3": 0.90,
    "min_mrr": 0.85,
    "min_route": 0.90,
    "scene_min_hit3": 0.80,
    "para_min_hit1": 0.55,
    "para_min_hit3": 0.75,
    "para_min_mrr": 0.65,
    "para_min_route": 0.80,
    "para_scene_min_hit3": 0.50,
}


def load_cases(directory: Path) -> list[dict]:
    if not directory.is_dir():
        sys.exit(f"找不到用例目录: {directory}")
    cases: list[dict] = []
    for path in sorted(directory.glob("*.jsonl")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as exc:
                sys.exit(f"{path.name}:{lineno} 解析失败 {exc}")
            for key in ("query", "scene", "expect"):
                if key not in case:
                    sys.exit(f"{path.name}:{lineno} 缺字段 {key}")
            cases.append(case)
    if not cases:
        sys.exit(f"{directory} 是空的")
    return cases


def load_gate() -> dict:
    gate = dict(DEFAULT_GATE)
    if GATE_FILE.exists():
        try:
            gate.update(json.loads(GATE_FILE.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            sys.exit(f"gate.json 解析失败: {exc}")
    return gate


def evaluate(index: Index, cases: list[dict], verbose: bool) -> dict:
    per_scene: dict[str, dict] = {}
    for case in cases:
        per_scene.setdefault(case["scene"], []).append(case)

    results: dict[str, dict] = {}
    for scene, rows in per_scene.items():
        hit1 = hit3 = route = 0
        rr_sum = 0.0
        misses = []
        for case in rows:
            top = index.search(case["query"], top=3, scene=case.get("scene"), use_outcomes=False)
            ids = [str(card.get("id")) for _, card in top]
            expect = set(case["expect"])
            pos = next((i for i, cid in enumerate(ids, 1) if cid in expect), 0)
            hit1 += pos == 1
            hit3 += pos > 0
            rr_sum += (1.0 / pos) if pos else 0.0
            route += bool(top) and top[0][1].get("scene") == case["scene"]
            if pos == 0:
                misses.append((case, ids))
            if verbose:
                mark = "OK1" if pos == 1 else ("OK3" if pos else "MISS")
                print(f"{mark:<4} {scene:<11} {case['query'][:30]:<32} -> {','.join(ids)}")
        n = len(rows)
        results[scene] = {
            "n": n,
            "hit1": hit1 / n,
            "hit3": hit3 / n,
            "mrr": rr_sum / n,
            "route": route / n,
            "misses": misses,
        }
    return results


def report(title: str, per_scene: dict, gate: dict, prefix: str, scene_key: str) -> int:
    print(f"\n== {title} ==")
    print(f"{'场景':<12}{'条数':>4}{'hit@1':>8}{'hit@3':>8}{'MRR':>8}{'route':>8}")
    total = {k: 0.0 for k in ("n", "hit1", "hit3", "mrr", "route")}
    for scene, m in sorted(per_scene.items()):
        print(f"{scene:<12}{m['n']:>4}{m['hit1']:>8.0%}{m['hit3']:>8.0%}{m['mrr']:>8.2f}{m['route']:>8.0%}")
        total["n"] += m["n"]
        for key in ("hit1", "hit3", "mrr", "route"):
            total[key] += m[key] * m["n"]
    n = total["n"] or 1
    agg = {k: total[k] / n for k in ("hit1", "hit3", "mrr", "route")}
    print(f"{'总计':<12}{int(total['n']):>4}{agg['hit1']:>8.0%}{agg['hit3']:>8.0%}{agg['mrr']:>8.2f}{agg['route']:>8.0%}")

    failures = []
    for key, label in (("hit1", "hit@1"), ("hit3", "hit@3"), ("mrr", "MRR"), ("route", "route@1")):
        threshold = gate.get(prefix + key)
        if threshold is not None and agg[key] < threshold:
            failures.append(f"{label} {agg[key]:.0%} < 门槛 {threshold:.0%}")
    scene_floor = gate.get(scene_key)
    if scene_floor is not None:
        for scene, m in sorted(per_scene.items()):
            if m["hit3"] < scene_floor:
                failures.append(f"场景 {scene} hit@3 {m['hit3']:.0%} < 门槛 {scene_floor:.0%}")

    if failures:
        print("没过门槛:")
        for line in failures:
            print(f"  x {line}")
        for scene, m in sorted(per_scene.items()):
            for case, ids in m["misses"]:
                print(f"  x [{scene}] {case['query']}  期望 {case['expect']}  实际 {ids}")
        return 1
    print("过门槛。")
    return 0


def calibrate(index: Index) -> int:
    """「对得上」和「完全无关」的分数重叠多少。重叠越大，说明分数不能当置信度用。"""
    if not OFFTOPIC.exists():
        print(f"没有 {OFFTOPIC.name}，跳过校准")
        return 0
    cases = load_cases(ROOT / "evals" / "cases")
    matched = [(index.search(c["query"], top=1, scene=c["scene"], use_outcomes=False) or [(0.0, None)])[0]
               for c in cases]
    off = [line.strip() for line in OFFTOPIC.read_text(encoding="utf-8").splitlines()
           if line.strip() and not line.startswith("#")]
    unrelated = [(index.search(q, top=1, use_outcomes=False) or [(0.0, None)])[0] for q in off]

    def stats(rows):
        scores = sorted(score for score, _ in rows)
        return (scores[0], scores[len(scores) // 2], scores[-1])

    m_lo, m_mid, m_hi = stats(matched)
    u_lo, u_mid, u_hi = stats(unrelated)
    print(f"对得上的 {len(matched)} 条: top1 分数 min {m_lo:.1f} / 中位 {m_mid:.1f} / max {m_hi:.1f}")
    print(f"不相关的 {len(unrelated)} 条: top1 分数 min {u_lo:.1f} / 中位 {u_mid:.1f} / max {u_hi:.1f}")
    overlap = sum(1 for score, _ in unrelated if score >= m_mid)
    print(f"不相关的查询里，有 {overlap} 条分数达到或超过相关用例的中位数（{m_mid:.1f}），这部分是假阳性风险。")
    return 0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--calibrate", action="store_true")
    args = parser.parse_args()

    index = Index(load_cards())

    if args.calibrate:
        sys.exit(calibrate(index))

    gate = load_gate()
    code = 0
    for title, directory, prefix, scene_key in TRACKS:
        code |= report(title, evaluate(index, load_cases(directory), args.verbose), gate, prefix, scene_key)
    sys.exit(code)


if __name__ == "__main__":
    main()