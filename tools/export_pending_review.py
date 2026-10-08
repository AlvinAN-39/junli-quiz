#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_pending_review.py — 导出「需要联网核查」的题目清单
==========================================================

背景：`tools/audit_textbook.py` 已对 894 道客观题做了三份本地语料
（教材 / 历年真题 / 模拟题）的全量覆盖比对，其中一部分题在三份语料里
**找不到任何原句**（verdict = no_corpus_evidence）。这类题按用户口径
需要联网核查，本脚本把它们导出成干净的 Markdown 清单交给联网核查者。

输出：`qa/pending-review/part-XX.md`，每批 ≤N 题，每题含：
    题号 / 题型 / 题干 / 全部选项（标出当前答案）/ 当前答案字母

注意：正文一律剔除控制字符（PDF 抽取语料含 NUL，会让下游读取工具
把文件误判为二进制而拒读 —— 本轮已实测踩过）。

用法：
    python tools/export_pending_review.py            # 默认 50 题一批
    python tools/export_pending_review.py --per 40
    python tools/export_pending_review.py --kind judge   # 只导判断题
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "qa" / "textbook-audit.json"
OUTDIR = ROOT / "qa" / "pending-review"
TYPE_LABEL = {"single": "单选", "multi": "多选", "judge": "判断"}


def clean(s: str) -> str:
    return "".join(ch for ch in str(s) if ch == "\n" or ch >= " ")


def main() -> int:
    per = 50
    if "--per" in sys.argv:
        try:
            per = int(sys.argv[sys.argv.index("--per") + 1])
        except Exception:
            per = 50
    kind = None
    if "--kind" in sys.argv:
        kind = sys.argv[sys.argv.index("--kind") + 1]

    data = json.loads(AUDIT.read_text(encoding="utf-8"))
    items = [d for d in data["details"] if d["verdict"] == "no_corpus_evidence"]
    if kind:
        items = [d for d in items if d["type"] == kind]
    items.sort(key=lambda d: d["id"])

    OUTDIR.mkdir(parents=True, exist_ok=True)
    for old in OUTDIR.glob("part-*.md"):
        old.unlink()

    files = []
    for i in range(0, len(items), per):
        chunk = items[i:i + per]
        lines = ["# 待联网核查清单 第 %d 批（%d 题）" % (i // per + 1, len(chunk)), "",
                 "> 这批题在三份本地语料（教材 / 历年真题 / 模拟题）中查不到原句。",
                 "> 核查要求：联网检索该题考点的权威表述（教材原文、国防部/教育部网站、",
                 "> 高校军事理论课件、权威辅导书），判断**当前答案是否正确**。", "",
                 "> 结论只用三种：`一致`（找到权威依据支持当前答案）、",
                 "> `可疑`（找到明确依据反对当前答案，须附原文与链接）、",
                 "> `无法判定`（查不到权威依据，如实写查不到，禁止编造）。", ""]
        for d in chunk:
            lines.append("## %s ｜ %s ｜ 当前答案：%s" % (
                d["id"], TYPE_LABEL.get(d["type"], d["type"]),
                "".join(d["answer"]) or "—"))
            lines.append("题干：%s" % clean(d["stem"]))
            for j, o in enumerate(d["options"]):
                L = chr(65 + j)
                lines.append("  - %s. %s%s" % (L, clean(o), "  ★当前答案" if L in d["answer"] else ""))
            lines.append("")
        p = OUTDIR / ("part-%02d.md" % (i // per + 1))
        p.write_text("\n".join(lines), encoding="utf-8")
        files.append((p, len(chunk)))

    print("导出待联网核查清单：%d 题，%d 个文件（每批 ≤%d 题）" % (len(items), len(files), per))
    for p, n in files:
        raw = p.read_text(encoding="utf-8")
        print("  %-44s %2d 题  %5.1f KB  NUL=%d" % (p.name, n, p.stat().st_size / 1024, raw.count("\x00")))
    print("目录：%s" % OUTDIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
