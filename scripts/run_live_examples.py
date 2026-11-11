#!/usr/bin/env python3
"""Run a bounded live-API example experiment inside the built Docker image."""
import argparse
import getpass
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="its-ia:agent")
    parser.add_argument("--budget", type=int, default=3000)
    args = parser.parse_args()
    if args.budget <= 0:
        parser.error("budget must be positive")
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["LLM_API_KEY"] = env.get("LLM_API_KEY") or getpass.getpass("API key from NeuralDeep (hidden): ").strip()
    if not env["LLM_API_KEY"] or env["LLM_API_KEY"].upper().startswith(("NGU26-", "НГУ-")):
        parser.error("copy the API key from the account, not the invite code")
    env.setdefault("LLM_BASE_URL", "https://api.neuraldeep.ru/v1")
    command = ["docker", "run", "--rm", "--read-only", "--tmpfs", "/tmp:rw,size=2g",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "512",
               "-e", "LLM_API_KEY", "-e", "LLM_BASE_URL", "--mount",
               f"type=bind,source={repo},target=/repo,readonly", "--entrypoint", "python", args.image,
               "/repo/scripts/evaluate_examples.py", "--llm", "--budget", str(args.budget)]
    print(f"Live experiment: 8 public examples, budget {args.budget}, up to 4 calls per unresolved task.", flush=True)
    # Credentials travel via the child environment, never in command arguments.
    return subprocess.run(command, env=env, cwd=repo).returncode


if __name__ == "__main__":
    raise SystemExit(main())
