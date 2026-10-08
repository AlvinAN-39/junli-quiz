#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_shard_quality.py — 分片阶段的质量预检（与 qa_explanations.py 同一口径）。

为什么要它：合并入库前先量一遍，避免把不合格解析灌进题库再回滚。
判据与 tools/qa_explanations.py 一致：
  · 解析非空、长度 8~400 字
  · 支持度：答案整串出现 / 连续实词重合 ≥0.4 / 首行「正确答案：」字母集合与答案字段完全一致
  · 排版噪声：中日韩汉字之间夹空格、书名号重复
  · 干扰项说明覆盖率（单选/多选）

用法：python tools/probe_shard_quality.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import gen_explanations as G  # noqa: E402
from answer_text import answer_text, letters_of  # noqa: E402

# 分片原件在扩容轮结束后归档到 qa/shard-audit-2026-10-08/（中间目录已按纪律清理）
SPLIT = ROOT / "qa" / "shard-audit-2026-10-08"


def declared_letters(txt: str) -> list:
    m = re.search(r"正确答案[:：]\s*([A-H](?:\s*[、,，/]\s*[A-H])*)", txt)
    return sorted(re.findall(r"[A-H]", m.group(1))) if m else []


def main() -> int:
    total = 0
    bad_exp: list[str] = []
    not_supported: list[str] = []
    short_exp: list[str] = []
    long_exp: list[str] = []
    noise: list[str] = []
    why_missing: list[str] = []
    src_dist: dict[str, int] = {}
    for p in sorted(SPLIT.glob("shard-*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data.get("items", [])
        done = [x for x in items if str(x.get("explanation", "")).strip()]
        print(f"\n{p.name}: {len(items)} 题，已写解析 {len(done)}")
        for it in done:
            total += 1
            tag = f"{p.name}:{it.get('v2_id') or it.get('origin_id')}"
            exp = str(it["explanation"]).strip()
            src = str(it.get("explanationSrc", ""))
            src_dist[src] = src_dist.get(src, 0) + 1
            if not exp:
                bad_exp.append(tag)
                continue
            if len(exp) < 8:
                short_exp.append(tag)
            if len(exp) > 400:
                long_exp.append(tag)
            parts = it.get("explanationParts") or {}
            blob = exp + "\n" + "\n".join(str(v) for v in parts.values())
            if re.search(r"[\u4e00-\u9fff][ \t\u3000]+[\u4e00-\u9fff]", blob):
                noise.append(tag)
            if re.search(r"(《[^》]{2,30}》)\1", blob):
                noise.append(tag)

            qtype = {"single": "single", "multi": "multi"}.get(it.get("type", ""))
            if qtype:
                q = {"type": qtype, "answer": it["answer"], "options": it.get("options", [])}
                ans = answer_text(q)
                letters_ok = bool(letters_of(q)) and declared_letters(exp) == sorted(letters_of(q))
                if not (G.squeeze(ans) in G.squeeze(exp) or G.span_fit(ans, exp) >= 0.4 or letters_ok):
                    not_supported.append(f"{tag} | ans={str(it['answer'])[:20]} | {exp[:60]}")
                why = it.get("distractorWhy") or {}
                answers = set(it["answer"] if isinstance(it["answer"], list) else [it["answer"]])
                wrong = [chr(65 + i) for i in range(len(q["options"])) if chr(65 + i) not in answers]
                if wrong and not any(str(why.get(k, "")).strip() for k in wrong):
                    why_missing.append(tag)

    print("\n" + "=" * 60)
    print(f"已写解析合计 {total} 题")
    print(f"依据分布 {src_dist}")
    print(f"解析为空 {len(bad_exp)}；过短 {len(short_exp)}；过长 {len(long_exp)}")
    print(f"不支持答案 {len(not_supported)}；排版噪声 {len(noise)}；干扰项说明缺失 {len(why_missing)}")
    for name, lst in (("不支持", not_supported), ("过短", short_exp), ("噪声", noise), ("干扰项缺失", why_missing)):
        for x in lst[:6]:
            print(f"   {name}: {x}")
    bad = len(bad_exp) + len(short_exp) + len(long_exp) + len(not_supported) + len(noise) + len(why_missing)
    print(f"问题合计 {bad}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
