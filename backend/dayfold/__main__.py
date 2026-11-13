"""Command line: ``dayfold serve`` (default), ``dayfold generate``, ``dayfold init``."""

from __future__ import annotations

import argparse
import logging


def main() -> None:
    parser = argparse.ArgumentParser(prog="dayfold", description="Dayfold server")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="run the web server, scheduler and worker (default)")
    sub.add_parser("generate", help="generate an edition now, in the foreground")
    sub.add_parser("init", help="create the database and default data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    from .bootstrap import bootstrap

    bootstrap()
    if args.cmd == "init":
        print("ok")
        return
    if args.cmd == "generate":
        from .db import session_scope
        from .models import GenerationJob
        from .pipeline.generate import run_generation_job

        with session_scope() as s:
            job = GenerationJob(trigger="cli", log=[])
            s.add(job)
            s.flush()
            job_id = job.id
        try:
            run_generation_job(job_id)
        finally:
            with session_scope() as s:
                for line in s.get(GenerationJob, job_id).log:
                    print(line)
        return
    import uvicorn

    from .config import config

    uvicorn.run("dayfold.app:app", host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    main()
