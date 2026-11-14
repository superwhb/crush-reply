#!/usr/bin/env python3
"""crush-reply 多轮链与开场白质检。

在仓库根目录跑:
    python scripts/lint_extra.py                 检查 data/threads 和 data/openers.jsonl
    python scripts/lint_extra.py data/threads/daily.jsonl   只查一个文件

任何一条不通过就 exit 1，CI 会拦下 PR。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THREAD_DIR = ROOT / "data" / "threads"
OPENERS = ROOT / "data" / "openers.jsonl"

STAGES = {"初识", "聊得来", "暧昧", "已在恋爱"}
SCENES = {"daily", "period", "conflict", "jealousy", "latenight", "meetup",
          "family", "distance", "friends", "anniversary"}
THREAD_ID = re.compile(r"^th-[a-z]+-\d{2}$")
OPENER_ID = re.compile(r"^op-\d{3}$")
ANCHORS = {"共同经历", "她提过的事", "当下时空", "轻话题", "求助请教"}
BANNED = [
    "打压", "冷暴力", "欲擒故纵", "假装忙", "装忙", "多喝热水", "忍一忍",
    "矫情", "想太多", "未成年", "开房", "那就分手",
]
BANNED_CALLS = ["宝", "小仙女", "亲爱的", "臭宝", "老婆"]
LAZY = re.compile(r"^(哈{2,}|h{3,}|草)$", re.I)


def check_text(text: str, where: str, lo: int, hi: int, errors: list[str], label: str) -> None:
    if not isinstance(text, str):
        errors.append(f"{where}: {label} 要是字符串")
        return
    if "\n" in text:
        errors.append(f"{where}: {label} 有换行")
    if not lo <= len(text) <= hi:
        errors.append(f"{where}: {label} 长度 {len(text)}，要 {lo} 到 {hi} 字")
    for word in BANNED:
        if word in text:
            errors.append(f"{where}: {label} 命中红线词 {word!r}")
    for call in BANNED_CALLS:
        if call in text:
            errors.append(f"{where}: {label} 用了称呼 {call!r}，改成 {{称呼}}")
    if LAZY.match(text.strip()):
        errors.append(f"{where}: {label} 是单独哈哈哈")


def check_thread(t: dict, where: str, errors: list[str]) -> None:
    need = ["id", "scene", "title", "premise", "turns", "exit", "tags", "difficulty"]
    missing = [k for k in need if k not in t]
    if missing:
        errors.append(f"{where}: 缺字段 {', '.join(missing)}")
        return
    if not THREAD_ID.match(str(t["id"])):
        errors.append(f"{where}: id 不合规 {t['id']!r}，要像 th-daily-01")
    if t["scene"] not in SCENES:
        errors.append(f"{where}: scene 不在枚举里 {t['scene']!r}")
    elif str(t["id"]).split("-")[1] != t["scene"]:
        errors.append(f"{where}: id 前缀和 scene 不一致 {t['id']} / {t['scene']}")
    check_text(t["title"], where, 4, 20, errors, "title")
    check_text(t["premise"], where, 10, 80, errors, "premise")
    check_text(t["exit"], where, 6, 80, errors, "exit")

    turns = t["turns"]
    if not isinstance(turns, list) or not 3 <= len(turns) <= 5:
        errors.append(f"{where}: turns 要 3 到 5 轮")
    else:
        for i, turn in enumerate(turns):
            if not isinstance(turn, dict) or set(turn) < {"her", "you", "why"}:
                errors.append(f"{where}: turns[{i}] 要是 {{her, you, why}}")
                continue
            check_text(turn["her"], where, 2, 60, errors, f"turns[{i}].her")
            check_text(turn["you"], where, 4, 60, errors, f"turns[{i}].you")
            check_text(turn["why"], where, 4, 30, errors, f"turns[{i}].why")

    tags = t["tags"]
    if not isinstance(tags, list) or not 2 <= len(tags) <= 5:
        errors.append(f"{where}: tags 要 2 到 5 个")
    if t["difficulty"] not in (1, 2, 3):
        errors.append(f"{where}: difficulty 只能是 1/2/3")


def check_opener(o: dict, where: str, errors: list[str]) -> None:
    need = ["id", "scene", "stage", "anchor", "title", "example", "why", "followup", "tags", "difficulty"]
    missing = [k for k in need if k not in o]
    if missing:
        errors.append(f"{where}: 缺字段 {', '.join(missing)}")
        return
    if not OPENER_ID.match(str(o["id"])):
        errors.append(f"{where}: id 不合规 {o['id']!r}，要像 op-001")
    if o["anchor"] not in ANCHORS:
        errors.append(f"{where}: anchor 不在枚举里 {o['anchor']!r}")
    if not isinstance(o["stage"], list) or not o["stage"]:
        errors.append(f"{where}: stage 要是非空数组")
    else:
        bad = [s for s in o["stage"] if s not in STAGES]
        if bad:
            errors.append(f"{where}: stage 不在枚举里 {bad}")
    check_text(o["title"], where, 4, 20, errors, "title")
    check_text(str(o["example"]), where, 4, 60, errors, "example")
    check_text(str(o["why"]), where, 6, 60, errors, "why")
    check_text(str(o["followup"]), where, 6, 60, errors, "followup")
    tags = o["tags"]
    if not isinstance(tags, list) or not 2 <= len(tags) <= 5:
        errors.append(f"{where}: tags 要 2 到 5 个")
    if o["difficulty"] not in (1, 2, 3):
        errors.append(f"{where}: difficulty 只能是 1/2/3")


def load(path: Path, errors: list[str]):
    rel = path.as_posix().split("crush-reply/")[-1]
    rows = []
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append((path, f"{rel}:{lineno}", json.loads(line)))
            except json.JSONDecodeError as exc:
                errors.append(f"{rel}:{lineno}: JSON 解析失败 {exc}")
    return rows


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", help="只查指定 jsonl")
    args = parser.parse_args()

    errors: list[str] = []
    threads: list[dict] = []
    openers: list[dict] = []
    seen: dict[str, str] = {}

    if args.files:
        thread_paths = [Path(f) for f in args.files if "threads" in str(f)]
        opener_paths = [Path(f) for f in args.files if "openers" in str(f)]
    else:
        thread_paths = sorted(THREAD_DIR.glob("*.jsonl"))
        opener_paths = [OPENERS] if OPENERS.exists() else []

    for path in thread_paths:
        for _, where, row in load(path, errors):
            if not isinstance(row, dict):
                errors.append(f"{where}: 每行必须是一个对象")
                continue
            check_thread(row, where, errors)
            tid = str(row.get("id"))
            if tid in seen:
                errors.append(f"{where}: id 重复 {tid}，第一次出现在 {seen[tid]}")
            seen[tid] = where
            threads.append(row)

    for path in opener_paths:
        for _, where, row in load(path, errors):
            if not isinstance(row, dict):
                errors.append(f"{where}: 每行必须是一个对象")
                continue
            check_opener(row, where, errors)
            oid = str(row.get("id"))
            if oid in seen:
                errors.append(f"{where}: id 重复 {oid}，第一次出现在 {seen[oid]}")
            seen[oid] = where
            openers.append(row)

    if not threads and not openers:
        sys.exit(f"没找到多轮链或开场白: {THREAD_DIR} / {OPENERS}")

    if threads:
        print(f"多轮链 {len(threads)} 条，场景分布 {dict(Counter(t.get('scene') for t in threads))}")
        print(f"  平均 {sum(len(t.get('turns', [])) for t in threads) / len(threads):.1f} 轮")
    if openers:
        print(f"开场白 {len(openers)} 条，锚点分布 {dict(Counter(o.get('anchor') for o in openers))}")

    if errors:
        print(f"\n错误 {len(errors)} 条:")
        for e in errors:
            print(f"  x {e}")
        sys.exit(1)

    print("\n通过: 多轮链与开场白无错误。")


if __name__ == "__main__":
    main()