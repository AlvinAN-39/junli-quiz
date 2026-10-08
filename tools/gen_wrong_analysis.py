#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_wrong_analysis.py — 为「答错后」生成关键词解析
=================================================

用户需求：答错之后要给「关键词解析」，而不只是正确答案。

源 PDF 里**没有逐选项解析**（实测 `解析：`/`错在` 等标记均为 0 处），
教材里也没有。因此这里做的是**可验证的派生**，而不是编造：

为每道题计算四个字段：
  * `keywords`   —— 本题关键词（按「在本题库中越罕见越关键」排序，TF-IDF 思路）
  * `keyConcept` —— 本题考点（从题干里抽出的核心名词短语）
  * `evidence`   —— 教材/提纲里的依据句（复用 gen_explanations 的检索结果）
  * `distractorWhy` —— 每个**错误选项**为什么错（基于语料核验，见下）

「错误选项为什么错」的判定（都基于语料，不靠猜）：
  1. 该选项在教材里的出现次数 df；
  2. 该选项与「依据句」的字符重合度；
  3. 该选项是否与某个正确项高度相似（近似混淆项）。
  → 分别给出「教材中无此表述/未成体系」「与考点无关」「与正确项易混淆」三类说明。

原则：**能核验才写，核验不了就说「干扰项」**，不编造具体史实纠错。
"""

from __future__ import annotations

import json
import math
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
import gen_explanations as G  # noqa: E402

BANK = ROOT / "data" / "questions.json"
LETTERS = "ABCDEFGH"

# 题干里要剥掉的「问法外壳」，剩下的才是考点
SHELL_PATTERNS = [
    r"^下列(?:选项中)?", r"^以下", r"^关于", r"不属于", r"不包括", r"不正确", r"错误的是",
    r"有误的是", r"正确的是", r"是____。?$", r"是\s*$", r"有____。?$", r"包括____。?$",
    r"________", r"____", r"（\s*）", r"\(\s*\)", r"[（(]\s*[)）]",
]
SHELL_RE = [re.compile(p) for p in SHELL_PATTERNS]


def strip_shell(stem: str) -> str:
    s = stem
    for r in SHELL_RE:
        s = r.sub(" ", s)
    s = re.sub(r"[\s　]+", " ", s).strip(" ，,。、？?")
    return s


# 考点短语里不该出现的问法尾词
CONCEPT_TAIL = re.compile(r"(分别|指的是|是指|包括|属于|有|是|的|中|里|内|等)$")
# 题干尾部的问法短语：应整段剥掉，否则考点会变成「……分为哪几类」这种半句话
Q_TAIL_RE = re.compile(
    r"((?:分为|分成|包括|有哪些|是哪|是什么|是哪些|是哪几|有哪|是哪一|是哪几[个类种项]|"
    r"属于哪|指的是什么|是指什么|如何|怎样|怎么样|始于|终于|发生于|出现在)[^，。；？]{0,12})"
    r"[?？。]?$")
# 考点开头的引述/铺垫框架（只剥最前面那一小段，避免误删题干主体）
QUOTE_HEAD_RE = re.compile(
    r"^(根据|据|按照|依据|结合|基于)(你对|我们|自己)?[^，。；？]{0,12}?(的学习|的了解|的认识|的理解)?[，,]?"
    r"|^(党的二十大报告指出|报告指出|会议指出|习近平指出|教材指出|一般认为|通常|所谓)")

# 关键词黑名单：虚词、问法词、无区分度的通用词。
# 语料凝固度筛法会把这些也选进来（实测「是指」「两个」「方面」「象是」都出现过）。
KW_STOP = set("""
是指 指的是 包括 属于 不是 就是 可以 应当 必须 主要 重要 基本 一般 一些 各种 有关 相关
这个 那个 这些 那些 什么 哪些 哪个 怎么 怎样 如何 因为 所以 但是 而且 并且 如果 虽然
两个 三个 四个 五个 一个 第一 第二 第三 方面 内容 情况 问题 作用 意义 特点 特征 方式 方法
下列 以下 上述 正确 错误 说法 选项 内容 我 我们 你 他们 它 其 之 者 的 地 得 了 是 在 和 与
我国 中国 国家 人民 世界 现代 古代 时期 阶段 发展 建设 进行 通过 对于 关于 由于 为了
""".split())


def key_concept(stem: str) -> str:
    """抽取考点短语（生成侧质量由其后的 `validate_concept` 兜底）。

    目标：得到**像词条、不像半句话**的短名词短语，例如
      「国防的对象是____。」            → 国防的对象
      「国防设施的保护分为哪几类？」      → 国防设施的保护
      「《战争论》一书的作者是____。」    → 《战争论》一书的作者
      「党的十八大报告指出：“____是…」  → 党的十八大报告

    流程（逐步收缩，不会越改越长）：
      1. 去掉「下列/以下/不属于…」等问法外壳；
      2. 剥掉尾部问法短语与引述框架；
      3. 在第一个分句边界停下；
      4. 在「是/包括/有/属于/指的是/称为」处切掉谓语；
      5. 过长时**优先在「的」处收尾**（得到完整短语），最后才硬截断。
    """
    s = re.sub(r"[_＿]{2,}", " ", stem)
    s = re.sub(r"^(下列|以下)(选项中)?(不属于|不包括|不是|不正确|错误的是|正确的是|属于)?", "", s)
    s = Q_TAIL_RE.sub("", s).strip()
    s = s.strip(" ，,。、？?：:（()）\"'“”‘’")
    s = QUOTE_HEAD_RE.sub("", s).strip()

    # ③ 第一个分句边界
    for sep in ("。", "；", "，", "？", "：", ":", "?", ";", ","):
        i = s.find(sep)
        if 0 < i:
            s = s[:i]
    s = s.strip(" ，,。、？?：:（()）\"'“”‘’")

    # ④ 切掉谓语，只留主语/话题部分
    m = re.match(r"^(.{2,28}?)\s*(?:是|包括|有|属于|指的是|是指|称为|被称为|分为)\s*", s)
    cand = (m.group(1) if m else s).strip()

    # 清理尾词
    cand = re.sub(r"(分别|指的是|是指|有哪些|是什么|哪些|的)$", "", cand).strip()
    while CONCEPT_TAIL.search(cand) and len(cand) > 4:
        cand = CONCEPT_TAIL.sub("", cand).strip()

    # ⑤ 过长时先在「的」处收尾（保住完整短语），仍长才硬截断
    if len(cand) > 20:
        cut = max(cand.rfind("的"), cand.rfind("和"), cand.rfind("与"), cand.rfind("、"))
        cand = cand[:cut + 1] if cut >= 6 else cand[:20]
    cand = cand.replace(" ", "").strip(" ，,。、？?：:的和与及")
    return cand


# 纯时间/数量表述不能当考点（如「2013年秋」「1年10月」）——它们不是知识点
TIME_ONLY_RE = re.compile(r"^[\d０-９年月日时分秒第上下旬初末春秋\s]+$")
# 一整句（含逗号并列）不是考点短语
CLAUSE_RE = re.compile(r"[，,；;。].{4,}")


def validate_concept(concept: str, keywords: list[str], chapter: str) -> str:
    """考点文案的质量闸 —— 宁可置空（前端会省略该行），也不显示坏文案。

    实测会产出这几类垃圾（app-dev 核对字段时发现，这里逐类拦截）：
      * 以「哪」开头（`哪一个`/`哪项不`）—— 问法剥离后残留的疑问词；
      * 含空格 —— 原题干 `____` 填空位的残留（`辛亥革命于 年爆发`）；
      * 纯时间表述（`2013年秋`）—— 是题面信息，不是知识点；
      * 整句带逗号并列（`把中国军事思想发展到一个全新的阶段`）；
      * 引号/书名号不配对（截断的半句）；
      * 过短或无实义、结尾是单字虚词。
    不合格时返回空串，由调用方回退到关键词。
    """
    c = (concept or "").strip()
    if not c:
        return ""
    # 最外层硬闸：含阿拉伯数字的"考点"一律不用。
    # 知识点的名字里几乎不会出现数字（例外极少），而实测所有时间/编号类垃圾
    # （「2013年秋」「1年10月」）都带数字 —— 直接一刀切，简单且绝不误伤真考点。
    if re.search(r"[0-9０-９]", c):
        return ""
    if c[0] in "哪什么怎":
        return ""
    if " " in c or "\u3000" in c:
        return ""
    if len(c) < 2:
        return ""
    if TIME_ONLY_RE.match(c):
        return ""
    # 以时间表述开头 → 是题面信息，不是知识点。
    # 注意：截断可能把「2001年10月」变成「1年10月」，所以这里做**归一化探测**，
    # 只要前半段是「数字+年/月/日/秋/春…」形态就判为时间表述。
    probe = re.sub(r"[\s　]", "", c)
    if re.match(r"^[0-9０-９]{1,4}\s*[年月日时分秒][0-9０-９]{0,4}", probe) \
            or re.match(r"^[0-9０-９]{4}\s*年", probe) \
            or TIME_ONLY_RE.match(probe[:12]):
        return ""
    # 以时间词起始（「辛亥革命于 年爆发」这类含空格的已被上面拦掉）
    if re.match(r"^[0-9０-９]+[年月日]", probe):
        return ""
    # 动宾式半句（「把中国军事思想发展到一个全新的阶段」）
    if c.startswith(("把", "将", "使", "促使", "让", "带领", "促使")):
        return ""
    if CLAUSE_RE.search(c):
        return ""
    if c.endswith(("的", "和", "与", "及", "在", "于", "是", "为", "把", "被", "对",
                   "而", "以", "其", "所", "就", "也", "都")):
        return ""
    if c.count("《") != c.count("》") or c.count("“") != c.count("”"):
        return ""
    # 结尾是半截数字（如「公元前21世」）→ 明显截断
    if re.search(r"[0-9０-９][世年月日个条项种次届期元人倍]?$", c):
        return ""
    # 单字 + 数量词凑出来的（如「1年10月」已被 TIME_ONLY 拦截，这里兜底）
    if len(re.sub(r"[\d０-９]", "", c)) < 2:
        return ""
    return c


def _bad_kw(term: str) -> bool:
    """剔除跨词碎片与虚词片段。

    实测纯 n-gram 会产出「的军」「防的」「象是」「的战」「的主」这类碎片 ——
    中文没有词边界，枚举窗口切出来的东西大多不是词。这里做两道筛：
      1. 首尾虚词（的/是/了/在/和/与/就/也/之/为/以/而/其/所…）；
      2. 内部出现「的」等助词且整体不像固定短语。
    """
    if term in KW_STOP or len(term) < 2:
        return True
    head_tail = "的是了在和与就也之为以而其所以对把被从中内外上下个的了"
    if term[0] in head_tail or term[-1] in head_tail:
        return True
    if len(term) >= 3 and "的" in term[1:-1]:
        return True
    return False


def corpus_keywords(stem: str, terms: list[str], df_fn, limit: int = 6) -> list[str]:
    """提取关键词：**优先取源材料里真实存在的术语**，而不是猜词。

    中文没有词边界，纯 n-gram 枚举必然产出跨词碎片（实测「的军」「象是」「防的」）。
    正确做法是换一个词表来源 —— 本题自带的材料里本来就有真正的术语：
      * 题干中出现的政令/文件名与专有名词（《…》、「…」、引号内容、外文、数字代号）
      * **正确选项的文本**（就是本题的答案术语，如「祝榆生」「克劳塞维茨」「国家安全」）
      * 「考点」短语本身
      * 依据句（教材原句）里的名词性片段
    这些来源都是"已知是词"的，再按语料稀有度（IDF）与长度排序。
    只有在词表为空时，才退回 n-gram 枚举作为兜底。
    """
    text = re.sub(r"[_＿]{2,}", " ", stem)
    cands: dict[str, float] = {}

    def add(term: str, bonus: float = 0.0) -> None:
        term = re.sub(r"\s+", "", term or "")
        term = term.strip("，,。、；：？！（）()《》〈〉\"'“”‘’[]【】…-—·")
        if not (2 <= len(term) <= 12):
            return
        if not re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]+", term):
            return
        if _bad_kw(term):
            return
        d = df_fn(term)
        if d < 1:
            return
        score = (1.0 + min(len(term), 8) / 4.0) * (1.0 + 1.6 / (1.0 + d) ** 0.5) + bonus
        if term not in cands or score > cands[term]:
            cands[term] = score

    # ① 专有名词标记
    for pat, bonus in ((r"《([^》]{2,20})》", 4.0), (r"“([^”]{2,20})”", 3.0),
                       (r"\"([^\"]{2,20})\"", 3.0), (r"([A-Za-z]{2,})", 2.5)):
        for m in re.finditer(pat, text):
            add(m.group(1), bonus)
    # ② 词表来源：正确选项 + 考点 + 其他选项里的长术语
    for t in terms:
        add(t, bonus=3.0)
    # ③ 依据句里的候选片段
    for extra in terms:
        for piece in re.split(r"[，、和与及或]", extra):
            add(piece, bonus=1.2)
    # ④ 兜底：n-gram 枚举（仅在词表不足时）
    if len(cands) < 2:
        n = G.norm(text)
        for size in (6, 5, 4, 3, 2):
            for i in range(len(n) - size + 1):
                add(n[i:i + size])

    ranked = sorted(cands.items(), key=lambda kv: -kv[1])
    out: list[str] = []
    for term, _ in ranked:
        if any(term in o for o in out):      # 去掉被已选词包含的碎片
            continue
        # 过滤「整句/动宾短语」：长度 > 12 或含明显动词性尾词的不算关键词
        if len(term) > 12:
            continue
        if re.search(r"(始于|是|有|包括|分为|属于|成为|应当|必须)$", term) and len(term) > 6:
            continue
        out.append(term)
        if len(out) >= limit:
            break
    return out


def main() -> int:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = bank["questions"]
    print(f"题库: {len(qs)} 题")

    # ---- 教材语料 + 文档频率 ----
    units, _ = G.load_corpus()
    idx = G.Index(units)
    joined = "\n".join(t for _, t in units)
    nat = G.norm(joined)                      # 去标点的全语料
    print(f"语料: {len(units):,} 句, 去标点 {len(nat):,} 字")

    def df(term: str) -> int:
        """term 在语料里出现的次数（用于稀有度与「是否存在」判断）。"""
        if len(term) < 2:
            return 0
        return len(re.findall(re.escape(G.norm(term)), nat))

    # 全库关键词频次（用于 TF-IDF 式排序：全库越常见越不关键）
    all_tokens: Counter[str] = Counter()
    per_q_tokens: list[list[str]] = []
    for q in qs:
        toks = [t for t in G.keywords(q["stem"]) if len(t) >= 2][:60]
        per_q_tokens.append(toks)
        all_tokens.update(set(toks))
    N = len(qs)

    # ---- 语料文档频率（带缓存；用于术语校验与「是否存在」判断）----
    df_cache: dict[str, int] = {}

    def df_cached(term: str) -> int:
        key = G.norm(term)
        if key not in df_cache:
            df_cache[key] = (len(re.findall(re.escape(key), nat)) if len(key) >= 2 else 0)
        return df_cache[key]

    NEG_STEM = re.compile(r"不属于|不包括|不是|不正确|错误的是|有误的是|以下不是")

    filled_kw = filled_conc = filled_why = 0
    for q, toks in zip(qs, per_q_tokens):
        stem = q["stem"]
        ans = q["answer"]
        opts = q["options"]
        neg = bool(NEG_STEM.search(stem))

        # ---- 考点（经质量闸；不合格则回退到关键词，前端会自动省略空行）----
        raw_concept = key_concept(stem)
        concept = validate_concept(raw_concept, [], q.get("chapter") or "")

        # ---- 关键词（优先取源材料里真实存在的术语）----
        pool = [raw_concept]
        if opts:
            if q["type"] == "single":
                ci = LETTERS.index(ans) if ans in LETTERS else -1
                if 0 <= ci < len(opts):
                    pool.append(opts[ci])
            elif q["type"] == "multi":
                pool += [opts[LETTERS.index(a)] for a in ans
                         if LETTERS.index(a) < len(opts)]
        # 依据句也作为术语来源（教材原句里的名词更可靠）
        for piece in re.split(r"[，。；：、]", (q.get("explanation") or "")):
            piece = piece.strip()
            if 2 <= len(piece) <= 16 and "本题库未收录" not in piece:
                pool.append(piece)
        kws = corpus_keywords(stem, pool, df_cached, limit=6)
        if kws:
            q["keywords"] = kws
            filled_kw += 1
        # 考点为空时，用最长的关键词兜底（它来自源材料，至少是个真词）。
        # 注意：兜底也必须过同一道闸 —— 否则「2013年秋」这类词会从关键词路径绕进来。
        if not concept:
            concept = next((k for k in kws
                            if len(k) >= 3
                            and not re.search(r"[0-9０-９]", k)
                            and not _bad_kw(k)), "")
        q["keyConcept"] = concept
        if concept:
            filled_conc += 1

        # ---- 错误选项说明（仅选择题）----
        if q["type"] in ("single", "multi") and opts:
            correct_idx = ([LETTERS.index(ans)] if q["type"] == "single"
                           else [LETTERS.index(a) for a in ans])
            ev = ""
            m = re.search(r"[：:]\s*(.+)$", q.get("explanation") or "")
            ev = m.group(1) if m else (q.get("explanation") or "")
            ev = ev.split("本题库未收录")[0].strip()
            why = {}
            for i, o in enumerate(opts):
                if i in correct_idx or not o.strip():
                    continue
                L = LETTERS[i]
                d = df_cached(o)
                cov = G.span_fit(o, ev) if ev else 0.0
                near = [LETTERS[j] for j in correct_idx
                        if j < len(opts) and G.span_fit(o, opts[j]) >= 0.5]
                if d == 0:
                    why[L] = ("该说法在本软件核对过的教材语料中查不到，"
                              "属于为本题设置的干扰项。")
                elif near:
                    why[L] = f"与正确项 {'/'.join(near)} 表述相近、容易混淆，注意区分限定语。"
                elif neg:
                    # 否定题：其他选项正是考点包含的项，所以它们「对但不符合题意」
                    why[L] = "它属于该考点包含的内容，但本题问的是“不属于”的那一项。"
                elif cov >= 0.45:
                    why[L] = "该说法教材中有，但指向的不是本题所问的考点。"
                elif d <= 2:
                    why[L] = "教材中仅零星出现，不是本考点的规范表述。"
                else:
                    why[L] = "属于相关但错误的选项，注意题干限定的范围。"
            if why:
                q["distractorWhy"] = why
                filled_why += 1

    # ---- 统计与输出 ----
    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写入 keywords      : {filled_kw}/{len(qs)}")
    print(f"写入 keyConcept    : {filled_conc}/{len(qs)}")
    print(f"写入 distractorWhy : {filled_why}（选择题 {sum(1 for q in qs if q['type'] in ('single','multi'))} 道）")

    print()
    print("=== 抽样（答错后会看到的内容）===")
    for q in qs:
        if q["id"] in ("q-0001", "q-0378", "q-0453", "q-0082"):
            print(f"\n[{q['id']} {q['type']}] {q['stem'][:60]}")
            for i, o in enumerate(q["options"]):
                L = LETTERS[i]
                mark = ""
                if q["type"] == "single" and q["answer"] == L:
                    mark = " ✓"
                if q["type"] == "multi" and L in q["answer"]:
                    mark = " ✓"
                note = ("  ← " + q.get("distractorWhy", {}).get(L, "")) if L in q.get("distractorWhy", {}) else ""
                print(f"    {L}. {o[:54]}{mark}{note}")
            print(f"    关键词: {q.get('keywords')}")
            print(f"    考点  : {q.get('keyConcept')}")
            print(f"    答案  : {q['answer']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
