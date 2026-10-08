#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_round5_findings.py — 修正第四批发现（含一处**上一轮改错**的答案）
======================================================================

背景：子代理在生成对比说明时按语料如实描述，报出两处答案与教材冲突，回原文核对如下。

`q-0685`「外国近代军事思想可划分为两大体系，它们是____」——**上一轮改错了**
    现答案 B、C、D（无产阶级 / 封建地主阶级 / 奴隶主阶级）→ 应为 **A、B**。
    教材原文：「外国近代军事思想可划分为两大体系，即**资产阶级军事思想和无产阶级军事思想**。」
    ⚠ 上一轮（fix_round3_findings.py）按子代理建议把本题由 ABC 改成 BCD —— 那是错的：
    教材把「两大体系」说得很明确，C/D 两项（封建地主阶级、奴隶主阶级）属干扰项。
    这正是「需学科判断的先报不改」该起作用的地方，本轮据原文改回。

`q-0684`「古罗马军事思想的基本思想是____」
    现答案 A、B、C（战争有正义与非正义之分 / 进攻为主防御为辅 / 以攻为守）→ 应为 **D**。
    教材原文把这三条明确列在**古希腊**军事思想的主要观点之下：
      「古希腊军事思想的主要观点有：①战争是由根本利害矛盾引起的；②战争的目的是征服，
        谋求城邦、国家利益和霸主地位；③战争的胜败……」而古希腊、古罗马军事思想在教材中
      并列成节，古罗马部分另述。因此 A、B、C 属古希腊思想，不属于题干所问的古罗马。

安全设计：改前断言旧值、改后回读、重跑「解析块答案 == 答案字段」自校验。

用法：
    python tools/fix_round5_findings.py --check
    python tools/fix_round5_findings.py
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
REPORT = ROOT / "qa" / "round5-answer-fix.json"

FIXES = {
    "q-0685": {
        "old": ["B", "C", "D"],
        "new": ["A", "B"],
        "explanationParts": {
            "answer": "A、B（资产阶级军事思想；无产阶级军事思想）",
            "reason": ("教材原文：外国近代军事思想可划分为两大体系，即资产阶级军事思想和"
                       "无产阶级军事思想。"),
            "note": "上一轮曾误按“无产阶级/封建地主阶级/奴隶主阶级”改为 B、C、D，"
                    "与教材原文冲突，本轮回改为 A、B。",
        },
        "explanation": (
            "正确答案：A、B（资产阶级军事思想；无产阶级军事思想）\n"
            "教材原文：「外国近代军事思想可划分为两大体系，即资产阶级军事思想和无产阶级军事思想。」\n"
            "提示：本题上一轮曾被误改为 B、C、D，与教材原文冲突，本轮按原文改回 A、B；"
            "选项 C（封建地主阶级军事思想）、D（奴隶主阶级军事思想）不是教材所说的两大体系。\n"
            "依据：教材《普通高校军事课教程》·军事思想（外国近代军事思想）"
        ),
        "why": {
            "C": "封建地主阶级军事思想不属教材所说的两大体系：教材明确两大体系是资产阶级与无产阶级军事思想。",
            "D": "奴隶主阶级军事思想不属教材所说的两大体系：它是更早的奴隶社会时期的军事思想。",
        },
    },
    "q-0684": {
        "old": ["A", "B", "C"],
        "new": ["D"],
        "type": "single",
        "explanationParts": {
            "answer": "D（以物质、精神、纪律建立一支忠于统帅的军队）",
            "reason": ("教材把“战争是由根本利害矛盾引起的”“战争的目的是征服，谋求城邦、国家利益和"
                       "霸主地位”等列为**古希腊**军事思想的主要观点；题干问的是古罗马军事思想，"
                       "故 A、B、C 属古希腊而不属古罗马。"),
            "note": "原答案 A、B、C 与教材归类冲突（三项均为古希腊军事思想观点），已改为 D，"
                    "并将题型改为单选（本题只有一个选项属古罗马）。",
        },
        "explanation": (
            "正确答案：D（以物质、精神、纪律建立一支忠于统帅的军队）\n"
            "教材原文把「战争是由根本利害矛盾引起的」「战争的目的是征服，谋求城邦、国家利益和"
            "霸主地位」等明确列在**古希腊**军事思想的主要观点之下；而题干问的是**古罗马**军事思想，"
            "因此 A、B、C 三项属古希腊思想，只有 D 与古罗马军事思想相符。\n"
            "提示：原答案为 A、B、C，与教材的归类冲突（三项均为古希腊军事思想观点）；"
            "本题只有一个选项属古罗马，故题型由多选改为单选。\n"
            "依据：教材《普通高校军事课教程》·军事思想（古希腊与古罗马军事思想）"
        ),
        "why": {},
    },
}


