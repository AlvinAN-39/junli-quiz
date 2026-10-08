#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_notes_clean.py — 把「说明」行彻底清理干净（幂等）
====================================================

前几轮补说明时反复追加，导致出现这类重复文本：

    教材中未收录与该题直接对应的内容，建议对照原卷核实，建议对照原卷核实。
    教材中未收录与该题直接对应的内容，建议对照原卷核实

本脚本的做法是**先清空所有已知措辞，再按规则重新拼一次**，因此可以反复运行而结果不变：

  1. 剥掉所有「未收录」类措辞（含重复与残缺变体）；
  2. 若原本没有依据句 → 补一句规范的「教材中未收录与该题直接对应的内容，建议对照原卷核实」；
  3. 判断题 → 前面加「本题由单选题派生，判断该表述是否与教材原文一致」；
  4. 简答题 → 若无说明则补「本题库收录的是原卷参考答案要点，见下方」；
  5. 人工校订的说明原样保留。
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
BANK = ROOT / "data" / "questions.json"

CANON = "教材中未收录与该题直接对应的内容，建议对照原卷核实"
JUDGE = "本题由单选题派生，判断该表述是否与教材原文一致"
SHORT = "本题库收录的是原卷参考答案要点，见下方"

# 所有出现过的「未收录」措辞，按长到短剥离
NOREASON_FORMS = [
    CANON,
    "本题库未收录教材中的直接出处，建议对照原卷核实",
    "本题库未收录教材中的直接出处",
    "教材中未收录与该题直接对应的内容",
    "建议对照原卷核实",
]


def strip_noreason(note: str) -> str:
    s = note or ""
    for _ in range(4):
        before = s
        for form in NOREASON_FORMS:
            s = s.replace(form, "")
        # 压掉剥离后残留的重复标点与空白
        s = re.sub(r"[。；，、]{2,}", "。", s)
        s = re.sub(r"\s{2,}", " ", s).strip(" 。；，、")
        if s == before:
            break
    return s


def main() -> int:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = bank["questions"]
    changed = 0
    for q in qs:
        parts = q.get("explanationParts") or {}
        note = (parts.get("note") or "").strip()
        has_reason = bool((parts.get("reason") or "").strip())
        manual = q.get("explanationSrc") == "manual" or "人工" in note

        tail = strip_noreason(note)
        pieces: list[str] = []
        if manual:
            if tail:
                pieces.append(tail)          # 人工校订说明原样保留
        else:
            if not has_reason:
                pieces.append(CANON)
            if q["type"] == "judge":
                pieces.insert(0, JUDGE)
            elif q["type"] == "short" and tail:
                pieces.append(tail)
            elif tail:
                pieces.append(tail)

        new_note = "。".join(p for p in pieces if p).strip("。")
        if new_note != note:
            changed += 1
        if new_note:
            parts["note"] = new_note
        else:
            parts.pop("note", None)

        q["explanationParts"] = parts
        out = []
        if parts.get("answer"):
            out.append("正确答案：" + parts["answer"])
        if parts.get("reason"):
            out.append(parts["reason"])
        if parts.get("note"):
            out.append("提示：" + parts["note"])
        if parts.get("ref"):
            out.append("依据：" + parts["ref"])
        q["explanation"] = "\n".join(out)

    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")

    dup = sum(1 for q in qs if ((q.get("explanationParts") or {}).get("note") or "").count("未收录") > 1)
    bad = sum(1 for q in qs if "核实，建议对照原卷核实" in ((q.get("explanationParts") or {}).get("note") or ""))
    judge_ok = sum(1 for q in qs if q["type"] == "judge"
                   and "派生" in ((q.get("explanationParts") or {}).get("note") or ""))
    judge_tot = sum(1 for q in qs if q["type"] == "judge")
    blank = sum(1 for q in qs
                if not any((v or "").strip() for v in (q.get("explanationParts") or {}).values()))
    print("=" * 74)
    print("说明行清理（幂等）")
    print("=" * 74)
    print(f"  改动条数          : {changed}")
    print(f"  说明重复的题      : {dup}  (应为 0)")
    print(f"  含残缺重复措辞的题: {bad}  (应为 0)")
    print(f"  判断题派生说明    : {judge_ok}/{judge_tot}")
    print(f"  完全空白的题      : {blank}  (应为 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
