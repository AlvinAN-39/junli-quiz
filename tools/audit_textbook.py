#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_textbook.py — 744 道客观题的教材全量比对（教材证据覆盖率法）
=====================================================================

目标（本轮用户要求）
--------------------
对全部客观题（单选 / 多选 / 判断）逐题比对教材原文，找出「答案与教材不一致」
的候选；结构性错误直接修，需要学科判断的先列出清单，不擅自改答案。

方法
----
1. 语料规范化：教材是 PDF 抽取文本，中文字之间存在空格（`八 一 南 昌`），
   先去掉汉字之间的空格、统一全角半角，让「选项文本」能真正命中教材原句。
2. 定位相关段落：用题干实词做倒排索引，取与题干重合度最高的 N 段作为该题的
   「教材证据池」。
3. 计算教材证据分：对每个选项，在证据池里找最大字符覆盖率
   （选项文本在段落中的最长连续命中占比；短选项按字符集包含计分）。
4. 判定：
   * 若**答案选项的教材证据分**明显低于某个干扰项 → 列为 `suspect_answer`
     （教材更支持别的选项，答案可能错）。
   * 若全题各选项证据分都低 → 列为 `no_corpus_evidence`（教材未覆盖，按
     用户口径「先报不改」，不得据此改答案）。
   * 其余为 `ok`。

为什么用覆盖率而不是关键词计数
------------------------------
上一轮遗留的 `qa/multi-answer-audit.json` 用的是「选项词在语料里出现次数」，
对填空题式的多选题会误判（如 q-0069 被列为可疑，而它其实是单选题误标）。
覆盖率直接衡量「选项原句是否出现在教材里」，噪声明显更小。

输出
----
  qa/textbook-audit.json   —— 逐题明细（含证据池段落，供人工复核）
  终端只打印计数与可疑清单前若干条

用法：
    python tools/audit_textbook.py
    python tools/audit_textbook.py --suspect-limit 20
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
CORPUS = ROOT / "build" / "text" / "1-textbook.txt"
REPORT = ROOT / "qa" / "textbook-audit.json"

OBJ_TYPES = ("single", "multi", "judge")
CJK = r"\u4e00-\u9fff"
STOP = set("的是了在有和与及或为对不也都就而等这那其中下列哪些什么如何以及一个一种可以因为所以本题下列属于"
           "以下关于说法正确错误答案选项内容主要基本根本第一我国中国人民国家")

# 题干里出现的「题型提示词」不参与检索，避免把「哪些」当实词
RE_TOKEN = re.compile(r"[%s]{2,6}|[0-9]{2,4}|[A-Za-z]{2,}" % CJK)


