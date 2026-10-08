#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_explanations.py — 解析质量抽检：把「解析与答案是否相关」量化。"""
import json
import random
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

bank = json.loads((ROOT / "data" / "questions.json").read_text(encoding="utf-8"))
qs = bank["questions"]
units, _ = G.load_corpus()
idx = G.Index(units)

print("=" * 84)
print("解析覆盖与依据分布")
print("=" * 84)
print("依据分布:", dict(Counter(q.get("explanationSrc") or "none" for q in qs)))
LEN = [len((q.get("explanation") or "")) for q in qs]
print(f"解析长度: 平均 {sum(LEN)/len(LEN):.0f} 字符, 最短 {min(LEN)}, 最长 {max(LEN)}")
print(f"空解析: {sum(1 for x in LEN if x == 0)} 道")
print()

# ---- 量化检查：解析里是否真的提到正确答案 ----
print("=" * 84)
print("「解析是否真的讲到正确答案」量化抽检")
print("=" * 84)
for t in ("single", "multi"):
    sub = [q for q in qs if q["type"] == t]
    covered = 0
    checked = 0
    for q in sub:
        exp = q.get("explanation") or ""
        if q.get("explanationSrc") not in ("textbook", "manual"):
            continue
        checked += 1
        if t == "single":
            ai = "ABCDEFGH".index(q["answer"])
            if ai >= len(q["options"]):
                continue
            ans = q["options"][ai]
        else:
            ans = "".join(q["options"]["ABCDEFGH".index(a)]
                          for a in q["answer"] if "ABCDEFGH".index(a) < len(q["options"]))
        # 用与生成时一致的判据：解析与答案的连续实词片段重合度
        if G.span_fit(ans, exp) >= 0.4 or ans[:6] in exp:
            covered += 1
    print(f"  {t:6}: 有教材依据 {checked} 道，其中解析确实提及答案的 {covered} 道 "
          f"({covered/max(1,checked):.1%})")
print()

# ---- 抽样人工可读 ----
random.seed(20260930)
print("=" * 84)
print("随机抽样（固定种子 20260930）——请人工判断解析是否切题")
print("=" * 84)
for t in ("single", "multi", "fill", "short"):
    sub = [q for q in qs if q["type"] == t]
    for q in random.sample(sub, min(4, len(sub))):
        print(f"\n[{q['id']} {t}] {q['stem'][:70]}")
        if q["options"]:
            for i, o in enumerate(q["options"]):
                mark = "✓" if (t == "single" and q["answer"] == "ABCDEFGH"[i]) or \
                              (t == "multi" and "ABCDEFGH"[i] in q["answer"]) else " "
                print(f"     {mark} {chr(65+i)}. {o[:60]}")
        print(f"   答案: {str(q['answer'])[:90]}")
        print(f"   解析({q.get('explanationSrc')}): {(q.get('explanation') or '')[:170]}")
        if q.get("explanationRef"):
            print(f"   出处: {q['explanationRef']}")
