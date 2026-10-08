#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_notes.py — 补回每条解析都应有的「说明」行
============================================

逐轮修正依据时，有些题的 `note` 被覆盖或丢失，导致解析只剩一个光秃秃的答案。
本脚本按题型补齐必要的说明，确保**任何一道题都不会只有答案没有解释**：

  * 判断题（150 道，全部由单选题派生）→ 说明它由哪道题派生、该怎么理解；
  * 简答题 → 说明参考答案见下方；
  * 撤下依据的题 → 说明教材未收录直接对应内容（已有则保留）；
  * 人工校订过的题 → 保留校订说明。
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
from explain_text import render_text  # noqa: E402

BANK = ROOT / "data" / "questions.json"

JUDGE_NOTE = "本题由单选题派生，判断该表述是否与教材原文一致"
SHORT_NOTE = "本题库收录的是原卷参考答案要点，见下方"
NOREASON_NOTE = "教材中未收录与该题直接对应的内容，建议对照原卷核实"


def main() -> int:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = bank["questions"]
    fixed = 0
    for q in qs:
        p = q.get("explanationParts") or {}
        note = (p.get("note") or "").strip()
        has_reason = bool((p.get("reason") or "").strip())
        manual = q.get("explanationSrc") == "manual" or "人工" in note

        # 判断题：始终补上「由单选题派生」的说明（它决定了怎么理解这道判断题）
        if q["type"] == "judge":
            if "派生" not in note:
                base = JUDGE_NOTE
                if not has_reason and NOREASON_NOTE not in note:
                    base += "。" + NOREASON_NOTE
                # 去掉已重复出现的「未收录」说明，避免拼接出两遍
                tail = note.replace(NOREASON_NOTE, "").strip(" 。")
                p["note"] = (base + ("。" + tail if tail else "")).strip("。")
                fixed += 1
        elif q["type"] == "short" and not note and not has_reason:
            p["note"] = SHORT_NOTE
            fixed += 1
        elif not has_reason and not note and not manual:
            p["note"] = NOREASON_NOTE
            fixed += 1

        if p:
            q["explanationParts"] = p
            q["explanation"] = render_text(p)

    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")

    blank = [q["id"] for q in qs
             if not any((v or "").strip() for v in (q.get("explanationParts") or {}).values())]
    judge_ok = sum(1 for q in qs if q["type"] == "judge"
                   and "派生" in ((q.get("explanationParts") or {}).get("note") or ""))
    judge_tot = sum(1 for q in qs if q["type"] == "judge")
    n_note = sum(1 for q in qs if (q.get("explanationParts") or {}).get("note"))
    print("=" * 74)
    print("说明行补齐")
    print("=" * 74)
    print(f"  补齐条数            : {fixed}")
    print(f"  判断题含派生说明    : {judge_ok}/{judge_tot}  (应为 150/150)")
    print(f"  有说明行的题        : {n_note}/{len(qs)}")
    print(f"  完全空白的题        : {len(blank)}  (应为 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
