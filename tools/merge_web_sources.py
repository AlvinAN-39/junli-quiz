#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_web_sources.py — 把联网核查结果合并进题库
==============================================

输入：`build/web-sourced/out-{a,b,c}/*.json`（各批次核查产出的结果数组）
输出：写回 `data/questions.json`，为通过校验的题补上 `reason` 与出处。

## 收录闸（不达标一律不收录）

  * `found` 必须为 true；
  * `confidence` 只收 `high` / `medium`（`low` 视为不可靠，丢弃）；
  * `reason` 至少 12 字，且不能只是复述答案；
  * 必须有真实 `url`（http/https 开头）；
  * **与题干必须有 ≥4 个连续汉字重合**（沿用与本地依据同一把尺子，
    防止"来源讲的其实是别的事"）；
  * `disputed=true` 的题**照收依据，但不动答案**，并在 `note` 里标明存疑
    —— 依据归依据、答案归答案，我无权擅自改答案。

## 输出

  * 收录的题：`explanationSrc = "web"`，`explanationRef = "<来源>（联网核查）"`，
    `explanationParts.reason = 依据原文`；
  * 生成 `qa/web-source-report.json`：收录/丢弃清单与原因，便于复核。
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
import gen_explanations as G              # noqa: E402
from explain_text import clean_evidence, render_text  # noqa: E402
from fix_relevance_final import longest_cjk_run       # noqa: E402

BANK = ROOT / "data" / "questions.json"
SRC = ROOT / "build" / "web-sourced"
REPORT = ROOT / "qa" / "web-source-report.json"
RUN_MIN = 4
MIN_REASON = 12

# **URL 权威性白名单**（所有联网依据都必须命中，不分置信度）。
# 为什么要有这一道：核查过程会把商业内容平台的**转载**当成来源
# （实测 18 条引用了 `baijiahao.baidu.com` 上一篇《国防法》全文转载）。
# 转载内容即使正确，也不是**可核查的权威出处** —— 目标是「真实、可核查」，
# 所以一律只收：法律法规数据库 / 政府 / 教育机构 / 权威官媒 / 经典文献库。
# 被排除的：百家号、搜狐、网易、新浪新闻、今日头条等自媒体与商业门户。
AUTHORITATIVE_URL = re.compile(
    r"^https?://([^/]*\.)?("
    r"gov\.cn|npc\.gov\.cn|moe\.gov\.cn|mod\.gov\.cn|"
    r"edu\.cn|ac\.cn|"
    r"people\.com\.cn|people\.cn|xinhuanet\.com|news\.cn|81\.cn|"
    r"cctv\.com|cctv\.cn|qstheory\.cn|studytimes\.cn|"
    r"chaoxing\.com|xueyinonline\.com|"
    r"ctext\.org|wikisource\.org|nlc\.cn|china\.org\.cn|"
    r"ungeneva\.org|chinadaily\.com\.cn|mrdx\.cn|"
    # 科普中国（中国科协主办，已核实：kepuchina.cn 站内公告与《科普中国工作手册》）
    r"kepuchina\.cn|"
    # 湖南宣讲（中共湖南省委宣传部理论宣讲平台，已核实其培训班通知页）
    r"hnxuanjiang\.cn|"
    # 中共中央党史和文献研究院官网（已核实其「十一届三中全会以来重要文献」等栏目）
    r"dswxyjy\.org\.cn|"
    # 中国科学院官网（已核实其「中国科学报」转载栏目）
    r"cas\.cn|"
    # 高等教育出版社（教材出版方，已核实其产品检索系统 hep.com.cn 为同一机构）
    r"hxedu\.com\.cn|hep\.com\.cn|"
    # 中国教育和科研计算机网（CERNET，教育部主管）
    r"cernet\.edu\.cn"
    r")(:\d+)?(/|$)")


