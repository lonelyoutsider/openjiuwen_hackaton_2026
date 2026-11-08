"""Conservative parsers for documented example families; no stored answers."""
import csv
from dataclasses import dataclass, asdict
import re
from harness.tasks import Task


@dataclass(frozen=True)
class Result:
    status: str
    answer: str | None = None
    reason: str = ""

    def to_dict(self):
        return asdict(self)


def _question(instruction, tool_prefix):
    question, sep, suffix = instruction.partition(tool_prefix)
    if not sep or not suffix.startswith(" "):
        return None
    return question.strip()


def solve_math(task):
    question = _question(task.instruction, "Compute it with the bash tool")
    if question is None:
        return Result("unsupported", reason="unknown math instruction")
    match = re.fullmatch(r"A warehouse starts with (\d+) boxes\. (.*?)How many boxes does it have at the end\?", question)
    if not match:
        return Result("unsupported", reason="unknown warehouse grammar")
    value, rest = int(match[1]), match[2]
    operations = [
        (r"It ships (\d+) boxes per day for (\d+) days\. ", lambda v, a, b: v - a*b),
        (r"It receives (\d+) deliveries of (\d+) boxes each\. ", lambda v, a, b: v + a*b),
        (r"Then the stock is split equally into (\d+) warehouses and it keeps one share \(rounded down\)\. ", lambda v, a: v // a),
        (r"Then the stock is doubled by merging with a sister warehouse\. ", lambda v: 2*v),
    ]
    while rest:
        for pattern, operation in operations:
            step = re.match(pattern, rest)
            if step:
                args = [int(v) for v in step.groups()]
                if "split equally" in step[0] and args[0] == 0:
                    return Result("insufficient_data", reason="division into zero warehouses")
                value = operation(value, *args)
                if value < 0:
                    return Result("insufficient_data", reason="stock becomes negative")
                rest = rest[step.end():]
                break
        else:
            return Result("unsupported", reason="unrecognized warehouse operation")
    return Result("solved", str(value))


def _kb(task):
    folder = (task.workspace() / "kb").resolve()
    if not folder.is_relative_to(task.workspace()) or not folder.is_dir():
        raise ValueError("knowledge base missing")
    entries = {}
    files = sorted(folder.glob("*.md"))
    if len(files) > 2000:
        raise ValueError("knowledge base too large for deterministic baseline")
    for path in files:
        if path.is_symlink() or path.stat().st_size > 262144:
            raise ValueError("invalid knowledge base file")
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        if not lines or not lines[0].startswith("# "):
            raise ValueError("unknown knowledge base format")
        name = lines[0][2:].strip()
        if name in entries:
            raise ValueError("duplicate entity name")
        fields = {}
        for line in lines[1:]:
            if not line.strip():
                continue
            key, sep, value = line.partition(":")
            if not sep or key.strip() in fields:
                raise ValueError("ambiguous knowledge base field")
            fields[key.strip()] = value.strip()
        entries[name] = fields
    return entries


def solve_search(task):
    question = _question(task.instruction, "Use the file tools or bash")
    prefix = "The directory kb/ contains a small knowledge base of markdown files. "
    if question is None or not question.startswith(prefix):
        return Result("unsupported", reason="unknown search grammar")
    question = question[len(prefix):]
    born = re.fullmatch(r"In which year was ([^?\n]+) born\?", question)
    city = re.fullmatch(r"In which city is the headquarters of ([^?\n]+)'s employer\?", question)
    if not born and not city:
        return Result("unsupported", reason="unknown search relation")
    entries = _kb(task)
    person = entries.get((born or city)[1], {})
    if born:
        answer = person.get("Born")
        if answer and not re.fullmatch(r"\d{4}", answer):
            return Result("insufficient_data", reason="birth year not explicit")
    else:
        answer = entries.get(person.get("Employer"), {}).get("Headquarters")
    if not answer:
        return Result("insufficient_data", reason="required relation absent from local KB")
    return Result("solved", answer)


def solve_data(task):
    question = _question(task.instruction, "Use bash with python3 to compute it.")
    if question is None:
        return Result("unsupported", reason="unknown data instruction")
    match = re.fullmatch(
        r"The file sales\.csv has columns order_id,region,product,month,units,price \((\d+) rows\)\. "
        r"How many units of product '([^'\n]+)' were sold in months (\d+) through (\d+) inclusive\?", question)
    if not match:
        return Result("unsupported", reason="unknown CSV query")
    row_count, product, low, high = int(match[1]), match[2], int(match[3]), int(match[4])
    if not 1 <= low <= high <= 12:
        return Result("insufficient_data", reason="invalid month range")
    path = task.workspace() / "sales.csv"
    if path.is_symlink() or path.stat().st_size > 8_000_000:
        raise ValueError("invalid CSV file")
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ["order_id", "region", "product", "month", "units", "price"]:
            raise ValueError("unexpected CSV schema")
        total, seen = 0, 0
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("malformed CSV row")
            month, units = int(row["month"]), int(row["units"])
            if not 1 <= month <= 12:
                raise ValueError("invalid month in CSV")
            if row["product"] == product and low <= month <= high:
                total += units
            seen += 1
        if seen != row_count:
            return Result("insufficient_data", reason="CSV row count differs from task description")
    return Result("solved", str(total))


def solve(task: Task):
    handler = {"math": solve_math, "search": solve_search, "data_analysis": solve_data}.get(task.task_type)
    if handler is None:
        return Result("unsupported", reason="no deterministic solver; LLM fallback pending")
    try:
        return handler(task)
    except (ValueError, OSError, KeyError, csv.Error) as error:
        return Result("insufficient_data", reason=str(error))
