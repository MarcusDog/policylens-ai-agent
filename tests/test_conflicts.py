from src.agent import Agent
from src.evidence import EvidenceValidator
from src.model import MockModel, ScriptedModel, final_payload
from src.retriever import Corpus
from src.tools import ToolDispatcher
from .conftest import cite, final, read, search


def test_conflicting_sources_require_both_reads(root):
    corpus = Corpus(root / "data")
    model = ScriptedModel(
        [
            search(),
            read(),
            final(),
            read("D02"),
            final(
                "CONFLICT",
                "相同范围分别规定30天和15天，未明确优先级。",
                [
                    cite(),
                    cite("D02", "员工应在费用发生后15天内提交报销申请。", "2026-03-01"),
                ],
                ["生效优先级"],
                "请财务确认哪个制度有效？",
            ),
        ]
    )
    agent = Agent(model, corpus)
    result = agent.run("报销期限")
    assert result["status"] == "CONFLICT"
    assert {c["doc_id"] for c in result["citations"]} == {"D01", "D02"}
    assert any(
        "D02" in str(e.get("errors"))
        for e in agent.trace["events"]
        if e["type"] == "validation"
    )


def test_different_scopes_request_clarification(root):
    result = Agent(MockModel(), Corpus(root / "data/scenarios/scope")).run("报销期限")
    assert result["status"] == "NEEDS_CLARIFICATION"
    assert (
        result["clarification_question"] and "部门" in result["clarification_question"]
    )


def test_explicit_supersedes(root):
    result = Agent(MockModel(), Corpus(root / "data/scenarios/supersedes")).run(
        "报销期限"
    )
    assert result["status"] == "ANSWERED"
    assert "15天" in result["answer"] and "30天" not in result["answer"]
    assert {c["doc_id"] for c in result["citations"]} == {"D02"}


def test_single_source_does_not_force_conflict(corpus):
    result = Agent(MockModel(), corpus).run("报销期限")
    assert result["status"] == "ANSWERED" and "30天" in result["answer"]


def test_same_topic_not_automatically_conflict(tmp_path, corpus):
    import json

    docs = list(corpus.docs.values())
    newer = dict(docs[0], doc_id="COMPATIBLE", version_date="2026-07-01")
    docs.append(newer)
    path = tmp_path / "documents.jsonl"
    path.write_text("\n".join(json.dumps(d) for d in docs), encoding="utf-8")
    result = Agent(MockModel(), Corpus(path)).run("报销期限")
    assert result["status"] == "ANSWERED"


def test_guard_sees_candidates_outside_top_k(root):
    tools = ToolDispatcher(Corpus(root / "data"))
    tools.dispatch("search_docs", {"query": "报销期限", "top_k": 1, "purpose": "check"})
    tools.dispatch(
        "read_doc_span", {"doc_id": "D01", "span_id": "s1", "purpose": "check"}
    )
    errors = EvidenceValidator(tools).validate(
        final_payload("ANSWERED", "30天", [cite()])
    )
    assert any("D02" in e for e in errors)
