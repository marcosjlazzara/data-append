"""
dedup.py — Duplicate detection and user decision prompting for the append pipeline.

Responsibilities:
    - normalize_for_comparison: Strip/lowercase string columns for fair comparison.
    - find_duplicate_rows: Identify incoming rows that already exist in the master.
    - prompt_dedup_decision: Ask the user how to handle detected duplicates.

Normalization note:
    Nan values in object columns are kept as Nan (not converted to the string "nan").
    pandas duplicated() treats two Nan cells as equal, so two rows that are both Nan in a key column
    are still treated as duplicates of each other
"""

from __future__ import annotations

import logging
import sys
from typing import Literal

import pandas as pd
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


def normalize_for_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a copy of df with all string-dtype columns stripped and lowercased.

    Handles both legacy object dtype and pandas StringDtype (introduced in
    pandas 1.0, now the default for string columns in pandas 2.x+).

    This normalises superficial differences (trailing spaces, case) that should
    not prevent duplicate detection.

    Args:
        df: DataFrame to normalise (only the comparison-relevant columns should
            be passed in to avoid unnecessary work).

    Returns:
        New DataFrame with normalised string columns.
    """
    result = df.copy()
    for col in result.columns:
        col_data = result[col]
        if isinstance(col_data, pd.Series) and (
            col_data.dtype == object or isinstance(col_data.dtype, pd.StringDtype)
        ):
            result[col] = col_data.str.strip().str.lower()
    return result


def find_duplicate_rows(
    incoming_df: pd.DataFrame,
    master_df: pd.DataFrame,
    subset: list[str] | None = None,
) -> pd.Index:
    """
    Return the positional integer positions (not labels) of incoming_df rows
    that already exist in master_df.

    IMPORTANT — index contract:
        The returned values are *positional integers* (0-based row positions
        within incoming_df), not index labels.  Callers must use .iloc or
        ensure incoming_df has a clean RangeIndex(0, N) before calling
        drop(index=...).  apply_column_mapping() guarantees this via
        reset_index(drop=True).

    Duplicate detection strategy:
        Concatenate normalised master and normalised incoming, then mark rows
        in the combined frame that are duplicates of an earlier row
        (keep="first").  Any marked row whose combined-frame position is >=
        len(master_df) is a duplicate incoming row.  The returned position is
        offset back to incoming_df's local space (0-based).

    Args:
        incoming_df: Newly mapped rows to check (must have clean RangeIndex).
        master_df: Existing master data.
        subset: Column names to use as the duplicate key.  Defaults to all
                columns common to both DataFrames.

    Returns:
        pd.Index of integer positions in incoming_df that are duplicates.
        Empty index if master is empty or no common columns exist.
    """
    if master_df.empty:
        logger.debug("Master is empty — no duplicates possible")
        return pd.Index([], dtype=int)

    common_cols = [c for c in incoming_df.columns if c in master_df.columns]
    if not common_cols:
        logger.warning(
            "No common columns between incoming and master — cannot detect duplicates"
        )
        return pd.Index([], dtype=int)

    check_subset = subset if subset is not None else common_cols
    check_subset = [c for c in check_subset if c in common_cols]
    # Deduplicate while preserving order — duplicate column names cause pd.concat to crash.
    seen: set[str] = set()
    check_subset = [c for c in check_subset if not (c in seen or seen.add(c))]
    if not check_subset:
        logger.warning(
            "Requested subset columns not found in common columns | subset=%r", subset
        )
        return pd.Index([], dtype=int)

    logger.debug(
        "Checking duplicates | subset=%r master_rows=%d incoming_rows=%d",
        check_subset, len(master_df), len(incoming_df),
    )

    # Drop duplicate columns from both frames before slicing — pandas returns all
    # matching columns (including duplicates) when indexing by name, which breaks concat.
    master_deduped = master_df.loc[:, ~master_df.columns.duplicated()]
    incoming_deduped = incoming_df.loc[:, ~incoming_df.columns.duplicated()]

    norm_master = normalize_for_comparison(master_deduped[check_subset])
    norm_incoming = normalize_for_comparison(incoming_deduped[check_subset])

    # ignore_index=True gives a clean 0-based RangeIndex on the combined frame,
    # which makes the offset arithmetic below unambiguous.
    combined = pd.concat(
        [norm_master, norm_incoming],
        ignore_index=True,
    )
    dupe_mask = combined.duplicated(subset=check_subset, keep="first")

    # combined.index is RangeIndex(0, len(master)+len(incoming)).
    # Positions >= offset belong to incoming_df; subtract offset to get
    # incoming_df-local positions (0-based), which match its RangeIndex labels.
    offset = len(master_df)
    incoming_dupe_positions = [
        pos - offset
        for pos in dupe_mask.index[dupe_mask]
        if pos >= offset
    ]

    logger.info(
        "Duplicate detection complete | duplicates=%d incoming_rows=%d",
        len(incoming_dupe_positions), len(incoming_df),
    )
    return pd.Index(incoming_dupe_positions, dtype=int)


def prompt_dedup_decision(
    dupe_count: int, total_incoming: int
) -> Literal["append_all", "skip_dupes", "cancel"]:
    """
    Present a deduplication decision menu and return the user's choice.

    Args:
        dupe_count: Number of duplicate rows detected.
        total_incoming: Total number of incoming rows before dedup filtering.

    Returns:
        "append_all"  — write all incoming rows including duplicates.
        "skip_dupes"  — write only non-duplicate rows.
        "cancel"      — abort the pipeline, write nothing.
    """
    new_count = total_incoming - dupe_count
    console.print(
        f"\n[yellow]Found {dupe_count} duplicate row(s) out of "
        f"{total_incoming} incoming row(s).[/yellow]"
    )
    console.print("  [1] Append all rows (including duplicates)")
    console.print(f"  [2] Skip duplicates — append {new_count} new row(s) only")
    console.print("  [3] Cancel — do not write anything")

    try:
        while True:
            raw = input("\nYour choice [1/2/3]: ").strip()
            if raw == "1":
                logger.info("User chose: append_all")
                return "append_all"
            if raw == "2":
                logger.info("User chose: skip_dupes")
                return "skip_dupes"
            if raw == "3":
                logger.info("User chose: cancel")
                return "cancel"
            console.print("[red]Enter 1, 2, or 3.[/red]")
    except EOFError:
        console.print("\n[red]Input closed unexpectedly. Exiting.[/red]")
        sys.exit(1)
