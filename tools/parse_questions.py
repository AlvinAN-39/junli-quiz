#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_questions.py — 把 build/text/*.txt 解析为 data/questions.json
=================================================================

数据契约见 docs/02-data-contract.md（冻结）。

源文件结构（实测）：
    第一章中国国防            <- 章标题（每章题目编号从 1 重新开始）
    单选题                    <- 题型块标题
    1.题干____。              <- 题干（可能跨行）
    A.选项 ...                <- 选项（可能 4 个挤在一行）
    ...
    不定项选择题              <- 题型块标题（编号接续单选题）
    简答题 / 论述题
    ...
    答案                      <- 章末答案区
    第一章中国国防1-5AAACA 6-10ABBAA ...   <- 客观题答案（压缩串）
    87.①…②…                 <- 主观题答案（按题号）

解析策略：
  * 正文两遍扫描：先按章/题型块切分，再按 `N.` 题号聚拢「题干 + 选项」。
  * 答案区：解析 `a-b<字母串>` 压缩区间 → 顺序字母流。
  * 客观题答案按「顺序」与题目顺序配准（题号在部分章会错位，按顺序更稳），
    并要求 单选题答案数 == 单选题题数；不定项按字母组长度（≥2）切分。
  * 主观题答案用 `N.` 显式编号按题号匹配，支持续行拼接。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
TEXT_DIR = ROOT / "build" / "text"
OUT = ROOT / "data" / "questions.json"
DEBUG = "--debug" in sys.argv

# ---------------------------------------------------------------------------
# 正则
# ---------------------------------------------------------------------------
CHAPTER_RE = re.compile(r"^第([一二三四五六七八九十百零\d]+)章\s*(.*)$")
SEC_RE = re.compile(
    r"^[（(]?\s*[一二三四五六七八九十]+\s*[）)]?\s*[、.．]?\s*"
    r"(单选题|不定项选择题|多项选择题|多选题|判断题|填空题|简答题|论述题|名词解释)\s*$"
)
BARE_SEC_RE = re.compile(r"^(单选题|不定项选择题|多项选择题|多选题|判断题|填空题|简答题|论述题)$")
QNUM_RE = re.compile(r"^(\d{1,3})\s*[.、．]\s*(.*)$")
# 「1.8万多千米」「8.89万亿日元」「1.3%」这类是**数字本身**，不是题号。
# 判据：`\d+.\d`（小数点后还有数字）+ 常见量词。真正的题号形如 `33.我国…`
# 或 `1949年…`（`1949年` 之后不是小数点+数字），因此不会被误判。
NUMBER_LIKE_RE = re.compile(
    r"^\d{1,4}[.．]\d+(万|千|百|亿|%|％|倍|米|千米|公里|吨|人|个)")
OPT_RE = re.compile(r"^([A-H])\s*[.、．)）]\s*(.*)$")
ANS_HEAD_RE = re.compile(r"^答案\s*$")
PAGE_RE = re.compile(r"^===\s*PAGE\s*\d+\s*===$")
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮"

OBJECTIVE_KINDS = {"单选题", "不定项选择题", "多项选择题", "多选题"}
# 必须是 tuple/list（不能是 set）：set 的迭代顺序随 PYTHONHASHSEED 变化，
# 会导致主观题输出顺序漂移 → App 的 localStorage 进度（按 id 索引）错位。
SUBJECTIVE_KINDS = ("简答题", "论述题", "名词解释")
TYPE_MAP = {
    "单选题": "single",
    "不定项选择题": "multi",
    "多项选择题": "multi",
    "多选题": "multi",
    "判断题": "judge",
    "填空题": "fill",
    "简答题": "short",
    "论述题": "short",
    "名词解释": "short",
}


def clean(s: str) -> str:
    s = s.replace("\u3000", " ").replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize_stem(s: str) -> str:
    """题干归一化，用于去重。"""
    s = clean(s)
    s = re.sub(r"[（(]\s*[）)]", "", s)
    s = re.sub(r"[_＿—\-]{2,}", "", s)
    return re.sub(r"[^\w\u4e00-\u9fff]", "", s)


# ---------------------------------------------------------------------------
# 正文解析
# ---------------------------------------------------------------------------

class RawQ:
    __slots__ = ("chapter", "kind", "num", "stem", "options", "inline_answer", "raw")

    def __init__(self, chapter, kind, num):
        self.chapter = chapter
        self.kind = kind
        self.num = num
        self.stem = ""
        self.options: list[str] = []
        self.inline_answer = None
        self.raw = ""


def split_inline_options(text: str) -> tuple[str, list[str]]:
    """处理「A. xx B. yy C. zz D. ww」挤在一行的情况。
    返回 (题干, [选项...])；若没有行内选项则返回 (text, [])。
    """
    # 需要至少 3 个 A-D 标记才认为是行内选项行
    marks = list(re.finditer(r"(?:(?<=^)|(?<=[\s。？，、]))([A-H])\s*[.、．)）]\s*", text))
    if len(marks) < 3:
        return text, []
    stem = text[: marks[0].start()].strip()
    opts = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        opts.append(clean(text[m.end():end]))
    return stem, opts


