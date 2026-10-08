#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_corpus.py — 检查「教材被利用得是否完整」
============================================

用户要求「再检查一遍教材，尽量确保每一道题都有依据」。
在改检索之前，必须先把**语料本身**查清楚。本脚本回答四个问题：

  A. 教材/提纲原文里有多少内容**因为长度过滤被丢掉了**？
     （`load_corpus` 只保留 12~220 字的片段，短句全被丢弃）
  B. 教材的正文是否**完整提取**出来了？（按页/按行抽查，看有没有大段缺失或乱码）
  C. 丢失的短句里，有没有**正好能回答某些题**的？
  D. 目前无依据的题，在「包含短句的完整语料」里能否找到依据？
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

TEXT = ROOT / "build" / "text"
qs = json.loads((ROOT / "data" / "questions.json").read_text(encoding="utf-8"))["questions"]
L = "ABCDEFGH"

print("=" * 80)
print("A. 课文原文 vs 实际进入语料的内容（长度过滤损失）")
print("=" * 80)
for fname in ("1-textbook.txt", "0-outline.txt"):
    p = TEXT / fname
    if not p.exists():
        continue
    kept, dropped_short, dropped_long, total = 0, 0, 0, 0
    dropped_samples: list[str] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = G.clean_line(raw)
        if not line or G.PAGE_RE.match(line) or G.JUNK_RE.match(line):
            continue
        for seg in re.split(r"(?<=[。！？])", line):
            seg = G.clean_line(re.sub(r"^\d{1,4}\s*", "", G.clean_line(seg)))
            if not seg or not re.search(r"[\u4e00-\u9fff]", seg):
                continue
            total += 1
            if len(seg) < 12:
                dropped_short += 1
                if len(dropped_samples) < 12 and len(seg) >= 6:
                    dropped_samples.append(seg)
            elif len(seg) > 220:
                dropped_long += 1
            else:
                kept += 1
    print(f"\n{fname}")
    print(f"  片段总数      : {total:,}")
    print(f"  进入语料(12~220字): {kept:,}")
    print(f"  **因过短被丢弃(<12字)**: {dropped_short:,}  ({dropped_short/max(1,total):.1%})")
    print(f"  因过长被丢弃(>220字) : {dropped_long:,}")
    print("  被丢弃的短句样例（这些其实是有用的知识点）:")
    for s in dropped_samples:
        print(f"      · {s}")

print()
print("=" * 80)
print("B. 教材正文提取完整性抽查")
print("=" * 80)
tb = (TEXT / "1-textbook.txt").read_text(encoding="utf-8")
lines = [l for l in tb.splitlines() if l.strip()]
print(f"  教材文本行数: {len(lines):,}   字符数: {len(tb):,}")
cjk = len(re.findall(r"[\u4e00-\u9fff]", tb))
print(f"  其中汉字数  : {cjk:,}")
print(f"  平均每行汉字: {cjk/max(1,len(lines)):.1f}")
# 乱码/替换字符
print(f"  替换字符 U+FFFD: {tb.count(chr(0xFFFD))}")
print(f"  私有区字符(U+E000-U+F8FF): {len(re.findall(r'[\ue000-\uf8ff]', tb))}")
# 空行比例（反映排版）
print(f"  空行比例: {sum(1 for l in tb.splitlines() if not l.strip())/max(1,len(tb.splitlines())):.1%}")
print("  末尾 200 字（看是否有截断）:")
print("   ", repr(tb[-200:]))

print()
print("=" * 80)
print("C. 现有语料 vs 含短句语料的规模对比")
print("=" * 80)
units, _ = G.load_corpus()
print(f"  当前语料句数: {len(units):,}")

