#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plan_web_sourcing.py — 规划「联网补齐依据」的工作量
==================================================

目标：把没有依据的题按**可补齐的难度**分层，先做高性价比的，
避免对 400+ 道题盲目逐题联网（那样既慢又容易错）。

分层依据：
  * 题型：简答题（参考答案即答案要点）本就不需要逐字引文；
  * 主题：能命中**权威公开文件**的题（国防法规、教学大纲、白皮书）最容易一次性覆盖；
  * 其余才算真正需要逐题核实。
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

qs = json.loads((ROOT / "data" / "questions.json").read_text(encoding="utf-8"))["questions"]
no = [q for q in qs if not (q.get("explanationParts") or {}).get("reason")]
print("=" * 78)
print(f"无依据的题: {len(no)} / {len(qs)}")
print("=" * 78)
print("按题型:", dict(Counter(q["type"] for q in no)))
print("按章节:", dict(Counter(q.get("chapter") or "" for q in no)))
print("按来源:", dict(Counter(q.get("source") or "" for q in no)))
print()

# 主题分层：能靠权威公开文件覆盖的
TOPICS = {
    "国防法规原文（国防法/兵役法/国防教育法/国防动员法）":
        r"国防法|兵役法|国防教育法|国防动员法|军事设施保护法|预备役|兵役制度|国防教育日|国防义务|国防权利",
    "军事课教学大纲 / 学生军训":
        r"军训|军事课|教学大纲|高等学校|大学生|课程",
    "国防白皮书 / 国防政策":
        r"国防政策|白皮书|积极防御|防御性国防|国防现代化|三步走",
    "国防领导体制 / 中央军委":
        r"中央军委|国家主席|全国人民代表大会|国务院|国防委员会|领导职权|宣布.*战时|动员委员会",
    "人民军队 / 军兵种":
        r"解放军|武警|民兵|预备役|军种|兵种|海军|空军|陆军|火箭军|战区|军衔|条令",
    "国防教育 / 全民国防":
        r"国防教育|全民国防|国防观念|国防意识",
}

buckets: dict[str, list] = {k: [] for k in TOPICS}
rest: list = []
for q in no:
    text = (q["stem"] or "") + " " + " ".join(q.get("options") or []) + " " + str(q.get("answer") or "")
    hit = None
    for name, pat in TOPICS.items():
        if re.search(pat, text):
            hit = name
            break
    (buckets[hit] if hit else rest).append(q)

print("按主题分层（可用权威公开文件批量覆盖）:")
for name, items in buckets.items():
    if items:
        print(f"  {name:44} {len(items):4d} 道")
print(f"  {'其余（需逐题核实）':44} {len(rest):4d} 道")
print()

print("=" * 78)
print("建议的执行顺序（性价比从高到低）")
print("=" * 78)
print("  1. 简答题：答案本身就是要点，无需引文 → 补「答题要点见参考答案」即可")
print("     ", sum(1 for q in no if q["type"] == "short"), "道")
print("  2. 权威文件建库：把国防法规、教学大纲原文抓下来做语料 → 批量覆盖")
print("     ", sum(len(v) for v in buckets.values()), "道候选")
print("  3. 逐题联网核实剩余部分")
print("     ", len(rest), "道")
print()
print("=== 「其余」样例（看看它们到底是什么题）===")
for q in rest[:20]:
    print(f"  [{q['id']} {q['type']}/{q.get('chapter')}] {q['stem'][:62]}")
    print(f"       答案: {str(q['answer'])[:50]}")
