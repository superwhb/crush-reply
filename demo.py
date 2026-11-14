#!/usr/bin/env python3
"""一条命令把材料拼成「可以直接贴给模型」的提示包。

这个脚本不调用任何模型，它只做三件事：读画像、检索、按固定格式排版。
你把输出整段贴给 ChatGPT / Claude / DeepSeek，模型就能按卡片方向写出回复。

用法:
    python demo.py "她说明天来例假，肚子疼得起不来"
    python demo.py "她说还是做朋友吧" --profile 小鹿
    python demo.py --openers --profile 小鹿          # 只想要开场话题
    python demo.py "她已读不回三天了" --json          # 给别的程序接
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

from query import bm25, load_cards, scene_boost, tokenize  # noqa: E402
from thread import index_text as thread_text, load_threads  # noqa: E402

PROFILE_DIR = ROOT / "profiles"
VOICE_DIR = ROOT / "voices"
OPENERS = ROOT / "data" / "openers.jsonl"

VOICE_RULE = "每一句都按「我的说话习惯」写：句长、标点、表情、连发几条、常用词。他不会用的词一个都别用。"

OPENING_RULES = f"""输出要求（照这个格式，别写别的）：
【挑哪一条】从上面三条里选一条最适合现在用的，说清为什么这条而不是那两条。
【可以这样发】把选中的那条改成符合我说话习惯的一句，能直接发出去。
【别再补一句】哪些追加的话会让它变刻意，写具体的句子。
【她这样回，你就】她接得住和接不住两种反应，各一句怎么往下走。
{VOICE_RULE}"""

OUTPUT_RULES = f"""输出要求（照这个格式，别写别的）：
【判断】一两句说清她这条在要什么。
【可以这样回】三条，按轻重排，每条不超过四十个字，都要能直接发出去。
【别这样回】两条，写具体的错句，不是抽象原则。
【她要是只回一个表情，你就】一句具体的续法。
【第二三轮注意】这条链最容易崩在哪一轮，以及撑不住时怎么收。
{VOICE_RULE}"""


def read_profile(name: str | None) -> str:
    if not name:
        return "（没有提供画像。缺了这层，回复会偏通用，建议先跑 python scripts/profile.py new 代号）"
    path = PROFILE_DIR / f"{name}.md"
    if not path.exists():
        return f"（没找到 profiles/{name}.md，先跑 python scripts/profile.py new {name}）"
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("<") or line.startswith(">"):
            continue
        if ":" not in line and "：" not in line:
            continue
        key, _, value = line.replace("：", ":", 1).partition(":")
        value = value.strip()
        if not value:
            continue
        lines.append(f"{key.strip()}: {value}")
    return "\n".join(lines) if lines else "（画像是空的，先把知道的填上）"


def read_voice(name: str | None) -> str:
    """读说话风格档案：去掉 HTML 注释和标题外的空行，保留样本和口径。"""
    if not name:
        return ""
    path = VOICE_DIR / f"{name}.md"
    if not path.exists():
        return ""
    lines: list[str] = []
    in_comment = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("<!--"):
            in_comment = not stripped.endswith("-->")
            continue
        if in_comment:
            in_comment = not stripped.endswith("-->")
            continue
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def card_scores(query: str, scene: str | None) -> list[tuple[float, dict]]:
    cards = load_cards()
    pool = [c for c in cards if not scene or c["scene"] == scene]
    if not pool:
        return []
    from collections import Counter

    tfs, df = [], Counter()
    for card in pool:
        tf = Counter(tokenize(
            str(card.get("title", "")) * 3 + " " + " ".join(card.get("tags", [])) * 3 + " "
            + str(card.get("signal", "")) * 2 + " " + " ".join(e.get("text", "") for e in card.get("examples", []))
        ))
        tfs.append(tf)
        for token in tf:
            df[token] += 1
    lens = [sum(tf.values()) for tf in tfs]
    avgdl = sum(lens) / len(lens) if lens else 1.0
    qtokens = tokenize(query)
    scored = [(bm25(qtokens, tf, df, avgdl, len(pool)) + scene_boost(query, c), c) for tf, c in zip(tfs, pool)]
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [(s, c) for s, c in scored if s > 0]


def search_cards(query: str, top: int, scene: str | None) -> list[dict]:
    return [c for _, c in card_scores(query, scene)[:top]]


def search_threads(query: str, top: int) -> list[dict]:
    threads = load_threads()
    from collections import Counter

    tfs, df = [], Counter()
    for thread in threads:
        tf = Counter(tokenize(thread_text(thread)))
        tfs.append(tf)
        for token in tf:
            df[token] += 1
    lens = [sum(tf.values()) for tf in tfs]
    avgdl = sum(lens) / len(lens) if lens else 1.0
    qtokens = tokenize(query)
    scored = [(bm25(qtokens, tf, df, avgdl, len(threads)) + scene_boost(query, t), t) for tf, t in zip(tfs, threads)]
    scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [t for s, t in scored if s > 0][:top]


def pick_openers(profile: str, n: int) -> list[dict]:
    if not OPENERS.exists():
        return []
    rows = [json.loads(line) for line in OPENERS.read_text(encoding="utf-8").splitlines() if line.strip()]
    # 画像里有「近期事件」就优先挑她提过的事
    has_event = "近期事件" in profile and "：" in profile.split("近期事件", 1)[1][:2]
    rows.sort(key=lambda o: (o.get("anchor") != "她提过的事", o.get("difficulty", 1), o["id"]))
    return rows[:n] if has_event else rows[:n]


def wants_openers(query: str, flag: bool) -> bool:
    """问「聊什么」的时候自动附上开场话题，不用记参数。"""
    if flag or not query:
        return True
    return any(word in query for word in ("话题", "开口", "说什么", "没话说", "怎么聊", "找点事"))


WEAK_SCORE = 6.0

FALLBACK_HINT = """## 库里没有这种情况
先别硬凑。跑：
    python scripts/find.py "她的原话"
