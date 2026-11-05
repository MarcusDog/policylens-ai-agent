"""Validated dispatcher; errors are observations returned to the model."""

from __future__ import annotations

import json

from .retriever import Corpus, Retriever


def tool_spec(name: str, description: str, properties: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        },
    }


TOOLS = [
    tool_spec(
        "search_docs",
        "检索当前企业文档，预览不是正式引用证据。related_documents 是同主题待核查候选，不能据此断言冲突。",
        {
            "query": {"type": "string", "description": "检索关键词或精确文档 ID"},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 8},
            "purpose": {
                "type": "string",
                "description": "简短可观察行动目的，不写内部推理",
            },
        },
    ),
    tool_spec(
        "read_doc_span",
        "读取当前磁盘上的原文与版本元数据，正式引用必须先读取。",
        {
            "doc_id": {"type": "string"},
            "span_id": {"type": "string"},
            "purpose": {"type": "string"},
        },
    ),
]


def error(code: str, message: str, retryable: bool = False) -> dict:
    return {
        "ok": False,
        "error": {"code": code, "message": message, "retryable": retryable},
    }


class ToolDispatcher:
    def __init__(
        self,
        corpus: Corpus,
        method: str = "improved",
        fail_tool: str | None = None,
        fail_count: int = 0,
    ):
        if (
            fail_tool not in {None, "search_docs", "read_doc_span"}
            or type(fail_count) is not int
            or fail_count < 0
        ):
            raise ValueError("Invalid fault injection")
        self.corpus, self.retriever = corpus, Retriever(corpus, method)
        self.fail_tool, self.fail_remaining = fail_tool, fail_count
        self.reads: dict[tuple[str, str], dict] = {}
        self.discovered: dict[str, set[str]] = {}
        self.errors = 0
        self.successful_searches = 0
        self.observed_digest: str | None = None

    def dispatch(self, name: str, arguments: str | dict) -> dict:
        result = self._dispatch(name, arguments)
        if not result["ok"]:
            self.errors += 1
        return result

    def _dispatch(self, name: str, arguments: str | dict) -> dict:
        if name not in {"search_docs", "read_doc_span"}:
            return error("UNKNOWN_TOOL", "Unknown tool name")
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
        except (json.JSONDecodeError, TypeError):
            return error("INVALID_JSON", "Tool arguments must be a JSON object")
        keys = (
            {"query", "top_k", "purpose"}
            if name == "search_docs"
            else {"doc_id", "span_id", "purpose"}
        )
        if not isinstance(args, dict) or set(args) != keys:
            return error(
                "INVALID_ARGUMENTS", "Required fields: " + ", ".join(sorted(keys))
            )
        strings = keys - {"top_k"}
        if any(
            not isinstance(args[k], str) or not args[k].strip() or len(args[k]) > 4000
            for k in strings
        ):
            return error(
                "INVALID_ARGUMENTS",
                "Expected nonempty strings of at most 4000 characters",
            )
        if name == "search_docs" and (
            type(args["top_k"]) is not int or not 1 <= args["top_k"] <= 8
        ):
            return error("INVALID_ARGUMENTS", "top_k must be an integer in [1, 8]")
        if self.fail_tool == name and self.fail_remaining:
            self.fail_remaining -= 1
            return error("INJECTED_FAILURE", "Injected tool failure", True)
        try:
            self.corpus.refresh()
            if name == "search_docs":
                hits = self.retriever.search(args["query"], args["top_k"])
                for hit in hits:
                    self.discovered.setdefault(hit["topic"], set()).add(hit["doc_id"])
                    self.discovered[hit["topic"]].update(
                        d["doc_id"] for d in hit["related_documents"]
                    )
                self.successful_searches += 1
                self.observed_digest = self.corpus.digest
                return {
                    "ok": True,
                    "data": {
                        "hits": hits,
                        "corpus_digest": self.corpus.digest,
                        "method": self.retriever.method,
                    },
                }
            span = self.corpus.get_span(args["doc_id"], args["span_id"])
            self.reads[(args["doc_id"], args["span_id"])] = dict(span)
            self.observed_digest = self.corpus.digest
            related = []
            if self.retriever.method == "improved":
                related = [
                    {
                        k: d[k]
                        for k in (
                            "doc_id",
                            "title",
                            "scope",
                            "version_date",
                            "supersedes",
                        )
                    }
                    | {"span_ids": [s["span_id"] for s in d["sections"]]}
                    for d in self.corpus.docs.values()
                    if d["topic"] == span["topic"]
                ]
                self.discovered.setdefault(span["topic"], set()).update(
                    d["doc_id"] for d in related
                )
            return {
                "ok": True,
                "data": span
                | {"corpus_digest": self.corpus.digest, "related_documents": related},
            }
        except KeyError:
            return error("NOT_FOUND", "Document or span no longer exists")
        except (OSError, ValueError, TypeError):
            return error("DATA_ERROR", "Corpus cannot be read or is malformed")
        except Exception:
            return error(
                "TOOL_EXCEPTION", "Unexpected tool failure; no evidence was read"
            )
