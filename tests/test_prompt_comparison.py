import json

import pytest

from scripts.compare_prompts import compare


def test_saved_pair_is_comparable(root):
    result = compare(
        root / "examples/generalization-v4-live.json",
        root / "examples/generalization-v5-live.json",
    )
    assert result["case_count"] == 8
    assert result["independent_blind_test"] is False


def test_comparison_rejects_changed_corpus(root, tmp_path):
    left = root / "examples/generalization-v4-live.json"
    right = json.loads(
        (root / "examples/generalization-v5-live.json").read_text(encoding="utf-8")
    )
    right["reports"]["improved"]["cases"][0]["corpus_digest"] = "a different corpus"
    path = tmp_path / "mismatched.json"
    path.write_text(json.dumps(right), encoding="utf-8")
    with pytest.raises(ValueError, match="Corpus differs"):
        compare(left, path)
