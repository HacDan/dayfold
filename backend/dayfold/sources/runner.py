"""Run scraper strategies in an isolated subprocess and validate their output."""

from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
from dataclasses import dataclass, field

from ..config import config
from ..i18n import tr
from .base import ScrapedItem
from .strategies import ALLOWED_STRATEGIES

TIMEOUT_S = 180
MEMORY_LIMIT = 1024 * 1024 * 1024  # 1 GiB address space


@dataclass
class RunOutcome:
    ok: bool
    items: list[ScrapedItem] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    error: str | None = None


def _limits() -> None:  # pragma: no cover - runs in the child
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
    os.setsid()


def run_isolated(strategy: str, spec: dict, *, max_items: int = 15, language: str | None = None,
                 want_body: bool = True, timeout: int = TIMEOUT_S) -> RunOutcome:
    if strategy not in ALLOWED_STRATEGIES:
        return RunOutcome(ok=False, error=tr(f"estratégia não permitida: {strategy}",
                                             f"strategy not allowed: {strategy}"))
    job = json.dumps({"strategy": strategy, "spec": spec, "max_items": max_items,
                      "language": language, "want_body": want_body})
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-m", "dayfold.sources.worker"],
            input=job, capture_output=True, text=True, timeout=timeout,
            preexec_fn=_limits,
            # The worker builds the log lines shown in the dashboard: let it read the same language.
            env={"PATH": os.environ.get("PATH", ""), "HOME": "/tmp", "DAYFOLD_LANGUAGE": config.language},
        )
    except subprocess.TimeoutExpired:
        return RunOutcome(ok=False, error=tr(f"tempo esgotado ({timeout}s)", f"timed out ({timeout}s)"))
    if proc.returncode != 0 or not proc.stdout.strip():
        return RunOutcome(ok=False, error=(proc.stderr or tr("worker sem saída",
                                                             "worker produced no output")).strip()[-800:])
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return RunOutcome(ok=False, error=tr("saída inválida do worker",
                                             "invalid output from the worker"))
    if not data.get("ok"):
        return RunOutcome(ok=False, error=data.get("error"), log=[data.get("trace", "")])
    items = [ScrapedItem(**i) for i in data.get("items", [])]
    return RunOutcome(ok=True, items=items, log=data.get("log", []))


def validate(outcome: RunOutcome, *, min_items: int = 2, need_body: bool = False) -> dict:
    """Test report used to decide whether a scraper version can be activated."""
    items = outcome.items
    n = len(items)
    report = {
        "ok": False,
        "count": n,
        "with_body": sum(1 for i in items if i.body and len(i.body) > 300),
        "with_date": sum(1 for i in items if i.published_at),
        "with_author": sum(1 for i in items if i.author),
        "with_image": sum(1 for i in items if i.image_url),
        "sample": [{"title": i.title, "url": i.url, "published_at": i.published_at,
                    "author": i.author} for i in items[:5]],
        "reasons": [],
        "error": outcome.error,
    }
    if not outcome.ok:
        report["reasons"].append(outcome.error or tr("falha na execução", "the run failed"))
        return report
    if n < min_items:
        report["reasons"].append(tr(f"apenas {n} matérias (mínimo {min_items})",
                                     f"only {n} stories (minimum {min_items})"))
    bad_titles = [i for i in items if len(i.title) < 12 or len(i.title) > 400]
    if n and len(bad_titles) > n / 2:
        report["reasons"].append(tr("títulos curtos ou longos demais: seletor provavelmente errado",
                                     "titles too short or too long: the selector is probably wrong"))
    if len({i.url for i in items}) < n:
        report["reasons"].append(tr("URLs repetidas", "repeated URLs"))
    if need_body and n and report["with_body"] < max(1, n // 2):
        report["reasons"].append(tr("menos da metade das matérias com corpo de texto",
                                     "fewer than half of the stories have body text"))
    report["ok"] = not report["reasons"]
    return report
