"""Small authored validation suite, not an official or representative test set.

Eight solvable tasks across four types, plus two missing-data tasks. Labels
and extra coding checks are for the offline evaluator only.
"""
import json
from pathlib import Path


def build_validation_set(root):
    root = Path(root)
    labels = {}

    def add(name, kind, instruction, reward, expected, files=None, private_check=None):
        folder = root / name
        folder.mkdir(parents=True)
        raw = {"task_id": name, "task_type": kind, "instruction": instruction,
               "reward": reward, "expected": expected,
               "check": "unittest" if kind == "coding" else "exact_str"}
        (folder / "task.json").write_text(json.dumps(raw), encoding="utf-8")
        for path, content in (files or {}).items():
            target = folder / "workspace" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        labels[name] = {**raw, "private_check": private_check}

    add("math_delivery", "math", "A delivery van carried 240 parcels. It dropped off three batches of 28 parcels and then collected 17 parcels. How many parcels remain? Return only the integer.", 2, "173")
    add("math_grid", "math", "A sheet has 18 rows and 24 columns of cells. Exactly one quarter of all cells are shaded. How many cells are NOT shaded? Return only the integer.", 4, "324")
    kb = {"kb/nia.md": "# Nia Park\nBorn: 1994\nEmployer: Cedar Systems\nMentor: Leo Wong\n",
          "kb/leo.md": "# Leo Wong\nBorn: 1988\nEmployer: Aster Devices\n",
          "kb/mira.md": "# Mira Sen\nBorn: 1982\nEmployer: Aster Devices\n",
          "kb/aster.md": "# Aster Devices\nFounded: 2014\nHeadquarters: Riga\n"}
    add("search_mentor_company", "search", "Using only kb/, give the founding year of the company that employs Nia Park's mentor. Return only the year.", 3, "2014", kb)
    add("search_earliest", "search", "Among the people in kb/ employed by Aster Devices, who was born earliest? Return only the full name.", 1, "Mira Sen", kb)
    add("search_missing", "search", "Using only kb/, name the university that awarded Nia Park her bachelor's degree. An exact answer is required; do not infer missing facts.", 5, None, kb)
    sales = "order_id,region,product,month,units,price\n1,north,widget,1,3,12.5\n2,south,widget,2,5,9\n3,north,gizmo,2,4,8\n4,north,widget,3,2,12.5\n5,north,widget,2,1,15\n"
    add("data_revenue", "data_analysis", "In sales.csv, calculate total revenue (units multiplied by price) for the north region in months 2 and 3 together. Return the numeric result with no currency symbol.", 2, "72", {"sales.csv": sales})
    add("data_missing_costs", "data_analysis", "Determine the exact net profit for all transactions in sales.csv after deducting all business expenses. Use only the supplied data; do not assume an expense ratio or that expenses are zero.", 5, None, {"sales.csv": sales})
    units = "product,units\nbolt,7\nnut,9\nbolt,4\nnut,2\ngear,3\n"
    add("data_tie", "data_analysis", "Aggregate units by product in inventory.csv. Which product has the largest total? Break a tie by taking the alphabetically first product name. Return only that name.", 3, "bolt", {"inventory.csv": units})
    normalize_tests = "import unittest\nfrom text_utils import normalize\nclass T(unittest.TestCase):\n    def test_spaces(self): self.assertEqual(normalize('  Hello   WORLD  '),'hello world')\n    def test_empty(self): self.assertEqual(normalize(''), '')\n"
    add("coding_normalize", "coding", "Fix normalize(text) in text_utils.py. It must lowercase text, trim leading/trailing whitespace and replace each run of whitespace with one space, preserving punctuation. Keep tests unchanged. Return DONE after fixing the source.", 4, "tests_pass", {
        "text_utils.py": "def normalize(text):\n    return text.strip()\n", "test_text_utils.py": normalize_tests},
        "from text_utils import normalize\nassert normalize('A\\tB\\nC!') == 'a b c!'\nassert normalize('  ÉCOLE  ') == 'école'\n")
    unique_tests = "import unittest\nfrom sequence_utils import unique_in_order\nclass T(unittest.TestCase):\n    def test_order(self): self.assertEqual(unique_in_order([3,1,3,2,1]),[3,1,2])\n    def test_empty(self): self.assertEqual(unique_in_order([]),[])\n"
    add("coding_unique", "coding", "Repair unique_in_order(values) in sequence_utils.py. For an iterable of hashable values return a new list containing each distinct value once, preserving first-occurrence order. Do not mutate the input or edit tests. Return DONE when finished.", 2, "tests_pass", {
        "sequence_utils.py": "def unique_in_order(values):\n    return list(set(values))\n", "test_sequence_utils.py": unique_tests},
        "from sequence_utils import unique_in_order\nx=['b','a','b','c']; assert unique_in_order(x)==['b','a','c']; assert x==['b','a','b','c']\nassert unique_in_order(v for v in [4,2,4,1]) == [4,2,1]\n")
    # Revenue permits a decimal representation such as 72.0; all other values
    # are exact strings. Additional checks never enter task.json or workspace.
    labels["data_revenue"]["check"] = "exact_number"
    return labels
