"""
scripts/check_invariants.py — Verify that key code invariants are still enforced.

Checks the five invariants documented in SYSTEM_OVERVIEW.md whose violation
causes silent data corruption rather than an immediate error or crash.

Usage:
    python scripts/check_invariants.py

Exit codes:
    0  all invariants present
    1  one or more invariants violated
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

ROOT          = Path(__file__).parent.parent
COLUMN_MAPPER = ROOT / "column_mapper.py"
DEDUP         = ROOT / "dedup.py"
FILE_IO       = ROOT / "file_io.py"


class Result(NamedTuple):
    ok:        bool
    invariant: str   # short name shown in the report
    detail:    str   # what was found (or what is wrong)
    location:  str   # file and function where the fix goes
    fix:       str   # exact line(s) to restore


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fn_body(src: str, fn_name: str) -> str:
    """Return source text from the start of fn_name to the next top-level def."""
    start = src.find(f"def {fn_name}(")
    if start == -1:
        return ""
    end = src.find("\ndef ", start + 1)
    return src[start:end] if end != -1 else src[start:]


# ---------------------------------------------------------------------------
# Invariant 1 — reset_index(drop=True) in apply_column_mapping
# ---------------------------------------------------------------------------

def check_reset_index() -> Result:
    src  = _read(COLUMN_MAPPER)
    body = _fn_body(src, "apply_column_mapping")
    ok   = "reset_index(drop=True)" in body

    return Result(
        ok        = ok,
        invariant = "reset_index(drop=True) in apply_column_mapping",
        detail    = (
            "Present — mapped DataFrame always has a clean RangeIndex" if ok
            else "MISSING — find_duplicate_rows returns positional integers; "
                 "without a clean RangeIndex, drop(index=...) silently removes the wrong rows"
        ),
        location  = "column_mapper.py — last line of apply_column_mapping",
        fix       = "return renamed.reset_index(drop=True)",
    )


# ---------------------------------------------------------------------------
# Invariant 2 — parse_dates=False on every read_csv / read_excel call
# ---------------------------------------------------------------------------

def check_parse_dates() -> Result:
    src   = _read(FILE_IO)
    lines = src.splitlines()

    violations: list[int] = []
    for i, line in enumerate(lines, start=1):
        if re.search(r"pd\.read_(csv|excel)\(", line):
            # Check this line plus the next 6 to handle multi-line calls
            block = "\n".join(lines[i - 1 : i + 6])
            if "parse_dates=False" not in block:
                violations.append(i)

    ok = len(violations) == 0
    return Result(
        ok        = ok,
        invariant = "parse_dates=False on every read_csv / read_excel call",
        detail    = (
            "All read_csv / read_excel calls include parse_dates=False" if ok
            else f"parse_dates=False missing near line(s) {', '.join(str(v) for v in violations)} of file_io.py"
        ),
        location  = f"file_io.py — line(s) {', '.join(str(v) for v in violations) if violations else 'n/a'}",
        fix       = "pd.read_csv(path, encoding='utf-8', parse_dates=False)\n"
                    "pd.read_excel(xf, sheet_name=sheet, engine='openpyxl', parse_dates=False)",
    )


# ---------------------------------------------------------------------------
# Invariant 3 — ~df.columns.duplicated() guard before every pd.concat
# ---------------------------------------------------------------------------

def check_columns_deduped() -> Result:
    violations: list[str] = []

    for filepath in (FILE_IO, DEDUP):
        src          = _read(filepath)
        concat_count = src.count("pd.concat(")
        dedup_count  = src.count("columns.duplicated()")
        if dedup_count < concat_count:
            violations.append(
                f"{filepath.name}: {concat_count} pd.concat call(s) "
                f"but only {dedup_count} columns.duplicated() guard(s)"
            )

    ok = len(violations) == 0
    return Result(
        ok        = ok,
        invariant = "~df.columns.duplicated() guard before every pd.concat",
        detail    = (
            "Guard present before every pd.concat in file_io.py and dedup.py" if ok
            else "; ".join(violations)
        ),
        location  = "file_io.py and/or dedup.py — immediately before each pd.concat call",
        fix       = "master_df = master_df.loc[:, ~master_df.columns.duplicated()]\n"
                    "new_rows  = new_rows.loc[:,  ~new_rows.columns.duplicated()]",
    )


# ---------------------------------------------------------------------------
# Invariant 4 — master rows placed first in dedup pd.concat
# ---------------------------------------------------------------------------

def check_master_first_in_concat() -> Result:
    src   = _read(DEDUP)
    match = re.search(r"pd\.concat\(\s*\[([^\]]+)\]", src, re.DOTALL)

    if not match:
        return Result(
            ok        = False,
            invariant = "Master rows placed first in dedup pd.concat",
            detail    = "No pd.concat call found in dedup.py",
            location  = "dedup.py — find_duplicate_rows",
            fix       = "combined = pd.concat([norm_master, norm_incoming], ignore_index=True)",
        )

    args         = match.group(1)
    master_pos   = args.find("norm_master")
    incoming_pos = args.find("norm_incoming")
    ok           = 0 <= master_pos < incoming_pos

    return Result(
        ok        = ok,
        invariant = "Master rows placed first in dedup pd.concat",
        detail    = (
            "norm_master is first — master rows are protected from being flagged as duplicates" if ok
            else "norm_incoming appears before norm_master — master rows will be incorrectly "
                 "flagged as duplicates and could be dropped from the output"
        ),
        location  = "dedup.py — find_duplicate_rows, the pd.concat call",
        fix       = "combined = pd.concat(\n"
                    "    [norm_master, norm_incoming],\n"
                    "    ignore_index=True,\n"
                    ")",
    )


# ---------------------------------------------------------------------------
# Invariant 5 — append_to_master returns (int, Path) tuple
# ---------------------------------------------------------------------------

def check_append_to_master_return() -> Result:
    src   = _read(FILE_IO)
    body  = _fn_body(src, "append_to_master")
    match = re.search(r"return\s+len\([^)]+\)\s*,\s*\w+", body)
    ok    = match is not None

    return Result(
        ok        = ok,
        invariant = "append_to_master returns (int, Path) tuple",
        detail    = (
            f"Returns `{match.group(0).strip()}` — matches (int, Path) contract" if ok
            else "Return statement does not match (int, Path) pattern — "
                 "main.py two-value unpack will raise ValueError at runtime"
        ),
        location  = "file_io.py — last line of append_to_master",
        fix       = "return len(new_rows), new_path",
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

CHECKS = [
    check_reset_index,
    check_parse_dates,
    check_columns_deduped,
    check_master_first_in_concat,
    check_append_to_master_return,
]


def main() -> None:
    print("\nChecking pipeline invariants...\n")

    results  = [check() for check in CHECKS]
    failures = [r for r in results if not r.ok]

    for r in results:
        label = "  PASS" if r.ok else "  FAIL"
        print(f"{label}  {r.invariant}")
        print(f"        {r.detail}")
        if not r.ok:
            print(f"\n        Location : {r.location}")
            print(f"        Restore  :")
            for line in r.fix.splitlines():
                print(f"            {line}")
        print()

    if failures:
        print(f"  {len(failures)} INVARIANT(S) VIOLATED — silent data corruption risk")
        sys.exit(1)
    else:
        print(f"  ALL {len(results)} INVARIANTS PRESENT")
        sys.exit(0)


if __name__ == "__main__":
    main()
