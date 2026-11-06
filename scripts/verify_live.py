"""Run paid Live acceptance explicitly; never auto-fallback to Mock.

Usage: python scripts/verify_live.py --env-file /local/model.env
"""

import argparse
import json
import sys
from uuid import uuid4
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from src.evaluation import evaluate
from src.model import LiveModel
from src.trace import write_json


def main():
    p = argparse.ArgumentParser(
        description="Explicit real-model acceptance (uses API credits)"
    )
    p.add_argument("--env-file", type=Path)
    p.add_argument(
        "--output",
        type=Path,
        default=ROOT / "runs/live" / f"verification-{uuid4().hex[:8]}.json",
    )
    p.add_argument("--case-delay", type=float, default=2)
    args = p.parse_args()
    if args.env_file and not args.env_file.is_file():
        p.error("Configuration file not found")
    load_dotenv(args.env_file or ROOT / ".env")
    try:
        preflight = LiveModel()
        preflight.client.close()
    except (ValueError, OSError):
        write_json(
            ROOT / "examples/live-summary.json",
            {
                "mode": "live",
                "executed": False,
                "status": "NOT_VERIFIED",
                "reason": "Missing/invalid model configuration; no API request was made and no Mock fallback was used.",
                "distinct_tool_paths": [],
                "at_least_two_real_paths": False,
            },
        )
        print(
            "Live not verified: missing/invalid model configuration. No Mock fallback.",
            file=sys.stderr,
        )
        return 2
    output = args.output
    report = evaluate(
        ROOT / "data/live_cases.jsonl",
        ROOT,
        "live",
        output,
        examples_dir=ROOT / "examples",
        progress=lambda row: print(
            f"[{row['method']}] {row['case_id']}: {row['status']}", flush=True
        ),
        case_delay_seconds=args.case_delay,
    )
    paths = set()
    passed = True
    for case in report["reports"]["improved"]["cases"]:
        trace_path = Path(case["trace"])
        if not trace_path.is_absolute():
            trace_path = ROOT / trace_path
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        path = tuple(e["tool_name"] for e in trace["events"] if e["type"] == "tool")
        if (
            case["status_correct"]
            and case["fact_checks_pass"]
            and case["citation_expectations_pass"]
        ):
            paths.add(path)
        else:
            passed = False
    summary = {
        "mode": "live",
        "report": str(output.relative_to(ROOT))
        if output.is_absolute() and output.is_relative_to(ROOT)
        else str(output),
        "executed": True,
        "all_improved_cases_passed": passed,
        "distinct_tool_paths": [list(p) for p in sorted(paths)],
        "at_least_two_real_paths": len(paths) >= 2,
        "note": "Review semantic support and injection resistance manually in saved traces.",
    }
    write_json(ROOT / "examples/live-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed and len(paths) >= 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
