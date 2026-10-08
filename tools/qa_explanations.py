#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qa_explanations.py — 解析质量量化验收（独立于生成器）
====================================================

对 1171 道题逐题检查「解析是否支持其答案」，产出一张可复现的质量表：

  1. 覆盖率：多少题有非空解析、多少题有教材依据
  2. 支持度：解析中是否出现该题的正确答案（整串或连续实词片段）
  3. 冲突检查：解析是否恰好支持了一个**错误**选项而没有支持正确项
  4. 长度检查：过短（<8 字）或过长（>400 字）
  5. 否定型题单独统计（这类题的判据不同）

输出 qa/explanation-audit.json，并在 stdout 打印结论。
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
import gen_explanations as G  # noqa: E402
from answer_text import answer_text  # noqa: E402  单一真相：答案读取只有一处实现
from answer_text import letters_of   # noqa: E402  答案字母同样只有一处实现

BANK = ROOT / "data" / "questions.json"
OUT = ROOT / "qa" / "explanation-audit.json"

LETTERS = "ABCDEFGH"


def answer_text(q) -> str:
    """已移至 `tools/answer_text.py`（单一真相）。

    保留此转发是为了不破坏可能的外部调用；**新代码请直接用 answer_text 模块**。
    历史上这里与另外 5 个脚本各自实现了一遍，且都假定 single 是字符串，
    结果 T18 修正答案引入列表型单选后 6 处同时崩 —— 这正是重复实现的代价。
    """
    from answer_text import answer_text as _impl
    return _impl(q)


