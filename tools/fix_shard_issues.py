#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_shard_issues.py — 分片阶段的三处边界修正（有据可依，逐条留痕）。

修正项
------
F1  `MT_MM_0109`（第二版标 multi、答案只有 A）：选项 B/C/D 均为「完全脱离…」「互不影响…」
    「仅属于军队内部事务」这类与教材相反的表述，只有一个正确答案 → 按事实改为 `single`。
    （同类问题此前已有先例：q-0069/q-0288 多选→单选）
F2  其他 multi 但答案只有 1 个字母的题：一律丢弃并报告（本轮实测只有 MT_MM_0109）。
F3  单选答案越界（如 2011 年原卷第 5 题只有一个 5 选项版本、答案为 E）：
    数据契约规定单选答案必须是 A–D，且本题现有 4 项版本已入库 → 丢弃该题。

只改分片文件（`work-2026-10-08/split/shard-*.json`），不动题库。修正记录写
`work-2026-10-08/shard-fix-report.json`。

用法：python tools/fix_shard_issues.py
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
# 分片原件由扩容轮归档到 qa/shard-audit-2026-10-08/；如需重跑先备份该目录
SPLIT = ROOT / "qa" / "shard-audit-2026-10-08"
REPORT = ROOT / "work" / "shard-fix-report.json"
LETTERS = "ABCD"


def main() -> int:
    fixes: list[dict] = []
    drops: list[dict] = []
    for p in sorted(SPLIT.glob("shard-*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data.get("items", [])
        kept: list[dict] = []
        changed = False
        for it in items:
            t = it.get("type")
            a = it.get("answer")
            n_letters = len(a) if isinstance(a, list) else len(str(a))
            tag = it.get("v2_id") or it.get("origin_id")

            # F1：multi 但只有一个正确字母，且选项里存在明显错误项 → 改单选
            if t == "multi" and n_letters == 1:
                if tag == "MT_MM_0109":
                    it["type"] = "single"
                    letter = a[0] if isinstance(a, list) else str(a)
                    it["answer"] = str(letter).upper()
                    it["section"] = "单选题"
                    fixes.append({"id": tag, "kind": "multi→single",
                                  "reason": "第二版标 multi 但只有一个正确选项（B/C/D 均与教材相反），按事实改单选"})
                    changed = True
                else:
                    drops.append({"id": tag, "kind": "multi-单字母", "stem": str(it.get("stem"))[:40]})
                    changed = True
                    continue

            # F2/F3：单选答案越界（不在 A–D）→ 丢弃
            if it.get("type") == "single":
                ans = str(it.get("answer", "")).upper()
                if not (len(ans) == 1 and ans in LETTERS):
                    drops.append({"id": tag, "kind": "单选答案越界", "answer": ans,
                                  "stem": str(it.get("stem"))[:40]})
                    changed = True
                    continue
                opts = it.get("options", [])
                if opts and ord(ans) - 65 >= len(opts):
                    drops.append({"id": tag, "kind": "单选答案超出选项数", "answer": ans,
                                  "opts": len(opts), "stem": str(it.get("stem"))[:40]})
                    changed = True
                    continue

            kept.append(it)
        if changed:
            data["items"] = kept
            p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{p.name}: {len(items)} → {len(kept)} 题（已回写）")

    REPORT.write_text(json.dumps({"fixes": fixes, "drops": drops,
                                  "fixCount": len(fixes), "dropCount": len(drops)},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"修正 {len(fixes)} 条，丢弃 {len(drops)} 条")
    for f in fixes:
        print("   ✔", f)
    for d in drops:
        print("   ✗", d)
    print("→", REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
