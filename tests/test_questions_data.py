#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_questions_data.py — `data/questions.json` 的数据契约校验
=====================================================================

题库是**唯一随仓库发布的成品数据**，也是前端、解析脚本、质检脚本共同的输入。
它一旦违反契约，故障点会散布在 App 的五个题型渲染分支里，很难定位。
所以这里逐题校验 docs/02-data-contract.md 第 1 节的字段与答案规范。

说明：本文件按**现网真实契约**逐题校验，并与 `docs/02-data-contract.md` 保持一致；
契约文档中「约定但尚未写入」的顶层元数据，在这里被固化成显式断言，
避免有人照文档去读 `bank["counts"]`。改数据或改契约时，两边必须同时更新。
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.answer_text import LETTERS, answer_text

DATA = ROOT / "data" / "questions.json"

TYPES = ("single", "multi", "judge", "fill", "short")
CHOICE = ("single", "multi")
# 依据等级枚举（与 docs/02-data-contract.md 同步）
EXPLANATION_SRC = ("textbook", "manual", "bank", "template", "web")
SOURCES = ("真题", "模拟题", "提纲", "教程")
CHAPTERS = ("第一章中国国防", "第二章国家安全", "第三章军事思想",
            "第四章现代战争", "第五章信息化装备")

BANK = json.loads(DATA.read_text(encoding="utf-8"))
QUESTIONS = BANK["questions"]


def by_type(t):
    return [q for q in QUESTIONS if q["type"] == t]


def readme_type_counts() -> dict:
    """从 README 的「题库」表格里解析各题型数量。

    断言的是 **README 与数据是否一致** 这个真实不变量，而不是一组写死的数字 ——
    题库扩容时只要 README 一起更新，测试无需改动；两边不一致才会失败。
    """
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|", line)
        if not m:
            continue
        label, n = m.group(1).strip(), int(m.group(2))
        if label == "单选题":
            out["single"] = n
        elif "不定项" in label or "多选" in label:
            out["multi"] = n
        elif "判断" in label:
            out["judge"] = n
        elif "填空" in label:
            out["fill"] = n
        elif "简答" in label or "论述" in label:
            out["short"] = n
    return out


class TestTopLevelShape(unittest.TestCase):
    def test_file_is_utf8_json_object(self):
        self.assertIsInstance(BANK, dict)
        self.assertIsInstance(QUESTIONS, list)
        self.assertTrue(QUESTIONS)

    def test_top_level_shape_is_forward_compatible(self):
        """顶层必须含 questions；约定的四个元数据字段**缺失或存在都要能工作**。

        docs/02-data-contract.md 把 schema/generatedAt/counts/sources 记为
        「约定但尚未写入」，读取方必须容错（前端 isBank() 只要求 questions 非空）。
        若将来把元数据补上，这里顺带校验 counts 与实际题量一致 ——
        也就是说「补齐元数据」这个待修复项不会让测试变红，反而会被验证。
        """
        self.assertIn("questions", BANK)
        self.assertIsInstance(QUESTIONS, list)
        if "counts" in BANK:
            counts = BANK["counts"]
            got = Counter(q["type"] for q in QUESTIONS)
            self.assertEqual({k: v for k, v in counts.items() if k != "total"}, dict(got))
            self.assertEqual(counts.get("total"), len(QUESTIONS))


class TestIdentity(unittest.TestCase):
    def test_ids_unique(self):
        ids = [q["id"] for q in QUESTIONS]
        self.assertEqual(len(ids), len(set(ids)))
        dupes = [i for i, n in Counter(ids).items() if n > 1]
        self.assertEqual(dupes, [])

    def test_id_format_and_range(self):
        for q in QUESTIONS:
            with self.subTest(qid=q["id"]):
                self.assertRegex(q["id"], r"^q-\d{4}$")
        nums = sorted(int(q["id"][2:]) for q in QUESTIONS)
        self.assertEqual(nums[0], 1)           # 从 q-0001 起
        self.assertLessEqual(nums[-1], 9999)   # 4 位格式能表达的范围内
        # 不要求「连续无空洞」：删题会留下空号，那不是数据错误。


