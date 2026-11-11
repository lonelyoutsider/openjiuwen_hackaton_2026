#!/usr/bin/env python3
"""Isolated local evaluator. Only this evaluator may read expected labels."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["openjiuwen", "stdlib"], default="openjiuwen")
    parser.add_argument("--llm", action="store_true", help="allow bounded live calls using LLM_API_KEY")
    parser.add_argument("--budget", type=int, default=3000)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    source = repo / "examples/task-dir"
    labels = {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in source.glob("*/task.json")}
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "tasks"
        shutil.copytree(source, root)
        for path in root.glob("*/task.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            data.pop("expected", None)
            path.write_text(json.dumps(data), encoding="utf-8")
        options = ["--budget", str(args.budget), "--time-limit", "300", "--max-calls-per-task", "4"] if args.llm else ["--no-llm"]
        subprocess.run([sys.executable, str(repo / "run_agent.py"), "--tasks-dir", str(root),
                        "--engine", args.engine, *options], check=True, cwd=repo, timeout=360)
        records = [json.loads(p.read_text(encoding="utf-8")) for p in root.glob("*/its_ia_result.json")]
        earned, solved = 0, 0
        for name, label in sorted(labels.items()):
            answer = root / name / "answer.txt"
            correct = False
            if answer.is_file():
                text = answer.read_text(encoding="utf-8").strip()
                if label["check"] == "exact_int":
                    try:
                        correct = int(text) == int(label["expected"])
                    except ValueError:
                        pass
                elif label["check"] == "exact_str":
                    correct = text == label["expected"]
                elif label["check"] == "unittest" and text == "DONE":
                    result = subprocess.run([sys.executable, "test_mylib.py"],
                                            cwd=root/name/"workspace", capture_output=True, timeout=10)
                    correct = result.returncode == 0
            solved += int(correct)
            earned += label["reward"] * int(correct)
            print(name, "PASS" if correct else "UNSOLVED")
        print(json.dumps({"dataset": "8 public examples; not hidden score",
                          "engine": args.engine, "correct": solved, "tasks": len(labels),
                          "reward": earned, "available_reward": sum(t["reward"] for t in labels.values()),
                          "llm_calls": sum(r.get("llm_calls", 0) for r in records),
                          "weighted_tokens": sum(r["weighted_tokens"] for r in records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
