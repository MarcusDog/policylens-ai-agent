import json

from src.evaluation import evaluate


def test_full_offline_matrix(root, tmp_path):
    report = evaluate(
        root / "data/test_cases.jsonl", root, "mock", tmp_path / "eval.json"
    )
    assert report["mode"] == "mock" and report["case_count"] == 16
    for method in ("baseline", "improved"):
        for case in report["reports"][method]["cases"]:
            assert case["status_correct"], (method, case["case_id"], case["result"])
            assert case["fact_checks_pass"], (method, case["case_id"], case["result"])
            assert case["citation_expectations_pass"]
    saved = json.loads((tmp_path / "eval.json").read_text(encoding="utf-8"))
    assert saved["reports"]["improved"]["metrics"]["unsupported_answer_rate_proxy"] == 0
