"""Paired, reproducible metrics; missing Live data is never replaced by Mock."""

from __future__ import annotations

import json
import hashlib
import re
import time
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
    spans = {(c["doc_id"], c.get("span_id")) for c in result["citations"]}
    obligations_pass = all(
        not re.search(rule["trigger_pattern"], answer)
        or any(
            re.search(rule["quote_pattern"], citation["quote"])
            for citation in result["citations"]
        )
        for rule in case.get("citation_obligations", [])
    )
    return {
        "status_correct": result["status"] == case["expected_status"],
        # These small regression checks are semantic proxies, not an LLM judge.
        "fact_checks_pass": all(x in answer for x in case.get("required_facts", []))
        and not any(x in answer for x in case.get("forbidden_facts", []))
        and all(
            re.search(pattern, answer) for pattern in case.get("required_patterns", [])
        )
        and not any(
            re.search(pattern, answer) for pattern in case.get("forbidden_patterns", [])
        )
        and obligations_pass,
        "citation_expectations_pass": set(case.get("required_citations", [])) <= ids
        and not (set(case.get("forbidden_citations", [])) & ids)
        and set(map(tuple, case.get("required_spans", []))) <= spans,
        "clarification_checks_pass": all(
            re.search(pattern, result.get("clarification_question") or "")
            for pattern in case.get("clarification_patterns", [])
        ),
    }


def evaluate(
    cases_path: Path,
    root: Path,
    mode: str,
    output: Path,
    retrieval_only: bool = False,
    examples_dir: Path | None = None,
    *,
    system_prompt: str | None = None,
    methods: tuple[str, ...] = ("baseline", "improved"),
    progress=None,
    final_review: bool | None = None,
    case_delay_seconds: float = 0,
) -> dict:
    cases = read_cases(cases_path)
    if (
        not cases
        or mode not in {"live", "mock"}
        or not methods
        or any(m not in {"baseline", "improved"} for m in methods)
    ):
        raise ValueError("Nonempty cases, valid mode and retrieval methods required")
    reports = {}
    for method in methods:
        rows = []
        for case in cases:
            if case_delay_seconds:
                time.sleep(min(max(case_delay_seconds, 0), 30))
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
                    max_model_steps=case.get("max_model_steps", 8),
                    max_tool_calls=case.get("max_tool_calls", 10),
                    system_prompt=system_prompt,
                    final_review=final_review,
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
                    "model_calls": result["task_state"]["model_calls"],
                    "token_usage": agent.trace["token_usage"],
                    "prompt_sha256": agent.trace["prompt_sha256"],
                    "corpus_digest": agent.trace["corpus_digest"],
                    "api_errors": [
                        e["error_type"]
                        for e in agent.trace["events"]
                        if e["type"] == "model_error"
                    ],
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
            if progress:
                progress(
                    {
                        "mode": mode,
                        "method": method,
                        "case_id": case["id"],
                        "status": row.get("status", "RETRIEVED"),
                    }
                )
            write_json(
                output,
                {
                    "mode": "retrieval-only" if retrieval_only else mode,
                    "complete": False,
                    "reports": reports | {method: {"cases": rows}},
                    "case_count": len(cases),
                },
            )
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
                "mean_model_calls": mean(r["model_calls"] for r in rows),
                "mean_total_tokens": mean(
                    r["token_usage"]["total_tokens"] for r in rows
                ),
                "case_pass_rate": mean(
                    r["status_correct"]
                    and r["fact_checks_pass"]
                    and r["citation_expectations_pass"]
                    and r["clarification_checks_pass"]
                    for r in rows
                ),
                "api_error_rate": mean(bool(r["api_errors"]) for r in rows),
                "mean_duration_ms": mean(r["duration_ms"] for r in rows),
            }
        reports[method] = {"metrics": metrics, "cases": rows}
    report = {
        "mode": "retrieval-only" if retrieval_only else mode,
        "complete": True,
        "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
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
