改动之前先说清楚这是什么，比写得好更重要。

## 这次改了什么

- [ ] 加卡（场景：）
- [ ] 加多轮链 / 开场白
- [ ] 加心理学概念
- [ ] 改脚本
- [ ] 改文档

## 自己跑过什么

```
python scripts/lint_data.py
python scripts/lint_extra.py
python scripts/lint_psych.py
python scripts/eval.py
python scripts/doctor.py
```

把最后一行贴上来。

## 关于内容的三条

- 我写的不是可直接复制的句子，只写方向、禁忌和续法。
- 我没有把对方的隐私信息写进卡里（姓名、账号、住址、截图）。
- 我没有把 PUA、冷处理、试探、「劝分」当方法写进去。

## 关于代码的两条

- 没引入第三方依赖（这个仓库只依赖标准库）。
- 如果改了检索或者 lint 规则，我加了对应的回归用例。