import json
import os
from pathlib import Path
import tempfile
from harness.solvers import solve


def atomic_text(path: Path, content: str):
    fd, temporary = tempfile.mkstemp(prefix=".answer-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def execute(task):
    result = solve(task)
    if result.status == "solved":
        atomic_text(task.directory / "answer.txt", result.answer + "\n")
    record = {"task_id": task.task_id, "reward": task.reward,
              **result.to_dict(), "input_tokens": 0, "output_tokens": 0,
              "weighted_tokens": 0, "backend": "deterministic"}
    atomic_text(task.directory / "its_ia_result.json", json.dumps(record, ensure_ascii=False) + "\n")
    return record
