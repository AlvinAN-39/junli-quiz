#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_sources_compile.py — 全仓源码语法体检
====================================================

仓库里有 60+ 个 `tools/*.py` 脚本，没有 lint/CI。任何一个脚本被改出语法错误，
都要等到「有人真的跑到它」才暴露 —— 而这些脚本大多是一次性数据加工，
出问题时数据往往已经被写坏。

这里只做**编译**（不 import，避免执行模块级副作用），外加对 JS 做 `node --check`。
成本近乎为零，却能把整仓语法错误挡在提交之前。
"""

from __future__ import annotations

import ast
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NODE = shutil.which("node")


def python_sources():
    seen = []
    for pattern in ("tools/*.py", "tests/*.py", "*.py"):
        for p in sorted(ROOT.glob(pattern)):
            if p.is_file() and p not in seen:
                seen.append(p)
    return seen


class TestPythonSourcesCompile(unittest.TestCase):
    def test_every_python_source_compiles(self):
        with tempfile.TemporaryDirectory(prefix="junli-pyc-") as tmp:
            bad = []
            for src in python_sources():
                out = Path(tmp) / (src.stem + ".pyc")
                try:
                    py_compile.compile(str(src), cfile=str(out), doraise=True)
                except py_compile.PyCompileError as e:
                    bad.append(f"{src.relative_to(ROOT)}: {e.msg.strip().splitlines()[-1]}")
            self.assertEqual(bad, [], "存在语法错误的文件：\n" + "\n".join(bad))

    def test_sources_are_utf8(self):
        for src in python_sources():
            with self.subTest(src=str(src.relative_to(ROOT))):
                src.read_text(encoding="utf-8")   # 解码失败即抛错

    def test_at_least_the_known_tools_exist(self):
        names = {p.name for p in ROOT.glob("tools/*.py")}
        for expected in ("bundle.py", "answer_text.py", "qr_svg.py",
                         "parse_questions.py", "verify_app.py"):
            with self.subTest(tool=expected):
                self.assertIn(expected, names)

    def test_tools_have_no_third_party_imports(self):
        """「零第三方依赖」是项目的对外承诺，用导入清单把它钉住。

        只做静态解析（不 import，避免执行模块级副作用），允许：
        标准库、`tools/` 内部的兄弟模块、以及 `tests` 包自身。
        """
        stdlib = set(sys.stdlib_module_names)
        local = {p.stem for p in ROOT.glob("tools/*.py")} | {"tools", "tests"}
        offenders = []
        for src in sorted(ROOT.glob("tools/*.py")):
            tree = ast.parse(src.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    mods = [node.module.split(".")[0]]
                for m in mods:
                    if m not in stdlib and m not in local:
                        offenders.append(f"{src.name}: {m}")
        self.assertEqual(offenders, [],
                         "tools/ 出现了第三方依赖：\n" + "\n".join(offenders))


@unittest.skipIf(NODE is None, "未找到 node，跳过 JS 语法检查")
class TestJavaScriptSyntax(unittest.TestCase):
    def test_app_js_and_sw_js_parse(self):
        for name in ("app.js", "sw.js"):
            src = ROOT / "app" / name
            with self.subTest(name=name):
                r = subprocess.run([NODE, "--check", str(src)],
                                   capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=120)
                self.assertEqual(r.returncode, 0, (r.stdout or "") + (r.stderr or ""))

    def test_test_harness_parses(self):
        harness = ROOT / "tests" / "js" / "app_contract.mjs"
        r = subprocess.run([NODE, "--check", str(harness)],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(r.returncode, 0, (r.stdout or "") + (r.stderr or ""))

    def test_app_js_has_no_esm_syntax(self):
        # bundle.py 靠字符串内联，ESM 会让单文件版直接报错
        js = (ROOT / "app" / "app.js").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^\s*(import|export)\s", js, re.M))


if __name__ == "__main__":
    unittest.main(verbosity=2)
