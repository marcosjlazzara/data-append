"""
file_io.py — Source/master file loading and output writing for the weekly append pipeline.

Responsibilities:
    - load_source_file: Read an .xlsx or .csv source file into a DataFrame.
    - find_latest_master: Locate the most recently modified CSV in a folder.
    - load_master: Read the master CSV, tolerating empty files.
    - append_to_master: Atomically write the combined DataFrame back to disk.

Known limitations:
    - find_latest_master uses mtime, which can be spoofed by file copies.
    - Encoding fallback (utf-8 → latin-1) is a best-effort heuristic; files with
      mixed encodings will still corrupt silently.
    - Atomic replacement on Windows uses os.replace() (MoveFileEx with
      MOVEFILE_REPLACE_EXISTING), which is not a true atomic swap but is as close
      as Windows allows for cross-process safety.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Matches the timestamp suffix appended by append_to_master: _YYYY-MM-DD_HH-MM-SS
_TIMESTAMPED_RE = re.compile(r"_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")


def load_source_file(path: str | Path) -> pd.DataFrame:
    """
    Load a source file (.xlsx or .csv) into a DataFrame.

    Args:
        path: Path to the source file.

    Returns:
        DataFrame with the file contents.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is not .xlsx or .csv.
        pd.errors.EmptyDataError: If a CSV file has no parseable content.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {path}")

    ext = path.suffix.lower()
    logger.debug("Loading source file | path=%s ext=%s", path, ext)

    if ext == ".xlsx":
        # Use ExcelFile as a context manager to ensure the file handle is
        # released even if the user interrupts during the sheet-selection prompt.
        with pd.ExcelFile(path, engine="openpyxl") as xf:
            sheet_names = xf.sheet_names
            if len(sheet_names) == 1:
                sheet = sheet_names[0]
                logger.debug("Single sheet detected | sheet=%s", sheet)
            else:
                print("Multiple sheets found:")
                for i, name in enumerate(sheet_names):
                    print(f"  [{i}] {name}")
                try:
                    while True:
                        raw = input("Select sheet index: ").strip()
                        if raw.isdigit() and int(raw) < len(sheet_names):
                            sheet = sheet_names[int(raw)]
                            break
                        print(f"  Enter a number between 0 and {len(sheet_names) - 1}.")
                except EOFError:
                    raise RuntimeError("Input closed unexpectedly during sheet selection.") from None
                logger.debug("User selected sheet | sheet=%s", sheet)
            df = pd.read_excel(xf, sheet_name=sheet, engine="openpyxl", parse_dates=False)

        logger.info(
            "Loaded Excel source | path=%s sheet=%s rows=%d cols=%d",
            path, sheet, len(df), len(df.columns),
        )
        return df

    elif ext == ".csv":
        try:
            df = pd.read_csv(path, encoding="utf-8", parse_dates=False)
            logger.debug("Read CSV with utf-8 | path=%s", path)
        except UnicodeDecodeError:
            logger.warning(
                "utf-8 decode failed, falling back to latin-1 | path=%s", path
            )
            df = pd.read_csv(path, encoding="latin-1", parse_dates=False)

        logger.info(
            "Loaded CSV source | path=%s rows=%d cols=%d",
            path, len(df), len(df.columns),
        )
        return df

    else:
        raise ValueError(f"Unsupported file extension '{ext}'. Expected .xlsx or .csv.")


def find_latest_master(folder: str | Path) -> Optional[Path]:
    """
    Return the most recently modified master CSV or Excel file in folder, or None.

    Excludes:
    - Office lock files (names starting with ~$)
    - Pipeline output files (stems ending with _YYYY-MM-DD_HH-MM-SS), which are
      outputs from prior runs — selecting them would cause the stem to grow
      indefinitely on each subsequent run.

    Uses mtime (modification time). Files touched with a backdated mtime may
    cause the wrong file to be selected — acceptable for this pipeline's use case.

    Args:
        folder: Directory to search.

    Returns:
        Path to the newest eligible .csv or .xlsx file, or None.
    """
    folder = Path(folder)
    all_files = list(folder.glob("*.csv")) + list(folder.glob("*.xlsx"))
    candidates = [
        p for p in all_files
        if not p.name.startswith("~$")
        and not _TIMESTAMPED_RE.search(p.stem)
    ]
    if not candidates:
        logger.warning(
            "No master candidates found | folder=%s total_files=%d excluded=%d",
            folder, len(all_files), len(all_files) - len(candidates),
        )
        return None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    logger.debug(
        "Latest master | path=%s candidates=%s",
        latest, [p.name for p in candidates],
    )
    return latest


