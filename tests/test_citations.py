import json

import pytest

from src.agent import Agent
from src.evidence import EvidenceValidator
from src.model import ScriptedModel, final_payload
from src.retriever import Corpus
from src.tools import ToolDispatcher
from .conftest import cite, final, read, search


@pytest.fixture
def checked(corpus):
    tools = ToolDispatcher(corpus)
    tools.dispatch(
        "read_doc_span", {"doc_id": "D01", "span_id": "s1", "purpose": "verify"}
    )
    return tools


def test_valid_quote(checked):
    assert (
        EvidenceValidator(checked).validate(final_payload("ANSWERED", "30天", [cite()]))
        == []
    )


@pytest.mark.parametrize(
    "change",
    [
        {"doc_id": "DELETED"},
        {"span_id": "s404"},
        {"version_date": "2020-01-01"},
        {"quote": "费用发生后45天内"},
        {"quote": ""},
    ],
)
def test_bad_citations_rejected(checked, change):
    assert EvidenceValidator(checked).validate(
        final_payload("ANSWERED", "期限", [cite() | change])
    )


def test_unread_and_no_evidence(corpus):
    validator = EvidenceValidator(ToolDispatcher(corpus))
    assert validator.validate(final_payload("ANSWERED", "30天", [cite()]))
    assert validator.validate(final_payload("ANSWERED", "30天", []))


def test_invalid_then_corrected(corpus):
    model = ScriptedModel(
        [search(), read(), final(citations=[cite() | {"quote": "45天"}]), final()]
    )
    result = Agent(model, corpus).run("报销期限")
    assert result["status"] == "ANSWERED"
    assert result["task_state"]["model_calls"] == 4


def test_invalid_never_repaired_terminates(corpus):
    result = Agent(ScriptedModel([final(), final()]), corpus, max_model_steps=2).run(
        "期限"
    )
    assert result["status"] == "LIMIT_REACHED" and not result["citations"]


def test_provenance_is_not_semantic_entailment(checked):
    wrong = final_payload("ANSWERED", "允许在90天内提交。", [cite()])
    assert not EvidenceValidator(checked).validate(wrong)
    from src.evaluation import check_case

    assert not check_case(
        {
            "expected_status": "ANSWERED",
            "required_facts": ["30"],
            "forbidden_facts": ["90天"],
        },
        wrong,
    )["fact_checks_pass"]


def test_same_process_deleted_doc_cannot_be_cited(tmp_path, corpus):
    path = tmp_path / "documents.jsonl"
    path.write_bytes(corpus.path.read_bytes())
    tools = ToolDispatcher(Corpus(path))
    tools.dispatch(
        "read_doc_span", {"doc_id": "D01", "span_id": "s1", "purpose": "verify"}
    )
    remaining = [d for d in tools.corpus.docs.values() if d["doc_id"] != "D01"]
    path.write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in remaining),
        encoding="utf-8",
    )
    assert EvidenceValidator(tools).validate(
        final_payload("ANSWERED", "30天", [cite()])
    )


@pytest.mark.parametrize("obj", [None, [], {}, {"status": []}])
def test_malformed_output_is_validation_error(checked, obj):
    assert EvidenceValidator(checked).validate(obj)


def test_wrong_status_type_does_not_crash(checked):
    obj = final_payload("ANSWERED", "30天", [cite()])
    obj["status"] = []
    assert EvidenceValidator(checked).validate(obj) == ["Unknown status"]


def test_late_competitor_added_requires_fresh_observation(tmp_path, corpus):
    path = tmp_path / "documents.jsonl"
    path.write_bytes(corpus.path.read_bytes())
    tools = ToolDispatcher(Corpus(path))
    tools.dispatch(
        "read_doc_span", {"doc_id": "D01", "span_id": "s1", "purpose": "read"}
    )
    new_doc = dict(tools.corpus.docs["D01"], doc_id="NEW")
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(new_doc) + "\n")
    assert any(
        "changed" in e
        for e in EvidenceValidator(tools).validate(
            final_payload("ANSWERED", "30天", [cite()])
        )
    )
