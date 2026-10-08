#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_textbook_review.py — 把教材比对结果导出为「逐题复核清单」
=================================================================

输入：`qa/textbook-audit.json`（由 tools/audit_textbook.py 生成）
输出：`qa/textbook-review/part-XX.md`，每条含：
    * 题号 / 题型 / 题干 / 全部选项 / 当前答案
    * 机器判定（可疑 / 教材未覆盖）与教材证据分
    * 该题的教材候选段落（最多 6 段）

用途：让复核者（人或子代理）只在**这些候选段落**里判断，不必翻 700 KB 教材；
同时保证复核结论可溯源到具体段落。

用法：
    python tools/export_textbook_review.py            # 只导出可疑(81)
    python tools/export_textbook_review.py --all      # 可疑 + 未覆盖(229)
    python tools/export_textbook_review.py --per 40   # 每个文件最多 40 题
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "qa" / "textbook-audit.json"
OUTDIR = ROOT / "qa" / "textbook-review"

TYPE_LABEL = {"single": "单选", "multi": "多选", "judge": "判断"}


def clean(s: str) -> str:
    """剔除控制字符（PDF 抽取文本含 NUL，会让下游读取工具判定为二进制文件）。"""
    return "".join(ch for ch in str(s) if ch == "\n" or ch >= " ")


def main() -> int:
    include_all = "--all" in sys.argv
    per = 40
    if "--per" in sys.argv:
        try:
            per = int(sys.argv[sys.argv.index("--per") + 1])
        except Exception:
            per = 40

    data = json.loads(AUDIT.read_text(encoding="utf-8"))
    want = {"suspect_answer"} | ({"no_corpus_evidence"} if include_all else set())
    items = [d for d in data["details"] if d["verdict"] in want]
    items.sort(key=lambda d: (d["verdict"], d["id"]))

    OUTDIR.mkdir(parents=True, exist_ok=True)
    for old in OUTDIR.glob("part-*.md"):
        old.unlink()

    files = []
    for i in range(0, len(items), per):
        chunk = items[i:i + per]
        lines = ["# 语料比对复核清单 第 %d 批（%d 题）" % (i // per + 1, len(chunk)), ""]
        lines.append("> 判定口径：以「语料候选段落」为主要证据（带来源标签）；")
        lines.append("> 证据明确否定当前答案 → `可疑`；证据不足或与本题无关 → `无法判定`，不得凭想象改答案。")
        lines.append("> 每题的「题库现有解析」是生成物，只能作为参考线索，不能当作独立证据。")
        lines.append("")
        for d in chunk:
            lines.append("## %s ｜ %s ｜ 当前答案：%s" % (
                d["id"], TYPE_LABEL.get(d["type"], d["type"]), "".join(d["answer"]) or "—"))
            lines.append("机器判定：%s（答案均值 %.2f / 答案最低 %.2f / 干扰项最高 %.2f）"
                         % (d["verdict"], d["ansAvg"], d["ansMin"], d["disMax"]))
            lines.append("题干：%s" % clean(d["stem"]))
            for j, o in enumerate(d["options"]):
                L = chr(65 + j)
                mark = "★答案" if L in d["answer"] else ""
                sc = (d.get("scores") or {}).get(L, {}).get("score", 0)
                lines.append("  - %s. %s %s（匹配度 %.2f）" % (L, clean(o), mark, sc))
            lines.append("语料候选段落（带来源标签；匹配度＝选项在该段的最长连续命中占比）：")
            for c in (d.get("corpus") or [])[:6]:
                lines.append("  > %s" % clean(c))
            ex = clean((d.get("explanation") or "").replace("\n", " "))
            if ex:
                lines.append("题库现有解析（生成物，仅供参考）：%s" % ex[:300])
            lines.append("")
        p = OUTDIR / ("part-%02d.md" % (i // per + 1))
        p.write_text("\n".join(lines), encoding="utf-8")
        files.append((p, len(chunk)))

    print("导出复核清单：%d 题，%d 个文件（每文件 ≤%d 题）" % (len(items), len(files), per))
    print("  可疑(证据不支持当前答案) %d 题；无语料覆盖 %d 题"
          % (sum(1 for d in items if d["verdict"] == "suspect_answer"),
             sum(1 for d in items if d["verdict"] == "no_corpus_evidence")))
    for p, n in files:
        raw = p.read_text(encoding="utf-8")
        nuls = raw.count("\x00")
        print("  %-46s %2d 题  %5.1f KB  NUL=%d" % (p.name, n, p.stat().st_size / 1024, nuls))
    print("目录：%s" % OUTDIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
