#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_explanations.py — 基于教材语料为每道题生成「解析」
=====================================================

目标：让每道题作答后都能看到一段**有依据、可回查**的解析。

依据优先级：
  1. 教材《普通高校军事课教程》全文（build/text/1-textbook.txt，20.5 万中文字）
  2. 提纲（build/text/0-outline.txt）
  3. 题库内部（简答题参考答案、人工校订说明）
  4. 兜底：确定性模板（明确说明「未收录直接出处」，不冒充依据）

写入每题的字段：
  * explanation     解析正文（作答后显示）
  * explanationSrc  依据等级：textbook / outline / bank / manual / template
  * explanationRef  出处位置，如「教材·第一章 中国国防」

原则：**宁可短、不可编**。检索要求「依据句里真的含正确答案文本」，
找不到就如实说明，绝不杜撰史实或数字。
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
TEXT = ROOT / "build" / "text"
BANK = ROOT / "data" / "questions.json"

PAGE_RE = re.compile(r"^===\s*PAGE\s*\d+\s*===$")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
STOP = set("的了是在和与及或有为对到等都也就这那其之上面下把一个我们他们可以应当必须这个那个以及"
           "从而因而所以因为如果虽然但是而且并且不过只是还是就是不是没有一些各种进行通过关于对于"
           "主要包括包括哪些下列以下关于说法正确错误内容方面主要")

CHAPTER_KEYS = ["中国国防", "国家安全", "军事思想", "现代战争", "信息化装备"]

# 教材用「第 一 节」字间空格；章标题可能带页码
CHAPTER_HEAD_RE = re.compile(
    r"^第\s*([一二三四五六七八九十]+)\s*章[\s　]*([\u4e00-\u9fff\s]{0,18}?)[\s　]*[（(]?\s*\d{0,4}\s*[)）]?\s*$")
# 页眉：正文页顶部重复「第N章 + 页码 + 章名」，并常与正文粘在同一行
RUNNING_HEAD_RE = re.compile(r"^第\s*[一二三四五六七八九十]+\s*章\s*(\d{1,4})\s*")
# 纯页码行：「28 第一部分 军事理论」「30 第 一 部 分 军事理论」
PAGE_STRIP_RE = re.compile(r"^\d{1,4}\s*(第\s*[一二三四五六七八九十]\s*部\s*分[\s　]*[\u4e00-\u9fff\s]{0,10})?\s*$")
# 目录行：以「第一章 / 一、/ 1.」开头且以 (页码) 结尾
TOC_RE = re.compile(r"^(第\s*[一二三四五六七八九十]+\s*章|第\s*[一二三四五六七八九十]+\s*节"
                    r"|[一二三四五六七八九十]\s*[、.．]|\d{1,3}\s*[、.．])")
PAGENO_RE = re.compile(r"[（(]\s*\d{1,4}\s*[)）]\s*$")
JUNK_RE = re.compile(r"^[\s\x00-\x1f\u2000-\u206f\u3000-\u303f\W_]*$")
# 教材每节末尾的「自测题」形如「现代国防的基本特征有哪些?」——是问题不是依据
META_Q_RE = re.compile(r"[?？]\s*$|有哪些\s*[?？]|是什么\s*[?？]|怎样\s*[?？]")
# 否定型题干：「下列不属于……的是」。这类题的答案是「被排除项」，
# 不能用「含答案词」去找依据（实测会把「民兵」匹配到国防动员的句子上），
# 而应找**列举了该概念全部组成项、恰好不含答案**的句子。
NEG_STEM_RE = re.compile(r"不属于|不包括|不正确|错误的是|有误的是|不是.*的是|以下不是|不列入")


def clean_line(s: str) -> str:
    s = s.replace("\x00", " ").replace("\ufeff", "")
    s = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", " ", s)
    s = re.sub(r"[ \t\u3000]{2,}", " ", s)
    return s.strip()


