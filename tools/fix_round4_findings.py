#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_round4_findings.py — 修正第三批「答案与教材冲突」（子代理复核时报出）
==========================================================================

三道题都由**教材原文 + 模拟题同题**双重支持，且题目自身的解析文本早已写明正确答案，
只是 `answer` 字段与解析冲突（改答案时漏改字段，或初始解析时误取）。

| 题号 | 题干 | 原答案 | 新答案 | 依据 |
|------|------|--------|--------|------|
| `q-0537` | 两极格局结束后，当今世界出现____并立的态势 | D「多超与多强」 | **A「一超与多强」** | 教材「两极格局结束后，世界出现了“一超”和“多强”并立的态势」 |
| `q-0543` | 两极格局结束后，当今世界战略格局的基本态势是____ | A「美国单极世界已确立」 | **B「一超和多强并立」** | 教材「美国构筑“单极世界”的战略不断推进，但它没有也不可能阻止世界多极化的发展趋势」 |
| `q-0555` | 相对稳定的安全环境中存在的不安全因素包括？ | A、C | **A、B、C、D** | 教材小标题「(二)相对稳定的安全环境中存在着不安全因素」下列四项，选项逐字对应 |

三题的 `distractorWhy` 原先写的是「本题答案定的是 X 那条」——那是**对被改错的答案作循环论证**，
一并按教材重写为具体说明。

安全设计：改前断言旧值、改后回读、并重跑「解析块答案 == 答案字段」自校验。

用法：
    python tools/fix_round4_findings.py --check
    python tools/fix_round4_findings.py
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
REPORT = ROOT / "qa" / "round4-answer-fix.json"

