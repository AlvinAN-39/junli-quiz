#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_new_questions.py — 本轮新增题目的数据层体检（只看新题，不动数据）。

检查项
------
N1  新题 id 连续、全局唯一，且不与既有题冲突
N2  字段完备：契约要求的字段一个不少，类型正确
N3  答案合法性：单选单字母且在选项内；多选升序去重 ≥2 且都在选项内；判断为布尔
N4  选项：单选/多选 ≥2 项且无空项；判断/填空/简答 options 必须为 []
N5  解析：非空、`explanationParts.answer` 与 `answer` 自洽（与既有 R9 同一口径）
N6  `distractorWhy` 只指向错误选项；多选/单选的干扰项说明覆盖率
N7  章节：chapter 必须在现库 5 章内；section 非空
N8  依据：`explanationSrc` 取值合法；`web` 必须有 URL；`template` 必须是「未收录」口径
N9  与既有题库的重复：题干+选项集合完全一致（应为 0）
N10 新题内部重复：同上
N11 难题标记：是否存在（不判定对错，只报覆盖率）
N12 小节归属（subsection/sectionName）是否为字符串（供复习提纲并入用）

用法：python tools/verify_new_questions.py [新题起始 id，默认 q-1172]
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
BANK = ROOT / "data" / "questions.json"
(ROOT / "work").mkdir(parents=True, exist_ok=True)
OUT = ROOT / "work" / "verify-new-report.json"
CHAPTERS = {"第一章中国国防", "第二章国家安全", "第三章军事思想", "第四章现代战争", "第五章信息化装备"}
VALID_SRC = {"textbook", "manual", "bank", "template", "web"}
REQ = ["id", "type", "stem", "options", "answer", "explanation", "source", "chapter", "section",
       "explanationSrc", "explanationRef", "keyConcept", "keywords", "distractorWhy",
       "explanationParts"]


