import json

from src.agent import Agent
from src.evidence import EvidenceValidator
from src.model import MockModel, final_payload
from src.retriever import Corpus, Retriever
from src.tools import ToolDispatcher
from .conftest import cite


def save(path, docs):
    path.write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in docs), encoding="utf-8"
    )


def test_replace_after_initial_run_uses_runtime_data(tmp_path, corpus):
    path = tmp_path / "documents.jsonl"
    path.write_bytes(corpus.path.read_bytes())
    current = Corpus(path)
    agent = Agent(MockModel(), current)
    assert "30天" in agent.run("报销期限")["answer"]
    docs = list(current.docs.values())
    docs[0]["sections"][0]["text"] = "员工应在费用发生后45天内提交报销申请。"
    save(path, docs)
    final = agent.run("报销期限")
    assert "45天" in final["answer"] and "30天" not in final["answer"]
    assert "45天" in final["citations"][0]["quote"]


def test_delete_competitor_after_conflict(tmp_path, root):
    path = tmp_path / "documents.jsonl"
    path.write_bytes((root / "data/documents.jsonl").read_bytes())
    corpus = Corpus(path)
    agent = Agent(MockModel(), corpus)
    assert agent.run("报销期限")["status"] == "CONFLICT"
    save(path, [d for d in corpus.docs.values() if d["doc_id"] != "D02"])
    result = agent.run("报销期限")
    assert result["status"] == "ANSWERED" and "30天" in result["answer"]
    assert all(c["doc_id"] != "D02" for c in result["citations"])


def test_same_version_text_changed_requires_new_read(tmp_path, corpus):
    path = tmp_path / "documents.jsonl"
    path.write_bytes(corpus.path.read_bytes())
    tools = ToolDispatcher(Corpus(path))
    tools.dispatch(
        "read_doc_span", {"doc_id": "D01", "span_id": "s1", "purpose": "read"}
    )
    docs = list(tools.corpus.docs.values())
    # The quoted substring survives; provenance still must be refreshed.
    docs[0]["sections"][0]["text"] += "逾期须另行申请。"
    save(path, docs)
    assert EvidenceValidator(tools).validate(
        final_payload("ANSWERED", "30天", [cite()])
    )


def test_index_refresh_on_disk_change(tmp_path, corpus):
    path = tmp_path / "documents.jsonl"
    path.write_bytes(corpus.path.read_bytes())
    current = Corpus(path)
    retriever = Retriever(current)
    assert retriever.search("D01")[0]["doc_id"] == "D01"
    save(path, [d for d in current.docs.values() if d["doc_id"] != "D01"])
    assert not retriever.search("D01")
