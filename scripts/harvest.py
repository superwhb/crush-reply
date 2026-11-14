#!/usr/bin/env python3
"""每日情报：轮转检索词、登记看过的内容、把候选整理成卡。

这个脚本不联网。联网的部分由模型（或你自己）用搜索完成，脚本负责三件事：
  1. plan     按日期轮转出今天该搜的三组词（并避开最近看过的东西）
  2. check    校验 research/inbox 里的候选、查重、报统计
  3. promote  把一条候选变成能进 lint 的卡片骨架

用法:
    python scripts/harvest.py plan
    python scripts/harvest.py plan --day 2026-11-14 -n 2
    python scripts/harvest.py check
    python scripts/harvest.py check --explain
    python scripts/harvest.py promote hb-0007
    python scripts/harvest.py stats
"""
from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

RESEARCH = ROOT / "research"
INBOX = RESEARCH / "inbox"
SEEN = RESEARCH / "seen.jsonl"

SCENES = [
    "daily", "period", "conflict", "jealousy", "latenight",
    "meetup", "family", "distance", "friends", "anniversary",
]
PLATFORMS = ["xiaohongshu", "douyin", "zhihu", "douban", "weibo", "bilibili", "news", "other"]
VERDICTS = ["keep", "dup", "reject", "promoted"]

# 十二组检索词，按日轮转。每组三条：一条偏知乎（文字易被索引），
# 一条偏小红书/抖音（靠搜索结果里的标题摘要），一条偏「反面视角」。
GROUPS = [
    {
        "topic": "已读不回与回消息慢",
        "scene": "daily",
        "queries": [
            "知乎 女朋友 已读不回 男生 怎么回",
            "小红书 他回消息很慢 我该怎么回 评论区",
            "回消息慢 是不是不在乎 双方面 讨论 知乎",
        ],
        "watch": "这类内容一半是「他不爱你」，只取讲具体做法的部分",
    },
    {
        "topic": "生理期怎么关心才不显得敷衍",
        "scene": "period",
        "queries": [
            "知乎 女朋友 来例假 男生该做什么",
            "小红书 痛经 男朋友 做了这些 评论",
            "多喝热水 为什么被讨厌 知乎",
        ],
        "watch": "医学建议不要抄，只取「做什么动作」",
    },
    {
        "topic": "冷战与吵架后修复",
        "scene": "conflict",
        "queries": [
            "知乎 情侣 冷战 谁先低头 怎么破冰",
            "小红书 吵架后 男朋友 第一句话",
            "吵架 不要说什么 越说越僵 知乎",
        ],
        "watch": "别取「晾着她」这一类策略，仓库红线禁",
    },
    {
        "topic": "吃醋与异性朋友",
        "scene": "jealousy",
        "queries": [
            "知乎 女朋友 异性朋友 边界 怎么表达不舒服",
            "小红书 男友 吃醋 反应 评论",
            "吃醋 说出来 显得小气吗 知乎",
        ],
        "watch": "警惕控制欲包装成关心",
    },
    {
        "topic": "深夜情绪与自我否定",
        "scene": "latenight",
        "queries": [
            "知乎 女生 半夜 说睡不着 男生 怎么回",
            "小红书 深夜 emo 有人陪着 聊天",
            "她说自己没用 怎么安慰 不要讲道理 知乎",
        ],
        "watch": "出现自伤表述的内容一律不进卡，只作为危机口径参考",
    },
    {
        "topic": "约不出来与第一次见面",
        "scene": "meetup",
        "queries": [
            "知乎 约女生 不出来 怎么再开口",
            "小红书 第一次约会 男生 减分 细节",
            "暧昧期 约 被拒绝 还要不要约 知乎",
        ],
        "watch": "「再约三次」这类硬推不要",
    },
    {
        "topic": "父母反对与见家长",
        "scene": "family",
        "queries": [
            "知乎 父母反对 恋爱 男生 怎么处理",
            "小红书 见家长 男生 表现 评论",
            "女朋友 家里不同意 我该说什么 知乎",
        ],
        "watch": "别取「让女生去说服父母」这种把压力推回去的说法",
    },
    {
        "topic": "异地与时差",
        "scene": "distance",
        "queries": [
            "知乎 异地恋 没话说 怎么维持",
            "小红书 异地 视频 冷场 怎么办",
            "异地 见面频率 吵架 知乎",
        ],
        "watch": "承诺类内容要落到具体动作，否则不进卡",
    },
    {
        "topic": "朋友圈、闺蜜与社交评价",
        "scene": "friends",
        "queries": [
            "知乎 女朋友 闺蜜 说我不好 怎么办",
            "小红书 男友 不被朋友看好 评论",
            "女朋友 聚会 不带我 知乎",
        ],
        "watch": "「让闺蜜闭嘴」这类不要",
    },
    {
        "topic": "生日、纪念日与礼物",
        "scene": "anniversary",
        "queries": [
            "知乎 忘记纪念日 怎么补救",
            "小红书 男朋友 礼物 送到心坎 评论",
            "礼物 太贵 有压力 怎么送 知乎",
        ],
        "watch": "消费主义话术不进卡，只取「怎么表达在意」",
    },
    {
        "topic": "暧昧期判断与推进",
        "scene": "daily",
        "queries": [
            "知乎 怎么判断 女生 有没有好感 具体表现",
            "小红书 暧昧期 男生 什么时候该表白 评论",
            "暧昧 一直不推进 原因 知乎",
        ],
        "watch": "「测试她」类内容一律拒",
    },
    {
        "topic": "分手边缘与挽回（高危）",
        "scene": "conflict",
        "queries": [
            "知乎 她说累了 想分手 还有救吗 双方",
            "小红书 分手 挽回 男生 做错了什么",
            "体面分手 怎么说 知乎",
        ],
        "watch": "只取「体面收场」和「问清原因」两类，任何挽回套路都不进",
    },
]

