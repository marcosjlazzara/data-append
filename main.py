"""
main.py — Entry point for the weekly data append pipeline.

Usage:
    python main.py

    The script is fully interactive.  It will prompt for:
        1. Source file path (.xlsx or .csv)
        2. Master folder path (containing the latest master CSV)
        3. Column selection from the source
        4. Column mapping confirmation (fuzzy-matched to master)
        5. Duplicate handling decision (if duplicates are detected)

Configuration:
    No environment variables or config files are required.
    All inputs are gathered interactively at runtime.

Logging:
    Set the LOG_LEVEL environment variable to control verbosity:
        LOG_LEVEL=DEBUG python main.py
    Defaults to WARNING (silent in normal operation).
"""

from __future__ import annotations

import logging
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import pandas as pd
from rich.console import Console

from column_mapper import (
    apply_column_mapping,
    compute_fuzzy_matches,
    confirm_column_mapping,
    prompt_column_selection,
)
from dedup import find_duplicate_rows, prompt_dedup_decision
from file_io import append_to_master, find_latest_master, load_master, load_source_file

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

console = Console()


def pick_file(title: str) -> Path:
    """Open a native file picker dialog and return the selected path."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(
        title=title,
        filetypes=[("Excel files", "*.xlsx"), ("CSV files", "*.csv"), ("All files", "*.*")],
    )
    root.destroy()
    if not path:
        console.print("[red]No file selected. Exiting.[/red]")
        sys.exit(1)
    return Path(path)


def pick_folder(title: str) -> Path:
    """Open a native folder picker dialog and return the selected path."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askdirectory(title=title)
    root.destroy()
    if not path:
        console.print("[red]No folder selected. Exiting.[/red]")
        sys.exit(1)
    return Path(path)


def prompt_driver_name() -> str:
    """Prompt until the user enters a non-empty driver name."""
    try:
        while True:
            name = input("Enter Brand Name: ").strip()
            if name:
                return name
            console.print("[yellow]Driver Name cannot be blank. Please enter a name.[/yellow]")
    except EOFError:
        console.print("\n[red]Input closed unexpectedly. Exiting.[/red]")
        sys.exit(1)


