"""评测集运行器：用固定的 25 条 JD 守住每次改动，不靠感觉调 Prompt。

正例看「有没有把对的项目证据送进上下文」，负例看「无关 JD 会不会硬凑证据」。
"""
import json
import os
from datetime import datetime

from .knowledge import all_chunks
from .retrieval import MIN_EVIDENCE_SCORE, EvidenceRetriever

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(ROOT, "reports")


def fmt_evidence(evidence):
    return "\n".join(
        f'[{c["chunk_id"]}] {c["project_name"]}：{c["text"]}' for c in evidence
    )


def run_eval(chain=None, offline_only=False, k=4):
    with open(os.path.join(ROOT, "eval_set.json"), "r", encoding="utf-8") as f:
        cases = json.load(f)
    retriever = EvidenceRetriever(all_chunks())

    rows = []
    pos_total = neg_total = pos_hits = neg_correct = 0
    json_ok = api_calls = fallbacks = evidence_ok = 0
    latencies = []
    for c in cases:
        evidence = retriever.search(c["jd"], k=k)
        top_score = evidence[0]["score"] if evidence else 0.0
        is_neg = c["expect_project"] == "NONE"
        if is_neg:
            neg_total += 1
            hit = top_score < MIN_EVIDENCE_SCORE
            neg_correct += int(hit)
        else:
            pos_total += 1
            hit = any(e["project_id"] == c["expect_project"] for e in evidence)
            pos_hits += int(hit)
        mode, provider = "offline", "-"
        if chain is not None and chain.available and not offline_only:
            strong = [e for e in evidence if e["score"] >= MIN_EVIDENCE_SCORE]
            data, meta = chain.structured(c["jd"], fmt_evidence(strong))
            api_calls += 1
            latencies.append(meta["latency_ms"])
            if data is not None:
                json_ok += 1
                if data.get("dropped_invalid_evidence", 0) == 0:
                    evidence_ok += 1
                mode, provider = "api", meta["provider"] or "-"
            else:
                fallbacks += 1
                mode = "fallback"
        else:
            fallbacks += 1
        rows.append({
            "id": c["id"],
            "kind": "负例" if is_neg else "正例",
            "expect": c["expect_project"],
            "hit": bool(hit),
            "top1": evidence[0]["chunk_id"] if evidence else "-",
            "top_score": top_score,
            "mode": mode,
            "provider": provider,
            "jd": c["jd"],
        })

    n = len(cases)
    summary = {
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cases": n,
        "cases_positive": pos_total,
        "cases_negative": neg_total,
        "retrieval_hit_at_k": round(pos_hits / pos_total, 4) if pos_total else None,
        "negative_reject_rate": round(neg_correct / neg_total, 4) if neg_total else None,
        "evidence_threshold": MIN_EVIDENCE_SCORE,
        "k": k,
        "api_calls": api_calls,
        "json_compliance": round(json_ok / api_calls, 4) if api_calls else None,
        "evidence_compliance": round(evidence_ok / api_calls, 4) if api_calls else None,
        "fallback_rate": round(fallbacks / n, 4),
        "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else None,
        "mode": "api" if api_calls else "offline",
        "note": "offline 模式只反映检索层（正例命中 / 负例拒绝）；JSON 遵守率、证据引用合规率与延迟需配置 API Key 后重跑才有效。",
    }

    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(os.path.join(REPORT_DIR, "eval_report.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "cases": rows}, f, ensure_ascii=False, indent=2)

    jc = f'{summary["json_compliance"]:.0%}' if summary["json_compliance"] is not None else "N/A（未调用模型）"
    ec = f'{summary["evidence_compliance"]:.0%}' if summary["evidence_compliance"] is not None else "N/A（未调用模型）"
    lat = f'{summary["avg_latency_ms"]} ms' if summary["avg_latency_ms"] is not None else "N/A"
    lines = [
        "# 评测报告",
        "",
        f'- 运行时间：{summary["run_at"]}',
        f'- 运行模式：{summary["mode"]}',
        f'- 评测用例：{n} 条（正例 {pos_total} / 负例 {neg_total}）',
        f'- 正例检索 Hit@{k}：**{summary["retrieval_hit_at_k"]:.0%}**',
        f'- 负例正确拒绝率：**{summary["negative_reject_rate"]:.0%}**（证据阈值 {MIN_EVIDENCE_SCORE}）',
        f'- 结构化输出遵守率：{jc}',
        f'- 证据引用合规率：{ec}',
        f'- 降级触发率：{summary["fallback_rate"]:.0%}',
        f'- 平均单次调用延迟：{lat}',
        "",
        "> " + summary["note"],
        "",
        "| 用例 | 类型 | 期望项目 | 判定正确 | Top1 片段 | 得分 | 模式 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f'| {r["id"]} | {r["kind"]} | {r["expect"]} | {"是" if r["hit"] else "否"} | '
            f'{r["top1"]} | {r["top_score"]} | {r["mode"]} |'
        )
    lines += ["", "## 用例 JD 原文", ""]
    for r in rows:
        lines.append(f'- **{r["id"]}**（{r["kind"]}，期望 {r["expect"]}）：{r["jd"]}')
    with open(os.path.join(REPORT_DIR, "eval_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return summary
