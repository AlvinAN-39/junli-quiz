#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_reflection_questions.py — 剔除「依据句其实是教材思考题」的解析
================================================================

独立复核（`tools/verify_relevance.py`）发现的新问题类别：
语料里混入了教材的**思考题/复习题**（`军事思想有哪些作用?`、`总体国家安全观的内涵是什么?` …），
它们被当成"依据句"挂到了解析上。这类句子的特征很明显：

  * 以问号结尾；
  * 形如「X是什么」「X有哪些」「什么是X」「X包括哪些」。

它们**不是知识内容**，挂在解析上纯属误导。本脚本把它们从 `reason` 里剔除；
若剔除后没有依据可留，就整条撤下并标注「教材未收录直接对应内容」。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from explain_text import structure, render_text  # noqa: E402

BANK = ROOT / "data" / "questions.json"

# 「思考题」形态：问号结尾，或明显的提问句式
QFORM_RE = re.compile(
    r"[?？]\s*$"
    r"|^(什么|怎样|如何|为什么|试述|简述|论述|请说明|谈谈)"
    r"|(是什么|有哪些|包括哪些|是哪几|如何理解|怎么样)\s*[?？]?\s*$")


def is_reflection(sent: str) -> bool:
    s = (sent or "").strip()
    if not s:
        return False
    if s.endswith(("?", "？")):
        return True
    return bool(re.search(r"(是什么|有哪些|包括哪些|是哪几|如何理解)\s*[?？]?\s*$", s))


def main() -> int:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = bank["questions"]
    removed = kept_empty = 0
    samples = []
    for q in qs:
        p = q.get("explanationParts") or {}
        reason = (p.get("reason") or "").strip()
        if not reason or not is_reflection(reason):
            continue
        removed += 1
        p.pop("reason", None)
        if q.get("explanationSrc") == "textbook":
            q["explanationSrc"] = "template"
        q["explanationRef"] = ""
        p.pop("ref", None)
        note = p.get("note") or ""
        if "未收录" not in note and "人工" not in note:
            note = "教材中未收录与该题直接对应的内容，建议对照原卷核实"
        p["note"] = note
        q["explanationParts"] = p
        q["explanation"] = render_text(p)
        if len(samples) < 8:
            samples.append((q["id"], reason))

    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    left = sum(1 for q in qs if (q.get("explanationParts") or {}).get("reason"))
    still = sum(1 for q in qs if is_reflection((q.get("explanationParts") or {}).get("reason", "")))
    print("=" * 74)
    print("剔除「思考题当依据」的解析")
    print("=" * 74)
    print(f"  剔除条数        : {removed}")
    print(f"  剔除后仍有依据  : {left}")
    print(f"  残留思考题依据  : {still}（应为 0）")
    print()
    print("  样例（原依据其实是教材思考题）:")
    for qid, r in samples:
        print(f"    {qid}: {r[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
