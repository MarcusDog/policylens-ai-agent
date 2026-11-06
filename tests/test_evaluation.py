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


def test_competing_document_retrieval_stress(root, tmp_path):
    report = evaluate(
        root / "data/retrieval_stress_cases.jsonl",
        root,
        "mock",
        tmp_path / "stress.json",
        retrieval_only=True,
    )
    assert report["reports"]["improved"]["metrics"]["recall_at_5"] == 1
    assert report["reports"]["baseline"]["metrics"]["recall_at_5"] < 1


def test_preview_fact_requires_its_own_cited_evidence():
    from src.evaluation import check_case
    from .conftest import cite

    case = {
        "expected_status": "ANSWERED",
        "citation_obligations": [{"trigger_pattern": "草稿", "quote_pattern": "草稿"}],
    }
    result = {
        "status": "ANSWERED",
        "answer": "30天内提交，草稿不代表提交。",
        "citations": [cite()],
    }
    assert not check_case(case, result)["fact_checks_pass"]
    result["citations"].append(cite("D13", "草稿状态不代表报销已经提交", "2026-05-03"))
    assert check_case(case, result)["fact_checks_pass"]


def test_numeric_fact_regression_uses_whole_deadline():
    from src.evaluation import check_case

    case = {"expected_status": "ANSWERED", "required_patterns": [r"(?<!\d)7\s*天"]}
    assert not check_case(
        case, {"status": "ANSWERED", "answer": "77天", "citations": []}
    )["fact_checks_pass"]
    assert check_case(case, {"status": "ANSWERED", "answer": "7 天", "citations": []})[
        "fact_checks_pass"
    ]
