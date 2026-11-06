"""Check comparability before calculating a paired Prompt result."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def compare(left_path: Path, right_path: Path) -> dict:
    left, right = [
        json.loads(p.read_text(encoding="utf-8")) for p in (left_path, right_path)
    ]
    if not all(r.get("complete") and r.get("mode") == "live" for r in (left, right)):
        raise ValueError("Only complete Live reports can be compared")
    if left["cases_sha256"] != right["cases_sha256"]:
        raise ValueError("Case annotations differ")
    pairs = []
    trees = set()
    a, b = [r["reports"]["improved"] for r in (left, right)]
    if [c["case_id"] for c in a["cases"]] != [c["case_id"] for c in b["cases"]]:
        raise ValueError("Case IDs/order differ")
    for ca, cb in zip(a["cases"], b["cases"]):
        if ca["corpus_digest"] != cb["corpus_digest"]:
            raise ValueError("Corpus differs for " + ca["case_id"])
        traces = [
            json.loads((ROOT / c["trace"]).read_text(encoding="utf-8"))
            for c in (ca, cb)
        ]
        ta, tb = traces
        tree_a, tree_b = [t["implementation"]["source_tree_sha256"] for t in traces]
        if tree_a != tree_b:
            raise ValueError("Runtime implementation differs")
        trees.add(tree_a)
        for field in (
            "question",
            "history_summary",
            "limits",
            "final_review_enabled",
            "model",
        ):
            if ta[field] != tb[field]:
                raise ValueError("Run setting differs: " + field)
        if ta["prompt_sha256"] == tb["prompt_sha256"]:
            raise ValueError("Prompts are identical")
        pairs.append(
            {
                "case_id": ca["case_id"],
                "left_status": ca["status"],
                "right_status": cb["status"],
                "left_pass": all(
                    ca[k]
                    for k in (
                        "status_correct",
                        "fact_checks_pass",
                        "citation_expectations_pass",
                        "clarification_checks_pass",
                    )
                ),
                "right_pass": all(
                    cb[k]
                    for k in (
                        "status_correct",
                        "fact_checks_pass",
                        "citation_expectations_pass",
                        "clarification_checks_pass",
                    )
                ),
            }
        )
    if len(trees) != 1:
        raise ValueError("Runtime changed within the batches")
    return {
        "type": "checked-paired-prompt-comparison",
        "independent_blind_test": False,
        "limitations": "Same AI authored the set. Prompt v5 was refined after observing v4's G05 failure; this is a frozen regression comparison, not unseen-test accuracy or a statistical significance claim.",
        "source_reports": [str(p) for p in (left_path, right_path)],
        "source_reports_sha256": [
            hashlib.sha256(p.read_bytes()).hexdigest() for p in (left_path, right_path)
        ],
        "case_count": len(pairs),
        "shared_source_tree_sha256": next(iter(trees)),
        "left_metrics": a["metrics"],
        "right_metrics": b["metrics"],
        "observed_token_reduction": 1
        - b["metrics"]["mean_total_tokens"] / a["metrics"]["mean_total_tokens"],
        "cases": pairs,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--left", type=Path, default=ROOT / "examples/generalization-v4-live.json"
    )
    p.add_argument(
        "--right", type=Path, default=ROOT / "examples/generalization-v5-live.json"
    )
    p.add_argument(
        "--output", type=Path, default=ROOT / "docs/prompt-v4-v5-comparison.json"
    )
    args = p.parse_args()
    result = compare(args.left, args.right)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "paired_cases": result["case_count"],
                "token_reduction": result["observed_token_reduction"],
            }
        )
    )


if __name__ == "__main__":
    main()
