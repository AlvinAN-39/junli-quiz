#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_multi_answers.py — 独立抽检多选题答案的语义可靠性
=====================================================

思路：把「源文件无可避免的切分歧义」变成一个**可测量的指标**。
对每道多选题的每个选项，在 `build/text/1-textbook.txt`（教程，20 万中文字）与
`0-outline.txt`（提纲）里查找该选项文本是否出现：

  * 选中的选项（在 answer 里）应当更常出现在权威文本中；
  * 未选中的选项若也大量出现，说明该题答案很可能切错了。

输出：整体命中率对比 + 可疑题清单（未选中的选项命中数 > 选中选项命中数）。
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
BANK = ROOT / "data" / "questions.json"
TEXT = ROOT / "build" / "text"


def load_corpus() -> str:
    parts = []
    for name in ("1-textbook.txt", "0-outline.txt"):
        p = TEXT / name
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    s = "\n".join(parts)
    s = re.sub(r"=== PAGE \d+ ===", " ", s)
    return re.sub(r"\s+", "", s)


def norm(s: str) -> str:
    return re.sub(r"[\s，。、；：？！“”‘’（）()《》〈〉\-—…·,.!?\"'\[\]]+", "", s)


def main() -> int:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = [q for q in bank["questions"] if q["type"] == "multi"]
    corpus = load_corpus()
    print(f"题库多选题 {len(qs)} 道；语料 {len(corpus)} 字符（教程+提纲）")

    hit_sel = hit_unsel = 0
    n_sel = n_unsel = 0
    suspicious: list[tuple[str, str, int, int]] = []
    no_corpus_hit = 0

    for q in qs:
        opts = q["options"]
        ans = set(q["answer"])
        sel_hits, unsel_hits = [], []
        for i, o in enumerate(opts):
            letter = "ABCDEFGH"[i]
            key = norm(o)
            if len(key) < 2:
                h = 0
            else:
                h = corpus.count(key)
            if letter in ans:
                sel_hits.append(h)
                n_sel += 1
                hit_sel += 1 if h > 0 else 0
            else:
                unsel_hits.append(h)
                n_unsel += 1
                hit_unsel += 1 if h > 0 else 0
        if not any(sel_hits):
            no_corpus_hit += 1
        if unsel_hits and sel_hits:
            if max(unsel_hits) > min(sel_hits) and max(unsel_hits) >= 2:
                suspicious.append((q["id"], q["stem"][:56], min(sel_hits), max(unsel_hits)))

    print()
    print("=== 选项在权威语料中的命中率 ===")
    print(f"  被选为答案的选项 : {hit_sel}/{n_sel} = {hit_sel / max(1, n_sel):.1%}")
    print(f"  未被选中的选项   : {hit_unsel}/{n_unsel} = {hit_unsel / max(1, n_unsel):.1%}")
    print(f"  选中选项在语料中完全找不到出处（可能是切分错误或语料未覆盖）: {no_corpus_hit} 道")
    print()
    print(f"=== 可疑题（未选中选项的出现次数 > 选中选项）: {len(suspicious)} 道 ===")
    for qid, stem, mn, mx in suspicious[:25]:
        print(f"  {qid}  选中最小命中={mn:>3}  未选中最大命中={mx:>3}  {stem}")
    if len(suspicious) > 25:
        print(f"  ...（其余 {len(suspicious) - 25} 道见 qa/multi-answer-audit.json）")

    out = {
        "multiTotal": len(qs),
        "selectedOptionHitRate": round(hit_sel / max(1, n_sel), 4),
        "unselectedOptionHitRate": round(hit_unsel / max(1, n_unsel), 4),
        "noCorpusEvidence": no_corpus_hit,
        "suspiciousCount": len(suspicious),
        "suspicious": [
            {"id": qid, "stem": stem, "minSelectedHits": mn, "maxUnselectedHits": mx}
            for qid, stem, mn, mx in suspicious
        ],
    }
    dst = ROOT / "qa" / "multi-answer-audit.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n输出: {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
