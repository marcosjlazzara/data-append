# Weekly Data Append Pipeline — System Overview

This document has two parts. **Part 1** explains what the tool does and how it works in plain English — no technical background required. **Part 2** covers the internal architecture, data flow, and design decisions for anyone maintaining or extending the code.

A note on language: technical terms are defined in parentheses the first time they appear in Part 1. Part 2 assumes familiarity with Python and pandas.

---

## Part 1 — Plain English Guide

### What this tool is

The Weekly Data Append Pipeline is a small desktop tool that takes a new data export file — the kind you might receive weekly from a reporting platform, a CRM (Customer Relationship Manager, a system that stores contact and sales data), or any other data system — and merges its records into a single growing master file.

Every week you run it, it adds the new week's rows to the bottom of your master. Over time, the master becomes a complete historical record of everything that has ever come in.

### What problem it solves

Doing this manually in a spreadsheet is tedious and error-prone for three reasons:

- **Column names change.** The export you receive this week might call a field "Email Address" while your master calls it "email". Copying rows without noticing that difference means data lands in the wrong column — or gets lost entirely.
- **The same record can appear more than once.** If a record was in last week's export and again in this week's, you could accidentally count it twice. The tool detects this and lets you decide what to do.
- **Spreadsheets can be damaged if something goes wrong mid-save.** The tool writes your data safely so a crash or interruption never damages your existing master file.

### The people in the process

The tool runs interactively — it asks questions and waits for answers at each step. Nothing is changed automatically without your input or confirmation.

There is one piece of information the tool always collects before doing anything: a **Driver Name**. This is a label — typically the name of the person or team responsible for submitting this week's data — that gets recorded as the first column of every row added in that run. It makes it easy to trace, later on, which weekly submission each record came from.

### What happens to your files

The tool never modifies or deletes your original master file. Instead, every time it runs successfully, it creates a **new** master file with the date and time in the name (for example, `master_2026-04-30_09-14.csv`). Your previous master is left exactly as it was. This means you always have a trail of snapshots and can go back to any earlier version if something goes wrong.

### How the tool works, step by step

**Step 1 — Pick your source file.**
A file picker window opens. You select this week's export file. It must be an Excel file (`.xlsx`) or a comma-separated values file (`.csv`). The tool reads it and confirms how many rows and columns it found.

If the Excel file has multiple sheets (tabs), the tool lists them and asks you to pick one before continuing.

**Step 2 — Enter the Driver Name.**
You type a name — for example, your own name or a team name — and press Enter. This label will be stamped onto every row added during this run.

**Step 3 — Pick your master folder.**
A folder picker window opens. You select the folder where your master file lives. The tool automatically finds the most recently modified file in that folder and uses it as the master. You do not need to type the filename. If the folder is empty (the very first time you run the tool), it will ask you to name the new master file it is about to create.

**Step 4 — Choose which columns to bring in.**
The tool lists every column from your source file with a number next to each one. You type the numbers of the columns you want to include, separated by commas — or type `all` to take everything. Only the columns you select here will be added to the master.

**Step 5 — Confirm how columns line up.**
Your source file's column names probably do not match your master's column names exactly. The tool makes its best guess at which source column corresponds to which master column using a technique called fuzzy matching (a method that finds names that look or sound similar, even if they are not spelled identically — so "Email Address" would match "email" even though the words are different).

Matches it is confident about are accepted and shown to you automatically. For the ones it is less certain about, it shows you a list and asks you to pick which ones to include, then confirm, correct, skip, or create a new column for each one. You work through these one at a time.

**Step 6 — Handle duplicates (if any are found).**
The tool checks whether any rows in your new file already exist in the master. If it finds duplicates (rows that appear to be identical), it tells you exactly how many and gives you three choices:

| Choice | What it does |
|---|---|
| Append all rows | Adds everything, including the duplicates |
| Skip duplicates | Adds only the genuinely new rows, discards the duplicates |
| Cancel | Writes nothing — the master is left completely unchanged |

**Step 7 — Done.**
If everything went smoothly, the tool creates a new master file containing all the previous master rows plus the new rows you approved. It tells you the name of the new file and how many rows were added.

---

## Part 2 — Technical Reference

### Module structure

The codebase is split across four Python files, each with a single, clearly bounded responsibility. No module reaches into another module's domain.

```
data_append/
├── main.py          Orchestrator. Owns all user-facing dialogs and pipeline sequencing.
├── file_io.py       All disk I/O. Reads source and master files, writes new master.
├── column_mapper.py Fuzzy column matching and interactive mapping confirmation.
└── dedup.py         Duplicate detection and user decision prompting.
```

### Pipeline data flow

The diagram below shows the full sequence executed by `main()`, the module responsible for each step, and the data type passed forward to the next step.

