#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
answer_text.py — 题库「答案」字段的统一读取工具（单一真相）
==========================================================

为什么需要这个模块：
  `answer` 字段的形态**按题型不统一**，而项目里曾有 6 处各自实现了一遍读取逻辑，
  且**都假定 single 是字符串**。修正答案时引入了 7 道 `answer` 为列表的单选，
  于是这 6 处全部抛 `TypeError: 'in <string>' requires string as left operand, not list`，
  相互独立却同时崩 —— 正是「同一段逻辑出现第二处」的代价。

本模块是**唯一**的答案读取实现，供所有脚本与校验使用。

形态约定（也已按此修正题库数据）：
  single → 字符串（"A"）
  multi  → 字母数组（["A","B"]）
  judge  → 布尔（True/False）
  fill   → 字符串**或**单元素数组（两种历史形态并存，故此处容错）
  short  → 参考答案文本
"""

from __future__ import annotations

LETTERS = "ABCDEFGH"

# 注意：必须用**集合**判断，不能用 `a in LETTERS` —— 后者是子串匹配，
# 会把 ""、"AB"、"ABC" 当成合法答案，再经 `LETTERS.index()` 静默落到错误选项上
# （实测 `answer_text({"type":"single","answer":"AB"})` 返回 A 的文本而不是报错）。
_LETTER_SET = frozenset(LETTERS)


def letters_of(q) -> list[str]:
    """返回答案的字母列表（仅选择题有意义）；非选择题返回空列表。

    容错：single 若是单元素列表也接受 —— 数据层虽已修正，但读取端不应因此崩溃。
    """
    a = q.get("answer")
    if q.get("type") == "single":
        if isinstance(a, str) and a in _LETTER_SET:
            return [a]
        if isinstance(a, list) and len(a) == 1 and isinstance(a[0], str) and a[0] in _LETTER_SET:
            return [a[0]]
        return []
    if q.get("type") == "multi":
        if not isinstance(a, list):
            return []
        return [x for x in a if isinstance(x, str) and x in _LETTER_SET]
    return []


def answer_text(q) -> str:
    """取「用于比对解析是否支持答案」的答案**文本**。

    这是全项目唯一的实现：任何脚本需要答案文本都应调用它，不要各写一份。
    """
    t = q.get("type")
    a = q.get("answer")
    opts = q.get("options") or []

    if t == "single":
        ls = letters_of(q)
        if not ls:
            return ""
        i = LETTERS.index(ls[0])
        return opts[i] if i < len(opts) else ""

    if t == "multi":
        out = []
        for x in letters_of(q):
            i = LETTERS.index(x)
            if i < len(opts):
                out.append(opts[i])
        return "".join(out)

    if t == "judge":
        return "正确" if a is True else "错误"

    if t == "fill":
        if isinstance(a, list):
            return str(a[0]) if a else ""
        return str(a) if a else ""

    # short：参考答案即答案文本
    if isinstance(a, list):
        return "".join(str(x) for x in a)
    return str(a) if a else ""


def answer_display(q, letters: str = LETTERS) -> str:
    """用于展示的答案字符串：选择题给「A、文本」，其余给文本。"""
    t = q.get("type")
    opts = q.get("options") or []
    if t == "single":
        ls = letters_of(q)
        if not ls:
            return ""
        i = letters.index(ls[0])
        return ls[0] + ("、" + opts[i] if i < len(opts) else "")
    if t == "multi":
        ls = letters_of(q)
        names = [opts[letters.index(x)] for x in ls if letters.index(x) < len(opts)]
        return "、".join(ls) + ("（" + "；".join(names) + "）" if names else "")
    if t == "judge":
        return "正确" if q.get("answer") is True else "错误"
    a = q.get("answer")
    if isinstance(a, list):
        return "；".join(str(x) for x in a)
    return str(a) if a else ""
