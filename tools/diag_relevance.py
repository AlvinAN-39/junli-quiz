#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
diag_relevance.py — 量化「解析是否与题目有关」
============================================

用户要求「确保解析与题目有关」。本脚本给出客观判据：

对每道有 `reason` 的题，检查依据句是否**真的在讲这道题问的东西**：
  1. `subjectHit` —— 依据句是否包含题干的**主语短语**（题干「X是____」里的 X）。
     这是最硬的相关性判据：如果问「国防的对象」，依据句里连「国防的对象」都没有，
     那它多半是在讲别的。
  2. `topical`   —— 依据句中出现的题干内容词个数（≥2 视为切题）。
  3. 反例清单   —— 列出两者都不满足的题，供人工判断与定向修复。
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
import gen_explanations as G           # noqa: E402
import gen_wrong_analysis as W         # noqa: E402

BANK = ROOT / "data" / "questions.json"
qs = json.loads(BANK.read_text(encoding="utf-8"))["questions"]


def subject_phrase(stem: str) -> str:
    """题干主语短语（「X是____」的 X）——用于判断依据句是否在讲同一件事。"""
    s = re.sub(r"[_＿]{2,}", " ", stem)
    s = re.sub(r"^(下列|以下)(选项中)?(不属于|不包括|不是|不正确|错误的是|正确的是|属于)?", "", s)
    m = re.match(r"^\s*(.{2,20}?)\s*(?:是|包括|有|属于|指的是|是指|称为|被称为|分为)", s)
    if m:
        return re.sub(r"[\s　]", "", m.group(1))
    m2 = re.match(r"^\s*(.{2,20}?)[，。？]", s)
    return re.sub(r"[\s　]", "", m2.group(1)) if m2 else ""


rows = []
for q in qs:
    parts = q.get("explanationParts") or {}
    reason = (parts.get("reason") or "").strip()
    src = q.get("explanationSrc") or ""
    subj = subject_phrase(q["stem"])
    if not reason:
        rows.append({"q": q, "subj": subj, "hasReason": False, "subjectHit": None,
                     "topical": 0, "src": src})
        continue
    rn = G.squeeze(reason)
    subjectHit = bool(subj) and len(subj) >= 2 and subj in rn
    # 题干内容词在依据句中的命中数
    kws = [k for k in G.keywords(q["stem"]) if len(k) >= 2]
    topical = sum(1 for k in kws if k in rn)
    rows.append({"q": q, "subj": subj, "hasReason": True, "subjectHit": subjectHit,
                 "topical": topical, "src": src})

has = [r for r in rows if r["hasReason"]]
print("=" * 78)
print("解析相关性诊断")
print("=" * 78)
print(f"总题数            : {len(rows)}")
print(f"有 reason（有依据句）: {len(has)}")
print(f"无 reason          : {len(rows) - len(has)}")
print()
ok_subj = [r for r in has if r["subjectHit"]]
ok_top = [r for r in has if not r["subjectHit"] and r["topical"] >= 2]
weak = [r for r in has if not r["subjectHit"] and r["topical"] < 2]
print(f"① 依据句含题干主语短语   : {len(ok_subj)}  ({len(ok_subj)/max(1,len(has)):.1%})  ← 最硬的相关性证据")
print(f"② 虽无主语但题干词命中≥2 : {len(ok_top)}")
print(f"③ **疑似不相关**（两者都不满足）: {len(weak)}")
print()
print("依据来源分布（③ 疑似不相关里）:", dict(Counter(r["src"] for r in weak)))
print()
print("=" * 78)
print("③ 疑似不相关的样例（人工判断）")
print("=" * 78)
for r in weak[:18]:
    q = r["q"]
    print(f"[{q['id']} {q['type']}/{r['src']}] 题干: {q['stem'][:52]}")
    print(f"    主语短语: {r['subj']!r}   题干词命中: {r['topical']}")
    print(f"    依据句  : {(q.get('explanationParts') or {}).get('reason','')[:110]}")
    print()

# 无 reason 的题分布
noreason = [r for r in rows if not r["hasReason"]]
print("=" * 78)
print(f"无 reason 的 {len(noreason)} 道按题型:", dict(Counter(r["q"]["type"] for r in noreason)))
print(f"无 reason 的来源:", dict(Counter(r["src"] for r in noreason)))
