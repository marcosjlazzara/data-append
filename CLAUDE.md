# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate.bat
pip install -r requirements.txt
```

## Running

```bash
python main.py
```

No CLI arguments — fully interactive. Set `LOG_LEVEL=DEBUG` for verbose output:

```bash
LOG_LEVEL=DEBUG python main.py
```

## Architecture

The pipeline is split across four modules with strict separation of concerns:

- **`main.py`** — orchestrator only. Owns all user-facing path prompts (via `tkinter` file/folder dialogs), sequences the pipeline steps, and handles top-level error catching. Never does I/O or data logic directly.
- **`file_io.py`** — all disk I/O. Reads `.xlsx`/`.csv` source and master files (`parse_dates=False` on all reads to preserve types), finds the latest master by `mtime`, and writes the combined output as a new timestamped `.csv` (never overwrites the original master).
- **`column_mapper.py`** — fuzzy column matching and interactive mapping. Matches ≥ 80 score are auto-accepted; matches < 80 are presented as a numbered list for bulk selection, then confirmed individually. Uses `rapidfuzz.fuzz.WRatio` scorer.
- **`dedup.py`** — duplicate detection. Normalises string columns (strip + lowercase) before comparison. Uses concat-then-`duplicated(keep="first")` so master rows are never flagged. Returns positional integers — callers must ensure incoming DataFrame has a clean `RangeIndex` (guaranteed by `apply_column_mapping`).

## Key invariants

- `apply_column_mapping()` always calls `reset_index(drop=True)` on its output — this is required for `find_duplicate_rows()` positional arithmetic to be correct. Do not remove it.
- Both `master_df` and `new_rows` are deduplicated with `df.loc[:, ~df.columns.duplicated()]` before any `pd.concat` call — source files with duplicate column names are a known real-world input.
- `append_to_master()` returns `(int, Path)` — the row count and the path of the newly created file. `main.py` unpacks both.
- All `pd.read_csv` and `pd.read_excel` calls use `parse_dates=False` to prevent pandas from silently coercing numeric or string values into dates.

## Output naming

New master files are written as `<original_stem>_<YYYY-MM-DD_HH-MM>.csv` in the same folder as the source master. The original master is never modified.
