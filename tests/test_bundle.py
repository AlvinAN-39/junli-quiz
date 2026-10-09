#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_bundle.py — `tools/bundle.py`（打包器）的测试
============================================================

打包产物是用户唯一真正拿到手的东西：单文件版必须**零外部请求**、
题库必须**内联**、PWA 版必须能注册 Service Worker。这些性质目前只由
`tools/verify_app.py` 在手动运行时检查，且它依赖已存在的 `dist/`
（`.gitignore` 忽略，CI/新克隆里没有）。这里把同样的检查变成**可自动运行的测试**：
在临时目录里真实跑一遍 `build_single_file` / `build_web` / `build_deploy_zip`。
"""

from __future__ import annotations

import copy
import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import bundle

REAL_BANK = json.loads((ROOT / "data" / "questions.json").read_text(encoding="utf-8"))
N_REAL = len(REAL_BANK["questions"])

# 前端确实会读取、且**每题都有**的字段（见 app.js hydrate()/explainBody()/explainSrcLine()）
REQUIRED_FRONTEND_FIELDS = ("id", "type", "stem", "options", "answer", "explanation",
                            "explanationSrc", "explanationRef", "source", "chapter",
                            "section", "keyConcept", "keywords",
                            "explanationParts", "isHard", "subsection", "sectionName")
# 只在部分题上出现（hydrate 会把缺失的归一化为 {}），但一旦存在就不能被精简掉
OPTIONAL_FRONTEND_FIELDS = ("distractorWhy",)


class TestSafeInline(unittest.TestCase):
    def test_escapes_script_close_tag(self):
        self.assertEqual(bundle.safe_inline("a</script>b"), "a<\\/script>b")

    def test_escapes_html_comment_open(self):
        # 实现把 `<!--` 换成 `<\!--`：序列 `<!--` 不再出现，注释不会被打开。
        self.assertEqual(bundle.safe_inline("a<!--b"), "a<\\!--b")

    def test_leaves_normal_code_untouched(self):
        src = "var x = 1 < 2 && 3 > 2; // 注释"
        self.assertEqual(bundle.safe_inline(src), src)

    def test_real_app_js_has_no_script_close_tag(self):
        js = (ROOT / "app" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("</script", js.lower())


class TestStripDebugFields(unittest.TestCase):
    @staticmethod
    def crafted():
        return {
            "questions": [
                {
                    "id": "q-0001", "type": "single", "stem": "s", "options": ["a", "b"],
                    "answer": "A", "explanation": "e", "explanationRef": "教材《x》",
                    "raw": "原始片段", "webSourceUrl": "https://e.com",
                    "relatedSection": "1.1", "lawCitationIssue": "x",
                    "lawCitationStatus": "ok", "answerUncertain": False,
                    "explanationParts": {"answer": "A、a", "reason": "为什么", "ref": "教材《x》"},
                },
                {
                    "id": "q-0002", "type": "multi", "stem": "s", "options": ["a", "b"],
                    "answer": ["A"], "explanation": "e", "explanationRef": "教材《y》",
                    "explanationParts": {"answer": "A、a", "reason": "为什么", "ref": "教材《不同》"},
                },
                {"id": "q-0003", "type": "judge", "stem": "s", "options": [],
                 "answer": True, "explanation": "e", "explanationParts": "不是对象"},
                {"id": "q-0004", "type": "short", "stem": "s", "options": [],
                 "answer": "a", "explanation": "e"},
            ]
        }

    def test_removes_only_zero_read_fields(self):
        bank, removed = bundle.strip_debug_fields(self.crafted())
        q1, q2, q3, q4 = bank["questions"]
        for field in ("raw", "webSourceUrl", "relatedSection",
                      "lawCitationIssue", "lawCitationStatus", "answerUncertain"):
            self.assertNotIn(field, q1)
        self.assertEqual(removed["raw"], 1)
        self.assertEqual(removed["webSourceUrl"], 1)
        self.assertEqual(removed["relatedSection"], 1)
        self.assertEqual(removed["lawCitationIssue"], 1)
        self.assertEqual(removed["lawCitationStatus"], 1)
        self.assertEqual(removed["answerUncertain"], 1)

    def test_keeps_reason_which_frontend_renders(self):
        bank, _ = bundle.strip_debug_fields(self.crafted())
        self.assertEqual(bank["questions"][0]["explanationParts"]["reason"], "为什么")
        self.assertEqual(bank["questions"][1]["explanationParts"]["reason"], "为什么")

    def test_drops_parts_ref_only_when_redundant(self):
        bank, removed = bundle.strip_debug_fields(self.crafted())
        # q-0001：parts.ref == explanationRef → 删
        self.assertNotIn("ref", bank["questions"][0]["explanationParts"])
        # q-0002：两者不同 → 保留
        self.assertEqual(bank["questions"][1]["explanationParts"]["ref"], "教材《不同》")
        self.assertEqual(removed["parts.ref"], 1)

    def test_tolerates_non_dict_parts_and_missing_fields(self):
        bank, removed = bundle.strip_debug_fields(self.crafted())
        self.assertEqual(bank["questions"][2]["explanationParts"], "不是对象")
        self.assertEqual(removed["raw"], 1)  # q-0004 无 raw，不计数

    def test_mutates_in_place_and_returns_same_object(self):
        bank = self.crafted()
        out, _ = bundle.strip_debug_fields(bank)
        self.assertIs(out, bank)


class TestBuildStamp(unittest.TestCase):
    def test_version_format(self):
        stamp = bundle.build_stamp()
        self.assertRegex(stamp["v"], r"^\d{4}\.\d{2}\.\d{2}-\d{4}$")
        self.assertRegex(stamp["iso"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

    def test_keys_are_stable(self):
        self.assertEqual(set(bundle.build_stamp().keys()), {"v", "iso"})


class TestReferenceScript(unittest.TestCase):
    def test_json_is_substituted(self):
        src = bundle.reference_script()
        self.assertNotIn("__REFERENCE_JSON__", src)
        self.assertIn(bundle.REFERENCE["isbn"], src)
        self.assertIn(bundle.REFERENCE["title"], src)
        self.assertIn("ref-book-card", src)

    def test_payload_is_parseable_json(self):
        src = bundle.reference_script()
        start = src.index("var REF = ") + len("var REF = ")
        end = src.index(";\n", start)
        self.assertEqual(json.loads(src[start:end]), bundle.REFERENCE)

    def test_reference_metadata_matches_docs(self):
        ref = bundle.REFERENCE
        self.assertEqual(ref["isbn"], "978-7-306-07893-3")
        self.assertEqual(ref["press"], "中山大学出版社")
        self.assertTrue(ref["use"])


class TestBuildEndToEnd(unittest.TestCase):
    """在临时目录里真实打包一次，然后检查产物。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="junli-bundle-")
        cls.tmp = Path(cls._tmp.name)
        cls._orig_dist = bundle.DIST
        bundle.DIST = cls.tmp
        try:
            cls.single = bundle.build_single_file(copy.deepcopy(REAL_BANK))
            cls.index = bundle.build_web(copy.deepcopy(REAL_BANK))
            cls.zip_path = bundle.build_deploy_zip()
        finally:
            bundle.DIST = cls._orig_dist
        cls.html = cls.single.read_text(encoding="utf-8")
        cls.web_html = cls.index.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # ---- 单文件版 ----
    def test_single_file_exists(self):
        self.assertTrue(self.single.exists())
        self.assertEqual(self.single.name, "军理刷题.html")

    def test_single_file_has_no_external_resources(self):
        self.assertFalse(re.search(r'(?:src|href)\s*=\s*["\'](?:https?:)?//', self.html))
        self.assertFalse(re.search(r"<script[^>]+src=", self.html))
        self.assertFalse(re.search(r"<link[^>]+stylesheet", self.html))

    def test_single_file_inlines_style_and_bank(self):
        self.assertIn("<style", self.html)
        self.assertIn("window.__QUESTION_BANK__", self.html)
        self.assertIn("window.__BUILD__", self.html)

    def test_single_file_has_reference_card_script(self):
        self.assertIn("ref-book-card", self.html)
        self.assertIn(bundle.REFERENCE["isbn"], self.html)

    def test_embedded_bank_is_parseable_and_complete(self):
        m = re.search(r"window\.__QUESTION_BANK__\s*=\s*(\{.*?\});\s*\n</script>",
                      self.html, re.S)
        self.assertIsNotNone(m, "未能从产物中提取内联题库")
        bank = json.loads(m.group(1))
        self.assertEqual(len(bank["questions"]), N_REAL)

    def test_embedded_bank_is_stripped_but_keeps_frontend_fields(self):
        m = re.search(r"window\.__QUESTION_BANK__\s*=\s*(\{.*?\});\s*\n</script>",
                      self.html, re.S)
        bank = json.loads(m.group(1))
        for q in bank["questions"]:
            for field in REQUIRED_FRONTEND_FIELDS:
                self.assertIn(field, q, f"{q['id']} 缺少前端读取的字段 {field}")
            self.assertNotIn("raw", q)
            self.assertNotIn("webSourceUrl", q)
            for field in OPTIONAL_FRONTEND_FIELDS:
                if field in q:
                    self.assertIsInstance(q[field], dict, f"{q['id']}.{field}")
        # explanationParts.reason 必须保留（前端「为什么」一行靠它渲染）
        with_reason = sum(1 for q in bank["questions"]
                          if (q.get("explanationParts") or {}).get("reason"))
        self.assertGreater(with_reason, 0)
        # 可选字段确实存在（否则上面的检查等于没跑）
        self.assertGreater(sum(1 for q in bank["questions"] if "distractorWhy" in q), 0)

    def test_build_stamp_is_injected(self):
        m = re.search(r"window\.__BUILD__\s*=\s*(\{[^}]*\});", self.html)
        self.assertIsNotNone(m)
        stamp = json.loads(m.group(1))
        self.assertRegex(stamp["v"], r"^\d{4}\.\d{2}\.\d{2}-\d{4}$")

    # ---- PWA 版 ----
    def test_web_index_exists(self):
        self.assertTrue(self.index.exists())
        self.assertEqual(self.index.name, "index.html")

    def test_web_index_has_manifest_and_service_worker(self):
        self.assertIn("manifest.webmanifest", self.web_html)
        self.assertIn("serviceWorker", self.web_html)
        self.assertIn("window.__QUESTION_BANK__", self.web_html)

    def test_web_assets_copied(self):
        web = self.index.parent
        for name in ("app.css", "app.js", "sw.js", "manifest.webmanifest",
                     "icons/icon.svg"):
            with self.subTest(name=name):
                self.assertTrue((web / name).exists(), f"缺少 {name}")

    def test_web_inlined_bank_matches_source(self):
        """PWA 版不再放 data/questions.json，题库以**内联**为准 —— 这里核对内联内容。"""
        m = re.search(r"window\.__QUESTION_BANK__\s*=\s*(\{.*?\});\s*\n</script>",
                      self.web_html, re.S)
        self.assertIsNotNone(m, "PWA 版未内联题库")
        bank = json.loads(m.group(1))
        self.assertEqual(len(bank["questions"]), N_REAL)
        self.assertEqual({q["id"] for q in bank["questions"]},
                         {q["id"] for q in REAL_BANK["questions"]})
        self.assertNotIn("raw", bank["questions"][0])
        self.assertIn("explanation", bank["questions"][0])

    def test_web_has_no_dead_data_dir(self):
        """部署目录不放 data/：题库与提纲都已内联，这两个文件永远不会被请求。"""
        self.assertFalse((self.index.parent / "data").exists())

    def test_web_manifest_is_valid_json(self):
        mf = json.loads((self.index.parent / "manifest.webmanifest")
                        .read_text(encoding="utf-8"))
        self.assertTrue(mf.get("name"))
        self.assertTrue(mf.get("start_url"))

    # ---- 部署包 ----
    def test_deploy_zip_is_flat_and_complete(self):
        self.assertTrue(self.zip_path.exists())
        with zipfile.ZipFile(self.zip_path) as z:
            names = z.namelist()
        self.assertIn("index.html", names, "zip 必须是扁平结构（部署平台要求）")
        # 题库/提纲已内联，data/ 属于白占体积（实测约 45%），不应进部署包
        self.assertNotIn("data/questions.json", names)
        self.assertIn("app.js", names)
        self.assertIn("manifest.webmanifest", names)
        self.assertFalse(any(n.startswith("web/") for n in names))


if __name__ == "__main__":
    unittest.main(verbosity=2)