def parse_body(lines: list[str]) -> tuple[dict[str, dict[str, list[RawQ]]], int | None]:
    """返回 ({章标题: {题型: [RawQ...]}}, 答案区起始 index)。

    注意：正文里题型块标题有时会粘在一行末尾（如「66.混合战争有哪些特点？论述题」），
    此时需要把该行切开：「题干」重新入队处理，题型切换立即生效。
    """
    chapters: dict[str, dict[str, list[RawQ]]] = {}
    chapter = None
    kind = None
    cur: RawQ | None = None
    ans_start = None
    queue: list[str] = []

    def handle(line: str, idx: int) -> None:
        nonlocal chapter, kind, cur
        if not line or PAGE_RE.match(line):
            return

        # 1) 章标题
        m = CHAPTER_RE.match(line)
        if m and len(line) <= 30:
            chapter = clean(line)
            chapters.setdefault(chapter, {})
            kind = None
            cur = None
            return

        # 2) 题型块标题（整行）
        m = SEC_RE.match(line) or BARE_SEC_RE.match(line)
        if m:
            kind = m.group(1)
            cur = None
            return

        # 3) 题型块标题粘在行尾
        m2 = re.search(
            r"(单选题|不定项选择题|多项选择题|判断题|填空题|简答题|论述题)\s*$", line)
        if m2 and len(line) > len(m2.group(1)):
            head = line[: m2.start()].rstrip(" 　")
            kind = m2.group(1)
            cur = None
            if head:
                handle(head, idx)
            return

        if chapter is None or kind is None:
            return

        # 4) 新题号
        mq = QNUM_RE.match(line)
        if mq and not NUMBER_LIKE_RE.match(line):
            num = int(mq.group(1))
            stem_part, inline_opts = split_inline_options(mq.group(2))
            cur = RawQ(chapter, kind, num)
            cur.stem = clean(stem_part)
            if inline_opts:
                cur.options = inline_opts
            cur.raw = line
            chapters[chapter].setdefault(kind, []).append(cur)
            return
        # 4b) 「像题号但其实是数字」的行（分页把题干切开）：并回上一题的题干/选项
        if mq and NUMBER_LIKE_RE.match(line) and cur is not None:
            if cur.options:
                cur.options[-1] = clean(cur.options[-1] + line)
            else:
                cur.stem = clean(cur.stem + line)
            cur.raw += " " + line
            return

        # 5) 选项行（可能一行挤多个选项）
        if cur is not None and OPT_RE.match(line):
            rest = line
            guard = 0
            while rest and guard < 12:
                guard += 1
                mo = OPT_RE.match(rest)
                if not mo:
                    break
                nxt = re.search(r"[A-H]\s*[.、．)）]", rest[mo.start(2):])
                if nxt:
                    opt_text = rest[mo.start(2): mo.start(2) + nxt.start()]
                    cur.options.append(clean(opt_text))
                    rest = rest[mo.start(2) + nxt.start():]
                else:
                    cur.options.append(clean(rest[mo.start(2):]))
                    break
            cur.raw += " " + line
            return

        # 6) 续行
        if cur is not None:
            if cur.options:
                cur.options[-1] = clean(cur.options[-1] + line)
            else:
                stem_part, inline_opts = split_inline_options(line)
                if inline_opts:
                    cur.stem = clean(cur.stem + " " + stem_part)
                    cur.options = inline_opts
                else:
                    cur.stem = clean(cur.stem + line)
            cur.raw += " " + line

    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        if ANS_HEAD_RE.match(line):
            ans_start = idx
            break
        if PAGE_RE.match(line):
            continue
        queue.append(line)
        while queue:
            handle(queue.pop(0), idx)
    return chapters, ans_start


# ---------------------------------------------------------------------------
# 答案区解析
# ---------------------------------------------------------------------------

def parse_answer_section(lines: list[str]) -> tuple[dict[str, str], dict[str, dict[int, str]]]:
    """返回 ({章关键词: 客观题答案文本}, {章关键词: {题号: 主观题参考答案}})。

    关键点：答案区会跨页（`=== PAGE n ===`），客观题答案串可能被拆到下一页；
    且有主观题答案夹在中间。因此这里按章切段、**保留段内全部文本**，
    客观题答案用区间/裸字母提取，主观题答案用 `N.` 编号提取。
    """
    # 按章分段（章标题行会出现在答案区开头，也可能在主观题答案之间）
    segs: dict[str, list[str]] = {}
    cur: str | None = None
    for ln in lines:
        s = ln.strip()
        if not s or PAGE_RE.match(s):
            continue
        m = re.match(r"^(第[一二三四五六七八九十]+章)[^\n\d]{0,10}", s)
        if m:
            cur = m.group(1)
            segs.setdefault(cur, [])
            rest = s[m.end():]
            if rest:
                segs[cur].append(rest)
            continue
        if cur:
            segs[cur].append(s)

    obj: dict[str, str] = {}
    subj: dict[str, dict[int, str]] = {}
    for key, parts in segs.items():
        blob = "\n".join(parts)
        # 主观题答案起点：形如 "82.军事战略是..."（题号 + 句点 + 中文/①/数字）
        cut = re.search(r"(?<![\dA-Ha-h])(\d{1,3})\s*[.、．]\s*(?=[①一-鿿]|\d)", blob)
        obj[key] = blob[: cut.start()] if cut else blob
        subj_seg = blob[cut.start():] if cut else ""
        items = re.split(r"(?<![\dA-Ha-h])(\d{1,3})\s*[.、．]\s*", subj_seg)
        d: dict[int, str] = {}
        for j in range(1, len(items) - 1, 2):
            num = int(items[j])
            txt = clean(items[j + 1])
            if txt:
                d[num] = txt
        subj[key] = d
    return obj, subj


RANGE_TOK = re.compile(r"^(\d{1,3})-(\d{1,3})")
LETTERS_TOK = re.compile(r"^[A-Ha-h]+")      # 扫描用（按位置切片后 match）
ANY_LETTERS = re.compile(r"[A-Ha-h]+")       # findall 用（不能带 ^ 锚点！）
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _key_part(line: str) -> str:
    """截取行首的「答案串」部分。

    答案串常与后续正文粘在一行（如 `...ABCD 62.在中国古代典籍中，战争...`），
    因此在第一个 CJK 字符处截断，只保留前面的 ASCII 部分。
    """
    m = CJK_RE.search(line)
    if m:
        line = line[: m.start()]
    return line.strip()


def _is_key_line(line: str) -> bool:
    """判断一行是否像「答案串」：以区间或 ≥4 连续字母开头，字母占比 ≥25%。"""
    line = _key_part(line)
    if len(line) < 4 or CJK_RE.search(line):
        return False
    if not RANGE_TOK.match(line) and not re.match(r"^[A-Ha-h]{4,}", line):
        return False
    letters_n = len(re.findall(r"[A-Ha-h]", line))
    return letters_n >= 4 and letters_n / len(line) >= 0.25


