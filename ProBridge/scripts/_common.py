"""Shared helpers for ProBridge arcpy job scripts.

ProBridge puts this directory on PYTHONPATH, so a script can simply do
`from _common import main, out_path`.

The contract with `run_arcpy` is one JSON object per job:

  * write it to the path in PROBRIDGE_RESULT, or
  * print one line `PROBRIDGE_RESULT: {...}`

A `layers` list in that object is added to the current map (unless the caller
passed add_layers explicitly).
"""

from __future__ import annotations

import json
import os
import sys
import traceback


def emit(payload: dict) -> dict:
    """Write the job result as JSON, both to disk and to stdout."""
    text = json.dumps(payload, ensure_ascii=False, default=str)
    path = os.environ.get("PROBRIDGE_RESULT")
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    print("PROBRIDGE_RESULT: " + text)
    return payload


def job_dir() -> str:
    """Per-run scratch directory created by ProBridge (writable)."""
    return os.environ.get("PROBRIDGE_JOB_DIR") or os.getcwd()


def out_path(name: str) -> str:
    """A path inside this job's scratch directory."""
    return os.path.join(job_dir(), name)


def main(fn) -> None:
    """Run fn(), emit its dict result, and report failures as exit code 1."""
    try:
        emit(fn() or {})
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        emit({"error": traceback.format_exc()})
        sys.exit(1)
