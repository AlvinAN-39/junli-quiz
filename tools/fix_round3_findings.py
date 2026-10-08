#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_round3_findings.py — 第三批复核（90 道可疑题 + 218 道联网核查）确认的错误答案
==================================================================================

来源：2 个可疑题复核子代理 + 4 个联网核查子代理，逐条回到教材/真题/模拟题原文验证。

**确证要改（4 道）**
* `q-0275`「冷兵器时代的典型武器装备有____」
    ABD → **AD**。选项 B「手枪」是火器，教材原文：「在冷兵器时代…中国人最早发明了
    火药，并最早把火器应用于作战中」，手枪不属于冷兵器。
* `q-0333`「按照作战使命可以将巡航导弹分为____」
    AB（海射型/陆射型）→ **CD**（战略/战术）。教材原文：「核武器按照**担负的任务或
    作战使用目的**，分为战略核武器和战术核武器两大类」，题干问「作战使命」即任务/使用目的，
    而海射型、陆射型是按发射平台分类，答非所问。
* `q-0544`「下列不属于俄罗斯武装力量三大军种的是____」
    A（陆军）→ **D**（空降兵）。俄军由陆军、海军、空天军三个军种构成，空降兵属独立兵种，
    显然不属于三大军种。
* `q-0546`「下列不属于美国现役部队组成部分的是____」
    C（海军陆战队）→ **D**（国民警卫队）。教材原文：「现役部队规模约为140万人，
    涵盖陆军、海军、空军、太空军及海军陆战队。预备役部队总数超过120万人，
    包括国民警卫队及联邦后备队」，即国民警卫队属预备役。

**不改，列入待确认（3 道）**
* `q-0064` 国防随「阶级」还是「国家」出现：教材只有「国防是随着国家的产生而出现的」，
  但选项为多选，是否含 A（阶级）属学科口径争议，留待用户裁定。
* `q-0291` 信息化战争需具备的「制权」：子代理建议 ABCD，教材强调的是制信息权为制高点，
  未穷举列举，证据不足以判定原答案 AD 有误。
* `q-0295` 打击目标：子代理建议 AC，另有语料亦支持「重要军事设施」（B），证据互相冲突。

安全设计：按 id 定位、改前断言旧值、同步解析与 `explanationParts`、清理已变成正确答案的
`distractorWhy` 条目；写盘后回读并自校验（解析块字母 == 答案字母）。

用法：
    python tools/fix_round3_findings.py --check
    python tools/fix_round3_findings.py
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
REPORT = ROOT / "qa" / "round3-answer-fix.json"

# id → dict(old, new, explanation, parts_answer, parts_note)
FIXES = {
    "q-0275": {
        "old": ["A", "B", "D"], "new": ["A", "D"],
        "explanation": (
            "正确答案：A、D（长矛、弓箭）\n"
            "教材原文：「在冷兵器时代，我国的武器技术在许多方面都领先于世界。中国人最早发明了火药，"
            "并最早把火器应用于作战中」——手枪属火器（热兵器），不是冷兵器时代的武器装备；"
            "C 火炮同样属火器。\n"
            "提示：原答案含 B（手枪），与「冷兵器时代」的限定冲突，已按教材更正为 A、D。\n"
            "依据：教材《普通高校军事课教程》·中国国防（国防发展历史）"
        ),
        "parts_answer": "A、D（长矛；弓箭）",
        "parts_note": "原答案含 B（手枪），与「冷兵器时代」的限定冲突，已按教材更正为 A、D。",
        "drop_why": ["B"],
    },
    "q-0333": {
        "old": ["A", "B"], "new": ["C", "D"],
        "explanation": (
            "正确答案：C、D（战略巡航导弹、战术巡航导弹）\n"
            "教材原文：「核武器按照担负的任务或作战使用目的，分为战略核武器和战术核武器两大类」，"
            "题干问「按作战使命」分类，对应的是战略 / 战术；而海射型、陆射型是按发射平台划分。\n"
            "提示：原答案 A、B 是按发射平台分类，答非所问，已按教材更正为 C、D。\n"
            "依据：教材《普通高校军事课教程》·信息化装备（核武器分类）"
        ),
        "parts_answer": "C、D（战略巡航导弹；战术巡航导弹）",
        "parts_note": "原答案 A、B 是按发射平台分类，答非所问，已按教材更正为 C、D。",
        "drop_why": ["C", "D"],
    },
    "q-0544": {
        "old": "A", "new": "D",
        "explanation": (
            "正确答案：D（空降兵）\n"
            "俄罗斯武装力量由陆军、海军、空天军三个军种构成，空降兵属独立兵种（与战略火箭军并列），"
            "因此不属于三大军种的是 D。\n"
            "提示：原答案为 A（陆军），与俄军军种构成冲突，已更正为 D。\n"
            "依据：公开军事资料中俄军「三军种两兵种」的构成表述（陆军 / 海军 / 空天军）"
        ),
        "parts_answer": "D（空降兵）",
        "parts_note": "原答案为 A（陆军），与俄军军种构成冲突，已更正为 D。",
        "drop_why": ["D"],
    },
    "q-0546": {
        "old": "C", "new": "D",
        "explanation": (
            "正确答案：D（国民警卫队）\n"
            "教材原文：「现役部队规模约为140万人，涵盖陆军、海军、空军、太空军及海军陆战队。"
            "预备役部队总数超过120万人，包括国民警卫队及联邦后备队」——国民警卫队属预备役。\n"
            "提示：原答案为 C（海军陆战队），但教材把海军陆战队列入现役部队，已更正为 D。\n"
            "依据：教材《普通高校军事课教程》·国家安全（美国军事力量）"
        ),
        "parts_answer": "D（国民警卫队）",
        "parts_note": "原答案为 C（海军陆战队），但教材把海军陆战队列入现役部队，已更正为 D。",
        "drop_why": ["D"],
    },
}

