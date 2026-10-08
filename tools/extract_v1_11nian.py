#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_v1_11nian.py — 解析【第一版】题库的 2011 年原卷为结构化题目。

背景与口径（本轮用户裁定）
--------------------------
* 第一版题库里**唯一没被第二版覆盖**的只有 2011 年真题（`整理前/真题/已提取真题/11年.txt`）。
  其余年份（2012/2015/2016/2022/2023/2024）的题目都已进现库。
* 用户口径：「只收能做题且答案明确的」。
* 源文件是 Word 转 txt，结构是**两段式**（实测）：
    - 题干区：`一、判断题`(行 8-30) + `二、选择题`(行 32-127)
    - 答案区：`【参考答案】`(行 135) 之后，形如 `N、答案：正确。` / `N、正确答案：a`
* 已知源缺陷（照录，不臆改）：
    - 判断题第 5 题答案原文「1840年的叶片战争」疑为「鸦片战争」笔误（源文件说明已注明）
    - 选择题有两处编号都是「11、」，答案也是两条（c / a）→ **无法判定归属，丢弃该编号**
    - 选择题选项数不足 4（3 项 × 多数）→ 不补第 4 项，解析里如实标注

输出：`work/v1-11nian.json`（`work/` 由脚本自动创建）
    结构：{"judge":[{n,stem,answer,note}], "choice":[{n,stem,options,answer,note}], "dropped":[...]}

用法：python tools/extract_v1_11nian.py
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
SRC = Path(r"D:\.Study\大学\军训期间\军理课\【第一版】题库\整理前\真题\已提取真题\11年.txt")
WORK = ROOT / "work"
WORK.mkdir(parents=True, exist_ok=True)
OUT = WORK / "v1-11nian.json"

QNUM_RE = re.compile(r"^\s*(\d{1,3})\s*[、.]\s*(\S.*)$")
OPT_RE = re.compile(r"^\s*([a-eA-E])\s*[、.]\s*(\S.*)$")
SEC_RE = re.compile(r"^\s*([一二三四五六七八九十]+)\s*[、.]\s*(.*)$")
ANS_JUDGE_RE = re.compile(r"^\s*(\d{1,3})\s*[、.]\s*答案[：:]\s*(正确|错误)[。.]?\s*(.*)$")
ANS_CHOICE_RE = re.compile(r"^\s*(\d{1,3})\s*[、.]\s*(?:正确答案|正确答难|正确答案)\s*[：:]\s*([a-eA-E])\s*$")


