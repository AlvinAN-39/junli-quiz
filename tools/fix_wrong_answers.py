#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_wrong_answers.py — 按教材原文改正有充分依据的错误答案
============================================================

本轮用户明确授权（第 2 轮追问）：「有教材原文可引的直接改正」。

处置的两道题及其教材依据
------------------------
* `q-0539`「邓小平提出，当代世界解决国际争端应主要采取____」
    现答案 B（战争方式）→ 改 A（和平方式）。
    依据：教材《普通高校军事课教程》原文「主要内容有：…④**用和平方式解决国际争端**」；
    同题在 `build/text/3-mock.txt` 中亦以「A.和平方式」为题干形态出现。
* `q-0844`「电磁炮和粒子束武器属于新概念武器中的？」
    现答案 B（定向能武器）→ 改 A（动能武器）。
    依据：教材原文「**电磁炮**是利用电磁能代替化学发射药发射弹丸的远程武器系统」
    （属动能武器）；「**粒子束武器**…依靠粒子加速器发射…粒子束流」（属定向能武器）。
    两者分属不同类别，题干本身不严谨，已在解析中如实写明，避免误导。

不改的部分
----------
`q-0803`（单兵数字化装备分系统，子代理建议 ABCD）**不在本脚本处理范围**：
该题答案改动缺少我独立复核的教材原文，已列入待你确认清单。

安全设计：按 id 定位、改前断言当前值与预期一致（防止覆盖人工修改）、
写盘后回读验证、改动清单写入 `qa/wrong-answer-fix.json`。

用法：
    python tools/fix_wrong_answers.py --check
    python tools/fix_wrong_answers.py
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
DATA = ROOT / "data" / "questions.json"
REPORT = ROOT / "qa" / "wrong-answer-fix.json"

# q-0539：答案 B → A，解析改写为与答案一致（保留教材依据原文）
Q0539 = {
    "answer": "A",
    "explanation": (
        "正确答案：A（和平方式）\n"
        "教材《普通高校军事课教程》在阐述邓小平对战争与和平的新认识时，把主要内容列为："
        "①战争从不可避免到可以避免；②和平与发展是当今世界的两大主题；③霸权主义是当代战争的主要根源；"
        "④用和平方式解决国际争端；⑤发展制约战争的和平力量；⑥建立国际新秩序，实现持久和平；"
        "⑦未来战争是现代条件下的局部战争。即解决国际争端应主要采取和平方式。\n"
        "提示：原答案为 B（战争方式），与教材原文冲突，已按教材更正为 A。\n"
        "依据：教材《普通高校军事课教程》·军事思想（第 2 章「邓小平新时期军队建设思想」）"
    ),
    "part_reason": (
        "教材把「用和平方式解决国际争端」列为邓小平对战争与和平新认识的主要内容之一；"
        "战争方式是与之相反的选项。"
    ),
    "part_note": "原答案为 B（战争方式），与教材原文冲突，已按教材更正为 A。",
}

# q-0844：答案 B → A，解析明确说明题干分属两类的缺陷
Q0844 = {
    "answer": "A",
    "explanation": (
        "正确答案：A（动能武器）\n"
        "教材原文把电磁炮归入动能武器：「电磁炮是利用电磁能代替化学发射药发射弹丸的远程武器系统」；"
        "而粒子束武器属定向能武器：「粒子束武器是指依靠粒子加速器发射的高度聚集的强原子粒子束流"
        "或亚原子粒子束流，以接近光速的速度攻击目标的武器」，与激光武器同属「定向能武器」。"
        "即电磁炮与粒子束武器分属动能武器与定向能武器两类。\n"
        "提示：本题题干把两类武器并列提问，本身不够严谨；原答案为 B（定向能武器），"
        "与教材对电磁炮的归类冲突，已按教材更正为 A。\n"
        "依据：教材《普通高校军事课教程》·军事高技术（新概念武器：定向能武器 / 动能武器）"
    ),
    "part_answer": "A（动能武器）",
    "part_reason": (
        "教材将电磁炮归入动能武器；粒子束武器属定向能武器，两者不同类，"
        "故不能以「定向能武器」统摄两项。"
    ),
    "part_note": "本题题干把动能武器与定向能武器并列提问，不够严谨；答案已按教材更正为 A。",
}

