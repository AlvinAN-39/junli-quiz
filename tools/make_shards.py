#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_shards.py — 为本轮题目入库生成「子代理写入口」分片文件。

设计约束（AGENTS.md 第 4 条：子代理只回简报、明细写文件）
------------------------------------------------------
* 每个分片是一个独立 JSON 文件，**一个子代理只写自己那一个文件**，互不重叠。
* 分片里只放「不可推导的原始信息」：题干、选项、答案、来源、章/节归属、小节名。
* 解析相关字段由子代理补齐，字段名与数据契约（docs/02-data-contract.md）一致。

**回填保护**：分片一旦被解析子代理写过（含 explanation 字段），再跑本脚本会先备份到
`split/_backup-<时间戳>/`，重写后用 `backfill()` 把解析字段按 id/题干匹配回来 ——
即使因补小节名需要重新分片，子代理的工作也不会丢。

产出（`work/split/`，`work/` 由脚本自动创建；扩容轮的产物已归档到 `qa/shard-audit-2026-10-08/`）
    shard-01..04.json   第二版独有题（321 题切 4 片，含 subsection 小节名）
    shard-11nian.json   第一版 2011 年真题（40 题：判断 20 + 选择 20）
    hard-review.json    既有 1171 题的难度复核输入（只读用）

用法：python tools/make_shards.py
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
WORK.mkdir(parents=True, exist_ok=True)
SPLIT = WORK / "split"
OUTLINE = ROOT.parent / "军理课资料" / "military_theory" / "outline.json"

CH_NAME = {
    "MT_CH01": "第一章中国国防",
    "MT_CH02": "第二章国家安全",
    "MT_CH03": "第三章军事思想",
    "MT_CH04": "第四章现代战争",
    "MT_CH05": "第五章信息化装备",
}
SEC_NAME = {"single": "单选题", "multi": "不定项选择题", "short_answer": "简答题", "essay": "简答题"}

BRIEF = """你是「军理刷题」项目的题目解析生成子代理。任务：为分片里的每道题补齐解析相关字段。

【依据优先级（严格按顺序，不得跳级）】
1. `build/text/1-textbook.txt`（教材抽取文本，716 KB，用 grep 定位后 read 取段，不要整篇读）
2. 第一版题库语料：自行准备的资料目录下的 txt（900题库、已提取真题等）
3. 本轮真题语料：`build/text/2-past.txt`、`3-mock.txt`
4. 以上都没有 → 允许联网检索（web_search / web_fetch），只用能核对到的权威表述，并把 URL 填进 explanationRef
5. 仍然找不到 → `explanationSrc` 写 `"template"`，解析里如实写「未收录」（**绝不编造出处或原文**）

【每题必须补齐的字段（字段名/取值不得改）】
- explanation        string  解析全文，多行用 \\n 分隔，首行固定「正确答案：X、选项文字」
- explanationParts   object  {answer, reason, ref, note}（reason=为什么对，ref=出处，note=补充/易错点，可为空串）
- explanationSrc     string  textbook | bank | web | manual | template（五选一）
- explanationRef     string  出处定位，如「教材《普通高校军事课教程》·中国国防」；web 时填 URL；template 时空串
- keyConcept         string  考点短名词短语（≤12 字）
- keywords           array   3~6 条用于搜索复现解析的关键词/短句（必须是语料里出现过的表述）
- distractorWhy      object  {选项字母: 该错误选项为什么错}，**只写错误选项**；要求具体到「它错在哪/与哪个概念混淆」
                             （例：「你把“募兵制”和“征兵制”搞混了：“募兵制”是宋朝的」），禁止「表述相近容易混淆」这类空话
- isHard             boolean 沿用输入里的原值，不要改

【质量红线】
- 答案字段（answer）**一个字都不许改**；若你确信答案有误，只在 note 里写「存疑：…」并在简报里列出题号。
- 给出的依据必须能在你引用的语料里找到原句；找不到就降级，不要编。
- 多选答案按升序字母数组，单选是单个大写字母。

【写盘规则】
- 只允许写你自己的那一个分片文件（路径见任务说明），不得触碰 `data/questions.json`、其他分片、任何 `tools/` 脚本。
- 输出格式：与输入同构的 JSON，`items` 数组里每题在原有键基础上**追加**上述字段；不要删改原有键。
- 写完用 python -c 读回校验 JSON 可解析，再回报。

【简报格式（只回这个，不要贴明细、不要贴表格）】
【简报】分片=<文件名> 处理 N 题；依据分布 textbook=a/bank=b/web=c/template=d；存疑=[题号...]；输出=<绝对路径>
"""


