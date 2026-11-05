"""Paired, reproducible metrics; missing Live data is never replaced by Mock."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from .agent import Agent
from .model import LiveModel, MockModel
from .retriever import Corpus, Retriever
from .trace import write_json


def read_cases(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def check_case(case: dict, result: dict) -> dict:
    answer = result["answer"]
    ids = {c["doc_id"] for c in result["citations"]}
    return {
        "status_correct": result["status"] == case["expected_status"],
        # These small regression checks are semantic proxies, not an LLM judge.
        "fact_checks_pass": all(x in answer for x in case.get("required_facts", []))
        and not any(x in answer for x in case.get("forbidden_facts", [])),
        "citation_expectations_pass": set(case.get("required_citations", [])) <= ids
        and not (set(case.get("forbidden_citations", [])) & ids),
    }


def evaluate(
    cases_path: Path,
    root: Path,
    mode: str,
    output: Path,
    retrieval_only: bool = False,
    examples_dir: Path | None = None,
) -> dict:
    cases = read_cases(cases_path)
    reports = {}
    for method in ("baseline", "improved"):
        rows = []
        for case in cases:
            corpus = Corpus(root / "data/scenarios" / case["scenario"])
            # Context resolution is the model's responsibility; retrieval benchmark uses
            # the exact same question for both methods, with no oracle query rewrite.
            hits = Retriever(corpus, method).search(case["question"], 5)
            relevant = set(case["relevant_docs"])
            row = {
                "case_id": case["id"],
                "name": case["name"],
                "expected_status": case["expected_status"],
                "recalled_docs": sorted({h["doc_id"] for h in hits}),
                "recall_at_5": len(relevant & {h["doc_id"] for h in hits})
                / len(relevant)
                if relevant
                else None,
            }
            if not retrieval_only:
                model = LiveModel() if mode == "live" else MockModel()
                agent = Agent(
                    model,
                    corpus,
                    method=method,
                    fail_tool=case.get("fail_tool"),
                    fail_count=case.get("fail_count", 0),
                )
                trace_path = (
                    output.parent
                    / f"{output.stem}-traces"
                    / mode
                    / method
                    / f"{case['id']}.json"
                )
                try:
                    result = agent.run(
                        case["question"], case.get("history"), trace_path
                    )
                finally:
                    if mode == "live":
                        model.client.close()
                citation_checks = [
                    e for e in agent.trace["events"] if e["type"] == "validation"
                ]
                valid_citations = (
                    len(result["citations"])
                    if citation_checks and citation_checks[-1]["valid"]
                    else 0
                )
                row |= check_case(case, result) | {
                    "status": result["status"],
                    "tool_calls": result["task_state"]["tool_calls"],
                    "duration_ms": agent.trace["duration_ms"],
                    "citation_count": len(result["citations"]),
                    "valid_citations": valid_citations,
                    "unsupported_answer": result["status"] == "ANSWERED"
                    and (
                        case["expected_status"]
                        in {
                            "NOT_FOUND",
                            "CONFLICT",
                            "NEEDS_CLARIFICATION",
                            "TOOL_ERROR",
                        }
                        or not agent.trace["evidence_validation"]["valid"]
                        or not check_case(case, result)["fact_checks_pass"]
                    ),
                    "trace": _portable_path(trace_path, root),
                    "result": result,
                }
                if examples_dir is not None and method == "improved":
                    directory = examples_dir / case["name"] / mode
                    write_json(directory / "input.json", case)
                    write_json(directory / "output.json", result)
                    write_json(directory / "trace.json", agent.trace)
            rows.append(row)
        recalls = [r["recall_at_5"] for r in rows if r["recall_at_5"] is not None]
        metrics = {"recall_at_5": mean(recalls) if recalls else None}
        if not retrieval_only:
            conflict = [r for r in rows if r["expected_status"] == "CONFLICT"]
            citation_count = sum(r["citation_count"] for r in rows)
            metrics |= {
                "status_accuracy": mean(r["status_correct"] for r in rows),
                "conflict_detection_rate": mean(
                    r["status"] == "CONFLICT" for r in conflict
                )
                if conflict
                else None,
                "citation_validity_rate": sum(r["valid_citations"] for r in rows)
                / citation_count
                if citation_count
                else None,
                "unsupported_answer_rate_proxy": mean(
                    r["unsupported_answer"] for r in rows
                ),
                "fact_regression_pass_rate": mean(r["fact_checks_pass"] for r in rows),
                "mean_tool_calls": mean(r["tool_calls"] for r in rows),
                "mean_duration_ms": mean(r["duration_ms"] for r in rows),
            }
        reports[method] = {"metrics": metrics, "cases": rows}
    report = {
        "mode": "retrieval-only" if retrieval_only else mode,
        "case_count": len(cases),
        "cases_file": _portable_path(cases_path, root),
        "limitations": "Mock state metrics are harness checks, not LLM capability. Citation validity is provenance only; unsupported-answer rate is a fixture proxy, not complete semantic support assessment. Recall excludes empty relevance sets.",
        "reports": reports,
    }
    write_json(output, report)
    return report


def _portable_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
