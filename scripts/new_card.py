#!/usr/bin/env python3
"""加一张情境卡。

为什么要有这个：手写 JSONL 容易漏字段、拼错枚举、id 撞车，
改完还得再跑一遍 lint 才知道错在哪。这个脚本一次把该问的问完，
写完立刻用 lint_data 的同一套规则验一遍，过不了就把文件恢复原样。

用法:
    # 一条命令直接加（适合熟练之后）
    python scripts/new_card.py --scene period \
        --title "说肚子疼得厉害" \
        --signal "晚上八点她说「疼得厉害了，坐着都难受」" \
        --goal "认真接住疼，落到一个具体动作" \
        --stage 聊得来,暧昧 \
        --moves 共情,认真回应 \
        --example "共情=这句听着就知道不是一般的疼" \
        --example "推进=我给你点份热的汤，二十分钟到楼下" \
        --taboo "忍一忍就过去了" --taboo "是不是吃坏东西了" \
        --followup "她没回先不追，一小时后发一句「汤放门口了」"

    # 先看看会生成什么，不写文件
    python scripts/new_card.py --scene period ... --dry-run

    # 不想背参数：一步步问
    python scripts/new_card.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lint_data import MOVES, SCENES, STYLES, check_card  # noqa: E402

SCENE_DIR = ROOT / "data" / "scenes"


def next_id(scene: str) -> str:
    path = SCENE_DIR / f"{scene}.jsonl"
    used = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                used.add(json.loads(line).get("id"))
            except json.JSONDecodeError:
                pass
    n = 1
    while f"{scene}-{n:03d}" in used:
        n += 1
    return f"{scene}-{n:03d}"


def split_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in re.split(r"[,，]", value) if part.strip()]


def parse_examples(values: list[str]) -> list[dict]:
    out = []
    for raw in values:
        if "=" not in raw:
            sys.exit(f"--example 要写成 风格=句子，收到的是: {raw}")
        style, text = raw.split("=", 1)
        style, text = style.strip(), text.strip()
        if style not in STYLES:
            sys.exit(f"风格 {style!r} 不在枚举里，可选: {' / '.join(sorted(STYLES))}")
        out.append({"style": style, "text": text})
    return out


def ask(prompt: str, default: str = "") -> str:
    suffix = f"（{default}）" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def build(args: argparse.Namespace) -> dict:
    scene = args.scene or ask(f"场景（{'/'.join(sorted(SCENES))}）").strip()
    if scene not in SCENES:
        sys.exit(f"场景 {scene!r} 不在枚举里，可选: {' / '.join(sorted(SCENES))}")

    title = args.title or ask("标题（4 到 20 字，写现场不写下结论）")
    signal = args.signal or ask("现场信号（她说了什么、什么时候、有没有补一句）")
    goal = args.goal or ask("这一步只想做到什么（一句话）")

    stage = split_list(args.stage) or split_list(ask("适用阶段（初识,聊得来,暧昧,已在恋爱）"))
    moves = split_list(args.moves) or split_list(ask("这次的动作（共情,认真回应,推进,退让…）"))
    bad_moves = [m for m in moves if m not in MOVES]
    if bad_moves:
        sys.exit(f"动作 {bad_moves} 不在枚举里，可选: {' / '.join(sorted(MOVES))}")

    examples = parse_examples(args.example)
    if not examples:
        print("至少给两种写法，输入空行结束：")
        while True:
            style = ask(f"  风格（{'/'.join(sorted(STYLES))}）")
            if not style:
                break
            text = ask("  这句话")
            if not text:
                break
            if style not in STYLES:
                print(f"  风格不在枚举里，跳过 {style!r}")
                continue
            examples.append({"style": style, "text": text})

    taboo = args.taboo or []
    if not taboo:
        taboo = split_list(ask("禁忌（她听了会关门的说法，逗号分隔，2 到 3 条）"))

    followup = args.followup or ask("续法（她没回、或者只回一个表情，你怎么办）")
    tags = split_list(args.tags) or split_list(ask("标签（2 到 5 个，方便以后检索）"))
    difficulty_raw = args.difficulty or ask("难度（1 平常 / 2 要小心 / 3 容易出事）", "2")
    try:
        difficulty = int(difficulty_raw)
    except ValueError:
        difficulty = 2

    return {
        "id": args.id or next_id(scene),
        "scene": scene,
        "title": title,
        "signal": signal,
        "stage": stage,
        "goal": goal,
        "moves": moves,
        "examples": examples,
        "taboo": taboo,
        "followup": followup,
        "tags": tags,
        "difficulty": difficulty,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="给 crush-reply 加一张情境卡")
    ap.add_argument("--scene")
    ap.add_argument("--title")
    ap.add_argument("--signal")
    ap.add_argument("--goal")
    ap.add_argument("--stage", help="逗号分隔")
    ap.add_argument("--moves", help="逗号分隔")
    ap.add_argument("--example", action="append", default=[], help="风格=句子，可重复")
    ap.add_argument("--taboo", action="append", default=[], help="可重复")
    ap.add_argument("--followup")
    ap.add_argument("--tags", help="逗号分隔")
    ap.add_argument("--difficulty")
    ap.add_argument("--id", help="一般不用给，自动取下一个")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    card = build(args)

    errors: list[str] = []
    warns: list[str] = []
    check_card(card, card["id"], errors, warns)
    for w in warns:
        print(f"  ! {w}")

    line = json.dumps(card, ensure_ascii=False)
    if errors:
        print(f"\n先别写文件，有 {len(errors)} 处不合规：")
        for e in errors:
            print(f"  x {e}")
        print("\n改完再跑一次。完整字段说明见 data/schema.md。")
        sys.exit(1)

    if args.dry_run:
        print("\n会往 data/scenes/" + card["scene"] + ".jsonl 追加这一行：\n")
        print(line)
        return

    path = SCENE_DIR / f"{card['scene']}.jsonl"
    original = path.read_text(encoding="utf-8") if path.exists() else ""
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")

    proc = __import__("subprocess").run(
        [sys.executable, str(ROOT / "scripts" / "lint_data.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT),
    )
    if proc.returncode != 0:
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(original)
        print("\n写进去之后整体 lint 没过，已回滚。下面是报错：")
        print((proc.stdout or "") + (proc.stderr or ""))
        sys.exit(1)

    print(f"\n已追加到 {path.relative_to(ROOT)}：{card['id']}")
    print("整库 lint 通过。想让它被检索到，不需要别的操作。")


if __name__ == "__main__":
    main()