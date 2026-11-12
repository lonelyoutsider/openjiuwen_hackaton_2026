#!/usr/bin/env python3
"""Run one bounded A/B pair in Docker; no API requests unless --live is given."""
import argparse
from datetime import datetime, timezone
import getpass
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import uuid


COMPARISONS = {
    "edit": {"baseline": {"enable_edit": False, "recover_actions": False},
             "edit": {"enable_edit": True, "recover_actions": False}},
    "action-format": {"strict": {"enable_edit": True, "recover_actions": False},
                      "recover": {"enable_edit": True, "recover_actions": True}},
}


def docker_command(image, snapshot, reports, arm, budget, *, comparison="edit"):
    if comparison not in COMPARISONS or arm not in COMPARISONS[comparison]:
        raise ValueError("unknown experiment arm")
    command = ["docker", "run", "--rm", "--read-only", "--tmpfs", "/tmp:rw,size=2g",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "512",
        "-e", "LLM_API_KEY", "-e", "LLM_BASE_URL", "-e", "LLM_MODEL",
        "--mount", f"type=bind,source={reports},target=/results",
        "--mount", f"type=bind,source={snapshot},target=/repo,readonly",
        "--entrypoint", "python", image, "/repo/scripts/evaluate_examples.py",
        "--suite", "coding-edit", "--llm", "--budget", str(budget), "--quiet",
        "--diagnostics", "--report", f"/results/{arm}.json"]
    features = COMPARISONS[comparison][arm]
    if features["enable_edit"]:
        command.append("--enable-edit")
    if features["recover_actions"]:
        command.append("--recover-actions")
    return command


def snapshot_checkout(repo, destination):
    def git(*args):
        return subprocess.run(["git", *args], cwd=repo, check=True,
                              capture_output=True, text=True).stdout.strip()
    if git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("commit or set aside tracked changes before the paired experiment")
    sha = git("rev-parse", "HEAD")
    archive = subprocess.run(["git", "archive", "--format=tar", sha], cwd=repo,
                             check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        if any(not (m.isfile() or m.isdir()) for m in bundle.getmembers()):
            raise ValueError("snapshot requires regular tracked files")
        bundle.extractall(destination, filter="data")
    return sha


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="explicitly enable the two paid runs")
    parser.add_argument("--image", default="its-ia:edit-experiment")
    parser.add_argument("--budget-per-arm", type=int, default=3000)
    parser.add_argument("--comparison", choices=list(COMPARISONS), default="edit")
    parser.add_argument("--order", choices=["control-first", "treatment-first", "baseline-first", "edit-first"], default="control-first")
    args = parser.parse_args(argv)
    if args.budget_per_arm <= 0:
        parser.error("budget per arm must be positive")
    print(f"One pair: {args.comparison}; qwen3.8-27b-noreason; <= {args.budget_per_arm * 2} weighted tokens total; "
          "4 calls/task, max output 1024; no automatic repeats.", flush=True)
    if not args.live:
        print("No API calls. Build the image and add --live to run the pair.")
        return 0
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["LLM_MODEL"] = "qwen3.8-27b-noreason"
    env.setdefault("LLM_BASE_URL", "https://api.neuraldeep.ru/v1")
    order = list(COMPARISONS[args.comparison])
    if args.order in ("treatment-first", "edit-first"):
        order.reverse()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="its-ia-edit-snapshot-") as temporary:
        snapshot = Path(temporary)
        sha = snapshot_checkout(repo, snapshot)
        image = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", args.image],
                               check=True, capture_output=True, text=True).stdout.strip()
        env["LLM_API_KEY"] = env.get("LLM_API_KEY") or getpass.getpass("API key from NeuralDeep (hidden): ").strip()
        if not env["LLM_API_KEY"] or any(c.isspace() for c in env["LLM_API_KEY"]) or env["LLM_API_KEY"].upper().startswith(("NGU26-", "НГУ-")):
            raise ValueError("use the account API key, not the invite code")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        reports = repo / "artifacts" / (args.comparison + "-experiment-" + stamp + "-" + uuid.uuid4().hex[:8])
        reports.mkdir(parents=True, exist_ok=False)
        pair = {"source_commit": sha, "image_id": image, "model": env["LLM_MODEL"],
                "suite": "coding-edit-v1; development diagnostics, not hidden score",
                "comparison": args.comparison, "arms_config": COMPARISONS[args.comparison],
                "order": order, "budget_per_arm": args.budget_per_arm,
                "max_pair_budget": 2 * args.budget_per_arm, "max_calls_per_task": 4,
                "max_output_tokens": 1024, "arms": {}, "status": "incomplete"}
        summary_path = reports / "comparison.json"
        try:
            for arm in order:
                print(f"Starting {arm}; report {reports / (arm + '.json')}", flush=True)
                run = subprocess.run(docker_command(image, snapshot, reports, arm, args.budget_per_arm, comparison=args.comparison),
                                     env=env, cwd=repo, timeout=420)
                path = reports / (arm + ".json")
                summary = json.loads(path.read_text(encoding="utf-8"))["summary"] if path.is_file() else {}
                pair["arms"][arm] = {"exit_code": run.returncode, "summary": summary}
                if run.returncode or not summary or summary.get("usage_uncertain") or summary.get("agent_exit_code"):
                    pair["status"] = "stopped_after_error_or_uncertain_usage"
                    return 1
            pair["status"] = "completed"
            return 0
        finally:
            pair["elapsed_seconds"] = round(time.monotonic() - started, 3)
            pair["reported_weighted_tokens"] = round(sum(a["summary"].get("weighted_tokens", 0) for a in pair["arms"].values()), 1)
            pair["usage_complete"] = pair["status"] == "completed"
            pair["weighted_tokens"] = pair["reported_weighted_tokens"] if pair["usage_complete"] else None
            summary_path.write_text(json.dumps(pair, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Pair summary: {summary_path}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
