"""Observable actions only: no hidden reasoning or provider credentials."""

from __future__ import annotations

import json
import hashlib
import platform
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _implementation_snapshot() -> dict:
    root = Path(__file__).resolve().parents[1]
    sources = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((root / "src").glob("*.py"))
    }
    return {
        "python": platform.python_version(),
        "source_files_sha256": sources,
        "source_tree_sha256": hashlib.sha256(
            json.dumps(sources, sort_keys=True).encode()
        ).hexdigest(),
        "requirements_sha256": hashlib.sha256(
            (root / "requirements-lock.txt").read_bytes()
        ).hexdigest(),
    }


# Capture the loaded revision once. Editing files while this process is running
# must not relabel already-imported Python code as a newer implementation.
_LOADED_IMPLEMENTATION = _implementation_snapshot()


def new_trace(mode: str, model: str, question: str, history: list[dict]) -> dict:
    return {
        "run_id": uuid4().hex,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "model": model,
        "question": question,
        "history_summary": [
            {"role": x["role"], "content": x["content"][:250]} for x in history
        ],
        "model_calls": 0,
        "tool_calls": 0,
        "events": [],
        "final": None,
        "state": "RUNNING",
        "in_flight": None,
        "implementation": deepcopy(_LOADED_IMPLEMENTATION),
    }


def write_json(path: str | Path, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid4().hex)
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
