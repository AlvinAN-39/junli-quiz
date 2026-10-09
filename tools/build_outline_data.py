#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_outline_data.py — 把【26最新改版】军理课提纲 PDF 转成结构化提纲数据。

用户 2026-10-09 要求：复习提纲模块的内容改为**加入新的提纲 PDF**
（`D:/fields/xwechat_files/.../【26最新改版】军理课提纲(1).pdf`），替换原来「按题库解析聚合」的内容。

切分口径（实测踩过坑后定的）
------------------------
* 章：`第一章中国国防` 这类固定串（5 个）。
* 节：`第X节` + 紧随的节名；节名以「首个句读」为界，避免把正文首句吞进标题
  （旧版曾产出「第一节国防概述国防是一个历史概念」这种脏标题）。
* 小节：以**行首编号**为准 —— `㈠㈡㈢…`（国防/理论类条目）与 `⒈⒉⒊…`（细分条目）。
  用行首而非全串匹配，是因为正文里也大量出现「一、」「二、」的引用，全串匹配会把正文切碎。
* 页眉页脚：`=== PAGE n ===` 与行首孤零零的页码（如 `12第一章…`）在清洗阶段去掉。

输出：`data/outline-2026.json`（前端只消费这个 JSON，不直接解析 PDF，保持零依赖）

用法：python tools/build_outline_data.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "text" / "4-outline-2026.pdf.txt"
OUT = ROOT / "data" / "outline-2026.json"

CH_RE = re.compile(r"第([一二三四五])章(中国国防|国家安全|军事思想|现代战争|信息化装备)")
SEC_RE = re.compile(r"第([一二三四五六七八九十]+)节\s*([^，。；：、\s]{2,12})")
# 小节标记：行首的 ㈠…㈩ 或 ⒈…⒑
SUB_LINE_RE = re.compile(r"(?m)^\s*([㈠㈡㈢㈣㈤㈥㈦㈧㈨㈩⒈⒉⒊⒋⒌⒍⒎⒏⒐⒑])\s*(.{0,30})")
PAGE_RE = re.compile(r"=== PAGE \d+ ===")
LEAD_NUM_RE = re.compile(r"(?m)^\s*\d{1,3}(?=第|㈠|[㈠-㈩])")
TITLE_STOP = "，。；：()《》\"“”‘’"

# 21 个标准节名（来自教材/考纲目录）。
# 为什么写死：该 PDF 的节标题与正文首句**没有任何分隔符**（「第二节国防法规国防法规是国家为了加强防务…」），
# 用算法切永远会多切或少切（实测产出了「第一节国防概述国防是一个历史概念」这种脏标题）。
# 节名是确定且封闭的 21 个，直接按「最长匹配」切最可靠；若将来改版目录变了，改这一处即可。
SECTION_NAMES = {
    "第一章中国国防": ["国防概述", "国防法规", "国防建设", "武装力量", "国防动员"],
    "第二章国家安全": ["国家安全概述", "国家安全形势", "国际战略形势"],
    "第三章军事思想": ["军事思想概述", "外国军事思想", "中国古代军事思想", "当代中国军事思想"],
    "第四章现代战争": ["战争概述", "新军事革命", "机械化战争", "信息化战争", "混合战争"],
    "第五章信息化装备": ["信息化装备概述", "信息化作战平台", "综合电子信息系统", "信息化杀伤武器"],
}
_ORD = "一二三四五六七八九十"