class TestEnumsAndCounts(unittest.TestCase):
    def test_type_enum(self):
        for q in QUESTIONS:
            with self.subTest(qid=q["id"]):
                self.assertIn(q["type"], TYPES)

    def test_source_enum(self):
        for q in QUESTIONS:
            with self.subTest(qid=q["id"]):
                self.assertIn(q["source"], SOURCES)

    def test_explanation_src_enum(self):
        actual = {q["explanationSrc"] for q in QUESTIONS}
        # 与 docs/02-data-contract.md 的枚举完全一致；新增取值必须同时更新文档与本测试。
        self.assertEqual(actual, set(EXPLANATION_SRC))
        for q in QUESTIONS:
            with self.subTest(qid=q["id"]):
                self.assertIn(q["explanationSrc"], EXPLANATION_SRC)

    def test_chapter_enum(self):
        for q in QUESTIONS:
            with self.subTest(qid=q["id"]):
                self.assertIn(q["chapter"], CHAPTERS)

    def test_type_counts_match_readme(self):
        published = readme_type_counts()
        self.assertEqual(set(published), set(TYPES),
                         "README 的题型数量表应覆盖全部 5 种题型")
        got = Counter(q["type"] for q in QUESTIONS)
        for typ in TYPES:
            with self.subTest(type=typ):
                self.assertEqual(got.get(typ, 0), published[typ],
                                 f"README 公布 {typ}={published[typ]}，实际 {got.get(typ, 0)}")
        self.assertEqual(len(QUESTIONS), sum(published.values()),
                         "README 各题型数量之和应等于题库总题数")

    def test_hard_flag_is_a_meaningful_split(self):
        # README 不公布具体数字，这里只保证标记既非「全选」也非「全不选」。
        hard = sum(1 for q in QUESTIONS if q["isHard"] is True)
        self.assertGreater(hard, 0)
        self.assertLess(hard, len(QUESTIONS))


class TestStemAndOptions(unittest.TestCase):
    def test_stem_is_non_empty_stripped_string(self):
        for q in QUESTIONS:
            with self.subTest(qid=q["id"]):
                self.assertIsInstance(q["stem"], str)
                self.assertTrue(q["stem"].strip())
                self.assertEqual(q["stem"], q["stem"].strip())

    def test_options_is_list_of_plain_text(self):
        for q in QUESTIONS:
            with self.subTest(qid=q["id"]):
                opts = q["options"]
                self.assertIsInstance(opts, list)
                for o in opts:
                    self.assertIsInstance(o, str)
                    self.assertTrue(o.strip())
                    # 契约：选项**不含** "A." 前缀
                    self.assertIsNone(re.match(r"^\s*[A-H][\.、]", o), o)

    def test_choice_questions_have_at_least_two_options(self):
        for q in by_type("single") + by_type("multi"):
            with self.subTest(qid=q["id"]):
                self.assertGreaterEqual(len(q["options"]), 2)
                self.assertLessEqual(len(q["options"]), len(LETTERS))

    def test_non_choice_questions_have_no_options(self):
        for t in ("judge", "fill", "short"):
            for q in by_type(t):
                with self.subTest(qid=q["id"]):
                    self.assertEqual(q["options"], [])


class TestAnswerShapes(unittest.TestCase):
    """契约第 1 节「答案规范」逐条落地。"""

    def test_single(self):
        for q in by_type("single"):
            with self.subTest(qid=q["id"]):
                a = q["answer"]
                self.assertIsInstance(a, str)
                self.assertIn(a, LETTERS)
                self.assertEqual(a, a.strip().upper())
                self.assertLess(LETTERS.index(a), len(q["options"]))

    def test_multi(self):
        for q in by_type("multi"):
            with self.subTest(qid=q["id"]):
                a = q["answer"]
                self.assertIsInstance(a, list)
                self.assertGreaterEqual(len(a), 2)
                for x in a:
                    self.assertIsInstance(x, str)
                    self.assertIn(x, LETTERS)
                self.assertEqual(a, sorted(set(a)), "必须升序且无重复")
                self.assertLess(LETTERS.index(max(a)), len(q["options"]))

    def test_judge(self):
        for q in by_type("judge"):
            with self.subTest(qid=q["id"]):
                self.assertIsInstance(q["answer"], bool)

    def test_fill(self):
        for q in by_type("fill"):
            with self.subTest(qid=q["id"]):
                a = q["answer"]
                self.assertIsInstance(a, list)
                self.assertTrue(a)
                for x in a:
                    self.assertIsInstance(x, str)
                    self.assertTrue(x.strip())

    def test_short(self):
        for q in by_type("short"):
            with self.subTest(qid=q["id"]):
                self.assertIsInstance(q["answer"], str)
                self.assertTrue(q["answer"].strip())

    def test_answer_text_never_raises_and_is_non_empty(self):
        # 全库 1531 题都必须能被「唯一答案读取实现」处理，且拿到非空文本。
        for q in QUESTIONS:
            with self.subTest(qid=q["id"]):
                txt = answer_text(q)
                self.assertIsInstance(txt, str)
                self.assertTrue(txt, "答案文本为空，说明答案字段与选项不匹配")


