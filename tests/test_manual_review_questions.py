#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查人工复核涉及的可答性、法规时点、原典引文和来源边界。"""

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = json.loads((ROOT / "data/questions.json").read_text(encoding="utf-8"))["questions"]
BY_ID = {q["id"]: q for q in QUESTIONS}
RESTORED = (
    "q-0875", "q-0897", "q-0902", "q-0913", "q-0915", "q-0921",
    "q-0923", "q-0934", "q-0946", "q-0954", "q-1009", "q-1010", "q-1015",
)


def selected(q):
    """按内容核对正确项，避免把原始字母当作显示顺序。"""
    return q["options"][ord(q["answer"]) - ord("A")]


class ManualReviewQuestionsTest(unittest.TestCase):
    def test_closed_questions_keep_visible_choices(self):
        for qid in RESTORED:
            with self.subTest(qid=qid):
                q = BY_ID[qid]
                self.assertEqual(q["type"], "single")
                self.assertEqual(len(q["options"]), 4)
                self.assertNotIn("备选范围", q["stem"])
                self.assertNotIn("请填入其中", q["stem"])
                self.assertTrue(selected(q))

    def test_filling_neutral_defense_answer_has_no_duplicate_suffix(self):
        q = BY_ID["q-0892"]
        self.assertNotIn("型型", q["stem"].replace("____", q["answer"][0]))

    def test_armed_police_uses_dated_command_system(self):
        for qid in ("q-0052", "q-0916", "q-1102", "q-1103"):
            with self.subTest(qid=qid):
                q = BY_ID[qid]
                self.assertIn("2018年1月1日", q["stem"])
                self.assertIn("中央军委", q["explanationParts"]["reason"])
                self.assertNotIn("总部、总队、支队", q["explanation"])
        q = BY_ID["q-0916"]
        self.assertNotIn("级级", q["stem"].replace("____", q["answer"][0]))

    def test_old_militia_questions_keep_old_law_and_exact_terms(self):
        for qid in ("q-0050", "q-0914", "q-1100", "q-1101", "q-0057", "q-0919", "q-1108", "q-1109"):
            with self.subTest(qid=qid):
                q = BY_ID[qid]
                self.assertIn("1998年", q["stem"])
                self.assertNotIn("凡年满", q["stem"])
                self.assertNotIn("除征集", q["stem"])
                self.assertNotIn("改编为", q["stem"])

    def test_current_military_service_has_two_forms(self):
        for qid in ("q-0034", "q-0902"):
            q = BY_ID[qid]
            self.assertIn("2021年", q["stem"])
            self.assertEqual(selected(q), "现役和预备役")
        for qid in ("q-0091", "q-0092"):
            self.assertNotIn("三种", BY_ID[qid]["answer"])
            self.assertNotIn("预备役年龄为18岁到35岁", BY_ID[qid]["answer"])
            self.assertIn("国防教育法", BY_ID[qid]["explanationRef"])

    def test_reserve_question_does_not_mix_current_and_old_categories(self):
        q = BY_ID["q-0380"]
        self.assertIn("2021年", q["stem"])
        self.assertNotIn("第一类", selected(q))
        self.assertIn("第三十条", q["explanationRef"])

    def test_defense_definition_and_historical_question_have_clear_versions(self):
        for qid in ("q-0370", "q-0467", "q-0475"):
            q = BY_ID[qid]
            text = q["stem"] + str(q["answer"]) + q["explanation"]
            self.assertIn("分裂", text)
            self.assertIn("发展利益", text)
            self.assertIn("2020年", q["explanationRef"])
        self.assertIn("2011年", BY_ID["q-1493"]["stem"])
        self.assertIn("2011年", BY_ID["q-1502"]["stem"])

    def test_military_rule_authorities_are_current(self):
        for qid in ("q-0477", "q-0480", "q-1225"):
            q = BY_ID[qid]
            self.assertIn("战区", q["answer"])
            self.assertNotIn("军委各总部", q["answer"])
            self.assertIn("第一百一十七条", q["explanationRef"])

    def test_new_force_question_has_only_one_correct_choice(self):
        q = BY_ID["q-1211"]
        self.assertEqual(selected(q), "信息支援部队")
        self.assertNotIn("不包括", q["stem"])
        self.assertIn("调整", q["explanation"])
        self.assertNotIn("三支新力量组建", q["explanation"])

    def test_quotes_follow_original_words(self):
        for qid in ("q-0173", "q-0963"):
            q = BY_ID[qid]
            self.assertEqual(q["stem"].count("仍是"), 2)
            self.assertNotIn("乃是", q["explanation"])
        for qid in ("q-0190", "q-0976"):
            self.assertIn("战争行动", BY_ID[qid]["stem"])
            self.assertNotIn("战争行为", BY_ID[qid]["stem"])
        self.assertIn("紧紧地和中国人民站在一起", BY_ID["q-0643"]["stem"])
        self.assertIn("为中国人民服务，就是这个军队的唯一的宗旨", BY_ID["q-0643"]["stem"])

    def test_treaty_wording_and_political_attribution(self):
        self.assertEqual(BY_ID["q-0117"]["options"][2], "极端主义")
        self.assertIn("十五大", BY_ID["q-0636"]["stem"])
        for qid in ("q-0537", "q-0543"):
            self.assertNotIn("当今", BY_ID[qid]["stem"])

    def test_ctbt_single_choice_accounts_for_russian_withdrawal(self):
        q = BY_ID["q-0319"]
        self.assertNotIn("俄罗斯", q["options"])
        self.assertEqual(selected(q), "美国")
        self.assertIn("2023年", q["explanation"])

    def test_ammunition_proportion_has_period_and_denominator(self):
        q = BY_ID["q-0303"]
        self.assertNotIn("80%", q["answer"])
        for token in ("19948", "9251", "68%", "2003年3月19日", "4月18日"):
            self.assertIn(token, q["answer"] + q["explanation"])

    def test_network_centric_history_avoids_unproved_first_claim(self):
        q = BY_ID["q-1422"]
        self.assertIn("1998年", q["stem"])
        self.assertNotIn("最早", q["stem"])
        self.assertNotIn("第一次正式提出", q["explanationParts"]["reason"])

    def test_war_stages_and_gps_classification_are_not_conflated(self):
        self.assertEqual(BY_ID["q-1009"]["type"], "single")
        self.assertEqual(selected(BY_ID["q-1009"]), "越南战争")
        self.assertEqual(BY_ID["q-0995"]["answer"], ["海湾战争"])
        for qid in ("q-0306", "q-1015"):
            q = BY_ID[qid]
            self.assertIn("分系统", q["stem"])
            self.assertIn("GPS", q["explanation"])
            self.assertIn("计算机", q["explanationParts"]["reason"])

    def test_mismatched_explanations_are_removed(self):
        self.assertIn("1985年", BY_ID["q-0400"]["explanation"])
        self.assertNotIn("布罗迪", BY_ID["q-0400"]["explanation"])
        self.assertIn("恺撒", BY_ID["q-1158"]["explanation"])
        self.assertIn("1848年", BY_ID["q-1159"]["explanation"])
        for qid in ("q-1158", "q-1159"):
            self.assertNotIn("下列", BY_ID[qid]["stem"])
            self.assertNotIn("中国古代军事思想是指", BY_ID[qid]["explanation"])

    def test_mixed_war_case_distinguishes_material_from_verified_fact(self):
        for qid in ("q-0304", "q-1485", "q-1486"):
            self.assertIn("所供PDF", BY_ID[qid]["stem"])
        text = BY_ID["q-1486"]["explanation"]
        self.assertIn("不能", text)
        self.assertIn("免除", text)
        self.assertNotIn("使美国规避了正规军事行动的法律与政治责任", text)

    def test_correct_choices_have_no_distractor_explanation(self):
        ids = RESTORED + ("q-0034", "q-0319", "q-0347", "q-0537", "q-0543", "q-1211", "q-1422")
        for qid in ids:
            with self.subTest(qid=qid):
                q = BY_ID[qid]
                self.assertEqual(q["type"], "single")
                self.assertNotIn(q["answer"], q.get("distractorWhy", {}))
                self.assertTrue(q["explanationParts"]["reason"].strip())
                self.assertTrue(q["explanationRef"].strip())


if __name__ == "__main__":
    unittest.main()
