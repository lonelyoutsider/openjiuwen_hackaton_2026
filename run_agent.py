#!/usr/bin/env python3
import argparse
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from harness.execution import execute
from harness.tasks import load_tasks
from harness.profile import DEFAULT_MODEL, DEFAULT_CALLS, DEFAULT_COMPACT_DATA_CONTEXT, resolve_json_mode


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks-dir", type=Path, required=True)
    parser.add_argument("--budget", type=int, default=int(os.environ.get("BUDGET", "100000")))
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--diagnostics", action="store_true", default=os.environ.get("ITS_IA_DIAGNOSTICS") == "1", help="record bounded model actions and tool observations")
    parser.add_argument("--enable-edit", action=argparse.BooleanOptionalAction, default=True, help="exact text replacement in coding sources")
    parser.add_argument("--recover-actions", action=argparse.BooleanOptionalAction, default=True, help="accept one complete terminal JSON action after commentary")
    parser.add_argument("--json-mode", action=argparse.BooleanOptionalAction, default=None, help="provider JSON format; auto only for the verified NeuralDeep HTTPS endpoint")
    parser.add_argument("--compact-data-context", action=argparse.BooleanOptionalAction,
                        default=DEFAULT_COMPACT_DATA_CONTEXT,
                        help="short, explicitly marked previews of data files; full files remain available to tools")
    parser.add_argument("--max-calls-per-task", type=int, default=DEFAULT_CALLS)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--time-limit", type=int, default=3300)
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--engine", choices=["openjiuwen", "stdlib"], default="openjiuwen",
                        help="stdlib: parser diagnostics only, not a submission")
    args = parser.parse_args()
    if args.budget < 0 or min(args.max_calls_per_task, args.max_output_tokens, args.time_limit) < 1:
        parser.error("invalid budget or execution limits")
    deadline = time.monotonic() + args.time_limit
    tasks = load_tasks(args.tasks_dir)
    if any((t.directory / "answer.txt").exists() for t in tasks):
        parser.error("existing answer.txt; use a clean copy of tasks to avoid stale answers")
    # Finish all zero-cost tasks before spending budget on any LLM route.
    tasks.sort(key=lambda t: (-t.reward, t.task_id))
    if args.engine == "openjiuwen":
        # SDK file logging may use a relative logs/ path during import.
        # /app is read-only in the evaluator; task paths are already absolute.
        os.chdir(tempfile.mkdtemp(prefix="its-ia-openjiuwen-"))
        from harness.workflow import build_workflow, run_task
        flow = build_workflow()
    pending = []
    for task in tasks:
        if args.engine == "openjiuwen":
            await run_task(flow, task, deadline=deadline)
        else:
            execute(task)
        record = json.loads((task.directory / "its_ia_result.json").read_text(encoding="utf-8"))
        print(json.dumps(record, ensure_ascii=False), flush=True)
        if record["status"] != "solved":
            pending.append(task)
    if not args.no_llm and os.environ.get("LLM_API_KEY"):
        from harness.llm import Client
        from harness.agent import Agent
        base_url = os.environ.get("LLM_BASE_URL", "https://api.neuraldeep.ru/v1")
        client = Client(base_url,
                        os.environ["LLM_API_KEY"], args.budget, model=args.model, deadline=deadline,
                        json_mode=resolve_json_mode(base_url, args.json_mode))
        agent = Agent(client, max_calls=args.max_calls_per_task,
                      max_tokens=args.max_output_tokens, deadline=deadline, diagnostics=args.diagnostics,
                      enable_edit=args.enable_edit, recover_actions=args.recover_actions,
                      compact_data_context=args.compact_data_context)
        if args.engine == "openjiuwen":
            flow = build_workflow(agent)
        # Initial cost estimates are explicit heuristics, not trained predictions.
        cost = {"coding": 3000, "data_analysis": 1500, "math": 1000, "search": 1000}
        pending.sort(key=lambda t: (-t.reward / cost.get(t.task_type, 2000), t.task_id))
        try:
            for task in pending:
                if time.monotonic() >= deadline or client.stopped:
                    break
                if args.engine == "openjiuwen":
                    await run_task(flow, task, deadline=deadline)
                else:
                    execute(task, agent)
                print((task.directory / "its_ia_result.json").read_text(encoding="utf-8").strip(), flush=True)
        finally:
            # An SDK/tool exception must not hide charges already in the ledger.
            print(json.dumps({"run_usage": client.snapshot()}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