class TestExplanation(unittest.TestCase):
    def test_every_question_has_explanation(self):
        for q in QUESTIONS:
            with self.subTest(qid=q["id"]):
                self.assertIsInstance(q["explanation"], str)
                self.assertTrue(q["explanation"].strip())

    def test_explanation_ref_is_string(self):
        for q in QUESTIONS:
            with self.subTest(qid=q["id"]):
                self.assertIsInstance(q["explanationRef"], str)

    def test_section_is_string(self):
        for q in QUESTIONS:
            with self.subTest(qid=q["id"]):
                self.assertIsInstance(q["section"], str)
                self.assertTrue(q["section"])

    def test_explanation_parts_answer_matches_answer_field(self):
        """解析块「正确答案」行与判分用的 answer 字段必须一致。

        不一致时同一屏会显示两套答案（历史上实测出现 q-0539）。
        口径与 tools/verify_app.py 相同：对每个选项字母，检查它是否以
        「字母 + 分隔符」出现在解析文本里。
        """
        bad = []
        for q in QUESTIONS:
            if q["type"] not in CHOICE:
                continue
            pa = (q.get("explanationParts") or {}).get("answer") or ""
            if not pa:
                continue
            got = []
            for i in range(len(q["options"])):
                c = LETTERS[i]
                if re.search(re.escape(c) + r"\s*[、,，/；;（(]", pa) or pa.rstrip().endswith(c):
                    got.append(c)
            want = sorted(q["answer"] if isinstance(q["answer"], list)
                          else [str(q["answer"]).strip().upper()])
            if got and got != want:
                bad.append((q["id"], got, want))
        self.assertEqual(bad, [], f"{len(bad)} 题解析与答案不一致，前 5 个：{bad[:5]}")


class TestOptionalFields(unittest.TestCase):
    def test_answer_uncertain_is_bool_and_multi_only(self):
        for q in QUESTIONS:
            if "answerUncertain" not in q:
                continue
            with self.subTest(qid=q["id"]):
                self.assertIsInstance(q["answerUncertain"], bool)
                if q["answerUncertain"]:
                    self.assertEqual(q["type"], "multi")

    def test_distractor_why_keys_are_option_letters(self):
        for q in QUESTIONS:
            dw = q.get("distractorWhy")
            if dw is None:
                continue
            with self.subTest(qid=q["id"]):
                self.assertIsInstance(dw, dict)
                for k, v in dw.items():
                    self.assertIn(k, LETTERS[:len(q["options"])])
                    self.assertIsInstance(v, str)
                    self.assertTrue(v.strip())

    def test_keywords_is_list_of_strings(self):
        for q in QUESTIONS:
            with self.subTest(qid=q["id"]):
                self.assertIsInstance(q["keywords"], list)
                for k in q["keywords"]:
                    self.assertIsInstance(k, str)

    def test_is_hard_is_bool(self):
        for q in QUESTIONS:
            with self.subTest(qid=q["id"]):
                self.assertIsInstance(q["isHard"], bool)

    def test_explanation_parts_is_object_when_present(self):
        for q in QUESTIONS:
            parts = q.get("explanationParts")
            if parts is None:
                continue
            with self.subTest(qid=q["id"]):
                self.assertIsInstance(parts, dict)

class TestUserFacingText(unittest.TestCase):
    """用户可见文本的质量门槛（2026-10-09 内容修复后固化）。

    这三类问题都是「用户翻到某道题就会看到」的内容缺陷，而且改数据时极易回归：
      · 内部质检措辞 / 英文置信度评级泄漏到「提示」行；
      · 解析里出现「。年五四运动爆发」这种缺数字的年份（读不通、史实失真）；
      · 题干含异体字「⺠」（U+2EA0）。
    """

    JARGON = ("独立质检", "源答案串", "本题输入答案", "本处未擅改",
              "本卷一律按原卷", "答案内部亦不自洽")

    @staticmethod
    def user_text(q) -> str:
        pr = q.get("explanationParts") or {}
        return "\n".join([q.get("explanation") or "",
                          pr.get("reason") or "", pr.get("note") or ""])

    def test_no_internal_qa_jargon(self):
        bad = [(q["id"], w) for q in QUESTIONS for w in self.JARGON if w in self.user_text(q)]
        self.assertEqual(bad, [], f"内部质检措辞泄漏到用户可见文本：{bad[:5]}")

    def test_no_english_confidence_rating(self):
        bad = [q["id"] for q in QUESTIONS
               if re.search(r"\b(low|medium|high)\b", self.user_text(q))]
        self.assertEqual(bad, [], f"英文置信度评级泄漏：{bad[:5]}")

    def test_no_stripped_year(self):
        """解析里不得出现「年五四运动爆发」这类缺数字的年份。

        例外是**正常写法**：「每年9月」「次年2月」「四年一度」「一九九四年」「二○○一年」。
        """
        pat = re.compile(r"(?<![0-9])年(?=[0-9一二三四五六七八九十])")
        normal = re.compile(r"(每|次|四|同|九四)$")
        bad = []
        for q in QUESTIONS:
            t = self.user_text(q)
            for m in pat.finditer(t):
                pre = t[max(0, m.start() - 5):m.start()]
                if normal.search(pre) or re.search(r"[○〇]", pre):
                    continue
                bad.append((q["id"], t[max(0, m.start() - 12):m.end() + 8]))
        self.assertEqual(bad, [], f"解析中缺少年份数字：{bad[:5]}")

    def test_stem_and_options_have_no_compatibility_ideograph(self):
        bad = [q["id"] for q in QUESTIONS
               if "\u2ea0" in q["stem"] or any("\u2ea0" in o for o in q["options"])]
        self.assertEqual(bad, [], f"题干/选项含异体字「⺠」：{bad[:5]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
