"""Trace JSONL : une ligne par appel LLM ou outil.

Champs : horodatage, case_id, agent, prompt_id, version, modèle, tokens, coût,
latence, statut. Le notebook d'analyse en tire le tableau des coûts du rapport.
"""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def write_trace(path: Path, record: dict[str, Any]) -> None:
    record = {"ts": datetime.now(UTC).isoformat(timespec="milliseconds"), **record}
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _lock, path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


@contextmanager
def traced(path: Path, **fields: Any):
    """Mesure la latence et écrit la trace, même en cas d'exception.

    Le bloc peut enrichir la trace : ``with traced(p, agent="x") as rec: rec["tokens_in"] = 12``
    """
    rec: dict[str, Any] = dict(fields)
    start = time.perf_counter()
    try:
        yield rec
        rec.setdefault("status", "ok")
    except Exception as exc:
        rec["status"] = "error"
        rec["error"] = f"{type(exc).__name__}: {exc}"[:500]
        raise
    finally:
        rec["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
        write_trace(path, rec)


def read_traces(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
