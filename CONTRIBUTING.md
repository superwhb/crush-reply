# 怎么加一张卡

改一个文件，加一行 JSON，跑一下检查，提 PR。不需要写代码。

## 步骤

```bash
git clone https://github.com/<you>/crush-reply.git
cd crush-reply

# 1. 读格式
cat data/schema.md

# 2. 挑场景，加一行（追加到文件末尾）
#    data/scenes/daily.jsonl        分享日常
#    data/scenes/period.jsonl       生理期
#    data/scenes/conflict.jsonl     闹矛盾
#    data/scenes/jealousy.jsonl     吃醋
#    data/scenes/latenight.jsonl    深夜情绪
#    data/scenes/meetup.jsonl       约出来
#    data/scenes/family.jsonl       家人与家庭
#    data/scenes/distance.jsonl     异地
#    data/scenes/friends.jsonl      朋友与社交
#    data/scenes/anniversary.jsonl  生日与纪念日
#
#    多轮链放 data/threads/<场景>.jsonl，开场白放 data/openers.jsonl

# 3. 检查（缺字段、id 重复、红线词都会报行号）
python scripts/lint_data.py
python scripts/lint_extra.py

# 4. 试试别人能不能搜到你这张卡
python scripts/query.py "你自己想的那句对方的话"
```

需要 Python 3.9 以上，没有第三方依赖。

## 什么卡会被合

- 情境具体到能对号入座，`signal` 带原话。
- 示例是**真能发出去的微信**，四十字以内，不油腻。
- `taboo` 写到具体句子，不是「避免否定情绪」这种空话。
- `followup` 是可执行的动作，不是「保持沟通」。
- 覆盖的情境在现有卡里找不到重复。

## 什么卡会被拒

- 教人打压、冷处理、假装忙、欲擒故纵、试探性欺骗。
- 打分、排序、物化对方的表达。
- 搬运别人视频或文章的文案（版权问题，而且多数质量不行）。
- 涉及未成年人，或者带性暗示。
- 一句「多喝热水」式的万能答案。这类只能进 `taboo`。

## 加一条多轮链或一句开场白

多轮链比单卡有用，也比单卡难写。合格线是三条：

- 每一轮都要变动作，第二轮不能和第一轮同一个手法。
- 每一轮都得推进一小步：情绪 → 具体的事 → 一个动作 → 时间地点。
- `exit` 必须写清「她没接怎么收」。这不是补充说明，是这条链最值钱的一行。

开场白看 `data/openers.jsonl`，一个文件装全部场景。优先补 `anchor=她提过的事` 这类，它的接受率最高。

## 从素材到卡

不想直接写卡，可以先交素材。`research/` 那条路是：看完一篇外部内容，在 `research/inbox/` 里写一行结构化的话（情境、缺口、提炼），跑 `python scripts/harvest.py check`，`keep` 的再 `promote` 出骨架。

规矩只有一条硬的：**素材里不许有原文句子**。情境要用自己的话复述，示例要自己写。带链接、不抄句子，这条路才能长期走。

## 加新场景

十个场景不够用的时候可以加，但要同时改五处：

1. 新建 `data/scenes/<新场景>.jsonl`，至少 8 张卡才能单独立文件。
2. `scripts/query.py` 的 `SCENES` 和 `SCENE_HINTS` 各加一条。
3. `scripts/thread.py` 的 `SCENES` 加名字（否则多轮链检索会忽略这个场景）。
4. `scripts/lint_data.py` 和 `scripts/lint_extra.py` 的 `SCENES` 各加名字。
5. `SKILL.md` 的场景表和文件地图各加一行。

没把握就先开 issue 说一句，别一口气提两百行。

## 审 PR 时看什么

- 跑过 `lint_data.py` 吗，CI 绿了吗。
- 卡里的话你自己愿意发出去吗，读出来像不像真人。
- 有没有把「套路」换个名字写进来。
- `difficulty` 标得对不对：会让关系更糟的场合必须标 3。
- 有没有顺手带上 `profiles/` 或 `voices/` 里的东西——那两份是本机私人物料，`.gitignore` 已经挡住，但复制粘贴进 issue 或 PR 也等于漏出去。