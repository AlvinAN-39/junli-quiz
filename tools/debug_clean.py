#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debug_clean.py — 逐步验证 clean_evidence 的行为，找出破坏括号/书名号的原因。"""
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
import explain_text as T  # noqa: E402

CASES = [
    "( 一 ) 古 代 国 防中国古代国防始于公元前 21 世纪的夏王朝，止于 1840 年的鸦片战争，历 经 近 4000年、 20 多个王朝的更迭",
    ". 《中华人民共和国国防法 》《 中 华 人 民 共 和 国 国 防 法 》 ( 以 下 简 称 《 国 防 法 》 ) 于1997 年 3 月 14日通过",
    "五 、 现 代 国 防 的 基 本 特 征现代国防是对传统国防的继承和发展，是在综合国力的基础上，以军事手段配合政治、经济、科技、外交等手段进行的总体较量",
    "《中华人民共和国国防教育法》( 以下简 称 《 国 防 教 育 法 》 ) 于2001 年 4 月 28 日由第九届全国人民代表大会常务委员会第二十一次会议通过并实施；",
    "其余 18 岁 至 35 岁",
]

for c in CASES:
    print("原始:", c[:90])
    print("清理:", T.clean_evidence(c)[:110])
    print()

# 再看题库里剩下的 903 道到底是什么样的空格
import json, re
from pathlib import Path
qs = json.loads((Path(__file__).resolve().parent.parent / "data" / "questions.json").read_text(encoding="utf-8"))["questions"]
bad = [q for q in qs if re.search(r"[\u4e00-\u9fff]\s[\u4e00-\u9fff]", q.get("explanation") or "")]
print(f"题库存量：仍含「汉字 空格 汉字」的 {len(bad)} 道")
for q in bad[:5]:
    e = q["explanation"]
    m = re.search(r".{0,12}[\u4e00-\u9fff]\s[\u4e00-\u9fff].{0,12}", e)
    print(f"  [{q['id']} {q.get('explanationSrc')}] …{m.group(0) if m else ''}…")
    print(f"      full: {e[:130]}")
print()
# 检查 explanationParts 与 explanation 是否一致
same = sum(1 for q in qs if (q.get("explanationParts", {}).get("reason") or "") in (q.get("explanation") or ""))
print(f"explanationParts.reason 出现在 explanation 中的题数: {same}/{len(qs)}")
