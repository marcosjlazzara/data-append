"""
scripts/validate_output.py — Validate the most recent (or a specified) output CSV.

Usage:
    python scripts/validate_output.py                     # validates latest file in Outputs/
    python scripts/validate_output.py path/to/file.csv    # validates a specific file

Exit codes:
    0  all checks passed
    1  one or more checks failed
    2  file not found or unreadable
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd


# Matches filenames like: master_2026-05-06_17-11-42.csv (seconds optional)
_TIMESTAMP_RE = re.compile(r".+_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}(-\d{2})?$")

OUTPUTS_DIR = Path(__file__).parent.parent / "Outputs"


# ---------------------------------------------------------------------------
# Individual checks — each returns (passed: bool, message: str)
# ---------------------------------------------------------------------------

def check_has_rows(df: pd.DataFrame):
    ok = len(df) > 0
    return ok, f"{len(df):,} data row(s) found" if ok else "File has no data rows (header only)"


def check_driver_name_column(df: pd.DataFrame):
    if "Driver Name" not in df.columns:
        return False, "'Driver Name' column is missing — rows may have been appended before this feature was added"
    non_null = df["Driver Name"].notna().sum()
    null_count = df["Driver Name"].isna().sum()
    if non_null == 0:
        return False, "'Driver Name' column is entirely NaN — no appended rows found"
    msg = f"'Driver Name' present: {non_null:,} appended row(s) have a value"
    if null_count > 0:
        msg += f", {null_count:,} pre-existing master row(s) have NaN (expected)"
    return True, msg


def check_no_duplicate_rows(df: pd.DataFrame):
    dupe_count = int(df.duplicated().sum())
    ok = dupe_count == 0
    return ok, (
        "No fully duplicate rows" if ok
        else f"{dupe_count:,} fully duplicate row(s) detected — possible double-append"
    )


def check_no_all_nan_columns(df: pd.DataFrame):
    all_nan = [c for c in df.columns if df[c].isna().all()]
    ok = len(all_nan) == 0
    return ok, (
        "No entirely-NaN columns" if ok
        else f"{len(all_nan)} column(s) are entirely NaN: {', '.join(all_nan)} — likely a column mapping issue"
    )


def check_filename_pattern(path: Path):
    ok = bool(_TIMESTAMP_RE.match(path.stem))
    return ok, (
        f"Filename follows expected timestamped pattern" if ok
        else f"Filename '{path.name}' does not match expected pattern <stem>_YYYY-MM-DD_HH-MM-SS.csv"
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

CHECKS = [
    check_has_rows,
    check_driver_name_column,
    check_no_duplicate_rows,
    check_no_all_nan_columns,
]


def validate(path: Path) -> int:
    """Run all checks. Returns the number of failures."""
    if not path.exists():
        print(f"  ERROR  File not found: {path}")
        return 1
    if path.stat().st_size == 0:
        print(f"  ERROR  File is empty (0 bytes): {path}")
        return 1

    try:
        df = pd.read_csv(path, parse_dates=False)
    except Exception as exc:
        print(f"  ERROR  Could not read CSV: {exc}")
        return 1

    print(f"  Rows : {len(df):,}")
    print(f"  Cols : {len(df.columns)} — {', '.join(df.columns)}")
    print()

    filename_ok, filename_msg = check_filename_pattern(path)
    _print_result(filename_ok, filename_msg)

    failures = 0 if filename_ok else 1

    for check in CHECKS:
        ok, msg = check(df)
        _print_result(ok, msg)
        if not ok:
            failures += 1

    return failures


def _print_result(ok: bool, msg: str) -> None:
    label = "  PASS" if ok else "  FAIL"
    print(f"{label}  {msg}")


def find_latest_output() -> Path | None:
    if not OUTPUTS_DIR.exists():
        return None
    candidates = list(OUTPUTS_DIR.glob("*.csv"))
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def main() -> None:
    if len(sys.argv) > 1:
        target = Path(sys.argv[1]).expanduser()
    else:
        target = find_latest_output()
        if target is None:
            if not OUTPUTS_DIR.exists():
                print(f"ERROR: Outputs/ directory not found at {OUTPUTS_DIR}")
            else:
                print(f"ERROR: No CSV files found in {OUTPUTS_DIR}")
            sys.exit(2)

    print(f"\nValidating: {target.name}")
    print(f"Size      : {target.stat().st_size:,} bytes")
    print()

    failures = validate(target)

    print()
    if failures == 0:
        print("  ALL CHECKS PASSED")
        sys.exit(0)
    else:
        print(f"  {failures} CHECK(S) FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
