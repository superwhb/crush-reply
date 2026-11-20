#!/usr/bin/env python3
"""数据目录：画像、说话风格、结果记录，不放在技能包里面。

默认 ~/.crush-reply，可以用环境变量 CRUSH_HOME 指定到别处。
老版本把 profiles/ 和 voices/ 放在仓库根目录，第一次运行时自动复制过来，原文件不删。
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def data_home() -> Path:
    raw = os.environ.get("CRUSH_HOME", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".crush-reply"


def profiles_dir() -> Path:
    return data_home() / "profiles"


def voices_dir() -> Path:
    return data_home() / "voices"


def outcomes_file() -> Path:
    return data_home() / "outcomes.jsonl"


def gaps_dir() -> Path:
    return data_home() / "gaps"


def _migrate(src: Path, dst: Path) -> list[str]:
    moved: list[str] = []
    if not src.is_dir():
        return moved
    copies = [p for p in sorted(src.glob("*.md")) if not p.name.startswith("_")]
    if not copies:
        return moved
    dst.mkdir(parents=True, exist_ok=True)
    for path in copies:
        target = dst / path.name
        if target.exists():
            continue
        shutil.copy2(path, target)
        moved.append(path.name)
    return moved


def ensure() -> Path:
    """建目录，并把仓库里的旧数据搬进来。CLI 入口调用一次就够了。"""
    home = data_home()
    home.mkdir(parents=True, exist_ok=True)
    for folder in (profiles_dir(), voices_dir(), gaps_dir()):
        folder.mkdir(parents=True, exist_ok=True)
    moved = _migrate(ROOT / "profiles", profiles_dir()) + _migrate(ROOT / "voices", voices_dir())
    if moved:
        print(
            f"已把 {len(moved)} 份旧数据复制到 {home}（仓库里原来的文件没删，确认没问题后可以自己删掉）",
            file=sys.stderr,
        )
    return home