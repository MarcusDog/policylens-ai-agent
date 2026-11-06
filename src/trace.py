"""Observable actions only: no hidden reasoning or provider credentials."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


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
    }


def write_json(path: str | Path, value: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid4().hex)
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
