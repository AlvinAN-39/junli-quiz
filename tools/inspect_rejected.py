#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inspect_rejected.py — 查看质量门拒绝条目的原文（一次性排查工具）
==================================================================
用途：merge_contrast_results.py 拒绝了一批条目，需要看清它们到底是
「真的不合格」还是「质量门规则过严」（例如选项文本里带 C4ISR 这类缩写）。
用法：python tools/inspect_rejected.py
"""
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "qa" / "contrast-merge-report.json"
RE_BAD = re.compile(r"[A-Za-z]|\*\*|^#|^\d+[.、)]|`")

if not REPORT.exists():
    raise SystemExit("缺少 qa/contrast-merge-report.json，请先跑 merge_contrast_results.py")

rep = json.loads(REPORT.read_text(encoding="utf-8"))
rejected = rep.get("rejected", [])

# 建立 (id,key) -> text 索引
idx = {}
for f in sorted(glob.glob(str(ROOT / "qa" / "contrast-tasks" / "result-*.json"))):
    d = json.loads(Path(f).read_text(encoding="utf-8"))
    for it in d.get("items", []):
        idx[(it.get("id"), it.get("key"))] = str(it.get("text") or "")

print("报告里被拒 %d 条" % len(rejected))
for r in rejected:
    tag = r.get("tag")
    if not tag or "/" not in tag:
        print("  [%s] %s" % (r.get("file"), r.get("reason")))
        continue
    qid, key = tag.split("/", 1)
    text = idx.get((qid, key), "")
    m = RE_BAD.search(text)
    print("  %-12s len=%-3d 命中=%-8s %s" % (tag, len(text), m.group(0) if m else "-", text[:70]))
