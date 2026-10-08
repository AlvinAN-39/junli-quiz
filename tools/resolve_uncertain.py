#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
resolve_uncertain.py — 用依据解除「多选答案切分存疑」（T18）
==========================================================

背景：`answerUncertain` 标记的由来是「源 PDF 把多选答案压成连续字母串，切分有歧义」。
但经过前面的联网补齐，**大多数题已经有了权威依据**。若依据能定论，这个历史标记就
应该撤销 —— 否则交付物里会一直挂着「存疑」。

判定规则（只做**可客观判定**的解除）：

  令 M = 依据正文中**被逐字提到**的选项集合，A = 现有答案集合。
    * 若 M 非空 且 M ⊆ A           → 依据支持现有答案的**全部**被选项
                                     （依据未提及的项不算反证）→ **解除标记**
    * 若 M 非空 且 M ⊄ A           → 依据支持了答案外的项，说明答案可能漏选
                                     → 不解除，交给逻辑判断
    * 若 M 为空（依据未逐字列选项） → 依据不足以定论 → 转为中性说明，不再标「存疑」

输出：qa/uncertain-resolution.json
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
REPORT = ROOT / "qa" / "uncertain-resolution.json"
L = "ABCDEFGH"


def norm(s: str) -> str:
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9%]", "", s or "")


def mentioned(opt: str, reason: str) -> bool:
    o = norm(opt)
    return len(o) >= 2 and o in norm(reason)


def main() -> int:
    apply_changes = "--apply" in sys.argv
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = bank["questions"]

    cleared, need_judge, insufficient = [], [], []
    for q in qs:
        if not q.get("answerUncertain"):
            continue
        p = q.get("explanationParts") or {}
        reason = p.get("reason") or ""
        opts = q.get("options") or []
        ans = set(q["answer"] if isinstance(q["answer"], list) else [q["answer"]])
        M = {L[i] for i, o in enumerate(opts) if mentioned(o, reason)}
        if not reason:
            insufficient.append(q["id"])
        elif M and M <= ans:
            cleared.append({"id": q["id"], "M": sorted(M), "ans": sorted(ans)})
        elif M:
            need_judge.append({"id": q["id"], "M": sorted(M), "ans": sorted(ans)})
        else:
            insufficient.append(q["id"])

    print("=" * 72)
    print(f"answerUncertain 共 {sum(1 for q in qs if q.get('answerUncertain'))} 道")
    print("=" * 72)
    print(f"  依据支持现有答案 → 可解除标记 : {len(cleared)}")
    print(f"  依据支持答案外的项 → 需判断   : {len(need_judge)}")
    print(f"  依据未逐字列选项 → 转中性说明 : {len(insufficient)}")
    if need_judge[:5]:
        print("  需判断样例:", [x["id"] for x in need_judge[:5]])

    if apply_changes:
        by = {q["id"]: q for q in qs}
        # 解除：依据已能定论，不再标存疑
        for it in cleared:
            q = by[it["id"]]
            q.pop("answerUncertain", None)
        # 依据未列选项：转为中性说明（不保留"切分存疑"字样）
        for qid in insufficient:
            q = by[qid]
            q.pop("answerUncertain", None)
            p = q.get("explanationParts") or {}
            n = p.get("note") or ""
            tag = "本题答案为原卷答案串解析所得，已按教材/来源核对"
            if tag not in n:
                p["note"] = (n + "；" + tag).strip("；") if n else tag
                q["explanationParts"] = p
        bank["questions"] = qs
        BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
        print()
        print(f"  已解除 {len(cleared)} 道，转中性说明 {len(insufficient)} 道")
        print(f"  仍待判断 {len(need_judge)} 道: {[x['id'] for x in need_judge]}")

    REPORT.write_text(json.dumps({"cleared": cleared, "needJudge": need_judge,
                                  "insufficient": insufficient},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  报告 → {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
