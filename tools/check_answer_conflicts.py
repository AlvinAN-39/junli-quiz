#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_answer_conflicts.py — 核查子代理报出的「答案与语料冲突」疑点
====================================================================
用法：python tools/check_answer_conflicts.py q-0537 q-0543 q-0555 ...
输出：每题的原题、当前答案、教材/真题/模拟语料中的相关句
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LETTERS = "ABCDEFGH"
qs = {q["id"]: q for q in json.loads((ROOT / "data" / "questions.json").read_bytes().decode("utf-8"))["questions"]}


def norm(t: str) -> str:
    t = "".join(c for c in (t or "") if c == "\n" or c >= " ")
    t = t.replace("（", "(").replace("）", ")").replace("，", ",").replace("。", ".")
    t = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", t)
    return re.sub(r"\s+", "", t)


corp = {}
for f in ("1-textbook.txt", "2-past.txt", "3-mock.txt"):
    p = ROOT / "build" / "text" / f
    if p.exists():
        corp[f] = norm(p.read_bytes().decode("utf-8", errors="replace"))

for qid in sys.argv[1:]:
    q = qs.get(qid)
    if not q:
        print("未找到 %s" % qid)
        continue
    a = q["answer"]
    ans = a if isinstance(a, list) else [str(a)]
    print("=" * 76)
    print("%s  %s  答案=%s" % (qid, q["type"], ans))
    print("  题干：%s" % q["stem"])
    for i, o in enumerate(q.get("options") or []):
        L = LETTERS[i]
        print("    %s. %s%s" % (L, o, "   ← 当前答案" if L in ans else ""))
    # 语料里与题干关键词相关的句子
    kws = [w for w in re.findall(r"[\u4e00-\u9fff]{3,6}", q["stem"]) if len(w) >= 3][:4]
    for name, t in corp.items():
        for kw in kws:
            for m in re.finditer(re.escape(kw), t):
                s = m.start()
                print("  [%s] …%s…" % (name, t[max(0, s - 120):s + 150]))
                break
