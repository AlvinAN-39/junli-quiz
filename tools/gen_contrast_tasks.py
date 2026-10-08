#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_contrast_tasks.py — 为「干扰项具体对比」生成待办清单（供逐个生成/补写）
============================================================================

背景：`gen_distractor_contrast.py` 用规则法只覆盖了 31/1720 条（宁缺勿造），
剩下约 1689 条需要写「你把这个和什么搞混了」。本脚本把这些待办导出成
**自带上下文的任务清单**，便于「逐个交给小模型生成 → 人工复核」，而不是
让复核者自己去翻 700 KB 教材。

每条任务自带：
  * 题号 / 题型 / 题干 / 全部选项 / 正确答案
  * 该干扰项**当前**的说明文字（将被替换）
  * 教材中与「题干 + 该选项」最相关的若干段落（最多 4 段、每段 220 字）

输出：`qa/contrast-tasks/task-XXXX.json`（每条一个文件，便于断点续跑）
      `qa/contrast-tasks/index.json`（总数与文件索引）

用法：
    python tools/gen_contrast_tasks.py            # 只导出「模板话术」的条目
    python tools/gen_contrast_tasks.py --all      # 导出全部干扰项（含已具体的）
    python tools/gen_contrast_tasks.py --limit 50 # 先只导 50 条试试
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
CORPUS = ROOT / "build" / "text" / "1-textbook.txt"
OUTDIR = ROOT / "qa" / "contrast-tasks"

LETTERS = "ABCDEFGH"
# 需要重写的模板话术（与 gen_distractor_contrast.py 保持同一套）
TEMPLATES = {
    "该表述与正确选项相近，容易混淆，注意区分题干限定的范围。",
    "属于相关但错误的选项，注意题干限定的范围。",
    "该说法在本软件核对过的教材语料中查不到，属于为本题设置的干扰项。",
    "该说法教材中未出现或不属本考点的规范表述。",
    "该说法教材中有，但指向的不是本题所问的考点。",
    "它属于该考点包含的内容，但本题问的是“不属于”的那一项。",
}


def norm(text: str) -> str:
    t = "".join(ch for ch in (text or "") if ch == "\n" or ch >= " ")
    t = t.replace("\u3000", " ").replace("（", "(").replace("）", ")")
    t = t.replace("，", ",").replace("。", ".").replace("、", ",")
    t = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", t)
    return re.sub(r"\s+", "", t)


def main() -> int:
    include_all = "--all" in sys.argv
    limit = 0
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except Exception:
            limit = 0

    qs = json.loads(DATA.read_bytes().decode("utf-8"))["questions"]
    raw = CORPUS.read_bytes().decode("utf-8", errors="replace")
    paras = [norm(p) for p in re.split(r"[\n]", raw) if len(norm(p)) >= 12]

    tasks = []
    for q in qs:
        if q.get("type") not in ("single", "multi"):
            continue
        opts = q.get("options") or []
        if not opts:
            continue
        a = q.get("answer")
        ans = list(a) if isinstance(a, list) else [str(a)]
        ans = [x for x in ans if x in LETTERS]
        why = q.get("distractorWhy")
        if not isinstance(why, dict):
            continue
        ans_text = [opts[LETTERS.index(x)] for x in ans if LETTERS.index(x) < len(opts)]
        for i, o in enumerate(opts):
            L = LETTERS[i]
            if L in ans or not o.strip() or L not in why:
                continue
            cur = why[L]
            if not include_all and cur not in TEMPLATES:
                continue
            # 相关段：题干关键词或该选项命中的段（取最多 4 段）
            key = re.sub(r"(制度|兵役制|主义|思想|武器|系统|政策|战略)$", "", o) or o
            stem_kw = [w for w in re.findall(r"[\u4e00-\u9fff]{2,6}", q["stem"]) if len(w) >= 3][:4]
            picked = []
            for p in paras:
                if (o in p or key in p) or any(k in p for k in stem_kw):
                    picked.append(p[:220])
                if len(picked) >= 4:
                    break
            tasks.append({
                "id": q["id"], "type": q["type"], "key": L,
                "stem": q["stem"], "options": opts, "answer": ans_text,
                "chosen": o, "current": cur, "corpus": picked,
            })

    if limit:
        tasks = tasks[:limit]

    OUTDIR.mkdir(parents=True, exist_ok=True)
    for old in OUTDIR.glob("task-*.json"):
        old.unlink()
    for old in OUTDIR.glob("shard-*.json"):
        old.unlink()
    for i, t in enumerate(tasks):
        (OUTDIR / ("task-%04d.json" % i)).write_text(
            json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")

    # 分片：供并行处理使用（每片 SHARD 条，避免上下文被 1689 条撑爆）
    SHARD = 100
    shards = []
    for i in range(0, len(tasks), SHARD):
        chunk = tasks[i:i + SHARD]
        p = OUTDIR / ("shard-%02d.json" % (i // SHARD + 1))
        p.write_text(json.dumps({
            "shard": i // SHARD + 1,
            "range": [i, i + len(chunk) - 1],
            "count": len(chunk),
            "items": chunk,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        shards.append(p.name)

    (OUTDIR / "index.json").write_text(json.dumps({
        "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "count": len(tasks),
        "files": ["task-%04d.json" % i for i in range(len(tasks))],
        "shards": shards,
        "shardSize": SHARD,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print("导出待办任务：%d 条 → %s" % (len(tasks), OUTDIR))
    print("分片：%d 个（每片 ≤%d 条）%s" % (len(shards), SHARD, shards))
    print("每条含题干/选项/答案/当前说明/教材相关段落（最多 4 段）")
    if tasks:
        print("\n=== 样例 ===")
        t = tasks[0]
        print(" %s %s 你选=%s" % (t["id"], t["stem"][:40], t["chosen"]))
        print(" 当前说明：%s" % t["current"][:60])
        print(" 教材段：%s" % (t["corpus"][0][:90] if t["corpus"] else "（无）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
