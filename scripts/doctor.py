#!/usr/bin/env python3
"""crush-reply 自检。

装完先跑这个。它会告诉你四件事：
1. 这个目录是不是一个能被 Claude Code / Codex / DSH 读到的 skill
2. 数据文件在不在、能不能解析
3. 三个 lint 和一条检索冒烟能不能过
4. 过不了的时候，最可能是哪一个问题

用法:
    python scripts/doctor.py
    python scripts/doctor.py --quiet   # 只报结论，不逐条打勾
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

REQUIRED = [
    "SKILL.md",
    "data/schema.md",
    "data/memes.jsonl",
    "data/openers.jsonl",
    "data/psych.jsonl",
    "data/stickers.json",
    "scripts/query.py",
    "scripts/thread.py",
    "scripts/find.py",
    "scripts/voice.py",
    "scripts/psych.py",
]
SCENE_FILES = ["daily", "period", "conflict", "jealousy", "latenight",
               "meetup", "family", "distance", "friends", "anniversary"]
THREAD_SCENES = SCENE_FILES

# 常见安装位置，用来判断「装没装对地方」
SKILL_HOMES = [
    ("~/.claude/skills", "Claude Code"),
    ("~/.codex/skills", "Codex CLI"),
    ("~/.dsh/skills", "DeepSeek Harness"),
    ("~/.cursor/skills", "Cursor"),
]

ok_count = 0
bad_count = 0
problems: list[str] = []


def ok(msg: str, quiet: bool) -> None:
    global ok_count
    ok_count += 1
    if not quiet:
        print(f"  ok  {msg}")


def bad(msg: str, fix: str, quiet: bool) -> None:
    global bad_count
    bad_count += 1
    problems.append(f"{msg} -> {fix}")
    print(f"  xx  {msg}")
    if not quiet:
        print(f"      {fix}")


def run(script: str, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        [PY, str(ROOT / script), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(ROOT),
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="crush-reply 自检")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    quiet = args.quiet

    print(f"crush-reply doctor · {ROOT}")
    print(f"python {sys.version.split()[0]}  ({PY})\n")

    # 1. 是不是一个 skill 目录
    print("一、这个目录能不能被客户端读到")
    skill = ROOT / "SKILL.md"
    if not skill.exists():
        bad("缺 SKILL.md", "你大概在仓库子目录里，回到仓库根目录再跑", quiet)
    else:
        text = skill.read_text(encoding="utf-8")
        name = ""
        if text.startswith("---"):
            for line in text.splitlines()[1:]:
                if line.strip() == "---":
                    break
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
        if name != ROOT.name:
            bad(f"SKILL.md 里的 name 是 {name!r}，目录名是 {ROOT.name!r}",
                "两边必须一模一样，否则客户端不会加载；改 frontmatter 或重命名目录", quiet)
        else:
            ok(f"frontmatter name = {name}", quiet)

    resolved = ROOT.as_posix()
    hit = None
    for home, client in SKILL_HOMES:
        base = Path(home).expanduser()
        if str(base.resolve()) in resolved:
            hit = client
            break
    if hit:
        ok(f"装在 {hit} 的 skills 目录下", quiet)
    else:
        ok("目录不在任何内置 skills 路径下（也能用，但要按 README 的安装方式放）", quiet)

    # 2. 文件在不在
    print("\n二、数据文件")
    missing = [p for p in REQUIRED if not (ROOT / p).exists()]
    if missing:
        bad(f"缺 {len(missing)} 个文件: {', '.join(missing)}", "重新解压一份完整仓库，别只拷 data 或 scripts 的一部分", quiet)
    else:
        ok(f"{len(REQUIRED)} 个必需文件都在", quiet)

    for scene in SCENE_FILES:
        p = ROOT / "data" / "scenes" / f"{scene}.jsonl"
        if not p.exists():
            bad(f"缺场景文件 {p.name}", f"补 data/scenes/{scene}.jsonl，或删掉 scenes 里这个键", quiet)
        elif not any(l.strip() for l in p.read_text(encoding="utf-8").splitlines()):
            bad(f"{p.name} 是空的", "至少留一张卡；只想测格式可以只留一行", quiet)
    for scene in THREAD_SCENES:
        p = ROOT / "data" / "threads" / f"{scene}.jsonl"
        if not p.exists():
            bad(f"缺多轮链文件 {p.name}", f"补 data/threads/{scene}.jsonl", quiet)
    if not any(p for p in [ROOT / "data" / "threads"] if p.exists()):
        bad("data/threads 不存在", "多轮链是独立目录，漏拷了", quiet)

    # 3. 编码
    print("\n三、编码")
    bad_enc = []
    for path in list(ROOT.glob("data/**/*.jsonl")) + list(ROOT.glob("data/*.json")) + [ROOT / "SKILL.md"]:
        if not path.exists():
            continue
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            bad_enc.append(f"{path.relative_to(ROOT)} 带 BOM")
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            bad_enc.append(f"{path.relative_to(ROOT)} 不是 UTF-8（可能是 GBK）")
    if bad_enc:
        for item in bad_enc[:5]:
            bad(item, "用 VS Code 另存为 UTF-8（无 BOM）", quiet)
    else:
        ok("数据文件都是 UTF-8 无 BOM", quiet)

    # 4. 跑 lint 与冒烟
    print("\n四、校验与检索")
    lint_checks = [
        ("scripts/lint_data.py", "卡片"),
        ("scripts/lint_extra.py", "多轮链与开场白"),
        ("scripts/lint_psych.py", "心理学概念"),
    ]
    for script, label in lint_checks:
        if not (ROOT / script).exists():
            bad(f"缺 {script}", "重新解压完整仓库", quiet)
            continue
        code, out = run(script)
        if code == 0:
            ok(f"{label} lint 通过", quiet)
        else:
            tail = "\n".join(out.strip().splitlines()[-6:])
            bad(f"{label} lint 没过", f"逐条改完再跑一次：{script}\n{tail}", quiet)

    code, out = run("scripts/query.py", "--scene", "period", "--top", "1", "疼得厉害了，坐着都难受")
    if code == 0 and "period-" in out:
        ok("检索冒烟通过（period 能命中）", quiet)
    else:
        bad("检索冒烟失败：query.py 跑不出结果", "确认在仓库根目录跑，并检查 scripts/query.py 是否被改动", quiet)

    # 5. 结论
    print("\n" + "-" * 46)
    if bad_count == 0:
        print(f"全部通过（{ok_count} 项）。可以开始用了：")
        print('  python scripts/query.py "她说来例假了疼得厉害" --scene period')
        if not quiet:
            print("\n想看对比演示：python demo.py \"她说来例假了疼得厉害\" --scene period")
        return

    print(f"{bad_count} 个问题，{ok_count} 项正常。按下面的提示改：")
    for i, item in enumerate(problems, 1):
        print(f"  {i}. {item}")
    print("\n最常见的四个原因，先对一下：")
    print("  1. frontmatter 的 name 和目录名不一致 —— 客户端只认目录名")
    print("  2. 放错位置 —— Claude Code 要 ~/.claude/skills/crush-reply，Codex 要 ~/.codex/skills/")
    print("  3. 数据只拷了一部分 —— data/scenes 要 10 个文件，data/threads 要 10 个文件")
    print("  4. 文件被编辑器存成了 GBK —— 重存为 UTF-8 无 BOM")
    sys.exit(1)


if __name__ == "__main__":
    main()