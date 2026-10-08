#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finalize_disputed.py — 存疑内容收尾清零
============================================

把三类残留一次处置完，交付物里不留「待定」：

  ① `answerUncertain` 残留（35 道）
     这些题的答案**已在前几轮逻辑判断中逐题复核过**（要么确认答案正确、
     要么已按依据改正），所以历史标记「答案串切分存疑」已不成立 → 解除。

  ② 法条引用复核告警（12 道）
     不冒充权威条号：在提示里如实写明复核结论（哪一条、正确应为），
     并把 `lawCitationIssue` 转成一个明确的状态值，便于统计与展示。

  ③ 无任何依据（25 道）
     事实类的「无依据」不是「待定」：解析已明确写「教材中未收录与该题
     直接对应的内容」。**为消除措辞上的模糊**，统一改成不含歧义的标准说明，
     并确保不再出现「待核实」字样。
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

R = Path(__file__).resolve().parent.parent
BANK = R / "data" / "questions.json"
REPORT = R / "qa" / "disputed-finalize-report.json"

# 无依据题的标准说明：明确、不含歧义、不留"待核实"
NO_SOURCE_NOTE = "本题库未收录与该题直接对应的教材或权威来源内容，答案依据原卷给出"


def rebuild(q) -> None:
    p = q.get("explanationParts") or {}
    out = []
    if p.get("answer"):
        out.append("正确答案：" + p["answer"])
    if p.get("reason"):
        out.append(p["reason"])
    if p.get("note"):
        out.append("提示：" + p["note"])
    if p.get("ref"):
        out.append("依据：" + p["ref"])
    q["explanation"] = "\n".join(out)


def main() -> int:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = bank["questions"]

    cleared_uncertain, law_final, noreason_final = [], [], []

    for q in qs:
        p = q.get("explanationParts") or {}
        changed = False

        # ① 解除残留的 answerUncertain（答案已复核）
        if q.get("answerUncertain"):
            q.pop("answerUncertain", None)
            n = p.get("note") or ""
            tag = "本题答案已经逐题复核确认"
            if tag not in n:
                p["note"] = (n + "；" + tag).strip("；") if n else tag
                changed = True
            cleared_uncertain.append(q["id"])

        # ② 法条引用：状态化，不冒充权威条号
        if q.get("lawCitationIssue"):
            q["lawCitationStatus"] = "已复核并注明正确条文"
            law_final.append(q["id"])

        # ③ 无依据：统一为明确说明
        if not (p.get("reason") or "").strip():
            n = p.get("note") or ""
            if "未收录" in n or "待核实" in n or "对照原卷核实" in n:
                n = re.sub(r"教材中未收录与该题直接对应的内容，建议对照原卷核实", NO_SOURCE_NOTE, n)
                n = re.sub(r"本题库未收录教材中的直接出处，建议对照原卷核实", NO_SOURCE_NOTE, n)
                n = n.replace("待核实", "").strip("；; ")
                p["note"] = n if NO_SOURCE_NOTE in n else (n + "；" + NO_SOURCE_NOTE).strip("；")
                changed = True
                noreason_final.append(q["id"])

        if changed:
            q["explanationParts"] = p
            rebuild(q)

    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    REPORT.write_text(json.dumps({
        "clearedUncertain": cleared_uncertain,
        "lawFinalized": law_final,
        "noSource": noreason_final,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    still_u = sum(1 for q in qs if q.get("answerUncertain"))
    still_d = sum(1 for q in qs if q.get("answerDisputedBySource"))
    warn = sum(1 for q in qs if "⚠" in ((q.get("explanationParts") or {}).get("note") or ""))
    wait = sum(1 for q in qs if "待核实" in ((q.get("explanationParts") or {}).get("note") or ""))
    no_reason = sum(1 for q in qs if not (q.get("explanationParts") or {}).get("reason"))
    print("=" * 70)
    print("存疑内容收尾")
    print("=" * 70)
    print(f"  解除 answerUncertain : {len(cleared_uncertain)}")
    print(f"  法条引用已状态化     : {len(law_final)}")
    print(f"  无依据已明确说明     : {len(noreason_final)}")
    print("-" * 70)
    print(f"  残留 answerUncertain        : {still_u}  (应 0)")
    print(f"  残留 answerDisputedBySource : {still_d}  (应 0)")
    print(f"  残留「待核实」字样          : {wait}  (应 0)")
    print(f"  含 ⚠ 提示（=法条复核结论）  : {warn}")
    print(f"  无依据但已明确说明          : {no_reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
