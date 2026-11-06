"""Structural provenance validation, deliberately not a semantic entailment oracle."""

from __future__ import annotations

from .tools import ToolDispatcher

STATUSES = {
    "ANSWERED",
    "CONFLICT",
    "NEEDS_CLARIFICATION",
    "NOT_FOUND",
    "TOOL_ERROR",
    "LIMIT_REACHED",
}
PROOF_FIELDS = (
    "doc_id",
    "title",
    "version_date",
    "topic",
    "scope",
    "supersedes",
    "span_id",
    "text",
)


class EvidenceValidator:
    def __init__(self, tools: ToolDispatcher):
        self.tools = tools

    def validate(self, final: object) -> list[str]:
        if not isinstance(final, dict):
            return ["Final output must be a JSON object"]
        required = {
            "status",
            "answer",
            "citations",
            "missing_information",
            "clarification_question",
            "task_state",
        }
        if set(final) != required:
            return ["Final fields must be: " + ", ".join(sorted(required))]
        errors = []
        status = final["status"]
        if not isinstance(status, str) or status not in STATUSES:
            return ["Unknown status"]
        if not isinstance(final["answer"], str) or not final["answer"].strip():
            errors.append("answer must be a nonempty string")
        if not isinstance(final["missing_information"], list) or any(
            not isinstance(x, str) for x in final["missing_information"]
        ):
            errors.append("missing_information must be a list of strings")
        if final["clarification_question"] is not None and not isinstance(
            final["clarification_question"], str
        ):
            errors.append("clarification_question must be a string or null")
        if not isinstance(final["task_state"], dict):
            errors.append("task_state must be an object (runtime overwrites counters)")
        citations = final["citations"]
        if not isinstance(citations, list):
            return errors + ["citations must be a list"]
        try:
            self.tools.corpus.refresh()
        except (OSError, ValueError, TypeError):
            return errors + ["Current corpus unavailable; evidence cannot be verified"]
        if (
            self.tools.observed_digest is not None
            and self.tools.observed_digest != self.tools.corpus.digest
        ):
            errors.append(
                "Corpus changed since the last observation; search/read current data again"
            )
        valid = []
        for cite in citations:
            keys = {"doc_id", "version_date", "span_id", "quote"}
            if (
                not isinstance(cite, dict)
                or set(cite) != keys
                or any(not isinstance(cite[k], str) or not cite[k] for k in keys)
            ):
                errors.append(
                    "Each citation needs nonempty doc_id, version_date, span_id, quote"
                )
                continue
            try:
                span = self.tools.corpus.get_span(cite["doc_id"], cite["span_id"])
            except KeyError:
                errors.append("Cited document/span does not exist in current corpus")
                continue
            if cite["version_date"] != span["version_date"]:
                errors.append("Citation version differs from current corpus")
            if cite["quote"] not in span["text"]:
                errors.append("Quote is not an exact original substring")
            read = self.tools.reads.get((cite["doc_id"], cite["span_id"]))
            if read is None or any(read[k] != span[k] for k in PROOF_FIELDS):
                errors.append(
                    "Citation must have been read successfully in THIS run at its current version"
                )
            valid.append(span)
        if status == "ANSWERED" and not citations:
            errors.append("ANSWERED requires successfully read evidence")
        if status in {"CONFLICT", "NEEDS_CLARIFICATION"}:
            if not final["clarification_question"] or not final["missing_information"]:
                errors.append(
                    "Conflict/clarification requires a key question and missing information"
                )
        if (
            status == "CONFLICT"
            and len(
                {
                    (c.get("doc_id"), c.get("span_id"))
                    for c in citations
                    if isinstance(c, dict)
                    and isinstance(c.get("doc_id"), str)
                    and isinstance(c.get("span_id"), str)
                }
            )
            < 2
        ):
            errors.append("CONFLICT requires at least two distinct evidence spans")
        if status == "NOT_FOUND" and not self.tools.successful_searches:
            errors.append("NOT_FOUND requires a successful search in this run")
        if status == "TOOL_ERROR" and not self.tools.errors:
            errors.append("TOOL_ERROR requires an observed tool failure")
        # This gate only demands checking candidates. It never decides which policy wins.
        if status in {"ANSWERED", "CONFLICT", "NEEDS_CLARIFICATION"}:
            for topic in {s["topic"] for s in valid}:
                known = (
                    self.tools.discovered.get(topic, set())
                    & self.tools.corpus.docs.keys()
                )
                checked = {
                    doc_id
                    for (doc_id, span_id), read in self.tools.reads.items()
                    if doc_id in self.tools.corpus.docs
                    and self._read_is_current(doc_id, span_id, read)
                }
                if known - checked:
                    errors.append(
                        "Read known same-topic candidate documents before deciding: "
                        + ", ".join(sorted(known - checked))
                    )
                for doc_id in sorted(known & checked):
                    unread = [
                        s["span_id"]
                        for s in self.tools.corpus.docs[doc_id]["sections"]
                        if (doc_id, s["span_id"]) not in self.tools.reads
                        or not self._read_is_current(
                            doc_id,
                            s["span_id"],
                            self.tools.reads[(doc_id, s["span_id"])],
                        )
                    ]
                    if unread:
                        errors.append(
                            f"Known same-topic document {doc_id} has unchecked sections: "
                            + ", ".join(unread)
                        )
        return list(dict.fromkeys(errors))

    def _read_is_current(self, doc_id: str, span_id: str, read: dict) -> bool:
        try:
            current = self.tools.corpus.get_span(doc_id, span_id)
        except KeyError:
            return False
        return all(current[k] == read[k] for k in PROOF_FIELDS)
