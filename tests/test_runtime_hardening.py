import hashlib
import json
from types import SimpleNamespace

from src.agent import Agent
from src.evidence import EvidenceValidator
from src.model import LiveModel, ScriptedModel, final_payload
from src.retriever import Corpus, Retriever
from src.tools import ToolDispatcher
from src.trace import write_json
from .conftest import cite, final, read, search


def test_known_document_must_not_hide_conflict_in_unread_section(root, tmp_path):
    docs = [
        json.loads(s)
        for s in (root / "data/documents.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    docs[1]["sections"].insert(0, {"span_id": "intro", "text": "关于本文的说明。"})
    path = tmp_path / "documents.jsonl"
    path.write_text("\n".join(json.dumps(d) for d in docs), encoding="utf-8")
    tools = ToolDispatcher(Corpus(path))
    tools.dispatch(
        "search_docs", {"query": "报销期限", "top_k": 5, "purpose": "search"}
    )
    tools.dispatch(
        "read_doc_span", {"doc_id": "D01", "span_id": "s1", "purpose": "read"}
    )
    tools.dispatch(
        "read_doc_span", {"doc_id": "D02", "span_id": "intro", "purpose": "read"}
    )
    errors = EvidenceValidator(tools).validate(
        final_payload("ANSWERED", "30天", [cite()])
    )
    assert any("unchecked sections: s1" in e for e in errors)


def test_minimax_continuation_and_usage_never_leak_in_trace(monkeypatch, corpus):
    responses = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=None,
                        reasoning_content="PRIVATE_REASONING_MARKER",
                        tool_calls=[
                            SimpleNamespace(
                                id="provider-call",
                                function=SimpleNamespace(
                                    name="read_doc_span",
                                    arguments=json.dumps(
                                        {
                                            "doc_id": "D01",
                                            "span_id": "s1",
                                            "purpose": "read",
                                        }
                                    ),
                                ),
                            )
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
            usage=SimpleNamespace(
                model_dump=lambda **kw: {
                    "total_tokens": 30,
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                }
            ),
            model="MiniMax-M3.1-Flash",
            id="response-1",
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=final().content,
                        reasoning_content="PRIVATE_REASONING_MARKER",
                        tool_calls=[],
                    ),
                    finish_reason="stop",
                )
            ],
            usage=None,
            model="MiniMax-M3.1-Flash",
            id="response-2",
        ),
    ]
    captured = []

    class Client:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            captured.append(kwargs)
            return responses.pop(0)

    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setenv("MODEL_NAME", "MiniMax-M3.1-Flash")
    monkeypatch.setenv("MODEL_PROVIDER", "minimax")
    monkeypatch.setenv("MODEL_JSON_MODE", "off")
    monkeypatch.setattr("openai.OpenAI", Client)
    agent = Agent(LiveModel(), corpus, final_review=False)
    assert agent.run("报销期限")["status"] == "ANSWERED"
    assert any(
        m.get("reasoning_content") == "PRIVATE_REASONING_MARKER"
        for m in captured[1]["messages"]
    )
    assert "PRIVATE_REASONING_MARKER" not in json.dumps(agent.trace)
    assert "response_format" not in captured[0]
    assert captured[0]["extra_body"] == {"reasoning_split": True}
    assert agent.trace["token_usage"]["total_tokens"] == 30


def test_prompt_version_and_budget_are_observable(corpus):
    model = ScriptedModel([search(), read(), final()])
    agent = Agent(model, corpus, system_prompt="custom-system")
    assert agent.run("报销期限")["status"] == "ANSWERED"
    assert model.messages_seen[0][0]["content"] == "custom-system"
    observation = json.loads(model.messages_seen[1][-1]["content"])
    assert observation["runtime_budget"] == {
        "model_steps_remaining": 7,
        "tool_calls_remaining": 9,
    }
    assert agent.trace["prompt_sha256"] == hashlib.sha256(b"custom-system").hexdigest()


def test_doc_id_adjacent_to_chinese_is_exact(corpus):
    assert Retriever(corpus).search("查D01的规定")[0]["ranking"]["rrf_score"] >= 1
    assert not any(
        h["doc_id"] == "D01" and h["ranking"]["rrf_score"] >= 1
        for h in Retriever(corpus).search("D010")
    )


def test_json_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "result.json"
    write_json(path, {"round": 1})
    write_json(path, {"round": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"round": 2}
    assert list(tmp_path.glob("*.tmp-*")) == []


def test_same_agent_final_review_can_revise_status(corpus):
    initial = final()
    revised = final(
        "NEEDS_CLARIFICATION",
        "请确认适用部门。",
        [],
        ["员工所属部门"],
        "你属于哪个部门？",
    )
    model = ScriptedModel([search(), read(), initial, revised])
    agent = Agent(model, corpus, final_review=True)
    result = agent.run("报销期限")
    assert result["status"] == "NEEDS_CLARIFICATION"
    assert result["task_state"]["model_calls"] == 4
    assert any(e["type"] == "final_review" for e in agent.trace["events"])
    assert "final_review" in model.messages_seen[-1][-1]["content"]


def test_review_cannot_bypass_model_budget(corpus):
    model = ScriptedModel([search(), read(), final()])
    agent = Agent(model, corpus, max_model_steps=3, final_review=True)
    assert agent.run("报销期限")["status"] == "LIMIT_REACHED"
