#!/usr/bin/env python3
"""用户的说话风格档案：读、建、校验。

这不是给对方看的资料，是让回复别像 AI 写的那份样本。
里面只该出现「你自己真发过的字」，不写形容词评价（比如「我比较幽默」）。

用法:
    python scripts/voice.py new 小鹿      # 按模板建一份
    python scripts/voice.py show 小鹿     # 打印成一段，贴给模型
    python scripts/voice.py check         # 校验有没有填够
    python scripts/voice.py list
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICE_DIR = ROOT / "voices"
TEMPLATE = VOICE_DIR / "_template.md"
MIN_SAMPLES = 3


def cmd_new(alias: str) -> None:
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    path = VOICE_DIR / f"{alias}.md"
    if path.exists():
        sys.exit(f"voices/{alias}.md 已经存在，直接编辑它")
    if TEMPLATE.exists():
        text = TEMPLATE.read_text(encoding="utf-8").replace("{代号}", alias)
    else:
        text = f"# 我的说话风格 · {alias}\n\n## 我平时怎么发消息\n\n```\n（贴 3-10 条你真发过的消息）\n```\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"已建好: {path.relative_to(ROOT)}")
    print("贴 5 到 10 条你自己真发过的消息进去，越日常越好；别挑最好听的，挑最像你平时的。")


PLACEHOLDER = re.compile(r"^[（(].*(贴|在这里).*[）)]$")


def samples(text: str) -> list[str]:
    """取「我平时怎么发消息」下面代码块里的非空行。"""
    lines: list[str] = []
    inside = False
    in_fence = False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = "平时怎么发消息" in line
            in_fence = False
            continue
        if not inside:
            continue
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and line.strip() and not PLACEHOLDER.match(line.strip()):
            lines.append(line.strip())
    return lines


def cmd_show(alias: str) -> None:
    path = VOICE_DIR / f"{alias}.md"
    if not path.exists():
        sys.exit(f"没有 voices/{alias}.md，先 `python scripts/voice.py new {alias}`")
    text = path.read_text(encoding="utf-8")
    body = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("<!--")]
    print("\n".join(body))


def cmd_check() -> None:
    if not VOICE_DIR.is_dir():
        sys.exit("voices/ 目录不存在")
    paths = sorted(p for p in VOICE_DIR.glob("*.md") if not p.name.startswith("_"))
    if not paths:
        print("还没有风格档案（只有模板）。想更像本人就先建一份。")
        return
    bad = 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        got = samples(text)
        problems = []
        if len(got) < MIN_SAMPLES:
            problems.append(f"样例只有 {len(got)} 条，至少 {MIN_SAMPLES} 条才学得像")
        if any(len(s) > 80 for s in got):
            problems.append("有超过 80 字的样例，贴一小段就够，别放小作文")
        if problems:
            bad += 1
            print(f"x {path.name}: {'；'.join(problems)}")
        else:
            avg = sum(len(s) for s in got) / len(got)
            print(f"v {path.name}: {len(got)} 条样例，平均 {avg:.0f} 字")
    print(f"\n{len(paths) - bad}/{len(paths)} 通过")


def cmd_list() -> None:
    for path in sorted(VOICE_DIR.glob("*.md")):
        if path.name.startswith("_"):
            continue
        print(f"{path.stem:<10} {len(samples(path.read_text(encoding='utf-8')))} 条样例")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="说话风格档案")
    parser.add_argument("action", choices=["new", "show", "check", "list"])
    parser.add_argument("alias", nargs="?", help="代号")
    args = parser.parse_args()

    if args.action == "new":
        if not args.alias:
            parser.error("new 要带代号，比如 `new 小鹿`")
        cmd_new(args.alias)
    elif args.action == "show":
        if not args.alias:
            parser.error("show 要带代号")
        cmd_show(args.alias)
    elif args.action == "check":
        cmd_check()
    else:
        cmd_list()


if __name__ == "__main__":
    main()