#!/usr/bin/env python3
"""用户的说话风格档案：读、建、校验。

这不是给对方看的资料，是让回复别像 AI 写的那份样本。
里面只该出现「你自己真发过的字」，不写形容词评价（比如「我比较幽默」）。

数据放在 ~/.crush-reply/voices/（可用 CRUSH_HOME 改），不放在技能包里。
模板仍然读仓库里的 voices/_template.md。

用法:
    python scripts/voice.py new 小鹿      # 按模板建一份
    python scripts/voice.py show 小鹿     # 打印成一段，贴给模型
    python scripts/voice.py check         # 校验有没有填够
    python scripts/voice.py list
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import paths

TEMPLATE = ROOT / "voices" / "_template.md"
MIN_SAMPLES = 3


def cmd_new(alias: str) -> None:
    folder = paths.voices_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{alias}.md"
    if path.exists():
        sys.exit(f"{alias}.md 已经存在，直接编辑它")
    if TEMPLATE.exists():
        text = TEMPLATE.read_text(encoding="utf-8").replace("{代号}", alias)
    else:
        text = f"# 我的说话风格 · {alias}\n\n## 我平时怎么发消息\n\n```\n（贴 3-10 条你真发过的消息）\n```\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"已建好: {path}")
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
    path = paths.voices_dir() / f"{alias}.md"
    if not path.exists():
        sys.exit(f"没有 {alias}.md，先 `python scripts/voice.py new {alias}`")
    text = path.read_text(encoding="utf-8")
    body = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("<!--")]
    print("\n".join(body))


def cmd_check() -> None:
    folder = paths.voices_dir()
    if not folder.is_dir():
        print(f"还没有说话风格目录（{folder}），用到时会自动建。")
        return
    file_list = sorted(p for p in folder.glob("*.md") if not p.name.startswith("_"))
    if not file_list:
        print("还没有风格档案（只有模板）。想更像本人就先建一份。")
        return
    bad = 0
    for path in file_list:
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
    print(f"\n{len(file_list) - bad}/{len(file_list)} 通过")


def cmd_list() -> None:
    folder = paths.voices_dir()
    if not folder.is_dir():
        print(f"还没有说话风格档案（{folder}）")
        return
    for path in sorted(folder.glob("*.md")):
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

    paths.ensure()

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