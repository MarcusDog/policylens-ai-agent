"""Rescore existing real outputs after an explicit annotation correction.

Does not call a model or change any saved output/trace. Original reports stay intact.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.evaluation import check_case, read_cases
from src.trace import write_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--cases", type=Path, default=ROOT / "data/live_cases.jsonl")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.resolve() == args.report.resolve():
        p.error("Rescore must not overwrite the original run")
    report = json.loads(args.report.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in read_cases(args.cases)}
    results = {}
    for method, block in report["reports"].items():
        checks = []
        for row in block["cases"]:
            trace_path = Path(row["trace"])
            trace = json.loads(
                (
                    trace_path if trace_path.is_absolute() else ROOT / trace_path
                ).read_text(encoding="utf-8")
            )
            assert trace["mode"] == "live"
            case = cases[row["case_id"]]
            if case["question"] != trace["question"]:
                raise ValueError("Cannot rescore changed questions")
            current = check_case(case, row["result"])
            checks.append(
                {
                    "case_id": row["case_id"],
                    "original_fact_check": row["fact_checks_pass"],
                    **current,
                    "passed": all(current.values()),
                    "trace": row["trace"],
                }
            )
        results[method] = {
            "case_pass_rate": mean(c["passed"] for c in checks),
            "cases": checks,
        }
    result = {
        "type": "annotation-rescore-of-existing-live-outputs",
        "new_model_calls": 0,
        "source_report": args.report.as_posix(),
        "source_sha256": hashlib.sha256(args.report.read_bytes()).hexdigest(),
        "case_annotations_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        "reason": "Blanket banned terms wrongly rejected a reminder that had a real, read D13 citation. Conditional citation obligations still reject the same claim without its supporting quote. All original outputs and failed checks are retained.",
        "reports": results,
    }
    write_json(args.output, result)
    print(json.dumps({m: b["case_pass_rate"] for m, b in results.items()}))
    return 0 if all(c["passed"] for b in results.values() for c in b["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
