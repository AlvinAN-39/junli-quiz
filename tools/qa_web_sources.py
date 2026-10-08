#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qa_web_sources.py — 独立复核「联网核查来的依据」
==============================================

不信任 merge 脚本自报的数字，换个角度重新检查每一条 `explanationSrc == "web"` 的依据：

  A. **出处完整性**：是否都有 `explanationRef`、`webSourceUrl`，URL 是否为 http(s)。
  B. **相关性**：依据句与题干的最长连续汉字重合（沿用本地依据同一把尺子）。
  C. **是否只是复述答案**：依据句去掉答案后还剩多少有效内容
     （如果依据 = 题干 + 答案，那它没有解释力）。
  D. **互相矛盾**：同一个知识点被多道题引用时，是否出现"同句依据、不同结论"。
  E. **被核查标记为 disputed 的题**：单独列出，供人工对照原卷。
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
sys.path.insert(0, str(ROOT / "tools"))
import gen_explanations as G                          # noqa: E402
from fix_relevance_final import longest_cjk_run       # noqa: E402

qs = json.loads((ROOT / "data" / "questions.json").read_text(encoding="utf-8"))["questions"]
web = [q for q in qs if q.get("explanationSrc") == "web"]
print("=" * 78)
print(f"联网核查依据复核：{len(web)} 道")
print("=" * 78)
if not web:
    print("  （尚无联网依据）")
    raise SystemExit(0)

# A. 出处完整性
no_ref = [q["id"] for q in web if not (q.get("explanationRef") or "").strip()]
bad_url = [q["id"] for q in web if not re.match(r"^https?://", q.get("webSourceUrl") or "")]
print(f"A. 缺出处        : {len(no_ref)}  {no_ref[:5]}")
print(f"   非法 URL      : {len(bad_url)}  {bad_url[:5]}")

# B. 相关性
# 注意：联网来源**允许**用「话题重合」而非「字面重合」通过 ——
# 法规/大纲是规范表述，题干常是它的口语化改写，逐字重合天然就短
# （如 q-0107「与我国边界没有接壤的国家」↔ 政府网《版图》列出陆地邻国后指出泰国不接壤）。
# 所以这里分别统计「字面重合达标」与「靠话题重合通过」，后者不是缺陷，但要可见。
runs = []
for q in web:
    r = (q.get("explanationParts") or {}).get("reason", "")
    stem = re.sub(r"[_＿]{2,}", " ", q["stem"])
    terms = [t for t in G.keywords(stem) if len(t) >= 2 and t not in G.STOP]
    hit = sum(1 for t in terms if t in r)
    runs.append((longest_cjk_run(stem, r), hit, q))
low_run = [(run, hit, q) for run, hit, q in runs if run < 4]
bad_overlap = [(run, hit, q) for run, hit, q in low_run if hit < 2]
print(f"B. 字面重合<4    : {len(low_run)} 道（其中靠话题重合通过 {len(low_run)-len(bad_overlap)} 道）")
print(f"   **话题也不达标**: {len(bad_overlap)}  {[q['id'] for _,_,q in bad_overlap][:5]}")

# C. 是否只是复述答案
echo = []
for q in web:
    r = re.sub(r"[^\u4e00-\u9fff]", "", (q.get("explanationParts") or {}).get("reason", ""))
    stem = re.sub(r"[^\u4e00-\u9fff]", "", re.sub(r"[_＿]{2,}", "", q["stem"]))
    a = q["answer"]
    ans = ""
    opts = q.get("options") or []
    if isinstance(a, str) and a in "ABCDEFGH":
        i = "ABCDEFGH".index(a)
        ans = re.sub(r"[^\u4e00-\u9fff]", "", opts[i]) if i < len(opts) else ""
    elif isinstance(a, list):
        # 多选答案可能是字母数组，也可能是文本数组 —— 两种都要能处理
        for x in a:
            if isinstance(x, str) and x in "ABCDEFGH":
                k = "ABCDEFGH".index(x)
                if k < len(opts):
                    ans += re.sub(r"[^\u4e00-\u9fff]", "", opts[k])
            else:
                ans += re.sub(r"[^\u4e00-\u9fff]", "", str(x))
    else:
        ans = re.sub(r"[^\u4e00-\u9fff]", "", str(a))
    # 依据里去掉与题干/答案重复的字后，还剩多少
    rest = set(r) - set(stem) - set(ans)
    if len(rest) < 6:
        echo.append(q["id"])
print(f"C. 近似复述答案  : {len(echo)}  {echo[:5]}")

# D. 同一依据句被用到结论不同的题上
by_reason: dict[str, list] = defaultdict(list)
for q in web:
    key = G.squeeze((q.get("explanationParts") or {}).get("reason", ""))[:40]
    if key:
        by_reason[key].append(q)
shared = {k: v for k, v in by_reason.items() if len(v) > 1}
print(f"D. 同一依据复用  : {len(shared)} 组")
for k, v in list(shared.items())[:5]:
    print(f"     {len(v)} 道: {'/'.join(x['id'] for x in v)}  «{k[:36]}…»")

# E. disputed
disp = [q for q in qs if q.get("answerDisputedBySource")]
print()
print(f"E. 来源与答案有出入（需人工对照原卷）: {len(disp)} 道")
for q in disp:
    note = (q.get("explanationParts") or {}).get("note", "")
    m = re.search(r"建议对照原卷核实[：:]\s*(.*)$", note)
    print(f"   [{q['id']}] {q['stem'][:44]}")
    print(f"        答案: {json.dumps(q['answer'], ensure_ascii=False)[:40]}")
    print(f"        {(m.group(1) if m else note)[:110]}")

# 汇总
print()
print("=" * 78)
ok_all = not no_ref and not bad_url and not bad_overlap
print(f"结论: 出处完整={'是' if not no_ref and not bad_url else '否'}，"
      f"相关性达标={'是' if not bad_overlap else '否'}")
print(f"  依据来源分布: {dict(Counter(q.get('explanationRef','').split('（')[0][:18] for q in web).most_common(6))}")
