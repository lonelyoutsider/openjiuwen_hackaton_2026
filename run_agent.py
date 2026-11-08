#!/usr/bin/env python3
import argparse
import asyncio
import json
import os
from pathlib import Path
from harness.execution import execute
from harness.tasks import load_tasks


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks-dir", type=Path, required=True)
    parser.add_argument("--budget", type=int, default=int(os.environ.get("BUDGET", "100000")))
    parser.add_argument("--engine", choices=["openjiuwen", "stdlib"], default="openjiuwen",
                        help="stdlib: parser diagnostics only, not a submission")
    args = parser.parse_args()
    if args.budget < 0:
        parser.error("budget must be nonnegative")
    tasks = load_tasks(args.tasks_dir)
    if any((t.directory / "answer.txt").exists() for t in tasks):
        parser.error("existing answer.txt; use a clean copy of tasks to avoid stale answers")
    # Supported deterministic routes have zero LLM cost. LLM planning is pending.
    tasks.sort(key=lambda t: (-t.reward, t.task_id))
    if args.engine == "openjiuwen":
        from harness.workflow import build_workflow, run_task
        flow = build_workflow()
    for task in tasks:
        if args.engine == "openjiuwen":
            await run_task(flow, task)
        else:
            execute(task)
        record = json.loads((task.directory / "its_ia_result.json").read_text(encoding="utf-8"))
        print(json.dumps(record, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
