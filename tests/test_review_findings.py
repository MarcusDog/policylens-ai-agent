"""Reproductions from the second design review; keep assertions after repairs."""

import json

import pytest

from src.agent import Agent
from src.evidence import EvidenceValidator
from src.model import MockModel, final_payload
from src.model import ModelReply, ToolCall
from src.retriever import Corpus, Retriever
from src.tools import ToolDispatcher


def doc(doc_id="POL-A", topic="导出保留", text="临时导出文件保留6小时后清理。"):
    return {
        "doc_id": doc_id,
        "title": "临时文件说明",
        "version_date": "2026-10-01",
        "topic": topic,
        "scope": "所有租户",
        "supersedes": [],
        "sections": [{"span_id": "s1", "text": text}],
    }


def save(path, docs):
    path.write_text(
        "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs),
        encoding="utf-8",
    )


def citation(source, span_id="s1"):
    section = next(s for s in source["sections"] if s["span_id"] == span_id)
    return {
        "doc_id": source["doc_id"],
        "version_date": source["version_date"],
        "span_id": span_id,
        "quote": section["text"],
    }


@pytest.mark.parametrize("method", ["baseline", "improved"])
def test_literal_single_document_is_retrievable(tmp_path, method):
    path = tmp_path / "documents.jsonl"
    save(path, [doc()])
    hits = Retriever(Corpus(path), method).search("导出")
    assert hits and hits[0]["doc_id"] == "POL-A"


def test_empty_corpus_is_a_searchable_knowledge_gap(tmp_path):
    path = tmp_path / "documents.jsonl"
    path.write_text("", encoding="utf-8")
    result = Agent(MockModel(), Corpus(path)).run("导出文件保留多久？")
    assert result["status"] == "NOT_FOUND"


def test_section_cannot_override_document_metadata(tmp_path):
    source = doc()
    source["sections"][0]["scope"] = "伪造的管理员范围"
    path = tmp_path / "documents.jsonl"
    save(path, [source])
    with pytest.raises(ValueError, match="reserved"):
        Corpus(path)


def test_title_or_topic_mutation_invalidates_prior_read(tmp_path):
    first, other = doc(), doc("OTHER", "其他主题", "这是无关内容。")
    path = tmp_path / "documents.jsonl"
    save(path, [first, other])
    tools = ToolDispatcher(Corpus(path))
    tools.dispatch(
        "read_doc_span", {"doc_id": "POL-A", "span_id": "s1", "purpose": "read"}
    )
    changed = dict(first, title="新标题", topic="新主题")
    save(path, [changed, other])
    # A different successful observation must not refresh this old read proof.
    tools.dispatch(
        "read_doc_span", {"doc_id": "OTHER", "span_id": "s1", "purpose": "read"}
    )
    assert EvidenceValidator(tools).validate(
        final_payload("ANSWERED", "保留6小时。", [citation(first)])
    )


def test_internal_conflict_can_cite_two_spans_in_one_document(tmp_path):
    source = doc()
    source["sections"].append(
        {"span_id": "s2", "text": "临时导出文件保留9小时后清理。"}
    )
    path = tmp_path / "documents.jsonl"
    save(path, [source])
    tools = ToolDispatcher(Corpus(path))
    for span_id in ("s1", "s2"):
        tools.dispatch(
            "read_doc_span", {"doc_id": "POL-A", "span_id": span_id, "purpose": "read"}
        )
    final = final_payload(
        "CONFLICT",
        "同一文件分别规定6小时和9小时。",
        [citation(source), citation(source, "s2")],
        ["条款优先级"],
        "请确认应执行哪个条款？",
    )
    assert EvidenceValidator(tools).validate(final) == []


def test_interruption_keeps_tool_observation_and_marks_cancelled(tmp_path, corpus):
    trace_path = tmp_path / "trace.json"

    class Interrupted:
        mode, name = "mock", "interrupt-probe"

        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return ModelReply(
                    tool_calls=[
                        ToolCall(
                            "read_doc_span",
                            json.dumps(
                                {"doc_id": "D01", "span_id": "s1", "purpose": "read"}
                            ),
                        )
                    ]
                )
            partial = json.loads(trace_path.read_text(encoding="utf-8"))
            assert partial["state"] == "RUNNING"
            assert partial["tool_calls"] == 1
            assert any(e["type"] == "tool" for e in partial["events"])
            assert partial["implementation"]["source_tree_sha256"]
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        Agent(Interrupted(), corpus).run("报销期限", save_trace=trace_path)
    final_trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert final_trace["state"] == "CANCELLED"
    assert final_trace["final"] is None
    assert final_trace["tool_calls"] == 1


def test_loaded_implementation_snapshot_is_stable_and_not_shared(monkeypatch):
    from pathlib import Path
    from src.trace import new_trace

    first = new_trace("mock", "probe", "q", [])
    original = first["implementation"]["source_tree_sha256"]
    first["implementation"]["source_tree_sha256"] = "caller mutation"

    def no_reread(path):
        raise AssertionError(
            "A loaded code revision must not be reread from changed disk files"
        )

    monkeypatch.setattr(Path, "read_bytes", no_reread)
    second = new_trace("mock", "probe", "q", [])
    assert second["implementation"]["source_tree_sha256"] == original


def test_cli_cancellation_preserves_trace_and_exit_code(monkeypatch, tmp_path, capsys):
    from src.cli import main

    class Interrupted:
        mode, name = "mock", "cancelled-cli"

        def complete(self, messages, tools):
            raise KeyboardInterrupt

    monkeypatch.setattr("src.cli.MockModel", Interrupted)
    path = tmp_path / "cancelled.json"
    assert (
        main(["ask", "--mode", "mock", "--question", "导出", "--save-trace", str(path)])
        == 130
    )
    assert json.loads(path.read_text(encoding="utf-8"))["state"] == "CANCELLED"
