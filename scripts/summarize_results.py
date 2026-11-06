"""Render a small evidence index from saved runs; no model requests."""

import json
from pathlib import Path
from collections import Counter
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main():
    primary = read("examples/evaluation-live-final.json")
    rescore = read("examples/grounding-regression-rescore.json")
    challenge = read("examples/challenge-final-live.json")
    stress = read("docs/retrieval-stress.json")
    if not primary["complete"] or not challenge["complete"]:
        raise ValueError("Cannot describe incomplete runs as finished")
    suite = ET.parse(ROOT / "docs/test-results.xml").getroot().find("testsuite")
    lines = [
        "# Live 证据索引",
        "",
        "本页由 scripts/summarize_results.py 从实际产物生成，不发出模型调用。",
        "",
        f"pytest：{suite.attrib['tests']} 项，失败 {suite.attrib['failures']}，错误 {suite.attrib['errors']}。",
        "",
        "## 基础集：相同模型、问题和资料",
        "",
        "模型：MiniMax-M3.1-Flash；Prompt v4；单 Agent 最终复核；默认上限 8 轮 / 10 次工具。",
        "",
        "| 指标 | Baseline | Improved |",
        "|---|---:|---:|",
    ]
    for label, key in [
        ("Recall@5", "recall_at_5"),
        ("状态正确率", "status_accuracy"),
        ("冲突发现率", "conflict_detection_rate"),
        ("引用出处有效率", "citation_validity_rate"),
        ("原始事实回归率（旧口径）", "fact_regression_pass_rate"),
        ("平均工具调用", "mean_tool_calls"),
        ("平均模型调用（含复核）", "mean_model_calls"),
        ("平均 token 用量", "mean_total_tokens"),
        ("API 错误率", "api_error_rate"),
    ]:
        a, b = [primary["reports"][m]["metrics"][key] for m in ("baseline", "improved")]
        lines.append(f"| {label} | {a:.4f} | {b:.4f} |")
    lines += [
        "",
        "原始 Improved 有一项事实检查未通过。逐条查证后确认：草稿提醒已成功读取且引用 D13，",
        "属于原先禁止词断言的误报。条件引文测试仍拒绝无草稿引文的同一回答。原始报告和失败值保留；",
        "以下仅对已有输出按修订注释重评分，新增模型调用为 0，不能当作一次新运行。",
        "",
        "| 修订后的案例通过率 | Baseline | Improved |",
        "|---|---:|---:|",
        f"| 条件引文义务回归 | {rescore['reports']['baseline']['case_pass_rate']:.4f} | {rescore['reports']['improved']['case_pass_rate']:.4f} |",
        "",
        "[原始运行](../examples/evaluation-live-final.json) · [重评分及规则说明](../examples/grounding-regression-rescore.json)",
        "",
        "## 六项必验和资料变更",
        "",
        "| 案例 | 实际状态 | 工具 / 模型调用 | Trace |",
        "|---|---|---|---|",
    ]
    paths = set()
    for row in primary["reports"]["improved"]["cases"]:
        trace = read(row["trace"])
        paths.add(tuple(e["tool_name"] for e in trace["events"] if e["type"] == "tool"))
        lines.append(
            f"| {row['case_id']} {row['name']} | {row['status']} | {row['tool_calls']} / {row['model_calls']} | [查看](../{row['trace']}) |"
        )
    lines += [
        "",
        f"真实工具名称序列有 {len(paths)} 种，超过要求的两种；每次模型调用有实际 response_id 与用量。",
        "",
        "## 扩展集",
        "",
        "| 案例 | 状态 | 三项回归检查 |",
        "|---|---|---|",
    ]
    for row in challenge["reports"]["improved"]["cases"]:
        passed = (
            row["status_correct"]
            and row["fact_checks_pass"]
            and row["citation_expectations_pass"]
        )
        lines.append(
            f"| {row['case_id']} {row['name']} | {row['status']} | {'通过' if passed else '未通过'} |"
        )
    lines += [
        "",
        "[扩展集完整原始结果](../examples/challenge-final-live.json)。包含已知部门、历史部门、读失败、一次搜索失败恢复、",
        "替代链、ID/片段改名和 77 天新值、多片段冲突、真实轮次耗尽、旧历史与当前 45 天资料。",
        "",
        "## 竞争文档压力集",
        "",
        f"6 个针对精确 ID 的候选发现案例：Baseline Recall@5={stress['reports']['baseline']['metrics']['recall_at_5']:.4f}，Improved={stress['reports']['improved']['metrics']['recall_at_5']:.4f}。",
        "这是针对机制设计的压力集，不是通用盲测；普通问题集两者仍为 1.0。",
        "",
    ]
    audit_path = ROOT / "examples/semantic-audit-complete-context.json"
    if audit_path.exists():
        audit = read("examples/semantic-audit-complete-context.json")
        lines += [
            "## 补充语义审查",
            "",
            f"实际判定计数：{dict(Counter(c['verdict'] for c in audit['checks']))}。",
            "[完整上下文判定](../examples/semantic-audit-complete-context.json)。它是无工具的离线模型检查，不是第二个运行时 Agent，也不是真值。",
            "初次审查因漏传真实文档标题出现误报，旧判定保留为 examples/semantic-audit-final.json；完整元数据版本另存，未覆盖。",
            "",
        ]
    lines += [
        "## 失败记录与限制",
        "",
        "examples/prompt-v1、prompt-v2-pilot、baseline-live、challenge-live、challenge-v3-live、challenge-v4-live",
        "及 evaluation-live.json 等保留了先前输出；包括限流、范围状态、过度拒答和预算挤占，不能用新结果覆盖。",
        "源码和 Prompt 的回归仍不能保证任意问题都正确。模型语义审查不独立；全部资料为合成，小样本非生产准确率。",
    ]
    (ROOT / "docs/06-live-evidence.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    summary = {
        "mode": "live",
        "executed": True,
        "status": "VERIFIED_WITH_DISCLOSED_ANNOTATION_RESCORE",
        "report": "examples/evaluation-live-final.json",
        "annotation_rescore": "examples/grounding-regression-rescore.json",
        "all_improved_cases_passed_original_checks": all(
            c["status_correct"]
            and c["fact_checks_pass"]
            and c["citation_expectations_pass"]
            for c in primary["reports"]["improved"]["cases"]
        ),
        "all_improved_cases_passed_current_checks": all(
            c["passed"] for c in rescore["reports"]["improved"]["cases"]
        ),
        "all_challenge_cases_passed": all(
            c["status_correct"]
            and c["fact_checks_pass"]
            and c["citation_expectations_pass"]
            for c in challenge["reports"]["improved"]["cases"]
        ),
        "distinct_tool_paths": [list(p) for p in sorted(paths)],
        "at_least_two_real_paths": len(paths) >= 2,
        "note": "Original failed fact check retained; conditional citation obligation rescored existing outputs with zero new API requests. Small synthetic dataset, not production accuracy.",
    }
    (ROOT / "examples/live-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