拿到检索词，联网搜两到三篇（小红书的对话截图最有参考价值），只提炼情境结构，不抄句子。
然后按下面这个格式回答，并且说清这是外部参考、库里没有同类卡。"""


def render_pack(query: str, profile_name: str | None, scene: str | None,
                with_openers: bool, voice_name: str | None = None) -> str:
    profile = read_profile(profile_name)
    voice = read_voice(voice_name or profile_name)
    scored = card_scores(query, scene) if query else []
    cards = [card for _, card in scored[:3]]
    threads = search_threads(query, 2) if query else []
    openers = pick_openers(profile, 3) if wants_openers(query, with_openers) else []

    opening_only = not query
    out = ["我想找个话题开口，材料如下。" if opening_only else "我要回一条消息，材料如下。", ""]
    out += ["## 对方画像", profile, ""]

    if voice:
        out += ["## 我的说话习惯（必须模仿，不是参考）", voice, ""]
    else:
        out += ["## 我的说话习惯",
                "（还没建 voices/ 档案。先按普通口语写，并在回答最后一行提醒我贴三条自己发过的消息。）", ""]

    if query:
        out += ["## 现在的现场", f"她说的 / 当前情况：{query}", ""]
    if cards:
        out += ["## 检索到的情境卡（给方向，不要照抄）"]
        for card in cards:
            out.append(f"- {card['id']} {card['title']}｜目标：{card['goal']}｜手法：{'/'.join(card['moves'])}")
            for ex in card["examples"]:
                out.append(f"    · {ex['style']}口径：{ex['text']}")
            out.append(f"    · 别说：{'；'.join(card['taboo'])}")
            out.append(f"    · 续法：{card['followup']}")
        out.append("")
        if scored and scored[0][0] < WEAK_SCORE:
            out += [f"> 提醒：这几张只是词对上了（最高分 {scored[0][0]:.1f}），情境不一定真对。"
                    "如果读完觉得不对路，先跑 scripts/find.py 去外面找，别硬套。", ""]
    elif query:
        out += [FALLBACK_HINT, ""]
    if threads:
        out += ["## 可能走向的多轮链（看节奏，别照念）"]
        for thread in threads:
            out.append(f"- {thread['id']} {thread['title']}｜前提：{thread['premise']}")
            for i, turn in enumerate(thread["turns"], 1):
                out.append(f"    {i}. 她：{turn['her']}")
                out.append(f"       你：{turn['you']}（{turn['why']}）")
            out.append(f"    收尾：{thread['exit']}")
        out.append("")
    if openers:
        out += ["## 开场话题候选（没由头时用）"]
        for o in openers:
            out.append(f"- {o['example']}（{o['anchor']}，她接得住因为：{o['why']}）")
        out.append("")

    out += [OPENING_RULES if opening_only else OUTPUT_RULES]
    return "\n".join(out)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="把画像、说话习惯、卡片、多轮链拼成提示包")
    parser.add_argument("query", nargs="*", help="她说了什么，或者你想找什么话题")
    parser.add_argument("--profile", help="profiles/ 下的画像代号，比如 小鹿")
    parser.add_argument("--voice", help="voices/ 下的风格代号，默认跟画像同名")
    parser.add_argument("--scene", help="限定场景")
    parser.add_argument("--openers", action="store_true", help="附上开场话题候选")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    query = " ".join(args.query).strip()
    if args.json:
        pack = {
            "query": query,
            "profile": read_profile(args.profile),
            "voice": read_voice(args.voice or args.profile),
            "cards": search_cards(query, 3, args.scene) if query else [],
            "threads": search_threads(query, 2) if query else [],
            "openers": pick_openers(read_profile(args.profile), 3) if wants_openers(query, args.openers) else [],
            "fallback": bool(query) and not search_cards(query, 3, args.scene),
        }
        print(json.dumps(pack, ensure_ascii=False, indent=2))
        return

    print(render_pack(query, args.profile, args.scene, args.openers, args.voice))


if __name__ == "__main__":
    main()