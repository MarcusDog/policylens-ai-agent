import json

import pytest

from src.cli import main


def test_cli_saves_valid_json_and_trace(root, tmp_path, capsys):
    output, trace = tmp_path / "output.json", tmp_path / "trace.json"
    code = main(
        [
            "ask",
            "--mode",
            "mock",
            "--question",
            "报销期限",
            "--data-dir",
            str(root / "data/scenarios/normal"),
            "--output",
            str(output),
            "--save-trace",
            str(trace),
            "--json",
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ANSWERED"
    assert json.loads(output.read_text(encoding="utf-8"))["citations"]
    assert json.loads(trace.read_text(encoding="utf-8"))["mode"] == "mock"


def test_cli_tool_failure_exit(root, tmp_path, capsys):
    code = main(
        [
            "ask",
            "--mode",
            "mock",
            "--question",
            "VPN",
            "--fail-tool",
            "search_docs",
            "--fail-count",
            "100",
            "--save-trace",
            str(tmp_path / "error.json"),
        ]
    )
    assert code == 1
    assert "TOOL_ERROR" in capsys.readouterr().out


def test_cli_missing_live_config_is_explicit(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.setattr("src.cli.load_dotenv", lambda *a, **kw: None)
    assert main(["ask", "--mode", "live", "--question", "VPN"]) == 2
    assert "Configuration/input error" in capsys.readouterr().err


@pytest.mark.parametrize("args", [["--max-model-steps", "0"], ["--fail-count", "-1"]])
def test_cli_invalid_limits(args, capsys):
    assert main(["ask", "--mode", "mock", "--question", "VPN"] + args) == 2


def test_cli_history_file(root, tmp_path, capsys):
    history = tmp_path / "history.json"
    history.write_text(
        json.dumps([{"role": "user", "content": "报销要准备什么？"}]), encoding="utf-8"
    )
    trace = tmp_path / "trace.json"
    code = main(
        [
            "ask",
            "--mode",
            "mock",
            "--question",
            "那差旅报销呢？",
            "--history-file",
            str(history),
            "--data-dir",
            str(root / "data/scenarios/normal"),
            "--save-trace",
            str(trace),
            "--json",
        ]
    )
    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["citations"][0]["doc_id"] == "D05"