CN_NUM = {"一": "1", "二": "2", "两": "2", "三": "3", "四": "4", "五": "5",
          "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}


def normalize(text: str) -> str:
    """去汉字间空格、统一真/半角标点，保留数字与字母。

    必须做两件事，否则会大面积误判：
      1. 剔除 NUL 与其它控制字符：教材是 PDF 抽取文本，含 `\\x00`
         （实测复核清单里因此混入 34 个 NUL，导致下游读取工具判定为二进制文件）。
      2. 汉字数字统一成阿拉伯数字：语料写「七个军区调整为五大战区」，选项写「5」，
         不统一就永远匹配不上（实测 q-0054 因此被误报为答案可疑）。
    """
    t = text or ""
    t = "".join(ch for ch in t if ch == "\n" or ch >= " ")
    t = t.replace("\u3000", " ")
    t = t.replace("（", "(").replace("）", ")").replace("，", ",").replace("。", ".")
    t = re.sub(r"(?<=[%s])\s+(?=[%s])" % (CJK, CJK), "", t)   # 汉字之间空格
    t = re.sub(r"\s+", "", t)                                   # 其余空白全去（比对用）
    # 汉字数字 → 阿拉伯数字：仅替换「数字+量词/单位」的确定形态，避免误伤（如「五一」）
    t = re.sub(r"([%s])(?=[个名位条项次大战区军年代月日篇章门类种点])" % "".join(CN_NUM),
               lambda m: CN_NUM[m.group(1)], t)
    return t


def tokens_of(text: str) -> list:
    """取实词 token（去停用词）。"""
    out = []
    for m in RE_TOKEN.finditer(normalize(text)):
        w = m.group(0)
        if w in STOP or len(w) < 2:
            continue
        out.append(w)
    return out


def cover_score(opt: str, para: str) -> float:
    """选项在段落中的语料证据分。

    * 长选项（≥3 字）：最长连续命中占比（选项原句是否出现在语料里）。
    * 极短选项（如「6」「3个」「一个」）：不能按字符包含算，否则「6」在
      任意含数字「6」的段落里都算命中 1.0，会把「我国当前共有几大战区」
      这类题判成可疑（实测 q-0054 即为此类噪声）。改为**整词边界匹配**：
      要求该短串在段落里以独立词出现（前后不是数字/字母）。
    """
    o = normalize(opt)
    if not o:
        return 0.0
    if len(o) >= 3:
        n = len(o)
        for L in range(n, 2, -1):
            for i in range(0, n - L + 1):
                if o[i:i + L] in para:
                    return L / n
        return 0.0
    # 短选项：整词边界匹配
    pat = r"(?<![0-9A-Za-z])%s(?![0-9A-Za-z])" % re.escape(o)
    return 1.0 if re.search(pat, para) else 0.0


def answer_letters(q) -> list:
    a = q.get("answer")
    t = q.get("type")
    if t == "multi":
        items = a if isinstance(a, list) else list(str(a))
        return sorted({str(x).strip().upper() for x in items if str(x).strip()})
    if t == "single":
        return [str(a).strip().upper()]
    return []


def judge_true(q) -> bool:
    """判断题：True → 题干成立（正确）"""
    return q.get("answer") is True


def main() -> int:
    suspect_limit = 20
    if "--suspect-limit" in sys.argv:
        try:
            suspect_limit = int(sys.argv[sys.argv.index("--suspect-limit") + 1])
        except Exception:
            suspect_limit = 20

    bank = json.loads(DATA.read_text(encoding="utf-8"))
    qs = [q for q in bank["questions"] if q.get("type") in OBJ_TYPES]

    # ---------- 多语料源：教材 / 历年真题 / 模拟题 ----------
    # 教材覆盖不全时（894 道客观题里约 1/6 在教材中查不到原句），
    # 真题与模拟题语料是同一考纲下的补充证据；来源会写进明细，便于区分证据强度。
    # 证据强度：教材(primary) > 真题/模拟题(secondary)。
    CORPUS_FILES = [("textbook", "教材", CORPUS, "primary"),
                    ("past", "历年真题", CORPUS.parent / "2-past.txt", "secondary"),
                    ("mock", "模拟题", CORPUS.parent / "3-mock.txt", "secondary")]
    paras, para_src = [], []
    for key, label, path, _strength in CORPUS_FILES:
        if not path.exists():
            print("[WARN] 语料缺失：%s" % path, file=sys.stderr)
            continue
        for ln in path.read_text(encoding="utf-8", errors="replace").split("\n"):
            s = ln.strip()
            if not s or s.startswith("=== PAGE"):
                continue
            n = normalize(s)
            if len(n) >= 12:
                paras.append(n)
                para_src.append(label)

    # ---------- 倒排索引：token → 段落号 ----------
    index = defaultdict(set)
    for i, p in enumerate(paras):
        for w in set(tokens_of(p)):
            index[w].add(i)

    print("=" * 78)
    print("教材全量比对：客观题 %d 道 / 语料段落 %d 段（%s）"
          % (len(qs), len(paras), "、".join(sorted(set(para_src)))))
    print("=" * 78)

    details = []
    n_ok = n_suspect = n_nocorpus = 0
    for q in qs:
        toks = tokens_of(q["stem"])
        hit_count = defaultdict(int)
        for w in toks:
            for i in index.get(w, ()):      # 题干实词命中的段落
                hit_count[i] += 1
        pool = [i for i, _ in sorted(hit_count.items(), key=lambda kv: -kv[1])[:40]]

        if q.get("type") == "judge":
            opts = ["正确", "错误"]
            letters = ["T", "F"] if judge_true(q) else ["F", "T"]
        else:
            opts = q.get("options") or []
            letters = [chr(65 + i) for i in range(len(opts))]

        # 补强证据池：把「含任一选项原文片段」的段落也纳入，否则「教材未覆盖」
        # 里会混进大量其实有原文的题（答案原句在教材里，只是题干实词没命中）。
        opt_tokens = set()
        for o in opts:
            n = normalize(o)
            for L in (6, 4):
                for i in range(0, max(0, len(n) - L + 1)):
                    opt_tokens.add(n[i:i + L])
        for w in opt_tokens:
            if w in index:
                pool.extend(index[w])
        pool = list(dict.fromkeys(pool))[:80]
        pool_txt = [paras[i] for i in pool]

        scores = {}
        best_src = {}
        for L, o in zip(letters, opts):
            best, best_para, src = 0.0, "", ""
            for i in pool:
                p = paras[i]
                s = cover_score(o, p)
                if s > best:
                    best, best_para, src = s, p, para_src[i]
            scores[L] = {"score": round(best, 3), "evidence": best_para[:120], "src": src}
            best_src[L] = src

        if q.get("type") == "judge":
            ans = ["T"] if judge_true(q) else ["F"]
        else:
            ans = answer_letters(q)
        ans_scores = [scores[L]["score"] for L in ans if L in scores]
        ans_min = min(ans_scores) if ans_scores else 0.0
        ans_avg = sum(ans_scores) / len(ans_scores) if ans_scores else 0.0
        dis = {L: v["score"] for L, v in scores.items() if L not in ans}
        dis_max = max(dis.values()) if dis else 0.0
        ans_src = "，".join(sorted({best_src.get(L, "") for L in ans if best_src.get(L)}))

        # 逆问题（「不属于 / 不包括 / 不是 / 不正确」）：覆盖最高的选项**本应**是
        # 干扰项，答案反而是查不到的那一项 —— 判定方向必须反过来，
        # 否则这类「选错误项」的题会被整批误报为可疑。
        neg_stem = bool(re.search(r"不属于|不包括|不是|不正确|不符合|错误|例外|除(?:了)?哪|哪(?:一)?项不", q["stem"]))
        if q.get("type") == "judge":
            neg_stem = False

        # 证据强度：答案证据来自教材 → primary；只来自真题/模拟题 → secondary
        ans_primary = "教材" in ans_src
        verdict = "ok"
        if not pool or (ans_avg == 0 and dis_max == 0):
            verdict = "no_corpus_evidence"
            n_nocorpus += 1
        elif neg_stem and ans_min >= 0.5:
            verdict = "suspect_answer"          # 答案项出现 → 与「不属于」矛盾
            n_suspect += 1
        elif dis_max >= 0.6 and dis_max - ans_min >= 0.25:
            verdict = "suspect_answer"          # 干扰项证据明显强于最弱的答案项
            n_suspect += 1
        elif not ans_primary and ans_avg > 0:
            verdict = "consistent_secondary"    # 证据充分但不来自教材，标记出来
            n_ok += 1
        else:
            verdict = "consistent"
            n_ok += 1

        details.append({
            "id": q["id"], "type": q["type"], "stem": q["stem"], "negative": neg_stem,
            "options": opts, "answer": ans, "verdict": verdict,
            "ansSrc": ans_src, "poolSize": len(pool),
            "ansAvg": round(ans_avg, 3), "ansMin": round(ans_min, 3), "disMax": round(dis_max, 3),
            "scores": scores,
            # 候选段落（带来源标签，供逐题复核；最多 6 段、每段 140 字）
            "corpus": ["【%s】%s" % (para_src[i], paras[i][:140]) for i in pool[:6]],
            # 题库现有解析（生成物）：给复核者当参考线索，不作为独立证据
            "explanation": (q.get("explanation") or "")[:400],
        })

    n_secondary = sum(1 for d in details if d["verdict"] == "consistent_secondary")
    print("证据一致（含教材原文）    : %d" % (n_ok - n_secondary))
    print("证据一致（仅真题/模拟题库）: %d" % n_secondary)
    print("可疑（证据不支持当前答案） : %d" % n_suspect)
    print("无任何语料覆盖（先报不改） : %d" % n_nocorpus)
    print("-" * 78)
    sus = [d for d in details if d["verdict"] == "suspect_answer"]
    sus.sort(key=lambda d: -(d["disMax"] - d["ansMin"]))
    print("可疑清单前 %d 条：" % min(suspect_limit, len(sus)))
    for d in sus[:suspect_limit]:
        strong = max((k for k in d["scores"] if k not in d["answer"]),
                     key=lambda k: d["scores"][k]["score"], default="-")
        print("  %-8s %-6s 答案=%s 干扰项%s=%.2f 答案最低=%.2f | %s"
              % (d["id"], d["type"], "".join(d["answer"]), strong,
                 d["scores"][strong]["score"], d["ansMin"], d["stem"][:34]))

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "corpus": str(CORPUS), "paragraphs": len(paras),
        "counts": {"total": len(qs), "ok": n_ok, "suspect": n_suspect, "noEvidence": n_nocorpus},
        "details": details,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("明细 → %s" % REPORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