def main() -> int:
    if not SRC.exists():
        print(f"!! 源文件不存在：{SRC}")
        return 2
    lines = SRC.read_text(encoding="utf-8", errors="replace").splitlines()

    # --- 段落定位 ---
    secs = [(i, m.group(2).strip()) for i, ln in enumerate(lines)
            for m in [SEC_RE.match(ln)] if m and m.group(2).strip() in ("判断题", "选择题", "思考题")]
    ans_start = next((i for i, ln in enumerate(lines) if ln.strip().startswith("【参考答案】")),
                     len(lines))
    print(f"段落：{secs}")
    print(f"答案区起点：{ans_start}")

    # --- 题干区切块（判断题区 / 选择题区）---
    judge_zone = [i for i, n in secs if n == "判断题" and i < ans_start]
    choice_zone = [i for i, n in secs if n == "选择题" and i < ans_start]
    if not judge_zone or not choice_zone:
        print("!! 未能定位题干区段落")
        return 3
    j0, c0 = judge_zone[0], choice_zone[0]
    c1 = next((i for i, n in secs if n == "思考题" and i > c0), ans_start)

    judges: list[dict] = []
    for i in range(j0 + 1, c0):
        m = QNUM_RE.match(lines[i])
        if m:
            judges.append({"n": m.group(1), "stem": m.group(2).strip()})

    choices: list[dict] = []
    cur: dict | None = None
    for i in range(c0 + 1, c1):
        ln = lines[i]
        om = OPT_RE.match(ln)
        qm = QNUM_RE.match(ln)
        if qm and not om:
            if cur:
                choices.append(cur)
            cur = {"n": qm.group(1), "stem": qm.group(2).strip(), "options": []}
        elif om and cur is not None:
            cur["options"].append({"letter": om.group(1).upper(), "text": om.group(2).strip()})
        elif cur is not None and ln.strip():
            cur["stem"] += " " + ln.strip()
    if cur:
        choices.append(cur)

    # --- 答案区 ---
    jans: dict[str, dict] = {}
    cans: dict[str, list[str]] = {}
    for i in range(ans_start, len(lines)):
        mj = ANS_JUDGE_RE.match(lines[i])
        if mj:
            jans[mj.group(1)] = {"verdict": mj.group(2), "note": mj.group(3).strip()}
            continue
        mc = ANS_CHOICE_RE.match(lines[i])
        if mc:
            cans.setdefault(mc.group(1), []).append(mc.group(2).upper())

    print(f"判断题题干 {len(judges)} 题，答案 {len(jans)} 条；选择题题干 {len(choices)} 题，答案 {len(cans)} 条组")

    dropped: list[dict] = []
    out_judge: list[dict] = []
    for j in judges:
        a = jans.get(j["n"])
        if not a:
            dropped.append({"kind": "judge", "n": j["n"], "reason": "原卷无答案", "stem": j["stem"][:40]})
            continue
        out_judge.append({"n": j["n"], "stem": j["stem"],
                          "answer": a["verdict"] == "正确", "note": a["note"]})

    out_choice: list[dict] = []
    for c in choices:
        ans = cans.get(c["n"], [])
        if not ans:
            dropped.append({"kind": "choice", "n": c["n"], "reason": "原卷无答案", "stem": c["stem"][:40]})
            continue
        if len(ans) > 1:
            dropped.append({"kind": "choice", "n": c["n"],
                            "reason": f"原卷编号重复，答案有 {len(ans)} 条（{'/'.join(ans)}）无法判定归属",
                            "stem": c["stem"][:40]})
            continue
        if len(c["options"]) < 3:
            dropped.append({"kind": "choice", "n": c["n"],
                            "reason": f"选项仅 {len(c['options'])} 个，不足 3 项", "stem": c["stem"][:40]})
            continue
        letters = [o["letter"] for o in c["options"]]
        if ans[0] not in letters:
            dropped.append({"kind": "choice", "n": c["n"],
                            "reason": f"答案 {ans[0]} 不在选项 {letters} 中", "stem": c["stem"][:40]})
            continue
        # 数据契约规定单选答案必须是 A–D；原卷第 5 题（嫦娥一号）只有 5 个选项、答案 E，
        # 且本题现有 4 项版本已在题库中 → 丢弃，不硬改字母。
        if ans[0] not in "ABCD":
            dropped.append({"kind": "choice", "n": c["n"],
                            "reason": f"答案 {ans[0]} 超出 A–D（原卷 {len(c['options'])} 个选项），契约不支持",
                            "stem": c["stem"][:40]})
            continue
        out_choice.append({"n": c["n"], "stem": c["stem"],
                           "options": [o["text"] for o in c["options"]],
                           "answer": ans[0], "note": f"原卷 {len(c['options'])} 个选项"})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source_file": str(SRC),
        "judge": out_judge, "choice": out_choice, "dropped": dropped,
        "counts": {"judge": len(out_judge), "choice": len(out_choice), "dropped": len(dropped)},
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"可用：判断题 {len(out_judge)} 题、选择题 {len(out_choice)} 题；丢弃 {len(dropped)} 条")
    for d in dropped:
        print(f"   丢弃 [{d['kind']} {d['n']}] {d['reason']} | {d['stem']}")
    print(f"→ {OUT}")
    # 题面/答案抽样自检（防止解析错位）
    for j in out_judge[:3]:
        print(f"   J{j['n']} ans={j['answer']} {j['stem'][:44]}")
    for c in out_choice[:3]:
        print(f"   C{c['n']} ans={c['answer']} opts={len(c['options'])} {c['stem'][:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
