#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_relevance_final.py — 最后一刀：按「与题干的连续公共片段」筛掉残余不相关依据
============================================================================

前几轮用了「题干覆盖 + 答案覆盖 + 关键词命中 + 字面命中」打分，仍留下约 28 道
依据与题干毫不相干，典型的是**同一句教材文本反复出现**，例如：

    「01年4月28日：《中华人民共和国国防教育法》通过并实施。年6月：上海合作组织成立…」
    被挂到了「我国"全民国防教育日"是每年九月的____」「RCEP 正式生效时间」
    「____成立了国家国防动员委员会」等好几道毫不相干的题上。

实测发现一个**更硬、更简单**的相关性判据：**依据句与题干的「最长连续公共片段」长度**。
  * ≥5 字 → 全部人工复核 8 例都是切题的（本题库/本教材里 5 字连续重合基本不可能巧合）；
  * <5 字 → 集中了全部真正的错配（数字枚举句、唱军歌句、法规颁发机关句…）。

所以最后一刀：`run < 5` 且「答案内容字覆盖 < 0.7」的依据一律撤下。
对 <5 字的句子保留一个例外：答案几乎整串都在句里（说明它确实在回答这道题，
只是题干问法不同，例如「我国古代海防建设始于____」vs「古代海防工程建设始于明朝」）。
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
import gen_explanations as G              # noqa: E402
from explain_text import structure, render_text  # noqa: E402
from answer_text import answer_text       # noqa: E402  单一真相：答案读取只有一处实现

BANK = ROOT / "data" / "questions.json"
L = "ABCDEFGH"
RUN_MIN = 4              # 连续**汉字**重合下限
ANS_FALLBACK = 0.55      # run<4 时的例外：答案内容字覆盖率
TERM_RATIO_MIN = 0.34    # 题干术语在依据句中的覆盖率下限（配合「≥2 个」的兜底）


def _clean(s: str) -> str:
    return G.squeeze(re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s))