```
  python main.py
        │
        ▼
  ┌─────────────────────────────────────────┐
  │  main.py  ·  pipeline entry point       │
  └──────────────────┬──────────────────────┘
                     │
       ┌─────────────▼──────────────┐
       │  1. Pick source file        │  tkinter file dialog
       │     file_io                 │
       │     load_source_file()      │
       └─────────────┬──────────────┘
                     │  source_df: DataFrame
       ┌─────────────▼──────────────┐
       │  2. Prompt driver name      │  terminal input
       │     main                   │
       │     prompt_driver_name()    │
       └─────────────┬──────────────┘
                     │  driver_name: str
       ┌─────────────▼──────────────┐
       │  3. Pick master folder      │  tkinter folder dialog
       │     file_io                 │
       │     find_latest_master()    │
       │     load_master()           │
       └─────────────┬──────────────┘
                     │  master_df: DataFrame
       ┌─────────────▼──────────────┐
       │  4. Column selection        │  terminal input
       │     column_mapper           │
       │     prompt_column_          │
       │     selection()             │
       └─────────────┬──────────────┘
                     │  selected_cols: list[str]
       ┌─────────────▼──────────────┐
       │  5. Fuzzy match +           │  terminal input
       │     mapping confirmation    │
       │     column_mapper           │
       │     compute_fuzzy_matches() │
       │     confirm_column_         │
       │     mapping()               │
       └─────────────┬──────────────┘
                     │  mapping: dict[str, str]
       ┌─────────────▼──────────────┐
       │  6. Apply mapping +         │
       │     inject Driver Name      │
       │     column_mapper           │
       │     apply_column_mapping()  │
       │     DataFrame.insert(0,     │
       │       "Driver Name", ...)   │
       └─────────────┬──────────────┘
                     │  mapped_df: DataFrame  (RangeIndex guaranteed)
       ┌─────────────▼──────────────┐
       │  7. Duplicate detection     │  terminal input
       │     dedup                   │
       │     find_duplicate_rows()   │
       │     prompt_dedup_decision() │
       └─────────────┬──────────────┘
                     │  filtered mapped_df: DataFrame
       ┌─────────────▼──────────────┐
       │  8. Write new master        │
       │     file_io                 │
       │     append_to_master()      │
       └─────────────┬──────────────┘
                     │  (rows_written: int, new_path: Path)
                     ▼
              new timestamped
              master CSV created
```

### Module reference

---

#### `main.py`

Entry point and orchestrator. Owns the `tkinter` file and folder dialogs, sequences every pipeline step, and handles all top-level error catching. Performs no I/O or data transformation directly.

| Function | Signature | What it does |
|---|---|---|
| `pick_file()` | `(title: str) -> Path` | Opens a native file picker dialog; calls `sys.exit(1)` if the user cancels. |
| `pick_folder()` | `(title: str) -> Path` | Opens a native folder picker dialog; calls `sys.exit(1)` if the user cancels. |
| `prompt_driver_name()` | `() -> str` | Loops until the user enters a non-empty string. |
| `main()` | `() -> None` | Runs the full pipeline in order; unpacks the `(int, Path)` tuple returned by `append_to_master`. |

---

#### `file_io.py`

All disk reads and writes. No interactive prompts live here. No data transformation beyond what is needed to load a file safely.

| Function | Signature | What it does |
|---|---|---|
| `load_source_file()` | `(path: str \| Path) -> DataFrame` | Reads `.xlsx` (with interactive sheet selection when multiple sheets exist) or `.csv`. Raises `FileNotFoundError` or `ValueError` on bad input. Uses `parse_dates=False` on all reads. |
| `find_latest_master()` | `(folder: str \| Path) -> Path \| None` | Scans a folder for `.csv` and `.xlsx` files and returns the path with the highest `mtime`. Returns `None` if the folder has no candidates. |
| `load_master()` | `(path: Path) -> DataFrame` | Delegates to `load_source_file()`. Returns an empty `DataFrame` if the file is zero bytes. |
| `append_to_master()` | `(master_df, new_rows, output_path) -> tuple[int, Path]` | Concatenates master and new rows, writes to a new timestamped CSV in the same folder as `output_path`. Never modifies the original master file. Returns `(rows_appended, new_file_path)`. |

---

#### `column_mapper.py`

Fuzzy column matching and interactive mapping confirmation. The only module that depends on `rapidfuzz`. Produces the `mapping` dict consumed by `apply_column_mapping`.