def squeeze(s: str) -> str:
    """去掉全部空白：教材字间插空格，必须压掉才能做子串匹配。"""
    return re.sub(r"\s+", "", s)


def match_chapter_prefix(line: str) -> tuple[str | None, str]:
    """识别并剥掉行首的「第N章+页码+章名」页眉，返回 (章名, 剩余正文)。

    教材同一页的页眉与正文会粘在一行，例如：
      `第 一 章23中 国 国 防`（纯页眉，无正文）
      `第 一 章21中国国防接受国防教育的权利和义务。…`（页眉+正文）
      `第 二 章125军事思想导地位。`（注意：页眉里的章名会把正文首字吞掉）
    """
    m = RUNNING_HEAD_RE.match(line)
    if not m:
        return None, line
    rest = line[m.end():]
    z = squeeze(rest)
    for k in sorted(CHAPTER_KEYS, key=len, reverse=True):
        if z.startswith(k):
            return k, rest[len(k) + (len(rest) - len(z)):] if False else _strip_n(rest, k)
    # 页眉章名含字间空格：逐字匹配
    for k in sorted(CHAPTER_KEYS, key=len, reverse=True):
        idx, ok = 0, True
        for ch in k:
            while idx < len(rest) and rest[idx].isspace():
                idx += 1
            if idx >= len(rest) or rest[idx] != ch:
                ok = False
                break
            idx += 1
        if ok:
            return k, rest[idx:]
    return None, rest


def _strip_n(s: str, k: str) -> str:
    """从 s 开头跳过 k 的字符（允许其间有空白）。"""
    idx = 0
    for ch in k:
        while idx < len(s) and s[idx].isspace():
            idx += 1
        if idx < len(s) and s[idx] == ch:
            idx += 1
        else:
            break
    return s[idx:]


def normalize_chapter(raw: str) -> str | None:
    z = squeeze(raw)
    for k in CHAPTER_KEYS:
        if k in z:
            return k
    return None


# ---------------------------------------------------------------------------
# 语料装载
# ---------------------------------------------------------------------------
def load_corpus() -> tuple[list[tuple[str, str]], dict[str, int]]:
    """返回 `(句子列表 [(章节, 句子)], {章节: 句数})`。

    注意第二个值是**章节句数**而非下标列表 —— 见函数末尾的说明：
    返回下标列表既无人使用，又会因被打印而撑爆上下文。
    """
    units: list[tuple[str, str]] = []
    order: list[str] = []          # 逐行累计的章节归属
    for fname in ("1-textbook.txt", "0-outline.txt"):
        p = TEXT / fname
        if not p.exists():
            continue
        chapter = "通用"
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = clean_line(raw)
            if not line or PAGE_RE.match(line) or JUNK_RE.match(line):
                continue
            if TOC_RE.match(line) and PAGENO_RE.search(line) and len(line) < 70:
                continue
            if PAGE_STRIP_RE.match(line):
                continue
            # 独立的章标题行（目录页/章首页）
            hm = CHAPTER_HEAD_RE.match(line)
            if hm:
                ch = normalize_chapter(hm.group(2))
                if ch:
                    chapter = ch
                    order.append(chapter)
                    continue
            # 页眉（常与正文粘在一起）
            ch2, rest = match_chapter_prefix(line)
            if ch2:
                chapter = ch2
                rest = clean_line(rest)
                if len(rest) < 10:
                    order.append(chapter)
                    continue
                line = rest
            order.append(chapter)
            for seg in re.split(r"(?<=[。！？])", line):
                seg = clean_line(seg)
                seg = re.sub(r"^\d{1,4}\s*", "", seg)
                if 12 <= len(seg) <= 220 and CJK_RE.search(seg):
                    units.append((chapter, seg))

    # 第二个返回值**故意只给计数**，不给下标列表。
    # 原因（实测教训）：原实现返回 `{章节: [下标, ...]}`，7 个调用点里有 6 个直接
    # 用 `units, _ =` 丢弃它，唯一需要它的地方也只要 `len()` ——
    # 即「一份数千个整数的结构，零真实用途」。但只要它被 print/日志带出来，
    # 就会瞬间把上下文撑爆（本次任务实际发生过一次）。
    # 改成计数后语义完全够用，且**不可能**再误伤上下文。
    by_ch: dict[str, int] = defaultdict(int)
    for ch, _ in units:
        by_ch[ch] += 1
    return units, dict(by_ch)