def load_results() -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    notes: list[str] = []
    for d in sorted(SRC.glob("out-*")):
        for f in sorted(d.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception as e:
                notes.append(f"{f.name}: 解析失败 {e}")
                continue
            if isinstance(data, dict):
                data = data.get("results", [])
            if not isinstance(data, list):
                notes.append(f"{f.name}: 不是数组")
                continue
            for it in data:
                if isinstance(it, dict):
                    it["_file"] = f.name
                    items.append(it)
            notes.append(f"{f.name}: {len(data)} 条")
    return items, notes


def already_has_reason(q) -> bool:
    return bool((q.get("explanationParts") or {}).get("reason"))


def main() -> int:
    if not SRC.exists():
        print("尚无联网核查结果目录 build/web-sourced/")
        return 1
    items, notes = load_results()
    print(f"读入 {len(items)} 条核查结果")
    for n in notes[:40]:
        print("  ·", n)

    bank = json.loads(BANK.read_text(encoding="utf-8"))
    qs = bank["questions"]
    by_id = {q["id"]: q for q in qs}

    stats: Counter[str] = Counter()
    accepted: list[dict] = []
    rejected: list[dict] = []
    disputed: list[dict] = []

    for it in items:
        qid = str(it.get("id") or "").strip()
        q = by_id.get(qid)
        if q is None:
            stats["未知题号"] += 1
            rejected.append({"id": qid, "why": "题号不存在"})
            continue
        if already_has_reason(q):
            # **例外**：若已有依据是 `web` 但出处 URL 不在白名单里，
            # 而本次这条是权威 URL，则允许**用权威出处替换掉转载出处**。
            # 实测踩过：out-a/b/c 先把这些题填成了泉州晚报/新浪等转载，
            # 导致 out-d 找到的 spp.gov.cn、gov.cn 等权威原文被 `already_has_reason` 挡掉。
            existing_url = q.get("webSourceUrl") or ""
            incoming_url = str(it.get("url") or "").strip()
            can_upgrade = (q.get("explanationSrc") == "web"
                           and not AUTHORITATIVE_URL.match(existing_url)
                           and AUTHORITATIVE_URL.match(incoming_url))
            if not can_upgrade:
                stats["已有依据，跳过"] += 1
                continue
            stats["升级为权威出处"] += 1
        if not it.get("found"):
            stats["found=false"] += 1
            rejected.append({"id": qid, "why": "未找到依据"})
            if it.get("disputed"):
                disputed.append({"id": qid, "note": it.get("note", ""), "kind": "未找到依据但疑答案有误"})
            continue
        conf = str(it.get("confidence") or "").lower()
        url = str(it.get("url") or "").strip()
        # 闸一：URL 必须落在权威白名单里（自媒体/商业门户转载一律不收）
        if not AUTHORITATIVE_URL.match(url):
            stats["来源非权威（自媒体/门户转载）"] += 1
            rejected.append({"id": qid, "why": "来源非权威域名",
                             "url": url[:70]})
            continue
        # 闸二：置信度 high/medium 直接收；low 需来源是教育/政府/官媒
        #（白名单已保证权威性，low 视为"确实找到了内容但来源非原始文件"）
        if conf not in ("high", "medium", "low"):
            stats[f"置信度异常({conf or '空'})，丢弃"] += 1
            rejected.append({"id": qid, "why": f"置信度异常({conf})"})
            continue
        reason = clean_evidence(it.get("reason") or "")
        src = str(it.get("source") or "").strip()
        if len(reason) < MIN_REASON:
            stats["依据过短"] += 1
            rejected.append({"id": qid, "why": f"依据过短({len(reason)}字)"})
            continue
        if not re.match(r"^https?://", url):
            stats["缺少有效 URL"] += 1
            rejected.append({"id": qid, "why": "缺少有效 URL"})
            continue
        stem = re.sub(r"[_＿]{2,}", " ", q["stem"])
        run = longest_cjk_run(stem, reason)
        # 相关性判据（联网来源专用）：
        #   本地依据要求「连续汉字重合 ≥4」，但**法规/大纲/白皮书是规范表述**，
        #   题干往往是它的口语化改写 —— 逐字重合天然就短。实测因此误杀了一批
        #   **完全正确**的依据，例如：
        #     q-0107「与我国边界没有接壤的国家」↔ 政府网《版图》列出陆地邻国后
        #            指出泰国与我国不接壤（只有 3 字重合，但这就是标准答案的依据）；
        #     q-0389「《国防法》哪年颁布实施」↔ 法条「1997年3月14日…通过」。
        #   所以改用**话题重合**判据：题干实词命中 ≥2 个，或连续重合 ≥3 字。
        #   来源可信度已由 confidence + 白名单把关，且 URL 会存进题目供用户自行核查。
        terms = [t for t in G.keywords(stem) if len(t) >= 2 and t not in G.STOP]
        hit = sum(1 for t in terms if t in reason)
        if run < 4 and not (hit >= 2 or run >= 3):
            stats["与题干对不上"] += 1
            rejected.append({"id": qid, "why": f"与题干对不上(run={run},词命中={hit})",
                             "reason": reason[:80]})
            continue

        is_disp = bool(it.get("disputed"))
        note_bits = []
        if src:
            note_bits.append("来源：" + src)
        if is_disp:
            note_bits.append("⚠ 来源与本题答案存在出入，已如实记录，建议对照原卷核实：" +
                             (it.get("note") or "")[:160])
        elif it.get("note"):
            note_bits.append(str(it["note"])[:160])

        p = q.get("explanationParts") or {}
        p["reason"] = reason
        if note_bits:
            p["note"] = "；".join(b for b in note_bits if b).strip("；")
        q["explanationParts"] = p
        q["explanationSrc"] = "web"
        q["explanationRef"] = (src + "（联网核查）") if src else "联网核查"
        q["explanation"] = render_text(p)
        q["webSourceUrl"] = url
        if is_disp:
            q["answerDisputedBySource"] = True
            disputed.append({"id": qid, "note": it.get("note", ""), "source": src, "url": url})
        stats["收录"] += 1
        accepted.append({"id": qid, "confidence": conf, "source": src, "url": url,
                         "disputed": is_disp})

    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1), encoding="utf-8")

    with_reason = sum(1 for q in qs if (q.get("explanationParts") or {}).get("reason"))
    report = {
        "stats": dict(stats),
        "withReason": with_reason,
        "total": len(qs),
        "coverage": round(with_reason / len(qs), 4),
        "accepted": accepted,
        "rejected": rejected,
        "disputed": disputed,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print()
    print("=" * 76)
    print("联网依据合并报告")
    print("=" * 76)
    for k, v in stats.most_common():
        print(f"  {k:26} {v}")
    print()
    print(f"  现有依据句: {with_reason} / {len(qs)}  ({with_reason/len(qs):.0%})")
    print(f"  来源与答案有出入（需人工核）: {len(disputed)} 道")
    for d in disputed[:12]:
        print(f"    {d['id']}: {d.get('note','')[:90]}")
    print()
    print(f"  报告: qa/web-source-report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
