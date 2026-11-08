import json
from pathlib import Path
import shutil
import tempfile
import unittest
from dataclasses import replace

from harness.tasks import Task
from harness.solvers import solve
from harness.execution import execute

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/task-dir"


class BaselineTests(unittest.TestCase):
    def test_labels_are_not_exposed_and_math_uses_current_input(self):
        original = Task.load(EXAMPLES / "math_0004")
        self.assertFalse(hasattr(original, "expected"))
        changed = replace(original, instruction=original.instruction.replace("1669", "1000"))
        self.assertEqual(solve(changed).answer, "1066")

    def test_unknown_operation_is_not_silently_ignored(self):
        original = Task.load(EXAMPLES / "math_0004")
        changed = replace(original, instruction=original.instruction.replace(
            "How many boxes", "It loses an unknown number of boxes. How many boxes"))
        self.assertEqual(solve(changed).status, "unsupported")
        self.assertIsNone(solve(changed).answer)

    def test_integer_floor_on_every_split(self):
        original = Task.load(EXAMPLES / "math_0000")
        changed = replace(original, instruction=original.instruction.replace("1752", "19"))
        # 19//2=9; *2=18; //3=6; *2=12; //3=4
        self.assertEqual(solve(changed).answer, "4")

    def test_missing_knowledge_creates_no_answer(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "task"
            shutil.copytree(EXAMPLES / "search_0005", target)
            (target / "workspace/kb/company_fjord_data.md").unlink()
            result = execute(Task.load(target))
            self.assertEqual(result["status"], "insufficient_data")
            self.assertFalse((target / "answer.txt").exists())

    def test_search_uses_changed_knowledge(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "task"
            shutil.copytree(EXAMPLES / "search_0001", target)
            path = target / "workspace/kb/person_irina_smith.md"
            path.write_text(path.read_text().replace("1983", "2001"))
            self.assertEqual(solve(Task.load(target)).answer, "2001")

    def test_missing_rows_are_not_treated_as_complete_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "task"
            shutil.copytree(EXAMPLES / "data_analysis_0002", target)
            path = target / "workspace/sales.csv"
            path.write_text("\n".join(path.read_text().splitlines()[:-1]) + "\n")
            self.assertEqual(solve(Task.load(target)).status, "insufficient_data")

    def test_coding_is_unsupported_not_declared_impossible(self):
        result = solve(Task.load(EXAMPLES / "coding_0003"))
        self.assertEqual(result.status, "unsupported")
        self.assertIsNone(result.answer)

    def test_zero_matching_csv_rows_is_a_valid_answer(self):
        original = Task.load(EXAMPLES / "data_analysis_0002")
        changed = replace(original, instruction=original.instruction.replace("'widget'", "'absent'"))
        self.assertEqual(solve(changed).answer, "0")


if __name__ == "__main__":
    unittest.main()
