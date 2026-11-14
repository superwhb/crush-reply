#!/usr/bin/env python3
"""校验 SKILL.md 的 frontmatter 是否符合 Agent Skills 规范。

    python scripts/lint_skill.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "SKILL.md"

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not SKILL.exists():
        sys.exit("找不到 SKILL.md")

    text = SKILL.read_text(encoding="utf-8")
    meta = parse_frontmatter(text)
    errors: list[str] = []

    if not meta:
        errors.append("SKILL.md 没有 --- 包起来的 frontmatter")

    name = meta.get("name", "")
    description = meta.get("description", "")

    if not name:
        errors.append("缺 name")
    else:
        if not NAME_RE.match(name):
            errors.append(f"name {name!r} 只能用小写字母、数字、连字符")
        if len(name) > 64:
            errors.append(f"name 长度 {len(name)}，上限 64")
        if name != ROOT.name:
            errors.append(f"name {name!r} 必须等于目录名 {ROOT.name!r}")

    if not description:
        errors.append("缺 description")
    else:
        if len(description) > 1024:
            errors.append(f"description 长度 {len(description)}，上限 1024")
        if len(description) < 40:
            errors.append("description 太短，要写清什么时候该用它")
        for bad in ("这个技能", "本技能", "you can use"):
            if bad in description:
                errors.append(f"description 里别写 {bad!r}，第三人称写触发场景")

    body = text.split("---", 2)[-1]
    if len(body.strip()) < 200:
        errors.append("SKILL.md 正文太短，没有可执行的工作流")

    existing = {p.name for p in ROOT.iterdir()}
    referenced = set(re.findall(r"`((?:data|scripts|profiles|voices|examples)/[\w./<>*-]+)`", body))
    for ref in sorted(referenced):
        head = re.split(r"[/*]", ref.split("/")[0] + "/" + (ref.split("/")[1] if "/" in ref else ""))
        first = ref.split("/")[0]
        if first not in existing:
            errors.append(f"正文引用了不存在的目录 {first}")

    if errors:
        print("SKILL.md 校验失败:")
        for err in errors:
            print(f"  x {err}")
        sys.exit(1)

    print(f"SKILL.md 通过: name={name}, description {len(description)} 字, 正文 {len(body)} 字")


if __name__ == "__main__":
    main()