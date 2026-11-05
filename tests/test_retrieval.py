import json

import pytest

from src.retriever import Corpus, Retriever
from src.tools import ToolDispatcher


@pytest.mark.parametrize(
    "query,expected",
    [
        ("报销期限", "D01"),
        ("花钱之后最晚隔多久得把报销单交上去？", "D01"),
        ("VPN远程访问申请", "D07"),
        ("产品项目的编辑权限", "D08"),
        ("D09", "D09"),
        ("公司配的电脑丢了怎么办？", "D10"),
    ],
)
def test_recall(corpus, query, expected):
    assert expected in {h["doc_id"] for h in Retriever(corpus).search(query)}


def test_expansion_and_metadata(root):
    retriever = Retriever(Corpus(root / "data"))
    hits = retriever.search("费用报销管理办法", 2)
    assert {h["doc_id"] for h in hits} == {"D01", "D02"}
    assert {r["doc_id"] for r in hits[0]["related_documents"]} == {"D01", "D02"}
    assert all(
        {"version_date", "scope", "rank", "ranking", "preview"} <= h.keys()
        for h in hits
    )


def test_unrelated_and_baseline(corpus):
    for method in ("baseline", "improved"):
        r = Retriever(corpus, method)
        assert not r.search("火星基地宠物托管补贴")
        assert not r.search("公司在火星基地的宠物托管补贴标准是多少？")
        assert not r.search("的了呢吗")
        assert r.search("D01")[0]["doc_id"] == "D01"


def test_ngram_boundaries_and_paraphrase_rank(corpus):
    from src.retriever import ngrams

    assert "单交" not in ngrams("申请单、交通")
    assert (
        Retriever(corpus).search("花钱之后最晚隔多久得把报销单交上去？")[0]["doc_id"]
        == "D01"
    )


@pytest.mark.parametrize(
    "name,args,code",
    [
        ("fake", {}, "UNKNOWN_TOOL"),
        ("search_docs", "{", "INVALID_JSON"),
        ("search_docs", [], "INVALID_ARGUMENTS"),
        (
            "search_docs",
            {"query": "报销", "purpose": "test", "top_k": True},
            "INVALID_ARGUMENTS",
        ),
        (
            "search_docs",
            {"query": "报销", "purpose": "test", "top_k": 9},
            "INVALID_ARGUMENTS",
        ),
        (
            "read_doc_span",
            {"doc_id": "D404", "span_id": "s1", "purpose": "test"},
            "NOT_FOUND",
        ),
    ],
)
def test_dispatch_errors(corpus, name, args, code):
    result = ToolDispatcher(corpus).dispatch(name, args)
    assert not result["ok"] and result["error"]["code"] == code


def test_finite_failure_injection(corpus):
    tools = ToolDispatcher(corpus, fail_tool="read_doc_span", fail_count=2)
    args = {"doc_id": "D01", "span_id": "s1", "purpose": "test"}
    assert not tools.dispatch("read_doc_span", args)["ok"]
    assert not tools.dispatch("read_doc_span", args)["ok"]
    assert tools.dispatch("read_doc_span", args)["ok"]
    assert tools.errors == 2


def test_unexpected_search_exception_is_structured(corpus, monkeypatch):
    tools = ToolDispatcher(corpus)

    def broken(*args):
        raise RuntimeError("do not expose provider secrets")

    monkeypatch.setattr(tools.retriever, "search", broken)
    result = tools.dispatch(
        "search_docs", {"query": "VPN", "top_k": 5, "purpose": "test"}
    )
    assert result["error"]["code"] == "TOOL_EXCEPTION"
    assert "secrets" not in json.dumps(result)


def test_malformed_corpus_after_loading(tmp_path, corpus):
    path = tmp_path / "documents.jsonl"
    path.write_bytes(corpus.path.read_bytes())
    tools = ToolDispatcher(Corpus(path))
    path.write_text("broken JSON", encoding="utf-8")
    result = tools.dispatch(
        "read_doc_span", {"doc_id": "D01", "span_id": "s1", "purpose": "test"}
    )
    assert result["error"]["code"] == "DATA_ERROR"


def test_duplicate_documents_rejected(tmp_path, corpus):
    d = next(iter(corpus.docs.values()))
    p = tmp_path / "documents.jsonl"
    p.write_text(json.dumps(d) + "\n" + json.dumps(d), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        Corpus(p)


def test_cyclic_version_graph_rejected(tmp_path, corpus):
    d = dict(next(iter(corpus.docs.values())))
    d["supersedes"] = [d["doc_id"]]
    p = tmp_path / "documents.jsonl"
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ValueError, match="Cyclic"):
        Corpus(p)