def _scan_key_line(line: str) -> list[tuple[int, int]]:
    """顺序扫描答案串，返回 [(n_letters, n_literal_per_question)] 片段序列。

    实际的答案串形如 `1-5AAACA 6-10ABBAA 11-15DAACB16-20BAAAA ...`：
    数字与字母常常紧贴，**区间宽度**才是「这段字母对应几道题」的唯一可靠信息。
    因此这里只负责按顺序切出「每段有多少字母」，题号由下游按顺序重新编号。

    返回元素：
      * `(n_letters, nq)` —— 一段字母 + 该段覆盖的题数（nq 由区间宽度给出）
      * 紧邻区间之间的裸字母段（源文件漏写区间）以 nq=0 表示，由下游顺延补齐。
    """
    items: list[tuple[str, object]] = []
    pos, n = 0, len(line)
    while pos < n:
        ch = line[pos]
        if ch.isspace():
            pos += 1
            continue
        rest = line[pos:]
        m = RANGE_TOK.match(rest)
        if m:
            items.append(("range", (int(m.group(1)), int(m.group(2)))))
            pos += m.end()
            continue
        m = LETTERS_TOK.match(rest)
        if m:
            items.append(("letters", m.group(0).upper()))
            pos += m.end()
            continue
        pos += 1

    out: list[tuple[int, int]] = []
    i = 0
    while i < len(items):
        kind, val = items[i]
        if kind == "letters":
            j = i + 1
            merged: str = val                                       # type: ignore[assignment]
            while j < len(items) and items[j][0] == "letters":
                merged += items[j][1]                               # type: ignore[operator]
                j += 1
            if j < len(items) and items[j][0] == "range":
                s, e = items[j][1]                                  # type: ignore[misc]
                out.append((len(merged), e - s + 1))
                i = j + 1
            else:
                out.append((len(merged), 0))
                i = j
            continue
        # 区间后面没有字母 → 空段
        s, e = val                                                  # type: ignore[misc]
        out.append((0, e - s + 1))
        i += 1
    return out


def parse_objective_key(seg: str) -> tuple[list[str], list[tuple[int, int, int]]]:
    """把答案串解析为 (顺序字母流, 区间提示列表)。

    * 只保留「像答案串」的行首部分（见 `_key_part` / `_is_key_line`），
      因此主观题答案正文里的 A-D 不会被误当成答案字母。
    * 提示列表的题号按**顺序计数**生成（不直接相信源文件里的数字），
      因为源文件个别章存在编号笔误或与正文不完全对齐。
      返回的提示对：`(start, end, n_letters)` 或裸字母 `(-1, -1, n)`。
    """
    raw: list[tuple[int, int]] = []          # [(n_letters, n_questions)]
    key_lines: list[str] = []
    for raw_line in seg.splitlines():
        line = _key_part(raw_line.strip())
        if not _is_key_line(line):
            continue
        key_lines.append(line)
        raw.extend(_scan_key_line(line))
    stream = [ch.upper() for grp in ANY_LETTERS.findall("\n".join(key_lines))
              for ch in grp]

    # 重新按顺序编号：题数由区间宽度给出，字母数由实际字母数给出
    hints: list[tuple[int, int, int]] = []
    cursor = 1
    for nletters, nq in raw:
        if nletters <= 0:
            continue
        if nq <= 0:
            nq = 1                               # 裸字母段：按 1 题处理
        hints.append((cursor, cursor + nq - 1, nletters))
        cursor += nq
    if len(stream) < sum(n for _, _, n in hints):
        stream = [ch.upper() for grp in ANY_LETTERS.findall(seg) for ch in grp]
    return stream, hints


def _distribute(nq: int, avail: int, min_len: int = 2, max_len: int = 4
                ) -> list[int] | None:
    """把 avail 个字母分给 nq 道题（每题 min_len~max_len），前面的题先拿满。"""
    if nq <= 0:
        return None
    if min_len == max_len:
        return [min_len] * nq if avail == nq * min_len else None
    if avail < nq * min_len or avail > nq * max_len:
        return None
    sizes = [max_len] * nq
    excess = nq * max_len - avail
    for i in range(nq - 1, -1, -1):        # 从后往前削
        if excess <= 0:
            break
        cut = min(excess, max_len - min_len)
        sizes[i] -= cut
        excess -= cut
    return sizes if excess == 0 else None


def _flex_distribute(nq: int, avail: int, min_len: int = 2, max_len: int = 8
                     ) -> list[int] | None:
    """宽松分配：每题 min_len~max_len 个字母，前面的题先拿满。"""
    if nq <= 0:
        return None
    if avail < nq * min_len or avail > nq * max_len:
        return None
    sizes = [max_len] * nq
    excess = nq * max_len - avail
    for i in range(nq - 1, -1, -1):
        if excess <= 0:
            break
        cut = min(excess, max_len - min_len)
        sizes[i] -= cut
        excess -= cut
    return sizes if excess == 0 else None


def _range_segments(hints: list[tuple[int, int, int]], n_single: int, n_multi: int
                    ) -> tuple[list[int], list[int]]:
    """按答案串区间提示求「每道多选题分到多少字母」。

    返回 (每题的字母数列表[长度 n_multi], 段边界内偏差说明列表)。

    规则：区间 `a-b<letters>` 覆盖题号 a..b；题号 ≤ n_single 的是单选题，
    其余为多选题。若区间从单选区跨入多选区，先扣掉单选区那部分的字母。
    """
    seg_q: list[int] = []        # 每段的多选题题数
    seg_l: list[int] = []        # 每段可用的字母数
    msgs: list[str] = []
    covered = 0
    pending_loose = 0            # 累积的裸字母（末尾或区间之间）
    for start, end, nletters in hints:
        if start < 0:
            pending_loose += nletters
            continue
        if covered >= n_multi:
            continue
        lo = max(start, n_single + 1)
        if end < lo:
            continue
        width = end - start + 1
        nq = min(end - lo + 1, n_multi - covered)
        skip = max(0, n_single - start + 1) if start <= n_single else 0
        use = max(0, nletters - skip)
        if nq < (end - lo + 1):
            use = int(round(use * nq / (end - lo + 1)))
        use += pending_loose         # 裸字母并入本段
        pending_loose = 0
        seg_q.append(nq)
        seg_l.append(use)
        covered += nq
        _ = width
    if covered < n_multi:                     # 尾部无区间提示
        seg_q.append(n_multi - covered)
        seg_l.append(pending_loose if pending_loose else -1)
        pending_loose = 0
    elif pending_loose and seg_q:             # 全部题已覆盖，裸字母追加到末段
        seg_l[-1] += pending_loose
    return seg_q, seg_l, msgs


