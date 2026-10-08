#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_relevance.py — 修正解析，确保与题目有关
==========================================

用户要求：「修改现有解析，确保让它们与题目有关」。

先量了天花板（`tools/retrieval_potential.py`）：
  * 教材 5409 句里，能同时**切题**（题干覆盖 ≥0.5）且**支持答案**
    （答案内容字覆盖 ≥0.6）的只有约 662 道 / 1171；
  * 现状挂了依据句的 702 道里，**254 道的依据句讲的是别的事**；
  * 另有 214 道其实能找到合格依据但没挂上。

**关键发现（决定了策略）**：有些题在教材里根本没有对应内容 ——
  `高校国防教育` 0 次、`军训的意义` 0 次、`中国人民解放军工作条例` 0 次、
  `国防动员委员会` 0 次。
这类题**不可能**有"相关依据"。硬挂一句教材原句（现状就是这么干的，
例如问「高校国防教育的基本形式」却引用教材前言里的编写说明）正是用户抱怨的问题。

因此本脚本的策略是**双向的**：
  1. **替换**：依据不合格但有更好句子的 → 换成切题的句子；
  2. **撤下**：依据不合格且教材里确无相关内容的 → 撤掉依据句，
     只保留「正确答案」+「提示：教材未收录直接出处」。
     这比留一句不相干的话更有用 —— 用户不会被误导去读一段无关文字。

附带：为每道题补 `relatedSection`（教材里最相关的**小节标题**，如「国防的对象」），
它本身就能告诉用户"这题考的是教材哪一节"，即便没有可引用的原句。
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
import gen_explanations as G              # noqa: E402
from explain_text import clean_evidence, trim_sentence, structure, render_text  # noqa: E402
from answer_text import answer_text as base_answer_text  # noqa: E402  单一真相

BANK = ROOT / "data" / "questions.json"
LETTERS = "ABCDEFGH"
STEM_MIN = 0.50          # 题干覆盖：切题门槛
STEM_FLOOR = 0.20        # 题干覆盖地板：低于此值一律不选（防"数字巧合"型误配）
ANS_CHAR_MIN = 0.60      # 答案内容字覆盖：支持答案门槛
DEFN_BONUS = 0.12        # 定义句加分（「…是指…」「…包括…」）

# 教材小节标题，如「( 二 ) 国 防 的 对 象」→ 国防的对象
HEAD_RE = re.compile(r"[（(]\s*[一二三四五六七八九十百\d]+\s*[)）]\s*([\u4e00-\u9fff]{2,18})")
# 定义句特征
DEFN_RE = re.compile(r"(是指|指的是|就是指|称为|又叫|包括|分为|由.{2,20}组成|是指以)")


def ans_phrase(ans: str) -> str:
    """答案的主干短语：取最长的一个分项，用于「答案字面是否就在这句里」的判断。

    为什么必须做这一步（实测踩过，且是本次最危险的一类错）：
      教材里同时存在
        「决定战争胜负的因素是**人不是物**」   ← 本题答案
        「**信息**是核心资源，是决定战争胜负的关键因素」
      两句都含题干的「决定战争胜负」，字面重合度几乎一样。
      旧算法挑中了后者 —— **解析指向的正是错误选项**。
      把答案主干「人的因素」单独拿出来做一次**字面命中**判断，就能选中前者。
    """
    parts = [re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", p)
             for p in re.split(r"[、，,；;和与及/]+", ans or "")]
    parts = [p for p in parts if len(p) >= 2]
    if not parts:
        return re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", ans or "")
    return max(parts, key=len)


def answer_text(q) -> str:
    """用于**检索**的答案文本。

    与 `tools/answer_text.py`（全项目单一真相）的唯一差异：**判断题返回空串**。
    原因：判断题由单选派生、没有自己的答案文本，若返回「正确/错误」去检索，
    会召回大量恰好含这两个词的句子，污染候选池。

    坑：填空题/简答题的 `answer` 是字符串（`"逐渐模糊，战役或战术行动…"`），
    而选择题是字母（`"A"`）。第一版直接返回 `q["answer"]`，
    于是填空题拿字母 `A` 去检索 —— `idx.candidates("A")` 返回 0 个候选，
    再好的依据也找不到（实测漏掉 q-0780、q-0692）。
    """
    a = q.get("answer")
    if isinstance(a, bool):
        return ""
    if q.get("type") in ("single", "multi"):
        return base_answer_text(q)
    if isinstance(a, list):
        return "".join(str(x) for x in a)
    return str(a) if a else ""


