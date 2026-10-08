#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diag_explanations.py — 诊断现有解析的具体质量问题（为「修正错误 + 更清晰」提供依据）"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BANK = Path(__file__).resolve().parent.parent / "data" / "questions.json"
qs = json.loads(BANK.read_text(encoding="utf-8"))["questions"]

def show(name, items, n=6):
    print(f"\n{'='*80}\n{name}: {len(items)} 道")
    for q in items[:n]:
        print(f"  [{q['id']} {q['type']}/{q.get('explanationSrc')}] {q['stem'][:46]}")
        print(f"      {(q.get('explanation') or '')[:200]}")

# 1) 残留 PDF 噪声：句首孤立的句点/空格、字间空格
p_noise = [q for q in qs if re.search(r"^[\s.。·]+", q.get("explanation") or "")]
show("① 解析以句点/空格开头（PDF 切句噪声）", p_noise)

p_space = [q for q in qs if re.search(r"[\u4e00-\u9fff]\s[\u4e00-\u9fff]", q.get("explanation") or "")]
show("② 解析含「中文 空格 中文」（排版噪声）", p_space)

p_paren = [q for q in qs if re.search(r"[（(]\s*[)）]", q.get("explanation") or "")]
show("③ 解析含空括号 (  )", p_paren)

# 2) 解析与题干/答案无关（纯答案复述）
def is_bare(q):
    e = (q.get("explanation") or "").strip()
    if q["type"] == "fill":
        a = q["answer"][0] if q.get("answer") else ""
        return e.rstrip("。") in (f"正确答案：{a}", f"正确答案：{a}。")
    return False
show("④ 解析只有「正确答案：X」无解释（填空题）", [q for q in qs if is_bare(q)], 8)

# 3) 多选题解析是否真的在解释「为什么选这几个」
p_multi_weak = []
for q in qs:
    if q["type"] != "multi":
        continue
    e = q.get("explanation") or ""
    if q.get("explanationSrc") == "template":
        p_multi_weak.append(q)
show("⑤ 多选题无教材依据（模板兜底）", p_multi_weak)

# 4) 判断题解析是否与选项自洽
p_judge = [q for q in qs if q["type"] == "judge" and "由单选题派生" not in (q.get("explanation") or "")]
show("⑥ 判断题解析非「派生说明」形态", p_judge)

# 5) 引用了错误/无关依据的疑似：解析里的教材句与题干关键词几乎不重合
import collections
p_offtopic = []
for q in qs:
    e = q.get("explanation") or ""
    if q.get("explanationSrc") != "textbook":
        continue
    stem_chars = set(re.sub(r"[^\u4e00-\u9fff]", "", q["stem"]))
    ev_chars = set(re.sub(r"[^\u4e00-\u9fff]", "", e))
    if len(stem_chars) < 6:
        continue
    ov = len(stem_chars & ev_chars) / len(stem_chars)
    if ov < 0.35:
        p_offtopic.append((ov, q))
p_offtopic.sort(key=lambda x: x[0])
print(f"\n{'='*80}\n⑦ 解析与题干词汇重合 <35%（疑似答非所问）: {len(p_offtopic)} 道")
for ov, q in p_offtopic[:8]:
    print(f"  [{q['id']} ov={ov:.2f}] {q['stem'][:44]}")
    print(f"      {(q.get('explanation') or '')[:170]}")

# 6) 长度分布
L = [len(q.get("explanation") or "") for q in qs]
print(f"\n{'='*80}\n⑧ 解析长度: 平均 {sum(L)/len(L):.0f}, 最短 {min(L)}, 最长 {max(L)}")
print("   长度<20 的:", sum(1 for x in L if x < 20), "   >200 的:", sum(1 for x in L if x > 200))

# 7) 截断（以省略号结尾）
p_trunc = [q for q in qs if (q.get("explanation") or "").rstrip().endswith("…")]
show("⑨ 解析以省略号结尾（被截断）", p_trunc)

print(f"\n{'='*80}\n汇总：①{len(p_noise)} ②{len(p_space)} ③{len(p_paren)} ④{len([q for q in qs if is_bare(q)])} "
      f"⑤{len(p_multi_weak)} ⑥{len(p_judge)} ⑦{len(p_offtopic)} ⑨{len(p_trunc)}")