def clean(s: str) -> str:
    s = PAGE_RE.sub("", s)
    s = LEAD_NUM_RE.sub("", s)
    s = s.replace("\u3000", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


def cut_title(s: str, maxlen: int = 12) -> str:
    """把「节名+正文首句」截成纯节名。

    PDF 里标题与正文常常没有任何标点分隔（如「第一节国防概述国防是一个历史概念，随阶级…」），
    所以不能只靠句读截断；再叠一条长度上限。实测 5 章的节名都在 8 字以内，
    取 12 字作界限可保证不吞正文，也不会切掉真实节名。
    """
    out = []
    for ch in s[:maxlen]:
        if ch in TITLE_STOP or ch == "\n":
            break
        out.append(ch)
    return "".join(out).strip()


def clean_section_title(sec_body: str, snum: str) -> str:
    """节名 = 「第X节」之后到节名结束的一段。

    实测：该 PDF 的节标题后紧跟正文首句且没有标点分隔（如
    「第一节国防概述国防是一个历史概念，随阶级…」）。可靠的分界是下一级标记：
      · 小节/正文编号：`一、`、`二、`（含紧跟的 `（P4）` 页码）
      · 句读：，。；：
    先截到第一个分界，再叠 14 字上限兜底。
    """
    tail = sec_body[len(f"第{snum}节"):]
    cut = len(tail)
    for m in re.finditer(r"[一二三四五六七八九十]+、|（P\d+）|[，。；：]", tail):
        cut = min(cut, m.start())
    return f"第{snum}节" + tail[:cut][:14].strip()


def main() -> int:
    if not SRC.exists():
        print(f"!! 源文本不存在：{SRC}\n   先运行 tools/pdftext.py 提取 PDF")
        return 2
    raw = clean(SRC.read_text(encoding="utf-8"))

    ch_pos = [(m.start(), m.group(1), m.group(2)) for m in CH_RE.finditer(raw)]
    if len(ch_pos) < 5:
        print(f"!! 只匹配到 {len(ch_pos)} 个章标题（应为 5）")
        return 3

    chapters = []
    for i, (pos, num, name) in enumerate(ch_pos):
        end = ch_pos[i + 1][0] if i + 1 < len(ch_pos) else len(raw)
        body = raw[pos:end]
        ch_title = f"第{num}章{name}"

        sec_pos = []
        for si, sname in enumerate(SECTION_NAMES.get(ch_title, [])):
            tok = f"第{_ORD[si]}节{sname}"
            p = body.find(tok)
            if p >= 0:
                sec_pos.append((p, tok))
            else:
                # 极端情况：目录串与正文不一致时退回旧口径，并打印告警（不静默）
                print(f"  ! {ch_title} 未找到节标题「{tok}」，改用文本切分")
                m = SEC_RE.search(body)
                if m:
                    sec_pos.append((m.start(), m.group(0)))
        sec_pos.sort(key=lambda x: x[0])
        sections = []
        for j, (spos, sec_title) in enumerate(sec_pos):
            send = sec_pos[j + 1][0] if j + 1 < len(sec_pos) else len(body)
            sec_body = body[spos:send]

            # 小节：按行首编号标记切分
            marks = list(SUB_LINE_RE.finditer(sec_body))
            subs = []
            for k, m in enumerate(marks):
                mstart = m.start()
                mend = marks[k + 1].start() if k + 1 < len(marks) else len(sec_body)
                block = sec_body[mstart:mend].strip()
                if len(block) < 4:
                    continue
                first = block.split("\n", 1)[0]
                title = cut_title(first[1:].strip() if first and first[0] in "㈠㈡㈢㈣㈤㈥㈦㈧㈨㈩⒈⒉⒊⒋⒌⒍⒎⒏⒐⒑" else first, maxlen=20)
                subs.append({"title": title or block[:18], "text": block})
            sections.append({"section": sec_title, "text": sec_body.strip(),
                             "subs": subs, "chars": len(sec_body.strip())})
        chapters.append({"chapter": ch_title, "sections": sections, "chars": len(body.strip())})

    total_chars = sum(c["chars"] for c in chapters)
    total_sections = sum(len(c["sections"]) for c in chapters)
    total_subs = sum(len(s["subs"]) for c in chapters for s in c["sections"])
    data = {
        "source": "【26最新改版】军理课提纲（第二版，Silensky 整理，2026-10-06）",
        "basis": "中山大学出版社《普通高校军事课教程》（2023年8月第1版、2026年5月第4次印刷）",
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "stats": {"chapters": len(chapters), "sections": total_sections,
                  "subs": total_subs, "chars": total_chars},
        "chapters": chapters,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"已生成 {OUT}")
    print(f"  章 {len(chapters)} / 节 {total_sections} / 小节 {total_subs} / 正文 {total_chars} 字符 / 文件 {OUT.stat().st_size/1024:.0f} KB")
    for c in chapters:
        print(f"  {c['chapter']}: {len(c['sections'])} 节 / {c['chars']} 字符")
        for s in c["sections"]:
            print(f"      {s['section']} — {len(s['subs'])} 小节 / {s['chars']} 字符")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
