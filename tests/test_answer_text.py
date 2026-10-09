#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_answer_text.py — `tools/answer_text.py` 的单元测试
================================================================

`answer_text.py` 自述是「全项目唯一的答案读取实现」，而项目历史上正是
「同一段逻辑出现第二处」导致 6 个脚本同时抛 `TypeError`。
因此这里的重点是**容错边界**：每种题型的每一种历史形态都必须给出确定结果，
且绝不抛异常。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.answer_text import LETTERS, answer_display, answer_text, letters_of

OPT4 = ["甲", "乙", "丙", "丁"]


def single(answer, options=OPT4):
    return {"type": "single", "answer": answer, "options": list(options)}


def multi(answer, options=OPT4):
    return {"type": "multi", "answer": answer, "options": list(options)}


class TestLettersOf(unittest.TestCase):
    def test_single_string(self):
        self.assertEqual(letters_of(single("A")), ["A"])
        self.assertEqual(letters_of(single("H")), ["H"])

    def test_single_single_element_list_is_tolerated(self):
        # 回归：T18 修正答案后出现 7 道 answer 为列表的单选题，
        # 读取端必须容错（当年 6 处各自实现全部崩在这里）。
        self.assertEqual(letters_of(single(["B"])), ["B"])

    def test_single_rejects_multi_element_list(self):
        self.assertEqual(letters_of(single(["A", "B"])), [])

    def test_single_rejects_invalid_values(self):
        for bad in ("", " ", "Z", "AB", "a", None, 3, [], ["Z"], ["AB"], True):
            with self.subTest(answer=bad):
                self.assertEqual(letters_of(single(bad)), [])

    def test_multi_preserves_order_and_filters(self):
        self.assertEqual(letters_of(multi(["C", "A"])), ["C", "A"])
        self.assertEqual(letters_of(multi(["A", "Z", 1, None, "B"])), ["A", "B"])

    def test_multi_requires_list(self):
        # 契约规定 multi 是数组；字符串形态不做「猜切分」，直接视为无答案。
        self.assertEqual(letters_of(multi("AB")), [])
        self.assertEqual(letters_of(multi(None)), [])

    def test_non_choice_types_have_no_letters(self):
        for t in ("judge", "fill", "short", "", "unknown"):
            with self.subTest(type=t):
                self.assertEqual(letters_of({"type": t, "answer": "A"}), [])

    def test_letters_constant_is_sane(self):
        self.assertTrue(LETTERS.startswith("A"))
        self.assertEqual(len(set(LETTERS)), len(LETTERS))


class TestAnswerText(unittest.TestCase):
    def test_single_returns_option_text(self):
        self.assertEqual(answer_text(single("A")), "甲")
        self.assertEqual(answer_text(single("D")), "丁")

    def test_single_out_of_range_letter_returns_empty(self):
        self.assertEqual(answer_text(single("D", options=["甲", "乙"])), "")

    def test_single_without_answer_returns_empty(self):
        self.assertEqual(answer_text(single("Z")), "")
        self.assertEqual(answer_text(single(None)), "")

    def test_multi_concatenates_option_texts(self):
        self.assertEqual(answer_text(multi(["A", "C"])), "甲丙")
        self.assertEqual(answer_text(multi(["A", "B", "C", "D"])), "甲乙丙丁")

    def test_multi_skips_out_of_range_letters(self):
        self.assertEqual(answer_text(multi(["A", "D"], options=["甲", "乙"])), "甲")

    def test_judge(self):
        self.assertEqual(answer_text({"type": "judge", "answer": True}), "正确")
        self.assertEqual(answer_text({"type": "judge", "answer": False}), "错误")
        # 非布尔一律按「错误」处理（契约要求 judge 必须是布尔）
        self.assertEqual(answer_text({"type": "judge", "answer": "对"}), "错误")

    def test_fill_accepts_string_and_list(self):
        self.assertEqual(answer_text({"type": "fill", "answer": ["南昌", "1927"]}), "南昌")
        self.assertEqual(answer_text({"type": "fill", "answer": "南昌"}), "南昌")
        self.assertEqual(answer_text({"type": "fill", "answer": []}), "")
        self.assertEqual(answer_text({"type": "fill", "answer": None}), "")

    def test_short_accepts_string_and_list(self):
        self.assertEqual(answer_text({"type": "short", "answer": "要点全文"}), "要点全文")
        self.assertEqual(answer_text({"type": "short", "answer": ["甲", "乙"]}), "甲乙")
        self.assertEqual(answer_text({"type": "short", "answer": ""}), "")

    def test_never_raises_on_hostile_input(self):
        # 单一真相的价值就在于此：任何形态都不许抛异常。
        hostile = [
            {}, {"type": "single"}, {"type": "single", "answer": {}},
            {"type": "multi", "answer": {"A": 1}},
            {"type": "single", "answer": "A", "options": None},
            {"type": "single", "answer": "A", "options": "不是数组"},
            {"type": "judge"}, {"type": "fill"}, {"type": "short", "answer": [None]},
        ]
        for q in hostile:
            with self.subTest(q=q):
                self.assertIsInstance(answer_text(q), str)
                self.assertIsInstance(answer_display(q), str)
                self.assertIsInstance(letters_of(q), list)


class TestAnswerDisplay(unittest.TestCase):
    def test_single(self):
        self.assertEqual(answer_display(single("B")), "B、乙")

    def test_single_without_answer(self):
        self.assertEqual(answer_display(single(None)), "")

    def test_multi_lists_letters_and_texts(self):
        self.assertEqual(answer_display(multi(["A", "C"])), "A、C（甲；丙）")

    def test_multi_without_answer(self):
        self.assertEqual(answer_display(multi([])), "")

    def test_judge(self):
        self.assertEqual(answer_display({"type": "judge", "answer": True}), "正确")
        self.assertEqual(answer_display({"type": "judge", "answer": False}), "错误")

    def test_fill_and_short_join_lists(self):
        self.assertEqual(answer_display({"type": "fill", "answer": ["甲", "乙"]}), "甲；乙")
        self.assertEqual(answer_display({"type": "fill", "answer": "甲"}), "甲")
        self.assertEqual(answer_display({"type": "short", "answer": "略"}), "略")
        self.assertEqual(answer_display({"type": "short", "answer": []}), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