def build_full_corpus() -> list[tuple[str, str]]:
    """不过滤长度，把所有片段（含短句）都收进来，并把被切断的拼接回去。"""
    out: list[tuple[str, str]] = []
    for fname in ("1-textbook.txt", "0-outline.txt"):
        p = TEXT / fname
        if not p.exists():
            continue
        chapter = "通用"
        buf: list[str] = []
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = G.clean_line(raw)
            if not line or G.PAGE_RE.match(line) or G.JUNK_RE.match(line):
                continue
            if G.TOC_RE.match(line) and G.PAGENO_RE.search(line) and len(line) < 70:
                continue
            if G.PAGE_STRIP_RE.match(line):
                continue
            hm = G.CHAPTER_HEAD_RE.match(line)
            if hm:
                ch = G.normalize_chapter(hm.group(2))
                if ch:
                    chapter = ch
                    continue
            ch2, rest = G.match_chapter_prefix(line)
            if ch2:
                chapter = ch2
                rest = G.clean_line(rest)
                if len(rest) < 10:
                    continue
                line = rest
            if not re.search(r"[\u4e00-\u9fff]", line):
                continue
            # 按句号切，但**不过滤长度**；同时把「不完整结尾」的片段攒起来与下一行拼接
            for seg in re.split(r"(?<=[。！？])", line):
                seg = G.clean_line(re.sub(r"^\d{1,4}\s*", "", seg))
                if not seg:
                    continue
                ends_clean = seg.endswith(("。", "！", "？"))
                if buf:
                    buf.append(seg)
                    seg = "".join(buf)
                    buf = []
                if not ends_clean:
                    buf = [seg]
                    continue
                if len(seg) <= 300:
                    out.append((chapter, seg))
        if buf:
            out.append((chapter, "".join(buf)))
    return out

full = build_full_corpus()
print(f"  含短句 + 拼接后的语料: {len(full):,}  (对比现有 {len(units):,})")


print()
print("=" * 80)
print("E. 合并语料（现有 + 短句 + 拼接）能救回多少题？")
print("=" * 80)
merged: list[tuple[str, str]] = list(units) + list(full)
seen: set[str] = set()
uniq: list[tuple[str, str]] = []
for ch, s in merged:
    k = G.squeeze(s)
    if k and k not in seen:
        seen.add(k)
        uniq.append((ch, s))
print(f"  合并去重后语料: {len(uniq):,}  (现有 {len(units):,} + 新增 {len(uniq)-len(units):,})")

# 「思考题列表」形态：两个以上「…是什么/有哪些?」串在一起，或整句以问号结尾。
# 这类句子不是知识内容，绝不能被当成依据（实测它靠题干字面重合拿到 cs=1.00）。
REFLECT_LIST_RE = re.compile(r"([^。？?]{4,30}[?？]){2,}|[?？]\s*$")


def is_question_list(s: str) -> bool:
    return bool(REFLECT_LIST_RE.search(s))


idx2 = G.Index(uniq)

no_reason = [q for q in qs if not (q.get("explanationParts") or {}).get("reason")]
rescued = []
for q in no_reason:
    ans = answer_text(q)
    keys = [p for p in re.split(r"[、，,；;和与及]+", ans)
            if len(re.sub(r"[^\u4e00-\u9fff]", "", p)) >= 2]
    if not keys:
        continue
    sq = re.sub(r"[_＿]{2,}", " ", q["stem"])
    cand = idx2.candidates(ans) or []
    best = None
    for i in cand[:300]:
        raw = uniq[i][1]
        if is_question_list(raw):
            continue
        s = G.squeeze(raw)
        if not any(k in s for k in keys):
            continue
        cs = idx2.weighted_coverage(sq, i)
        if cs >= 0.30 and (best is None or cs > best[2]):
            best = (q, raw, cs, i)
    if best:
        rescued.append(best)

print(f"  无依据题 {len(no_reason)} 道 → **可救回 {len(rescued)} 道**（已排除思考题列表）")
print(f"  ⇒ 采用合并语料后，有依据的题可达 {1171 - len(no_reason) + len(rescued)}"
      f" / 1171 ({(1171 - len(no_reason) + len(rescued))/1171:.0%})")
print()
for q, s, cs, _i in rescued[:24]:
    print(f"  [{q['id']} {q['type']}] cs={cs:.2f}  {q['stem'][:44]}")
    print(f"      答案: {answer_text(q)[:36]}")
    print(f"      依据: {G.clean_line(s)[:94]}")
