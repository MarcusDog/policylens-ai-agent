"""Real Chat Completions function calling and an explicitly deterministic mock."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass
class ToolCall:
    name: str
    arguments: str
    id: str = field(default_factory=lambda: "call_" + uuid4().hex[:16])


@dataclass
class ModelReply:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)

    def message(self) -> dict:
        msg: dict = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.arguments},
                }
                for c in self.tool_calls
            ]
        return msg


class LiveModel:
    mode = "live"

    def __init__(self):
        from openai import OpenAI

        if not os.getenv("OPENAI_API_KEY") or not os.getenv("MODEL_NAME"):
            raise ValueError(
                "Live requires OPENAI_API_KEY and MODEL_NAME (environment or --env-file)"
            )
        self.name = os.environ["MODEL_NAME"]
        self.client = OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.getenv("OPENAI_BASE_URL") or None,
            timeout=float(os.getenv("MODEL_TIMEOUT_SECONDS", "45")),
            max_retries=0,
        )

    def complete(self, messages: list[dict], tools: list[dict]) -> ModelReply:
        response = self.client.chat.completions.create(
            model=self.name,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            parallel_tool_calls=False,
            response_format={"type": "json_object"},
        )
        msg = response.choices[0].message
        # Never store reasoning_content or raw SDK response objects.
        return ModelReply(
            msg.content,
            [
                ToolCall(c.function.name, c.function.arguments, c.id)
                for c in msg.tool_calls or []
            ],
        )


def final_payload(
    status: str,
    answer: str,
    citations: list[dict] | None = None,
    missing: list[str] | None = None,
    question: str | None = None,
) -> dict:
    return {
        "status": status,
        "answer": answer,
        "citations": citations or [],
        "missing_information": missing or [],
        "clarification_question": question,
        "task_state": {},
    }


class ScriptedModel:
    """Test-only prescribed replies. Does not implement or prove model reasoning."""

    mode, name = "mock", "scripted-test-double"

    def __init__(self, replies: list[ModelReply]):
        self.replies = iter(replies)
        self.messages_seen: list[list[dict]] = []

    def complete(self, messages: list[dict], tools: list[dict]) -> ModelReply:
        self.messages_seen.append(list(messages))
        return next(self.replies)


class MockModel:
    """Offline protocol harness, NOT an LLM. Only simple synthetic policy patterns.

    Always searches, reads the first topic's candidate spans, then emits a fixture-like
    answer. These fixed rules must never be reported as autonomous Live behavior.
    """

    mode, name = "mock", "deterministic-offline-harness"

    def complete(self, messages: list[dict], tools: list[dict]) -> ModelReply:
        outputs = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
        if not outputs:
            current = messages[-1]["content"]
            earlier = [m["content"] for m in messages[1:-1] if m["role"] == "user"]
            query = current + (
                " " + earlier[-1]
                if earlier and ("那" in current or len(current) < 8)
                else ""
            )
            return self._call(
                "search_docs",
                {
                    "query": query,
                    "top_k": 5,
                    "purpose": "Mock 固定检索步骤（非模型决策）",
                },
            )
        if not outputs[-1]["ok"]:
            return self._final(
                final_payload(
                    "TOOL_ERROR",
                    "工具返回错误，尚不能完成资料核查。",
                    missing=["可用的文档工具结果"],
                )
            )
        search = next(
            (o["data"] for o in outputs if o["ok"] and "hits" in o["data"]),
            {"hits": []},
        )
        hits = search["hits"]
        if not hits:
            return self._final(
                final_payload(
                    "NOT_FOUND",
                    "当前资料中未检索到相关依据。",
                    missing=["相关企业制度或产品说明"],
                )
            )
        topic = hits[0]["topic"]
        candidates = [
            (d["doc_id"], s)
            for h in hits
            if h["topic"] == topic
            for d in h["related_documents"]
            for s in d["span_ids"]
        ]
        candidates += [(h["doc_id"], h["span_id"]) for h in hits if h["topic"] == topic]
        reads = [o["data"] for o in outputs if o["ok"] and "text" in o["data"]]
        seen = {(r["doc_id"], r["span_id"]) for r in reads}
        for doc_id, span_id in dict.fromkeys(candidates):
            if (doc_id, span_id) not in seen:
                return self._call(
                    "read_doc_span",
                    {
                        "doc_id": doc_id,
                        "span_id": span_id,
                        "purpose": "Mock 固定逐条读取候选原文",
                    },
                )
        superseded = {
            old
            for r in reads
            for old in r["supersedes"]
            if any(n["doc_id"] == old and n["scope"] == r["scope"] for n in reads)
        }
        active = [r for r in reads if r["doc_id"] not in superseded]
        scopes = {r["scope"] for r in active}
        # Mock's constrained synthetic-data rules are deliberately separate from Live.
        if len(scopes) > 1:
            return self._final(
                final_payload(
                    "NEEDS_CLARIFICATION",
                    "制度按适用部门区分，需补充部门信息。",
                    self._citations(active),
                    ["员工所属部门"],
                    "你属于哪个部门？",
                )
            )
        deadlines = {
            m.group(1)
            for r in active
            if (m := re.search(r"费用发生后(\d+)天内", r["text"]))
        }
        if len(deadlines) > 1:
            return self._final(
                final_payload(
                    "CONFLICT",
                    "同范围报销期限分别为"
                    + "、".join(sorted(deadlines))
                    + "天；未发现明确替代关系，暂不能确定执行哪项。",
                    self._citations(active),
                    ["制度优先级或明确替代关系"],
                    "请财务确认当前应执行哪一项制度？",
                )
            )
        return self._final(
            final_payload(
                "ANSWERED",
                "适用范围："
                + "、".join(scopes)
                + "。"
                + "\n".join(r["text"] for r in active),
                self._citations(active),
            )
        )

    @staticmethod
    def _call(name: str, args: dict) -> ModelReply:
        return ModelReply(
            tool_calls=[ToolCall(name, json.dumps(args, ensure_ascii=False))]
        )

    @staticmethod
    def _final(value: dict) -> ModelReply:
        return ModelReply(json.dumps(value, ensure_ascii=False))

    @staticmethod
    def _citations(reads: list[dict]) -> list[dict]:
        return [
            {k: r[k] for k in ("doc_id", "version_date", "span_id")}
            | {"quote": r["text"]}
            for r in reads
        ]
