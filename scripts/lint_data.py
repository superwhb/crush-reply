#!/usr/bin/env python3
"""crush-reply 数据质检。

在仓库根目录跑:
    python scripts/lint_data.py            检查全部
    python scripts/lint_data.py --stats    看数据分布
    python scripts/lint_data.py data/scenes/period.jsonl   只查一个文件

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
SCENE_DIR = ROOT / "data" / "scenes"

SCENES = {"daily", "period", "conflict", "jealousy", "latenight", "meetup",
          "family", "distance", "friends", "anniversary"}
STAGES = {"初识", "聊得来", "暧昧", "已在恋爱"}
MOVES = {"共情", "站队", "抛小问题", "自嘲", "玩梗", "认真回应", "转移话题", "给出口", "推进", "退让"}
STYLES = {"共情", "玩梗", "认真", "自嘲", "反向好奇", "推进", "退让"}
REQUIRED = ["id", "scene", "title", "signal", "stage", "goal", "moves",
            "examples", "taboo", "followup", "tags", "difficulty"]

ID_RE = re.compile(r"^(daily|period|conflict|jealousy|latenight|meetup|family|distance|friends|anniversary)-\d{3}$")

# 出现在示例话术里的红线词
BANNED = [
    "打压", "冷暴力", "欲擒故纵", "假装忙", "装忙", "多喝热水", "忍一忍",
    "矫情", "想太多", "早点睡就好了", "未成年", "开房", "那就分手",
]
# 不合适的称呼
BANNED_CALLS = ["宝", "小仙女", "亲爱的", "臭宝", "老婆"]
# 独立哈哈哈不算回复
LAZY = re.compile(r"^(哈{2,}|h{3,}|草)$", re.I)


def is_ascii(text: str) -> bool:
    return all(ord(c) < 128 for c in text)


def check_card(card: dict, where: str, errors: list[str], warns: list[str]) -> None:
    def err(msg: str) -> None:
        errors.append(f"{where}: {msg}")

    missing = [k for k in REQUIRED if k not in card]
    if missing:
        err(f"缺字段 {', '.join(missing)}")
        return

    if not ID_RE.match(card["id"]):
        err(f"id 不合规 {card['id']!r}，要像 daily-001")
    if card["scene"] not in SCENES:
        err(f"scene 不在枚举里 {card['scene']!r}")
    elif where.startswith("data/scenes/") and card["id"].split("-")[0] != card["scene"]:
        err(f"id 前缀和 scene 不一致 {card['id']} / {card['scene']}")

    title = str(card["title"])
    if not 4 <= len(title) <= 20:
        err(f"title 长度 {len(title)}，要 4 到 20 字")

    signal = str(card["signal"])
    if len(signal) < 8:
        err(f"signal 太短 {len(signal)} 字，要写得像真实现场")
    if "\n" in signal:
        err("signal 不能有换行")

    if not isinstance(card["stage"], list) or not card["stage"]:
        err("stage 要是非空数组")
    else:
        bad = [s for s in card["stage"] if s not in STAGES]
        if bad:
            err(f"stage 不在枚举里 {bad}")
        if len(set(card["stage"])) != len(card["stage"]):
            err("stage 有重复")

    if not str(card["goal"]).strip():
        err("goal 不能为空")

    moves = card["moves"]
    if not isinstance(moves, list) or not 2 <= len(moves) <= 4:
        err("moves 要 2 到 4 个")
    else:
        bad = [m for m in moves if m not in MOVES]
        if bad:
            err(f"moves 不在枚举里 {bad}")

    examples = card["examples"]
    if not isinstance(examples, list) or not 2 <= len(examples) <= 3:
        err("examples 要 2 到 3 条")
    else:
        for i, ex in enumerate(examples):
            if not isinstance(ex, dict) or "style" not in ex or "text" not in ex:
                err(f"examples[{i}] 要是 {{style, text}}")
                continue
            if ex["style"] not in STYLES:
                err(f"examples[{i}].style 不在枚举里 {ex['style']!r}")
            text = str(ex["text"])
            if "\n" in text:
                err(f"examples[{i}] 有换行")
            if not 4 <= len(text) <= 60:
                err(f"examples[{i}] 长度 {len(text)}，要 4 到 60 字")
            elif len(text) > 45:
                warns.append(f"{where}: examples[{i}] 偏长 {len(text)} 字，建议 40 字内")
            for word in BANNED:
                if word in text:
                    err(f"examples[{i}] 命中红线词 {word!r}")
            for call in BANNED_CALLS:
                if call in text:
                    err(f"examples[{i}] 用了称呼 {call!r}，改成 {{称呼}}")
            if LAZY.match(text.strip()):
                err(f"examples[{i}] 是单独哈哈哈，别当示例")

    taboo = card["taboo"]
    if not isinstance(taboo, list) or not 2 <= len(taboo) <= 3:
        err("taboo 要 2 到 3 条")

    followup = str(card["followup"])
    if len(followup) < 6:
        err("followup 太短，要写到具体怎么做")

    tags = card["tags"]
    if not isinstance(tags, list) or not 2 <= len(tags) <= 5:
        err("tags 要 2 到 5 个")
    elif any(len(str(t)) < 2 for t in tags):
        err("tags 里不要放单字")

    difficulty = card["difficulty"]
    if not isinstance(difficulty, int) or difficulty not in (1, 2, 3):
        err("difficulty 只能是 1/2/3")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", help="只查指定 jsonl")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    if args.files:
        paths = [Path(f) for f in args.files]
    else:
        paths = sorted(SCENE_DIR.glob("*.jsonl"))

    if not paths:
        sys.exit(f"没找到数据文件: {SCENE_DIR}")

    errors: list[str] = []
    warns: list[str] = []
    cards: list[dict] = []
    seen_ids: dict[str, str] = {}
    seen_text: Counter = Counter()

    for path in paths:
        rel = path.as_posix().split("crush-reply/")[-1]
        with path.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                where = f"{rel}:{lineno}"
                try:
                    card = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"{where}: JSON 解析失败 {exc}")
                    continue
                if not isinstance(card, dict):
                    errors.append(f"{where}: 每行必须是一个对象")
                    continue
                check_card(card, where, errors, warns)
                cid = str(card.get("id"))
                if cid in seen_ids:
                    errors.append(f"{where}: id 重复 {cid}，第一次出现在 {seen_ids[cid]}")
                else:
                    seen_ids[cid] = where
                for ex in card.get("examples", []):
                    seen_text[str(ex.get("text", ""))] += 1
                cards.append(card)

    for text, count in seen_text.items():
        if count > 1 and text:
            warns.append(f"示例话术重复 {count} 次: {text}")

    if args.stats:
        print(f"卡片总数: {len(cards)}")
        print("按场景:", dict(Counter(c.get("scene") for c in cards)))
        print("按难度:", dict(sorted(Counter(c.get("difficulty") for c in cards).items())))
        print("按阶段:", dict(Counter(s for c in cards for s in c.get("stage", []))))
        print("按风格:", dict(Counter(e.get("style") for c in cards for e in c.get("examples", []))))

    if warns:
        print(f"\n警告 {len(warns)} 条:")
        for w in warns:
            print(f"  ! {w}")

    if errors:
        print(f"\n错误 {len(errors)} 条:")
        for e in errors:
            print(f"  x {e}")
        print(f"\n共 {len(cards)} 张卡，{len(errors)} 条错误。")
        sys.exit(1)

    print(f"\n通过: {len(cards)} 张卡，{len(seen_ids)} 个 id，无错误。")


if __name__ == "__main__":
    main()