def answer_display(q) -> str:
    t, opts = q["type"], q.get("options") or []
    if t == "single":
        i = LETTERS.index(q["answer"]) if q["answer"] in LETTERS else -1
        return q["answer"] + ("、" + opts[i] if 0 <= i < len(opts) else "")
    if t == "multi":
        names = [opts[LETTERS.index(a)] for a in q["answer"] if LETTERS.index(a) < len(opts)]
        return "、".join(q["answer"]) + ("（" + "；".join(names) + "）" if names else "")
    if t == "judge":
        return "正确" if q["answer"] is True else "错误"
    if t == "fill":
        return "；".join(q["answer"]) if isinstance(q["answer"], list) else str(q["answer"])
    return ""


def stem_query(stem: str) -> str:
    """题干检索串：只去掉填空位，**保留**全部实词。

    注意不要在这里做激进的问法剥离 —— 实测把「在未来信息化战争中」这类
    前缀删掉后，目标句反而召回不到（q-0780）。
    """
    s = re.sub(r"[_＿]{2,}", " ", stem)
    return s.strip()


def ans_char_cover(ans: str, sent: str) -> float:
    """答案的**内容字**有多少出现在依据句里（整体口径，仅作参考）。"""
    a = set(re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", ans))
    if not a:
        return 1.0
    s = set(re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", sent))
    return len(a & s) / len(a)


def ans_part_cover(ans: str, sent: str) -> float:
    """**分项**口径的答案覆盖：多选/多空答案按分项各自算覆盖率，取最佳分项。

    为什么不能只看整体字覆盖率（实测踩过）：
      * q-0780 答案「逐渐模糊，战役或战术行动越来越具有战略意义」，
        依据句「…战争层次会逐渐模糊」只覆盖了后半句 → 整体覆盖率只有 0.53，
        低于 0.6 的阈值，被误判成"不相关"而撤下；
      * q-0692 答案是四段战术（保存自己/积极防御/歼灭战…），
        原句只列了其中一段 → 整体覆盖率 0.32。
    这两句其实都是**切题且支持答案**的，问题出在"要求答案全部字都出现"太苛刻。
    改为：只要**任一答案分项**与依据句高度重合，就认定这句在讲这个答案。
    """
    parts = [p for p in re.split(r"[、，,；;和与及/]+", ans or "") if p.strip()]
    if not parts:
        return ans_char_cover(ans, sent)
    best = 0.0
    for p in parts:
        p = re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", p)
        if len(p) < 2:
            continue
        ps = set(p)
        ss = set(re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", sent))
        best = max(best, len(ps & ss) / len(ps))
    return best if best > 0 else ans_char_cover(ans, sent)


def merge_fragments(units: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """把「断句碎片」拼回完整句 —— 这是本次最关键的一处修复。

    `gen_explanations` 把 PDF 文本按换行切成"句"，但教材排版会把句子断开，于是语料里
    出现大量**缺头**的碎片：
        `年7月7日，日本发动卢沟桥事变，标志着…`      ← 头上的「1937」被切走了
        `年2月17日，中共中央军委批准…`                ← 缺年份
    后果极严重：真正切题的句子**在语料里根本不存在**，检索只能在碎片里挑，
    于是挑出各种不相干的句子（实测 q-0009/q-0010 都被匹配到卢沟桥事变那句，
    因为只有那句含「年7月7日」这类碎片特征）。

    修法：某单元若以「年/月/日/，/、」等残段开头，或本身过短，就与前一个单元拼接。
    """
    out: list[tuple[str, str]] = []
    for chapter, text in units:
        t = text
        # 缺头碎片：以「年/月/日/，/、」等残段开头，或以 1~2 位数字接「月/日」开头。
        # 注意 `年2月17日，中共中央军委批准…` 只有 4 字残头，靠长度判断会漏掉，
        # 所以必须**按形态**判定（实测漏掉这批后，q-0016/q-0027/q-0034 都挂上了
        # 「年2月17日…人民海军成立日」这类不相干的句子）。
        broken = bool(re.match(r"^\s*[年月日时分秒、，,。；;）)]", t)) or \
            bool(re.match(r"^\s*\d{1,2}\s*[月日]", t))
        if out and (broken or len(clean_evidence(t)) < 8):
            prev_ch, prev_t = out[-1]
            out[-1] = (prev_ch, prev_t + t)
        else:
            out.append((chapter, t))
    return out


# 「思考题列表」形态：两个以上「…是什么?」串在一起，或整句以问号结尾。
# 这类句子**不是知识内容**，绝不能被当成依据
# （实测它靠与题干字面重合能拿到 cs=1.00，是最强的假阳性来源）。
REFLECT_LIST_RE = re.compile(r"([^。？?]{4,30}[?？]){2,}|[?？]\s*$")


def is_question_list(s: str) -> bool:
    return bool(REFLECT_LIST_RE.search(s))


def build_extended_corpus(base: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """在 `load_corpus()` 的基础上补齐被丢掉的内容 —— 本函数是「仔细检查教材」的核心。

    `load_corpus()` 只保留 12~220 字的片段，于是**大量有用的短句被直接丢弃**：
        `(3)兵役制度。`、`(1)服现役。`、`(2)服预备役。`、`国家主权和国家` …
    这些恰恰是填空题/多选题的答案所在。此外排版会把句子切断，
    出现 `年2月17日…` 这类缺头碎片，让真正的完整句在语料里根本不存在。

    本函数把「原文全部片段（不过滤长度）+ 拼接后的完整句」与现有语料**合并去重**，
    使教材的利用率从 4,673 句提升到 6,000+ 句。
    """
    text_dir = ROOT / "build" / "text"
    extra: list[tuple[str, str]] = []
    for fname in ("1-textbook.txt", "0-outline.txt"):
        p = text_dir / fname
        if not p.exists():
            continue
        chapter = "通用"
        buf: list[str] = []
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = G.clean_line(raw)
            if not line or G.PAGE_RE.match(line) or G.JUNK_RE.match(line):
                continue
            if G.TOC_RE.match(line) and G.PAGENO_RE.search(line) and len(line) < 70:
                continue
            if G.PAGE_STRIP_RE.match(line):
                continue
            hm = G.CHAPTER_HEAD_RE.match(line)
            if hm:
                ch = G.normalize_chapter(hm.group(2))
                if ch:
                    chapter = ch
                    continue
            ch2, rest = G.match_chapter_prefix(line)
            if ch2:
                chapter = ch2
                rest = G.clean_line(rest)
                if len(rest) < 10:
                    continue
                line = rest
            if not re.search(r"[\u4e00-\u9fff]", line):
                continue
            for seg in re.split(r"(?<=[。！？])", line):
                seg = G.clean_line(re.sub(r"^\d{1,4}\s*", "", seg))
                if not seg:
                    continue
                ends_clean = seg.endswith(("。", "！", "？"))
                if buf:
                    buf.append(seg)
                    seg = "".join(buf)
                    buf = []
                if not ends_clean:
                    buf = [seg]
                    continue
                if len(seg) <= 300:
                    extra.append((chapter, seg))
        if buf:
            extra.append((chapter, "".join(buf)))

    merged = list(base) + extra
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for ch, s in merged:
        k = G.squeeze(s)
        if k and k not in seen:
            seen.add(k)
            out.append((ch, s))
    return out


def retrieval_terms_for(q, ans: str) -> str:
    """为**长文本答案**（填空题/简答题）构造检索串。

    坑：填空题的 `answer` 往往是一整句话，例如
        「国防建设是国家为提高国防能力而进行的各方面的建设，是国家建设…」
    直接拿它去检索，会命中「同时包含题干与答案片段」的**无关长句**，
    而且题干的权重被整句稀释，最后挑出一句完全不相干的话（实测 q-0468/q-0661）。

    这里只取答案的**前两个短分句**作为查询串，让检索聚焦在答案本身。
    """
    if not ans or len(ans) <= 40:
        return ans
    parts = [p for p in re.split(r"[，。；、]", ans) if len(p.strip()) >= 3]
    return "".join(parts[:2])[:40] if parts else ans[:40]


def clause_shares_topic(stem: str, reason: str, ans: str) -> bool:
    """依据句里必须有一个**分句**同时落在答案上，且整句与题干话题相关。

    见 `fix_relevance_final.clause_shares_topic` 的说明。放在选句阶段作为
    **候选过滤条件**，而不是事后否决 —— 这样"选错句"的题会被换成"选对句"，
    而不是直接被撤下（实测：事后否决会白扔 321 道本可救回的题）。
    """
    terms = [t for t in G.keywords(re.sub(r"[_＿]{2,}", " ", stem))
             if len(t) >= 2 and t not in G.STOP]
    whole = G.squeeze(reason)
    if terms:
        hit = sum(1 for t in terms if t in whole)
        if hit == 0 or (hit / len(terms) < 0.34 and hit < 2):
            return False
    parts = [p for p in re.split(r"[，。；、（）()：:？！]", ans or "") if len(p.strip()) >= 2]
    if not parts:
        return True
    for clause in re.split(r"[，。；、（）()：:？！]", reason):
        c = G.squeeze(clause)
        if len(c) < 3:
            continue
        cs_ = set(re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", c))
        for p in parts:
            ps = set(re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", p))
            if len(ps) >= 2 and len(ps & cs_) / len(ps) >= 0.6:
                return True
    return False


def proximity(sent: str, phrase: str, terms: list[str], window: int = 14) -> float:
    """答案短语与题干关键术语在句子里的**邻近度**（0~1）。

    只判断「句里有没有答案」是不够的：答案往往只是长句里的一个小分句。
    这里看答案短语附近（±window 字）有没有出现题干的关键术语 ——
    两者挨在一起，才说明这句话确实在讲这个考点。
    """
    s = G.squeeze(sent)
    if not s or not phrase:
        return 0.0
    pos = s.find(phrase)
    if pos < 0:
        # 短语不在句里（可能因去标点后形态不同）：退化为整句是否含任一术语
        return 0.4 if any(t in s for t in terms) else 0.0
    lo, hi = max(0, pos - window), pos + len(phrase) + window
    near = s[lo:hi]
    hit = sum(1 for t in terms if t in near)
    return 1.0 if hit >= 2 else (0.6 if hit == 1 else 0.0)


def main() -> int:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = bank["questions"]
    raw_units, _ = G.load_corpus()
    units = merge_fragments(raw_units)
    units = build_extended_corpus(units)
    idx = G.Index(units)
    print(f"语料 基础 {len(raw_units):,} 句 → 拼接+补齐短句后 {len(units):,} 句；题目 {len(qs)} 道")

    # 教材小节标题清单（用于 relatedSection）
    # 注意：正则会在长标题里切出碎片（实测得到「进行形势」「时机」这类半截词），
    # 所以只保留**像完整名目**的：长度 ≥4 字，且以名词性字结尾。
    BAD_TAIL = ("的", "和", "与", "及", "在", "于", "把", "被", "对", "而", "以", "为", "是")
    sections: list[str] = []
    for _, text in units:
        for m in HEAD_RE.finditer(text):
            name = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", m.group(1))
            if not (4 <= len(name) <= 18):
                continue
            if name.endswith(BAD_TAIL):
                continue
            if name not in sections:
                sections.append(name)
    print(f"教材小节标题 {len(sections)} 个（已剔除碎片）")

    stats: Counter[str] = Counter()
    for n, q in enumerate(qs, 1):
        ans = answer_text(q)
        sq = stem_query(q["stem"])
        parts = q.get("explanationParts") or {}

        # ---- 1) 为本题挑最相关的句子 ----
        # 选句判据（这里踩过坑，务必按此实现）：
        #   * **必须同时**「切题」（题干覆盖高）**且**「落在答案上」（答案所在的
        #     那句话）。只按题干选句会选到小节标题，例如问「国防的对象是____」
        #     会选到「(二)国防的对象国防的对象是指国防要防备、抵抗和制止的行为」——
        #     切题度满分，但那句没写答案（答案在下一句「一是侵略，二是武装颠覆和分裂」）。
        #   * 先用**答案**取候选并排序（答案所在的句子才可能支持答案），
        #     再在其中要求切题。这样既不会选到小节标题，也不会选到无关句。
        ans_cand = idx.candidates(retrieval_terms_for(q, ans)) if ans else []
        if ans:
            cand = ans_cand or list(idx.candidates(f"{sq} {ans}"))
            cand = sorted(cand, key=lambda i: -idx.weighted_coverage(ans, i))
        else:
            cand = list(idx.candidates(sq))
            cand = sorted(cand, key=lambda i: -idx.weighted_coverage(sq, i))

        # 题干关键术语：用于硬性相关性检查（见 pick 内注释）
        key_terms = [t for t in G.keywords(sq) if len(t) >= 2 and t not in G.STOP][:10]
        term_pool = set(key_terms)

        # 两级选取（顺序很重要）：
        #   ① **优先**只在「答案主干字面出现」的句子里挑 —— 这类句子才是在讲答案；
        #   ② 没有这种句子时，才退回按覆盖率挑。
        # 为什么必须分两级：q-0968 问「决定战争胜负的关键因素是____」答案是「人的因素」。
        # 教材里有两句高度相似：
        #   「…人的因素对战争的胜负具有决定性作用」（答案句，但题干覆盖只有 0.24）
        #   「信息是核心资源，是决定战争胜负的关键因素」（**指向错误选项**，题干覆盖 0.87）
        # 单级打分里后者总分更高（0.54 vs 0.47），于是解析指向了错误选项。
        # 先按「字面命中」收窄候选，再比覆盖，就能选中前者。
        phrase = ans_phrase(ans)
        cand = sorted(cand, key=lambda i: -idx.weighted_coverage(ans, i))
        top = cand[:400]

        # 字面命中：不要求**整串完全一致**，而是答案主干的内容字基本都在句里。
        # 为什么要放宽（实测踩过）：
        #   q-0009 答案「开始沦为半殖民地半封建社会」，教材原句是
        #   「近代中国自1840年鸦片战争后**逐步沦为半殖民地半封建社会**」——
        #   只有「开始/逐步」两字之差，整串匹配却判定为"没命中"，
        #   于是放弃了这句（答案覆盖率 0.97，排名第 1）去选了别的句子。
        def literal_hit(sent_raw: str) -> bool:
            if not phrase or len(phrase) < 2:
                return False
            ps = set(phrase)
            ss = set(re.sub(r"[^\u4e00-\u9fff0-9A-Za-z%]", "", sent_raw))
            return len(ps & ss) / len(ps) >= 0.8

        def pick(pool):
            b = None
            for i in pool:
                raw = units[i][1]
                # 排除「思考题列表」：它不是知识内容，却因与题干字面重合而得分最高
                if is_question_list(raw):
                    continue
                # **候选过滤**：必须有一个分句落在答案上、且整句与题干话题相关。
                # 放在这里过滤（而不是事后否决）才能"换对句"而不是"直接撤下"。
                if not clause_shares_topic(sq, raw, ans):
                    continue
                rn = G.squeeze(raw)
                cs = idx.weighted_coverage(sq, i)
                ac = ans_part_cover(ans, raw) if ans else 1.0
                lit = 1.0 if literal_hit(raw) else 0.0
                # **答案优先**：句子能不能支撑这个答案，是解析成立的前提，权重最高。
                # 由此把顺序倒过来 —— 以前是「题干覆盖 0.45 + 答案 0.25」，于是
                # 一句「含很多题干词、但根本没提答案」的废话能压过「精确写出答案」的原句。
                # 实测 q-0407：教材原句「…确定每年9月的第三个星期六为全民国防教育日」
                # 答案覆盖 0.80、字面命中，却输给一句时间线法规列举（题干覆盖更高而已）。
                sc = ac * 0.45 + lit * 0.30 + cs * 0.25 \
                    + (DEFN_BONUS if DEFN_RE.search(raw) else 0.0)
                # **同段落加分**：答案与题干关键术语要出现在**同一个短片段**里。
                # 为什么需要：答案常常只是长句中的一个小分句，光看"句里有没有答案"
                # 分不出「这句就是在讲它」和「这句只是顺带列了它」。
                # 实测 q-0407：正确答案句「…确定每年9月的第三个星期六为全民国防教育日。」
                # 与一句时间线列举（把全民国防教育日夹在几十个日期中间）得分几乎相同，
                # 靠这一项才能把前者选出来。
                sc += 0.90 * proximity(raw, phrase, key_terms)
                # 地板要求：句子必须与题干沾边（防「三级战备」式的纯巧合）
                if cs < STEM_FLOOR:
                    continue
                # 题干关键术语至少命中一个（**只统计本身也是关键术语的那些词**，
                # 否则「服役」这种出现在长关键词里的子串会造成假命中，
                # 实测：q-0034 问兵役义务，却靠答案里的「服役」挂上了海军成立日的句子）
                if key_terms and not any(t in rn for t in key_terms if t in term_pool):
                    continue
                if b is None or sc > b[0]:
                    b = (sc, cs, ac, lit, i)
            return b

        GOOD_SCORE = 0.62
        # 三个候选池**都算一遍再比分数**，不要"先到先得"：
        #   ① 答案字面命中的（最可靠）② 倒排召回的 ③ **全库**
        # 必须都评估，否则倒排池里一个"还不错"的句子会先被选中，
        # 让全库里那句真正精确的答案句永远没机会 ——
        # 实测 q-0407 就是这样选错的：正确句「…确定每年9月的第三个星期六为
        # 全民国防教育日。」答案覆盖 1.00、字面命中、同分句命中，
        # 却因不在召回前 400 条而被跳过，换成了一句时间线法规列举。
        # 全库约 6000 句，逐题扫描毫秒级，完全可接受。
        pools = []
        lit_pool = [i for i in top if literal_hit(units[i][1])]
        if lit_pool:
            pools.append(lit_pool)
            stats["literalPool"] += 1
        pools.append(top)
        pools.append(range(len(units)))
        best = None
        for pool in pools:
            cand_best = pick(pool)
            if cand_best is not None and (best is None or cand_best[0] > best[0]):
                best = cand_best
        ok_relevance = bool(best and best[0] >= GOOD_SCORE)
        i = best[4] if best else -1
        _sc = best[0] if best else 0.0

        # ---- 2) 定 relatedSection（教材里最贴近本题的小节标题）----
        # 要求标题本身在题干里**成串出现**（span_fit 高），否则说明只是词语巧合。
        related = ""
        if sections:
            scored_sec = []
            for name in sections:
                direct = G.span_fit(name, sq)
                if direct < 0.5:
                    continue
                cov = idx.weighted_coverage(name, i) if i >= 0 else 0.0
                scored_sec.append((direct * 2.0 + cov, name))
            scored_sec.sort(key=lambda x: -x[0])
            if scored_sec and scored_sec[0][0] >= 1.1:
                related = scored_sec[0][1]

        old_reason = (parts.get("reason") or "").strip()
        had_reason = bool(old_reason)

        # ---- 3) 决定 replace / drop / keep ----
        if ok_relevance:
            new_reason = trim_sentence(clean_evidence(units[i][1]))
            # 若新句与旧句相同则保持
            parts["reason"] = new_reason
            if had_reason and old_reason != new_reason:
                stats["replaced"] += 1
            elif not had_reason:
                stats["filled"] += 1
            else:
                stats["kept"] += 1
            q["explanationSrc"] = q.get("explanationSrc") if q.get("explanationSrc") in (
                "manual", "bank") else "textbook"
        else:
            if had_reason:
                stats["dropped"] += 1
            parts.pop("reason", None)
            # 撤下依据后不再声称有教材出处
            if q.get("explanationSrc") == "textbook":
                q["explanationSrc"] = "template"
            q["explanationRef"] = ""
            parts.pop("ref", None)
            stats["noSource"] += 1

        if related:
            q["relatedSection"] = related
            stats["withSection"] += 1

        # 提示文案：撤下依据的题要说清"为什么没有依据"
        if not ok_relevance and q["type"] not in ("short",):
            note = parts.get("note") or ""
            if "未收录" not in note and "人工" not in note:
                note = "教材中未收录与该题直接对应的内容，建议对照原卷核实"
            parts["note"] = note

        q["explanationParts"] = parts
        q["explanation"] = render_text(parts)
        if n % 300 == 0:
            print(f"  ...{n}/{len(qs)}")

    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- 报告 ----
    with_reason = sum(1 for q in qs if (q.get("explanationParts") or {}).get("reason"))
    print()
    print("=" * 78)
    print("解析相关性修正报告")
    print("=" * 78)
    print(f"  替换为更切题的依据 : {stats['replaced']}")
    print(f"  新补上合格依据     : {stats['filled']}")
    print(f"  原有依据合格保留   : {stats['kept']}")
    print(f"  撤下不合格依据     : {stats['dropped']}   ← 原来讲的是别的事")
    print(f"  现有「有相关依据」  : {with_reason} / {len(qs)}  ({with_reason/len(qs):.0%})")
    print(f"  带考点小节提示      : {stats['withSection']}")
    print(f"  撤下后标注为未收录  : {stats['noSource']}")
    print(f"  依据句含答案主干字面: {stats['literalHit']}   ← 最硬的相关性证据")
    print(f"  由全库兜底扫描救回  : {stats['fullScan']}")
    print()
    print("=== 修正样例 ===")
    for qid in ("q-0001", "q-0010", "q-0014", "q-0019", "q-0029", "q-0030", "q-0052", "q-0026"):
        q = next((x for x in qs if x["id"] == qid), None)
        if not q:
            continue
        p = q.get("explanationParts") or {}
        print(f"\n[{qid} {q['type']}/{q.get('explanationSrc')}] {q['stem'][:54]}")
        for k in ("answer", "reason", "note", "ref"):
            if p.get(k):
                print(f"    {k:7}: {p[k][:120]}")
        if q.get("relatedSection"):
            print(f"    考点章节: {q['relatedSection']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
