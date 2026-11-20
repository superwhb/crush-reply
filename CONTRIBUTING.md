# 怎么加一张卡

改一个文件，加一行 JSON，跑一下检查，提 PR。不需要写代码。熟练之后十分钟能提一张。

## 第一次来，走这条十分钟的路

```bash
# 1. 拿一份
git clone https://github.com/superwhb/crush-reply.git
cd crush-reply
python scripts/doctor.py          # 十一行 ok 就说明环境没问题

# 2. 找一张你觉得写错的卡：跑一句真会出现的对话
python scripts/query.py --scene conflict "她生我气了，一句话都不回" --top 3

# 3. 用向导加一张新的进去，字段和枚举它当场验
python scripts/new_card.py --scene conflict
#    它会问标题、现场信号、目标、阶段、动作、两种写法、禁忌、续法、标签
#    写完自动跑一遍全库 lint，没过就回滚，不会把仓库搞坏

# 4. 确认它能被搜到
python scripts/query.py --scene conflict "你刚写的那句现场" --top 3

# 5. 提 PR，模板里的勾勾上
```

不想装 Python 也行：在 issue 里贴出「她说了什么 + 你希望这张卡覆盖什么」，用 [卡片缺口模板](.github/ISSUE_TEMPLATE/card-gap.md)，别人会接。

## 步骤

```bash
git clone https://github.com/superwhb/crush-reply.git
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
#    心理学概念放 data/psych.jsonl

# 3. 检查（缺字段、id 重复、红线词、诊断式表述都会报行号）
python scripts/lint_data.py
python scripts/lint_extra.py
python scripts/lint_psych.py

# 4. 试试别人能不能搜到你这张卡
python scripts/query.py "你自己想的那句对方的话"

# 5. 回归没被带坏
python scripts/eval.py
python -m unittest discover -s tests
```

加卡最容易踩的是第 5 步：新卡可能把旧用例的正确答案挤到第二位。这是真实存在的情况，`eval.py` 会点名是哪一条，改卡或者改用例都行，别直接跳过去。

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

## 加一条心理学概念

`data/psych.jsonl` 一行一条，字段和口径在 `data/schema.md` 的「心理学概念格式」一节。三条最容易踩的：

1. **source 必须能查**。写「Gottman 1999《The Seven Principles for Making Marriage Work》」，不写「看过一篇讲戈特曼的文章」。
2. **say 必须是人话**。出现「认知失调」「依恋图式」这种词，等于没写。
3. **不贴标签**。`when`/`say`/`do`/`dont` 里出现「你就是」「型人格」「确诊」「治愈」，`lint_psych.py` 直接失败，这是故意的。

```bash
python scripts/lint_psych.py            # 校验字段、来源、场景覆盖
python scripts/psych.py --scene period  # 看看这个场景现在有哪几条
```

## 从素材到卡

不想直接写卡，可以先交素材。`research/` 那条路是：看完一篇外部内容，在 `research/inbox/` 里写一行结构化的话（情境、缺口、提炼），跑 `python scripts/harvest.py check`，`keep` 的再 `promote` 出骨架。

规矩只有一条硬的：**素材里不许有原文句子**。情境要用自己的话复述，示例要自己写。带链接、不抄句子，这条路才能长期走。

## 加新场景

十个场景不够用的时候可以加，但要同时改六处：

1. 新建 `data/scenes/<新场景>.jsonl`，至少 8 张卡才能单独立文件。
2. `scripts/index.py` 的 `SCENES` 和 `SCENE_HINTS` 各加一条（所有检索都从这里取，改这一处就够了）。
3. `scripts/thread.py` 的 `SCENES` 加名字（否则多轮链检索会忽略这个场景）。
4. `scripts/lint_data.py` 和 `scripts/lint_extra.py` 的 `SCENES` 各加名字。
5. `SKILL.md` 的场景表和文件地图各加一行。
6. 新建 `evals/cases/<新场景>.jsonl` 和 `evals/paraphrase/<新场景>.jsonl`，各至少 10 条和 3 条；`evals/gate.json` 的 `scene_min_hit3` 会对这个场景生效，没有用例它就不受保护。

没把握就先开 issue 说一句，别一口气提两百行。

## 改用例

用例是评测的地基，改动前先看清两条赛道的分工：

- `evals/cases/<scene>.jsonl`：写用户真实会打出来的话，判定是 `expect` 里的卡 id（命中任意一张就算 hit@3，第 0 位算 hit@1）。**不要写「只认一张卡」**，除非你确认别的卡确实不该排前面。
- `evals/paraphrase/<scene>.jsonl`：刻意避开卡里的关键词，用同义说法问。这条赛道是防「检索只会背原词」的，写的时候别看卡里怎么写。
- `evals/offtopic.txt`：无关句，不进门槛，只用来看假阳性。加一句无关的话比删一条用例安全。

改门槛要写清理由。把 `min_hit1` 从 0.95 降到 0.90 这种事，等于向用户承诺「二十次里错一次」，PR 里要说清为什么值。

三种情况可以改用例而不改检索：卡本身写错了（那就先改卡）；这个问法本来就该由人多问一句（那就写进 SKILL.md 的「库里没有怎么办」）；两个场景的卡互相抢，且都对（那就同时接受两张）。

## 审 PR 时看什么

- 跑过 `lint_data.py` 吗，CI 绿了吗。
- 卡里的话你自己愿意发出去吗，读出来像不像真人。
- 有没有把「套路」换个名字写进来。
- `difficulty` 标得对不对：会让关系更糟的场合必须标 3。
- 有没有顺手带上 `~/.crush-reply/` 里的东西——画像、语气档案、结果记录都在仓库外，但复制粘贴进 issue 或 PR 也等于漏出去。