# 改前必须匹配的旧值（防止覆盖后续人工修改）
EXPECT = {
    "q-0539": {"answer": "B"},
    "q-0844": {"answer": "B"},
}


def main() -> int:
    check_only = "--check" in sys.argv
    text = DATA.read_text(encoding="utf-8")
    bank = json.loads(text)
    before = len(text.encode("utf-8"))
    by_id = {q["id"]: q for q in bank["questions"]}

    print("=" * 74)
    print("按教材原文改正错误答案")
    print("=" * 74)
    changes = []
    for qid, cfg in (("q-0539", Q0539), ("q-0844", Q0844)):
        q = by_id[qid]
        if q.get("type") != "single":
            print("[FAIL] %s 非单选题（type=%s），中止" % (qid, q.get("type")), file=sys.stderr)
            return 2
        want_old = EXPECT[qid]["answer"]
        if q["answer"] == cfg["answer"]:
            print("%s：已是 %s，跳过（幂等）" % (qid, cfg["answer"]))
            continue
        if q["answer"] != want_old:
            print("[FAIL] %s 当前答案 %r 与预期旧值 %r 不符，中止（避免覆盖人工修改）"
                  % (qid, q["answer"], want_old), file=sys.stderr)
            return 3
        changes.append({"id": qid, "field": "answer",
                        "before": q["answer"], "after": cfg["answer"]})
        q["answer"] = cfg["answer"]
        q["explanation"] = cfg["explanation"]
        parts = q.setdefault("explanationParts", {})
        for key in ("part_answer", "part_reason", "part_note"):
            if key in cfg:
                parts[key.replace("part_", "")] = cfg[key]
        print("%s：答案 %s → %s，解析已按教材重写" % (qid, want_old, cfg["answer"]))

    if not changes:
        print("无需改动。")
        return 0

    # 写盘前断言：改后 qa 必须与答案一致（简单自校验）
    for qid, cfg in (("q-0539", Q0539), ("q-0844", Q0844)):
        q = by_id[qid]
        assert q["answer"] == cfg["answer"], qid

    new_text = json.dumps(bank, ensure_ascii=False, indent=1) + "\n"
    if check_only:
        print("--check 模式：未写盘。")
        return 0

    DATA.write_text(new_text, encoding="utf-8")

    # 回读验证
    back = json.loads(DATA.read_text(encoding="utf-8"))
    bq = {q["id"]: q for q in back["questions"]}
    ok = True
    for qid, cfg in (("q-0539", Q0539), ("q-0844", Q0844)):
        good = bq[qid]["answer"] == cfg["answer"] and "已按教材更正" in (bq[qid].get("explanation") or "")
        ok = ok and good
        print("回读 %s：answer=%r %s" % (qid, bq[qid]["answer"], "[OK]" if good else "[FAIL]"))
    print("字节：%d -> %d" % (before, len(DATA.read_text(encoding="utf-8").encode("utf-8"))))
    if not ok:
        print("[FAIL] 回读未通过", file=sys.stderr)
        return 4

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "basis": "教材《普通高校军事课教程》原文；用户第 2 轮授权「有教材原文可引的直接改正」",
        "changes": changes,
        "pendingUserConfirm": ["q-0803 单兵数字化装备分系统（子代理建议 ABCD，缺少独立复核原文）"],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("清单 → %s" % REPORT)
    print("[PASS] 错误答案已按教材更正并回读确认")
    return 0


if __name__ == "__main__":
    sys.exit(main())
