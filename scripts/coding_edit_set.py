"""Three authored coding diagnostics; evaluator references stay outside inputs.

These are development cases, not a representative or held-out benchmark.
Baseline may still use its Python tool to edit sources: only availability of
the declared edit action changes between the two arms.
"""
import json
from pathlib import Path


MONEY_SOURCE = '''"""Accounting helpers used by a small order-processing application.

Prices enter the application as strings. Decimal arithmetic avoids binary-float
rounding. Utilities in this module are also used outside the report endpoint;
repairs must preserve their behavior and the public function signatures.
"""
from decimal import Decimal, ROUND_HALF_UP


def decimal_value(value):
    """Convert a value without introducing intermediate binary arithmetic."""
    return Decimal(str(value))


def money_text(value):
    """Format an amount to two decimal places using commercial rounding."""
    return str(decimal_value(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def line_amount(row):
    """Unsigned line amount before applying the transaction direction."""
    return decimal_value(row["price"]) * int(row["qty"])


def total_quantity(rows):
    """Quantity across records, irrespective of transaction direction."""
    return sum(int(row["qty"]) for row in rows)


def group_by_kind(rows):
    """Return a fresh grouping; do not mutate the supplied records."""
    groups = {}
    for row in rows:
        groups.setdefault(row["kind"], []).append(row)
    return groups


def kind_counts(rows):
    """Count records rather than item quantities for a dashboard widget."""
    return {kind: len(group) for kind, group in group_by_kind(rows).items()}


def net_total(rows):
    """Calculate the net amount of an iterable of transaction dictionaries."""
    return sum((line_amount(row) for row in rows), Decimal("0"))


def price_bounds(rows):
    """Return minimum and maximum unit prices, or None for no records."""
    prices = [decimal_value(row["price"]) for row in rows]
    return (min(prices), max(prices)) if prices else None


def quantities_by_kind(rows):
    """Aggregate quantities while retaining every encountered kind."""
    totals = {}
    for row in rows:
        kind = row["kind"]
        totals[kind] = totals.get(kind, 0) + int(row["qty"])
    return totals


def filter_kind(rows, kind):
    """Select original record objects without modifying their contents."""
    return [row for row in rows if row["kind"] == kind]


def summary_rows(rows):
    """Return formatted unsigned amounts for a legacy export format."""
    return [money_text(line_amount(row)) for row in rows]


def contains_kind(rows, kind):
    """Support generators and stop as soon as a matching record is seen."""
    return any(row["kind"] == kind for row in rows)


def copy_records(rows):
    """Make independent shallow dictionaries for downstream enrichment."""
    return [dict(row) for row in rows]


def apply_discount(price, percent):
    """Return an unrounded discounted unit price for an external calculator."""
    rate = decimal_value(percent) / Decimal("100")
    return decimal_value(price) * (Decimal("1") - rate)


def chunk_records(rows, size):
    """Yield batches of at most size records, including a final short batch."""
    if size <= 0:
        raise ValueError("size must be positive")
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def add_amounts(left, right):
    """Compatibility helper used by callers that already parsed their data."""
    return decimal_value(left) + decimal_value(right)


def unsigned_totals_by_kind(rows):
    """Return positive line totals grouped by their original kind labels.

    Unlike net_total, this legacy export function does not apply signs or
    reject unknown categories; downstream consumers decide how to display them.
    """
    totals = {}
    for row in rows:
        kind = row["kind"]
        totals[kind] = totals.get(kind, Decimal("0")) + line_amount(row)
    return totals


def select_price_range(rows, minimum, maximum):
    """Select records with an inclusive unit-price range, preserving order."""
    low, high = decimal_value(minimum), decimal_value(maximum)
    if low > high:
        raise ValueError("minimum exceeds maximum")
    return [row for row in rows if low <= decimal_value(row["price"]) <= high]


def running_unsigned_totals(rows):
    """Yield running unsigned amounts without buffering a one-pass source."""
    total = Decimal("0")
    for row in rows:
        total += line_amount(row)
        yield total
'''


