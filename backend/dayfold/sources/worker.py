"""Subprocess entry point: ``python -I -m dayfold.sources.worker < job.json``.

Runs one scraper strategy isolated from the server process (own memory limit, wall
clock timeout enforced by the parent) and prints a JSON result on stdout.
"""

from __future__ import annotations

import json
import sys
import traceback


def main() -> None:
    job = json.load(sys.stdin)
    from .strategies import run_strategy

    try:
        result = run_strategy(
            job["strategy"], job["spec"], max_items=int(job.get("max_items", 15)),
            language=job.get("language"), want_body=bool(job.get("want_body", True)),
        )
        json.dump({"ok": True, **result.to_dict()}, sys.stdout)
    except Exception as exc:  # noqa: BLE001
        json.dump({"ok": False, "error": f"{type(exc).__name__}: {exc}",
                   "trace": traceback.format_exc(limit=4)}, sys.stdout)


if __name__ == "__main__":
    main()
