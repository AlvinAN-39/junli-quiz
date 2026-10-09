#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_app_js.py — 前端 app/app.js 核心逻辑契约（Node 沙箱）
==================================================================

真正的浏览器 E2E 需要 Playwright/Puppeteer，而本项目坚持**零第三方依赖**，
`tools/verify_app.py` 因此把浏览器测试列为可选。这里退一步：
用 Node + 最小 DOM 桩执行真实的 app.js（见 `tests/js/app_contract.mjs`），
覆盖与数据契约直接相关、不依赖布局与事件的部分。

Node 不存在时整模块 skip（而不是失败）—— 仓库的构建产物不依赖 Node。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HARNESS = ROOT / "tests" / "js" / "app_contract.mjs"
NODE = shutil.which("node")

# 至少要跑到的检查项（防止脚本被改坏后「零检查也算通过」）
MIN_CHECKS = 12


@unittest.skipIf(NODE is None, "未找到 node，跳过 app.js 沙箱测试")
class TestAppJsContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc = subprocess.run(
            [NODE, str(HARNESS)],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300,
        )

    def _report(self):
        try:
            return json.loads(self.proc.stdout)
        except json.JSONDecodeError as e:
            self.fail(f"沙箱未输出合法 JSON（exit={self.proc.returncode}）：{e}\n"
                      f"stdout:\n{self.proc.stdout[:2000]}\nstderr:\n{self.proc.stderr[:2000]}")

    def test_harness_exits_zero(self):
        report = self._report()
        failed = [c for c in report.get("checks", []) if not c.get("ok")]
        detail = "\n".join(f"  · {c['name']} — {c['detail']}" for c in failed)
        self.assertEqual(self.proc.returncode, 0,
                         f"app.js 沙箱检查失败：\n{detail}\n{self.proc.stderr[:1000]}")

    def test_harness_actually_ran_checks(self):
        report = self._report()
        checks = report.get("checks", [])
        self.assertGreaterEqual(len(checks), MIN_CHECKS,
                                f"只跑了 {len(checks)} 项检查，疑似脚本被改坏")

    def test_every_named_check_is_present(self):
        report = self._report()
        names = {c["name"] for c in report.get("checks", [])}
        for expected in (
            "app.js 可执行（无异常）",
            "window.__JLX__ 已暴露",
            "normalizeAnswer 契约用例",
            "全量题库 normalizeAnswer 形态正确",
            "State.questions 吸收全量题目",
            "MOCK_BANK 覆盖 5 种题型",
        ):
            with self.subTest(check=expected):
                self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
