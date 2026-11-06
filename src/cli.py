"""python -m src.cli ask/eval. All paths work via pathlib on Windows and Unix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from .agent import Agent
from .evaluation import evaluate
from .model import LiveModel, MockModel
from .retriever import Corpus
from .trace import write_json

ROOT = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="PolicyLens enterprise knowledge agent")
    sub = p.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask")
    ask.add_argument("--question", required=True)
    ask.add_argument("--data-dir", type=Path, default=ROOT / "data")
    ask.add_argument("--history-file", type=Path)
    ask.add_argument(
        "--save-history", type=Path, help="Save the actual dialogue for the next turn"
    )
    ask.add_argument("--method", choices=["baseline", "improved"], default="improved")
    ask.add_argument("--fail-tool", choices=["search_docs", "read_doc_span"])
    ask.add_argument("--fail-count", type=int, default=1)
    ask.add_argument("--max-model-steps", type=int, default=8)
    ask.add_argument("--max-tool-calls", type=int, default=10)
    ask.add_argument("--save-trace", type=Path)
    ask.add_argument("--output", type=Path)
    ask.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    ev = sub.add_parser("eval")
    ev.add_argument("--cases", type=Path, default=ROOT / "data/test_cases.jsonl")
    ev.add_argument("--output", type=Path, default=ROOT / "runs/evaluation.json")
    ev.add_argument("--retrieval-only", action="store_true")
    ev.add_argument("--examples-dir", type=Path)
    ev.add_argument(
        "--methods",
        nargs="+",
        choices=["baseline", "improved"],
        default=["baseline", "improved"],
    )
    for cmd in (ask, ev):
        cmd.add_argument(
            "--no-final-review",
            action="store_true",
            help="Disable the single-agent final review for an explicit ablation",
        )
        cmd.add_argument(
            "--prompt-file",
            type=Path,
            help="Use a versioned system prompt for a reproducible comparison",
        )
        cmd.add_argument("--mode", choices=["live", "mock"], default="live")
        cmd.add_argument(
            "--env-file",
            type=Path,
            help="Load local model configuration; never printed",
        )
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.env_file and not args.env_file.is_file():
        print("Configuration file not found.", file=sys.stderr)
        return 2
    if args.mode == "live" and not getattr(args, "retrieval_only", False):
        load_dotenv(args.env_file or ROOT / ".env", override=False)
    try:
        prompt = (
            args.prompt_file.read_text(encoding="utf-8") if args.prompt_file else None
        )
        if args.command == "eval":
            report = evaluate(
                args.cases,
                ROOT,
                args.mode,
                args.output,
                args.retrieval_only,
                args.examples_dir,
                system_prompt=prompt,
                final_review=False if args.no_final_review else None,
                methods=tuple(args.methods),
                progress=(
                    lambda row: print(
                        f"[{row['method']}] {row['case_id']}: {row['status']}",
                        file=sys.stderr,
                        flush=True,
                    )
                )
                if args.mode == "live"
                else None,
            )
            print(
                json.dumps(
                    {k: v["metrics"] for k, v in report["reports"].items()},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            if args.retrieval_only:
                return 0
            return (
                0
                if all(
                    r["status_correct"]
                    and r["fact_checks_pass"]
                    and r["citation_expectations_pass"]
                    and r["clarification_checks_pass"]
                    for v in report["reports"].values()
                    for r in v["cases"]
                )
                else 1
            )
        if args.fail_count < 0:
            raise ValueError("fail-count must be nonnegative")
        model = LiveModel() if args.mode == "live" else MockModel()
        history = (
            json.loads(args.history_file.read_text(encoding="utf-8-sig"))
            if args.history_file
            else None
        )
        agent = Agent(
            model,
            Corpus(args.data_dir),
            method=args.method,
            max_model_steps=args.max_model_steps,
            max_tool_calls=args.max_tool_calls,
            fail_tool=args.fail_tool,
            fail_count=args.fail_count,
            system_prompt=prompt,
            final_review=False if args.no_final_review else None,
        )
        trace_path = args.save_trace or ROOT / "runs" / args.mode / "latest-trace.json"
        try:
            result = agent.run(args.question, history, trace_path)
        finally:
            if args.mode == "live":
                model.client.close()
        if args.output:
            write_json(args.output, result)
        if args.save_history:
            write_json(
                args.save_history,
                (history or [])
                + [
                    {"role": "user", "content": args.question},
                    {
                        "role": "assistant",
                        "content": json.dumps(result, ensure_ascii=False),
                    },
                ],
            )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"[{result['status']}] {result['answer']}")
            for c in result["citations"]:
                print(
                    f"  [{c['doc_id']} / {c['version_date']} / {c['span_id']}] {c['quote']}"
                )
            if result["missing_information"]:
                print("资料缺口：" + "；".join(result["missing_information"]))
            if result["clarification_question"]:
                print("澄清：" + result["clarification_question"])
            print("任务状态：" + json.dumps(result["task_state"], ensure_ascii=False))
            print(f"Trace: {trace_path}")
        return 1 if result["status"] in {"TOOL_ERROR", "LIMIT_REACHED"} else 0
    except KeyboardInterrupt:
        print(
            "运行已取消；已写入的 Trace 保留实际执行观察，不标记为成功。",
            file=sys.stderr,
        )
        return 130
    except (ValueError, OSError, TypeError) as exc:
        # Only controlled local errors. Avoid printing content of a malformed .env/data file.
        print(
            f"Configuration/input error ({type(exc).__name__}). Check paths, model variables, JSON and limits.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