| Function | Signature | What it does |
|---|---|---|
| `compute_fuzzy_matches()` | `(source_cols, master_cols, score_cutoff=60.0) -> list[ColumnMatch]` | Runs `fuzz.WRatio` for each source column against all master columns. Returns one `ColumnMatch` per source column; columns with no match above the cutoff get `master_col=None, score=0.0`. |
| `prompt_column_selection()` | `(source_df) -> list[str]` | Prints a numbered column list; accepts comma-separated indices or `all`. Never returns an empty list — the loop rejects empty input. |
| `confirm_column_mapping()` | `(matches, master_cols) -> dict[str, str]` | Auto-accepts matches with score ≥ 80. Presents lower-confidence matches as a numbered list for bulk selection, then steps through each selected one for individual confirmation. Returns `{source_col: master_col}`; skipped columns are absent. |
| `apply_column_mapping()` | `(source_df, mapping) -> DataFrame` | Subsets source columns to those in `mapping`, renames them per the mapping, and calls `reset_index(drop=True)`. The clean `RangeIndex` is a required invariant for dedup arithmetic. |

`ColumnMatch` dataclass fields: `source_col: str`, `master_col: Optional[str]`, `score: float`, `confirmed: bool = False`.

---

#### `dedup.py`

Duplicate detection by value comparison, not by row ID. Operates on normalised data so whitespace and capitalisation differences do not cause missed duplicates.

| Function | Signature | What it does |
|---|---|---|
| `normalize_for_comparison()` | `(df) -> DataFrame` | Returns a copy of `df` where all `object`-dtype columns are `strip()`ped and `lower()`cased. `NaN` values become the string `"nan"` via `astype(str)`. |
| `find_duplicate_rows()` | `(incoming_df, master_df, subset=None) -> pd.Index` | Concatenates normalised master and incoming frames, runs `duplicated(keep="first")` so master rows are never flagged, and returns positional integers (0-based) into `incoming_df`. |
| `prompt_dedup_decision()` | `(dupe_count, total_incoming) -> Literal["append_all", "skip_dupes", "cancel"]` | Presents the three-option menu and returns a string literal. |

---

### Design decisions

This section documents non-obvious choices: what was decided, why, and what tradeoff was accepted. Intended for anyone modifying the pipeline.

---

**1. Fuzzy match auto-accept threshold: score ≥ 80**

Matches scoring 80 or above on `fuzz.WRatio` are accepted without user review. Matches below 80 are queued for manual confirmation.

*Why 80:* In practice, column names from recurring exports (e.g. "First Name" vs "first_name") consistently score in the 85–95 range. Scores in the 60–79 range represent plausible but ambiguous matches (e.g. "Email" vs "Email Address") that are worth a human check. A threshold of 80 eliminates routine confirmations while still surfacing cases where a wrong mapping would otherwise go unnoticed.

*Tradeoff:* A higher threshold means more prompts; a lower one means more silent wrong mappings. 80 was chosen empirically.

---

**2. Fuzzy match display cutoff: score < 60 shown as NO MATCH**

Columns scoring below 60 are displayed as `NO MATCH` rather than showing the low-confidence suggestion.

*Why 60:* Below this score, the suggested match is more likely to mislead the user than help them. Forcing an explicit decision is safer than anchoring the user on a bad suggestion.

---

**3. Scorer: `fuzz.WRatio`**

`WRatio` (Weighted Ratio) is used instead of the simpler `fuzz.ratio` or `fuzz.partial_ratio`.

*Why WRatio:* It internally selects the best of several comparison strategies — token sort, token set, partial ratio — depending on the input. This makes it robust to reordered words ("Last Name" vs "Name Last"), abbreviations, and extra tokens, all of which appear regularly in real-world column names.

---

**4. `parse_dates=False` on all reads**

Every `pd.read_csv` and `pd.read_excel` call explicitly passes `parse_dates=False`.

*Why:* Pandas's default date inference is aggressive. A column named "ID" containing values like "2026-04-30" would be silently coerced to `datetime64`. This corrupts data without raising an error and is especially dangerous for deduplication, where the normalised string comparison would then operate on datetime objects rather than the original strings. `parse_dates=False` disables this inference entirely.

---

**5. `reset_index(drop=True)` invariant in `apply_column_mapping`**

`apply_column_mapping()` always calls `reset_index(drop=True)` on its output. This is a required invariant, not an optional cleanup.

*Why:* `find_duplicate_rows()` returns a `pd.Index` of *positional integers* (0-based row positions within `incoming_df`). `main.py` then calls `mapped_df.drop(index=dupe_index)`, which performs label-based dropping. If `mapped_df` retained its original index from a slice of the source file, label-based `drop` would silently drop the wrong rows — the integer labels would not correspond to positions. The `reset_index` call makes index labels equal positions, preventing this class of bug.

---

**6. Deduplication strategy: concat-then-`duplicated(keep="first")`**

