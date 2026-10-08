#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_explanations.py — 校正并改善已有解析
=======================================

做两件事（对应用户要求「修正已有解析中的错误」+「更清晰便于理解」）：

## 一、修正错误
实测三类真错（诊断脚本 `diag_explanations.py` 给出计数）：
  ① **排版噪声**（101 道）：解析里是 `( 一 ) 古 代 国 防中国古代国防始于公元前 21 世纪`，
     PDF 提取时字间插了空格 —— 用户看到的像乱码。→ 由 `explain_text.clean_evidence` 清理。
  ② **依据与题干/答案无关**（~115 道候选，其中一部分是明确的答非所问）：
     例如「精确制导武器直接命中概率超过____」答案是 `50%`，
     而引用的依据是「陆军信息化装备达到50%以上，海军和空军则达到70%以上」——
     数字对上了，讲的却是完全另一件事。→ 加**依据校验闸**：
     依据句必须与**答案**实质重合（连续实词片段 ≥0.4 或短答案整串命中），
     否则判为不可信依据，降级为「未收录直接出处」的如实说明（宁可短，不可错）。
  ③ **截断**（8 道）与被过长段落淹没：→ 只保留**最相关的那一句**并修剪到 ~120 字。

## 二、更清晰
把解析拆成结构化字段，前端分行加标签渲染：
  `explanationParts = {answer, reason, note, ref}`
  * answer → 「正确答案」（有明确答案时）
  * reason → 「为什么」（教材原句）
  * note   → 「提示」（存疑/核验范围说明）
  * ref    → 「依据出处」
同时保留 `explanation` 纯文本（供搜索/导出/旧路径）。

原则不变：**宁可短、不可错**。校验不过就如实说「未收录直接出处」，不硬凑依据。
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import gen_explanations as G           # noqa: E402
from explain_text import (             # noqa: E402
    clean_evidence, split_sentences, trim_sentence, structure, render_text,
)

BANK = ROOT / "data" / "questions.json"
LETTERS = "ABCDEFGH"


def answer_display(q) -> str:
    t = q["type"]
    opts = q.get("options") or []
    if t == "single":
        i = LETTERS.index(q["answer"]) if q["answer"] in LETTERS else -1
        return q["answer"] + ("、" + opts[i] if 0 <= i < len(opts) else "")
    if t == "multi":
        names = []
        for a in q["answer"]:
            i = LETTERS.index(a)
            if i < len(opts):
                names.append(opts[i])
        return "、".join(q["answer"]) + ("（" + "；".join(names) + "）" if names else "")
    if t == "judge":
        return "正确" if q["answer"] is True else "错误"
    if t == "fill":
        return "；".join(q["answer"]) if isinstance(q["answer"], list) else str(q["answer"])
    return "见下方参考答案"


def answer_plain(q) -> str:
    """用于「依据校验」的答案文本（尽量短而具体）。"""
    t = q["type"]
    opts = q.get("options") or []
    if t == "single":
        i = LETTERS.index(q["answer"]) if q["answer"] in LETTERS else -1
        return opts[i] if 0 <= i < len(opts) else ""
    if t == "multi":
        return "".join(opts[LETTERS.index(a)] for a in q["answer"]
                       if LETTERS.index(a) < len(opts))
    if t == "fill" and isinstance(q["answer"], list) and q["answer"]:
        return q["answer"][0]
    return ""


def extract_evidence(exp: str) -> str:
    """从旧解析里把「教材原句」部分取出来（去掉我们加的答案抬头与出处尾巴）。"""
    s = exp or ""
    s = re.split(r"本题库未收录", s)[0]
    s = re.sub(r"^正确答案[：:][^。]*。?", "", s)
    s = re.sub(r"^(已人工(校订|修正)答案[^：:]*[：:][^　]*)\s*", "", s)
    s = re.sub(r"依据[：:].*$", "", s)
    s = re.sub(r"相关表述[：:]\s*", "", s)
    s = re.sub(r"^[^—]{0,40}—\s*", "", s)          # 去掉「答案 — 」前缀
    s = re.sub(r"^参考答案见下方。?\s*", "", s)
    s = re.sub(r"教材相关表述[：:]\s*", "", s)
    s = re.sub(r"^(正确|错误)。.*?（由单选题派生，原题 [^）]*）。", "", s)
    s = re.sub(r"依据[：:]", "", s)
    return clean_evidence(s)