def _number_to_single_answers(stream: list[str], hints: list[tuple[int, int, int]],
                              n_single: int) -> dict[int, str]:
    """按**源题号**把答案字母映射到单选题号。

    答案串的区间 `a-b<letters>` 直接给出题号，因此可以精确还原「第几题的答案是哪个字母」，
    不依赖正文条目顺序（正文可能因分页断行产生幽灵条目、或编号错位）。
    """
    m: dict[int, str] = {}
    idx = 0
    for start, end, nletters in hints:
        for _ in range(nletters):
            if idx < len(stream) and start <= n_single:
                m.setdefault(start, stream[idx])
            start += 1
            idx += 1
    return m


def _number_to_multi_answers(stream: list[str], hints: list[tuple[int, int, int]],
                             n_single: int, n_multi: int,
                             sizes: list[int]) -> dict[int, list[str]]:
    """按源题号把多选答案映射到题号。

    `sizes[i]` 是第 i 道多选题占几个字母（由 `split_objective_answers` 决定）。
    题号取自**多选题区间**：区间 `a-b` 中题号 > n_single 的部分对应多选题。
    """
    m: dict[int, list[str]] = {}
    pos = n_single
    qi = 0
    for start, end, nletters in hints:
        lo = max(start, n_single + 1)
        if end < lo:
            continue
        for num in range(lo, end + 1):
            if qi >= n_multi or pos >= len(stream):
                return m
            take = sizes[qi] if qi < len(sizes) else 2
            grp = sorted({c for c in stream[pos:pos + take]})
            if grp:
                m.setdefault(num, grp)
            pos += take
            qi += 1
    return m


def split_objective_answers(stream: list[str], n_single: int,
                            multi_opt_counts: list[int],
                            hints: list[tuple[int, int, int]] | None = None
                            ) -> tuple[list[str], list[list[str]], str,
                                       dict[int, str], dict[int, list[str]]]:
    """把顺序字母流切成 单选答案 + 多选答案组。

    实测结论（4 份源文件交叉验证）：
      * 单选题答案 = 字母流的前 n_single 个字母，**完全吻合**，可直接采用。
      * 多选题答案在源文件里被压成连续串（区间之间有裸字母、数字与字母紧贴，
        且区间宽度与实际题数不完全一致），存在**固有歧义**：同样的字母串可以有
        多种合法切分。

    因此这里采用「按区间宽度比例摊派」的确定性策略：
      * 每段的多选题按段内字母数平均分配（至少 2、至多 4 个字母）；
      * 段内字母不足/富余时按比例给部分题多 1 个字母，保证**每题都有答案**；
      * 无法完全对齐的字母数在 note 中如实上报，交给质检环节抽样复核。

    这样既不会让任何一道多选题缺失答案，也把不确定性限制在「答案长度 2~4」之内。
    """
    notes: list[str] = []
    n_multi = len(multi_opt_counts)
    singles = stream[:n_single]
    rest = stream[n_single:]
    if n_multi <= 0:
        return (singles, [], ("" if not rest else f"多选无题但有 {len(rest)} 个字母"),
                _number_to_single_answers(stream, hints or [], n_single), {})
    if not rest:
        return (singles, [], f"多选无答案字母（需要 {n_multi} 组）",
                _number_to_single_answers(stream, hints or [], n_single), {})

    seg_q, seg_l, _ = _range_segments(hints or [], n_single, n_multi)
    total = len(rest)
    if DEBUG:
        print(f"      [split] n_single={n_single} n_multi={n_multi} total={total} "
              f"seg_q={seg_q} seg_l={seg_l}")

    sizes: list[int] = []
    if seg_q and sum(seg_q) == n_multi:
        # 源文件的多选答案串存在固有歧义（区间宽度与实际题数不完全一致、
        # 区间之间夹着裸字母、数字与字母紧贴）。这里采用**确定性且不留空洞**的策略：
        #   1) 按区间宽度切出每段题数；
        #   2) 段内把该段字母平均分给段内题目，长度锁定 2~4（多选题至少 2 个正确项、
        #      至多 4 个选项）；
        #   3) 段内字母多于容量时，多出的字母顺延给下一段（保持字母流严格连续）。
        left = total
        for si, (nq, avail) in enumerate(zip(seg_q, seg_l)):
            if nq <= 0:
                continue
            n_after = sum(q for q, _ in zip(seg_q[si + 1:], seg_l[si + 1:]))
            pool = max(0, left - n_after * 2) if n_after else left
            if avail >= 0:
                pool = min(pool, max(avail, nq * 2)) if avail else pool
            pool = max(nq * 2, min(pool, left))
            base, rem = divmod(pool, nq)
            base = max(2, min(4, base))
            part = [base + (1 if k < rem and base < 4 else 0) for k in range(nq)]
            diff = pool - sum(part)
            k = 0
            while diff > 0 and k < nq * 8:
                if part[k % nq] < 4:
                    part[k % nq] += 1
                    diff -= 1
                k += 1
            if diff > 0:                      # 段字母确实超出容量 → 允许超过 4
                part[0] += diff
                notes.append(f"第 {si + 1} 段答案超容量，已顺延（源文件答案串歧义）")
            elif diff < 0:
                k = 0
                while diff < 0 and k < nq * 8:
                    if part[k % nq] > 2:
                        part[k % nq] -= 1
                        diff += 1
                    k += 1
            sizes.extend(part)
            left -= sum(part)
        if left != 0:
            notes.append(f"多选答案有 {left} 个字母未能对齐（源文件答案串歧义，建议抽样复核）")

    if len(sizes) != n_multi:
        base, rem = divmod(total, n_multi)
        base = max(2, min(4, base))
        sizes = [base + (1 if k < rem else 0) for k in range(n_multi)]
        notes.append("区间提示不可用，按整体摊派（多选答案存在歧义）")

    # 切分 + 校验
    multis: list[list[str]] = []
    i = 0
    bad_range = 0
    odd_len = 0
    for idx, s in enumerate(sizes):
        grp = sorted(set(rest[i:i + s]))
        i += s
        nmax = multi_opt_counts[idx] if idx < len(multi_opt_counts) else 8
        valid = [a for a in grp if "ABCDEFGH".index(a) < max(1, nmax)]
        if len(valid) != len(grp):
            bad_range += 1
        if s > 4:
            odd_len += 1
        multis.append(valid)
    if bad_range:
        notes.append(f"{bad_range} 道多选题答案字母超出选项范围(已裁掉越界字母)")
    if odd_len:
        notes.append(f"{odd_len} 道多选题答案长度>4(答案串压缩所致,建议质检抽样)")
    if i < len(rest):
        notes.append(f"多选答案剩余 {len(rest) - i} 个字母未分配")
    num_single = _number_to_single_answers(stream, hints or [], n_single)
    num_multi = _number_to_multi_answers(stream, hints or [], n_single, n_multi, sizes)
    if DEBUG:
        print(f"      [split-out] sizes={sizes} 消费={i}/{len(rest)} "
              f"多选字母={sum(len(m) for m in multis)} "
              f"总={len(singles) + sum(len(m) for m in multis)}/{len(stream)} note={notes!r}")
        print(f"      [split-out] 题号锚定 单选={len(num_single)} 多选={len(num_multi)}")
    return singles, multis, "; ".join(notes), num_single, num_multi