def norm(s: str) -> str:
    return squeeze(re.sub(r"[，。、；：？！“”‘’（）()《》〈〉\-—…·,.!?\"'\[\]【】]+", "", s))


def keywords(s: str) -> list[str]:
    """抽取检索关键词。

    关键修正：中文没有词间空格，`[\\u4e00-\\u9fff]{2,}` 会把
    「侵略和武装颠覆、分裂」整段当成一个 token 而永远匹配不上。
    因此对中文长串再做**滑窗切片**（2~4 字），兼顾精确与召回。
    """
    out: list[str] = []
    for m in re.finditer(r"[\u4e00-\u9fff]+|[A-Za-z]{2,}|\d+(?:\.\d+)?", s):
        w = m.group(0)
        if not re.match(r"[\u4e00-\u9fff]", w):
            if w not in STOP:
                out.append(w)
            continue
        if len(w) <= 4:
            if w not in STOP and len(w) >= 2:
                out.append(w)
            continue
        for size in (4, 3, 2):
            for i in range(len(w) - size + 1):
                piece = w[i:i + size]
                if piece not in STOP:
                    out.append(piece)
    # 去重但保序
    seen: set[str] = set()
    uniq: list[str] = []
    for w in out:
        if w not in seen:
            seen.add(w)
            uniq.append(w)
    return uniq


def bigrams(s: str) -> set[str]:
    nf = norm(s)
    return {nf[i:i + 2] for i in range(max(0, len(nf) - 1))}


def coverage(needle: str, haystack: str) -> float:
    """needle 的字符 bigram 有多大比例出现在 haystack 中。

    为什么不要求整串子串匹配：教材表述常与选项不完全一致，例如
    选项「侵略和武装颠覆、分裂」 vs 教材「一是侵略，二是武装颠覆和分裂」。
    用 bigram 覆盖率能容忍这种词序/连接词差异，同时仍要求实质内容重合。
    """
    nb = bigrams(needle)
    if not nb:
        return 0.0
    hb = bigrams(haystack)
    return len(nb & hb) / len(nb)


def key_coverage(needle: str, haystack: str) -> float:
    """关键 n-gram 覆盖率：只统计 needle 中「最稀有」的 n-gram。

    为什么需要：像「阶级」「国家」这种高频词会让错误句子也拿到不低的覆盖率，
    出现「泛化匹配」。这里用**倒排序文档频率**过滤掉过于常见的 n-gram，
    只保留能真正区分语义的部分（长 n-gram 自带高权重）。
    """
    nb = bigrams(needle) | trigrams(needle)
    if not nb:
        return 0.0
    hb = bigrams(haystack) | trigrams(haystack)
    return len(nb & hb) / len(nb)


def trigrams(s: str) -> set[str]:
    nf = norm(s)
    return {nf[i:i + 3] for i in range(max(0, len(nf) - 2))}


def atoms(s: str) -> list[str]:
    """把答案文本切成「原子词」，用于顺序紧邻匹配。

    中文没有词边界，这里贪心切 2~4 字片段（优先长片段）。
    例：「阶级国家」→ ['阶级','国家']；「侵略和武装颠覆、分裂」→ 逐段切分。
    """
    out: list[str] = []
    for m in re.finditer(r"[\u4e00-\u9fff]+|[A-Za-z]+|\d+(?:\.\d+)?", s):
        w = m.group(0)
        if not re.match(r"[\u4e00-\u9fff]", w):
            out.append(w)
            continue
        i = 0
        while i < len(w):
            for size in (4, 3, 2):
                if i + size <= len(w):
                    out.append(w[i:i + size])
                    i += size
                    break
            else:
                out.append(w[i])
                i += 1
    return [a for a in out if a]