def main() -> int:
    start = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].startswith("q-") else "q-1172"
    startn = int(start.split("-")[1])
    bank = json.loads(BANK.read_text(encoding="utf-8"))["questions"]
    old = [q for q in bank if int(q["id"].split("-")[1]) < startn]
    new = [q for q in bank if int(q["id"].split("-")[1]) >= startn]
    problems: dict[str, list[str]] = {f"N{i}": [] for i in range(1, 13)}

    # N1
    nums = [int(q["id"].split("-")[1]) for q in new]
    if nums and nums != list(range(startn, startn + len(nums))):
        problems["N1"].append("新题 id 不连续")
    if len(set(q["id"] for q in bank)) != len(bank):
        problems["N1"].append("全库 id 有重复")

    # 重复基线
    oldkey = {(q["stem"], tuple(q.get("options", []))) for q in old}
    seen: dict[tuple, str] = {}
    for q in new:
        key = (q["stem"], tuple(q.get("options", [])))
        if key in oldkey:
            problems["N9"].append(f"{q['id']} 与既有题重复：{q['stem'][:26]}")
        if key in seen:
            problems["N10"].append(f"{q['id']} 与 {seen[key]} 重复：{q['stem'][:26]}")
        seen[key] = q["id"]

        # N2
        miss = [k for k in REQ if k not in q]
        if miss:
            problems["N2"].append(f"{q['id']} 缺字段 {'/'.join(miss)}")
            continue
        if q["type"] not in ("single", "multi", "judge", "fill", "short"):
            problems["N2"].append(f"{q['id']} 题型非法 {q['type']}")
        if not isinstance(q["options"], list) or not isinstance(q["keywords"], list):
            problems["N2"].append(f"{q['id']} options/keywords 不是数组")
        if not isinstance(q["explanationParts"], dict):
            problems["N2"].append(f"{q['id']} explanationParts 不是对象")

        opts = q["options"]
        # N3
        if q["type"] == "single":
            a = q["answer"]
            if not (isinstance(a, str) and len(a) == 1 and "A" <= a <= "D"):
                problems["N3"].append(f"{q['id']} 单选答案非法 {a!r}")
            elif ord(a) - 65 >= len(opts):
                problems["N3"].append(f"{q['id']} 单选答案 {a} 越界（{len(opts)} 项）")
        elif q["type"] == "multi":
            a = q["answer"]
            if not isinstance(a, list) or len(a) < 2:
                problems["N3"].append(f"{q['id']} 多选答案非数组或不足 2 项 {a!r}")
            else:
                if a != sorted(set(a)):
                    problems["N3"].append(f"{q['id']} 多选答案未升序去重 {a}")
                if any(not ("A" <= c <= "D") for c in a):
                    problems["N3"].append(f"{q['id']} 多选答案含非法字母 {a}")
                elif max(ord(c) - 65 for c in a) >= len(opts):
                    problems["N3"].append(f"{q['id']} 多选答案越界（{len(opts)} 项）")
        elif q["type"] == "judge":
            if not isinstance(q["answer"], bool):
                problems["N3"].append(f"{q['id']} 判断答案非布尔 {q['answer']!r}")

        # N4
        if q["type"] in ("single", "multi"):
            if len(opts) < 2:
                problems["N4"].append(f"{q['id']} 选项不足 2 项")
            if any(not str(o).strip() for o in opts):
                problems["N4"].append(f"{q['id']} 存在空选项")
        elif opts:
            problems["N4"].append(f"{q['id']} {q['type']} 不应有选项（{len(opts)} 项）")

        # N5 解析块首行声明的答案字母，必须与答案字段的字母集合完全一致
        #    口径与 verify_app.py「解析块『正确答案』与答案字段一致」一致：
        #    解析常写成「A、B、C、D（主体、对象…）」，故先取「正确答案：」后连续的字母序列。
        if not str(q["explanation"]).strip():
            problems["N5"].append(f"{q['id']} 解析为空")
        p = q["explanationParts"]
        pa = str(p.get("answer", ""))
        if q["type"] in ("single", "multi") and pa:
            # 口径与 verify_app.py 一致：逐个选项字母检查「字母+分隔符」是否出现在解析首行，
            # 覆盖「A、B、C、D（…）」「A、私有制；C、阶级」「A、选项文字」三种实测写法。
            if opts:
                got = [chr(65 + i) for i in range(len(opts))
                       if re.search(re.escape(chr(65 + i)) + r"\s*[、,，/；;（(]", pa)
                       or pa.rstrip().endswith(chr(65 + i))]
                want = sorted(q["answer"] if isinstance(q["answer"], list) else [str(q["answer"]).upper()])
                if got and got != want:
                    problems["N5"].append(f"{q['id']} 解析答案字母 {got} 与答案字段 {want} 不一致")
        # N6
        why = q["distractorWhy"]
        if q["type"] in ("single", "multi") and opts:
            ans_set = set(q["answer"] if isinstance(q["answer"], list) else [q["answer"]])
            wrong = [chr(65 + i) for i in range(len(opts)) if chr(65 + i) not in ans_set]
            all_letters = [chr(65 + i) for i in range(len(opts))]
            bad = [k for k in why if k not in all_letters]
            if bad:
                problems["N6"].append(f"{q['id']} distractorWhy 含非本题选项 {bad}")
            negative = bool(re.search(r"不属于|不包括|不是|不正确的|错误的是|除外|不对的", q["stem"]))
            covered_wrong = any(str(why.get(k, "")).strip() for k in wrong)
            covered_answer = any(str(why.get(k, "")).strip() for k in ans_set)
            # 全选型题（没有错误项）distractorWhy 为空是正确形态，不报问题
            if wrong and not (covered_wrong or (negative and covered_answer)):
                problems["N6"].append(f"{q['id']} 错误项无任何干扰项说明")

        # N7
        if q["chapter"] not in CHAPTERS:
            problems["N7"].append(f"{q['id']} 章节非法 {q['chapter']!r}")
        if not str(q["section"]).strip():
            problems["N7"].append(f"{q['id']} section 为空")

        # N8
        if q["explanationSrc"] not in VALID_SRC:
            problems["N8"].append(f"{q['id']} explanationSrc 非法 {q['explanationSrc']!r}")
        if q["explanationSrc"] == "web" and not str(q["explanationRef"]).strip():
            problems["N8"].append(f"{q['id']} 联网依据缺 URL")
        if q["explanationSrc"] == "template" and str(q["explanationRef"]).strip():
            problems["N8"].append(f"{q['id']} template 却有出处 {q['explanationRef'][:24]}")

        # N11
        if "isHard" not in q:
            problems["N11"].append(f"{q['id']} 缺 isHard")

        # N12 小节归属
        if not isinstance(q.get("subsection", ""), str):
            problems["N12"].append(f"{q['id']} subsection 不是字符串")
        if not isinstance(q.get("sectionName", ""), str):
            problems["N12"].append(f"{q['id']} sectionName 不是字符串")

    summary = {k: len(v) for k, v in problems.items()}
    report = {
        "oldCount": len(old), "newCount": len(new), "newIdFrom": start, "problems": summary,
        "details": {k: v[:40] for k, v in problems.items() if v},
        "byType": {t: sum(1 for q in new if q["type"] == t) for t in ("single", "multi", "judge", "fill", "short")},
        "bySource": {s: sum(1 for q in new if q["source"] == s) for s in ("真题", "模拟题")},
        "byExplanationSrc": {s: sum(1 for q in new if q["explanationSrc"] == s) for s in sorted(VALID_SRC)},
        "hardCount": sum(1 for q in new if q.get("isHard") is True),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"既有 {len(old)} 题；新题 {len(new)} 题（{start} 起）")
    print("题型", report["byType"], "来源", report["bySource"])
    print("依据", report["byExplanationSrc"], "难题", report["hardCount"])
    bad = 0
    for k in sorted(problems):
        n = len(problems[k])
        bad += n
        print(f"  {k}: {n}" + (f"  例：{problems[k][0]}" if n else ""))
    print(f"问题合计 {bad}；报告 → {OUT}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