# ---------------------------------------------------------------------------
# 组装
# ---------------------------------------------------------------------------

def _debug_segments(hints, n_single: int, n_multi: int, total: int) -> str:
    """诊断：把提示转成段，看看每段题数/字母数对不对得上。"""
    out = []
    covered = 0
    for start, end, nletters in hints:
        if start < 0:
            out.append(f"裸组{nletters}")
            continue
        lo = max(start, n_single + 1)
        if end < lo:
            continue
        nq = end - lo + 1
        skip = max(0, n_single - start + 1) if start <= n_single else 0
        use = max(0, nletters - skip)
        out.append(f"{start}-{end}:题{nq}/字{use}")
        covered += nq
    return (f"n_single={n_single} n_multi={n_multi} 流={total} 覆盖题={covered} | "
            + " ".join(out))


def build_question_bank() -> dict:
    report: list[str] = []
    questions: list[dict] = []
    counter = 0
    stats = {"single": 0, "multi": 0, "judge": 0, "fill": 0, "short": 0}
    dropped = {"no_answer": 0, "bad_options": 0, "empty_stem": 0, "dup": 0, "multi_unsplit": 0}

    sources = [
        ("2-past.txt", "真题"),
        ("3-mock.txt", "模拟题"),
        ("0-outline.txt", "提纲"),
    ]

    seen_stems: set[str] = set()

    for fname, source in sources:
        path = TEXT_DIR / fname
        if not path.exists():
            report.append(f"[跳过] {fname} 不存在")
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        chapters, ans_start = parse_body(lines)
        obj_keys, subj_keys = ({}, {})
        if ans_start is not None:
            obj_keys, subj_keys = parse_answer_section(lines[ans_start:])

        report.append(f"### {fname}（{source}）")
        ch_order = list(chapters.keys())

        def key_for(ch: str) -> str | None:
            m = re.match(r"(第[一二三四五六七八九十]+章)", ch)
            return m.group(1) if m else None

        for ch in ch_order:
            by_kind = chapters[ch]
            singles = by_kind.get("单选题", [])
            multis = (by_kind.get("不定项选择题", []) + by_kind.get("多项选择题", [])
                      + by_kind.get("多选题", []))
            subjectives: list[RawQ] = []
            for k in SUBJECTIVE_KINDS:
                subjectives.extend(by_kind.get(k, []))
            handled = OBJECTIVE_KINDS | set(SUBJECTIVE_KINDS)
            others = [k for k in by_kind if k not in handled]

            report.append(
                f"  {ch}: 单选 {len(singles)}, 多选 {len(multis)}, "
                f"主观 {len(subjectives)}, 其他 {others or 0}"
            )

            # ---- 客观题答案配准 ----
            k = key_for(ch)
            seg = obj_keys.get(k, "") if k else ""
            stream, hints = parse_objective_key(seg) if seg else ([], [])
            s_ans: list[str] = []
            m_ans: list[list[str]] = []
            num_map_s: dict[int, str] = {}
            num_map_m: dict[int, list[str]] = {}
            if obj_keys:
                if stream:
                    s_ans, m_ans, note, num_map_s, num_map_m = split_objective_answers(
                        stream, len(singles), [len(q.options) for q in multis], hints)
                    used = len(s_ans) + sum(len(m) for m in m_ans)
                    flag = " OK" if used == len(stream) else " !!不平"
                    report.append(
                        f"    答案配准: 单选 {len(s_ans)}/{len(singles)}, "
                        f"多选 {len(m_ans)}/{len(multis)}, 字母 {used}/{len(stream)}{flag} "
                        f"| 题号锚定 单选{len(num_map_s)} 多选{len(num_map_m)}"
                        + (f" | {note}" if note else ""))
                    if DEBUG and used != len(stream):
                        report.append("      [段诊断] "
                                      + _debug_segments(hints, len(singles), len(multis),
                                                        len(stream)))
                else:
                    report.append(f"    [!] {ch} 未找到客观题答案段")

            # 单选题：优先按**源题号**取答案（正文条目可能因分页断行错位）
            for i, q in enumerate(singles):
                ans = num_map_s.get(q.num)
                if ans is None:
                    ans = s_ans[i] if i < len(s_ans) else None
                add_objective(q, source, ans, "single", questions, stats, dropped,
                              seen_stems, report)

            # 多选（不定项）：同样优先按源题号
            for i, q in enumerate(multis):
                ans = num_map_m.get(q.num)
                if ans is None:
                    ans = m_ans[i] if i < len(m_ans) else None
                add_objective(q, source, ans, "multi", questions, stats, dropped,
                              seen_stems, report)

            # ---- 主观题 ----
            skey = subj_keys.get(k, {}) if k else {}
            base_num = subjectives[0].num if subjectives else 1
            for i, q in enumerate(subjectives):
                ans = skey.get(q.num) or skey.get(base_num + i)
                if not ans:
                    dropped["no_answer"] += 1
                    continue
                stem = clean(q.stem)
                if len(stem) < 4:
                    dropped["empty_stem"] += 1
                    continue
                norm = normalize_stem(stem)
                if norm in seen_stems:
                    dropped["dup"] += 1
                    continue
                seen_stems.add(norm)
                counter += 1
                questions.append({
                    "id": f"q-{counter:04d}",
                    "type": "short",
                    "stem": stem,
                    "options": [],
                    "answer": ans,
                    "explanation": "",
                    "source": source,
                    "chapter": ch,
                    "section": q.kind,
                    "raw": clean(q.raw)[:400],
                })
                stats["short"] += 1

            if others:
                report.append(f"    [i] 未处理题型: {sorted({o.kind for o in others})}")

    # 重新编号（保证 id 连续）
    for i, q in enumerate(questions, 1):
        q["id"] = f"q-{i:04d}"

    # 简答区里其实是填空题的，改判为 fill
    moved = reclassify_short_as_fill(questions)
    if moved:
        stats["short"] -= moved
        stats["fill"] = stats.get("fill", 0) + moved
        report.append(f"[i] 简答区识别出 {moved} 道填空题，已改判为 fill")

    # 派生出判断题 / 填空题（源文件没有这两种题型，但 App 需要覆盖）
    derived_fill, derived_judge = derive_fill_judge(questions)
    questions.extend(derived_fill)
    questions.extend(derived_judge)
    for i, q in enumerate(questions, 1):
        q["id"] = f"q-{i:04d}"
    stats["fill"] = stats.get("fill", 0) + len(derived_fill)
    stats["judge"] = stats.get("judge", 0) + len(derived_judge)
    report.append(f"[i] 派生填空题 {len(derived_fill)} 道，派生判断题 {len(derived_judge)} 道")

    # 人工校订（独立质检确认的语义错误，逐条核对后覆盖）
    hi, mid = apply_curated_fixes(questions)
    if hi or mid:
        report.append(f"[i] 人工校订多选题答案：高置信 {hi} 道，中等置信 {mid} 道"
                      f"（中等置信保留存疑标记，见 CURATED_FIXES）")

    counts = dict(stats)
    counts["total"] = len(questions)
    tz = timezone(timedelta(hours=8))
    bank = {
        "schema": 1,
        "generatedAt": datetime.now(tz).isoformat(timespec="seconds"),
        "counts": counts,
        "sources": sorted({q["source"] for q in questions}),
        "questions": questions,
    }
    return bank, report, dropped


