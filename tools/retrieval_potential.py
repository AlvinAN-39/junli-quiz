#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retrieval_potential.py — 先量出「检索天花板」，再决定怎么改
==========================================================

问题：有些解析引用的教材原句讲的不是这道题的事（例如问「武警部队设几级领导机关」
却引用「城市空气质量尚未达到三级水平」——「级」字巧合命中）。

动手改之前必须先知道一件事：**到底有多少题能在教材里真找到相关的句子？**
如果大部分题本来就找不到，那么"改得更相关"只会变成编造。

对每道题在全部 5409 句语料里算两个量：
  * `covStem` —— 按稀有度加权的**题干**覆盖率（这句是否在讲这道题）
  * `covAns`  —— 按稀有度加权的**答案**覆盖率（这句是否支持这个答案）
两者都达标才算「与题目有关」的依据。输出天花板，用来决定阈值与策略。
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import gen_explanations as G  # noqa: E402
from answer_text import answer_text  # noqa: E402  单一真相：答案读取只有一处实现

BANK = ROOT / "data" / "questions.json"
qs = json.loads(BANK.read_text(encoding="utf-8"))["questions"]
units, _ = G.load_corpus()
idx = G.Index(units)
print(f"语料 {len(units):,} 句；题目 {len(qs)} 道")


def stem_query(stem: str) -> str:
    s = re.sub(r"[_＿]{2,}", " ", stem)
    s = re.sub(r"^(下列|以下)(选项中)?(不属于|不包括|不是|不正确|错误的是|正确的是|属于)?", "", s)
    return s.strip()


STEM_MIN = 0.50
ANS_CHAR_MIN = 0.60      # 答案内容字在依据句里的出现比例


def ans_char_cover(ans: str, sent: str) -> float:
    """答案的**内容字**有多少出现在依据句里。

    不能用 n-gram 覆盖率衡量答案：选择题的答案常是「侵略和武装颠覆、分裂」这种
    对教材原句的**概括**，原句写的是「国防的对象是指国防要防备、抵抗和制止的行为」——
    两者意思一致但没有长公共子串，n-gram 覆盖率会算成 0（实测踩过，把正确答案
    全判成「不合格」）。按字覆盖率衡量则稳定得多。
    """
    a = set(re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", ans))
    if not a:
        return 1.0
    s = set(re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", sent))
    return len(a & s) / len(a)


rows = []
for n, q in enumerate(qs, 1):
    ans = answer_text(q)
    sq = stem_query(q["stem"])
    cand = idx.candidates(f"{sq} {ans}") or []
    if ans:
        cand = list(dict.fromkeys(cand + idx.candidates(ans)))
    best = (-1.0, 0.0, 0.0, -1)
    for i in cand[:400]:
        cs = idx.weighted_coverage(sq, i)
        ac = ans_char_cover(ans, units[i][1]) if ans else 1.0
        score = cs * 0.75 + ac * 0.25
        if score > best[0]:
            best = (score, cs, ac, i)
    score, cs, ac, i = best
    usable = bool(i >= 0 and cs >= STEM_MIN and ac >= ANS_CHAR_MIN)
    rows.append({"q": q, "ans": ans, "score": score, "covStem": cs, "covAns": ac,
                 "usable": usable, "sent": G.clean_line(units[i][1]) if i >= 0 else ""})
    if n % 300 == 0:
        print(f"  ...{n}/{len(qs)}")

has_reason = lambda r: bool((r["q"].get("explanationParts") or {}).get("reason"))
usable = [r for r in rows if r["usable"]]
stale = [r for r in rows if has_reason(r) and not r["usable"]]
rescue = [r for r in rows if not has_reason(r) and r["usable"]]

print()
print("=" * 80)
print("检索天花板：每道题在教材语料里的最佳相关句")
print("=" * 80)
print(f"  可用作「与题目有关」的依据 : {len(usable)} / {len(rows)} ({len(usable)/len(rows):.0%})")
print(f"     判据: 题干覆盖 ≥{STEM_MIN}（切题）且 答案内容字覆盖 ≥{ANS_CHAR_MIN}（支持答案）")
print()
print(f"  现状挂了依据句的题         : {sum(1 for r in rows if has_reason(r))}")
print(f"  其中**当前依据不合格**     : {len(stale)}   ← 讲了别的事，需修正或撤下")
print(f"  当前没依据但**能补上合格句**: {len(rescue)}")
print()
print(f"  → 修正后预计「有相关依据」: {len(usable)} 道")
print()

print("=" * 80)
print("A. 当前依据不合格（依据句讲的是别的事）")
print("=" * 80)
for r in stale[:12]:
    q = r["q"]
    print(f"  [{q['id']} {q['type']}/{q.get('explanationSrc')}] stem={r['covStem']:.2f} ans={r['covAns']:.2f}")
    print(f"     题干: {q['stem'][:58]}")
    print(f"     现有: {(q.get('explanationParts') or {}).get('reason', '')[:100]}")
print()
print("=" * 80)
print("B. 能替换/补上的合格依据")
print("=" * 80)
for r in (stale + rescue)[:12]:
    q = r["q"]
    print(f"  [{q['id']}] stem={r['covStem']:.2f} ans={r['covAns']:.2f}")
    print(f"     题干: {q['stem'][:58]}")
    print(f"     可用: {r['sent'][:104]}")
print()
print("=" * 80)
print("C. 教材里确实找不到（只能如实说明）")
print("=" * 80)
for r in [r for r in rows if not r["usable"]][:10]:
    q = r["q"]
    print(f"  [{q['id']} {q['type']}] {q['stem'][:62]}")
    print(f"     最佳(仍不切题): {r['sent'][:92]}")
