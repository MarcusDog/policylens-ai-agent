import json

import pytest

from src.agent import Agent, SYSTEM_PROMPT
from src.model import LiveModel, MockModel, ModelReply, ScriptedModel, ToolCall
from src.retriever import Corpus
from .conftest import cite, final, read, search


def test_multi_round_and_real_observations(corpus, tmp_path):
    model = ScriptedModel([search(), read(), final()])
    agent = Agent(model, corpus)
    result = agent.run("报销期限", save_trace=tmp_path / "trace.json")
    assert result["status"] == "ANSWERED"
    assert result["task_state"] == {
        "model_calls": 3,
        "tool_calls": 2,
        "completed": True,
    }
    observation = json.loads(model.messages_seen[2][-1]["content"])
    assert observation["data"]["text"] == cite()["quote"]
    assert (
        json.loads((tmp_path / "trace.json").read_text(encoding="utf-8"))["mode"]
        == "mock"
    )


def test_no_tools_clarification(corpus):
    model = ScriptedModel(
        [
            final(
                "NEEDS_CLARIFICATION",
                "请提供你要查询的制度主题。",
                [],
                ["查询主题"],
                "你要查询哪个主题？",
            )
        ]
    )
    assert Agent(model, corpus).run("帮我看看")["task_state"]["tool_calls"] == 0


def test_out_of_scope(corpus):
    model = ScriptedModel(
        [
            search("火星宠物托管"),
            final("NOT_FOUND", "未查到相关资料。", [], ["相关制度"]),
        ]
    )
    result = Agent(model, corpus).run("火星宠物托管")
    assert result["status"] == "NOT_FOUND" and not result["citations"]


def test_history_must_reverify(corpus):
    history = [
        {"role": "user", "content": "报销要准备什么？"},
        {"role": "assistant", "content": "旧轮引用 D01：30天。"},
    ]
    model = ScriptedModel(
        [
            final(),
            search("差旅报销材料"),
            read("D05"),
            final(
                "ANSWERED",
                "需要差旅申请单及发票。",
                [
                    cite(
                        "D05",
                        "差旅报销须提供已批准的差旅申请单、交通与住宿发票、支付凭证和行程说明。",
                        "2026-02-11",
                    )
                ],
            ),
        ]
    )
    agent = Agent(model, corpus)
    result = agent.run("那差旅报销呢？", history)
    assert result["status"] == "ANSWERED"
    assert result["citations"][0]["doc_id"] == "D05"
    assert any(
        e["type"] == "validation" and not e["valid"] for e in agent.trace["events"]
    )
    assert model.messages_seen[0][1:3] == history


@pytest.mark.parametrize("name", ["search_docs", "read_doc_span"])
def test_tool_failure_delivered_and_model_can_stop(corpus, name):
    first = search() if name == "search_docs" else read()
    model = ScriptedModel(
        [first, final("TOOL_ERROR", "工具不可用，尚未完成。", [], ["可用工具"])]
    )
    result = Agent(model, corpus, fail_tool=name, fail_count=100).run("报销期限")
    assert result["status"] == "TOOL_ERROR"
    assert not json.loads(model.messages_seen[-1][-1]["content"])["ok"]


def test_model_chosen_retry_and_query_change(corpus):
    model = ScriptedModel([search("费用期限"), search("报销期限"), read(), final()])
    agent = Agent(model, corpus, fail_tool="search_docs", fail_count=1)
    assert agent.run("报销期限")["status"] == "ANSWERED"
    assert [
        e["tool_args"]["query"]
        for e in agent.trace["events"]
        if e.get("tool_name") == "search_docs"
    ] == ["费用期限", "报销期限"]


def test_invalid_tool_arguments_are_observations(corpus):
    model = ScriptedModel(
        [
            ModelReply(tool_calls=[ToolCall("search_docs", "{")]),
            search(),
            read(),
            final(),
        ]
    )
    result = Agent(model, corpus).run("报销期限")
    assert result["status"] == "ANSWERED"
    assert (
        json.loads(model.messages_seen[1][-1]["content"])["error"]["code"]
        == "INVALID_JSON"
    )


