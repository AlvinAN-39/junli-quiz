#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_distractor_contrast.py — 把「你选的选项为什么不对」从模板话术改成具体对比
==============================================================================

要解决的缺陷（用户报告）
------------------------
答错时显示的说明是模板句，例如：
    「该表述与正确选项相近，容易混淆，注意区分题干限定的范围。」
用户的原话是「说了等于没说」——他要知道**自己把什么和什么搞混了**。

实测证据（这决定了本脚本可行）
------------------------------
教材原文里本来就有对照句：
    「中国古代兵役制度随着各个历史时期政治、经济、人口状况和军事需要而不断发展变化，
      如秦汉的征兵制、隋唐的府兵制、宋朝的募兵制、明朝的卫所兵役制、清初的八旗制等。」
所以「秦汉时期的兵役制度」这题选错时，完全可以写出：
    「募兵制是宋朝的兵役制度，不是秦汉的。」

生成策略（三级，逐级回退，宁缺勿造）
------------------------------------
  ① 同句对照（强条件）：语料里有一句**同时出现**该干扰项与某个**正确选项**的完整文本，
     且二者都紧跟在各自的范围词之后 → 写「X 是 <范围> 的…，不是本题所问的 <题干范围>」。
     （实测 q-0021「秦汉时期的兵役制度」正是此类：教材同句并列
       「秦汉的征兵制、隋唐的府兵制、宋朝的募兵制…」。）
  ② 归属判定（强条件）：干扰项前 12 字内紧跟一个**与题干限定不同**的范围词，
     即教材明写「<其它范围>的<该选项>」 → 写「该选项指的是<其它范围>的…」。
  ③ 其余一律**不生成**，如实进入待补清单，绝不编造。

  ⚠ 反面教训（本脚本第一版踩到）：初版只要「同句出现」就用，
    结果生成出「“1937”属日本」「“政府”属中国」这类错误归属——**宁可漏，不可错**。
    因此两条都必须带「范围词」，且距离受控。

写入方式：只改 `distractorWhy` 里**干扰项**对应的文字；正确选项不写。
输出：`qa/distractor-contrast.json`（明细与统计）、
      `qa/distractor-contrast-pending.json`（需人工补写的清单）

用法：
    python tools/gen_distractor_contrast.py --check   # 只统计与抽样，不写盘
    python tools/gen_distractor_contrast.py           # 写盘
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
CORPUS = ROOT / "build" / "text" / "1-textbook.txt"
REPORT = ROOT / "qa" / "distractor-contrast.json"
PENDING = ROOT / "qa" / "distractor-contrast-pending.json"

LETTERS = "ABCDEFGH"
# 题干里可能出现的「范围/时期」限定词：用于判定干扰项是否属于别的范围
SCOPE_WORDS = [
    "秦汉", "秦朝", "汉朝", "隋唐", "唐朝", "隋朝", "宋朝", "北宋", "南宋", "明朝", "清朝", "清初",
    "古代", "近代", "现代", "当代", "春秋", "战国", "三国", "元朝", "民国",
    "中国", "美国", "俄罗斯", "苏联", "日本", "印度", "英国", "法国", "德国",
    "陆军", "海军", "空军", "空天军", "战略", "战术", "信息化", "机械化",
]
# 「范围词 + 的 + 概念」的匹配：捕获范围词本身，用于生成「X 是<范围>的」
SCOPE_ALT = "(%s)" % "|".join(SCOPE_WORDS)

# 模板句：这些是要被替换掉的对象（命中任一即视为「等于没说」）
TPL_NEUTRAL = "该表述与正确选项相近，容易混淆，注意区分题干限定的范围。"
TPL_VAGUE = "属于相关但错误的选项，注意题干限定的范围。"
TPL_NOCORPUS = "该说法在本软件核对过的教材语料中查不到，属于为本题设置的干扰项。"
TPL_OBSCURE = "该说法教材中未出现或不属本考点的规范表述。"
TPL_RIGHT = "该说法教材中有，但指向的不是本题所问的考点。"
TPL_NEG = "它属于该考点包含的内容，但本题问的是“不属于”的那一项。"
TEMPLATES = {TPL_NEUTRAL, TPL_VAGUE, TPL_NOCORPUS, TPL_OBSCURE, TPL_RIGHT, TPL_NEG}


def norm(text: str) -> str:
    """规范化：去控制字符、去汉字间空格、统一标点（与审计脚本同口径）。"""
    t = "".join(ch for ch in (text or "") if ch == "\n" or ch >= " ")
    t = t.replace("\u3000", " ").replace("（", "(").replace("）", ")")
    t = t.replace("，", ",").replace("。", ".").replace("、", ",")
    t = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", t)
    return re.sub(r"\s+", "", t)


# 「<范围>的<概念>」配对：范围词后 0~8 字内出现「的」再接概念（概念取 2~12 字）
#   例：「秦汉的征兵制」「隋唐的府兵制」→ (秦汉, 征兵制) / (隋唐, 府兵制)
#   只有这种**教材明写**的配对才用于生成，避免「距离近就算关联」的噪声。
RE_SCOPE_PAIR = re.compile(SCOPE_ALT + r".{0,8}?的([\u4e00-\u9fff]{2,12})")


def scope_pairs(text: str) -> dict:
    """抽取一段文本里的「概念 → 范围」映射（概念需可与选项名互通）。"""
    out = {}
    for m in RE_SCOPE_PAIR.finditer(text):
        sc, concept = m.group(1), m.group(2)
        out.setdefault(concept, sc)
    return out