Rather than comparing incoming rows against the master row by row, the two normalised frames are concatenated and `DataFrame.duplicated(keep="first")` is run on the combined frame.

*Why:* `keep="first"` marks any row that is a duplicate of an *earlier* row in the combined frame. Since master rows are placed first in the concat, master rows are never flagged — only incoming rows that match an existing master row (or match each other) are marked. This is correct by definition: the master is the source of truth.

*Positional offset arithmetic:* After marking, the code filters positions `>= len(master_df)` (the incoming section) and subtracts `len(master_df)` to convert combined-frame positions back to `incoming_df`-local positions, which match its `RangeIndex` labels.

---

**7. NaN treatment in `normalize_for_comparison`**

`object`-dtype columns are normalised with `astype(str)` before `strip()` and `lower()`. This converts `NaN` to the string `"nan"`.

*Why this is intentional:* Two rows that are both `NaN` in a key column are treated as duplicates of each other. This is conservative: a row with all-null key fields is ambiguous, and silently appending many null-keyed rows is more dangerous than over-flagging them. The module docstring documents this and advises callers to fill or drop `NaN` upstream if this behaviour is undesirable.

---

**8. Master file selected by `mtime`**

`find_latest_master()` picks the most recently modified file in the master folder. It scans both `.csv` and `.xlsx` files. It does not use filename patterns or any explicit configuration.

*Why:* Zero configuration required. The user does not need to track or specify the master filename — the most recently written file is always the correct one given the tool's own timestamped naming convention.

*Known limitation:* `mtime` can be spoofed by a file copy or a manual timestamp change, causing the wrong file to be selected. The recommended mitigation is to keep the master folder clean, containing only master files produced by this tool.

---

**9. New timestamped output file — original master never modified**

`append_to_master()` writes the combined data to a *new* file named `<original_stem>_<YYYY-MM-DD_HH-MM>.csv` in the same folder. It does not overwrite or modify the existing master in any way.

*Why:* Protects against partial writes, user error, and silent corruption. If something goes wrong with an append run, the previous master is untouched and the run can be re-attempted cleanly. The timestamped naming also provides an automatic audit trail of every weekly run.

*Tradeoff:* The master folder accumulates one new file per run. Users should periodically archive or remove older versions.

---

**10. Driver Name injected at column position 0**

After `apply_column_mapping()`, `main.py` inserts the driver name as the first column of `mapped_df` using `DataFrame.insert(0, "Driver Name", driver_name)`.

*Why position 0:* Placing it first makes it immediately visible when the CSV is opened in a spreadsheet application. It also guarantees the column is present and consistently positioned in every row of every append, making it trivial to filter or group by driver in downstream analysis.

*Note:* The Driver Name column is appended-data-only — it is not retroactively added to existing master rows. Rows from earlier runs will have whatever value they had in this column at the time they were appended (or `NaN` if the column did not exist in those earlier runs).

---

**11. Duplicate column deduplication before `pd.concat`**

Both `master_df` and `new_rows` are filtered with `df.loc[:, ~df.columns.duplicated()]` before any `pd.concat` call.

*Why:* Real-world source files frequently contain duplicate column names (two columns both named "Notes", for example). `pd.concat` with duplicate column names in either input either raises an error or produces a frame where column-name indexing returns multiple columns, breaking all downstream operations. The deduplication is applied defensively at both the dedup step and the write step.

---

**12. Encoding fallback: UTF-8 → Latin-1**

`load_source_file()` first attempts to read CSV files as UTF-8. On `UnicodeDecodeError`, it retries with Latin-1 (ISO 8859-1).

*Why Latin-1:* Latin-1 maps every possible byte value to a character, so it never raises a decode error. It correctly handles the Western European characters (accented letters, special punctuation) that commonly appear in names and addresses. Files with mixed encodings — part UTF-8, part Latin-1 — may still corrupt silently; this is a documented known limitation.

---

### Key invariants — quick reference

A condensed reference for anyone modifying the pipeline. Violating any of these produces silent data corruption, not an immediate error.

| Invariant | Enforced in | What breaks if violated |
|---|---|---|
| `apply_column_mapping` always calls `reset_index(drop=True)` | `column_mapper.py` | Dedup drops the wrong rows silently |
| `master_df` and `new_rows` are column-deduplicated before any `concat` | `file_io.py`, `dedup.py` | `pd.concat` crashes or produces unfilterable duplicate columns |
| `append_to_master` returns `(int, Path)` | `file_io.py` | `main.py` unpack raises `ValueError` |
| All reads use `parse_dates=False` | `file_io.py` | Numeric or string columns silently coerced to `datetime64` |
| Master rows placed first in dedup concat | `dedup.py` | Master rows incorrectly flagged as duplicates and dropped |
