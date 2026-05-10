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
- **`file_io.py`** — all disk I/O. Reads `.xlsx`/`.csv` source and master files (`parse_dates=False` on all reads to preserve types), finds the latest master by `mtime` (excludes `~$` lock files and prior timestamped outputs), and writes the combined output as a new timestamped `.csv` (never overwrites the original master). `load_master` reads directly — it does NOT delegate to `load_source_file` — and always reads Excel files at sheet index 0 silently (master files are single-sheet pipeline outputs; interactive sheet selection is only for source files).
- **`column_mapper.py`** — fuzzy column matching and interactive mapping. Matches ≥ 80 score are auto-accepted; matches < 80 are presented as a numbered list for bulk selection, then confirmed individually. Uses `rapidfuzz.fuzz.WRatio` scorer. If two source columns both score ≥ 80 against the same master column, the higher-scoring one is auto-accepted and the lower-scoring one is moved to the manual review list with a conflict note (ties send all competing columns to review).
- **`dedup.py`** — duplicate detection. Normalises string columns (strip + lowercase) before comparison. Uses concat-then-`duplicated(keep="first")` so master rows are never flagged. Returns positional integers — callers must ensure incoming DataFrame has a clean `RangeIndex` (guaranteed by `apply_column_mapping`).

## Key invariants

- `apply_column_mapping()` always calls `reset_index(drop=True)` on its output — this is required for `find_duplicate_rows()` positional arithmetic to be correct. Do not remove it.
- Both `master_df` and `new_rows` are deduplicated with `df.loc[:, ~df.columns.duplicated()]` before any `pd.concat` call — source files with duplicate column names are a known real-world input.
- `append_to_master()` returns `(int, Path)` — the row count and the path of the newly created file. `main.py` unpacks both.
- All `pd.read_csv` and `pd.read_excel` calls use `parse_dates=False` to prevent pandas from silently coercing numeric or string values into dates.
- `append_to_master()` writes to a `.tmp` file first, then renames via `os.replace()` — do not revert to a direct `to_csv(new_path)` call, as a mid-write crash would corrupt the output file.
- `confirm_column_mapping()` resolves duplicate target columns upfront (before the auto-accept table), not post-hoc. The safety-net check at the end still exists for duplicates introduced during manual review.
- All `input()` calls across all four modules are wrapped in `try/except EOFError` — they exit cleanly with a message instead of crashing with a traceback if stdin closes.

## Output naming

New master files are written as `<original_stem>_<YYYY-MM-DD_HH-MM-SS>.csv` in the same folder as the source master. The original master is never modified.

## Driver Name

After the source file loads, the user is prompted to enter a Driver Name. This value is inserted as the first column (Column A) of all newly appended rows only if the source file does not already contain a "Driver Name" column. If the source already has that column, its values are kept as-is and the prompt value is ignored (a note is printed to the user). Existing master rows always get `NaN` for Driver Name. The prompt loops until a non-empty value is entered.

## Distribution (Windows EXE)

The app is packaged as a standalone Windows `.exe` using PyInstaller via GitHub Actions.

- **Repo:** https://github.com/marcosjlazzara/data-append
- **Workflow:** `.github/workflows/build.yml` — triggers on every push to `main`, builds on a Windows runner, uploads `main.exe` as a downloadable artifact
- **To get a new build:** push code changes → go to Actions tab → download artifact zip → unzip → send `main.exe` to user
- **User requirements:** nothing — no Python, no libraries needed on the user's machine
- Developer is on Mac; end users are on Windows.