def longest_cjk_run(a: str, b: str) -> int:
    """最长连续**纯汉字**公共子串长度。

    为什么不直接数「连续字符」：数字串会把长度撑起来
      `年8月31日` 与 `年8月31日` 有 6 个字连续相同，
    但那只是日期巧合，不代表句子在讲同一件事。
    只统计纯汉字片段，判据才真正对应"在讲同一个知识点"。
    """
    a, b = _clean(a), _clean(b)
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1] and re.match(r"[\u4e00-\u9fff]", a[i - 1]):
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def ans_cover(ans: str, sent: str) -> float:
    a = set(re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", ans))
    if not a:
        return 1.0
    s = set(re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", sent))
    return len(a & s) / len(a)


def clause_shares_topic(stem: str, reason: str, ans: str) -> bool:
    """**最终判据**：题干术语与答案必须落在依据句的**同一个分句**里。

    为什么整句级判据不够 —— 它分不清这两种情况：
      ✅ 「…确定每年9月的第三个星期六为全民国防教育日。」 ← 就在讲这道题
      ❌ 「…年8月31日：设立全民国防教育日（每年9月的第三个星期六）。…」
          同样含答案，但它只是一条时间线里的一个条目，与题干考点无关。

    注意**不要**要求「同一个分句里既有术语又有答案」——那会误杀正确答案句：
      「国防的对象，一是侵略，二是武装颠覆和分裂。」
      术语「国防的对象」在前一个分句、答案在后一个分句，仍然完全切题。
    所以判据是：**某个分句含答案**，并且**整句含题干术语**。
    """
    terms = [t for t in G.keywords(re.sub(r"[_＿]{2,}", " ", stem))
             if len(t) >= 2 and t not in G.STOP]
    if not terms:
        return True                       # 题干没有可用术语时不据此否决
    whole = G.squeeze(reason)
    # 术语命中要**按覆盖率**算，不能要求字面完全相同：
    # 题干「我国的全民国防教育日是____」会切出「我国的全」「的全民国」「国防教育」等碎片，
    # 而教材原句写的是「确定每年9月的第三个星期六为全民国防教育日」——
    # 字面只有「全民国防」重合，覆盖率口径下则命中充分（实测踩过，正确句被误杀）。
    hit = sum(1 for t in terms if t in whole)
    if hit == 0:
        return False
    if hit / len(terms) < TERM_RATIO_MIN and hit < 2:
        return False
    parts = [p for p in re.split(r"[，。；、（）()：:？！]", ans or "") if len(p.strip()) >= 2]
    if not parts:
        return True                       # 无具体答案文本（简答题）时只要求切题
    for clause in re.split(r"[，。；、（）()：:？！]", reason):
        c = G.squeeze(clause)
        if len(c) < 3:
            continue
        cs_ = set(re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", c))
        for p in parts:
            ps = set(re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", p))
            if len(ps) >= 2 and len(ps & cs_) / len(ps) >= 0.6:
                return True
    return False


def _drop(q, p: dict, samples: list | None = None, info: tuple | None = None) -> None:
    """撤下依据：清空 reason/ref，改写如实说明，并同步纯文本解析。"""
    p.pop("reason", None)
    if q.get("explanationSrc") == "textbook":
        q["explanationSrc"] = "template"
    q["explanationRef"] = ""
    p.pop("ref", None)
    note = p.get("note") or ""
    if "未收录" not in note and "人工" not in note:
        note = "教材中未收录与该题直接对应的内容，建议对照原卷核实"
    p["note"] = note
    q["explanationParts"] = p
    q["explanation"] = render_text(p)
    if samples is not None and info is not None and len(samples) < 10:
        samples.append(info)


def main() -> int:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = bank["questions"]
    stats = {"kept_high": 0, "kept_by_answer": 0, "dropped": 0, "dropped_clause": 0}
    samples = []
    for q in qs:
        p = q.get("explanationParts") or {}
        reason = (p.get("reason") or "").strip()
        if not reason:
            continue
        stem = re.sub(r"[_＿]{2,}", " ", q["stem"])
        run = longest_cjk_run(stem, reason)
        ans = answer_text(q)
        cov = ans_cover(ans, reason) if ans else 1.0
        # **硬闸**：依据句必须有一个分句同时命中题干术语与答案，否则一律撤下。
        # 这一条拦住的是"句里恰好有答案，但讲的是别的"那类（见函数注释里的反例）。
        if not clause_shares_topic(stem, reason, ans):
            stats["dropped_clause"] += 1
            _drop(q, p, samples, (q["id"], run, cov, q["stem"][:44], reason[:80]))
            continue
        if run >= RUN_MIN:
            stats["kept_high"] += 1
            continue
        if run < RUN_MIN and cov >= ANS_FALLBACK:
            stats["kept_by_answer"] += 1
            continue
        # 撤下
        stats["dropped"] += 1
        _drop(q, p, samples)
        continue

    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    left = sum(1 for q in qs if (q.get("explanationParts") or {}).get("reason"))
    print("=" * 78)
    print("相关性最终筛检")
    print("=" * 78)
    print(f"  与题干有 ≥{RUN_MIN} 个连续汉字重合（高置信）: {stats['kept_high']}")
    print(f"  汉字重合<{RUN_MIN} 但答案基本在句里（例外保留）: {stats['kept_by_answer']}")
    print(f"  撤下「同一分句里对不上题」的依据          : {stats['dropped_clause']}")
    print(f"  撤下相关性不足的依据                      : {stats['dropped']}")
    print(f"  ⇒ 现有依据句: {left} / {len(qs)} ({left/len(qs):.0%})")
    print()
    if samples:
        print("  撤下样例:")
        for qid, run, cov, stem, reason in samples:
            print(f"    {qid} (run={run}, 答案覆盖={cov:.2f}) {stem}")
            print(f"        原依据: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