CANDIDATE_RE = re.compile(r"^hb-\d{4}$")


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path.name}:{lineno} 解析失败 {exc}") from exc
    return rows


def candidates() -> list[dict]:
    rows = []
    for path in sorted(INBOX.glob("*.jsonl")):
        for row in load_jsonl(path):
            row["_file"] = path.name
            rows.append(row)
    return rows


def parse_day(text: str | None) -> date:
    if not text:
        return date.today()
    return datetime.strptime(text, "%Y-%m-%d").date()


def check_text(text: str, low: int, high: int) -> str | None:
    n = len(text.strip())
    if n < low:
        return f"太短（{n} 字，至少要 {low}）"
    if n > high:
        return f"太长（{n} 字，最多 {high}）"
    return None


# ---------- plan ----------

def cmd_plan(args) -> int:
    day = parse_day(args.day)
    cutoff = (day - timedelta(days=args.avoid_days)).isoformat()
    recent = {row.get("topic") for row in load_jsonl(SEEN)
              if row.get("topic") and str(row.get("date", "")) >= cutoff}
    start = day.toordinal() % len(GROUPS)
    picked = []
    for step in range(len(GROUPS)):
        group = GROUPS[(start + step) % len(GROUPS)]
        if group["topic"] in recent:
            continue
        picked.append(group)
        if len(picked) >= args.n:
            break

    if not picked:
        print("最近都搜过了，隔几天再来。")
        return 0

    print(f"# {day.isoformat()} 今日检索（{len(picked)} 组）\n")
    for group in picked:
        print(f"## {group['topic']}  → 场景 `{group['scene']}`")
        for q in group["queries"]:
            print(f"- `{q}`")
        print(f"\n提防：{group['watch']}\n")
    print("看完写候选：research/inbox/<日期>.jsonl，一行一个，字段见 research/README.md。")
    print("写完跑 `python scripts/harvest.py check`。")
    return 0


# ---------- check ----------

