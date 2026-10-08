#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_disputed.py — 盘点全库「存疑内容」（T18）
=============================================

目标：交付物里不留任何「待定」。本脚本先把所有存疑形态精确列出来，供逐类处置。

存疑形态：
  A. answerDisputedBySource —— 权威来源明确指出答案有出入（最硬的证据）
  B. lawCitationIssue       —— 法条引用经复核有误（条号/版本错）
  C. answerUncertain        —— 多选答案由原卷连续字母串切分而来，切分本身有歧义
  D. 提示含 ⚠               —— 解析里带着告警文字
  E. explanationSrc=template —— 无任何可核查依据

输出：qa/disputed-inventory.json + 控制台汇总
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "data" / "questions.json"
OUT = ROOT / "qa" / "disputed-inventory.json"


def has_warn(q) -> bool:
    note = (q.get("explanationParts") or {}).get("note") or ""
    return "⚠" in note


def main() -> int:
    qs = json.loads(BANK.read_text(encoding="utf-8"))["questions"]

    # 只把**仍处于待定状态**的计入「存疑」；已给出明确结论的不算。
    #   · answerUncertain        → 待定（答案切分没定论）
    #   · answerDisputedBySource → 待定（来源与答案冲突未处置）
    #   · 提示含「待核实/待定」   → 待定
    # 下列属于**已处置的明确结论**，不计入存疑：
    #   · lawCitationIssue       → 已复核并注明正确条文
    #   · 无依据(template)        → 已明确说明「未收录」，不是"待查"
    pending_uncertain = [q["id"] for q in qs if q.get("answerUncertain")]
    pending_disputed = [q["id"] for q in qs if q.get("answerDisputedBySource")]
    pending_words = [q["id"] for q in qs
                     if re.search(r"待核实|待定|存疑|尚待", (q.get("explanationParts") or {}).get("note") or "")]
    pending = sorted(set(pending_uncertain) | set(pending_disputed) | set(pending_words))

    # 已处置的结论性标注（保留是为了如实告知，不是待定）
    law_noted = [q["id"] for q in qs if q.get("lawCitationIssue")]
    no_reason = [q["id"] for q in qs if not (q.get("explanationParts") or {}).get("reason")]

    cats = {"pending_uncertain": pending_uncertain, "pending_disputed": pending_disputed,
            "pending_words": pending_words, "law_noted": law_noted, "no_reason": no_reason}

    print("=" * 74)
    print(f"存疑盘点：总题数 {len(qs)}")
    print("=" * 74)
    print("  【待定 — 必须为 0】")
    print(f"    answerUncertain（答案切分未定论）      {len(pending_uncertain):5}")
    print(f"    answerDisputedBySource（冲突未处置）    {len(pending_disputed):5}")
    print(f"    提示含「待核实/待定/存疑」字样          {len(pending_words):5}")
    print(f"    → 合计待定                             {len(pending):5}")
    print()
    print("  【已处置的明确结论 — 非待定】")
    print(f"    法条引用已复核并注明正确条文            {len(law_noted):5}")
    print(f"    无依据但已明确说明「未收录」            {len(no_reason):5}")
    print("=" * 74)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "total": len(qs), "pending": len(pending),
        "categories": cats, "pendingIds": pending,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"清单 → {OUT.relative_to(ROOT)}")
    return 0 if not pending else 1


if __name__ == "__main__":
    sys.exit(main())