def load_master(path: Path) -> pd.DataFrame:
    """
    Load the master file (.csv or .xlsx) into a DataFrame.

    Returns an empty DataFrame (no columns) if the file is zero bytes.
    Does NOT use load_source_file — master files never need interactive sheet
    selection (they are always single-sheet pipeline outputs), and calling
    load_source_file would inject an input() prompt that crashes in the
    Windows EXE environment.

    Args:
        path: Path to the master CSV or Excel file.

    Returns:
        DataFrame with master contents, or empty DataFrame.
    """
    logger.debug("Loading master | path=%s size=%d", path, path.stat().st_size)

    if path.stat().st_size == 0:
        logger.info("Master file is empty (0 bytes) | path=%s", path)
        return pd.DataFrame()

    ext = path.suffix.lower()
    if ext == ".xlsx":
        df = pd.read_excel(path, sheet_name=0, engine="openpyxl", parse_dates=False)
        logger.debug("Read master Excel (first sheet) | path=%s", path)
    elif ext == ".csv":
        try:
            df = pd.read_csv(path, encoding="utf-8", parse_dates=False)
            logger.debug("Read master CSV with utf-8 | path=%s", path)
        except UnicodeDecodeError:
            logger.warning(
                "utf-8 decode failed, falling back to latin-1 | path=%s", path
            )
            df = pd.read_csv(path, encoding="latin-1", parse_dates=False)
    else:
        raise ValueError(f"Unsupported master file extension '{ext}'. Expected .xlsx or .csv.")

    if df.empty and len(df.columns) == 0:
        logger.info("Master parsed but contains no columns | path=%s", path)
        return pd.DataFrame()

    logger.info(
        "Loaded master | path=%s rows=%d cols=%d",
        path, len(df), len(df.columns),
    )
    return df


def append_to_master(
    master_df: pd.DataFrame, new_rows: pd.DataFrame, output_path: Path
) -> tuple[int, Path]:
    """
    Combine master_df and new_rows and write the result to a new timestamped file.

    The original master file is never modified. The new file is written to the
    same folder as output_path, named as:
        <original_stem>_<YYYY-MM-DD_HH-MM>.csv

    For example, if output_path is /data/master.csv and the time is 09:14 on
    2026-04-30, the new file will be /data/master_2026-04-30_09-14.csv.

    Args:
        master_df: Existing master data (may be empty).
        new_rows: Rows to append.
        output_path: Path of the current master file (used for folder and stem).

    Returns:
        Tuple of (rows_appended, new_file_path).

    Note on column alignment:
        If master_df has columns absent from new_rows, those columns will be NaN
        in the appended rows.  If new_rows has columns absent from master_df,
        those columns will be NaN in all existing master rows.  Both cases are
        intentional pass-through behavior — callers should warn users upstream.
    """
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    new_filename = f"{output_path.stem}_{timestamp}.csv"
    new_path = output_path.parent / new_filename

    master_df = master_df.loc[:, ~master_df.columns.duplicated()]
    new_rows = new_rows.loc[:, ~new_rows.columns.duplicated()]
    combined = pd.concat([master_df, new_rows], ignore_index=True)

    logger.debug(
        "Writing new master | path=%s total_rows=%d", new_path, len(combined)
    )
    
    tmp_path = new_path.with_suffix(".tmp")
    try:
        combined.to_csv(tmp_path, index=False)
        os.replace(tmp_path, new_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    

    logger.info(
        "New master created | output=%s rows_appended=%d total_rows=%d",
        new_path, len(new_rows), len(combined),
    )
    return len(new_rows), new_path
