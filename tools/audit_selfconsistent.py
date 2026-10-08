#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_selfconsistent.py — 题库「四处自洽」结构性核查
=====================================================

为什么要有这个脚本
------------------
本轮用户报告的「错题本里答案有误、不保真」已被证实为**叙述与答案字段冲突**，
而非判分逻辑错误（判分只读 `q.qa`，即 `normalizeAnswer(q.answer)`）：
  * `q-0288` 解析仍写着旧答案 A，而答案字段是 D；
  * 283 道题的 `distractorWhy` 模板把干扰项称作「正确项」，或对正确选项说
    「不是本考点的规范表述」。
这两类都不由人工发现，只能靠规则扫出来。本脚本把可机器判定的自洽性缺陷
全部列出，作为「改哪里、改了多少」的证据，避免只修个例。

核查的 8 条规则
---------------
  R1 单个答案字母越界（指到不存在的选项，如 4 个选项却写 E）
  R2 题型与答案结构矛盾（multi 答案不足 2 项 / single 答案不止 1 项 / judge 非布尔）
  R3 答案文本中的选项文字与 options 对不上
  R4 解析文本里的「正确答案：X」与 answer 字段冲突
  R5 distractorWhy 模板指代错误（「与正确项 X」的 X 不在 answer；或答案串被塞进单选项）
  R6 distractorWhy 对正确答案写了否定性说明
  R7 完全重复题（题干标准化后相同，且选项集合相同）
  R8 同题干但答案不同（题库内部互相矛盾）
  R9 `explanationParts.answer`（解析块里的「正确答案」行）与 `answer` 字段不一致
     —— 界面同屏会显示两套答案：判分与「参考答案」走 `answer`，
     解析块走 `explanationParts.answer`。改答案时漏改后者即产生此缺陷
     （本轮实测踩到：q-0539 改了 answer 未改 parts.answer）。

输出
----
  qa/selfconsistent-audit.json —— 明细（供逐条处置）
  终端只打印各规则的计数与前若干条样例

用法：
    python tools/audit_selfconsistent.py
    python tools/audit_selfconsistent.py --limit 20
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "questions.json"
REPORT = ROOT / "qa" / "selfconsistent-audit.json"

LETTERS = "ABCDEFGH"

# --- 解析文本里「正确答案」的字母序列（只认明确形态，避免误伤正文）-------------
# 注意：解析经常**引用**题库原文（如「题库：『…正确答案：ABD』」），那些字母属于
# 引用内容，不是本题答案 —— 因此只检查出现在行首/句首的「正确答案：X」，
# 且要求字母序列后面紧接顿号、括号或行尾（排除「A、C4ISR系统」这种把选项文字
# 首字母误当答案字母的情况）。
RE_ANS_HEAD = re.compile(
    r"(?:^|[\n。；;])\s*正确答案[:：]\s*([A-H](?:\s*[、,，/]\s*[A-H](?![A-Za-z0-9\-—]))*、?)(?![A-Za-z0-9\-—])")
RE_ANS_PLAIN = re.compile(
    r"(?:^|[\n。；;])\s*正确选项是\s*([A-H](?:\s*[、,，/]\s*[A-H](?![A-Za-z0-9\-—]))*、?)(?![A-Za-z0-9\-—])")
# 「与正确项 A」/「与正确项 B/C」——模板残留判定
RE_WRONG_REF = re.compile(r"与正确项\s*([A-H](?:\s*/\s*[A-H])*)")
# 解析块「正确答案」行开头的字母序列（要求字母后是顿号/斜杠/括号或行尾，
# 避免把「A、C4ISR系统」里的 C 当成第二个答案字母）
RE_PART_ANSWER = re.compile(r"\s*([A-H](?:\s*[、,，/]\s*[A-H])*)\s*(?=[、,，/（(]|$)")
# 指向正确答案的否定性说明
NEGATIVE_HINTS = ("不是本考点", "不属本考点的规范表述", "查不到", "干扰项")


def norm_stem(s: str) -> str:
    """题干标准化：只留中文、字母、数字，用于重复题判定。"""
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s or "")