# 纯数字/日期/百分比类答案：不能仅凭「数字巧合」就认定教材依据成立。
# 实测反例 q-0730：题干问「精确制导武器直接命中概率超过____」答案 50%，
# 而命中的句子是「陆军信息化装备达到50%以上，海军和空军则达到70%以上」——
# 数字对上了，讲的却是完全另一件事。
NUMERIC_ANSWER_RE = re.compile(r"^[\d０-９.%％\-—~～至到年月日个条项种类次届期元人倍万亿分]+$")


def evidence_ok(ev: str, answer: str, stem: str) -> tuple[bool, str]:
    """判断这段依据是否**真的支持该答案**。

    判据：
      * 答案短（≤6 字）→ 要求整串命中，或与依据的连续片段占比 ≥0.5；
      * 答案长 → 连续实词片段占比 ≥0.4；
      * **纯数字/日期型答案**（`50%`/`1997年`）→ 额外要求依据与题干有 ≥2 个关键词重合，
        否则极易「数字巧合」型错配；
      * 依据与题干需有共同关键词，避免答非所问。
    返回 (是否可信, 原因)。
    """
    if not ev or len(ev) < 6:
        return False, "依据为空或过短"
    if not answer:
        kw = [k for k in G.keywords(stem) if len(k) >= 3]
        if kw and not any(k in ev for k in kw):
            return False, "依据与题干无共同关键词"
        return True, ""

    fit = G.span_fit(answer, ev)
    a = G.squeeze(answer)
    hit_full = len(a) >= 2 and a in G.squeeze(ev)
    kw = [k for k in G.keywords(stem) if len(k) >= 3]
    kw_hit = sum(1 for k in kw if k in ev)
    numeric = bool(NUMERIC_ANSWER_RE.match(a))

    if numeric:
        # 数字型答案：必须有足够的题干关键词支撑，单靠数字命中不算
        if kw_hit >= 2 and (hit_full or fit >= 0.8):
            return True, ""
        return False, f"数字型答案疑为巧合命中(kw={kw_hit},fit={fit:.2f})"

    if len(a) <= 6:
        # fit=1.00 意味着答案整串在依据里（近乎逐字支持）→ 无需再要求题干关键词
        if fit >= 0.9:
            return True, ""
        if hit_full and kw_hit >= 1:
            return True, ""
        if fit >= 0.5 and kw_hit >= 1:
            return True, ""
        return False, f"短答案未在依据中出现(fit={fit:.2f},kw={kw_hit})"
    # 长答案同理：几乎整句命中时，关键词要求放宽
    if fit >= 0.9:
        return True, ""
    if fit >= 0.4 and (kw_hit >= 1 or fit >= 0.6):
        return True, ""
    return False, f"依据与答案重合不足(fit={fit:.2f},kw={kw_hit})"


def best_reason_sentence(ev: str, answer: str, stem: str) -> str:
    """从依据段落里挑出**最相关**的一句并修剪长度。"""
    sents = split_sentences(ev)
    if not sents:
        return trim_sentence(ev)
    if len(sents) == 1:
        return trim_sentence(sents[0])
    scored = []
    for s in sents:
        fit = G.span_fit(answer, s) if answer else 0.0
        kw = sum(1 for k in G.keywords(stem) if len(k) >= 3 and k in s)
        scored.append((fit * 2.0 + kw, s))
    scored.sort(key=lambda x: -x[0])
    return trim_sentence(scored[0][1])


