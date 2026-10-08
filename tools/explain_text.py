#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
explain_text.py — 解析文案清理与结构化
=====================================

问题背景（实测数据）：
  * **101 道**解析里含「中文 空格 中文」——PDF 提取时字间插了空格，例如
      `( 一 ) 古 代 国 防中国古代国防始于公元前 21 世纪的夏王朝`
    用户看到这种文字既难读、又像乱码。
  * 解析是「答案 —— 一句教材原句」的长段落，没有层次，不利于理解。

本模块做两件事：
  `clean_evidence(text)` —— 清理提取噪声，得到可读的教材原句；
  `split_sentences(text)` —— 把长段落按句切开，便于挑出最相关的一句。
"""

from __future__ import annotations

import re

CJK = r"\u4e00-\u9fff"
# 空格清理规则（**只删安全的一侧**）：
#   * 开括号/开书名号**之后**的空格 → 删（`( 一` → `(一`）
#   * 闭括号/闭书名号/标点**之前**的空格 → 删（`一 )` → `一)`、` ，` → `，`）
#   * **绝不**删「闭符号 与 下一个开符号」之间的空格：`》 《` 删掉会把书名号粘成一团
#     （实测踩过：`《国防法 》《 国防法 》` 被压成 `《国防法》《国防法》` 甚至丢括号）
_AFTER_OPEN = re.compile(r"(?<=[（(〔【《〈“”‘’])[ \t\u3000]+")
_BEFORE_CLOSE = re.compile(r"[ \t\u3000]+(?=[）)〕】》〉，。；：、！？])")
# 句读标点**之后**的空格（中文排版里 `、 现代` 是噪声）；
# 注意不含 `）》《`——那后面跟空格往往是正常的（`》(以下…)` 除外）
_AFTER_PUNCT = re.compile(r"(?<=[、，。；：！？])[ \t\u3000]+")
# 汉字之间的空格（含全角空格）——PDF 排版噪声
_CJK_SPACE = re.compile(rf"(?<=[{CJK}])[ \t\u3000]+(?=[{CJK}])")
# 汉字与数字/拉丁字母之间的多余空格
_CJK_NUM_SPACE = re.compile(rf"(?<=[{CJK}])[ \t\u3000]+(?=[0-9A-Za-z])"
                            rf"|(?<=[0-9A-Za-z])[ \t\u3000]+(?=[{CJK}])")
# 数字之间的空格（`2020 年 12月 26 日` → `2020年12月26日` 的一半）
_NUM_SPACE = re.compile(r"(?<=[0-9])[ ]+(?=[0-9])")
# 悬挂的句点/编号
_LEAD_NOISE = re.compile(r"^[\s.·。]+|^\d{1,3}\s*[.、．]\s*")
# 小节编号如「( 一 ) 古 代 国 防」——页内小节标题，作为解析开头很突兀
_SECTION_NOISE = re.compile(rf"^[（(]\s*[一二三四五六七八九十\d]+\s*[)）]\s*"
                            rf"[{CJK}\s]{{0,20}}?(?=[{CJK}]{{8,}})")
# 页内小节号 + 小节标题，如「五、现代国防的基本特征」「(一)古代国防」，
# 其后紧跟正文 —— 整段剥掉，否则解析开头会像目录
_HEADING_NOISE = re.compile(
    rf"^(?:[（(]\s*[一二三四五六七八九十\d]+\s*[)）]|[一二三四五六七八九十\d]+\s*[、.．])"
    rf"\s*[{CJK}A-Za-z0-9]{{2,18}}?(?=[{CJK}]{{10,}})")
# 重复的书名/引号串：`《X》《X》` → `《X》`（PDF 把页眉里的标题与正文标题粘在一起）
_DUP_TITLE = re.compile(r"(《[^》]{2,30}》)\1+")
_DUP_QUOTE = re.compile(r"(“[^”]{2,30}”)\1+")
# 知识链接/页眉标记
_LINK_NOISE = re.compile(r"^★?\s*知\s*识\s*链\s*接\s*[:：]?\s*")
_EMPTY_PAREN = re.compile(r"[（(]\s*[)）]")
_DUP_PUNCT = re.compile(r"([，。；、！？])\1+")
_WS = re.compile(r"[ \t\u3000]{2,}")


def _strip_heading(s: str) -> str:
    """剥掉句首的「页内小节标题」，只针对**能确证是标题**的情况。

    教材页眉/小节标题会和正文粘在一起，例如
      `五、现代国防的基本特征现代国防是对传统国防的继承…`
      `(一)古代国防中国古代国防始于公元前21世纪的夏王朝…`
    判据：删除小节号后，句首 2~20 字里存在一段（≥3 字），
    **它在紧随其后的位置（≤20 字内）又出现一次** —— 前一段是标题，后一段是正文。
    找不到确证就原样返回：宁可留一点标题痕迹，也不能把正文吃掉
    （第一版正则太宽，把正文也删了，实测踩过）。
    """
    # 先去掉小节号本身 `五、` / `(一)` / `5.`
    body = re.sub(rf"^(?:[（(]\s*[一二三四五六七八九十\d]+\s*[)）]"
                  rf"|[一二三四五六七八九十\d]+\s*[、.．])\s*", "", s)
    if len(body) < 12:
        return body or s
    win = body[:22]
    for size in range(min(8, len(win) - 3), 2, -1):
        frag = win[:size]
        if len(frag) < 3:
            continue
        nxt = body.find(frag, size, size + 22)
        if nxt > 0:
            # 前一段（标题）被跳过，从重复处开始才是正文
            return body[nxt:]
    return body


def clean_evidence(text: str) -> str:
    """清理 PDF 提取噪声，返回可读的教材原句。

    顺序：去开括号后/闭符号前的空格 → 去句读后空格 → 去数字内空格 →
    反复去汉字间空格 → 去汉字与数字间空格 → 去重复书名号 → 剥页内标题。
    **不触碰闭符号与开符号之间的空格**（否则 `》 《` 会粘成一团）。
    """
    if not text:
        return ""
    s = str(text).replace("\x00", " ").replace("\ufeff", "")
    s = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", " ", s)
    s = _LEAD_NOISE.sub("", s)
    s = _LINK_NOISE.sub("", s)
    s = _AFTER_OPEN.sub("", s)
    s = _BEFORE_CLOSE.sub("", s)
    s = _AFTER_PUNCT.sub("", s)
    s = _NUM_SPACE.sub("", s)
    for _ in range(4):                      # 汉字间空格可能连着多组
        s2 = _CJK_SPACE.sub("", s)
        if s2 == s:
            break
        s = s2
    s = _CJK_NUM_SPACE.sub("", s)
    s = _EMPTY_PAREN.sub("", s)
    s = _DUP_PUNCT.sub(r"\1", s)
    s = _DUP_TITLE.sub(r"\1", s)
    s = _DUP_QUOTE.sub(r"\1", s)
    s = _WS.sub(" ", s)
    s = _strip_heading(s)
    s = s.strip(" 　\t.·。，、；：")
    return s


_SENT_SPLIT = re.compile(r"(?<=[。！？；])")


def split_sentences(text: str) -> list[str]:
    """把长段落切成句子（保留句末标点），便于挑最相关的一句。"""
    out = []
    for p in _SENT_SPLIT.split(text or ""):
        p = clean_evidence(p)
        if len(p) >= 6:
            out.append(p)
    return out


def trim_sentence(sent: str, maxlen: int = 120) -> str:
    """把一句教材原句修剪到适合阅读的长度：优先在分号/逗号处断开。"""
    s = clean_evidence(sent)
    if len(s) <= maxlen:
        return s
    for sep in ("；", "，", "、"):
        i = s.rfind(sep, 0, maxlen)
        if i >= maxlen * 0.5:
            return s[:i] + "。"
    return s[:maxlen] + "…"


def structure(*, answer: str = "", reason: str = "", note: str = "",
              ref: str = "") -> dict:
    """把解析拆成结构化字段，便于前端分行、加标签、加粗。

    前端只需按固定标签渲染，不必解析长字符串：
      answer → 「正确答案」
      reason → 「为什么」
      note   → 「提示」（可选，如存疑说明/核验范围）
      ref    → 「依据出处」
    """
    d: dict[str, str] = {}
    if answer:
        d["answer"] = clean_evidence(answer)
    if reason:
        d["reason"] = clean_evidence(reason) if len(reason) < 400 else clean_evidence(reason)
    if note:
        d["note"] = note.strip()
    if ref:
        d["ref"] = ref.strip()
    return d


def render_text(parts: dict) -> str:
    """把结构化解析拼回**纯文本**，供搜索/导出/旧渲染路径使用。

    注意：这里**用换行分隔**，不能用空格 ——
    用空格会在「汉字 空格 汉字」之间造出新的排版噪声
    （实测：`…、分裂 国防的对象，一是侵略…`），与清理目标自相矛盾。
    """
    out = []
    if parts.get("answer"):
        out.append("正确答案：" + parts["answer"])
    if parts.get("reason"):
        out.append(parts["reason"])
    if parts.get("note"):
        out.append("提示：" + parts["note"])
    if parts.get("ref"):
        out.append("依据：" + parts["ref"])
    return "\n".join(out).strip()
