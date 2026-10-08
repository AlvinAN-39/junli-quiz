#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_stale_notes.py — 清理「改答案后遗留的未结论文本」
======================================================

缺陷成因（本轮取证）
--------------------
历史上修正答案时只改了 `answer` 字段，没有同步 `explanation` / `note`，
于是交付物里留下一批自相矛盾的文本：
  * `q-0080` 答案已是 ABCD，提示却写「给定答案为 B、C、D，漏选了 A」；
  * `q-0542` 答案已是 A，提示却写「本题库答案标注 D，与依据冲突。建议将答案改为 A」；
  * 共 13 条带「⚠ 来源与本题答案存在出入」，另有 2 条「与依据冲突 / 建议改答案」。
这些文字会让用户看到「答案对不上」的假象，也是本轮用户报告问题的一部分。

处置口径（本轮用户确认）
------------------------
* 答案字段已与来源/教材一致的：**删除过时的冲突描述**，改为「来源已核实，答案已按来源更正」，
  链接等可核查信息保留；
* 答案字段确实错的（`q-0539`、`q-0844`）：单独按教材原文改正（见 fix_known_issues2.py）。

安全设计：按题定位、改写后断言旧文本清零、回读验证；同时把每条改动写入
`qa/stale-note-fix.json` 备查。

用法：
    python tools/fix_stale_notes.py --check
    python tools/fix_stale_notes.py
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
DATA = ROOT / "data" / "questions.json"
REPORT = ROOT / "qa" / "stale-note-fix.json"

# ① 「⚠ 来源与本题答案存在出入，已如实记录，建议对照原卷核实：…」整段 → 结论语句
RE_CONFLICT_BLOCK = re.compile(
    r"⚠\s*来源与本题答案存在出入，已如实记录，建议对照原卷核实：.*?(?=(?:依据|另见)?https?://|$)",
    re.S)
NEW_CONFLICT = "来源已核实，本题答案已按来源更正。"

# ② q-0542 的旧答案残留（答案字段已是 A）
RE_Q0542 = re.compile(r"本题库答案标注\s*D（经济方式），与依据冲突。建议将答案改为\s*A。")
NEW_Q0542 = "本题答案已按依据更正为 A。"

# 必须清零的旧文本特征（写盘前后各断言一次）
STALE_MARKERS = [
    "来源与本题答案存在出入，已如实记录，建议对照原卷核实",
    "与依据冲突",
    "建议将答案改为",
]


def clean_text(s: str) -> str:
    """剔除控制字符（PDF 抽取残留的 NUL 会让下游工具误判为二进制）。"""
    return "".join(ch for ch in str(s) if ch == "\n" or ch >= " ")


def apply_fix(text: str) -> tuple:
    """对一段文本套用两条规则，返回 (新文本, 改动列表)。"""
    changes = []
    out = text
    for m in RE_CONFLICT_BLOCK.finditer(out):
        changes.append({"rule": "conflict_block", "before": m.group(0)[:200]})
    n1 = len(changes)
    out = RE_CONFLICT_BLOCK.sub(NEW_CONFLICT, out)
    n2 = 0
    if RE_Q0542.search(out):
        n2 += 1
        out = RE_Q0542.sub(NEW_Q0542, out)
    return out, changes, n1, n2


def main() -> int:
    check_only = "--check" in sys.argv
    raw = DATA.read_text(encoding="utf-8")
    bank = json.loads(raw)
    before_bytes = len(raw.encode("utf-8"))

    print("=" * 74)
    print("清理改答案后遗留的未结论文本")
    print("=" * 74)

    items = []
    n_total = 0
    for q in bank["questions"]:
        targets = [("explanation", lambda: q.get("explanation"),
                    lambda v: q.__setitem__("explanation", v))]
        parts = q.get("explanationParts")
        if isinstance(parts, dict):
            targets.append(("explanationParts.note", lambda: parts.get("note"),
                            lambda v: parts.__setitem__("note", v)))
        for field, getter, setter in targets:
            cur = getter()
            if not isinstance(cur, str) or not cur:
                continue
            new, changes, n1, n2 = apply_fix(cur)
            if n1 or n2:
                setter(new)
                n_total += n1 + n2
                items.append({"id": q["id"], "field": field,
                              "before": clean_text(cur)[-320:], "after": clean_text(new)[-320:]})

    print("改写条目：%d 条（涉及 %d 道题）" % (n_total, len({i['id'] for i in items})))
    for it in items[:15]:
        print("  %-8s %-20s 前：%s" % (it["id"], it["field"], it["before"][-60:]))

    new_text = json.dumps(bank, ensure_ascii=False, indent=1) + "\n"
    left = [m for m in STALE_MARKERS if m in new_text]
    if left:
        print("[FAIL] 改写后仍残留：%r" % left, file=sys.stderr)
        return 2
    print("写盘前断言：旧冲突文本已清零")

    if check_only:
        print("--check 模式：未写盘。")
        return 0

    DATA.write_text(new_text, encoding="utf-8")

    # 回读验证
    back_text = DATA.read_text(encoding="utf-8")
    back = json.loads(back_text)
    left2 = [m for m in STALE_MARKERS if m in back_text]
    n_nul = back_text.count("\x00")
    print("回读：旧文本残留 %s；NUL 字节 %d；题数 %d"
          % (left2 or "0", n_nul, len(back["questions"])))
    print("字节：%d -> %d（%+.1f%%）"
          % (before_bytes, len(back_text.encode("utf-8")),
             (len(back_text.encode("utf-8")) - before_bytes) / before_bytes * 100))
    if left2 or n_nul:
        print("[FAIL] 回读未通过", file=sys.stderr)
        return 3

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "rule1_conflictBlock": {"new": NEW_CONFLICT},
        "rule2_q0542": {"new": NEW_Q0542},
        "items": items,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("清单 → %s" % REPORT)
    print("[PASS] 未结论文本清理完成并回读确认")
    return 0


if __name__ == "__main__":
    sys.exit(main())
