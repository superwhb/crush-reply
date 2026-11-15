#!/usr/bin/env python3
"""crush-reply 概念参照质检。

在仓库根目录跑:
    python scripts/lint_psych.py

除了字段与长度，重点拦两类事：
1. 把概念写成诊断（「你就是回避型」「治愈」这类说法）
2. 场景覆盖缺口（10 类场景每类至少两条概念）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PSYCH_FILE = ROOT / "data" / "psych.jsonl"

SCENES = ["daily", "period", "conflict", "jealousy", "latenight",
          "meetup", "family", "distance", "friends", "anniversary"]
REQUIRED = ["id", "concept", "source", "scenes", "when", "say", "do", "dont", "tags"]
ID_RE = re.compile(r"^ps-\d{3}$")

# 诊断式表述：概念可以讲，但不能拿来给人下结论
BANNED = ["你就是", "型人格", "确诊", "诊断", "治愈", "病人", "有病", "心理疾病"]
# 稀缺证据：source 里不能只写「网上看到的」
VAGUE_SOURCES = ["网上", "听说", "网友", "经验之谈"]


def err(msg: str) -> None:
    print(f"  x {msg}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not PSYCH_FILE.exists():
        sys.exit(f"找不到 {PSYCH_FILE}")
    items = []
    errors = 0
    seen = {}
    covered = {s: 0 for s in SCENES}
    concepts = set()

    with PSYCH_FILE.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                err(f"{lineno}: JSON 解析失败 {exc}")
                errors += 1
                continue
            where = f"{item.get('id', lineno)}"
            missing = [k for k in REQUIRED if k not in item]
            if missing:
                err(f"{where}: 缺字段 {', '.join(missing)}")
                errors += 1
                continue
            if not ID_RE.match(str(item["id"])):
                err(f"{where}: id 要像 ps-001")
                errors += 1
            if item["id"] in seen:
                err(f"{where}: id 重复")
                errors += 1
            seen[item["id"]] = True
            if item["concept"] in concepts:
                err(f"{where}: 概念名重复 {item['concept']}")
                errors += 1
            concepts.add(item["concept"])

            for key, lo, hi in (("when", 8, 100), ("say", 8, 80), ("do", 8, 100), ("dont", 6, 100)):
                text = str(item[key])
                if not lo <= len(text) <= hi:
                    err(f"{where}: {key} 长度 {len(text)}，要 {lo} 到 {hi} 字")
                    errors += 1
                for word in BANNED:
                    if word in text:
                        err(f"{where}: {key} 出现诊断式表述 {word!r}")
                        errors += 1

            if not str(item["source"]).strip():
                err(f"{where}: source 不能为空，要写到具体文献")
                errors += 1
            for vague in VAGUE_SOURCES:
                if vague in str(item["source"]):
                    err(f"{where}: source 太含糊 {vague!r}，写具体文献")
                    errors += 1

            scenes = item["scenes"]
            if not isinstance(scenes, list) or not 1 <= len(scenes) <= 4:
                err(f"{where}: scenes 要是 1 到 4 个场景")
                errors += 1
            else:
                for s in scenes:
                    if s not in SCENES:
                        err(f"{where}: 场景不在枚举里 {s!r}")
                        errors += 1
                    else:
                        covered[s] += 1

            tags = item["tags"]
            if not isinstance(tags, list) or not 1 <= len(tags) <= 4:
                err(f"{where}: tags 要 1 到 4 个")
                errors += 1

    for scene in SCENES:
        if covered[scene] < 2:
            err(f"场景 {scene} 只有 {covered[scene]} 条概念，至少要 2 条")
            errors += 1

    if errors:
        print(f"\n共 {len(items) if items else 0} 条概念，{errors} 条错误。")
        sys.exit(1)
    print(f"\n通过: {len(seen)} 条概念，10 类场景都有覆盖。")


if __name__ == "__main__":
    main()