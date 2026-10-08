#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_perf_baseline.py — 构造「性能改动对照产物」（用于前后对比取证）
======================================================================

目的：证明「统计缓存 / 徽章合并 / 多选差量更新」各省了多少。
做法：拿当前单文件产物，把 app.js 里**三个性能开关**的初值 `true` 改成 `false`
      （开关语义见 app.js 的 PERF 段），其余完全一致，因此差异可归因于这三处。

为什么用开关而不是字符串替换代码：替换代码会制造不可达分支（死代码），
也不利于事后复核；同源代码 + 单点开关更严谨，且开关本身写明用途、对生产无影响。

安全性：输出 `dist/_perf-baseline.html`（临时对照物，验收后清理）；
        每处替换断言「命中且仅命中一次」，否则中止，不产出半成品。

用法：
    python tools/build_perf_baseline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dist" / "军理刷题.html"
OUT = ROOT / "dist" / "_perf-baseline.html"

SWITCHES = [
    ("PERF_CACHE_DERIVE", "统计结果缓存（derive 命中缓存）"),
    ("PERF_LEAN_BADGES", "徽章合并（一次 derive 取代 wrongIds+favIds+derive）"),
    ("PERF_DIFF_MULTI", "多选差量更新（不重建整卡）"),
]


def main() -> int:
    if not SRC.exists():
        print("缺少产物：%s" % SRC, file=sys.stderr)
        return 1
    html = SRC.read_text(encoding="utf-8")
    for name, desc in SWITCHES:
        old = "var %s = true;" % name
        new = "var %s = false;" % name
        n = html.count(old)
        if n != 1:
            print("[FAIL] 开关 %s 命中 %d 次（应为 1），中止" % (name, n), file=sys.stderr)
            return 2
        html = html.replace(old, new, 1)
        print("已关闭：%s（%s）" % (desc, name))
    OUT.write_text(html, encoding="utf-8")
    print("对照产物 → %s（%.0f KB）" % (OUT, OUT.stat().st_size / 1024))
    print("与正式产物唯一的差别是上述三个开关；验收后请清理。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
