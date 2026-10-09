#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_extract.py — 批量把 4 份源 PDF 提取为 UTF-8 文本，并打印体检报告。

用法:
    python run_extract.py            # 跳过已存在的输出
    python run_extract.py --force    # 全部重新提取
"""
import sys
import time
from pathlib import Path

# Windows 控制台默认 GBK，无法打印 • 等字符；强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FORCE = "--force" in sys.argv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from pdftext import extract_pdf  # noqa: E402

SRC = ROOT.parent / "军理课资料"   # 自行准备：把资料放这里（本项目不发布语料）
OUT = ROOT / "build" / "text"
OUT.mkdir(parents=True, exist_ok=True)

JOBS = [
    (SRC / "0" / "【2026年最新版】军理课提纲.pdf", "0-outline.txt"),
    (SRC / "1" / "【2026年最新版】普通高校军事课教程.pdf", "1-textbook.txt"),
    (SRC / "2" / "【最新最全】军理课真题集合.pdf", "2-past.txt"),
    (SRC / "3" / "【最新最全】军理课模拟题集合.pdf", "3-mock.txt"),
]

for src, name in JOBS:
    dst = OUT / name
    if dst.exists() and not FORCE:
        text = dst.read_text(encoding="utf-8")
        cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        print(f"SKIP {name}: 已存在，{len(text)} 字符, 中文 {cjk}")
        continue
    t0 = time.time()
    try:
        text = extract_pdf(src, verbose=True)
    except Exception as e:
        print(f"!! {src.name} 提取失败: {type(e).__name__}: {e}")
        continue
    dst.write_text(text, encoding="utf-8")
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    print(f"OK {name}: {len(text)} 字符, 中文 {cjk}, 非空行 {len(lines)}, "
          f"{time.time() - t0:.1f}s")
    print("  --- 前 12 行 ---")
    for ln in lines[:12]:
        print("  | " + ln[:110])
    print()
