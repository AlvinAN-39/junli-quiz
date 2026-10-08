#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_hard_flags.py — 把难度标记写入题库（全库覆盖）。

来源（两处，合并后写盘）：
  1. `work/hard-flags.json` —— 子代理对**既有 1171 题**的复核判定（扩容轮的产物已归档到
     `qa/shard-audit-2026-10-08/`，如需复跑先把它复制回 `work/`）
  2. `qa/shard-audit-2026-10-08/shard-*.json` 的 `isHard` —— 第二版 source 的原标记（新题）

写盘格式与既有文件一致：`json.dumps(indent=1)` + CRLF + 末尾换行；
仍坚持「既有题的其它字段一字不改」，只加/改 `isHard` 一个键。

用法：
    python tools/apply_hard_flags.py --dry
    python tools/apply_hard_flags.py
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
WORK = ROOT / "work"
WORK.mkdir(parents=True, exist_ok=True)
# 分片原件由扩容轮归档在 qa/shard-audit-2026-10-08/（原中间目录已按纪律清理）
SPLIT = ROOT / "qa" / "shard-audit-2026-10-08"
BANK = ROOT / "data" / "questions.json"
OUT = WORK / "hard-apply-report.json"


def load_flags() -> dict[str, bool]:
    """既有题的复核结果。"""
    p = WORK / "hard-flags.json"
    if not p.exists():
        print(f"!! 缺少 {p}（子代理产物），既有题难度无法应用")
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    flags = d.get("flags")
    if not isinstance(flags, dict):
        # 容忍数组形态：[{"id":..,"isHard":..}]
        flags = {x["id"]: bool(x.get("isHard")) for x in d.get("items", []) if isinstance(x, dict)}
    return {str(k): v is True for k, v in flags.items()}


def main() -> int:
    dry = "--dry" in sys.argv
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = bank["questions"]

    flags = load_flags()
    # 新题的原标记（按题干匹配，分片里的 isHard）
    new_flags: dict[str, bool] = {}
    for fn in ("shard-01.json", "shard-02.json", "shard-03.json", "shard-04.json", "shard-11nian.json"):
        p = SPLIT / fn
        if not p.exists():
            continue
        for it in json.loads(p.read_text(encoding="utf-8")).get("items", []):
            if it.get("isHard") is not None:
                new_flags[str(it.get("stem"))] = bool(it["isHard"])

    changed_new = 0
    missing_existing: list[str] = []
    changed_existing = 0
    for q in qs:
        if q["id"] in flags:
            want = flags[q["id"]]
            if q.get("isHard") is not want or "isHard" not in q:
                q["isHard"] = want
                changed_existing += 1
        elif q.get("stem") in new_flags:
            # 新入库的题（id 不在复核清单里）用第二版原标记
            q["isHard"] = new_flags[q["stem"]]
            changed_new += 1
        else:
            missing_existing.append(q["id"])

    total_hard = sum(1 for q in qs if q.get("isHard") is True)
    report = {
        "total": len(qs), "flaggedByReview": len(flags), "flaggedByV2": len(new_flags),
        "changedExisting": changed_existing, "changedNew": changed_new,
        "hardTotal": total_hard, "hardRatio": round(total_hard / max(1, len(qs)), 4),
        "noFlag": missing_existing[:20], "noFlagCount": len(missing_existing),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"题库 {len(qs)} 题；复核清单 {len(flags)} 条；新题原标记 {len(new_flags)} 条")
    print(f"改写既有题 {changed_existing}，标记新题 {changed_new}；难题合计 {total_hard}（占 {report['hardRatio']:.1%}）")
    if missing_existing:
        print(f"⚠ 无难度来源的题 {len(missing_existing)} 道（前 5：{missing_existing[:5]}）")

    if dry:
        print("--dry：未写盘")
        return 0
    text = json.dumps({"questions": qs}, ensure_ascii=False, indent=1) + "\n"
    tmp = BANK.with_suffix(".json.tmp")
    tmp.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    back = json.loads(tmp.read_text(encoding="utf-8"))
    assert len(back["questions"]) == len(qs)
    assert all("isHard" in q for q in back["questions"]), "有题目缺 isHard"
    tmp.replace(BANK)
    print(f"已写入 {BANK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
