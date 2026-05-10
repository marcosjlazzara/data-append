"""
column_mapper.py — Interactive column selection, fuzzy matching, and mapping confirmation.

Responsibilities:
    - prompt_column_selection: Ask the user which source columns to include.
    - compute_fuzzy_matches: Fuzzy-match source column names to master column names.
    - confirm_column_mapping: Present matches and let the user accept/override/skip/new.
    - apply_column_mapping: Rename and subset a DataFrame according to the confirmed map.

Dependencies:
    - rapidfuzz >= 2.0 (process.extractOne returns (match, score, index) tuple)
    - rich >= 12.0
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass  # 'field' was imported but never used — removed
from typing import Optional

import pandas as pd
from rapidfuzz import fuzz, process
from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class ColumnMatch:
    """Holds the fuzzy-match result for a single source column."""
    source_col: str
    master_col: Optional[str]
    score: float
    confirmed: bool = False
    conflict_note: str = ""  # set when bumped from auto-accept due to a conflict


def compute_fuzzy_matches(
    source_cols: list[str],
    master_cols: list[str],
    score_cutoff: float = 60.0,
) -> list[ColumnMatch]:
    """
    Fuzzy-match each source column name against the list of master column names.

    Args:
        source_cols: Column names from the source file (user-selected subset).
        master_cols: Column names from the master CSV.
        score_cutoff: Minimum WRatio score to consider a match (default 60.0).

    Returns:
        List of ColumnMatch objects, one per source column.
        Columns with no match above the cutoff have master_col=None, score=0.0.
    """
    matches: list[ColumnMatch] = []
    for col in source_cols:
        result = process.extractOne(col, master_cols, scorer=fuzz.WRatio)
        if result is None or result[1] < score_cutoff:
            logger.debug("No fuzzy match | source_col=%r cutoff=%.0f", col, score_cutoff)
            matches.append(ColumnMatch(source_col=col, master_col=None, score=0.0))
        else:
            logger.debug(
                "Fuzzy match | source_col=%r master_col=%r score=%.0f",
                col, result[0], result[1],
            )
            matches.append(
                ColumnMatch(source_col=col, master_col=result[0], score=result[1])
            )
    return matches


def prompt_column_selection(source_df: pd.DataFrame) -> list[str]:
    """
    Interactively ask the user which source columns to include.

    Args:
        source_df: The full source DataFrame (used only for its column list).

    Returns:
        Non-empty list of column name strings selected by the user.
        Guaranteed to return a list (never None, never empty — the loop
        rejects empty input).
    """
    cols = list(source_df.columns)
    console.print("\n[bold]Source columns:[/bold]")
    for i, col in enumerate(cols):
        console.print(f"  [{i}] {col}")

    try:
        while True:
            raw = input(
                "\nEnter column indices (comma-separated) or 'all': "
            ).strip()

            if raw.lower() == "all":
                logger.debug("User selected all %d columns", len(cols))
                return cols

            parts = [p.strip() for p in raw.split(",") if p.strip()]
            if not parts:
                console.print("[red]No input provided. Try again.[/red]")
                continue

            valid = True
            indices: list[int] = []
            for part in parts:
                if part.isdigit():
                    idx = int(part)
                    if 0 <= idx < len(cols):
                        indices.append(idx)
                    else:
                        console.print(
                            f"[red]Index {idx} out of range (0-{len(cols)-1}).[/red]"
                        )
                        valid = False
                        break
                else:
                    console.print(
                        f"[red]'{part}' is not a valid index. Enter numbers or 'all'.[/red]"
                    )
                    valid = False
                    break

            if valid and indices:
                seen: set[int] = set()
                deduped = [i for i in indices if not (i in seen or seen.add(i))]
                selected = [cols[i] for i in deduped]
                logger.debug("User selected columns | count=%d cols=%r", len(selected), selected)
                return selected

            continue
    except EOFError:
        console.print("\n[red]Input closed unexpectedly. Exiting.[/red]")
        sys.exit(1)


def _confirm_single_match(
    m: ColumnMatch, row_num: int, master_cols_lower: dict[str, str]
) -> Optional[str]:
    """
    Interactively confirm/override one low-confidence match.
    Returns the resolved master column name, or None if skipped.
    """
    has_suggestion = m.master_col is not None

    try:
        while True:
            if has_suggestion:
                prompt = (
                    f"  Row {row_num} — \"{m.source_col}\" → \"{m.master_col}\" "
                    f"(score {m.score:.0f}). Accept? [Enter/override/skip/new]: "
                )
            else:
                prompt = (
                    f"  Row {row_num} — \"{m.source_col}\" → NO MATCH. "
                    "Type a master column, 'skip', or 'new': "
                )

            raw = input(prompt).strip()

            if raw == "" and has_suggestion:
                logger.debug("Accepted suggestion | %r -> %r", m.source_col, m.master_col)
                return m.master_col

            if raw == "" and not has_suggestion:
                console.print(
                    "    [red]No suggestion available. Type a column name, 'skip', or 'new'.[/red]"
                )
                continue

            lower = raw.lower()

            if lower == "skip":
                logger.debug("Skipped column | source_col=%r", m.source_col)
                return None

            if lower == "new":
                console.print(f"    [dim]New column '{m.source_col}' will be created in master.[/dim]")
                logger.debug("New column | source_col=%r", m.source_col)
                return m.source_col

            canonical = master_cols_lower.get(lower)
            if canonical is not None:
                logger.debug("Override | %r -> %r", m.source_col, canonical)
                return canonical

            console.print(
                f"    [red]'{raw}' not found in master columns. "
                "Try again, or type 'skip'/'new'.[/red]"
            )
    except EOFError:
        console.print("\n[red]Input closed unexpectedly. Exiting.[/red]")
        sys.exit(1)


def confirm_column_mapping(
    matches: list[ColumnMatch], master_cols: list[str]
) -> dict[str, str]:
    """
    Auto-accept matches with score >= 80. For lower-confidence matches, show a
    numbered list and let the user choose which to include, then confirm each
    selected one individually.

    Conflicts — two source columns both scoring >= 80 against the same master
    column — are resolved before the auto-accept table is shown: the higher-
    scoring source column is kept; the lower-scoring one is moved to the manual-
    review section with a conflict note. Ties send all competing columns to
    manual review.

    Args:
        matches: Output of compute_fuzzy_matches.
        master_cols: Full list of master column names (for override validation).

    Returns:
        Dict mapping source_col -> master_col for all confirmed columns.
        Skipped columns are absent from the dict.
        "new" columns map source_col -> source_col.
    """
    from collections import defaultdict

    HIGH_CONFIDENCE = 80.0

    high = [m for m in matches if m.score >= HIGH_CONFIDENCE]
    low  = [m for m in matches if m.score < HIGH_CONFIDENCE]

    master_cols_lower = {c.lower(): c for c in master_cols}
    mapping: dict[str, str] = {}

    # ── Resolve high-confidence conflicts before auto-accepting ───────────────
    target_groups: dict[str, list[ColumnMatch]] = defaultdict(list)
    for m in high:
        target_groups[m.master_col].append(m)

    clean_high: list[ColumnMatch] = []
    winner_notes: dict[str, str] = {}  # source_col -> note shown in auto-accept table
    bumped: list[ColumnMatch] = []

    for master_col, group in target_groups.items():
        if len(group) == 1:
            clean_high.append(group[0])
        else:
            logger.warning(
                "High-confidence conflict | master_col=%r competing_sources=%r",
                master_col, [m.source_col for m in group],
            )
            group_sorted = sorted(group, key=lambda m: m.score, reverse=True)
            top_score = group_sorted[0].score
            winners = [m for m in group_sorted if m.score == top_score]
            losers  = [m for m in group_sorted if m.score != top_score]

            if len(winners) == 1:
                winner = winners[0]
                clean_high.append(winner)
                beaten = ", ".join(f'"{m.source_col}" ({m.score:.0f})' for m in losers)
                winner_notes[winner.source_col] = f"conflict resolved — beat {beaten}"
                for loser in losers:
                    loser.conflict_note = (
                        f'conflict: "{master_col}" taken by '
                        f'"{winner.source_col}" ({winner.score:.0f})'
                    )
                    loser.master_col = None  # original target is taken; no suggestion
                    bumped.append(loser)
            else:
                # Tie — all competing columns go to manual review
                for m in group_sorted:
                    m.conflict_note = f'conflict: tied for "{master_col}"'
                    m.master_col = None
                    bumped.append(m)

    # Bumped columns appear first in the review table so they're easy to spot
    low = bumped + low

    # ── Auto-accept high-confidence matches ──────────────────────────────────
    if clean_high:
        has_notes = bool(winner_notes)
        auto_table = Table(title="Auto-accepted (score ≥ 80)", show_lines=True)
        auto_table.add_column("Source Column", style="cyan", no_wrap=True)
        auto_table.add_column("Master Column", style="green", no_wrap=True)
        auto_table.add_column("Score", justify="right", style="green")
        if has_notes:
            auto_table.add_column("Note", style="yellow")
        for m in clean_high:
            mapping[m.source_col] = m.master_col
            if has_notes:
                auto_table.add_row(
                    m.source_col, m.master_col, f"{m.score:.0f}",
                    winner_notes.get(m.source_col, ""),
                )
            else:
                auto_table.add_row(m.source_col, m.master_col, f"{m.score:.0f}")
            logger.debug("Auto-accepted | %r -> %r score=%.0f", m.source_col, m.master_col, m.score)
        console.print()
        console.print(auto_table)

    # ── Handle low-confidence / no-match / bumped columns ────────────────────
    if low:
        n_bumped = len(bumped)
        n_low = len(low) - n_bumped
        if n_bumped and n_low:
            console.print(
                f"\n[bold]Review required:[/bold] [yellow]{n_bumped}[/yellow] conflict(s) "
                f"bumped from auto-accept + [yellow]{n_low}[/yellow] low-confidence match(es)."
            )
        elif n_bumped:
            console.print(
                f"\n[bold]Review required:[/bold] [yellow]{n_bumped}[/yellow] column(s) "
                f"bumped from auto-accept due to conflicts."
            )
        else:
            console.print("\n[bold]Low-confidence matches (score < 80) — review required:[/bold]")

        has_conflict_notes = any(m.conflict_note for m in low)
        low_table = Table(show_lines=True)
        low_table.add_column("#", justify="right", style="dim")
        low_table.add_column("Source Column", style="cyan", no_wrap=True)
        low_table.add_column("Suggested Master Column", no_wrap=True)
        low_table.add_column("Score", justify="right")
        if has_conflict_notes:
            low_table.add_column("Note", style="yellow")

        for i, m in enumerate(low):
            if m.master_col is None:
                master_label = "[red]NO MATCH[/red]"
                score_label  = "[red]—[/red]"
            elif m.score >= 60:
                master_label = f"[yellow]{m.master_col}[/yellow]"
                score_label  = f"[yellow]{m.score:.0f}[/yellow]"
            else:
                master_label = f"[red]{m.master_col}[/red]"
                score_label  = f"[red]{m.score:.0f}[/red]"
            if has_conflict_notes:
                low_table.add_row(str(i), m.source_col, master_label, score_label, m.conflict_note)
            else:
                low_table.add_row(str(i), m.source_col, master_label, score_label)

        console.print(low_table)
        console.print(
            "\nEnter the [bold]indices[/bold] of columns to include (comma-separated), "
            "[bold]all[/bold] to include all, or [bold]none[/bold] to skip all: "
        )

        try:
            while True:
                raw = input("  Your choice: ").strip().lower()
                if not raw:
                    console.print("  [red]No input provided. Try again.[/red]")
                    continue
                if raw == "none":
                    selected_low: list[ColumnMatch] = []
                    break
                if raw == "all":
                    selected_low = low
                    break
                parts = [p.strip() for p in raw.split(",") if p.strip()]
                valid = True
                indices: list[int] = []
                for part in parts:
                    if part.isdigit() and 0 <= int(part) < len(low):
                        indices.append(int(part))
                    else:
                        console.print(f"  [red]'{part}' is not a valid index (0-{len(low)-1}).[/red]")
                        valid = False
                        break
                if valid and indices:
                    seen: set[int] = set()
                    selected_low = [low[i] for i in indices if not (i in seen or seen.add(i))]
                    break
        except EOFError:
            console.print("\n[red]Input closed unexpectedly. Exiting.[/red]")
            sys.exit(1)

        if selected_low:
            console.print(
                "\nFor each selected column: press [bold]Enter[/bold] to accept the suggestion, "
                "type a master column name to override, [bold]skip[/bold] to exclude, "
                "or [bold]new[/bold] to create a new master column.\n"
            )
            for row_num, m in enumerate(selected_low, start=1):
                resolved = _confirm_single_match(m, row_num, master_cols_lower)
                if resolved is not None:
                    mapping[m.source_col] = resolved

    # ── Final summary ────────────────────────────────────────────────────────
    console.print("\n[bold]Final column mapping:[/bold]")
    if mapping:
        summary = Table(show_header=True, show_lines=False)
        summary.add_column("Source", style="cyan")
        summary.add_column("-> Master", style="green")
        for src, dst in mapping.items():
            summary.add_row(src, dst)
        console.print(summary)
    else:
        console.print("  [yellow]No columns mapped — nothing will be appended.[/yellow]")

    logger.info("Column mapping confirmed | mapped=%d total=%d", len(mapping), len(matches))
    # Safety net: catch duplicate targets introduced during manual review
    # (e.g. user typed the same master column name for two different source cols).
    seen_targets: dict[str, str] = {}
    for src, dst in list(mapping.items()):
        if dst in seen_targets:
            console.print(
                f"  [yellow]Warning:[/yellow] '[cyan]{src}[/cyan]' and "
                f"'[cyan]{seen_targets[dst]}[/cyan]' both map to '[cyan]{dst}[/cyan]'. "
                f"'[cyan]{src}[/cyan]' will be skipped."
            )
            del mapping[src]
        else:
            seen_targets[dst] = src
    return mapping


def apply_column_mapping(
    source_df: pd.DataFrame, mapping: dict[str, str]
) -> pd.DataFrame:
    """
    Subset source_df to the mapped columns and rename them to master column names.

    The returned DataFrame always has a clean RangeIndex (reset_index is called
    explicitly).  This is required for correct positional arithmetic in
    find_duplicate_rows(), which returns integer positions that are then used
    as index labels in drop(index=...).  A mismatched index would cause silent
    wrong-row drops.

    Args:
        source_df: Full source DataFrame.
        mapping: Dict of {source_col: master_col} from confirm_column_mapping.

    Returns:
        DataFrame with only the mapped columns, renamed, and a clean RangeIndex.
    """
    cols_present = [col for col in mapping if col in source_df.columns]
    missing = [col for col in mapping if col not in source_df.columns]
    if missing:
        logger.warning(
            "Mapped source columns not found in DataFrame and will be skipped | cols=%r",
            missing,
        )
    selected = source_df[cols_present].copy()
    renamed = selected.rename(columns=mapping)
    # Reset to RangeIndex so dedup positional arithmetic is always correct.
    return renamed.reset_index(drop=True)
