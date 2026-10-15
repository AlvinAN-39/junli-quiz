#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""锁定用户截图中的知识点、同源题一致性和实际题库消费契约。"""

import json
import unittest
from pathlib import Path

from tools.answer_text import answer_text


ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = json.loads(
    (ROOT / "data/questions.json").read_text(encoding="utf-8")
)["questions"]
BY_ID = {q["id"]: q for q in QUESTIONS}


def selected_texts(q):
    """比较选项内容，避免把乱序后的字母误当成知识答案。"""
    letters = q["answer"] if isinstance(q["answer"], list) else [q["answer"]]
    return {q["options"][ord(letter) - ord("A")] for letter in letters}


class ScreenshotQuestionsTest(unittest.TestCase):
    def test_defense_four_elements(self):
        for qid in ("q-0427", "q-1215"):
            with self.subTest(qid=qid):
                q = BY_ID[qid]
                self.assertEqual(selected_texts(q), set(q["options"]))

    def test_foreign_thought_includes_innovation(self):
        expected = {"创新性", "规范性", "开放性", "继承性"}
        for qid in ("q-0207", "q-1312"):
            with self.subTest(qid=qid):
                self.assertEqual(selected_texts(BY_ID[qid]), expected)

    def test_weapon_effectiveness_includes_traditional_capabilities(self):
        expected = {"火力", "机动力", "突击力和防护力", "电子信息处理能力"}
        for qid in ("q-0334", "q-1415"):
            with self.subTest(qid=qid):
                self.assertEqual(selected_texts(BY_ID[qid]), expected)

    def test_clausewitz_negative_question_has_choices(self):
        q = BY_ID["q-0944"]
        original = BY_ID["q-0146"]
        self.assertEqual(q["type"], "single")
        self.assertNotEqual(q["stem"], original["stem"])
        self.assertIn("时代属性", q["stem"])
        self.assertEqual(q["options"], original["options"])
        self.assertEqual(selected_texts(q), {"是西方古代军事理论的顶峰之作"})

    def test_assistance_uses_explicit_textbook_classification(self):
        q = BY_ID["q-0444"]
        self.assertIn("教材", q["stem"])
        self.assertEqual(q["answer"], ["B", "C", "D"])
        text = q["explanation"] + q["explanationRef"]
        for article in ("第五十六条", "第五十八条", "第六十三条", "第六十六条"):
            self.assertIn(article, text)
        for stale in ("建议复核", "被答案排除", "支撑不了", "待核实"):
            self.assertNotIn(stale, text)
        self.assertNotEqual(q.get("lawCitationIssue"), "unsupported")

    def test_informatization_question_separates_background_and_effect(self):
        q = BY_ID["q-0283"]
        self.assertNotIn("主要原因", q["stem"])
        self.assertNotIn("不二选择", q["stem"])
        self.assertEqual(selected_texts(q), set(q["options"]))
        reason = q["explanationParts"]["reason"]
        for concept in ("信息技术", "质量", "机械化", "指挥"):
            self.assertIn(concept, reason)

    def test_information_security_has_direct_textbook_evidence(self):
        q = BY_ID["q-0125"]
        self.assertEqual(
            selected_texts(q), {"技术缺陷", "网络黑客", "电脑病毒", "信息污染"}
        )
        self.assertEqual(q["explanationSrc"], "textbook")
        self.assertIn("69", q["explanationRef"])
        self.assertEqual(set(q["keywords"]), set(q["options"]))

    def test_mobilization_distinguishes_foundation_and_core(self):
        q = BY_ID["q-0062"]
        self.assertEqual(selected_texts(q), {"国民经济动员"})
        self.assertIn("核心", q["distractorWhy"]["A"])
        self.assertIn("国民经济动员", q["keywords"])
        self.assertIn("武装力量动员", q["keywords"])

    def test_correct_options_are_never_described_as_distractors(self):
        for qid in (
            "q-0427", "q-0207", "q-0334", "q-0944",
            "q-0444", "q-0283", "q-0125", "q-0062",
        ):
            q = BY_ID[qid]
            correct = (
                set(q["answer"])
                if isinstance(q["answer"], list)
                else {q["answer"]}
            )
            with self.subTest(qid=qid):
                self.assertTrue(correct.isdisjoint(q.get("distractorWhy", {})))
                self.assertTrue(q["explanationRef"].strip())
                # 使用生产打包共用的答案转换器，检查其输出有实际含义。
                self.assertTrue(answer_text(q).strip())
                self.assertTrue(q["explanationParts"].get("reason", "").strip())


if __name__ == "__main__":
    unittest.main()
