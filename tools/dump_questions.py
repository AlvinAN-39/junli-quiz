#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dump_questions.py — 打印指定题号的完整字段（排查/取证用）
==========================================================
用法：python tools/dump_questions.py q-0537 q-0543 q-0555
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
qs = {q["id"]: q for q in json.loads((ROOT / "data" / "questions.json").read_bytes().decode("utf-8"))["questions"]}
for qid in sys.argv[1:]:
    q = qs.get(qid)
    if not q:
        print("未找到 %s" % qid)
        continue
    print("=" * 76)
    print("%s  %s  答案=%s" % (qid, q["type"], q["answer"]))
    print("题干：%s" % q["stem"])
    for i, o in enumerate(q.get("options") or []):
        print("   %s. %s" % ("ABCDEFGH"[i], o))
    print("explanationParts:")
    for k, v in (q.get("explanationParts") or {}).items():
        print("   %-8s %s" % (k, str(v)[:200]))
    print("explanation:")
    print("   " + (q.get("explanation") or "").replace("\n", "\n   ")[:600])
    print("distractorWhy: %s" % json.dumps(q.get("distractorWhy"), ensure_ascii=False)[:400])