def main() -> None:
    console.rule("[bold blue]Weekly Data Append Pipeline[/bold blue]")

    # ------------------------------------------------------------------
    # 1. Load source file
    # ------------------------------------------------------------------
    console.print("\nSelect the Unify exported file (.xlsx or .csv)...")
    source_path = pick_file("Select source file")
    try:
        source_df = load_source_file(source_path)
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    # Fail fast on a source file that has no rows — there is nothing to append.
    if source_df.empty:
        console.print(
            f"[yellow]Source file '[cyan]{source_path.name}[/cyan]' contains no rows. "
            "Nothing to append. Exiting.[/yellow]"
        )
        sys.exit(0)

    # Fail fast on a source file that has no columns (malformed/empty header).
    if len(source_df.columns) == 0:
        console.print(
            f"[red]Error:[/red] Source file '[cyan]{source_path.name}[/cyan]' "
            "has no columns. Cannot proceed."
        )
        sys.exit(1)

    console.print(
        f"  Loaded [green]{len(source_df):,}[/green] rows, "
        f"[green]{len(source_df.columns)}[/green] columns from "
        f"[cyan]{source_path.name}[/cyan]."
    )

    # ------------------------------------------------------------------
    # 1a. Driver name
    # ------------------------------------------------------------------
    console.print()
    driver_name = prompt_driver_name()
    console.print(f"  Driver Name set to [cyan]{driver_name}[/cyan].")

    # ------------------------------------------------------------------
    # 2. Find / load master
    # ------------------------------------------------------------------
    console.print("\nSelect the master folder (containing the latest master CSV or Excel file)...")
    master_folder = pick_folder("Select master folder")

    master_path = find_latest_master(master_folder)
    master_df: pd.DataFrame

    if master_path is None:
        console.print(
            f"[yellow]No CSV files found in '{master_folder}'.[/yellow]"
        )
        default_name = master_folder / "master.csv"
        try:
            raw_new = input(f"Path for new master file [{default_name}]: ").strip()
        except EOFError:
            raw_new = ""
        master_path = Path(raw_new).expanduser() if raw_new else default_name

        master_df = pd.DataFrame()
        console.print(f"  Will create new master at [cyan]{master_path}[/cyan].")
    else:
        try:
            master_df = load_master(master_path)
        except Exception as exc:
            console.print(f"[red]Error loading master:[/red] {exc}")
            sys.exit(1)

        status = (
            f"[green]{len(master_df):,}[/green] rows"
            if not master_df.empty
            else "[yellow]empty[/yellow]"
        )
        console.print(
            f"  Using master [cyan]{master_path.name}[/cyan] — {status}."
        )

    # ------------------------------------------------------------------
    # 3. Column selection
    # ------------------------------------------------------------------
    console.print()
    selected_cols = prompt_column_selection(source_df)
    console.print(
        f"\n  Selected [green]{len(selected_cols)}[/green] column(s): "
        + ", ".join(f"[cyan]{c}[/cyan]" for c in selected_cols)
    )

    # ------------------------------------------------------------------
    # 4. Column mapping
    # ------------------------------------------------------------------
    if master_df.empty:
        mapping = {col: col for col in selected_cols}
        console.print(
            "\n  Master is empty — using identity mapping for all selected columns."
        )
    else:
        master_cols = list(master_df.columns)
        
    
        matches = compute_fuzzy_matches(selected_cols, master_cols)
        mapping = confirm_column_mapping(matches, master_cols)
        
        # Warn about master columns that the source has no mapping for - those
        # columns will be Nan in all newly appended rows.
        
        mapped_master_cols = set(mapping.values())
        unmatched_master_cols = [c for c in master_cols if c not in mapped_master_cols]
        if unmatched_master_cols:
                console.print(                                                                                                          
                  f"\n  [yellow]Note:[/yellow] {len(unmatched_master_cols)} master "
                  f"column(s) have no matching source column and will be "                                                            
                  f"[yellow]NaN[/yellow] in all new rows: "                                                                           
                  + ", ".join(f"[cyan]{c}[/cyan]" for c in unmatched_master_cols)
              )                                  
            
        # Warn about "new" columns (source columns the user mapped as 'new') —
        # these will be added to the master and all existing rows will be NaN.
        new_cols = [src for src, dst in mapping.items() if src == dst and dst not in master_cols]
        if new_cols:
            console.print(
                f"\n  [yellow]Note:[/yellow] {len(new_cols)} new column(s) will be "
                f"added to the master. All existing master rows will be "
                f"[yellow]NaN[/yellow] for these columns: "
                + ", ".join(f"[cyan]{c}[/cyan]" for c in new_cols)
            )

    if not mapping:
        console.print("\n[yellow]No columns mapped. Nothing to append. Exiting.[/yellow]")
        sys.exit(0)

    # ------------------------------------------------------------------
    # 5. Apply mapping
    # ------------------------------------------------------------------
    mapped_df = apply_column_mapping(source_df, mapping)
    if "Driver Name" in mapped_df.columns:
        console.print(
            "  [dim]Driver Name column found in source file — using source values "
            "(prompt value ignored).[/dim]"
        )
    else:
        mapped_df.insert(0, "Driver Name", driver_name)

    # ------------------------------------------------------------------
    # 6. Duplicate detection
    # ------------------------------------------------------------------
    if not master_df.empty:
        console.print(
            "\n [dim]Note: Driver Name is included in duplicate comparison - "
            "records from differenet drivers are never flagged as duplicate. [/dim]"
        )
        dupe_index = find_duplicate_rows(mapped_df, master_df)
        dupe_count = len(dupe_index)

        if dupe_count > 0:
            decision = prompt_dedup_decision(dupe_count, len(mapped_df))

            if decision == "cancel":
                console.print("\n[yellow]Operation cancelled. No data written.[/yellow]")
                sys.exit(0)

            if decision == "skip_dupes":
                # dupe_index contains positional integers matching mapped_df's
                # RangeIndex (guaranteed by apply_column_mapping's reset_index).
                # drop(index=...) here uses label-based dropping, and because
                # the index IS a RangeIndex, labels == positions.
                mapped_df = mapped_df.drop(index=dupe_index).reset_index(drop=True)
                console.print(
                    f"  Dropped {dupe_count} duplicate row(s). "
                    f"[green]{len(mapped_df)}[/green] row(s) remain."
                )

    # ------------------------------------------------------------------
    # 7. Guard: nothing left to write
    # ------------------------------------------------------------------
    if mapped_df.empty:
        console.print(
            "\n[yellow]No rows to append after deduplication. Exiting.[/yellow]"
        )
        sys.exit(0)

    # ------------------------------------------------------------------
    # 8. Write output
    # ------------------------------------------------------------------
    try:
        rows_written, new_master_path = append_to_master(master_df, mapped_df, master_path)
    except Exception as exc:
        console.print(f"[red]Error writing output:[/red] {exc}")
        sys.exit(1)

    console.print()
    console.rule("[bold green]Done[/bold green]")
    console.print(f" [green]{rows_written:,}[/green] row(s) appended")
    if not master_df.empty:
        console.print(f" Original master preserved: [cyan]{master_path.name}[/cyan]")
    console.print(f" New master created: [cyan]{new_master_path.name}[/cyan]")

if __name__ == "__main__":
    main()
