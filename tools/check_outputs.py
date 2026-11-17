"""Strict shape checker for a forecast output directory (standard library only).

Usage: python3 tools/check_outputs.py <out-dir> [expected ids...]
Exit code 0 when every file is valid, 1 otherwise.
"""

import json
import math
import sys
from pathlib import Path

HOURS = list(range(2, 25))


def check_file(path):
    problems = []
    raw = path.read_bytes()
    if len(raw) > 65536:
        problems.append(f"{len(raw)} bytes > 65536")
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"not UTF-8 JSON: {exc}"]
    if not isinstance(doc, dict):
        return ["top level is not an object"]
    if set(doc) != {"hours"}:
        problems.append(f"keys are {sorted(doc)}, not exactly ['hours']")
    rows = doc.get("hours")
    if not isinstance(rows, list):
        return problems + ["hours is not a list"]
    if len(rows) != 23:
        problems.append(f"{len(rows)} rows, not 23")
    seen = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(f"row {index} is not an object")
            continue
        if set(row) != {"hour", "q"}:
            problems.append(f"row {index} keys are {sorted(row)}")
        hour = row.get("hour")
        if isinstance(hour, bool) or not isinstance(hour, int):
            problems.append(f"row {index} hour is not an int")
        else:
            seen.append(hour)
        q = row.get("q")
        if not isinstance(q, list) or len(q) != 5:
            problems.append(f"row {index} q is not five values")
            continue
        previous = None
        for level, value in zip([0.05, 0.25, 0.5, 0.75, 0.95], q):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                problems.append(f"hour {hour} q@{level} is not a number")
                continue
            if not math.isfinite(value):
                problems.append(f"hour {hour} q@{level} is not finite")
                continue
            if value <= 0:
                problems.append(f"hour {hour} q@{level} is {value} <= 0")
            if value > 1e9:
                problems.append(f"hour {hour} q@{level} is {value} > 1e9")
            if previous is not None and value < previous:
                problems.append(f"hour {hour} q@{level} decreases")
            previous = value
            rounded = round(value * 100) / 100
            if abs(rounded - value) > 1e-6:
                problems.append(f"hour {hour} q@{level} has more than 2 decimals")
    if sorted(seen) != HOURS:
        problems.append(f"hours are not 2..24 exactly once: {seen}")
    return problems


def main():
    out_dir = Path(sys.argv[1])
    expected = sys.argv[2:]
    paths = sorted(out_dir.glob("*.out"))
    if not paths:
        print(f"FAIL: no *.out files in {out_dir}")
        return 1
    failed = 0
    for path in paths:
        problems = check_file(path)
        size = path.stat().st_size
        if problems:
            failed += 1
            print(f"FAIL {path.name} ({size} bytes)")
            for problem in problems[:10]:
                print(f"     - {problem}")
        else:
            rows = json.loads(path.read_text(encoding="utf-8"))["hours"]
            print(f"OK   {path.name} ({size} bytes) hours {rows[0]['hour']}..{rows[-1]['hour']}")
    if expected:
        have = {path.stem for path in paths}
        missing = sorted(set(expected) - have)
        if missing:
            failed += 1
            print(f"FAIL missing outputs: {missing}")
    print("ALL VALID" if not failed else f"{failed} INVALID")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