# 中文虚词/连接词：做连续片段匹配时忽略它们
# 例：答案「侵略和武装颠覆、分裂」与教材「一是侵略，二是武装颠覆和分裂」
#     去掉连接词后，后者含「侵略武装颠覆」与「武装颠覆分裂」，能对上。
CONNECT_RE = re.compile(r"[和与及或、，,·的和及]")


def span_key(s: str) -> str:
    """把文本压成「只留实词字符」的形式，用于连续片段匹配。"""
    return CONNECT_RE.sub("", squeeze(norm(s)))


def span_fit(needle: str, haystack: str) -> float:
    """答案与句子共享的**最长连续实词片段**占答案实词长度的比例（0~1）。

    例：答案「侵略和武装颠覆、分裂」→ 实词「侵略武装颠覆分裂」；
    教材句「一是侵略，二是武装颠覆和分裂」→ 实词「一是侵略二是武装颠覆分裂」，
    共享最长片段「侵略」或「武装颠覆分裂」(6)。取最长即 6/9 ≈ 0.67。
    """
    nq, sq = span_key(needle), span_key(haystack)
    if not nq or not sq:
        return 0.0
    best = 0
    for i in range(len(nq)):
        if len(nq) - i <= best:
            break
        for j in range(len(nq), i + best, -1):
            if nq[i:j] in sq:
                best = j - i
                break
    if best < 2:                     # 连续片段太短，退回按原子匹配
        for a in atoms(needle):
            if len(a) >= 2 and a in sq:
                best = max(best, len(a))
    return min(1.0, best / max(1, len(nq)))