PENDING = [
    {"id": "q-0064", "current": ["A", "B"], "issue": "国防随「阶级」还是「国家」出现：教材仅有「随着国家的产生而出现」，多选是否含阶级属口径争议"},
    {"id": "q-0291", "current": ["A", "D"], "issue": "信息化战争需具备的制权：教材强调制信息权为制高点，未穷举，证据不足以判定 AD 有误"},
    {"id": "q-0295", "current": ["B", "C"], "issue": "打击目标：另有语料支持「重要军事设施」（B），与子代理建议 AC 冲突"},
]


def ans_norm(q):
    a = q["answer"]
    return sorted(a) if isinstance(a, list) else a


def main() -> int:
    check_only = "--check" in sys.argv
    text = DATA.read_text(encoding="utf-8")
    bank = json.loads(text)
    before = len(text.encode("utf-8"))
    by_id = {q["id"]: q for q in bank["questions"]}

    print("=" * 74)
    print("第三批复核确认的错误答案修正")
    print("=" * 74)
    changes = []
    for qid, cfg in FIXES.items():
        q = by_id[qid]
        if ans_norm(q) == cfg["new"]:
            print("%s 已是目标值，跳过（幂等）" % qid)
        else:
            if ans_norm(q) != cfg["old"]:
                print("[FAIL] %s 当前答案 %r 与预期旧值 %r 不符，中止" % (qid, q["answer"], cfg["old"]),
                      file=sys.stderr)
                return 2
            q["answer"] = cfg["new"]
            q["explanation"] = cfg["explanation"]
            parts = q.setdefault("explanationParts", {})
            parts["answer"] = cfg["parts_answer"]
            parts["note"] = cfg["parts_note"]
            changes.append({"id": qid, "before": cfg["old"], "after": cfg["new"]})
            print("%s：%r → %r" % (qid, cfg["old"], cfg["new"]))
        # 无论是否改过答案，都要保证干扰项说明不再否定正确选项
        why = q.get("distractorWhy")
        if isinstance(why, dict):
            for k in cfg["drop_why"]:
                if k in why:
                    del why[k]
                    print("   已删除 %s/%s 的干扰项说明" % (qid, k))

    new_text = json.dumps(bank, ensure_ascii=False, indent=1) + "\n"
    if check_only:
        print("--check 模式：未写盘；改动 %d 处。" % len(changes))
        return 0
    DATA.write_text(new_text, encoding="utf-8")

    back = json.loads(DATA.read_text(encoding="utf-8"))
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
        q = next(x for x in back["questions"] if x["id"] == qid)
        good = ans_norm(q) == cfg["new"]
        ok = ok and good
        print("回读 %s：answer=%r %s" % (qid, q["answer"], "[OK]" if good else "[FAIL]"))
    print("自校验：解析块答案与答案字段不一致 %d 条" % len(bad))
    print("字节：%d -> %d" % (before, len(DATA.read_text(encoding="utf-8").encode("utf-8"))))
    if not ok or bad:
        print("[FAIL] 回读/自校验未通过", file=sys.stderr)
        return 3

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "basis": "教材/真题/模拟题原文 + 子代理复核，逐条回原文验证",
        "changes": changes,
        "pendingUserConfirm": PENDING,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("清单 → %s" % REPORT)
    print("[PASS] 第三批修正完成并回读确认")
    return 0


if __name__ == "__main__":
    sys.exit(main())