# ---------------------------------------------------------------------------
# 派生题型：判断题 / 填空题
# ---------------------------------------------------------------------------

# 「全选式」选项没有独立语义，不能用来派生判断题
ALL_OF_RE = re.compile(r"^(以上|上述|全部|都|均|都是|均是|以上都|以上均|前三|以上各项)")
# 判断题陈述句里不能残留的表述（会引出歧义）
BAD_JUDGE_STEM = re.compile(r"下列说法|下列选项|以下哪些|下列哪些|包括哪些"
                            r"|错误的是|不正确的是|有误的是|不是|不属于|不包括"
                            r"|不正确|不符合|哪些|哪项|哪一")


def derive_fill_judge(base: list[dict], max_fill: int = 150,
                      max_judge: int = 150) -> tuple[list[dict], list[dict]]:
    """从单选题派生填空题与判断题。

    依据：单选题题干多为「……是____。」的完整陈述句，其**正确选项**补进空白后即
    构成一句正确陈述，错误选项补进空白后即构成一句错误陈述。由此可稳定派生：

      * 填空题：把「正确选项 + 题干空白」拼成一句陈述，再挖掉正确选项 → 答案即该选项。
      * 判断题：同一题干分别用正确选项（→对）与错误选项（→错）生成两条陈述。

    为避免歧义，只保留满足以下条件的题：
      * 题干恰好含一个 `____` 风格空白；选项 4 个；题干长度 10~120；
      * 选项文本干净（不含「以上/都/均」等泛指词，长度 2~20，不含空白）；
      * 判断题的陈述句在题库中不重复。
    """
    fills: list[dict] = []
    judges: list[dict] = []
    seen_stmt: set[str] = set()
    seen_judge_stem: set[str] = set()
    blank_re = re.compile(r"[_＿]{2,}")

    for q in base:
        if len(fills) >= max_fill and len(judges) >= max_judge:
            break
        if q["type"] != "single":
            continue
        stem, opts, ans = q["stem"], q["options"], q["answer"]
        if len(opts) != 4 or not (10 <= len(stem) <= 120):
            continue
        if len(blank_re.findall(stem)) != 1:
            continue
        if "ABCDEFGH".index(ans) >= len(opts):
            continue
        clean_opts = []
        ok = True
        for o in opts:
            if not (2 <= len(o) <= 20) or blank_re.search(o) or ALL_OF_RE.match(o):
                ok = False
                break
            if any(ch in o for ch in "。；;！？"):
                ok = False
                break
            clean_opts.append(o)
        if not ok:
            continue
        correct = clean_opts["ABCDEFGH".index(ans)]

        # ---- 填空题 ----
        # 注意：题干必须**保留空白位**（`____`），否则 App 的填空流程无法作答。
        if len(fills) < max_fill:
            key = normalize_stem(stem)
            if len(stem) >= 8 and key not in seen_stmt:
                seen_stmt.add(key)
                fills.append({
                    "id": "",
                    "type": "fill",
                    "stem": stem,
                    "options": [],
                    "answer": [correct],
                    "explanation": f"由单选题派生（原题 {q['id']}）。正确答案：{correct}",
                    "source": q["source"],
                    "chapter": q["chapter"],
                    "section": "填空题（派生）",
                    "raw": q["raw"][:200],
                })

        # ---- 判断题 ----
        if len(judges) < max_judge:
            # 正确陈述
            stmt_t = blank_re.sub(correct, stem)
            kt = normalize_stem(stmt_t)
            if len(stmt_t) >= 8 and kt not in seen_judge_stem and not BAD_JUDGE_STEM.search(stem):
                seen_judge_stem.add(kt)
                judges.append({
                    "id": "",
                    "type": "judge",
                    "stem": stmt_t,
                    "options": [],
                    "answer": True,
                    "explanation": f"正确。由单选题派生（原题 {q['id']}）。",
                    "source": q["source"],
                    "chapter": q["chapter"],
                    "section": "判断题（派生）",
                    "raw": q["raw"][:200],
                })
            # 错误陈述（取一个语义不同、长度接近的错误选项）
            wrongs = [o for i, o in enumerate(clean_opts) if i != "ABCDEFGH".index(ans)]
            wrongs.sort(key=lambda o: abs(len(o) - len(correct)))
            for w in wrongs[:1]:
                stmt_f = blank_re.sub(w, stem)
                kf = normalize_stem(stmt_f)
                if (len(stmt_f) >= 8 and kf not in seen_judge_stem
                        and not BAD_JUDGE_STEM.search(stem)):
                    seen_judge_stem.add(kf)
                    judges.append({
                        "id": "",
                        "type": "judge",
                        "stem": stmt_f,
                        "options": [],
                        "answer": False,
                        "explanation": f"错误。正确表述应为「{correct}」"
                                       f"（由单选题派生，原题 {q['id']}）。",
                        "source": q["source"],
                        "chapter": q["chapter"],
                        "section": "判断题（派生）",
                        "raw": q["raw"][:200],
                    })
                break
    return fills, judges