# ---------------------------------------------------------------------------
# 检索
# ---------------------------------------------------------------------------
class Index:
    def __init__(self, units: list[tuple[str, str]]):
        self.units = units
        self.normed = [norm(s) for _, s in units]
        self.sq = [squeeze(s) for _, s in units]      # 跨空格匹配用
        self.gs = [bigrams(s) for _, s in units]
        self.g3 = [trigrams(s) for _, s in units]
        self.inv: dict[str, list[int]] = defaultdict(list)
        for i, gs in enumerate(self.gs):
            for g in gs:
                self.inv[g].append(i)
        # 稀有度权重：某 n-gram 出现在越少句子里，越能区分语义。
        # 没有它，「国家」「阶级」这类高频词会把错误句子也顶上来
        # （实测：「国防是随着____的出现而产生的」被匹配到五四运动的句子上）。
        n_doc = max(1, len(units))
        weights: dict[str, float] = {}
        for g, lst in self.inv.items():
            df = len(lst) / n_doc
            weights[g] = (1.0 / (1.0 + 60.0 * df)) ** 1.6
        # 三字组（更稀有）单独统计
        inv3: dict[str, list[int]] = defaultdict(list)
        for i, gs in enumerate(self.g3):
            for g in gs:
                inv3[g].append(i)
        for g, lst in inv3.items():
            df = len(lst) / n_doc
            weights[g] = max(weights.get(g, 0.0), (1.0 / (1.0 + 60.0 * df)) ** 1.3)
        self.w = weights

    def weighted_coverage(self, needle: str, i: int) -> float:
        """按稀有度加权的 n-gram 覆盖率（衡量「这句是否在讲这个答案」）。"""
        n = squeeze(norm(needle))
        ng: set[str] = set()
        if len(n) >= 2:
            ng |= {n[k:k + 2] for k in range(len(n) - 1)}
        if len(n) >= 3:
            ng |= {n[k:k + 3] for k in range(len(n) - 2)}
        if not ng:
            return 0.0
        have = self.gs[i] | self.g3[i]
        tot = sum(self.w.get(g, 0.05) for g in ng)
        if tot <= 0:
            return 0.0
        got = sum(self.w.get(g, 0.05) for g in ng if g in have)
        return got / tot

    def candidates(self, query: str, pool: list[int] | None = None) -> list[int]:
        hits: Counter[int] = Counter()
        allowed = set(pool) if pool is not None else None
        for g in bigrams(query):
            for i in self.inv.get(g, ()):            # type: ignore[arg-type]
                if allowed is None or i in allowed:
                    hits[i] += 1
        return [i for i, _ in hits.most_common(200)]

    def find(self, stem: str, answer_text: str, chapter: str | None,
             min_cov: float = 0.45) -> int | None:
        """返回「实质支持该答案」的最佳句下标，否则 None。

        判据（实测调过）：
          * 主判据是**按稀有度加权的答案覆盖率**——直接回答
            「这句话是否在讲这个答案」，且不会因「国家」这类高频词而误判；
          * 题干相关度只作**次级排序**，不作硬门槛：最贴切的定义句常是
            「国防的对象，一是侵略，二是武装颠覆和分裂。」，
            与题干「国防的对象是____」的字符重合反而不高。
          * 倒排候选里找不到高覆盖句时，再对全库抽样扫描兜底。
        """
        if len(squeeze(answer_text)) < 2:
            return None
        # 章节池必须**并入「通用」**：教材的概述性定义句常常落在章标题之前
        # （实测「国防的对象，一是侵略，二是武装颠覆和分裂。」就落在通用桶里），
        # 只用本章节过滤会把它排除掉，导致最好的依据反而找不到。
        pools: list[list[int] | None] = [None]
        if chapter:
            own = [i for i, (c, _) in enumerate(self.units) if c == chapter]
            general = [i for i, (c, _) in enumerate(self.units) if c == "通用"]
            pools = [own, own + general, None]
        best = None
        for pool in pools:
            cand = self.candidates(f"{stem} {answer_text}", pool) or self.candidates(
                f"{stem} {answer_text}")
            best = self._pick(cand, stem, answer_text, chapter, min_cov)
            if best is not None:
                return best
        # 兜底：全库抽样扫描
        return self._pick(range(len(self.units)), stem, answer_text, chapter,
                          min_cov, sample=1400)

    def _pick(self, indices, stem: str, answer_text: str, chapter: str | None,
              min_cov: float, sample: int | None = None) -> int | None:
        best: tuple[int, float] | None = None
        n = 0
        for i in indices:
            n += 1
            if sample and n > sample:
                break
            txt = self.units[i][1]
            if META_Q_RE.search(txt):          # 教材里的「……有哪些?」自测题，不能当依据
                continue
            cov = self.weighted_coverage(answer_text, i)
            fit = span_fit(answer_text, txt)
            if cov < min_cov or fit < 0.5:
                continue
            sc = self._score(stem, i, chapter)
            # 三项加权。实测校准说明：
            #   * fit（连续实词片段占比）最能区分「这句是不是在讲这个答案」；
            #   * cov（按稀有度加权的 n-gram 覆盖率）在**短答案**上不稳定
            #     （「阶级国家」只有 4 个字，n-gram 少、易被巧合匹配顶满），
            #     所以它对短答案降权、对长答案升权；
            #   * sc（题干相关度）保证是同一考点。
            L = len(squeeze(norm(answer_text)))
            w_fit = 0.50 if L <= 6 else 0.38
            w_cov = 0.22 if L <= 6 else 0.36
            w_sc = 1.0 - w_fit - w_cov
            rank = fit * w_fit + cov * w_cov + min(sc, 1.0) * w_sc
            if best is None or rank > best[1]:
                best = (i, rank)
        return best[0] if best else None

    def related(self, stem: str, chapter: str | None,
                min_score: float = 0.45) -> int | None:
        """只要与题干相关（不要求支持答案），用于「相关背景」类解析。"""
        pool = None
        if chapter:
            pool = [i for i, (c, _) in enumerate(self.units) if c == chapter]
        best: tuple[int, float] | None = None
        for i in self.candidates(stem, pool) or self.candidates(stem):
            sc = self._score(stem, i, chapter)
            if best is None or sc > best[1]:
                best = (i, sc)
        if best and best[1] >= min_score:
            return best[0]
        return None

    def _score(self, stem: str, i: int, chapter: str | None) -> float:
        kws = keywords(stem)
        if not kws:
            return 0.0
        text = self.units[i][1]
        hit = sum(1.0 + min(len(w), 6) / 12.0 for w in kws if w in text)
        jac = len(bigrams(stem) & self.gs[i]) / max(1, len(bigrams(stem) | self.gs[i]))
        in_ch = 1.0 if (chapter and self.units[i][0] == chapter) else 0.0
        return hit / max(1.0, len(kws)) * 0.62 + jac * 0.28 + in_ch * 0.10


