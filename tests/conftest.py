import json
from pathlib import Path

import pytest

from src.model import ModelReply, ToolCall, final_payload
from src.retriever import Corpus

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def root():
    return ROOT


@pytest.fixture
def corpus():
    return Corpus(ROOT / "data/scenarios/normal")


def call(name, **args):
    return ModelReply(tool_calls=[ToolCall(name, json.dumps(args, ensure_ascii=False))])


def search(query="报销期限", top_k=5):
    return call("search_docs", query=query, top_k=top_k, purpose="测试检索")


def read(doc_id="D01", span_id="s1"):
    return call("read_doc_span", doc_id=doc_id, span_id=span_id, purpose="测试读取")


def cite(
    doc_id="D01", quote="员工应在费用发生后30天内提交报销申请。", version="2026-01-10"
):
    return {"doc_id": doc_id, "span_id": "s1", "version_date": version, "quote": quote}


def final(
    status="ANSWERED",
    answer="应在30天内提交。",
    citations=None,
    missing=None,
    question=None,
):
    return ModelReply(
        json.dumps(
            final_payload(
                status,
                answer,
                [cite()] if citations is None else citations,
                missing,
                question,
            ),
            ensure_ascii=False,
        )
    )
