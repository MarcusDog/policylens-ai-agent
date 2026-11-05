"""Disk-backed corpus, Chinese BM25 and character n-gram/RRF retrieval."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

jieba.setLogLevel(logging.ERROR)
STOP = {
    "的",
    "了",
    "吗",
    "呢",
    "我",
    "我们",
    "请问",
    "一下",
    "怎么",
    "如何",
    "什么",
    "需要",
    "可以",
    "是",
    "在",
    "有",
    "和",
    "那",
    "要",
    "公司",
    "多少",
}


def tokens(text: str) -> list[str]:
    return [
        t.lower()
        for t in jieba.lcut(text)
        if re.search(r"[\w\u4e00-\u9fff]", t) and t not in STOP
    ]


def ngrams(text: str) -> set[str]:
    # Preserve punctuation/field boundaries: "单、交通" must not create "单交".
    segments = re.findall(r"[\u4e00-\u9fff]+|[a-z0-9_]+", text.lower())
    return {
        segment[i : i + n]
        for segment in segments
        for n in (2, 3)
        for i in range(len(segment) - n + 1)
    }


class Corpus:
    def __init__(self, path: str | Path):
        path = Path(path)
        self.path = path / "documents.jsonl" if path.is_dir() else path
        self.digest = ""
        self.docs: dict[str, dict] = {}
        self.spans: list[dict] = []
        self.refresh()

    def refresh(self) -> bool:
        raw = self.path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest == self.digest:
            return False
        docs, spans = {}, []
        for line_no, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            doc = json.loads(line)
            required = (
                "doc_id",
                "title",
                "version_date",
                "topic",
                "scope",
                "supersedes",
                "sections",
            )
            if not isinstance(doc, dict) or any(k not in doc for k in required):
                raise ValueError(f"Invalid document at line {line_no}")
            if any(
                not isinstance(doc[k], str) or not doc[k].strip() for k in required[:5]
            ):
                raise ValueError(f"Invalid metadata at line {line_no}")
            date.fromisoformat(doc["version_date"])
            if doc["doc_id"] in docs:
                raise ValueError("Duplicate document ID")
            if not isinstance(doc["supersedes"], list) or any(
                not isinstance(x, str) for x in doc["supersedes"]
            ):
                raise ValueError("supersedes must be a list of IDs")
            if not isinstance(doc["sections"], list) or not doc["sections"]:
                raise ValueError("Document must have sections")
            seen = set()
            for section in doc["sections"]:
                if not isinstance(section, dict) or any(
                    not isinstance(section.get(k), str) or not section[k].strip()
                    for k in ("span_id", "text")
                ):
                    raise ValueError("Invalid section")
                if section["span_id"] in seen:
                    raise ValueError("Duplicate span ID within document")
                seen.add(section["span_id"])
                spans.append({k: doc[k] for k in required if k != "sections"} | section)
            docs[doc["doc_id"]] = doc
        if not docs:
            raise ValueError("Corpus is empty")

        # Contradictory version graph cannot authorize choosing a policy.
        def visit(doc_id: str, visiting: set[str], done: set[str]) -> None:
            if doc_id in visiting:
                raise ValueError("Cyclic supersedes relation")
            if doc_id not in docs or doc_id in done:
                return
            visiting.add(doc_id)
            for old in docs[doc_id]["supersedes"]:
                visit(old, visiting, done)
            visiting.remove(doc_id)
            done.add(doc_id)

        done: set[str] = set()
        for doc_id in docs:
            visit(doc_id, set(), done)
        self.docs, self.spans, self.digest = docs, spans, digest
        return True

    def get_span(self, doc_id: str, span_id: str) -> dict:
        for span in self.spans:
            if span["doc_id"] == doc_id and span["span_id"] == span_id:
                return dict(span)
        raise KeyError("Document or span not found")


class Retriever:
    def __init__(self, corpus: Corpus, method: str = "improved"):
        if method not in {"baseline", "improved"}:
            raise ValueError("Unknown retrieval method")
        self.corpus, self.method, self._digest = corpus, method, ""

    def _index(self) -> None:
        self.corpus.refresh()
        if self._digest == self.corpus.digest:
            return
        self.rows = self.corpus.spans
        self.texts = [
            " ".join(str(r[k]) for k in ("doc_id", "title", "topic", "scope", "text"))
            for r in self.rows
        ]
        self.words = [tokens(t) for t in self.texts]
        self.grams = [ngrams(t) for t in self.texts]
        self.bm25 = BM25Okapi(self.words)
        df = Counter(g for gs in self.grams for g in gs)
        self.idf = {g: math.log(1 + len(self.rows) / count) for g, count in df.items()}
        self._digest = self.corpus.digest

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        self._index()
        qwords, qgrams = tokens(query), ngrams(query)
        if not qwords:
            return []
        bm_scores = self.bm25.get_scores(qwords)
        exact = {
            i
            for i, r in enumerate(self.rows)
            if re.search(r"(?<!\w)" + re.escape(r["doc_id"]) + r"(?!\w)", query, re.I)
            or r["title"].lower() in query.lower()
        }
        # Require lexical content; single common characters must not retrieve the corpus.
        eligible = {i for i, ws in enumerate(self.words) if set(qwords) & set(ws)}
        bm_order = sorted(
            (i for i in eligible if bm_scores[i] > 0),
            key=lambda i: (-float(bm_scores[i]), i),
        )
        gram_scores = {}
        for i, gs in enumerate(self.grams):
            overlap = qgrams & gs
            if len(overlap) >= 2:
                score = sum(self.idf[g] for g in overlap) / max(
                    1, sum(self.idf.get(g, 1) for g in qgrams)
                )
                if score >= 0.12:
                    gram_scores[i] = score
        gram_order = sorted(gram_scores, key=lambda i: (-gram_scores[i], i))
        ranks_bm = {i: rank for rank, i in enumerate(bm_order, 1)}
        ranks_ng = {i: rank for rank, i in enumerate(gram_order, 1)}
        scores = {i: 1 / (60 + rank) for i, rank in ranks_bm.items()}
        if self.method == "improved":
            for i, rank in ranks_ng.items():
                scores[i] = scores.get(i, 0) + 1 / (60 + rank)
        for i in exact:
            scores[i] = scores.get(i, 0) + 1
        order = sorted(scores, key=lambda i: (-scores[i], i))
        selected = order[:top_k]
        expanded: set[int] = set()
        if self.method == "improved" and selected:
            # Include a representative of each competing document in the best topic.
            # Related-document metadata remains complete even when top_k truncates spans.
            topic = self.rows[selected[0]]["topic"]
            priority = [selected[0]]
            seen_docs = {self.rows[selected[0]]["doc_id"]}
            for i, row in enumerate(self.rows):
                if row["topic"] == topic and row["doc_id"] not in seen_docs:
                    priority.append(i)
                    seen_docs.add(row["doc_id"])
                    if i not in scores:
                        expanded.add(i)
            selected = list(dict.fromkeys(priority + order))[:top_k]
        hits = []
        for rank, i in enumerate(selected, 1):
            row = self.rows[i]
            related = []
            if self.method == "improved":
                related = [
                    {
                        k: d[k]
                        for k in (
                            "doc_id",
                            "title",
                            "version_date",
                            "scope",
                            "supersedes",
                        )
                    }
                    | {"span_ids": [s["span_id"] for s in d["sections"]]}
                    for d in self.corpus.docs.values()
                    if d["topic"] == row["topic"]
                ]
            hits.append(
                {
                    k: row[k]
                    for k in (
                        "doc_id",
                        "title",
                        "version_date",
                        "topic",
                        "scope",
                        "supersedes",
                        "span_id",
                    )
                }
                | {
                    "preview": row["text"][:140],
                    "rank": rank,
                    "ranking": {
                        "bm25_rank": ranks_bm.get(i),
                        "ngram_rank": ranks_ng.get(i)
                        if self.method == "improved"
                        else None,
                        "rrf_score": round(scores.get(i, 0), 6),
                        "topic_expanded": i in expanded,
                    },
                    "related_documents": related,
                }
            )
        return hits
