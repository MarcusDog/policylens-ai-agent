"""Additional regression fixtures, independent of the original acceptance set."""

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )


def main():
    docs = [
        json.loads(s)
        for s in (ROOT / "data/documents.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    chain = copy.deepcopy(docs)
    chain[1]["supersedes"] = [chain[0]["doc_id"]]
    latest = copy.deepcopy(chain[1])
    latest.update(
        doc_id="VERSION_NEXT",
        title="费用提交期限修订",
        version_date="2026-08-01",
        supersedes=[chain[1]["doc_id"]],
    )
    latest["sections"][0]["text"] = "员工应在费用发生后7天内提交报销申请。"
    write(ROOT / "data/scenarios/transitive/documents.jsonl", chain + [latest])
    renamed = copy.deepcopy([d for d in docs if d["doc_id"] != "D02"])
    renamed[0].update(doc_id="R-82", version_date="2026-09-01")
    renamed[0]["sections"] = [
        {"span_id": "p9", "text": "员工应在费用发生后77天内提交报销申请。"}
    ]
    write(ROOT / "data/scenarios/renamed/documents.jsonl", renamed)
    # A benign paragraph must not hide a competing rule in another section.
    sections = copy.deepcopy(docs)
    sections[1]["sections"].insert(
        0, {"span_id": "intro", "text": "本文件描述费用提交流程，请核查其适用条款。"}
    )
    write(ROOT / "data/scenarios/multispan/documents.jsonl", sections)
    cases = [
        {
            "id": "C01",
            "name": "scope_known",
            "scenario": "scope",
            "question": "我是研发部员工，报销提交期限是多久？",
            "expected_status": "ANSWERED",
            "relevant_docs": ["D01", "D02"],
            "required_facts": ["30"],
            "required_citations": ["D01"],
        },
        {
            "id": "C02",
            "name": "scope_history",
            "scenario": "scope",
            "question": "那我报销必须几天内提交？",
            "history": [{"role": "user", "content": "我是销售部的新员工。"}],
            "expected_status": "ANSWERED",
            "relevant_docs": ["D01", "D02"],
            "required_facts": ["15"],
            "required_citations": ["D02"],
        },
        {
            "id": "C03",
            "name": "read_failure",
            "scenario": "normal",
            "question": "VPN 应该怎么申请？",
            "expected_status": "TOOL_ERROR",
            "relevant_docs": ["D07"],
            "fail_tool": "read_doc_span",
            "fail_count": 100,
        },
        {
            "id": "C04",
            "name": "search_recovery",
            "scenario": "normal",
            "question": "VPN 应该怎么申请？",
            "expected_status": "ANSWERED",
            "relevant_docs": ["D07"],
            "fail_tool": "search_docs",
            "fail_count": 1,
            "required_facts": ["工单"],
            "required_citations": ["D07"],
        },
        {
            "id": "C05",
            "name": "transitive",
            "scenario": "transitive",
            "question": "报销应按哪份有效制度、在多少天内提交？",
            "expected_status": "ANSWERED",
            "relevant_docs": ["D01", "D02", "VERSION_NEXT"],
            "required_facts": ["7"],
            "required_citations": ["VERSION_NEXT"],
        },
        {
            "id": "C06",
            "name": "renamed",
            "scenario": "renamed",
            "question": "现在费用报销应在发生后几天内提交？",
            "expected_status": "ANSWERED",
            "relevant_docs": ["R-82"],
            "required_facts": ["77"],
            "required_citations": ["R-82"],
            "forbidden_citations": ["D01", "D02"],
        },
        {
            "id": "C07",
            "name": "multispan",
            "scenario": "multispan",
            "question": "报销期限是多久？",
            "expected_status": "CONFLICT",
            "relevant_docs": ["D01", "D02"],
            "required_facts": ["30", "15"],
            "required_citations": ["D01", "D02"],
        },
        {
            "id": "C08",
            "name": "live_limit",
            "scenario": "normal",
            "question": "请查证报销提交期限。",
            "expected_status": "LIMIT_REACHED",
            "relevant_docs": ["D01"],
            "max_model_steps": 1,
        },
        {
            "id": "C09",
            "name": "stale_history",
            "scenario": "mutation",
            "question": "现在报销提交期限是多少天？",
            "history": [
                {"role": "assistant", "content": "先前版本提到30天，引用D01。"}
            ],
            "expected_status": "ANSWERED",
            "relevant_docs": ["D01"],
            "required_facts": ["45"],
            "required_citations": ["D01"],
        },
    ]
    for case in cases:
        case["required_patterns"] = [
            r"(?<!\d)" + f + r"\s*天"
            for f in case.get("required_facts", [])
            if f.isdigit()
        ]
        if case["id"] == "C05":
            case["forbidden_patterns"] = [r"\d{4}-\d{2}-\d{2}\s*起"]
    write(ROOT / "data/challenge_cases.jsonl", cases)


if __name__ == "__main__":
    main()
