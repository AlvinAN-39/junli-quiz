#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_known_issues.py — 修正题库中「叙述与答案字段冲突」的结构性缺陷
====================================================================

本轮取证发现的缺陷（全部由脚本可判定，属下述用户确认的「结构性错误」）：

  A. 题型与答案数量矛盾
     * `q-0069`「国防的对内职能是____。」答案仅 C 一项，却标注为多选。
     * `q-0288`「…新的作战方式的有____」答案仅 D 一项，却标注为多选。

  B. 解析文本指向已被改掉的旧答案
     * `q-0288` 解析里仍写着「答案选 A 而排除 B（软杀战）与教材表述不一致」，
       而答案字段已是 D —— 这正是用户报告的「错题本里答案有误、不保真」。

  C. `distractorWhy`（「你选的选项为什么不对」）由模板批量生成，模板把正确项
     字母写死，未按实际答案替换：
     * 259 条文本写成「与正确项 A/B/C 表述相近…」，但多数条目描述的其实是
       **干扰项**（把干扰项称作"正确项"），且多选答案串被塞进单选项描述里
       （出现「与正确项 A/B/C 表述相近」这种不可能成立的表述）。
     * 152 条文本写成「教材中仅零星出现，不是本考点的规范表述。」，其中 18 条
       指向的**正是正确选项**——等于告诉用户"你选的这个不是规范表述"。

处置口径（本轮用户确认）：
  * 结构性错误（题型误标、指向旧答案、指代错误）直接修，不改动任何答案的指向；
  * 修法一律采用「不指代具体字母」的中性措辞，避免再次产生字母与实际答案错位；
  * 全过程不改判分逻辑、不改答案含义，因此不影响判分、进度、错题本归类。

安全设计：
  * 先在内存中改 JSON 对象，再整体序列化写盘（原格式 = json.dumps(indent=1) + 换行）；
  * 写盘前断言：旧模板在全库的出现次数改写后必须为 0；
  * 写盘后**回读**再断言一次；任何一项不成立即以非 0 退出码中止；
  * 同时把受影响的每一道题、每一个字段写进 `qa/distractor-template-fix.json` 备查。

用法：
    python tools/fix_known_issues.py --check   # 预演：只报告，不写盘
    python tools/fix_known_issues.py           # 执行
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
REPORT = ROOT / "qa" / "distractor-template-fix.json"

# ---------------------------------------------------------------------------
# 规则①：「与正确项 X…」→ 中性表述（不指代任何字母）
#   匹配形态包括「与正确项 A」「与正确项 B/C」「与正确项 A/B/D」等
# ---------------------------------------------------------------------------
RE_WRONG_REF = re.compile(r"与正确项\s*[A-H](?:\s*/\s*[A-H])*\s*表述相近、容易混淆，注意区分限定语。")
NEUTRAL_REF = "该表述与正确选项相近，容易混淆，注意区分题干限定的范围。"

# 规则②：「教材中仅零星出现，不是本考点的规范表述。」→ 中性表述
STALE_OBSCURE = "教材中仅零星出现，不是本考点的规范表述。"
NEUTRAL_OBSCURE = "该说法教材中未出现或不属本考点的规范表述。"

