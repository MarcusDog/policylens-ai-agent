"""Bounded model -> tool -> observation loop; no prescribed Live tool path."""

from __future__ import annotations

import json
import hashlib
import time
from copy import deepcopy
from pathlib import Path

from .evidence import EvidenceValidator
from .model import final_payload
from .retriever import Corpus
from .tools import TOOLS, ToolDispatcher
from .trace import new_trace, write_json

SYSTEM_PROMPT = (Path(__file__).resolve().parents[1] / "prompts/v5.txt").read_text(
    encoding="utf-8"
)


class Agent:
    def __init__(
        self,
        model,
        corpus: Corpus,
        *,
        method: str = "improved",
        max_model_steps: int = 8,
        max_tool_calls: int = 10,
        fail_tool: str | None = None,
        fail_count: int = 0,
        system_prompt: str | None = None,
        final_review: bool | None = None,
    ):
        if (
            type(max_model_steps) is not int
            or type(max_tool_calls) is not int
            or min(max_model_steps, max_tool_calls) < 1
        ):
            raise ValueError("Limits must be positive integers")
        self.model, self.corpus, self.method = model, corpus, method
        self.max_model_steps, self.max_tool_calls = max_model_steps, max_tool_calls
        self.fail_tool, self.fail_count = fail_tool, fail_count
        self.system_prompt = SYSTEM_PROMPT if system_prompt is None else system_prompt
        self.final_review = (
            model.mode == "live" if final_review is None else final_review
        )
        if not isinstance(self.system_prompt, str) or not self.system_prompt.strip():
            raise ValueError("system_prompt must be a nonempty string")
        self.trace: dict = {}

    def run(
        self,
        question: str,
        history: list[dict] | None = None,
        save_trace: str | Path | None = None,
    ) -> dict:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a nonempty string")
        history = [] if history is None else history
        if not isinstance(history, list) or any(
            not isinstance(m, dict)
            or m.get("role") not in {"user", "assistant"}
            or not isinstance(m.get("content"), str)
            for m in history
        ):
            raise ValueError(
                "history must contain only user/assistant messages with string content"
            )
        history = [{"role": m["role"], "content": m["content"]} for m in history]
        dispatcher = ToolDispatcher(
            self.corpus, self.method, self.fail_tool, self.fail_count
        )
        validator = EvidenceValidator(dispatcher)
        messages = (
            [{"role": "system", "content": self.system_prompt}]
            + history
            + [{"role": "user", "content": question}]
        )
        self.trace = new_trace(self.model.mode, self.model.name, question, history)
        self.trace["prompt_sha256"] = hashlib.sha256(
            self.system_prompt.encode("utf-8")
        ).hexdigest()
        self.trace["limits"] = {
            "max_model_steps": self.max_model_steps,
            "max_tool_calls": self.max_tool_calls,
        }
        self.trace["final_review_enabled"] = self.final_review
        started = time.perf_counter()

        def checkpoint() -> None:
            if save_trace:
                write_json(save_trace, self.trace)

        checkpoint()

        def finish(
            final: dict, valid: bool, validation_errors: list[str] | None = None
        ) -> dict:
            final["task_state"] = {
                "model_calls": self.trace["model_calls"],
                "tool_calls": self.trace["tool_calls"],
                "completed": final["status"] in {"ANSWERED", "NOT_FOUND"},
            }
            self.trace["final"] = final
            self.trace["state"] = "FINISHED"
            self.trace["in_flight"] = None
            self.trace["evidence_validation"] = {
                "valid": valid,
                "errors": validation_errors or [],
                "scope": "structure/provenance/known-candidate coverage; not semantic entailment",
            }
            self.trace["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
            self.trace["corpus_digest"] = self.corpus.digest
            usages = [
                e["telemetry"].get("usage", {})
                for e in self.trace["events"]
                if e["type"] == "model"
            ]
            self.trace["token_usage"] = {
                k: sum(u.get(k, 0) or 0 for u in usages)
                for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            }
            checkpoint()
            return final

        last_errors: list[str] = []
        review_requested = False
        for step in range(1, self.max_model_steps + 1):
            self.trace["model_calls"] += 1
            tick = time.perf_counter()
            self.trace["in_flight"] = {"kind": "model", "step": step}
            checkpoint()
            try:
                reply = self.model.complete(messages, TOOLS)
            except KeyboardInterrupt:
                self.trace["state"] = "CANCELLED"
                self.trace["in_flight"] = None
                self.trace["events"].append({"type": "cancelled", "step": step})
                checkpoint()
                raise
            except Exception as exc:
                # Provider exception strings can contain URLs, request headers or secrets.
                self.trace["events"].append(
                    {
                        "type": "model_error",
                        "step": step,
                        "error_type": type(exc).__name__,
                        "http_status": getattr(exc, "status_code", None),
                        "retryable": type(exc).__name__
                        in {"RateLimitError", "APITimeoutError", "APIConnectionError"},
                        "success": False,
                    }
                )
                return finish(
                    final_payload(
                        "TOOL_ERROR",
                        "模型 API 调用失败，任务未完成。",
                        missing=["可用的模型 API 响应；请检查配置、连通性和超时"],
                    ),
                    False,
                    ["Model API unavailable"],
                )
            messages.append(reply.message())
            self.trace["in_flight"] = None
            self.trace["events"].append(
                {
                    "type": "model",
                    "step": step,
                    "action": "tools" if reply.tool_calls else "final",
                    "tool_names": [c.name for c in reply.tool_calls],
                    "telemetry": reply.telemetry,
                    "duration_ms": round((time.perf_counter() - tick) * 1000, 3),
                }
            )
            checkpoint()
            if reply.tool_calls:
                for call in reply.tool_calls:
                    if self.trace["tool_calls"] >= self.max_tool_calls:
                        return finish(
                            final_payload(
                                "LIMIT_REACHED",
                                "已达工具调用上限，核查未完成。",
                                missing=["尚未执行的工具调用和最终核查"],
                            ),
                            False,
                            last_errors,
                        )
                    self.trace["tool_calls"] += 1
                    self.trace["in_flight"] = {
                        "kind": "tool",
                        "step": step,
                        "tool_name": call.name,
                    }
                    checkpoint()
                    tick = time.perf_counter()
                    result = dispatcher.dispatch(call.name, call.arguments)
                    result["runtime_budget"] = {
                        "model_steps_remaining": self.max_model_steps - step,
                        "tool_calls_remaining": self.max_tool_calls
                        - self.trace["tool_calls"],
                    }
                    try:
                        args = json.loads(call.arguments)
                    except (json.JSONDecodeError, TypeError):
                        args = {"invalid_json": True}
                    summary = (
                        {"hits": len(result["data"]["hits"])}
                        if result["ok"] and "hits" in result["data"]
                        else (
                            {
                                "doc_id": result["data"]["doc_id"],
                                "span_id": result["data"]["span_id"],
                            }
                            if result["ok"]
                            else result["error"]
                        )
                    )
                    self.trace["events"].append(
                        {
                            "type": "tool",
                            "step": step,
                            "tool_name": call.name,
                            "tool_call_id": call.id,
                            "tool_args": args,
                            "purpose": args.get("purpose", "")
                            if isinstance(args, dict)
                            else "",
                            "result_summary": summary,
                            "result": result,
                            "success": result["ok"],
                            "duration_ms": round(
                                (time.perf_counter() - tick) * 1000, 3
                            ),
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                    self.trace["in_flight"] = None
                    checkpoint()
                continue
            try:
                final = json.loads(reply.content or "")
                last_errors = validator.validate(final)
            except (json.JSONDecodeError, TypeError):
                final, last_errors = None, ["Final output is not valid JSON"]
            self.trace["events"].append(
                {
                    "type": "validation",
                    "step": step,
                    "valid": not last_errors,
                    "errors": last_errors,
                    "candidate": deepcopy(final),
                }
            )
            checkpoint()
            if not last_errors:
                if (
                    self.final_review
                    and not review_requested
                    and final["status"]
                    in {"ANSWERED", "CONFLICT", "NEEDS_CLARIFICATION"}
                ):
                    review_requested = True
                    review = {
                        "final_review": "只复核候选答案，不输出分析过程。",
                        "checklist": [
                            "answer 每项企业事实是否由本轮读取且最终引用的原文或元数据支持？删除只见于 search preview 的附加流程。",
                            "用户问自己的或笼统的适用规则，而资料按不同部门给出不同结论：用户/历史是否已明确部门？未明确就应 NEEDS_CLARIFICATION 并提一个问题，不可用 ANSWERED 罗列条件让用户自选；明确问各部门对比则可回答比较。",
                            "是否擅自把 version_date 当成生效日期、推断历史适用时段，或把最新日期当优先级？明确替代关系和范围已足以确定当前规则时，可以回答当前规则，不必因缺生效日而拒答。",
                            "冲突是否引用各方、无依据是否明确缺口、持续工具失败是否停止？",
                        ],
                        "instruction": "若候选已正确，直接返回同一 JSON；否则自主修正最终 JSON 或继续查证。不要给复核报告或思维链。",
                    }
                    self.trace["events"].append(
                        {
                            "type": "final_review",
                            "step": step,
                            "checklist": review["checklist"],
                        }
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": json.dumps(review, ensure_ascii=False),
                        }
                    )
                    checkpoint()
                    last_errors = ["Final self-review not yet completed"]
                    continue
                return finish(final, True)
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "validation_errors": last_errors,
                            "instruction": "修正最终 JSON 或继续工具核查，不要伪造引用。",
                        },
                        ensure_ascii=False,
                    ),
                }
            )
        return finish(
            final_payload(
                "LIMIT_REACHED",
                "已达模型轮次上限，尚未形成有效答案。",
                missing=last_errors or ["剩余文档核查与最终回答"],
            ),
            False,
            last_errors,
        )