def cmd_check(args) -> int:
    from query import load_cards, tokenize  # 延迟导入，plan 不需要它

    errors: list[str] = []
    warns: list[str] = []

    seen_rows = load_jsonl(SEEN)
    seen_urls = set()
    for i, row in enumerate(seen_rows, 1):
        url = str(row.get("url", ""))
        if not url.startswith("http"):
            errors.append(f"seen.jsonl:{i} url 不是 http(s)")
        if url in seen_urls:
            warns.append(f"seen.jsonl:{i} url 重复 {url}")
        seen_urls.add(url)
        if not row.get("title"):
            errors.append(f"seen.jsonl:{i} 缺 title")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(row.get("date", ""))):
            errors.append(f"seen.jsonl:{i} date 必须是 YYYY-MM-DD")

    rows = candidates()
    ids = set()
    for row in rows:
        cid = str(row.get("id", ""))
        where = f"{row.get('_file')} {cid or '(无 id)'}"
        if not CANDIDATE_RE.match(cid):
            errors.append(f"{where} id 必须是 hb-四位数字")
        if cid in ids:
            errors.append(f"{where} id 重复")
        ids.add(cid)
        if row.get("platform") not in PLATFORMS:
            errors.append(f"{where} platform 必须是 {PLATFORMS}")
        if not str(row.get("url", "")).startswith("http"):
            errors.append(f"{where} 缺 url，候选必须能追溯到来源")
        if row.get("scene_guess") not in SCENES:
            errors.append(f"{where} scene_guess 必须是 {SCENES}")
        verdict = row.get("verdict")
        if verdict not in VERDICTS:
            errors.append(f"{where} verdict 必须是 {VERDICTS}")
        for field, low, high in (("situation", 10, 80), ("gap", 6, 60), ("insight", 10, 80)):
            problem = check_text(str(row.get(field, "")), low, high)
            if problem:
                errors.append(f"{where} {field} {problem}")
        if verdict == "dup" and not row.get("dup_of"):
            errors.append(f"{where} verdict=dup 时必须写 dup_of")
        if verdict == "reject" and not row.get("reject_reason"):
            warns.append(f"{where} verdict=reject 最好写一句 reject_reason")

    # 查重：候选的 situation 有多少「实词」已经被某张卡覆盖。
    # 用 IDF 加权覆盖率，不用 BM25 原始分——候选只有一句话，长度差距会把分数拉爆。
    cards = load_cards()
    tfs, df = [], Counter()
    for card in cards:
        text = (
            str(card.get("title", "")) * 3 + " " + " ".join(card.get("tags", [])) * 3 + " "
            + str(card.get("signal", "")) * 2 + " " + str(card.get("goal", "")) + " "
            + " ".join(card.get("moves", []))
        )
        # 只留 2-4 字的片段：整句子串的 IDF 太高，会把覆盖率压到接近 0
        tf = Counter(t for t in tokenize(text) if 2 <= len(t) <= 4)
        tfs.append(tf)
        for token in tf:
            df[token] += 1

    n = len(cards) or 1

    def idf(token: str) -> float:
        return math.log((n + 1) / (df.get(token, 0) + 1)) + 1.0

    for row in rows:
        if row.get("verdict") != "keep":
            continue
        situation = str(row.get("situation", ""))
        # 在库里出现过的 2-4 字片段，按稀有度排序：先看共性最强的共同词
        qtokens = [t for t in tokenize(situation) if 2 <= len(t) <= 4 and df.get(t, 0) >= 1]
        if not qtokens:
            continue
        scored = []
        for card, tf in zip(cards, tfs):
            shared = [t for t in qtokens if t in tf]
            if not shared:
                continue
            weight = sum(idf(t) for t in shared)
            shared.sort(key=lambda t: (-idf(t), -len(t)))
            scored.append((weight, card, shared))
        scored.sort(key=lambda item: -item[0])

        # 不管重不重复，都把最近的两张卡列出来：人看一眼就知道库里有没有
        near = []
        for weight, card, shared in scored[:2]:
            near.append(f"{card['id']}（{card['title']}）共同词 {'/'.join(shared[:3])}")
        print(f"近邻 {row.get('id')}: " + "；".join(near) if near else f"近邻 {row.get('id')}: 库里没有相近的")

        # 强重复信号：和一个几乎一样的句串重合，或共享一个全库只出现一两次的短语
        if scored:
            weight, card, shared = scored[0]
            rare = [t for t in shared if df.get(t, 0) <= 2 and len(t) >= 3]
            same_text = difflib.SequenceMatcher(None, situation, str(card.get("signal", ""))).ratio() >= 0.75
            if rare or same_text:
                why = f"共同稀有词 {'/'.join(rare)}" if rare else "描述几乎一样"
                warns.append(
                    f"可能重复：{row.get('id')} 和 {card['id']}（{card['title']}），{why}；"
                    f"如果库里已经有这张卡，改成 verdict=dup 并填 dup_of"
                )

    for line in warns:
        print(f"警告 {line}")
    for line in errors:
        print(f"错误 {line}")

    by_verdict = Counter(row.get("verdict") for row in rows)
    print(f"\n候选 {len(rows)} 条，登记 {len(seen_rows)} 条来源")
    if rows:
        print(f"结论分布: {dict(by_verdict)}")
    print(f"错误 {len(errors)}，警告 {len(warns)}")
    return 1 if errors else 0