# 规则③：distractorWhy 对**正确选项**写了否定性说明 → 改成中性表述
#   成因：模板同时用于「干扰项解释」与「正确项说明」，分配给正确项时就自相矛盾。
#   本表由 tools/audit_selfconsistent.py 的 R6 规则扫出（37 条 / 30 道题）。
OLD_NEG_INCORPUS = "该说法在本软件核对过的教材语料中查不到，属于为本题设置的干扰项。"
OLD_NEG_OBSCURE = "该说法教材中未出现或不属本考点的规范表述。"
NEW_CORRECT_NEUTRAL = "该说法属于本题的正确选项。"
CORRECT_KEY_ENTRIES = [
    ("q-0085", "B"), ("q-0085", "C"), ("q-0128", "B"), ("q-0130", "A"),
    ("q-0224", "A"), ("q-0224", "C"), ("q-0279", "A"), ("q-0282", "B"),
    ("q-0283", "A"), ("q-0324", "A"), ("q-0444", "B"), ("q-0446", "D"),
    ("q-0463", "D"), ("q-0554", "C"), ("q-0559", "C"), ("q-0561", "B"),
    ("q-0568", "A"), ("q-0568", "D"), ("q-0620", "B"), ("q-0679", "A"),
    ("q-0691", "D"), ("q-0694", "A"), ("q-0695", "C"), ("q-0696", "A"),
    ("q-0696", "B"), ("q-0697", "C"), ("q-0697", "D"), ("q-0698", "C"),
    ("q-0698", "D"), ("q-0699", "B"), ("q-0701", "D"), ("q-0808", "C"),
    ("q-0809", "B"), ("q-0811", "B"), ("q-0811", "C"), ("q-0812", "A"),
    ("q-0855", "D"),
]

Q0069_EXPLANATION = (
    "正确答案：C（制止武装颠覆和分裂）\n"
    "国防具有对外与对内两方面职能：防备和抵抗侵略是对外职能，制止武装颠覆和分裂是对内职能。"
    "A「武装侵略」与 B「非武装侵略」是侵略者可能采用的方式，不是国防的职能；"
    "D「防备和抵抗侵略」虽属国防职能，但属对外职能。\n"
    "提示：本题答案已逐题复核确认；原标注为多选，因答案仅一项，已改为单选。\n"
    "依据：教材《普通高校军事课教程》·中国国防"
)
Q0288_EXPLANATION = (
    "正确答案：D（心理战）\n"
    "教材“信息化战争的主要特征”把信息化战争新增的作战样式列为“精确战、网络战、电子战、"
    "情报战和心理战”，并指出信息化战争是在机械化战争原有作战样式之外增添这些新样式。\n"
    "提示：来源：《广东培正学院军事理论》第十四章“信息化战争的主要特征”"
    "（二、作战样式多样化）（联网核查）；运动战属机械化战争原有作战形式，不属新增样式。"
    "原标注为多选，因答案仅一项，已改为单选。\n"
    "依据：《广东培正学院军事理论》第十四章（联网核查）"
)
SWITCH_NOTE = "本题答案已逐题复核确认；原标注为多选，因答案仅一项，已改为单选。"
Q0288_NOTE = (
    "来源：《广东培正学院军事理论》第十四章“信息化战争的主要特征”"
    "（二、作业样式多样化）（联网核查）；运动战属机械化战争原有作战形式，不属新增样式。"
    "原标注为多选，因答案仅一项，已改为单选。"
).replace("作业样式", "作战样式")


