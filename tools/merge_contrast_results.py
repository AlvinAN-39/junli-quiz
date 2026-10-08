#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_contrast_results.py — 汇总「错题具体对比说明」并写回题库
================================================================

输入：`qa/contrast-tasks/result-NN.json`（子代理产出）
      `qa/contrast-tasks/shard-NN.json`（任务分片，用于逐条核对 id/key）
输出：写回 `data/questions.json` 的 `distractorWhy`（只改**干扰项**条目）
      `qa/contrast-merge-report.json`（统计与异常清单）

质量门（逐条校验，不合格**不入库**并列出原因）：
  1. id 必须存在于题库，且该题确有该选项（distractorWhy 里有这个 key）；
  2. key 必须是**干扰项**（不能覆盖正确选项）；
  3. 说明文字长度 15~80 字；
  4. 不含空话模板（「相近」「容易混淆」「注意区分题干限定的范围」「干扰项」等）；
  5. 不含英文字母、不含 Markdown 标记、不以序号开头；
  6. 同一题同一 key 只取一条（重复以分片顺序先到者为准）。

安全设计：写盘前先按 id/key 建立索引并全部校验通过才写；写盘后回读并复核计数。

用法：
    python tools/merge_contrast_results.py --check   # 只统计与校验，不写盘
    python tools/merge_contrast_results.py
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
DATA = ROOT / "data" / "questions.json"
TASKDIR = ROOT / "qa" / "contrast-tasks"
REPORT = ROOT / "qa" / "contrast-merge-report.json"
# 生成脚本可能仍在写结果文件，跳过它们自身的中间产物（以 _ 开头的文件不会被 glob 命中）

BANNED = ["相近", "容易混淆", "注意区分题干限定的范围", "干扰项", "与题目不符", "本题所问的考点"]
# 只拒绝**真正的英文单词**（≥2 个连续字母，如 C4ISR / ISR），
# 允许引用选项字母（「用户选了D项」「选项A与正确答案B」）——这类引用是必要的，
# 第一版规则禁用一切字母，误拒了 16 条合格内容。
RE_BAD = re.compile(r"[A-Za-z]{2,}|\*\*|^#|^\d+[.、)]|`")


def main() -> int:
    check_only = "--check" in sys.argv
    bank = json.loads(DATA.read_bytes().decode("utf-8"))
    by_id = {q["id"]: q for q in bank["questions"]}

    results = sorted(TASKDIR.glob("result-*.json"))
    print("发现结果文件：%d 个" % len(results))

    accepted, rejected, dup = [], [], []
    seen = set()
    for f in results:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            rejected.append({"file": f.name, "reason": "JSON 解析失败：%s" % e})
            continue
        for it in d.get("items", []):
            qid, key, text = it.get("id"), it.get("key"), str(it.get("text") or "").strip()
            tag = "%s/%s" % (qid, key)
            q = by_id.get(qid)
            if q is None or not text:
                rejected.append({"tag": tag, "file": f.name, "reason": "题目不存在或文本为空"})
                continue
            why = q.get("distractorWhy") or {}
            if key not in why:
                rejected.append({"tag": tag, "file": f.name, "reason": "该选项不是本题的干扰项"})
                continue
            a = q.get("answer")
            ans = a if isinstance(a, list) else [str(a)]
            if key in ans:
                rejected.append({"tag": tag, "file": f.name, "reason": "key 命中正确选项（拒绝覆盖）"})
                continue
            if tag in seen:
                dup.append({"tag": tag, "file": f.name})
                continue
            if not (15 <= len(text) <= 80):
                rejected.append({"tag": tag, "file": f.name, "reason": "长度 %d 越界" % len(text)})
                continue
            hit = [w for w in BANNED if w in text]
            if hit:
                rejected.append({"tag": tag, "file": f.name, "reason": "含空话词 %s" % hit})
                continue
            if RE_BAD.search(text):
                rejected.append({"tag": tag, "file": f.name, "reason": "含英文/标点/序号等异常字符"})
                continue
            seen.add(tag)
            accepted.append({"tag": tag, "id": qid, "key": key, "text": text, "file": f.name})

    print("校验通过：%d 条" % len(accepted))
    print("拒绝：%d 条；重复丢弃：%d 条" % (len(rejected), len(dup)))
    for r in rejected[:10]:
        print("   [拒] %s" % json.dumps(r, ensure_ascii=False)[:120])

    print("\n=== 抽样（前 5 条）===")
    for a in accepted[:5]:
        print("  %-12s %s" % (a["tag"], a["text"][:80]))

    if check_only:
        print("\n--check 模式：未写盘。")
        return 0
    if not accepted:
        print("\n没有可写入的条目，未写盘。")
        return 0

    # 写盘：只改对应题的对应干扰项
    for a in accepted:
        q = by_id[a["id"]]
        q["distractorWhy"][a["key"]] = a["text"]
    DATA.write_bytes((json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
                     .replace("\n", "\r\n").encode("utf-8"))

    # 回读验证
    back = json.loads(DATA.read_bytes().decode("utf-8"))
    bq = {q["id"]: q for q in back["questions"]}
    miss = [a["tag"] for a in accepted if (bq[a["id"]].get("distractorWhy") or {}).get(a["key"]) != a["text"]]
    print("\n回读校验：未生效 %d 条" % len(miss))
    print("题数：%d" % len(back["questions"]))
    if miss:
        print("[FAIL] %r" % miss[:5], file=sys.stderr)
        return 3

    REPORT.write_text(json.dumps({
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "files": [f.name for f in results],
        "accepted": len(accepted), "rejected": rejected, "duplicates": dup,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("报告 → %s" % REPORT)
    print("[PASS] 已写入题库并回读确认")
    return 0


if __name__ == "__main__":
    sys.exit(main())