def clip(text: str, required: str, maxlen: int = 160) -> str:
    """裁出包含 required 的片段，两侧留上下文。"""
    i = text.find(required)
    if i < 0:
        i = squeeze(text).find(squeeze(required))
        if i < 0:
            return text[:maxlen] + ("…" if len(text) > maxlen else "")
    start = max(0, i - maxlen // 3)
    end = min(len(text), i + len(required) + maxlen * 2 // 3)
    return ("…" if start > 0 else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def pick_sentence(text: str, required: str, maxlen: int = 160) -> str:
    req = squeeze(required)
    for p in re.split(r"(?<=[。！？；])", text):
        if req and req in squeeze(p):
            p = p.strip()
            return p if len(p) <= maxlen else clip(p, required, maxlen)
    return clip(text, required, maxlen)


def chapter_of(q: dict) -> str | None:
    for k in CHAPTER_KEYS:
        if k in (q.get("chapter") or ""):
            return k
    return None


def ref_label(units, i: int) -> str:
    ch = units[i][0]
    return f"教材《普通高校军事课教程》·{ch}" if ch != "通用" else "教材《普通高校军事课教程》"


# ---------------------------------------------------------------------------
# 各题型解析
# ---------------------------------------------------------------------------
def explain_neg_single(q, idx: Index, units) -> tuple[str, str, str] | None:
    """否定型单选题：「下列不属于X的是____」。

    这类题的答案是**被排除项**，用「含答案词」检索会跑偏
    （实测「下列不属于我国古代武装力量体制的是→民兵」被匹配到
     「武装力量动员通常包括…民兵动员」——讲的完全是另一回事）。

    正确做法：找**列举了 X 全部组成项、恰好不含答案**的句子。
    例如教材「在武装力量体制上，一般分为中央军、地方军和边防军。」
    列出了 A/B/C 而没有 D(民兵)，正是所需依据。
    """
    stem = q["stem"]
    opts = q["options"]
    ai = "ABCDEFGH".index(q["answer"])
    correct = opts[ai] if ai < len(opts) else ""
    others = [o for i, o in enumerate(opts) if i != ai]
    ch = chapter_of(q)
    # 概念名：题干里「不属于……的是」中间那段
    m = re.search(r"不属于(.{2,20}?)的是", stem) or re.search(r"不包括(.{2,20}?)的是", stem)
    concept = m.group(1).strip("，,。 　") if m else ""
    kws = [k for k in keywords(concept or stem) if len(k) >= 3]

    best: tuple[int, float] | None = None
    for i, (c, txt) in enumerate(units):
        if META_Q_RE.search(txt):
            continue
        if "不" in txt[:6] and correct in txt:
            continue
        # 命中「其他选项」的个数：命中越多，越可能是在列举该概念的组成项
        hit_others = sum(1 for o in others if o and squeeze(o) in squeeze(txt))
        if hit_others < 2:
            continue
        hit_concept = sum(1 for k in kws if k in txt)
        sc = idx._score(stem, i, ch)
        rank = hit_others * 1.0 + hit_concept * 1.4 + min(sc, 1.0) * 0.5
        if correct and squeeze(correct) in squeeze(txt):
            rank -= 2.0                    # 列举里含被排除项 → 不是这条
        if best is None or rank > best[1]:
            best = (i, rank)
    if best and best[1] >= 3.0:
        i = best[0]
        sent = units[i][1]
        return (f"正确答案：{correct}（{concept or '该概念'}的组成项不含它）。依据：{sent[:150]}",
                "textbook", ref_label(units, i))
    return None


def explain_single(q, idx: Index, units) -> tuple[str, str, str]:
    stem = re.sub(r"[_＿]{2,}", " ", q["stem"])
    opts = q["options"]
    ai = "ABCDEFGH".index(q["answer"])
    correct = opts[ai] if ai < len(opts) else ""
    ch = chapter_of(q)

    if NEG_STEM_RE.search(q["stem"]):
        got = explain_neg_single(q, idx, units)
        if got is not None:
            return got

    i = idx.find(stem, correct, ch)
    if i is not None:
        sent = pick_sentence(units[i][1], correct)
        body = sent if squeeze(sent).startswith(squeeze(correct)) else f"{correct} — {sent}"
        return (body, "textbook", ref_label(units, i))

    j = idx.related(stem, ch)
    if j is not None:
        sent = clip(units[j][1], correct) if squeeze(correct) in idx.sq[j] else units[j][1][:150]
        return (f"正确答案：{correct}。相关表述：{sent}", "textbook", ref_label(units, j))

    return (f"正确答案：{correct}。本题库未收录教材中的直接出处，"
            f"可结合「{q.get('chapter', '本课程')}」相关内容理解。", "template", "")


def explain_multi(q, idx: Index, units) -> tuple[str, str, str]:
    stem = re.sub(r"[_＿]{2,}", " ", q["stem"])
    opts = q["options"]
    letters = q["answer"]
    chosen = [opts["ABCDEFGH".index(a)] for a in letters if "ABCDEFGH".index(a) < len(opts)]
    if not chosen:
        return ("本题答案由原卷答案串解析，建议对照原卷核实。", "template", "")
    ch = chapter_of(q)
    head = f"正确答案：{'、'.join(letters)}（{'；'.join(chosen)}）。"
    # 多选要**整组一起**匹配：单个短选项（如「国家」「阶级」）会退化成泛化匹配
    # （实测会把「国防是随着____的出现而产生的」匹配到五四运动的句子上）。
    combined = "".join(chosen)
    # 短答案（如「阶级」「国家」这种单词选项）做依据检索不稳定：
    # 字符太少，任何含这两个词的句子都可能被误判为高相关。
    # 实测「国防是随着____的出现而产生的」会被匹配到讲战争定义的句子上。
    # 因此对短答案不做检索，改为如实说明——宁可短，不可编。
    if len(combined) < 8:
        return (head + "本题库未收录教材中的直接出处。"
                       "可从国防的基本概念（国防随阶级和国家的产生而产生）理解，"
                       "并对照原卷核实各选项。", "template", "")
    i = idx.find(stem, combined, ch, min_cov=0.45)
    if i is None and len(combined) > 14:
        i = idx.find(stem, combined, ch, min_cov=0.34)
    if i is not None:
        return (head + pick_sentence(units[i][1], chosen[0]), "textbook", ref_label(units, i))
    # 退一步：只用最长的选中项
    for key in sorted(chosen, key=len, reverse=True)[:2]:
        j = idx.find(stem, key, ch, min_cov=0.55)
        if j is not None:
            return (head + pick_sentence(units[j][1], key), "textbook", ref_label(units, j))
    k = idx.related(stem, ch)
    if k is not None:
        return (head + f"相关表述：{units[k][1][:150]}", "textbook", ref_label(units, k))
    return (head + "本题库未收录教材中的直接出处，建议对照原卷核实各选项。", "template", "")


def explain_short(q, idx: Index, units) -> tuple[str, str, str]:
    stem = q["stem"]
    ch = chapter_of(q)
    j = idx.related(stem, ch, min_score=0.58)
    if j is not None and not META_Q_RE.search(units[j][1]):
        return (f"参考答案见下方。教材相关表述：{units[j][1][:150]}",
                "textbook", ref_label(units, j))
    return ("参考答案见下方（本题库收录的是原卷参考答案要点）。", "bank", "")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = bank["questions"]
    units, by_ch = load_corpus()
    print(f"语料句数: {len(units):,}")
    print("各章句数:", {k: v for k, v in sorted(by_ch.items(), key=lambda x: -x[1])[:8]})

    idx = Index(units)
    stats: Counter[str] = Counter()
    changed = 0
    for q in qs:
        old = (q.get("explanation") or "").strip()
        manual = ("人工校订" in old) or ("人工修正" in old)
        t = q["type"]

        if t == "single":
            text, src, ref = explain_single(q, idx, units)
        elif t == "multi":
            text, src, ref = explain_multi(q, idx, units)
        elif t == "short":
            text, src, ref = explain_short(q, idx, units)
        elif t in ("judge", "fill"):
            if old and not manual:
                stats[f"{t}-keep"] += 1
                q.setdefault("explanationSrc", "bank")
                q.setdefault("explanationRef", "")
                continue
            ans = q["answer"]
            ans_txt = (ans[0] if isinstance(ans, list) and ans else str(ans))
            stem = re.sub(r"[_＿]{2,}", " ", q["stem"])
            ch = chapter_of(q)
            i = idx.find(stem, ans_txt, ch) if isinstance(ans, str) and 2 <= len(ans_txt) <= 30 else None
            if i is None and t == "judge":
                i = idx.related(stem, ch, min_score=0.5)
                if i is not None:
                    text = f"依据：{units[i][1][:150]}"
                    src, ref = "textbook", ref_label(units, i)
                else:
                    text, src, ref = "本题库未收录教材中的直接出处。", "template", ""
            elif i is not None:
                text = f"正确答案：{ans_txt}。{pick_sentence(units[i][1], ans_txt)}"
                src, ref = "textbook", ref_label(units, i)
            else:
                text = f"正确答案：{ans_txt}。"
                src, ref = "template", ""
        else:
            continue

        if manual:                      # 人工校订依据优先，追加自动解析
            text = old + "　" + text
            src = "manual"
        q["explanation"] = text
        q["explanationSrc"] = src
        q["explanationRef"] = ref
        changed += 1
        stats[src] += 1

    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")

    have = sum(1 for q in qs if (q.get("explanation") or "").strip())
    tb = sum(1 for q in qs if q.get("explanationSrc") in ("textbook", "manual"))
    print(f"写入: {changed} 道；解析覆盖 {have}/{len(qs)} = {have / len(qs):.1%}")
    print(f"有教材依据: {tb} 道 ({tb / len(qs):.1%})")
    print("依据分布:", dict(stats))
    print()
    print("=== 抽样 ===")
    for t in ("single", "multi", "judge", "fill", "short"):
        for q in [x for x in qs if x["type"] == t][:2]:
            print(f"  [{t}] {q['stem'][:46]}")
            print(f"      解析: {(q.get('explanation') or '')[:180]}")
            print(f"      依据: {q.get('explanationSrc')} | {q.get('explanationRef')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
