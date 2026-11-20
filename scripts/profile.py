#!/usr/bin/env python3
"""对方画像：读、写、校验。

数据放在 ~/.crush-reply/profiles/（可用 CRUSH_HOME 改），不放在技能包里，
这样升级、重装、git clean 都不会把你的数据一起删掉。老版本放在仓库里的
profiles/ 会在第一次运行时自动复制过去。

用法:
    python scripts/profile.py new 小鹿      # 按模板建一份
    python scripts/profile.py show 小鹿     # 打印成一段，直接贴给模型
    python scripts/profile.py check         # 校验全部画像
    python scripts/profile.py list

画像一行一个 `字段: 值`。不写不知道的字段，宁可空着，也不要猜。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import paths

FIELDS = [
    ("代号", True, "你怎么称呼她/他，不要写真名"),
    ("对方性别", False, "女 / 男，决定回复里的人称，不知道就按女写"),
    ("关系阶段", True, "初识 / 聊得来 / 暧昧 / 已在恋爱"),
    ("认识多久", False, "比如 三周、半年"),
    ("MBTI", False, "知道就写，不知道空着"),
    ("星座", False, ""),
    ("作息", False, "几点睡、几点在线、忙的时段"),
    ("饮食", False, "不吃什么、爱吃什么、忌口"),
    ("在意的事", False, "她现在最上心的东西"),
    ("雷区", False, "明确让她烦的表达方式"),
    ("近期事件", False, "考试、搬家、吵架、生病"),
    ("称呼习惯", False, "她怎么叫你，你怎么叫她"),
]

REQUIRED = [name for name, req, _ in FIELDS if req]
STAGES = {"初识", "聊得来", "暧昧", "已在恋爱"}
GENDERS = {"女", "男"}

LINE_RE = re.compile(r"^\s*([^:：]{1,10})[:：]\s*(.*)$")


def parse(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith(("#", "-", "|", ">")):
            continue
        match = LINE_RE.match(line)
        if match:
            key = match.group(1).strip()
            value = re.split(r"\s+#", match.group(2), maxsplit=1)[0].strip()
            if value.startswith("#"):
                value = ""
            data[key] = value
    return data


def template(alias: str) -> str:
    lines = [
        f"# 对方画像 · {alias}",
        "",
        "只写你知道的。不确定的字段留空，不要替对方编。",
        "这份文件只在本机，不会被上传，也不该写对方真名。",
        "",
        "<!-- 冒号后面直接写值，不要写 # 注释，注释会被当成内容读进去 -->",
        "",
    ]
    for name, req, _ in FIELDS:
        value = alias if name == "代号" else ""
        lines.append(f"{name}: {value}".rstrip())
    lines += [
        "",
        "<!-- 每个字段填什么：",
        "  对方性别  女 / 男，只影响回复里的人称，不影响别的判断",
        "  关系阶段  初识 / 聊得来 / 暧昧 / 已在恋爱，只能填这四个",
        "  作息      几点睡、几点在线、哪几天忙",
        "  饮食      不吃什么、爱吃什么、忌口，生理期那段最用得上",
        "  在意的事  她现在最上心的东西，话题从这儿长出来",
        "  雷区      明确让她烦的表达，比如「别催我回消息」",
        "  近期事件  考试、搬家、生病、和谁闹了别扭",
        "  称呼习惯  她怎么叫你，你怎么叫她，别在聊天里突然换称呼",
        "-->",
    ]
    return "\n".join(lines) + "\n"


def cmd_new(alias: str) -> None:
    folder = paths.profiles_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{alias}.md"
    if path.exists():
        sys.exit(f"{path.name} 已经存在，换一个代号，或者直接编辑它")
    path.write_text(template(alias), encoding="utf-8", newline="\n")
    print(f"已建好: {path}")
    print(f"填完跑 `python scripts/profile.py show {alias}` 看看读出来对不对")


def cmd_show(alias: str) -> None:
    path = paths.profiles_dir() / f"{alias}.md"
    if not path.exists():
        sys.exit(f"没有 {alias}.md，先 `python scripts/profile.py new {alias}`")
    data = parse(path)
    print(f"【{data.get('代号', alias)}】")
    for name, req, _ in FIELDS:
        if name == "代号":
            continue
        value = data.get(name, "").strip()
        if value:
            print(f"{name}: {value}")
    missing = [name for name in REQUIRED if not data.get(name, "").strip()]
    if missing:
        print(f"\n(还缺: {'、'.join(missing)})", file=sys.stderr)


def cmd_check() -> None:
    folder = paths.profiles_dir()
    if not folder.is_dir():
        print(f"还没有画像目录（{folder}），用到时会自动建。")
        return
    file_list = sorted(p for p in folder.glob("*.md") if not p.name.startswith("_"))
    if not file_list:
        print("没有画像文件")
        return
    bad = 0
    empty = 0
    for path in file_list:
        data = parse(path)
        # 分两种：值填错了算问题；字段还空着只算没填完，不算错误。
        problems = []
        stage = data.get("关系阶段", "").strip()
        if stage and stage not in STAGES:
            problems.append(f"关系阶段 {stage!r} 不在 {sorted(STAGES)} 里")
        gender = data.get("对方性别", "").strip()
        if gender and gender not in GENDERS:
            problems.append(f"对方性别 {gender!r} 只能是 女 或 男")
        missing = [name for name in REQUIRED if not data.get(name, "").strip()]
        if problems:
            bad += 1
            print(f"x {path.name}: {'；'.join(problems)}")
        elif missing:
            empty += 1
            print(f"- {path.name}: 还没填完（缺 {'、'.join(missing)}）")
        else:
            print(f"v {path.name}")
    done = len(file_list) - bad - empty
    print(f"\n{done}/{len(file_list)} 填完")
    if bad:
        sys.exit(1)
    if empty:
        print("还在模板状态的那份，填完再跑一次 check 就好。")


def cmd_list() -> None:
    folder = paths.profiles_dir()
    if not folder.is_dir():
        print(f"还没有画像（{folder}）")
        return
    for path in sorted(folder.glob("*.md")):
        if path.name.startswith("_"):
            continue
        data = parse(path)
        print(f"{path.stem:<10} {data.get('关系阶段', '-'):<6} {data.get('MBTI', '-'):<6} {data.get('星座', '-')}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="对方画像管理")
    parser.add_argument("action", choices=["new", "show", "check", "list"])
    parser.add_argument("alias", nargs="?", help="代号，new 和 show 需要")
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