def main() -> int:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = bank["questions"]

    stats: Counter[str] = Counter()
    problems: dict[str, list[dict]] = {
        "noExplanation": [], "tooShort": [], "tooLong": [],
        "notSupporting": [], "supportsWrongOption": [],
    }
    by_src: Counter[str] = Counter()
    by_type_support: dict[str, list[int]] = {}

    for q in qs:
        exp = (q.get("explanation") or "").strip()
        src = q.get("explanationSrc") or "none"
        by_src[src] += 1
        t = q["type"]
        by_type_support.setdefault(t, [0, 0])      # [有解析, 支持答案]

        if not exp:
            problems["noExplanation"].append({"id": q["id"], "type": t})
            continue
        by_type_support[t][0] += 1
        if len(exp) < 8:
            problems["tooShort"].append({"id": q["id"], "len": len(exp), "exp": exp})
        if len(exp) > 400:
            problems["tooLong"].append({"id": q["id"], "len": len(exp)})

        ans = answer_text(q)
        if not ans or t in ("short",):
            by_type_support[t][1] += 1             # 简答题看参考答案本身，另算
            continue

        # 支持度：答案整串出现，或与解析的连续实词片段重合 ≥ 0.4，
        # 或解析首行明确声明的答案字母与答案字段完全一致。
        #
        # 为什么需要第三条：`answer_text()` 对多选题是把各选项文字**连成一串**
        # （如「太空侦察系统地面侦察系统空中侦察系统水面（水下）侦察系统」），
        # 而解析按人读习惯写成「A、B、C、D（太空、地面、空中、水面（水下）侦察系统）」，
        # 整串自然不出现 —— 实测 q-0329 / q-0548 / q-0803 因此被误报为「解析不支持答案」。
        # 判定要求「字母集合完全一致」，不做子集放宽，避免把真问题掩盖成通过。
        #
        # 【2026-10-08 修正】旧实现只截取「字母 + 顿号/逗号/斜杠」直连序列，遇到
        # 「A、私有制；C、阶级」这种字母间夹选项文字与分号的写法，只拿到第一个字母，
        # 造成 15 道全选型多选题被误报。改为**逐个选项字母**检查「字母 + 分隔符」是否出现，
        # 与 verify_app.py / audit_selfconsistent.py 的口径保持一致。
        def declared_answer_letters(txt: str) -> list:
            m = re.search(r"正确答案[:：]\s*([^。\n]*)", txt)
            if not m:
                return []
            opts = q.get("options") or []
            return [chr(65 + i) for i in range(len(opts))
                    if re.search(re.escape(chr(65 + i)) + r"\s*[、,，/；;（(]", m.group(1))
                    or m.group(1).rstrip().endswith(chr(65 + i))]

        ans_letters = letters_of(q)
        letters_ok = bool(ans_letters) and declared_answer_letters(exp) == sorted(ans_letters)
        if G.squeeze(ans) in G.squeeze(exp) or G.span_fit(ans, exp) >= 0.4 or letters_ok:
            by_type_support[t][1] += 1
            stats["supported"] += 1
        else:
            stats["notSupported"] += 1
            problems["notSupporting"].append({
                "id": q["id"], "type": t, "answer": ans[:40],
                "src": src, "exp": exp[:120],
            })
            # 冲突：解析强烈支持某个**错误**选项，却不支持正确项
            if t == "single":
                ai = LETTERS.index(q["answer"])
                for i, o in enumerate(q["options"]):
                    if i == ai or not o:
                        continue
                    if G.span_fit(o, exp) >= 0.7 and len(G.squeeze(o)) >= 3:
                        problems["supportsWrongOption"].append({
                            "id": q["id"], "answer": ans, "wronglySupported": o,
                            "exp": exp[:120],
                        })
                        break

    # ---- 检查：排版噪声（只算空格/制表符；**换行是结构化分行，不是噪声**）----
    for q in qs:
        exp = q.get("explanation") or ""
        parts = q.get("explanationParts") or {}
        blob = exp + "\n" + "\n".join(str(v) for v in parts.values())
        if re.search(r"[\u4e00-\u9fff][ \t\u3000]+[\u4e00-\u9fff]", blob):
            problems.setdefault("spacingNoise", []).append({"id": q["id"], "exp": blob[:100]})
        if re.search(r"(《[^》]{2,30}》)\1", blob):
            problems.setdefault("dupTitle", []).append({"id": q["id"], "exp": blob[:100]})
        # 空标签：有 label 无内容（结构化渲染不应出现）
        if parts and not any(str(v).strip() for v in parts.values()):
            problems.setdefault("emptyParts", []).append({"id": q["id"]})

    report = {
        "total": len(qs),
        "byExplanationSrc": dict(by_src),
        "coverage": {
            "withExplanation": sum(1 for q in qs if (q.get("explanation") or "").strip()),
            "withTextbookGrounding": by_src.get("textbook", 0) + by_src.get("manual", 0),
        },
        "perType": {t: {"hasExplanation": v[0], "supportsAnswer": v[1]}
                    for t, v in by_type_support.items()},
        "problems": {k: v[:60] for k, v in problems.items()},
        "problemCounts": {k: len(v) for k, v in problems.items()},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print("=" * 76)
    print("解析质量验收")
    print("=" * 76)
    print(f"总题数            : {len(qs)}")
    print(f"有解析            : {report['coverage']['withExplanation']} "
          f"({report['coverage']['withExplanation']/len(qs):.1%})")
    print(f"有教材/人工依据   : {report['coverage']['withTextbookGrounding']} "
          f"({report['coverage']['withTextbookGrounding']/len(qs):.1%})")
    print(f"依据分布          : {dict(by_src)}")
    print()
    print("各题型支持度（解析中确实提到正确答案）:")
    for t, v in sorted(by_type_support.items()):
        pct = v[1] / max(1, v[0])
        print(f"  {t:6} {v[1]:>4}/{v[0]:<4} = {pct:6.1%}")
    print()
    print("问题计数:", report["problemCounts"])
    if problems["supportsWrongOption"]:
        print("\n[!] 解析支持了错误选项（优先修）:")
        for p in problems["supportsWrongOption"][:10]:
            print(f"  {p['id']} 正确={p['answer']} 却被支持={p['wronglySupported']}")
            print(f"      {p['exp']}")
    if problems["notSupporting"]:
        print("\n[!] 解析未提到正确答案（前 10）:")
        for p in problems["notSupporting"][:10]:
            print(f"  {p['id']} [{p['type']}/{p['src']}] 答案={p['answer']}")
            print(f"      {p['exp']}")
    print(f"\n输出: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