def reclassify_short_as_fill(questions: list[dict]) -> int:
    """把「简答题」里其实是填空题的题（含空白且答案很短）改为 fill。"""
    n = 0
    blank_re = re.compile(r"[_＿]{2,}")
    for q in questions:
        if q["type"] != "short":
            continue
        ans = q["answer"] if isinstance(q["answer"], str) else ""
        if blank_re.search(q["stem"]) and 0 < len(ans) <= 12:
            q["type"] = "fill"
            q["answer"] = [ans]
            q["section"] = "填空题（由简答区识别）"
            n += 1
    return n


# ---------------------------------------------------------------------------
# 人工校订表（Curated Patches）
# ---------------------------------------------------------------------------
# 说明：多选题答案来自源 PDF 的歧义字母串，程序用确定性策略切分，绝大多数
# 与通行表述一致，但个别题目按题意可判定切分有误。下面这些条目是**独立质检
# () 出具、并逐条核对原卷选项语义后确认**的修正，属「人工覆盖」，
# 因此 `answerUncertain` 会置为 False，并在解析里注明校订来源。
#
# 维护方式：如需新增，请同时给出「题干关键词 + 正确字母 + 判定依据」，
# 并在 `docs/qa-report.md` 中登记，保持可追溯。
CURATED_FIXES: dict[str, dict] = {
    # ---------- 高置信：源卷/提纲原文直接列举，可判定 ----------
    "公民的国防义务": {
        "answer": ["A", "B", "C", "D"],
        "why": "提纲 0-outline.txt:69《宪法》第五十五条列明公民国防义务；同库简答答案亦"
               "列举服兵役、接受国防教育、保护国防设施、保守国防秘密、支持国防建设等。",
    },
    "新型军兵种结构布局": {
        "answer": ["A", "B", "C", "D"],
        "why": "提纲 0-outline.txt:139：解放军形成陆军、海军、空军、火箭军等军种和军事航天、"
               "网络空间、信息支援、联勤保障等兵种的新型军兵种结构布局。",
    },
    "政治工作的原则有哪些": {
        "answer": ["A", "B", "D"],
        "why": "提纲 0-outline.txt:408：政治工作三大原则——官兵一致、军民一致、瓦解敌军。"
               "C「权力平等」不在其中。",
    },
    "政治工作的三大原则": {
        "answer": ["A", "B", "C"],
        "why": "提纲 0-outline.txt:408：官兵一致、军民一致、瓦解敌军（D「党指挥枪」是"
               "根本原则，不属三大原则）。",
    },
    "武警部队由": {
        "answer": ["A", "B", "C", "D"],
        "why": "提纲 0-outline.txt:156：武警部队由内卫部队、机动部队、海警部队以及院校和"
               "研究机构等组成。",
    },
    "国防动员内容的有": {
        "answer": ["A", "B", "C", "D"],
        "why": "提纲 0-outline.txt:171：国防动员内容分为武装力量动员、国民经济动员、"
               "人民防空动员、交通动员、装备动员、信息动员、政治动员七类，四项皆属其中。",
    },
    "信息动员主要包括": {
        "answer": ["A", "B", "C", "D"],
        "why": "提纲 0-outline.txt:175：信息动员主要包括信息基础设施动员、信息情报资源动员、"
               "信息专业力量动员和信息产业动员。",
    },
    "中国在多极格局中的地位与作用": {
        "answer": ["A", "B", "C"],
        "why": "提纲 0-outline.txt:289：一是在反对霸权主义和强权政治上起制约作用，二是在"
               "经济发展上起示范作用，三是在维护第三世界权益的斗争中起重要作用。",
    },
    "构建人类命运共同体": {
        "answer": ["A", "B", "C"],
        "why": "提纲 0-outline.txt:292：根本目标与核心任务是建设持久和平、普遍安全、共同繁荣、"
               "开放包容、清洁美丽的世界。",
    },
    "人民战争思想的基本原理": {
        "answer": ["A", "B", "C", "D"],
        "why": "提纲 0-outline.txt:411：基本原理——革命战争是群众的战争、战争伟力之最深厚的"
               "根源存在于民众之中、兵民是胜利之本、决定战争胜负的因素是人不是物。",
    },
    "必须确保部队": {
        "answer": ["A", "C", "D"],
        "why": "提纲 0-outline.txt:438：确保部队绝对忠诚、绝对纯洁、绝对可靠。"
               "B「绝对服从」不是原文表述。",
    },
    "作战要素一体化": {
        "answer": ["A", "B", "C", "D"],
        "why": "提纲 0-outline.txt:536：作战力量一体化、作战行动一体化、作战指挥一体化、"
               "综合保障一体化。",
    },
    "信息空间包括": {
        "answer": ["A", "C", "D"],
        "why": "1-textbook.txt:1426 与 0-outline.txt:533：信息空间包括电磁空间、网络空间和"
               "心理空间；B「作战空间」不是其构成。",
    },
    # ---------- 中等置信：术语口径需人工拍板，改答案但保留存疑标记 ----------
    "新兴领域国家安全": {
        "answer": ["A", "B", "C"],
        "why": "提纲 0-outline.txt:254 将科技安全、信息安全、海外利益安全列入非传统领域"
               "国家安全（题干称「新兴领域」，口径存疑，故仍保留存疑标记）。",
        "confidence": "medium",
    },
    "战前国防动员": {
        "answer": ["A", "B", "D"],
        "why": "提纲 0-outline.txt:171 的七类动员含国民经济动员（动员基础）与武装力量动员、"
               "政治动员；C「外交动员」不在七类内。题干「战前」源文件无专门定义，口径存疑，"
               "故仍保留存疑标记。",
        "confidence": "medium",
    },
    "两个结合": {
        "answer": ["A", "C"],
        "why": "我国兵役制度的“两个结合”＝义务兵役制与志愿兵役制相结合（A）、"
               "民兵与预备役相结合（C）；D「现役与预备役相结合」不是通行表述。",
    },
    "一带一路": {
        "answer": ["A", "B"],
        "why": "“一带一路”＝丝绸之路经济带（A）+ 21 世纪海上丝绸之路（B）；"
               "C/D（势力范围战略、贸易壁垒策略）与倡议无关。",
    },
    "新概念武器有什么": {
        "answer": ["A", "B", "C"],
        "why": "新概念武器指电磁发射器、激光武器、气象武器等；核武器属传统大规模"
               "杀伤武器，不列入新概念武器。",
    },
    # 注意：关键词必须够特指，避免与上面「新概念武器有什么」互相串题
    "新概念武器按基本原理": {
        "answer": ["A", "B"],
        "why": "新概念武器按基本原理分为定向能武器与动能武器；常规火炮、制导导弹"
               "均属传统/精确制导武器。同库单选题「新概念武器按基本原理可分为定向能"
               "武器、动能武器和？」（答案 A）互证。",
    },
    "传统领域国家安全": {
        "answer": ["A", "B", "C"],
        "why": "源卷参考答案原文（真题第 64 题，build/text/2-past.txt）：传统安全威胁"
               "包括政治安全、国土安全、军事安全等传统安全领域；经济安全被明确归入"
               "非传统安全威胁。故 A 政治安全、B 国土安全、C 军事安全 全选，D 不选。",
    },
}


