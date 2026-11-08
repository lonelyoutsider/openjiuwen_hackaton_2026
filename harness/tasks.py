from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Task:
    directory: Path
    task_id: str
    task_type: str
    instruction: str
    reward: int

    @classmethod
    def load(cls, directory: Path):
        raw = json.loads((directory / "task.json").read_text(encoding="utf-8"))
        # Explicit allowlist: expected is never exposed to the solver or planner.
        reward = raw["reward"]
        if type(reward) is not int or reward < 0:
            raise ValueError("reward must be a nonnegative integer")
        for key in ("task_id", "task_type", "instruction"):
            if not isinstance(raw[key], str):
                raise ValueError(f"{key} must be a string")
        return cls(directory.resolve(), raw["task_id"], raw["task_type"],
                   raw["instruction"], reward)

    def workspace(self):
        path = (self.directory / "workspace").resolve()
        if not path.is_relative_to(self.directory) or not path.is_dir():
            raise ValueError("missing or invalid workspace")
        return path


def load_tasks(root: Path):
    root = root.resolve(strict=True)
    tasks = []
    for path in sorted(root.glob("*/task.json")):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("task path escapes tasks root")
        tasks.append(Task.load(path.parent))
    ids = [task.task_id for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate task IDs")
    return tasks