# ---------- promote ----------

def cmd_promote(args) -> int:
    target = args.id
    row = next((r for r in candidates() if r.get("id") == target), None)
    if not row:
        raise SystemExit(f"没找到候选 {target}")
    if row.get("verdict") != "keep":
        raise SystemExit(f"{target} 的 verdict 是 {row.get('verdict')}，只有 keep 才转卡")

    scene = row["scene_guess"]
    skeleton = {
        "id": f"{scene}-NEW",
        "scene": scene,
        "title": "（6-14 字，写这个情境最典型的说法）",
        "signal": row["situation"],
        "stage": ["暧昧"],
        "goal": "（接情绪 / 推进 / 降级 / 给出口）",
        "moves": ["共情"],
        "examples": [
            {"style": "共情", "text": "（自己写一句，不许抄来源）"},
            {"style": "认真", "text": "（自己写一句，不许抄来源）"},
        ],
        "taboo": ["（写具体的错句）"],
        "followup": "（她没回时你做什么，要能执行）",
        "tags": [],
        "difficulty": 2,
    }
    print(f"来源：{row.get('url')}")
    print(f"缺口：{row.get('gap')}")
    print(f"提炼：{row.get('insight')}\n")
    print(f"复制下面这段，改掉括号里的内容，追加到 data/scenes/{scene}.jsonl：")
    print(json.dumps(skeleton, ensure_ascii=False))
    print("\n写完跑：python scripts/lint_data.py && python scripts/query.py \"她的原话\"")
    print("最后把这条候选的 verdict 改成 promoted，并在 seen.jsonl 里留一行来源。")
    return 0


# ---------- stats ----------

def cmd_stats(args) -> int:
    rows = candidates()
    seen_rows = load_jsonl(SEEN)

    print(f"候选 {len(rows)} 条 / 来源 {len(seen_rows)} 条")
    if not rows:
        return 0
    print(f"结论: {dict(Counter(r.get('verdict') for r in rows))}")
    print(f"平台: {dict(Counter(r.get('platform') for r in rows))}")
    print(f"场景: {dict(Counter(r.get('scene_guess') for r in rows))}")
    kept = Counter(r.get("scene_guess") for r in rows if r.get("verdict") == "keep")
    if kept:
        print(f"最缺的场景: {kept.most_common(3)}")
    return 0


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="每日情报：检索计划、候选校验、转卡")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_plan = sub.add_parser("plan", help="出今天的检索词")
    p_plan.add_argument("--day", help="指定日期 YYYY-MM-DD，默认今天")
    p_plan.add_argument("-n", type=int, default=3, help="出几组，默认 3")
    p_plan.add_argument("--avoid-days", type=int, default=10, help="最近几天搜过的主题跳过")
    p_plan.set_defaults(func=cmd_plan)

    p_check = sub.add_parser("check", help="校验候选与来源登记，并列出最近的卡")
    p_check.set_defaults(func=cmd_check)

    p_promote = sub.add_parser("promote", help="把候选转成卡片骨架")
    p_promote.add_argument("id")
    p_promote.set_defaults(func=cmd_promote)

    p_stats = sub.add_parser("stats", help="看看攒了多少")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()