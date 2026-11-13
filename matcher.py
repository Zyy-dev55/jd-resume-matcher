"""JD 简历适配助手 · 命令行入口

用法：
    python matcher.py --demo --offline
    python matcher.py --jd "熟悉 RAG 与结构化输出，能用 Python 做 Agent 开发"
    python matcher.py --jd-file jd.txt
    python matcher.py --eval --offline
    python matcher.py --providers
"""
import argparse
import json
import os
import sys

from jd_matcher.evaluate import fmt_evidence, run_eval
from jd_matcher.knowledge import all_chunks
from jd_matcher.llm import ProviderChain
from jd_matcher.retrieval import MIN_EVIDENCE_SCORE, EvidenceRetriever

ROOT = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(ROOT, "reports")

DEMO_JD = (
    "AI 应用开发实习生：参与大模型智能体（Agent）研发，依托 RAGFlow / GraphRAG 搭建检索与知识库问答体系；"
    "熟悉大模型 API 调用、结构化输出与 Prompt 设计，了解工具调用与失败降级；"
    "熟练 Python，了解 MySQL，具备接口联调与效果评测能力；能用 AI 工具快速构建原型。"
)


def strong_evidence(evidence):
    """低于阈值的片段不进上下文，避免无关 JD 也被硬凑成匹配点。"""
    return [e for e in evidence if e["score"] >= MIN_EVIDENCE_SCORE]


def rule_based(jd, evidence):
    """模型不可用时的降级结果：只给可溯源证据，不编造匹配结论。"""
    strong = strong_evidence(evidence)
    if not strong:
        return {
            "matched": [],
            "gaps": ["证据库中没有与该 JD 相关的可核对能力，按底线不生成匹配结论"],
            "rewrite": ["这份 JD 与现有项目不匹配，建议如实标注缺口，不要包装"],
            "score": 0,
        }
    return {
        "matched": [
            {
                "point": "检索到的可核对能力（规则模式，未做语义判断）",
                "evidence": e["text"],
                "project": e["project_name"],
                "chunk_id": e["chunk_id"],
            }
            for e in strong[:3]
        ],
        "gaps": ["未配置模型 API，本次不做语义级匹配、评分与逐条改写建议"],
        "rewrite": ["配置 config.json 或环境变量后重跑，可获得针对该 JD 的逐条改写建议"],
        "score": 0,
    }


def match(jd, offline=False, k=4):
    evidence = EvidenceRetriever(all_chunks()).search(jd, k=k)
    chain = ProviderChain(os.path.join(ROOT, "config.json"))
    meta = {"retrieval_k": k, "evidence_threshold": MIN_EVIDENCE_SCORE, "chain": chain.status()}
    if offline or not chain.available:
        analysis = rule_based(jd, evidence)
        mode = "offline" if not chain.available else "forced-offline"
        meta["reason"] = chain.load_error or "未配置可用的模型服务商，或显式指定 --offline"
    else:
        data, call_meta = chain.structured(jd, fmt_evidence(strong_evidence(evidence)))
        meta["call"] = call_meta
        if data is None:
            analysis = rule_based(jd, evidence)
            mode = "fallback"
            meta["reason"] = "所有服务商均失败，按三条底线自动放行"
        else:
            analysis = data
            mode = "api"
    return {
        "jd": jd,
        "mode": mode,
        "retrieval": [
            {"chunk_id": e["chunk_id"], "project": e["project_name"], "score": e["score"]}
            for e in evidence
        ],
        "analysis": analysis,
        "meta": meta,
    }


def print_result(result):
    print("=" * 68)
    print("JD 简历适配助手 | 模式：" + result["mode"])
    print("=" * 68)
    print("\n[检索到的证据片段]")
    for e in result["retrieval"]:
        print(f'  {e["chunk_id"]:<8} {e["project"]:<28} {e["score"]}')
    print(f'  （证据阈值 {result["meta"]["evidence_threshold"]}，低于阈值不进生成上下文）')
    a = result["analysis"]
    print("\n[匹配点]")
    if not a["matched"]:
        print("  （无可核对证据，未生成匹配结论）")
    for m in a["matched"][:5]:
        print(f'  - {m.get("point", "")}')
        print(f'    证据：{str(m.get("evidence", ""))[:90]}')
        print(f'    来源：{m.get("project", "")} / {m.get("chunk_id", "")}')
    print("\n[能力缺口]")
    for g in a["gaps"][:5]:
        print("  - " + str(g))
    print("\n[简历改写建议]")
    for r in a["rewrite"][:5]:
        print("  - " + str(r))
    print(f'\n[适配分] {a["score"]}')
    if result["mode"] != "api":
        print("[说明] " + result["meta"].get("reason", ""))


def main():
    ap = argparse.ArgumentParser(description="JD 简历适配助手")
    ap.add_argument("--jd", help="直接传入 JD 文本")
    ap.add_argument("--jd-file", help="从文件读取 JD")
    ap.add_argument("--demo", action="store_true", help="使用内置示例 JD")
    ap.add_argument("--eval", action="store_true", help="运行 25 条评测集并生成报告")
    ap.add_argument("--providers", action="store_true", help="查看模型服务商配置状态")
    ap.add_argument("--selftest", action="store_true", help="自检模型接入链路（无凭证时用本地 mock）")
    ap.add_argument("--mock", action="store_true", help="配合 --selftest 强制本地 mock 验证")
    ap.add_argument("--offline", action="store_true", help="强制离线规则模式，不调用模型")
    ap.add_argument("-k", type=int, default=4, help="检索返回片段数，默认 4")
    args = ap.parse_args()

    if args.selftest:
        from jd_matcher.selftest import run_mock_selftest, run_real_selftest
        chain = ProviderChain(os.path.join(ROOT, "config.json"))
        result = run_mock_selftest() if (args.mock or not chain.available) else run_real_selftest(chain)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        os.makedirs(REPORT_DIR, exist_ok=True)
        with open(os.path.join(REPORT_DIR, "selftest_report.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("\n自检报告已写入 reports/selftest_report.json")
        return

    if args.providers:
        print(json.dumps(ProviderChain(os.path.join(ROOT, "config.json")).status(), ensure_ascii=False, indent=2))
        return

    if args.eval:
        chain = None if args.offline else ProviderChain(os.path.join(ROOT, "config.json"))
        s = run_eval(chain=chain, offline_only=args.offline, k=args.k)
        print(json.dumps(s, ensure_ascii=False, indent=2))
        print("\n报告已写入 reports/eval_report.md 与 reports/eval_report.json")
        return

    if args.jd:
        jd = args.jd
    elif args.jd_file:
        with open(args.jd_file, "r", encoding="utf-8") as f:
            jd = f.read()
    elif args.demo:
        jd = DEMO_JD
    else:
        ap.print_help()
        return

    result = match(jd, offline=args.offline, k=args.k)
    print_result(result)
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(os.path.join(REPORT_DIR, "last_match.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("\n结构化结果已写入 reports/last_match.json")


if __name__ == "__main__":
    sys.exit(main())
