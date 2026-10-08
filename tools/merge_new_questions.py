#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_new_questions.py — 把本轮分片合并进 data/questions.json。

口径（用户裁定 + 数据契约 docs/02-data-contract.md）
--------------------------------------------------
* **只追加，不改动既有 1171 题**（47 条答案冲突题按用户裁定冻结）。
* 新题 id 从现有最大号 +1 起顺序分配（实测既有无缺号，接尾即连续）。
* 字段完备：新题必须补齐契约要求的全部字段；缺 explanation 的题**拒绝入库**并列出。
* 类型映射（论述题并入简答，用户裁定）：single/multi/judge/fill/short。
* source：`isReal` → `真题` / `模拟题`。
* 写盘格式与既有文件一致（实测）：`json.dumps(indent=1)` + **CRLF** + 末尾换行。

用法（`work/` 与 `work/split/` 由脚本自动创建）：
    python tools/merge_new_questions.py --dry     # 只体检，不写盘
    python tools/merge_new_questions.py           # 写盘（先 .tmp 再替换）
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
WORK = ROOT / "work"
WORK.mkdir(parents=True, exist_ok=True)
SPLIT = WORK / "split"
BANK = ROOT / "data" / "questions.json"
REPORT = WORK / "merge-report.json"

TYPE_MAP = {"single": "single", "multi": "multi", "judge": "judge", "fill": "fill",
            "short_answer": "short", "short": "short", "essay": "short"}
SHARD_FILES = ["shard-01.json", "shard-02.json", "shard-03.json", "shard-04.json", "shard-11nian.json"]
OUTLINE = Path(r"D:\.Study\大学\军训期间\军理课\【第二版】source\military_theory\outline.json")
CH_NAME = {"MT_CH01": "第一章中国国防", "MT_CH02": "第二章国家安全", "MT_CH03": "第三章军事思想",
           "MT_CH04": "第四章现代战争", "MT_CH05": "第五章信息化装备"}


def load_outline_names() -> dict[str, dict[str, str]]:
    """第二版考纲 {小节 id: {name, section_name}}，用于给新题补小节归属。"""
    out: dict[str, dict[str, str]] = {}
    try:
        o = json.loads(OUTLINE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"!! 读取第二版大纲失败（小节名将为空）：{e}")
        return out
    for ch in o.get("chapters", []):
        for sec in ch.get("sections", []):
            sec_name = sec.get("name", "")
            for u in sec.get("units", []):
                if isinstance(u, dict) and u.get("id"):
                    out[u["id"]] = {"name": u.get("name") or sec_name, "section_name": sec_name}
    return out

REQUIRED = ["id", "type", "stem", "options", "answer", "explanation", "source", "chapter",
            "section", "explanationSrc", "explanationRef", "keyConcept", "keywords",
            "explanationParts"]
VALID_SRC = {"textbook", "manual", "bank", "template", "web"}


def norm_answer(qtype: str, raw):
    """把答案归一化到数据契约规定的形态。"""
    if qtype == "multi":
        if isinstance(raw, list):
            letters = [str(x).strip().upper() for x in raw]
        else:
            letters = [c for c in str(raw).strip().upper() if c.isalpha()]
        return sorted({c for c in letters if "A" <= c <= "D"})
    if qtype == "single":
        return str(raw).strip().upper()
    if qtype == "judge":
        if isinstance(raw, bool):
            return raw
        t = str(raw).strip()
        if t in ("正确", "对", "true", "True", "T", "√"):
            return True
        if t in ("错误", "错", "false", "False", "F", "×"):
            return False
        raise ValueError(f"判断题答案无法识别：{raw!r}")
    if qtype == "fill":
        if isinstance(raw, list):
            return [str(x) for x in raw]
        return [str(raw)]
    return str(raw)


