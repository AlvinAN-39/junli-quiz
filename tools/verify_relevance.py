#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_relevance.py — 独立复核「解析与题目有关」
==============================================

不信任 `fix_relevance.py` 自报的数字，用**不同角度**重新检查：

A. 保留下来的 659 条依据句，是否真的**落在答案上**？
   对带具体答案的题，检查依据句是否包含答案的关键词（非纯数字/虚词部分）。
   如果一条依据句连答案都没提到，那它多半还是没在回答这道题。

B. 被撤下依据的题，是否**真的找不到**相关句？
   对已撤下的题做一次全库扫描，看是否存在「题干覆盖 ≥0.5 且含答案关键词」的句子。
   若存在，说明撤错了（漏杀），需要修。

C. 依据句与题干是否有共同实词（切题的最低要求）。
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
sys.path.insert(0, str(ROOT / "tools"))
import gen_explanations as G  # noqa: E402
from answer_text import answer_text  # noqa: E402  单一真相：答案读取只有一处实现

qs = json.loads((ROOT / "data" / "questions.json").read_text(encoding="utf-8"))["questions"]
units, _ = G.load_corpus()
idx = G.Index(units)
L = "ABCDEFGH"


def ans_keys(ans: str) -> list[str]:
    """答案里的关键词（去掉纯数字、单字、虚词）。"""
    parts = re.split(r"[、，,；;和与及（）()\s]+", ans)
    out = []
    for p in parts:
        p = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9%]", "", p)
        if len(p) >= 2 and not re.fullmatch(r"[\d.%％]+", p):
            out.append(p)
    return out


def stem_terms(stem: str) -> list[str]:
    s = re.sub(r"[_＿]{2,}", " ", stem)
    s = re.sub(r"^(下列|以下)(选项中)?(不属于|不包括|不是|不正确|错误的是|正确的是|属于)?", "", s)
    return [t for t in G.keywords(s) if len(t) >= 2 and t not in G.STOP]


kept, dropped = [], []
for q in qs:
    p = q.get("explanationParts") or {}
    (kept if p.get("reason") else dropped).append(q)

print("=" * 80)
print("A. 保留下来的依据句，是否落在答案上？")
print("=" * 80)
hit_ans, miss_ans, no_ans = 0, 0, 0
misses = []
for q in kept:
    reason = (q["explanationParts"] or {}).get("reason", "")
    ans = answer_text(q)
    keys = ans_keys(ans)
    if not keys:
        no_ans += 1
        continue
    rn = G.squeeze(reason)
    if any(k in rn for k in keys):
        hit_ans += 1
    else:
        miss_ans += 1
        misses.append((q, keys, reason))
tot_checked = hit_ans + miss_ans
print(f"  提到答案关键词 : {hit_ans}/{tot_checked}  ({hit_ans/max(1,tot_checked):.0%})")
print(f"  未提到答案关键词: {miss_ans}")
print(f"  （无具体答案可比: {no_ans}，多为判断题/简答题）")
if misses:
    print("\n  未提到答案的样例（需人工看一眼）:")
    for q, keys, reason in misses[:10]:
        print(f"    [{q['id']}] 答案={answer_text(q)[:24]!r} 关键词={keys[:3]}")
        print(f"        题干: {q['stem'][:52]}")
        print(f"        依据: {reason[:90]}")

print()
print("=" * 80)
print("B. 被撤下依据的题，是否真的找不到相关句？（查漏杀）")
print("=" * 80)
wrongly_dropped = []
for q in dropped:
    ans = answer_text(q)
    keys = ans_keys(ans)
    if not keys:
        continue
    sq = re.sub(r"[_＿]{2,}", " ", q["stem"])
    terms = stem_terms(q["stem"])
    cand = idx.candidates(ans) or []
    found = None
    for i in cand[:200]:
        cs = idx.weighted_coverage(sq, i)
        rn = G.squeeze(units[i][1])
        if cs >= 0.5 and any(k in rn for k in keys):
            found = G.clean_line(units[i][1])
            break
    if found:
        wrongly_dropped.append((q, found))
print(f"  撤下后仍能找到「切题且含答案」的句子: {len(wrongly_dropped)}")
if wrongly_dropped:
    print("  （这些属于漏杀，应当补回）:")
    for q, sent in wrongly_dropped[:10]:
        print(f"    [{q['id']}] {q['stem'][:50]}")
        print(f"        答案={answer_text(q)[:26]!r}")
        print(f"        可补: {sent[:90]}")

print()
print("=" * 80)
print("C. 依据句与题干的共同实词（切题最低要求）")
print("=" * 80)
zero = []
for q in kept:
    reason = (q["explanationParts"] or {}).get("reason", "")
    rn = G.squeeze(reason)
    terms = stem_terms(q["stem"])
    common = [t for t in terms if t in rn]
    if not common:
        zero.append((q, reason))
print(f"  与题干无任何共同实词: {len(zero)}/{len(kept)}")
for q, reason in zero[:8]:
    print(f"    [{q['id']}] {q['stem'][:50]}")
    print(f"        依据: {reason[:86]}")

print()
print("=" * 80)
print("汇总")
print("=" * 80)
print(f"  有依据句: {len(kept)}   无依据句: {len(dropped)}")
print(f"  A 提到答案: {hit_ans}/{tot_checked} ({hit_ans/max(1,tot_checked):.0%})")
print(f"  B 漏杀(撤错): {len(wrongly_dropped)}")
print(f"  C 与题干无共同词: {len(zero)}")