def answer_set(q) -> list:
    """答案字母集合（统一大写，排序）。"""
    a = q.get("answer")
    t = q.get("type")
    if t == "multi":
        items = a if isinstance(a, list) else list(str(a))
        return sorted({str(x).strip().upper() for x in items if str(x).strip()})
    if t == "single":
        return [str(a).strip().upper()] if a is not None else []
    return []


def letters_from_text(txt: str) -> list:
    """从一段文本里取「明确指代选项」的字母序列。"""
    out = []
    for rx in (RE_ANS_HEAD, RE_ANS_PLAIN):
        for m in rx.finditer(txt or ""):
            out += [c for c in re.findall(r"[A-H]", m.group(1))]
    return out


def main() -> int:
    limit = 10
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except Exception:
            limit = 10

    bank = json.loads(DATA.read_text(encoding="utf-8"))
    qs = bank["questions"]
    by_id = {q["id"]: q for q in qs}

    findings: dict[str, list] = defaultdict(list)

    for q in qs:
        qid, t = q["id"], q.get("type")
        opts = q.get("options") or []
        n = len(opts)
        ans = answer_set(q)
        letter_ok = [c for c in ans if LETTERS.find(c) >= n]

        # R1 字母越界
        if letter_ok and t in ("single", "multi"):
            findings["R1_letter_out_of_range"].append(
                {"id": qid, "type": t, "answer": ans, "options": n, "bad": letter_ok})

        # R2 题型与答案结构矛盾
        if t == "multi" and len(ans) < 2:
            findings["R2_type_answer_mismatch"].append(
                {"id": qid, "why": "multi 答案不足 2 项", "answer": ans, "stem": q["stem"][:60]})
        if t == "single" and len(ans) != 1:
            findings["R2_type_answer_mismatch"].append(
                {"id": qid, "why": "single 答案不是 1 项", "answer": ans, "stem": q["stem"][:60]})
        if t == "judge" and not isinstance(q.get("answer"), bool):
            findings["R2_type_answer_mismatch"].append(
                {"id": qid, "why": "judge 答案非布尔", "answer": q.get("answer"), "stem": q["stem"][:60]})

        # R3 「正确答案：X（选项文字）」里的文字与 options 对不上
        head = (q.get("explanationParts") or {}).get("answer") or ""
        m = re.match(r"([A-H])\s*[（(](.+?)[）)]\s*$", head.strip())
        if m and n:
            idx = LETTERS.find(m.group(1))
            opt_txt = str(opts[idx]) if 0 <= idx < n else None
            claim = m.group(2).strip()
            if opt_txt is not None and claim and claim not in opt_txt and opt_txt not in claim:
                findings["R3_answer_text_mismatch"].append(
                    {"id": qid, "answerLetter": m.group(1), "claim": claim, "option": opt_txt})

        # R4 解析文本里的答案字母与 answer 字段冲突
        txt = (q.get("explanation") or "") + "\n" + ((q.get("explanationParts") or {}).get("note") or "")
        if t in ("single", "multi"):
            for c in letters_from_text(txt):
                if c not in ans and LETTERS.find(c) < max(n, 1):
                    findings["R4_explanation_answer_conflict"].append(
                        {"id": qid, "type": t, "answer": ans, "textLetter": c,
                         "snippet": txt[max(0, txt.find(c) - 25):txt.find(c) + 25].replace("\n", " ")})
                    break

        # R5 / R6 distractorWhy 模板与答案的冲突
        for k, v in (q.get("distractorWhy") or {}).items():
            if not isinstance(v, str):
                continue
            m = RE_WRONG_REF.search(v)
            if m:
                refd = re.findall(r"[A-H]", m.group(1))
                if len(refd) > 1 or any(c not in ans for c in refd):
                    findings["R5_distractor_wrong_ref"].append(
                        {"id": qid, "key": k, "answer": ans, "refd": refd, "text": v[:60]})
            # R6：对正确选项写了否定性说明
            if k in ans and any(h in v for h in NEGATIVE_HINTS):
                findings["R6_distractor_on_correct"].append(
                    {"id": qid, "key": k, "answer": ans, "text": v[:60]})

    # R7 完全重复题
    groups = defaultdict(list)
    for q in qs:
        key = (norm_stem(q.get("stem")), tuple(sorted(str(x).strip() for x in (q.get("options") or []))))
        groups[key].append(q["id"])
    for key, ids in groups.items():
        if len(ids) > 1:
            findings["R7_duplicate_question"].append({"ids": ids, "stem": key[0][:60]})

    # R8 同题干不同答案（只比客观题：单选/多选/判断。填空与简答的 answer 是文本串，
    #    不构成「答案冲突」，此前把它们算进来会产生 150 条误报）
    by_stem = defaultdict(set)
    ids_by_stem = defaultdict(list)
    for q in qs:
        if q.get("type") not in ("single", "multi", "judge"):
            continue
        s = norm_stem(q.get("stem"))
        by_stem[s].add(tuple(answer_set(q)))
        ids_by_stem[s].append(q["id"])
    for s, answers in by_stem.items():
        if len(answers) > 1:
            findings["R8_stem_answer_conflict"].append(
                {"ids": ids_by_stem[s], "answers": [list(a) for a in answers], "stem": s[:60]})

    # R9 explanationParts.answer（解析块「正确答案」行）与 answer 字段不一致
    #    界面同屏两套答案：判分/参考答案走 answer，解析块走 parts.answer。
    #    口径（2026-10-08 修正）：解析块有三种实测写法
    #      ①「A、B、C、D（捍卫国家主权；…）」②「A、私有制；C、阶级」③「A、选项文字」
    #    旧写法只截取「字母+顿号」直连序列，遇到 ②（字母间夹文字与分号）只拿到第一个字母，
    #    扩容时把 76 道题误报成不一致。改为**逐个选项字母**检查「字母+分隔符」是否出现。
    for q in qs:
        if q.get("type") not in ("single", "multi"):
            continue
        pa = (q.get("explanationParts") or {}).get("answer") or ""
        opts = q.get("options") or []
        if not pa or not opts:
            continue
        letters = [chr(65 + i) for i in range(len(opts))
                   if re.search(re.escape(chr(65 + i)) + r"\s*[、,，/；;（(]", pa)
                   or pa.rstrip().endswith(chr(65 + i))]
        if letters and letters != answer_set(q):
            findings["R9_part_answer_mismatch"].append(
                {"id": q["id"], "type": q["type"], "answer": answer_set(q),
                 "partAnswer": pa[:60]})

    # ---------- 输出 ----------
    print("=" * 74)
    print("题库四处自洽核查：%d 题" % len(qs))
    print("=" * 74)
    titles = {
        "R1_letter_out_of_range": "R1 答案字母越界",
        "R2_type_answer_mismatch": "R2 题型与答案结构矛盾",
        "R3_answer_text_mismatch": "R3 答案文字与选项不符",
        "R4_explanation_answer_conflict": "R4 解析字母与答案冲突",
        "R5_distractor_wrong_ref": "R5 干扰项说明指代错误",
        "R6_distractor_on_correct": "R6 对正确选项写否定说明",
        "R7_duplicate_question": "R7 完全重复题",
        "R8_stem_answer_conflict": "R8 同题干不同答案",
        "R9_part_answer_mismatch": "R9 解析块答案与答案字段不一致",
    }
    total = 0
    for key, title in titles.items():
        items = findings.get(key) or []
        total += len(items)
        print("%-28s %4d" % (title, len(items)))
        for it in items[:limit]:
            print("    %s" % json.dumps(it, ensure_ascii=False)[:150])
    print("-" * 74)
    print("合计待处置：%d" % total)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    # counts 必须把 9 条规则**全部**写出（含 0），否则全 0 时 JSON 里 counts 为空，
    # 复核者无法判断「是真查过且为 0」还是「脚本没跑」。
    all_keys = list(titles.keys())
    REPORT.write_text(json.dumps({
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "totalQuestions": len(qs),
        "rules": {k: titles[k] for k in all_keys},
        "counts": {k: len(findings.get(k) or []) for k in all_keys},
        "findings": {k: (findings.get(k) or []) for k in all_keys},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("明细 → %s" % REPORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