def norm_options(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def check_item(it: dict, idx: int, errs: list[str], outline: dict[str, dict[str, str]]) -> dict | None:
    """校验并归一化单题；不合格返回 None。"""
    raw_type = str(it.get("type", "")).strip()
    qtype = TYPE_MAP.get(raw_type)
    if not qtype:
        errs.append(f"#{idx} 未知题型 {raw_type!r}（题面：{str(it.get('stem'))[:24]}）")
        return None
    stem = str(it.get("stem", "")).strip()
    if not stem:
        errs.append(f"#{idx} 题干为空")
        return None
    options = norm_options(it.get("options"))
    if qtype in ("single", "multi"):
        if len(options) < 2:
            errs.append(f"#{idx} {qtype} 选项不足 2 个（{stem[:24]}）")
            return None
    else:
        options = []
    try:
        answer = norm_answer(qtype, it.get("answer"))
    except ValueError as e:
        errs.append(f"#{idx} {e}")
        return None
    if qtype == "single":
        if len(answer) != 1 or not ("A" <= answer <= "D"):
            errs.append(f"#{idx} 单选答案非法 {answer!r}（{stem[:24]}）")
            return None
        if ord(answer) - 65 >= len(options):
            errs.append(f"#{idx} 单选答案 {answer} 超出选项范围 {len(options)}（{stem[:24]}）")
            return None
    if qtype == "multi":
        if len(answer) < 2:
            errs.append(f"#{idx} 多选答案不足 2 个字母 {answer!r}（{stem[:24]}）")
            return None
        if max(ord(c) - 65 for c in answer) >= len(options):
            errs.append(f"#{idx} 多选答案 {''.join(answer)} 超出选项范围 {len(options)}（{stem[:24]}）")
            return None
    explanation = str(it.get("explanation", "")).strip()
    if not explanation:
        errs.append(f"#{idx} 缺少解析（{stem[:24]}）")
        return None
    src = str(it.get("explanationSrc", "")).strip()
    if src not in VALID_SRC:
        errs.append(f"#{idx} explanationSrc 非法 {src!r}（{stem[:24]}）")
        return None
    parts = it.get("explanationParts")
    if not isinstance(parts, dict):
        errs.append(f"#{idx} explanationParts 不是对象（{stem[:24]}）")
        return None
    parts = {k: str(parts.get(k, "") or "") for k in ("answer", "reason", "ref", "note")}
    kw = it.get("keywords")
    kw = [str(x) for x in kw][:8] if isinstance(kw, list) else []
    why = it.get("distractorWhy")
    why = {str(k): str(v) for k, v in why.items()} if isinstance(why, dict) else {}
    # 干扰项说明的键必须指向真实存在的选项；合格判定分三种情况：
    #   ① 正向题：至少给一个**错误选项**写了说明；
    #   ② 否定题（问「不属于/不包括/不正确的是」）：给选定项写明它为何是错误表述；
    #   ③ 全选型题（所有选项都是正确答案，无错误项）：distractorWhy 为空是正确形态。
    if qtype in ("single", "multi"):
        wrong = [chr(65 + i) for i in range(len(options)) if chr(65 + i) not in set(answer)]
        allletters = [chr(65 + i) for i in range(len(options))]
        bad_keys = [k for k in why if k not in allletters]
        if bad_keys:
            errs.append(f"#{idx} distractorWhy 键 {'/'.join(bad_keys)} 不是本题选项（{stem[:24]}）")
            return None
        is_negative = bool(re.search(r"不属于|不包括|不是|不正确的|错误的是|除外|不对的", stem))
        covered_wrong = any(str(why.get(k, "")).strip() for k in wrong)
        covered_answer = any(str(why.get(k, "")).strip() for k in (answer if isinstance(answer, list) else [answer]))
        if wrong and not (covered_wrong or (is_negative and covered_answer)):
            errs.append(f"#{idx} 干扰项说明为空（既没写错误选项，否定题也没写错误说法）（{stem[:24]}）")
            return None
        if not wrong and why:
            errs.append(f"#{idx} 全选型题不应有 distractorWhy（{stem[:24]}）")
            return None

    is_real = it.get("isReal")
    source = "真题" if is_real is True else "模拟题"
    chapter = str(it.get("chapter", "")).strip() or "未分类"
    section = str(it.get("section", "")).strip() or "未分类"
    # 小节归属：分片里已写的优先（11 年真题片），否则按第二版小节 id 查表（新题）
    sub_name = str(it.get("subsection", "") or "")
    sec_name = str(it.get("section_name", "") or "")
    if not sub_name:
        info = outline.get(str(it.get("sub", "") or ""), {})
        sub_name = info.get("name", "")
        sec_name = info.get("section_name", "")
    if not sub_name and chapter == "第一章中国国防" and section in ("判断题", "单选题"):
        # 2011 年原卷属中国国防史范畴（第二版大纲无这一节，按考纲第一节归类）
        sub_name, sec_name = "中国国防历史", "国防概述"
    hard = it.get("isHard")
    item = {
        "id": "",
        "type": qtype,
        "stem": stem,
        "options": options,
        "answer": answer,
        "explanation": explanation,
        "source": source,
        "chapter": chapter,
        "section": section,
        "raw": str(it.get("originNote") or it.get("stem") or stem)[:200],
        "explanationSrc": src,
        "explanationRef": str(it.get("explanationRef", "") or ""),
        "keyConcept": str(it.get("keyConcept", "") or ""),
        "keywords": kw,
        "distractorWhy": why,
        "explanationParts": parts,
        "isHard": hard is True,
        # 小节归属（第二版考纲；供「复习提纲」并入 章 → 节 → 小节 用）
        "subsection": sub_name,
        "sectionName": sec_name,
        "_origin": str(it.get("origin_id") or it.get("v2_id") or ""),
    }
    if src == "web" and not item["explanationRef"]:
        errs.append(f"#{idx} explanationSrc=web 但 explanationRef 为空（{stem[:24]}）")
        return None
    return item


def main() -> int:
    dry = "--dry" in sys.argv
    # 允许指定靶文件：用于「彩排」（写到临时副本，不动正式题库）
    target = BANK
    for i, a in enumerate(sys.argv):
        if a == "--out" and i + 1 < len(sys.argv):
            target = Path(sys.argv[i + 1])
    bank = json.loads(target.read_text(encoding="utf-8"))
    qs = bank["questions"]
    used_ids = {q["id"] for q in qs}
    maxn = max(int(q["id"].split("-")[1]) for q in qs)

    errs: list[str] = []
    picked: list[dict] = []
    per_shard: dict[str, dict] = {}
    outline = load_outline_names()
    print(f"第二版考纲小节名 {len(outline)} 条")
    for fn in SHARD_FILES:
        p = SPLIT / fn
        if not p.exists():
            errs.append(f"分片缺失：{p}")
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data.get("items", [])
        ok = 0
        for i, it in enumerate(items):
            item = check_item(it, i, errs, outline)
            if item:
                picked.append(item)
                ok += 1
        per_shard[fn] = {"total": len(items), "accepted": ok, "rejected": len(items) - ok}

    # 新题内部去重（题干 + 选项集合）
    seen: dict[tuple, str] = {}
    dedup: list[dict] = []
    for it in picked:
        key = (it["stem"], tuple(it["options"]))
        if key in seen:
            errs.append(f"新题内部重复：{it['_origin']} 与 {seen[key]}（{it['stem'][:24]}）")
            continue
        seen[key] = it["_origin"]
        dedup.append(it)

    # 与既有题库比对（题干 + 选项集合完全一致 → 拒绝）
    bankkey = {(q["stem"], tuple(q.get("options", []))) for q in qs}
    final: list[dict] = []
    for it in dedup:
        key = (it["stem"], tuple(it["options"]))
        if key in bankkey:
            errs.append(f"与既有题库重复：{it['_origin']}（{it['stem'][:24]}）")
            continue
        final.append(it)

    for i, it in enumerate(final):
        nid = f"q-{maxn + 1 + i:04d}"
        if nid in used_ids:
            errs.append(f"id 冲突 {nid}")
        it["id"] = nid

    # 报告
    by_type: dict[str, int] = {}
    by_src: dict[str, int] = {}
    by_esrc: dict[str, int] = {}
    for it in final:
        by_type[it["type"]] = by_type.get(it["type"], 0) + 1
        by_src[it["source"]] = by_src.get(it["source"], 0) + 1
        by_esrc[it["explanationSrc"]] = by_esrc.get(it["explanationSrc"], 0) + 1
    report = {
        "existing": len(qs), "accepted": len(final), "rejected": len(picked) - len(final),
        "errors": errs[:200], "errorCount": len(errs),
        "perShard": per_shard,
        "byType": by_type, "bySource": by_src, "byExplanationSrc": by_esrc,
        "hardCount": sum(1 for it in final if it["isHard"]),
        "idFrom": final[0]["id"] if final else None,
        "idTo": final[-1]["id"] if final else None,
        "totalAfter": len(qs) + len(final),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"既有 {len(qs)} 题；新题接受 {len(final)}，拒绝 {report['rejected']}；错误 {len(errs)} 条")
    print(f"题型 {by_type}")
    print(f"来源 {by_src}")
    print(f"依据 {by_esrc}")
    print(f"难题 {report['hardCount']}；新 id {report['idFrom']} → {report['idTo']}；入库后共 {report['totalAfter']} 题")
    for e in errs[:15]:
        print("   ✗", e)
    if len(errs) > 15:
        print(f"   …另有 {len(errs) - 15} 条，见 {REPORT}")

    # 彩排模式：只容忍「缺少解析」（某分片的解析子代理尚未交付），其余错误照旧阻止写盘。
    # 用途：在最终分片到齐前，先用现有分片跑通「入库 → 打包 → 验收」全链路。
    tolerant = "--tolerant" in sys.argv
    blocking = [e for e in errs if not (tolerant and "缺少解析" in e)]
    if tolerant and len(blocking) != len(errs):
        print(f"--tolerant：放行 {len(errs) - len(blocking)} 条「缺少解析」，其余 {len(blocking)} 条仍为阻断项")
    if blocking:
        print("!! 存在校验错误，**不写盘**。修好后重跑。")
        return 1
    if dry:
        print("--dry：体检通过，未写盘。")
        return 0

    # 写盘：只追加，既有题目原样保留
    out_items = list(qs)
    for it in final:
        clean = {k: v for k, v in it.items() if not k.startswith("_")}
        out_items.append(clean)
    text = json.dumps({"questions": out_items}, ensure_ascii=False, indent=1) + "\n"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    # 回读校验：能解析、题数正确、既有题一字未变
    back = json.loads(tmp.read_text(encoding="utf-8"))
    assert len(back["questions"]) == len(out_items), "题数不一致"
    assert back["questions"][:len(qs)] == qs, "既有题目被改动"
    tmp.replace(target)
    print(f"已写入 {target}：{len(qs)} → {len(out_items)} 题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