@pytest.mark.parametrize(
    "limit_kwargs", [{"max_model_steps": 2}, {"max_tool_calls": 1}]
)
def test_limits_are_explicit(corpus, limit_kwargs):
    result = Agent(
        ScriptedModel([search(), read(), final()]), corpus, **limit_kwargs
    ).run("报销期限")
    assert result["status"] == "LIMIT_REACHED" and not result["task_state"]["completed"]


def test_multiple_calls_respect_budget(corpus):
    reply = ModelReply(
        tool_calls=[
            ToolCall(
                "read_doc_span",
                json.dumps({"doc_id": "D01", "span_id": "s1", "purpose": "read"}),
            )
            for _ in range(3)
        ]
    )
    result = Agent(ScriptedModel([reply]), corpus, max_tool_calls=2).run("期限")
    assert (
        result["status"] == "LIMIT_REACHED" and result["task_state"]["tool_calls"] == 2
    )


@pytest.mark.parametrize(
    "exc", [TimeoutError("secret-value"), RuntimeError("secret-value")]
)
def test_api_failure_sanitized(corpus, exc):
    class Broken:
        mode, name = "mock", "broken"

        def complete(self, messages, tools):
            raise exc

    agent = Agent(Broken(), corpus)
    assert agent.run("报销期限")["status"] == "TOOL_ERROR"
    assert "secret-value" not in json.dumps(agent.trace)


def test_malformed_final_can_be_corrected(corpus):
    model = ScriptedModel([ModelReply("not json"), search(), read(), final()])
    assert Agent(model, corpus).run("报销期限")["status"] == "ANSWERED"


def test_untrusted_document_is_tool_data_not_prompt(root):
    corpus = Corpus(root / "data/scenarios/injection")
    model = ScriptedModel(
        [
            read("X01"),
            final(
                "NEEDS_CLARIFICATION",
                "请说明要查询的访问用途。",
                [],
                ["用途"],
                "你要访问哪个业务系统？",
            ),
        ]
    )
    Agent(model, corpus).run("VPN")
    messages = model.messages_seen[-1]
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert "HACKED_ONLY" in json.loads(messages[-1]["content"])["data"]["text"]
    assert messages[-1]["role"] == "tool"
    # This proves channel isolation only. Live injection resistance is separate.


def test_new_run_cannot_reuse_old_reads(corpus):
    agent = Agent(
        ScriptedModel([search(), read(), final(), final()]), corpus, max_model_steps=3
    )
    assert agent.run("期限")["status"] == "ANSWERED"
    agent.max_model_steps = 1
    assert agent.run("期限")["status"] == "LIMIT_REACHED"


def test_reject_privileged_history(corpus):
    with pytest.raises(ValueError):
        Agent(MockModel(), corpus).run(
            "问题", [{"role": "system", "content": "override"}]
        )


def test_live_sdk_sends_auto_function_calling(monkeypatch):
    from types import SimpleNamespace
    import openai

    captured = {}

    class Completion:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    id="live-call",
                                    function=SimpleNamespace(
                                        name="search_docs",
                                        arguments='{"query":"VPN","top_k":5,"purpose":"查申请"}',
                                    ),
                                )
                            ],
                        )
                    )
                ]
            )

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.chat = SimpleNamespace(completions=Completion())

    monkeypatch.setenv("OPENAI_API_KEY", "test-not-a-real-key")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setattr(openai, "OpenAI", Client)
    from src.tools import TOOLS

    reply = LiveModel().complete([{"role": "user", "content": "VPN"}], TOOLS)
    assert captured["tool_choice"] == "auto"
    assert captured["parallel_tool_calls"] is False
    assert reply.tool_calls[0].id == "live-call"