def main() -> int:
    check_only = "--check" in sys.argv
    text = DATA.read_text(encoding="utf-8")
    bank = json.loads(text)
    before_bytes = len(text.encode("utf-8"))

    print("=" * 74)
    print("题库结构性缺陷修正（题型误标 / 旧答案残留 / 模板指代错误）")
    print("=" * 74)

    # ---------- 规则① ②：批量改写 distractorWhy ----------
    changed = []          # [{'id','field','key','before','after'}]
    n_rule1 = n_rule2 = 0
    for q in bank["questions"]:
        why = q.get("distractorWhy")
        if not isinstance(why, dict):
            continue
        for k in list(why.keys()):
            v = why[k]
            if not isinstance(v, str):
                continue
            nv = v
            if RE_WRONG_REF.search(nv):
                nv = RE_WRONG_REF.sub(NEUTRAL_REF, nv)
                n_rule1 += 1
            if STALE_OBSCURE in nv:
                nv = nv.replace(STALE_OBSCURE, NEUTRAL_OBSCURE)
                n_rule2 += 1
            if nv != v:
                changed.append({"id": q["id"], "field": "distractorWhy", "key": k,
                                "before": v, "after": nv})
                why[k] = nv
    print("规则①「与正确项 X 表述相近…」改写：%d 条" % n_rule1)
    print("规则②「教材中仅零星出现…」改写  ：%d 条" % n_rule2)

    # ---------- 规则③：对正确选项写否定说明的条目 ----------
    n_rule3 = 0
    for qid, key in CORRECT_KEY_ENTRIES:
        q = next((x for x in bank["questions"] if x["id"] == qid), None)
        if q is None:
            print("[FAIL] 规则③ 找不到题目 %s" % qid, file=sys.stderr)
            return 5
        why = q.get("distractorWhy") or {}
        old = why.get(key)
        if old not in (OLD_NEG_INCORPUS, OLD_NEG_OBSCURE):
            print("[FAIL] 规则③ %s/%s 当前文本与预期不符：%r" % (qid, key, old), file=sys.stderr)
            return 5
        why[key] = NEW_CORRECT_NEUTRAL
        changed.append({"id": qid, "field": "distractorWhy", "key": key,
                        "before": old, "after": NEW_CORRECT_NEUTRAL})
        n_rule3 += 1
    print("规则③ 对正确选项的否定说明改为中性：%d 条" % n_rule3)

    # ---------- 规则④：类型误标（幂等：已是 single 且答案一致就跳过）----------
    by_id = {q["id"]: q for q in bank["questions"]}
    for qid, want in (("q-0069", "C"), ("q-0288", "D")):
        q = by_id[qid]
        if q["type"] != "multi" or not (isinstance(q["answer"], list) and len(q["answer"]) == 1):
            if q["type"] == "single" and q["answer"] == want:
                print("%s：已是 single/answer=%r，跳过（幂等）" % (qid, want))
                continue
            print("[FAIL] %s 状态与预期不符：type=%s answer=%r"
                  % (qid, q["type"], q["answer"]), file=sys.stderr)
            return 2
        q["type"] = "single"
        q["answer"] = q["answer"][0]
        print("%s：type=multi→single，answer=%r（答案指向未变）" % (qid, q["answer"]))

    # 解析文本按真实答案重写（幂等：已重写过就不再覆盖）
    q = by_id["q-0069"]
    if "已改为单选" not in (q.get("explanation") or ""):
        q["explanation"] = Q0069_EXPLANATION
        q["explanationParts"]["answer"] = "C（制止武装颠覆和分裂）"
        q["explanationParts"]["reason"] = (
            "国防的对内职能是制止武装颠覆和分裂；防备和抵抗侵略属国防的对外职能，"
            "武装侵略与非武装侵略是侵略者的方式而非国防的职能。")
        q["explanationParts"]["note"] = SWITCH_NOTE
        q["distractorWhy"] = {
            "B": "非武装侵略是侵略者可能采用的方式，不是国防的职能；能涵盖武装侵略与和平演变等"
                 "非武装手段的对内职能是制止武装颠覆和分裂。"}
        print("q-0069 解析文本已重写")

    q = by_id["q-0288"]
    if "已改为单选" not in (q.get("explanation") or ""):
        q["explanation"] = Q0288_EXPLANATION
        q["explanationParts"]["note"] = Q0288_NOTE
        print("q-0288 解析文本已重写")

    # ---------- 写盘前的全局断言 ----------
    new_text = json.dumps(bank, ensure_ascii=False, indent=1) + "\n"
    problems = []
    if RE_WRONG_REF.search(new_text):
        problems.append("仍有「与正确项 X 表述相近」残留")
    if STALE_OBSCURE in new_text:
        problems.append("仍有「教材中仅零星出现」残留")
    # 断言：对正确选项的否定说明必须清零（对干扰项使用这两句是合理的，故按答案集合判定）
    n_bad = 0
    for q in bank["questions"]:
        a = q.get("answer")
        ans = set(a) if isinstance(a, list) else {str(a)}
        for k, v in (q.get("distractorWhy") or {}).items():
            if isinstance(v, str) and k in ans and (OLD_NEG_INCORPUS in v or OLD_NEG_OBSCURE in v):
                n_bad += 1
    if n_bad:
        problems.append("仍有 %d 条对正确选项的否定说明" % n_bad)
    if "答案选 A 而排除" in new_text:
        problems.append("仍有「答案选 A 而排除」残留")
    if problems:
        for p in problems:
            print("[FAIL] %s" % p, file=sys.stderr)
        return 3
    print("写盘前断言：旧模板与新冲突文本均已清零")

    if check_only:
        print("--check 模式：未写盘。受影响条目 %d 条，涉及题目 %d 道。"
              % (len(changed), len({c["id"] for c in changed})))
        return 0

    DATA.write_text(new_text, encoding="utf-8")

    # ---------- 回读验证（铁律 20）----------
    back_text = DATA.read_text(encoding="utf-8")
    back = json.loads(back_text)
    bq = {x["id"]: x for x in back["questions"]}
    ok = True
    for qid, want in (("q-0069", "C"), ("q-0288", "D")):
        good = bq[qid]["type"] == "single" and bq[qid]["answer"] == want
        ok = ok and good
        print("回读 %s：type=%s answer=%r %s"
              % (qid, bq[qid]["type"], bq[qid]["answer"], "[OK]" if good else "[FAIL]"))
    left = []
    if RE_WRONG_REF.search(back_text):
        left.append("与正确项 X")
    if STALE_OBSCURE in back_text:
        left.append("仅零星出现")
    if "答案选 A 而排除" in back_text:
        left.append("答案选 A 而排除")
    # R5/R6 自校验：模板指代错误与「对正确选项的否定说明」必须为 0
    n_r5 = n_r6 = 0
    for q in back["questions"]:
        a = q.get("answer")
        ans = set(a) if isinstance(a, list) else {str(a)}
        for k, v in (q.get("distractorWhy") or {}).items():
            if not isinstance(v, str):
                continue
            mm = RE_WRONG_REF.search(v)
            if mm:
                refd = re.findall(r"[A-H]", mm.group(1))
                if len(refd) > 1 or any(c not in ans for c in refd):
                    n_r5 += 1
            if k in ans and (OLD_NEG_INCORPUS in v or OLD_NEG_OBSCURE in v):
                n_r6 += 1
    print("回读自校验：R5 指代错误 %d 条、R6 对正确项写否定说明 %d 条（均应为 0）" % (n_r5, n_r6))
    if n_r5 or n_r6:
        left.append("R5=%d R6=%d" % (n_r5, n_r6))
    print("回读旧文本残留：%s" % (left or "0（全部清除）"))
    print("题数：%d  字节：%d -> %d（%+.1f%%）"
          % (len(back["questions"]), before_bytes, len(back_text.encode("utf-8")),
             (len(back_text.encode("utf-8")) - before_bytes) / before_bytes * 100))
    if not ok or left:
        print("[FAIL] 回读未通过", file=sys.stderr)
        return 4

    # ---------- 受影响清单落盘备查 ----------
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "rule1_neutralRef": {"count": n_rule1, "text": NEUTRAL_REF},
        "rule2_neutralObscure": {"count": n_rule2, "text": NEUTRAL_OBSCURE},
        "rule3_neutralCorrect": {"count": n_rule3, "text": NEW_CORRECT_NEUTRAL},
        "typeFixed": ["q-0069", "q-0288"],
        "items": changed,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("受影响清单 → %s（%d 条）" % (REPORT, len(changed)))
    print("[PASS] 结构性缺陷修正完成并回读确认")
    return 0


if __name__ == "__main__":
    sys.exit(main())