def ans_norm(q):
    a = q["answer"]
    return sorted(a) if isinstance(a, list) else a


def main() -> int:
    check_only = "--check" in sys.argv
    bank = json.loads(DATA.read_bytes().decode("utf-8"))
    before = len(DATA.read_bytes())
    by_id = {q["id"]: q for q in bank["questions"]}

    print("=" * 74)
    print("第四批修正（含一处上一轮改错的回改）")
    print("=" * 74)
    changes = []
    for qid, cfg in FIXES.items():
        q = by_id[qid]
        if ans_norm(q) == cfg["new"]:
            print("%s 已是目标值（幂等跳过）" % qid)
            continue
        if ans_norm(q) != cfg["old"]:
            print("[FAIL] %s 当前答案 %r 与预期旧值 %r 不符，中止" % (qid, q["answer"], cfg["old"]),
                  file=sys.stderr)
            return 2
        changes.append({"id": qid, "before": q["answer"], "after": cfg["new"],
                        "note": cfg["explanationParts"]["note"]})
        if cfg.get("type"):
            q["type"] = cfg["type"]
        # 数据契约：single 的 answer 必须是**字符串**，multi 才是字母数组。
        # 改题型时必须按新题型写 answer，否则会留下 ['D'] 这种非法格式
        # （本轮实测：写成数组后 R4/R9 立刻报不一致，因为答案集合退化成 "['D']"）。
        q["answer"] = cfg["new"][0] if q["type"] == "single" else list(cfg["new"])
        q["explanation"] = cfg["explanation"]
        parts = q.setdefault("explanationParts", {})
        parts.update(cfg["explanationParts"])
        if cfg["why"]:
            q["distractorWhy"] = cfg["why"]
        else:
            q.pop("distractorWhy", None)
        print("%s：%r → %r%s" % (qid, cfg["old"], cfg["new"],
                                "（题型→%s）" % cfg["type"] if cfg.get("type") else ""))

    new_text = json.dumps(bank, ensure_ascii=False, indent=1) + "\n"
    if check_only:
        print("--check：未写盘，改动 %d 处" % len(changes))
        return 0
    DATA.write_bytes(new_text.replace("\n", "\r\n").encode("utf-8"))

    back = json.loads(DATA.read_bytes().decode("utf-8"))
    bq = {q["id"]: q for q in back["questions"]}
    bad = []
    for q in back["questions"]:
        if q["type"] not in ("single", "multi"):
            continue
        pa = (q.get("explanationParts") or {}).get("answer") or ""
        m = re.match(r"\s*([A-H](?:\s*[、,，/]\s*[A-H])*)\s*(?=[、,，/（(]|$)", pa)
        if not m:
            continue
        got = sorted(re.findall(r"[A-H]", m.group(1)))
        want = sorted(q["answer"] if isinstance(q["answer"], list) else [str(q["answer"]).strip().upper()])
        if got != want:
            bad.append(q["id"])
    ok = True
    for qid, cfg in FIXES.items():
        good = ans_norm(bq[qid]) == cfg["new"]
        ok = ok and good
        print("回读 %s：answer=%r type=%s %s" % (qid, bq[qid]["answer"], bq[qid]["type"],
                                                "[OK]" if good else "[FAIL]"))
    print("自校验：解析块答案与答案字段不一致 %d 条" % len(bad))
    print("字节：%d -> %d" % (before, len(DATA.read_bytes())))
    if not ok or bad:
        print("[FAIL] 未通过", file=sys.stderr)
        return 3

    REPORT.write_text(json.dumps({
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "basis": "教材《普通高校军事课教程》原文；子代理在生成解析时按语料如实报出冲突",
        "changes": changes,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("清单 → %s" % REPORT)
    print("[PASS] 已修正并回读确认")
    return 0


if __name__ == "__main__":
    sys.exit(main())