def load_outline_names() -> dict[str, dict[str, str]]:
    """第二版 outline.json → {小节 id: {name, section_name, chapter_name}}。"""
    o = json.loads(OUTLINE.read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    for ch in o.get("chapters", []):
        ch_id = ch.get("id", "")
        ch_name = CH_NAME.get(ch_id, ch.get("name", ""))
        for sec in ch.get("sections", []):
            sec_name = sec.get("name", "")
            for u in sec.get("units", []):
                if not isinstance(u, dict):
                    continue
                uid = u.get("id")
                if not uid:
                    continue
                out[uid] = {"name": u.get("name") or sec_name,
                            "section_name": sec_name, "chapter_name": ch_name}
    return out


def backfill(items: list[dict], backup_dir: Path | None) -> int:
    """把备份分片里已生成的解析字段按题干回填到重写后的 items。"""
    if not backup_dir or not backup_dir.exists():
        return 0
    parsed: dict[str, dict] = {}
    for f in backup_dir.glob("*.json"):
        try:
            for it in json.loads(f.read_text(encoding="utf-8")).get("items", []):
                if it.get("explanation"):
                    parsed[str(it.get("stem"))] = it
        except Exception as e:
            print(f"  ! 备份读取失败 {f.name}: {e}")
    n = 0
    for it in items:
        src = parsed.get(str(it.get("stem")))
        if not src:
            continue
        for k, v in src.items():
            if k in ("chapter", "section", "sub", "subsection", "chapter_name", "section_name"):
                continue          # 归属字段以本次重算为准
            it[k] = v
        n += 1
    return n


def main() -> int:
    new = json.loads((WORK / "new-from-v2.json").read_text(encoding="utf-8"))["items"]
    hard = json.loads((WORK / "v1-11nian.json").read_text(encoding="utf-8"))
    SPLIT.mkdir(parents=True, exist_ok=True)

    # --- 备份已生成解析的分片（防重跑丢工作）---
    has_parsed = any("explanation" in it for f in SPLIT.glob("shard-0*.json")
                     for it in json.loads(f.read_text(encoding="utf-8")).get("items", []))
    backup_dir = None
    if has_parsed:
        backup_dir = SPLIT / f"_backup-{time.strftime('%Y%m%d-%H%M%S')}"
        backup_dir.mkdir()
        for f in SPLIT.glob("shard-*.json"):
            shutil.copy2(f, backup_dir / f.name)
        print(f"已备份含解析的分片 → {backup_dir}")

    names = load_outline_names()
    print(f"第二版大纲小节名 {len(names)} 条")

    # ---- 第二版独有题：补章名/section/小节名，按「章 → 原序」稳定排序后切 4 片 ----
    for i, x in enumerate(new):
        x["_ord"] = i
        x["chapter"] = CH_NAME.get(x.get("chapter"), "未分类")
        x["section"] = SEC_NAME.get(x["type"], "单选题")
        info = names.get(x.get("sub"), {})
        x["subsection"] = info.get("name", "")
        x["section_name"] = info.get("section_name", "")
        if x["type"] == "multi":
            a = str(x["answer"])
            x["answer"] = sorted(set(a)) if len(a) > 1 else a
        elif x["type"] == "single":
            x["answer"] = str(x["answer"]).strip().upper()
    new.sort(key=lambda x: (x["chapter"], x["_ord"]))

    per = (len(new) + 3) // 4
    manifest = []
    for k in range(4):
        part = new[k * per:(k + 1) * per]
        if not part:
            continue
        name = f"shard-{k + 1:02d}.json"
        reused = backfill(part, backup_dir)
        payload = {"brief": BRIEF, "origin": "第二版 source（military_theory）", "items": part}
        (SPLIT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        manifest.append({"file": name, "count": len(part), "backfilled": reused,
                         "types": {t: sum(1 for x in part if x["type"] == t) for t in
                                   ("single", "multi", "short_answer", "essay")},
                         "chapters": sorted({x["chapter"] for x in part})})
        print(f"{name}: {len(part)} 题，回填解析 {reused} 题 {manifest[-1]['types']}")

    # ---- 第一版 11 年真题 ----
    items11 = []
    for j in hard["judge"]:
        items11.append({
            "origin_id": f"v1-11nian-J{j['n']}", "src": "real", "type": "judge",
            "stem": j["stem"], "answer": j["answer"], "options": [],
            "isReal": True, "isHard": None, "chapter": "第一章中国国防", "section": "判断题",
            "subsection": "中国国防历史", "section_name": "国防概述",
            "originNote": f"第一版题库《11年》判断题第 {j['n']} 题（原卷有答案）" + (f"；原卷备注：{j['note']}" if j["note"] else ""),
        })
    for c in hard["choice"]:
        items11.append({
            "origin_id": f"v1-11nian-C{c['n']}", "src": "real", "type": "single",
            "stem": c["stem"], "answer": c["answer"], "options": c["options"],
            "isReal": True, "isHard": None, "chapter": "第一章中国国防", "section": "单选题",
            "subsection": "中国国防历史", "section_name": "国防概述",
            "originNote": f"第一版题库《11年》选择题第 {c['n']} 题（原卷有答案）",
            "optionCountNote": c["note"],
        })
    reused11 = backfill(items11, backup_dir)
    (SPLIT / "shard-11nian.json").write_text(
        json.dumps({"brief": BRIEF, "origin": "第一版题库 整理前/真题/已提取真题/11年.txt",
                    "items": items11}, ensure_ascii=False, indent=1), encoding="utf-8")
    manifest.append({"file": "shard-11nian.json", "count": len(items11), "backfilled": reused11,
                     "types": {"judge": len(hard["judge"]), "single": len(hard["choice"])},
                     "chapters": ["第一章中国国防"]})
    print(f"shard-11nian.json: {len(items11)} 题（判断 {len(hard['judge'])} / 选择 {len(hard['choice'])}），回填解析 {reused11} 题")

    # ---- 既有题难度复核输入（已由子代理产出 hard-flags.json，此处仅保留只读输入）----
    if not (SPLIT / "hard-review.json").exists():
        bank = json.loads((ROOT / "data" / "questions.json").read_text(encoding="utf-8"))["questions"]
        review = [{"id": q["id"], "type": q["type"], "stem": q["stem"], "answer": q["answer"],
                   "keyConcept": q.get("keyConcept", ""),
                   "reason": (q.get("explanationParts") or {}).get("reason", "")[:120]} for q in bank]
        (SPLIT / "hard-review.json").write_text(json.dumps({"items": review}, ensure_ascii=False, indent=1),
                                                encoding="utf-8")
        print(f"hard-review.json: {len(review)} 题（只读输入）")

    (SPLIT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→", SPLIT, ("（备份留在 " + backup_dir.name + "）") if backup_dir else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
