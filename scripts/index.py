#!/usr/bin/env python3
"""唯一的检索实现。分词、建索引、打分都在这里。

为什么只有一个：以前 query.py、demo.py、eval.py 各自拼了一份索引，字段还不一样，
结果 CI 认证的排序和模型实际拿到的排序不是同一个。现在四边共用这一份。

分词口径：
- 中文整段 + 相邻二元组 + 单字（单字降权到 CHAR_WEIGHT）
- 英文和数字整体保留、转小写
- 单字去一张很小的停用字表，只留实词。这样「她说疼」能命中「疼」那张卡，
  而「她说」不会把整库拉进来。
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import paths

ROOT = Path(__file__).resolve().parent.parent
SCENE_DIR = ROOT / "data" / "scenes"

SCENES = {
    "daily": "分享日常",
    "period": "生理期",
    "conflict": "闹矛盾",
    "jealousy": "吃醋",
    "latenight": "深夜情绪",
    "meetup": "约出来",
    "family": "家人与家庭",
    "distance": "异地",
    "friends": "朋友与社交",
    "anniversary": "生日与纪念日",
}

# 场景先验：命中这些词时给对应场景加一点分。
# 这里只放两个字以上的词，单字（血、谁、约）以前会误伤：血拼、是谁、大约都算命中。
SCENE_HINTS = {
    "period": "生理期 大姨妈 例假 月经 痛经 肚子疼 腰酸 经期 提前 推迟 卫生巾 痛经药",
    "conflict": "生气 吵架 冷战 道歉 惹毛 不高兴 闹别扭 误会 责怪 委屈 和好 不理我 已读不回",
    "jealousy": "吃醋 前任 异性 别的男生 别的女生 追她 追他 合照 点赞 占有欲 醋",
    "latenight": "凌晨 半夜 深夜 睡不着 失眠 压力 想哭 崩溃 撑不住 焦虑 想家 emo",
    "meetup": "约她 约你 见面 出来玩 周末 去哪 吃饭 看电影 咖啡 表白 改期 爽约",
    "daily": "日常 分享 照片 猫 狗 天气 食堂 外卖 无聊 干嘛 在吗 今天",
    "family": "家里 爸妈 父亲 母亲 父母 催婚 相亲 亲戚 弟弟 妹妹 姐姐 哥哥 奶奶 爷爷 回家 过年",
    "distance": "异地 火车 高铁 机票 车票 时差 见面 视频 距离 城市 搬家 调岗",
    "friends": "朋友 闺蜜 兄弟 聚会 同学 同事 介绍 见朋友 一起玩 圈子 聊天记录",
    "anniversary": "生日 纪念日 礼物 一周年 一百天 惊喜 蛋糕 情人 情人节 520 圣诞 跨年 忘了",
}

_CJK = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z]+|\d+")

# 只作用于单字的停用字表。不要往里加「疼、累、哭、忙、饿」这类实词。
_STOP = set("的了是我你她他它这那有就都也还又很在个吗吧啊呢嗯哦呀嘛么和跟与及把被给让对从到说过上下来去后前里外中会要能没不")

CHAR_WEIGHT = 0.5      # 单字命中打对折，二元组和整段不打折
MIN_TAG_DF = 2         # 全库只出现一次的标签不参与检索，它只制造假匹配
OUTCOME_BONUS = 0.6    # 结果回写的最大加分
SCENE_BOOST = 0.45     # 场景词每命中一个加多少，最多加三个
SCENE_BOOST_MAX = 3

# 分数低于这里就当「只是词对上了」。依据 `python scripts/eval.py --calibrate`：
# 对得上 100 条的最低分 44，完全不相关 12 条的最高分 21.6，取中间偏下一点。
# 改写问法的最低分可能低到 19，所以这个阈值是提示，不是硬判定。
WEAK_SCORE = 20.0


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for run in _CJK.findall(text or ""):
        if run.isascii():
            out.append(run.lower())
            continue
        if len(run) == 1:
            if run not in _STOP:
                out.append(run)
            continue
        out.append(run)
        out.extend(run[i:i + 2] for i in range(len(run) - 1))
        out.extend(ch for ch in run if ch not in _STOP)
    return out


def token_weight(token: str) -> float:
    return CHAR_WEIGHT if len(token) == 1 and not token.isascii() else 1.0


def load_cards() -> list[dict]:
    if not SCENE_DIR.is_dir():
        sys.exit(f"找不到数据目录: {SCENE_DIR}")
    cards: list[dict] = []
    for path in sorted(SCENE_DIR.glob("*.jsonl")):
        if path.name.startswith("_"):
            continue
        with path.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    card = json.loads(line)
                except json.JSONDecodeError as exc:
                    sys.exit(f"{path.name}:{lineno} JSON 解析失败: {exc}")
                card["_file"] = path.name
                cards.append(card)
    if not cards:
        sys.exit("数据目录里没有卡片，先跑 scripts/lint_data.py 看看是不是格式错了")
    return cards


def load_outcomes() -> dict[str, float]:
    """读结果回写：每张卡她「接了 / 没接」的净胜率，压成一个 [-0.6, 0.6] 的加分。"""
    path = paths.outcomes_file()
    if not path.exists():
        return {}
    wins: Counter = Counter()
    total: Counter = Counter()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        card_id = str(row.get("id", ""))
        score = row.get("score")
        if not card_id or score not in (-1, 0, 1):
            continue
        total[card_id] += 1
        wins[card_id] += int(score)
    return {cid: OUTCOME_BONUS * wins[cid] / (total[cid] + 3) for cid in total}


def bm25(qtokens, tf, df, avgdl, n_docs, k1=1.5, b=0.75) -> float:
    dl = sum(tf.values()) or 1
    score = 0.0
    for token in qtokens:
        freq = tf.get(token)
        if not freq:
            continue
        idf = math.log(1 + (n_docs - df[token] + 0.5) / (df[token] + 0.5))
        contrib = idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / avgdl))
        score += contrib * token_weight(token)
    return score


def scene_boost(query: str, item: dict) -> float:
    hints = SCENE_HINTS.get(item.get("scene", ""), "")
    hits = [word for word in hints.split() if len(word) >= 2 and word in query]
    return min(len(hits), SCENE_BOOST_MAX) * SCENE_BOOST


def card_text(card: dict, allowed_tags: set[str]) -> str:
    """标题和标签权重最高，靠重复次数实现。单次标签不进索引。"""
    tags = [t for t in card.get("tags") or [] if t in allowed_tags]
    parts = [
        str(card.get("title", "")) * 3,
        " ".join(tags) * 3,
        str(card.get("signal", "")) * 2,
        str(card.get("goal", "")),
        " ".join(card.get("moves") or []),
        " ".join(e.get("text", "") for e in card.get("examples") or []),
    ]
    return " ".join(parts)


class Index:
    """一份只读索引。items 可以是卡片，也可以是多轮链，用 text_fn 换取材方式。"""

    def __init__(self, items: list[dict], text_fn=None):
        self.items = list(items)
        tag_df: Counter = Counter()
        for item in self.items:
            tag_df.update(set(item.get("tags") or []))
        self.allowed_tags = {t for t, n in tag_df.items() if n >= MIN_TAG_DF}
        self.text_fn = text_fn or (lambda item: card_text(item, self.allowed_tags))
        texts = [self.text_fn(item) for item in self.items]
        self.tfs = [Counter(tokenize(text)) for text in texts]
        self.df: Counter = Counter()
        for tf in self.tfs:
            self.df.update(tf.keys())
        lens = [sum(tf.values()) for tf in self.tfs]
        self.avgdl = (sum(lens) / len(lens)) if lens else 1.0
        self.n = len(self.items)
        self.outcomes = load_outcomes()

    def search(self, query: str, top: int = 5, scene: str | None = None,
               stage: str | None = None, difficulty: int | None = None,
               min_difficulty: int | None = None, max_difficulty: int | None = None,
               use_outcomes: bool = True) -> list[tuple[float, dict]]:
        qtokens = tokenize(query)
        if not qtokens:
            return []
        scored: list[tuple[float, dict]] = []
        for item, tf in zip(self.items, self.tfs):
            if scene and item.get("scene") != scene:
                continue
            if stage and stage not in (item.get("stage") or []):
                continue
            level = item.get("difficulty")
            if difficulty is not None and level != difficulty:
                continue
            if min_difficulty is not None and (level or 0) < min_difficulty:
                continue
            if max_difficulty is not None and (level or 9) > max_difficulty:
                continue
            score = bm25(qtokens, tf, self.df, self.avgdl, self.n) + scene_boost(query, item)
            if use_outcomes:
                score += self.outcomes.get(str(item.get("id", "")), 0.0)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("id"))))
        return scored[:top]

    def explain(self, query: str, item: dict, limit: int = 6) -> list[tuple[str, int, int, float]]:
        """[(词, 卡里出现次数, 文档频率, 贡献分)]，按贡献从大到小。"""
        tf = self.tfs[self.items.index(item)] if item in self.items else Counter()
        dl = sum(tf.values()) or 1
        rows = []
        seen = set()
        for token in tokenize(query):
            if token in seen:
                continue
            seen.add(token)
            freq = tf.get(token)
            if not freq:
                continue
            idf = math.log(1 + (self.n - self.df[token] + 0.5) / (self.df[token] + 0.5))
            contrib = idf * (freq * 2.5) / (freq + 1.5 * (0.25 + 0.75 * dl / self.avgdl))
            rows.append((token, freq, self.df[token], contrib * token_weight(token)))
        rows.sort(key=lambda r: -r[3])
        return rows[:limit]


def scene_hits(query: str, scene: str) -> list[str]:
    return [w for w in SCENE_HINTS.get(scene, "").split() if len(w) >= 2 and w in query]


def render(card: dict, rank: int) -> str:
    lines = [
        f"[{rank}] {card['id']}  {card['title']}   难度{card['difficulty']}  阶段:{'/'.join(card['stage'])}",
        f"    现场: {card['signal']}",
        f"    目标: {card['goal']}",
        f"    手法: {' / '.join(card['moves'])}",
        "    示例:",
    ]
    for ex in card["examples"]:
        lines.append(f"      - {ex['style']}  {ex['text']}")
    lines.append(f"    别说: {'；'.join(card['taboo'])}")
    lines.append(f"    续法: {card['followup']}")
    return "\n".join(lines)