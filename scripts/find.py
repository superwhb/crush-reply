#!/usr/bin/env python3
"""库里没有这种情况时，把「该搜什么」算出来。

`query.py` 找到的卡片都不对路时用它：它不联网，只做三件事——
猜场景、把这个人自己的话变成几条能直接丢进搜索框的检索词、给一段提炼模板。
搜完之后按 research/README.md 的口径提炼，再按说话风格档案（~/.crush-reply/voices/）的句式写回复。

用法:
    python scripts/find.py "她说她最近有点累，但又不说具体怎么了"
    python scripts/find.py "她把我送的礼物退回来了" --json
    python scripts/find.py "她家让我过年去吃饭，我有点慌" --note   # 顺手记一条缺口
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from index import SCENE_HINTS, SCENES, load_cards  # noqa: E402

# 卡片标签之外，用户嘴里真正会出现的词。没命中标签时靠它兜底。
LEXICON = [
    "已读不回", "不回消息", "冷战", "吵架", "吃醋", "生气", "委屈", "敷衍", "冷淡", "误会",
    "道歉", "沉默", "不理我", "无聊", "加班", "考试", "期末", "考研", "毕业", "找工作", "辞职",
    "生病", "感冒", "发烧", "生理期", "大姨妈", "痛经", "失眠", "睡不着", "熬夜", "压力",
    "焦虑", "emo", "家里", "爸妈", "父母", "催婚", "相亲", "前任", "异地", "见面", "礼物",
    "生日", "纪念日", "表白", "拒绝", "分手", "复合", "朋友", "闺蜜", "同事", "身材", "减肥",
    "旅行", "累", "疲惫", "哭", "想哭", "难受", "忙", "没空", "在干嘛", "朋友圈", "合照",
]


def scene_of(text: str, vocab_hint: dict[str, str]) -> str | None:
    """按场景词的命中数猜场景。"""
    best, best_hits = None, 0
    for scene, hints in SCENE_HINTS.items():
        hits = sum(1 for word in hints.split() if word in text)
        if hits > best_hits:
            best, best_hits = scene, hits
    return best or vocab_hint.get("fallback")


def tag_vocab() -> set[str]:
    """用现有卡片的标签当词表：这些是这套数据真正认得的词。"""
    vocab: set[str] = set()
    for card in load_cards():
        for tag in card.get("tags", []):
            tag = str(tag).strip()
            if 2 <= len(tag) <= 6:
                vocab.add(tag)
    for hints in SCENE_HINTS.values():
        vocab.update(w for w in hints.split() if len(w) >= 2)
    return vocab


def key_terms(text: str, vocab: set[str]) -> list[str]:
    """从整句里捞出能当检索词的词：库里的标签优先，其次常见说法。"""
    found: list[str] = []
    for size in (4, 3, 2):
        for i in range(len(text) - size + 1):
            piece = text[i:i + size]
            if piece in vocab and piece not in found:
                found.append(piece)
    for word in LEXICON:
        if word in text and word not in found:
            found.append(word)
    found.sort(key=lambda w: (-len(w), text.find(w)))
    return found[:6]


def build_queries(text: str, term: list[str], scene: str | None) -> list[tuple[str, str]]:
    """返回 (检索词, 为什么这么搜)。词太少时直接把她的原话带上引号搜。"""
    label = SCENES.get(scene, "") if scene else ""
    raw = text.replace(" ", "")
    for lead in ("她说", "他说", "她跟我说", "她发来", "我想问", "她"):
        if raw.startswith(lead):
            raw = raw[len(lead):]
            break
    core = " ".join(term[:3])
    quoted = f'"{raw[:22]}"'
    if len(term) <= 1:
        core = quoted
    queries = [
        (f"{core} 怎么回", "最直白的一条，先看别人遇到同款时真的怎么回"),
        (f"{quoted} 高情商回复", "带上她的原话搜，命中率比描述句高"),
        (f"site:xiaohongshu.com {core} 聊天", "小红书的对话截图和评论区，语境最近"),
        (f"site:zhihu.com {core} 怎么办", "知乎容易搜到「她为什么这么说」，用来判断意图"),
        (f"{core} 女生 {label} 经验".strip(), "加上场景词，压掉泛泛而谈的鸡汤"),
        (f"豆瓣 {label} {core} 小组".strip(), "豆瓣小组的原帖，比媒体稿真实"),
    ]
    seen: set[str] = set()
    uniq = []
    for query, why in queries:
        query = " ".join(query.split())
        if query not in seen:
            seen.add(query)
            uniq.append((query, why))
    return uniq


def print_report(text: str, scene: str | None, terms: list[str], queries: list[tuple[str, str]]) -> None:
    label = SCENES.get(scene, "没判断出来") if scene else "没判断出来"
    print(f"# 库里没有，去外面找\n")
    print(f"现场：{text}")
    print(f"猜测场景：{label}（{scene or '-'}）")
    print(f"命中的库内词：{'、'.join(terms) if terms else '一个都没有 —— 这种情况库里确实没有'}\n")

    print("## 检索词（按顺序搜，够用就停，别把六条都搜一遍）\n")
    for i, (query, why) in enumerate(queries, 1):
        print(f"{i}. `{query}`")
        print(f"   {why}")
    print()

    print("## 搜到之后怎么提炼\n")
    print("只抄情境结构，不抄句子。四行就够：")
    print("- 她的原话里，真正在要的是什么（被接住 / 被认同 / 要空间 / 想推进）")
    print("- 网上那些回复里，共同的动作是什么（先接情绪，还是先给方案）")
    print("- 哪一种做法在你这个阶段不成立，为什么")
    print("- 你会用的一句：用你说话风格档案里的句式和标点重写，不要用网上的原句\n")

    print("## 还要问用户的（一次问完，别来回问）\n")
    print("- 她这条消息后面还有没有别的？前一句是什么")
    print("- 你们上次见面或上次吵架是什么时候")
    print("- 她平时生气是说出来，还是变短、变冷")
    print()

    print("## 收尾\n")
    print("回答完在最后加一句：这个情况库里没有，我先按上面的思路给，回头可以补成一张卡。")
    print("不要假装是查表查到的，也不要用「通常女生都……」这种话填空白。")


def save_note(text: str, scene: str | None) -> Path:
    import paths

    folder = paths.gaps_dir()
    folder.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    path = folder / f"{today}.md"
    stamp = dt.datetime.now().strftime("%H:%M")
    block = f"- {stamp} [{scene or '?'}] {text}\n"
    if path.exists():
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(block)
    else:
        path.write_text(
            "# 库里没有的情况\n\n"
            "检索不到合适卡片时记在这里。攒够几条，按 data/schema.md 补成卡。\n\n" + block,
            encoding="utf-8",
            newline="\n",
        )
    return path


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="库里没有时，算出该搜什么")
    parser.add_argument("query", nargs="*", help="她的原话，或者你描述的情况")
    parser.add_argument("--scene", choices=sorted(SCENES), help="已经知道场景就直接指定")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--note", action="store_true", help="顺手把这条缺口记到你的数据目录（默认 ~/.crush-reply/gaps/）")
    args = parser.parse_args()

    text = " ".join(args.query).strip()
    if not text:
        parser.error("给一句她的原话，比如 \"她说她最近有点累，但不说怎么了\"")

    vocab = tag_vocab()
    terms = key_terms(text, vocab)
    scene = args.scene or scene_of(text, {})
    queries = build_queries(text, terms, scene)

    if args.note:
        path = save_note(text, scene)
        print(f"已记到 {path.relative_to(ROOT)}\n", file=sys.stderr)

    if args.json:
        print(json.dumps(
            {"situation": text, "scene": scene, "terms": terms,
             "queries": [{"q": q, "why": w} for q, w in queries]},
            ensure_ascii=False, indent=2,
        ))
        return

    print_report(text, scene, terms, queries)


if __name__ == "__main__":
    main()