def main() -> int:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = bank["questions"]
    stats: Counter[str] = Counter()
    downgraded: list[dict] = []

    for q in qs:
        old = (q.get("explanation") or "").strip()
        src = q.get("explanationSrc") or ""
        manual = src == "manual" or "人工校订" in old or "人工修正" in old
        ans_disp = answer_display(q)
        ans_plain = answer_plain(q)
        ref = (q.get("explanationRef") or "").strip()

        # 已有「人工校订」说明的：保留其依据文本，作为 note 的一部分
        manual_note = ""
        if manual:
            m = re.search(r"（([^）]*发现源答案串切分有误[^）]*)）", old)
            manual_note = m.group(1) if m else "已人工校订答案"

        ev_raw = extract_evidence(old)
        ev = clean_evidence(ev_raw)

        # ---- 依据校验 ----
        ok, why = evidence_ok(ev, ans_plain, q["stem"])
        if manual and not ok:
            # 人工校订的依据是人工写的，不参与自动校验
            ok, why = True, ""
        if ok:
            reason = best_reason_sentence(ev, ans_plain, q["stem"])
            note = manual_note
            if src == "template" or not ref:
                src_new = src if src in ("manual",) else ("bank" if q["type"] in ("judge", "fill") else "textbook")
            else:
                src_new = src
        else:
            reason = ""
            note = manual_note
            if src in ("textbook", "manual") and not manual:
                src_new = "template"
                downgraded.append({"id": q["id"], "why": why,
                                   "old": old[:110], "answer": ans_plain[:30]})
            else:
                src_new = src or "template"

        # ---- 结构化 ----
        if q["type"] == "short":
            parts = structure(reason=reason, note=note or "参考答案见下方",
                              ref=ref if ok else "")
            if not reason:
                parts = structure(note="本题库收录的是原卷参考答案要点，见下方",
                                  ref=ref if ok else "")
        elif q["type"] == "judge":
            parts = structure(answer=ans_disp, reason=reason,
                              note=note or ("由单选题派生，判断该表述是否与教材一致"
                                            if "派生" in old else ""),
                              ref=ref if ok else "")
        else:
            parts = structure(answer=ans_disp, reason=reason,
                              note=note or ("" if ok else "本题库未收录教材中的直接出处，建议对照原卷核实"),
                              ref=ref if ok else "")

        q["explanationParts"] = parts
        q["explanation"] = render_text(parts)
        q["explanationSrc"] = src_new
        if not ok:
            q["explanationRef"] = ""
        stats[src_new] += 1
        stats["downgraded" if (not ok and src_new == "template"
                               and src in ("textbook", "manual") and not manual) else "kept"] += 1

    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- 报告 ----
    noise_left = sum(1 for q in qs
                     if re.search(r"[\u4e00-\u9fff]\s[\u4e00-\u9fff]", q.get("explanation") or ""))
    print("=" * 74)
    print("解析校正报告")
    print("=" * 74)
    print(f"总题数            : {len(qs)}")
    print(f"依据分布          : {dict((k, v) for k, v in stats.items() if k != 'kept' and k != 'downgraded')}")
    print(f"保留下教材依据    : {stats['kept']}")
    print(f"因依据不可信而降级: {stats['downgraded']}（改为如实说明，不再挂靠错误出处）")
    print(f"清理后仍含字间空格: {noise_left}（应为 0）")
    L = [len(q.get("explanation") or "") for q in qs]
    print(f"解析长度          : 平均 {sum(L)/len(L):.0f}，最长 {max(L)}")
    print()
    if downgraded:
        print("降级样例（原依据与答案/题干不符）:")
        for d in downgraded[:8]:
            print(f"  {d['id']}  答案={d['answer']}  ← {d['why']}")
            print(f"      原依据: {d['old']}")
    print()
    print("=== 抽样：结构化后的解析 ===")
    for q in qs:
        if q["id"] in ("q-0001", "q-0005", "q-0730", "q-0288", "q-0028", "q-1117"):
            print(f"\n[{q['id']} {q['type']}/{q.get('explanationSrc')}] {q['stem'][:52]}")
            for k, v in (q.get("explanationParts") or {}).items():
                print(f"    {k:7}: {v[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
