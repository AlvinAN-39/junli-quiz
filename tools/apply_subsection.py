#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_subsection.py — 用第二版考纲给「既有题」补小节归属（供复习提纲并入用）。

口径
----
* 只做**可核验的题干精确匹配**：规范化题干（去空格/标点/下划线）相同才算命中，不做模糊猜测。
* 第二版里同一题干可能同时有单选与多选变体，它们的小节完全一致，因此匹配唯一。
* 命中的既有题补 `subsection`（小节名）与 `sectionName`（节名）；未命中的留空，不编。
* 新题的小节在 `make_shards.py` 阶段已写好，本脚本只处理既有题。
* 既有题**其它字段一字不改**，只加两个键；写盘格式与题库现状一致（indent=1 + CRLF）。

用法：
    python tools/apply_subsection.py --dry
    python tools/apply_subsection.py
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
WORK = ROOT / "work"
WORK.mkdir(parents=True, exist_ok=True)
BANK = ROOT / "data" / "questions.json"
V2 = Path(r"D:\.Study\大学\军训期间\军理课\【第二版】source\military_theory")
CH_NAME = {"MT_CH01": "第一章中国国防", "MT_CH02": "第二章国家安全", "MT_CH03": "第三章军事思想",
           "MT_CH04": "第四章现代战争", "MT_CH05": "第五章信息化装备"}
TYPE_FILE = {"single": "single.json", "multi": "multi.json",
             "short_answer": "short_answer.json", "essay": "essay.json"}


def norm(s: str) -> str:
    s = s or ""
    s = re.sub(r"[_＿—\-－\s]+", "", s)
    s = re.sub(r"[，。、；：？！,.;:?!（）()【】\[\]\"“”‘’'`]", "", s)
    return s


def collect_v2() -> dict[tuple[str, str], dict[str, str]]:
    """{（章名, 规范化题干）: {subsection, sectionName, type}}，含多题型变体。"""
    out: dict[tuple[str, str], dict[str, str]] = {}

    def walk(node, qtype, ch_name, sec_name, sub_name):
        if isinstance(node, dict):
            if "stem" in node and "answer" in node:
                key = (ch_name, norm(node["stem"]))
                out.setdefault(key, {"subsection": sub_name or sec_name,
                                     "sectionName": sec_name, "type": qtype})
                return
            for k, v in node.items():
                if isinstance(v, (dict, list)):
                    if ch_name is None:
                        walk(v, qtype, CH_NAME.get(k, k), None, None)
                    elif sec_name is None:
                        walk(v, qtype, ch_name, k, None)
                    else:
                        walk(v, qtype, ch_name, sec_name, k)
        elif isinstance(node, list):
            for v in node:
                walk(v, qtype, ch_name, sec_name, sub_name)

    for src in ("mock", "real"):
        for qtype, fn in TYPE_FILE.items():
            p = V2 / src / fn
            if not p.exists():
                continue
            walk(json.loads(p.read_text(encoding="utf-8")), qtype, None, None, None)
    return out


def main() -> int:
    dry = "--dry" in sys.argv
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = bank["questions"]
    v2 = collect_v2()
    print(f"第二版索引 {len(v2)} 条（章 + 规范化题干）")

    hit = 0
    nohit: list[str] = []
    for q in qs:
        info = v2.get((q.get("chapter", ""), norm(q.get("stem", ""))))
        if info:
            q["subsection"] = info["subsection"]
            q["sectionName"] = info["sectionName"]
            hit += 1
        else:
            q["subsection"] = ""
            q["sectionName"] = ""
            nohit.append(q["id"])

    subs = sorted({q["subsection"] for q in qs if q["subsection"]})
    report = {"total": len(qs), "matched": hit, "unmatched": len(nohit),
              "subsections": len(subs), "unmatchedIds": nohit[:50]}
    (WORK / "subsection-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                                 encoding="utf-8")
    print(f"现库 {len(qs)} 题：命中小节 {hit}，未命中 {len(nohit)}，涉及小节 {len(subs)} 个")
    print(f"未命中示例：{nohit[:8]}")
    if dry:
        print("--dry：未写盘")
        return 0
    text = json.dumps({"questions": qs}, ensure_ascii=False, indent=1) + "\n"
    tmp = BANK.with_suffix(".json.tmp")
    tmp.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    back = json.loads(tmp.read_text(encoding="utf-8"))
    assert len(back["questions"]) == len(qs)
    assert all("subsection" in q for q in back["questions"])
    tmp.replace(BANK)
    print(f"已写入 {BANK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