def build_coding_edit_set(root):
    root = Path(root)
    labels = {}

    def add(name, instruction, reward, files, private_check):
        folder = root / name
        folder.mkdir(parents=True)
        raw = {"task_id": name, "task_type": "coding", "instruction": instruction,
               "reward": reward, "check": "unittest", "expected": "tests_pass"}
        (folder / "task.json").write_text(json.dumps(raw), encoding="utf-8")
        for name_, content in files.items():
            path = folder / "workspace" / name_
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        labels[name] = {**raw, "private_check": private_check, "validation_group": name}

    add("coding_ledger", "Repair net_total(rows) in money.py. Each record has kind, qty and price. "
        "Quantities are nonnegative integers and prices are decimal strings. Add charge amounts and subtract "
        "refund amounts. Reject any other kind with ValueError. Return an exact Decimal, including Decimal zero "
        "for empty input; accept a one-pass iterable and do not mutate records. Preserve all other helpers and tests.",
        3, {"money.py": MONEY_SOURCE, "test_money.py": '''import unittest
from decimal import Decimal
from money import net_total, money_text
class T(unittest.TestCase):
    def test_refund(self):
        rows = [dict(kind="charge", qty=2, price="12.50"), dict(kind="refund", qty=1, price="7")]
        self.assertEqual(net_total(rows), Decimal("18.00"))
    def test_format(self):
        self.assertEqual(money_text("1.235"), "1.24")
'''}, '''from decimal import Decimal
from money import net_total, chunk_records, apply_discount, group_by_kind
rows = [dict(kind="refund", qty=3, price="0.10"), dict(kind="charge", qty=1, price="0.20")]
before = [dict(r) for r in rows]
assert net_total(iter(rows)) == Decimal("-0.10") and rows == before
assert isinstance(net_total([]), Decimal) and net_total([]) == 0
try:
    net_total([dict(kind="gift", qty=1, price="2")])
except ValueError:
    pass
else:
    raise AssertionError("unknown kind was accepted")
assert list(chunk_records(range(5), 2)) == [[0,1],[2,3],[4]]
assert apply_discount("10", "12.5") == Decimal("8.75")
assert len(group_by_kind(rows)["refund"]) == 1
''')
    add("coding_intervals", "Repair merge_intervals(intervals) in intervals.py. Input is an iterable of "
        "closed integer intervals [start, end], start <= end. Return a sorted list of fresh lists containing "
        "their union. Merge intervals sharing an endpoint, but not separated integer intervals. Preserve "
        "nested intervals correctly and never mutate the input or tests.", 2,
        {"intervals.py": '''def merge_intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start < merged[-1][1]:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return merged
''', "test_intervals.py": '''import unittest
from intervals import merge_intervals
class T(unittest.TestCase):
    def test_touch(self): self.assertEqual(merge_intervals([[1,3],[3,5]]), [[1,5]])
    def test_separate(self): self.assertEqual(merge_intervals([[5,6],[1,2]]), [[1,2],[5,6]])
'''}, '''from intervals import merge_intervals
import random
rng = random.Random(29)
for _ in range(40):
    pairs = [sorted([rng.randrange(-5, 6), rng.randrange(-5, 6)]) for _ in range(7)]
    before = [p[:] for p in pairs]
    reference = []
    for lo, hi in sorted(pairs):
        if reference and lo <= reference[-1][1]:
            reference[-1][1] = max(reference[-1][1], hi)
        else:
            reference.append([lo, hi])
    assert merge_intervals(iter(pairs)) == reference and pairs == before
assert merge_intervals([]) == []
assert merge_intervals([[1,10],[2,3]]) == [[1,10]]
''')
    add("coding_tags", "Repair normalize_tag in normalization.py and format_tags in formatter.py. "
        "Normalize each string by Unicode casefolding, trimming, and collapsing runs of whitespace to one space. "
        "Skip empty normalized values, remove duplicate normalized tags, preserve first-occurrence order, "
        "and join with ', '. Keep punctuation. Accept any iterable of strings and preserve the input and tests.",
        4, {"normalization.py": '''def normalize_tag(value):
    return value.strip().lower()
''', "formatter.py": '''from normalization import normalize_tag

def format_tags(values):
    return ", ".join(sorted({normalize_tag(value) for value in values}))
''', "test_formatter.py": '''import unittest
from normalization import normalize_tag
from formatter import format_tags
class T(unittest.TestCase):
    def test_order(self): self.assertEqual(format_tags(["Beta", "ALPHA", "beta", ""]), "beta, alpha")
    def test_spaces(self): self.assertEqual(normalize_tag("  Red   Fox  "), "red fox")
'''}, '''from formatter import format_tags
from normalization import normalize_tag
values = ["Straße", "STRASSE", "B\\tC", "  ", "X!"]
before = values[:]
assert format_tags(iter(values)) == "strasse, b c, x!" and values == before
assert format_tags([]) == ""
assert normalize_tag(" A\\nB! ") == "a b!"
''')
    return labels