def apply_curated_fixes(questions: list[dict]) -> tuple[int, int]:
    """应用人工校订表：按题干关键词匹配多选题并覆盖答案。

    返回 `(高置信校订数, 中等置信校订数)`。
    高置信条目 `answerUncertain` 置为 False；中等置信条目改答案但**保留**存疑标记
    （术语口径仍需人工拍板，不能给用户「已确认」的错觉）。
    """
    hi = mid = 0
    for q in questions:
        if q["type"] != "multi":
            continue
        for kw, fix in CURATED_FIXES.items():
            if kw in q["stem"]:
                medium = fix.get("confidence") == "medium"
                changed = list(q["answer"]) != list(fix["answer"])
                if changed:
                    q["answer"] = list(fix["answer"])
                q["explanation"] = (
                    ("已人工校订答案" if not medium else "答案已人工修正，但术语口径待确认")
                    + "（独立质检发现源答案串切分有误）：" + fix["why"])
                if medium:
                    q["answerUncertain"] = True
                    if changed:
                        mid += 1
                else:
                    q["answerUncertain"] = False
                    if changed:
                        hi += 1
                break
    return hi, mid


def add_objective(q: RawQ, source: str, ans, qtype: str, questions: list, stats: dict,
                  dropped: dict, seen_stems: set, report: list) -> None:
    stem = clean(q.stem)
    stem = re.sub(r"[（(]\s*[）)]\s*$", "", stem).strip()   # 去掉题尾空括号
    if len(stem) < 4:
        dropped["empty_stem"] += 1
        return
    opts = [clean(o) for o in q.options if clean(o)]
    # 去掉选项里误并入的「答案：X」
    cleaned_opts = []
    for o in opts:
        o = re.sub(r"^\s*(参考答案|正确答案|答案)\s*[:：].*$", "", o).strip()
        if o:
            cleaned_opts.append(o)
    opts = cleaned_opts
    if len(opts) < 2:
        dropped["bad_options"] += 1
        return
    if qtype == "single":
        if not ans or ans not in "ABCDEFGH"[:len(opts)]:
            dropped["no_answer"] += 1
            return
        answer = ans
        # 若答案字母超出选项范围，丢弃
        if "ABCDEFGH".index(ans) >= len(opts):
            dropped["no_answer"] += 1
            return
    else:
        if not ans or len(ans) < 2:
            dropped["multi_unsplit"] += 1
            return
        answer = [a for a in sorted(set(ans)) if "ABCDEFGH".index(a) < len(opts)]
        if len(answer) < 2:
            dropped["multi_unsplit"] += 1
            return
    norm = normalize_stem(stem)
    if norm in seen_stems:
        dropped["dup"] += 1
        return
    seen_stems.add(norm)
    q_obj = {
        "id": "",
        "type": qtype,
        "stem": stem,
        "options": opts,
        "answer": answer,
        "explanation": "",
        "source": source,
        "chapter": q.chapter,
        "section": q.kind,
        "raw": clean(q.raw)[:400],
    }
    # 源文件把多选题答案压成连续字母串，切分存在固有歧义 → 仅 multi 显式标注
    if qtype == "multi":
        q_obj["answerUncertain"] = True
    questions.append(q_obj)
    stats[qtype] += 1


def main() -> int:
    bank, report, dropped = build_question_bank()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")

    print("=" * 74)
    print("题库生成报告")
    print("=" * 74)
    for line in report:
        print(line)
    print("-" * 74)
    print(f"题型统计: {bank['counts']}")
    print(f"来源: {bank['sources']}")
    print(f"丢弃统计: {dropped}")
    print(f"输出: {OUT}  ({OUT.stat().st_size / 1024:.1f} KB)")
    print("-" * 74)
    print("抽样 6 题：")
    for q in bank["questions"][:2] + bank["questions"][-4:]:
        ans = q["answer"]
        print(f"  [{q['id']}] ({q['type']}/{q['source']}/{q['chapter']}) {q['stem'][:60]}")
        for i, o in enumerate(q["options"]):
            print(f"      {chr(65 + i)}. {o[:58]}")
        print(f"      答案: {ans}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
