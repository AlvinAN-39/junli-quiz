#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_explain_answer_sync.py — 同步「解析块里的正确答案」与答案字段
====================================================================

缺陷成因（本轮由用户「问题都出现在错题场景」的提示查出）
--------------------------------------------------------
界面上有两处答案：
  * `q.answer`（经 normalizeAnswer → q.qa）—— 判分、「参考答案」行用它；
  * `explanationParts.answer` —— 解析块里的「正确答案」行用它
    （`explainBody()` 的 `p.answer` 分支）。
本轮把 `q-0539` 的 `answer` 从 B 改成 A 时，只改了前者，
于是错题重做页上「参考答案」显示 A、解析块「正确答案」仍显示旧值「B、战争方式」
—— 用户说的「错题里答案有误、不保真」正是这种同屏两套答案。

处置：按 id 修正 `explanationParts`，并新增/复用核查规则 R9
（`tools/audit_selfconsistent.py`）防止再犯。

误报说明：`q-0751` 的 parts.answer 是「A、C4ISR系统」，其中 C 属于选项文本
（C4ISR 系统）而非第二个答案字母；R9 用「字母后必须是顿号/斜杠/括号/行尾」
的形态判定，不会把它算成不一致。

用法：
    python tools/fix_explain_answer_sync.py --check
    python tools/fix_explain_answer_sync.py
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
REPORT = ROOT / "qa" / "explain-answer-sync.json"

# 期望修正项：id → {字段: 新值}
FIXES = {
    "q-0539": {
        "answer": "A（和平方式）",
        "reason": ("教材把「用和平方式解决国际争端」列为邓小平对战争与和平新认识的主要内容之一；"
                   "战争方式是与之相反的选项。"),
    },
}


def main() -> int:
    check_only = "--check" in sys.argv
    text = DATA.read_text(encoding="utf-8")
    bank = json.loads(text)
    before = len(text.encode("utf-8"))
    by_id = {q["id"]: q for q in bank["questions"]}

    print("=" * 74)
    print("同步「解析块正确答案」与答案字段")
    print("=" * 74)
    changed = []
    for qid, fields in FIXES.items():
        q = by_id[qid]
        parts = q.setdefault("explanationParts", {})
        for key, val in fields.items():
            old = parts.get(key)
            if old == val:
                print("%s.%s 已是目标值，跳过（幂等）" % (qid, key))
                continue
            changed.append({"id": qid, "field": "explanationParts." + key, "before": old, "after": val})
            parts[key] = val
            print("%s.%s：%r → %r" % (qid, key, old, val))

    if not changed:
        print("无需改动。")
        return 0

    new_text = json.dumps(bank, ensure_ascii=False, indent=1) + "\n"
    if check_only:
        print("--check 模式：未写盘。")
        return 0
    DATA.write_text(new_text, encoding="utf-8")

    # 回读 + 全库自校验：字母形态的 parts.answer 必须与答案字段一致
    back = json.loads(DATA.read_text(encoding="utf-8"))

    def ans_set(q):
        a = q["answer"]
        if q["type"] == "multi":
            return sorted(a if isinstance(a, list) else list(str(a)))
        if q["type"] == "single":
            return [str(a).strip().upper()]
        return []

    bad = []
    for q in back["questions"]:
        if q["type"] not in ("single", "multi"):
            continue
        pa = (q.get("explanationParts") or {}).get("answer") or ""
        m = re.match(r"\s*([A-H](?:\s*[、,，/]\s*[A-H])*)\s*(?=[、,，/（(]|$)", pa)
        if not m:
            continue
        letters = sorted(re.findall(r"[A-H]", m.group(1)))
        if letters != ans_set(q):
            bad.append({"id": q["id"], "answer": ans_set(q), "partAnswer": pa[:60]})
    print("全库自校验：答案字段与 parts.answer 不一致 %d 条" % len(bad))
    for b in bad[:10]:
        print("   ", b)
    print("字节：%d -> %d" % (before, len(DATA.read_text(encoding="utf-8").encode("utf-8"))))
    if bad:
        print("[FAIL] 仍存在不一致", file=sys.stderr)
        return 3

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "cause": "改 answer 字段时未同步 explanationParts.answer（界面同屏两套答案）",
        "changes": changed,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("清单 → %s" % REPORT)
    print("[PASS] 已同步并回读确认")
    return 0


if __name__ == "__main__":
    sys.exit(main())