def core_of(t: str) -> str:
    """选项去掉通用后缀，便于与教材概念名互通（卫所兵役制 → 卫所）。"""
    return re.sub(r"(制度|兵役制|主义|思想|武器|系统|政策|战略|理论)$", "", t)


def sentences_of(qid: str) -> list:
    """按句切分教材文本（保留句子边界，便于引用）。"""
    raw = CORPUS.read_bytes().decode("utf-8", errors="replace")
    t = norm(raw)
    return [s for s in re.split(r"[.。;；!?！？]", t) if len(s) >= 6]


def main() -> int:
    check_only = "--check" in sys.argv
    bank = json.loads(DATA.read_bytes().decode("utf-8"))
    qs = bank["questions"]
    sents = sentences_of("")
    print("教材句子数：%d" % len(sents))

    # 句子级倒排：选项文本 → 命中的句子下标
    #   完整文本匹配优先；失败时退化到「选项去掉后缀词后的核心」，以覆盖
    #   教材写「卫所制」而选项写「卫所兵役制」这类同义不同形的情况。
    def core(t: str) -> str:
        return re.sub(r"(制度|兵役制|主义|思想|武器|系统|政策|战略)$", "", t)

    def hits_of(text: str) -> list:
        for key in (text, core(text)):
            if len(key) >= 2:
                got = [i for i, s in enumerate(sents) if key in s]
                if got:
                    return got
        return []

    def match_key(text: str) -> str:
        """实际用于定位的键（与 hits_of 保持一致）"""
        for key in (text, core(text)):
            if len(key) >= 2 and any(key in s for s in sents):
                return key
        return text

    changed = []
    pending = []
    n_same_sentence = n_scope = n_none = 0

    def scope_of_option(opt: str, pairs: dict) -> str:
        """在「概念→范围」映射里查该选项所属范围（支持去掉通用后缀后互通）。"""
        for key in (opt, core_of(opt)):
            if key in pairs:
                return pairs[key]
        return ""

    for q in qs:
        if q.get("type") not in ("single", "multi"):
            continue
        opts = q.get("options") or []
        if not opts:
            continue
        a = q.get("answer")
        ans = list(a) if isinstance(a, list) else [str(a)]
        ans = [x for x in ans if x in LETTERS]
        why = q.get("distractorWhy")
        if not isinstance(why, dict):
            continue
        stem_scopes = [w for w in SCOPE_WORDS if w in q["stem"]]
        ans_texts = [(LL, opts[LETTERS.index(LL)])
                     for LL in ans if LETTERS.index(LL) < len(opts)]
        for i, o in enumerate(opts):
            L = LETTERS[i]
            if L in ans or not o.strip() or L not in why:
                continue
            cur = why[L]
            if cur not in TEMPLATES:
                continue                      # 已写过具体说明的，不覆盖
            new_text = None
            # 只在「包含该选项原文」的句子里取配对，保证句与选项确实相关
            for s in sents:
                if o not in s and core_of(o) not in s:
                    continue
                pairs = scope_pairs(s)
                sc_o = scope_of_option(o, pairs)
                if not sc_o:
                    continue
                # ① 同句对照：同一句里正确选项也有明确范围 → 点明二者各属什么
                for LL, t in ans_texts:
                    if not t or t == o or t not in s:
                        continue
                    sc_t = scope_of_option(t, pairs)
                    if sc_t and sc_t != sc_o:
                        new_text = ("你把“%s”和“%s”搞混了：“%s”是%s的，“%s”（本题答案）是%s的。" % (
                            o, t, o, sc_o, t, sc_t))
                        n_same_sentence += 1
                        break
                if new_text:
                    break
                # ② 归属判定：教材明写「<其它范围>的<该选项>」，而题干问的是另一个范围
                if sc_o not in stem_scopes:
                    z = stem_scopes[0] if stem_scopes else "本题所问的范围"
                    new_text = "“%s”（你选的）指的是%s的，不是本题所问的%s。" % (o, sc_o, z)
                    n_scope += 1
                    break
            if new_text:
                changed.append({"id": q["id"], "key": L, "before": cur, "after": new_text})
                why[L] = new_text
            else:
                n_none += 1
                pending.append({
                    "id": q["id"], "key": L, "stem": q["stem"], "option": o,
                    "answer": [t for _, t in ans_texts],
                    "current": cur, "why": "语料中找不到该干扰项与正确项的对照句或范围归属",
                })

    print("同句对照生成：%d 条" % n_same_sentence)
    print("归属判定生成：%d 条" % n_scope)
    print("无法自动生成（转人工补写）：%d 条" % n_none)
    print("覆盖：%d / %d" % (n_same_sentence + n_scope, n_same_sentence + n_scope + n_none))

    print("\n=== 样例（改写后）===")
    for c in changed[:8]:
        print("  %-8s %s" % (c["id"], c["after"][:110]))

    if check_only:
        print("\n--check 模式：未写盘。")
        return 0

    DATA.write_bytes((json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
                     .replace("\n", "\r\n").encode("utf-8"))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "sameSentence": n_same_sentence, "scopeDerived": n_scope, "manualPending": n_none,
        "items": changed,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    PENDING.write_text(json.dumps({
        "note": "以下干扰项无法自动生成具体对比，需人工补写（用户选择「自动生成 + 我逐条补写剩下的」）",
        "count": len(pending), "items": pending,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n明细 → %s" % REPORT)
    print("待补清单 → %s（%d 条）" % (PENDING, len(pending)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
