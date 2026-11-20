#!/usr/bin/env python3
"""最小回归测试。跑 `python -m unittest discover -s tests -v`。

这些测试只覆盖「改坏了会静默变差」的地方：分词、过滤、检索、画像数据位置、
评测用例里有没有写错的卡 id。它们不测措辞，也不测回复质量。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


class RetrievalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from index import Index, load_cards

        cls.cards = load_cards()
        cls.index = Index(cls.cards)

    def test_single_char_still_finds_something(self):
        """以前单字会被整个丢掉，「疼」这种最常见的输入直接 0 命中。"""
        from index import tokenize

        self.assertIn("疼", tokenize("她说疼"))
        top = self.index.search("疼", top=3, scene="period", use_outcomes=False)
        self.assertTrue(top, "单字「疼」应该能查到 period 的卡")
        self.assertTrue(all(card["scene"] == "period" for _, card in top))

    def test_scene_filter_is_strict(self):
        top = self.index.search("她不理我", top=5, scene="conflict", use_outcomes=False)
        self.assertTrue(top)
        self.assertTrue(all(card["scene"] == "conflict" for _, card in top))

    def test_stage_filter_works(self):
        # 异地场景目前没有「初识」的卡（数据缺口，见复盘），用有这个阶段的场景测。
        top = self.index.search("同城见不到", top=5, scene="distance", stage="暧昧", use_outcomes=False)
        self.assertTrue(top)
        for _, card in top:
            self.assertIn("暧昧", card["stage"])

    def test_min_difficulty_filter(self):
        top = self.index.search("冷战", top=5, scene="conflict", min_difficulty=3, use_outcomes=False)
        self.assertTrue(top)
        self.assertTrue(all(card["difficulty"] >= 3 for _, card in top))

    def test_irrelevant_query_scores_survive_filter(self):
        """完全不相关的句子可以没有结果，但不能报错。"""
        top = self.index.search("把空调温度调低一点", top=3, use_outcomes=False)
        self.assertIsInstance(top, list)

    def test_scores_are_sorted(self):
        top = self.index.search("她说明天来例假肚子疼", top=5, scene="period", use_outcomes=False)
        scores = [s for s, _ in top]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_explain_mentions_matched_terms(self):
        card = next(c for c in self.cards if c["id"] == "period-037")
        terms = {token for token, *_ in self.index.explain("别再让我多喝热水", card)}
        self.assertIn("多喝", terms)


class EvalCaseTest(unittest.TestCase):
    def test_every_expected_id_exists(self):
        from index import load_cards

        ids = {card["id"] for card in load_cards()}
        for folder in ("cases", "paraphrase"):
            for path in sorted((ROOT / "evals" / folder).glob("*.jsonl")):
                for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if not line.strip():
                        continue
                    case = json.loads(line)
                    for expected in case["expect"]:
                        self.assertIn(expected, ids, f"{folder}/{path.name}:{lineno} 期望的卡不存在")

    def test_each_main_scene_has_enough_cases(self):
        counts = {}
        for path in (ROOT / "evals" / "cases").glob("*.jsonl"):
            counts[path.stem] = len([l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()])
        self.assertEqual(len(counts), 10, "十个场景都要有用例")
        for scene, n in counts.items():
            self.assertGreaterEqual(n, 10, f"{scene} 的用例少于 10 条")

    def test_gate_parses(self):
        gate = json.loads((ROOT / "evals" / "gate.json").read_text(encoding="utf-8"))
        for key in ("min_hit1", "min_hit3", "para_min_hit3"):
            self.assertIn(key, gate)


class PathsTest(unittest.TestCase):
    def test_home_follows_env(self):
        import paths

        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("CRUSH_HOME")
            os.environ["CRUSH_HOME"] = tmp
            try:
                self.assertEqual(paths.data_home(), Path(tmp))
                paths.ensure()
                self.assertTrue(paths.profiles_dir().is_dir())
                self.assertTrue(paths.voices_dir().is_dir())
            finally:
                if old is None:
                    os.environ.pop("CRUSH_HOME", None)
                else:
                    os.environ["CRUSH_HOME"] = old


class OpenersTest(unittest.TestCase):
    def test_pick_respects_anchor(self):
        from openers import pick

        rows = pick(n=3, anchor="求助请教")
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r["anchor"] == "求助请教" for r in rows))

    def test_pick_is_deterministic(self):
        from openers import pick

        self.assertEqual([r["id"] for r in pick(n=3)], [r["id"] for r in pick(n=3)])

    def test_pick_prefers_her_own_words_when_profile_has_event(self):
        from openers import pick

        profile = "代号: 小鹿\n近期事件: 下周三门考试\n"
        rows = pick(profile=profile, n=3)
        self.assertEqual(rows[0]["anchor"], "她提过的事")


if __name__ == "__main__":
    unittest.main()