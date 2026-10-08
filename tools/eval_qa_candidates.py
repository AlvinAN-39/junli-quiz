#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eval_qa_candidates.py — 逐条核对质检提出的「疑似漏选」候选，供人工拍板。

对每条候选打印：题号 / 题干 / 选项 / 当前答案 / 质检建议答案，
便于与 build/text 的源文件行号对照后决定是否加入 CURATED_FIXES。
"""
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
bank = json.loads((ROOT / "data" / "questions.json").read_text(encoding="utf-8"))
by_id = {q["id"]: q for q in bank["questions"]}

CANDIDATES = [
    ("q-0074", ["A", "B", "C", "D"], "0-outline:69 公民国防义务"),
    ("q-0083", ["A", "B", "C", "D"], "0-outline:139 新型军兵种结构布局"),
    ("q-0221", ["A", "B", "D"], "0-outline:408 政治工作三大原则"),
    ("q-0223", ["A", "B", "C"], "0-outline:408 三大原则"),
    ("q-0458", ["A", "B", "C", "D"], "0-outline:156 武警组成"),
    ("q-0465", ["A", "B", "C", "D"], "0-outline:171 国防动员七类"),
    ("q-0466", ["A", "B", "C", "D"], "0-outline:175 信息动员四项"),
    ("q-0569", ["A", "B", "C"], "0-outline:289 三点作用"),
    ("q-0571", ["A", "B", "C"], "0-outline:292 持久和平/普遍安全/共同繁荣"),
    ("q-0689", ["A", "B", "C", "D"], "0-outline:411 四条基本原理"),
    ("q-0703", ["A", "C", "D"], "0-outline:438 绝对忠诚/纯洁/可靠"),
    ("q-0801", ["A", "B", "C", "D"], "0-outline:536 四项一体化"),
    ("q-0805", ["A", "C", "D"], "1-textbook:1426 + 0-outline:533 信息空间"),
    ("q-0557", ["A", "B", "C"], "0-outline:254 海外利益安全（中等置信）"),
    ("q-0086", ["A", "B", "D"], "0-outline:171 七类动员（中等置信）"),
]

print("=" * 100)
print("质检「疑似漏选」候选逐条核对")
print("=" * 100)
missing = []
for qid, suggest, why in CANDIDATES:
    q = by_id.get(qid)
    if not q:
        missing.append(qid)
        continue
    cur = q.get("answer")
    flag = "★需改" if list(cur) != list(suggest) else "  一致"
    print(f"\n[{flag}] {qid}  {why}")
    print(f"  题干: {q['stem'][:88]}")
    for i, o in enumerate(q["options"]):
        mark = "✓" if "ABCDEFGH"[i] in suggest else " "
        curmark = "●" if "ABCDEFGH"[i] in (cur if isinstance(cur, list) else []) else " "
        print(f"    {curmark}{mark} {chr(65+i)}. {o[:74]}")
    print(f"  当前答案={cur}   质检建议={suggest}")
    if list(cur) != list(suggest):
        print(f"  依据: {why}")

if missing:
    print(f"\n!! 题库中找不到这些 id（可能已重编号）: {missing}")
print()
print(f"合计候选 {len(CANDIDATES)} 条，其中需改动 "
      f"{sum(1 for qid, s, _ in CANDIDATES if qid in by_id and list(by_id[qid]['answer']) != list(s))} 条")