FIXES = {
    "q-0537": {
        "old": "D",
        "new": "A",
        "explanationParts": {
            "answer": "A、“一超”与“多强”",
            "reason": ("教材原文：两极格局结束后，世界出现了“一超”和“多强”并立的态势，"
                       "大国之间的关系不断发生变化与调整，世界上各种政治力量不断分化组合。"),
            "note": "原答案为 D（“多超”与“多强”），与教材原文冲突，已按教材更正为 A。",
        },
        "explanation": (
            "正确答案：A、“一超”与“多强”\n"
            "教材原文：「两极格局结束后，世界出现了“一超”和“多强”并立的态势，大国之间的关系"
            "不断发生变化与调整，世界上各种政治力量不断分化组合，当今世界正经历百年未有之大变局。」\n"
            "提示：原答案为 D（“多超”与“多强”），与教材原文冲突，已按教材更正为 A。\n"
            "依据：教材《普通高校军事课教程》·国家安全（国际战略形势）"
        ),
        "why": {
            "D": "“多超”与教材不符：教材写的是“一超”（美国）与“多强”并立，不是一个以上的超级大国。",
            "B": "“两超”不成立：两极格局结束后只剩美国一个超级大国，不存在两个超级大国并立。",
            "C": "“一超”与“一强”不是教材表述：教材的并立格局是“一超”和“多强”。",
        },
    },
    "q-0543": {
        "old": "A",
        "new": "B",
        "explanationParts": {
            "answer": "B、世界出现“一超”和“多强”并立的态势",
            "reason": ("教材原文：美国构筑“单极世界”的战略不断推进，但它没有也不可能阻止世界多极化"
                       "的发展趋势；两极格局结束后世界出现“一超”和“多强”并立的态势。"),
            "note": "原答案为 A（美国单极世界已经确立），与教材表述冲突，已按教材更正为 B。",
        },
        "explanation": (
            "正确答案：B、世界出现“一超”和“多强”并立的态势\n"
            "教材原文：「当前国际战略形势的主要态势是，美国构筑“单极世界”的战略不断推进，"
            "但它没有也不可能阻止世界多极化的发展趋势。两极格局结束后，世界出现了“一超”和“多强”"
            "并立的态势。」\n"
            "提示：原答案为 A（美国“单极世界”已经确立，其他力量无足轻重），与教材“没有也不可能"
            "阻止世界多极化”的表述冲突，已按教材更正为 B。\n"
            "依据：教材《普通高校军事课教程》·国家安全（国际战略形势）"
        ),
        "why": {
            "A": "教材明确“美国构筑单极世界的战略不断推进，但它没有也不可能阻止世界多极化的发展趋势”，"
                 "说“已经确立、其他力量无足轻重”与教材相反。",
            "C": "两极化格局已经结束，不存在重回美苏两极对峙的态势。",
            "D": "教材指出多极化趋势在发展中，仍有美国这一主导力量，并非“势均力敌、无主导力量”。",
        },
    },
    "q-0555": {
        "old": ["A", "C"],
        "new": ["A", "B", "C", "D"],
        "explanationParts": {
            "answer": "A、B、C、D（四项均属教材所列的不安全因素）",
            "reason": ("教材小标题「(二)相对稳定的安全环境中存在着不安全因素」下列出四项："
                       "西方军事强国对我国安全环境影响深远（美国尤甚）、周边热点地区仍有发生情况突变的可能、"
                       "恐怖主义和民族分裂活动威胁我国安全、外国势力插手台湾问题。四个选项与之一一对应。"),
            "note": "原答案只列 A、C 两项，漏选 B、D，已按教材小标题下的四项补全。",
        },
        "explanation": (
            "正确答案：A、B、C、D\n"
            "教材小标题「(二)相对稳定的安全环境中存在着不安全因素」下列出四项：①西方军事强国对我国"
            "安全环境影响深远（世界军事强国中美国影响尤甚）；②周边热点地区仍有发生情况突变的可能；"
            "③恐怖主义和民族分裂活动威胁我国安全；④外国势力插手台湾问题。四个选项与之一一对应。\n"
            "提示：原答案只列 A、C 两项，漏选 B、D，已按教材原文补全。\n"
            "依据：教材《普通高校军事课教程》·国家安全（周边安全环境）"
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
    print("第三批「答案与教材冲突」修正")
    print("=" * 74)
    changes = []
    for qid, cfg in FIXES.items():
        q = by_id[qid]
        if ans_norm(q) == cfg["new"] and (q.get("explanationParts") or {}).get("answer", "").find("已按教材") < 0:
            print("%s 答案已是目标值（幂等跳过）" % qid)
        else:
            if ans_norm(q) != cfg["old"]:
                print("[FAIL] %s 当前答案 %r 与预期旧值 %r 不符，中止" % (qid, q["answer"], cfg["old"]),
                      file=sys.stderr)
                return 2
            changes.append({"id": qid, "before": q["answer"], "after": cfg["new"]})
            q["answer"] = cfg["new"]
            print("%s：%r → %r" % (qid, cfg["old"], cfg["new"]))
        # 解析与干扰项说明：始终按教材重写（保证与答案一致）
        q["explanation"] = cfg["explanation"]
        parts = q.setdefault("explanationParts", {})
        parts.update(cfg["explanationParts"])
        if cfg["why"]:
            q["distractorWhy"] = cfg["why"]
        else:
            q.pop("distractorWhy", None)

    new_text = json.dumps(bank, ensure_ascii=False, indent=1) + "\n"
    if check_only:
        print("--check：未写盘，改动 %d 处" % len(changes))
        return 0
    DATA.write_bytes(new_text.replace("\n", "\r\n").encode("utf-8"))

    # 回读 + 自校验
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
        print("回读 %s：answer=%r %s" % (qid, bq[qid]["answer"], "[OK]" if good else "[FAIL]"))
    print("自校验：解析块答案与答案字段不一致 %d 条" % len(bad))
    print("字节：%d -> %d" % (before, len(DATA.read_bytes())))
    if not ok or bad:
        print("[FAIL] 未通过", file=sys.stderr)
        return 3

    REPORT.write_text(json.dumps({
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "basis": "教材原文 + 模拟题同题双重支持；题目自身解析早已写对，是 answer 字段与之冲突",
        "changes": changes,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("清单 → %s" % REPORT)
    print("[PASS] 已修正并回读确认")
    return 0


if __name__ == "__main__":
    sys.exit(main())
