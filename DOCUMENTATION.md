# Weekly Data Append Pipeline — User Documentation

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Requirements](#2-requirements)
3. [Installation](#3-installation)
4. [How to Run](#4-how-to-run)
5. [Step-by-Step Walkthrough](#5-step-by-step-walkthrough)
6. [File Reference](#6-file-reference)
7. [Enabling Debug Logging](#7-enabling-debug-logging)
8. [Edge Cases and Error Messages](#8-edge-cases-and-error-messages)
9. [Weekly Workflow](#9-weekly-workflow)

---

## 1. Project Overview

**What it does:** This tool takes a new export file (an Excel `.xlsx` or `.csv`) and appends its rows to a running "master" CSV that accumulates data week over week. It handles three things that would otherwise require manual effort in a spreadsheet:

- **Column alignment** — your new export probably has different column names than the master. The tool fuzzy-matches them automatically and lets you confirm or correct each mapping before anything is written.
- **Deduplication** — if any rows in the new export already exist in the master, the tool tells you exactly how many and lets you choose whether to skip them, include them anyway, or abort.
- **Safe writing** — the master file is updated using a write-then-swap strategy so a crash or interruption mid-write cannot corrupt your existing data.

**What problem it solves:** Manually copying rows from a weekly export into a master spreadsheet is error-prone and slow, especially when column names change between exports or when the same records appear in more than one week's file. This tool automates the repetitive parts while keeping a human in the loop for any decision that requires judgment.

**Who it is for:** Anyone who receives a recurring data export (from a CRM, reporting platform, data warehouse, etc.) and needs to accumulate those records over time into a single CSV file. No programming knowledge is required to run it — every step is an interactive prompt in plain English.

---

## 2. Requirements

| Requirement | Minimum Version |
|---|---|
| Python | 3.10 or later |
| pandas | 2.0 or later |
| openpyxl | 3.1 or later |
| rapidfuzz | 3.0 or later |
| rich | 13.0 or later |

`openpyxl` is used to read `.xlsx` files. `rapidfuzz` powers the fuzzy column-name matching. `rich` formats the interactive tables and coloured prompts you see in the terminal.

---

## 3. Installation

Follow these steps exactly, in order. You only need to do this once per machine.

**Step 1 — Get the project files**

If you received a zip file, unzip it to a folder of your choice (for example, `~/data_append`). If you are cloning from a Git repository:

```bash
git clone <repository-url> ~/data_append
cd ~/data_append
```

**Step 2 — Check your Python version**

Open a terminal and run:

```bash
python3 --version
```

You should see `Python 3.10.x` or higher. If you see `Python 2.x.x` or an error, install Python 3.10+ from [python.org](https://www.python.org/downloads/) before continuing.

**Step 3 — Create a virtual environment**

A virtual environment keeps the tool's dependencies isolated from anything else on your machine.

```bash
python3 -m venv ~/data_append/.venv
```

**Step 4 — Activate the virtual environment**

On macOS and Linux:

```bash
source ~/data_append/.venv/bin/activate
```

On Windows (Command Prompt):

```bat
~/data_append\.venv\Scripts\activate.bat
```

On Windows (PowerShell):

```powershell
~/data_append\.venv\Scripts\Activate.ps1
```

Your terminal prompt should now show `(.venv)` at the beginning — this confirms the environment is active.

**Step 5 — Install dependencies**

```bash
pip install -r ~/data_append/requirements.txt
```

This downloads and installs the four required libraries listed in the requirements file. It should take less than a minute.

**Verification** — confirm everything installed correctly:

```bash
python -c "import pandas, openpyxl, rapidfuzz, rich; print('All dependencies OK')"
```

You should see `All dependencies OK`.

---

## 4. How to Run

Every time you want to run the tool, open a terminal, activate the virtual environment (Step 4 above), navigate to the project folder, and run:

```bash
python main.py
```

That is the only command. Everything else happens interactively — the tool will ask you for all the information it needs.

> **Note:** You must activate the virtual environment each time you open a new terminal window before running the script. If you see `ModuleNotFoundError: No module named 'pandas'` (or similar), it means the virtual environment is not active.

---

## 5. Step-by-Step Walkthrough

This section walks through every prompt you will see when you run `python main.py`. Follow along in order. Example inputs are shown in `code blocks`.

---

### Step 1 — Welcome banner

When the script starts, you will see a styled banner:

```
────────────────── Weekly Data Append Pipeline ──────────────────
```

No action needed — this is just a confirmation the script is running.

---

### Step 2 — Source file path

```
Source file path (.xlsx or .csv):
```

Type the full path to this week's new export file and press Enter.

**Examples:**

```
/Users/jane/Downloads/weekly_export_2026-04-30.xlsx
```

```
C:\Users\jane\Downloads\weekly_export.csv
```

You can also use `~` as a shortcut for your home folder:

```
~/Downloads/weekly_export.xlsx
```

After you enter the path, the tool will load the file and confirm how many rows and columns it found:

```
  Loaded 1,432 rows, 12 columns from weekly_export_2026-04-30.xlsx
```

**If your Excel file has multiple sheets**, the tool will list them and ask you to pick one:

```
Multiple sheets found:
  [0] Sheet1
  [1] Data
  [2] Archive
Select sheet index:
```

Type the number next to the sheet you want (for example, `1` for "Data") and press Enter.

---

### Step 3 — Master folder path

```
Master folder path:
```

Type the path to the folder that contains your master CSV file and press Enter.

```
/Users/jane/Documents/master_data
```

The tool will automatically find the most recently modified CSV file in that folder and use it as the master. It will tell you which file it found and how many rows it currently contains:

```
  Using master master_records.csv — 8,750 rows.
```

**If the folder contains no CSV files yet** (the very first time you run this), the tool will ask you to name the new master file it will create:

```
No CSV files found in '/Users/jane/Documents/master_data'.
Path for new master file [/Users/jane/Documents/master_data/master.csv]:
```

Press Enter to accept the suggested name, or type a different path and press Enter. The master file will be created automatically at the end of the run.

---

### Step 4 — Column selection

The tool prints a numbered list of every column in your source file:

```
Source columns:
  [0] First Name
  [1] Last Name
  [2] Email Address
  [3] Phone
  [4] Company
  [5] Revenue
  [6] Internal ID
  [7] Notes
  [8] Last Updated

Enter column indices (comma-separated) or 'all':
```

You have two options:

- Type `all` to include every column from the source file.
- Type a comma-separated list of the index numbers for the columns you want.

**Example — selecting specific columns:**

```
0, 1, 2, 4, 5
```

This would select: First Name, Last Name, Email Address, Company, Revenue.

**Example — selecting all:**

```
all
```

After you confirm, the tool shows which columns were selected:

```
  Selected 5 column(s): First Name, Last Name, Email Address, Company, Revenue
```

---

### Step 5 — Column mapping review

The tool compares your selected source column names against the column names in the master CSV using fuzzy matching (it looks for names that sound or look similar, even if they are not identical). It then prints a table showing its best guess for each mapping:

```
              Column Match Overview
┌──────────────┬──────────────────────────┬───────┐
│ Source Column│ Suggested Master Column  │ Score │
├──────────────┼──────────────────────────┼───────┤
│ First Name   │ first_name               │   90  │
│ Last Name    │ last_name                │   90  │
│ Email Address│ email                    │   72  │
│ Company      │ company_name             │   80  │
│ Revenue      │ NO MATCH                 │   —   │
└──────────────┴──────────────────────────┴───────┘
```

**Score colour guide:**

| Colour | Score range | Meaning |
|---|---|---|
| Green | 75 and above | High confidence match — likely correct |
| Yellow | 60–74 | Moderate confidence — worth double-checking |
| Red / NO MATCH | Below 60 or no match | The tool could not find a close enough match |

The tool then steps through each row one at a time and asks you to confirm, override, skip, or create a new column:

```
  Row 1 — "First Name" → "first_name" (score 90). Accept? [Enter/override/skip/new]:
```

**Your options for each row:**

| What to type | What it does |
|---|---|
| Press **Enter** (nothing) | Accept the suggested mapping |
| A master column name | Override — map this source column to a different master column |
| `skip` | Exclude this source column entirely — it will not be appended |
| `new` | Create a brand-new column in the master using the source column's exact name |

**Example session:**

```
  Row 1 — "First Name" → "first_name" (score 90). Accept? [Enter/override/skip/new]:
  [just pressed Enter — accepted]

  Row 2 — "Last Name" → "last_name" (score 90). Accept? [Enter/override/skip/new]:
  [just pressed Enter — accepted]

  Row 3 — "Email Address" → "email" (score 72). Accept? [Enter/override/skip/new]:
  [just pressed Enter — accepted]

  Row 4 — "Company" → "company_name" (score 80). Accept? [Enter/override/skip/new]:
  [just pressed Enter — accepted]

  Row 5 — "Revenue" → NO MATCH. Type a master column, 'skip', or 'new':
  new
    New column 'Revenue' will be created in master.
```

After all rows are confirmed, the tool prints a final summary of every mapping:

```
Final column mapping:
Source          -> Master
──────────────────────────────
First Name      -> first_name
Last Name       -> last_name
Email Address   -> email
Company         -> company_name
Revenue         -> Revenue
```

**Warnings you may see at this stage:**

- If the master has columns that no source column maps to, those columns will be filled with blank (NaN) values in all newly appended rows. The tool warns you:

  ```
  Note: 2 master column(s) have no matching source column and will be NaN in all new rows: internal_id, notes
  ```

- If you marked any column as `new`, those new columns will be blank for all existing rows in the master:

  ```
  Note: 1 new column(s) will be added to the master. All existing master rows will be NaN for these columns: Revenue
  ```

---

### Step 6 — Duplicate detection

The tool checks every row in your new, mapped data against the master and counts exact matches. If none are found, it skips this step silently. If duplicates are found, you see:

```
Found 47 duplicate row(s) out of 1,432 incoming row(s).
  [1] Append all rows (including duplicates)
  [2] Skip duplicates — append 1,385 new row(s) only
  [3] Cancel — do not write anything

Your choice [1/2/3]:
```

| Choice | What happens |
|---|---|
| `1` | All 1,432 rows are appended, including the 47 that already exist in the master |
| `2` | Only the 1,385 genuinely new rows are appended; the 47 duplicates are dropped |
| `3` | Nothing is written; the master file is left completely unchanged |

Type `1`, `2`, or `3` and press Enter.

---

### Step 7 — Done

If everything succeeds, the tool prints a completion banner:

```
────────────────────────── Done ──────────────────────────
  1,385 row(s) appended to /Users/jane/Documents/master_data/master_records.csv.
```

The master CSV has been updated. You can open it in Excel or any other tool immediately.

---

## 6. File Reference

The project is made up of four Python files. Here is what each one does.

---

### `main.py`

The entry point — the file you run with `python main.py`. It calls functions from the other three files in the correct order and handles top-level errors.

| Function | What it does |
|---|---|
| `prompt_path(label)` | Asks the user for a file or folder path and repeats the prompt until a non-empty value is entered. |
| `main()` | Orchestrates the full pipeline: loads the source file, finds the master, runs column selection and mapping, runs duplicate detection, and writes the final output. |

---

### `file_io.py`

Handles all reading from and writing to disk. No interactive prompts live here — it is purely about file operations.

| Function | What it does |
|---|---|
| `load_source_file(path)` | Opens an `.xlsx` or `.csv` file and returns its contents as a table; raises a clear error if the file does not exist or the format is unsupported. |
| `find_latest_master(folder)` | Scans a folder for CSV files and returns the path to the one most recently modified; returns nothing if the folder contains no CSVs. |
| `load_master(path)` | Reads the master CSV into a table, gracefully handling a zero-byte (empty) file; tries UTF-8 encoding first and falls back to Latin-1 if needed. |
| `append_to_master(master_df, new_rows, output_path)` | Combines the master and new rows, writes the result to a temporary file, then atomically replaces the master file so a mid-write crash cannot corrupt it. |

---

### `column_mapper.py`

Handles the interactive column selection and mapping workflow: showing the user what columns exist, fuzzy-matching them to the master, and collecting per-column decisions.

| Function | What it does |
|---|---|
| `compute_fuzzy_matches(source_cols, master_cols)` | Compares each source column name against all master column names using fuzzy string matching and returns a ranked suggestion for each. |
| `prompt_column_selection(source_df)` | Prints a numbered list of source columns and asks the user to pick which ones to include (by index number or `all`). |
| `confirm_column_mapping(matches, master_cols)` | Steps through each fuzzy-matched column one at a time, lets the user accept the suggestion or override it, and builds the final source-to-master column mapping. |
| `apply_column_mapping(source_df, mapping)` | Filters the source table down to only the selected columns and renames them to match the master's column names. |

---

### `dedup.py`

Handles duplicate detection: comparing incoming rows against the master and asking the user what to do.

| Function | What it does |
|---|---|
| `normalize_for_comparison(df)` | Returns a cleaned copy of a table where all text columns are trimmed of whitespace and converted to lowercase, so differences in spacing or capitalisation do not cause missed duplicates. |
| `find_duplicate_rows(incoming_df, master_df)` | Identifies which rows in the new data already exist in the master (after normalisation) and returns their row positions so they can be dropped or kept. |
| `prompt_dedup_decision(dupe_count, total_incoming)` | Tells the user how many duplicates were found and presents three choices: append all, skip duplicates, or cancel. |

---

## 7. Enabling Debug Logging

By default, the tool runs silently — you only see the interactive prompts and results. If something goes wrong and you need to see exactly what the tool is doing internally, you can enable detailed debug output by setting the `LOG_LEVEL` environment variable before running the script.

**macOS / Linux:**

```bash
LOG_LEVEL=DEBUG python main.py
```

**Windows (Command Prompt):**

```bat
set LOG_LEVEL=DEBUG
python main.py
```

**Windows (PowerShell):**

```powershell
$env:LOG_LEVEL="DEBUG"
python main.py
```

With debug logging enabled, you will see timestamped lines like these alongside the normal prompts:

```
2026-04-30T09:14:02 DEBUG    file_io — Loading source file | path=weekly_export.xlsx ext=.xlsx
2026-04-30T09:14:02 DEBUG    file_io — Single sheet detected | sheet=Sheet1
2026-04-30T09:14:03 DEBUG    column_mapper — Fuzzy match | source_col='Email Address' master_col='email' score=72
2026-04-30T09:14:05 DEBUG    dedup — Checking duplicates | subset=['first_name', 'email'] master_rows=8750 incoming_rows=1432
```

This is most useful when:
- A column mapping is not being suggested as expected (you can see the exact fuzzy score).
- You are unsure which master file was selected (the path is logged).
- Duplicate detection returns unexpected results (you can see which columns are being compared).

To turn it off, simply omit `LOG_LEVEL=DEBUG` and the tool returns to its default silent mode.

---

## 8. Edge Cases and Error Messages

This section describes the most common problems users encounter, what the error message looks like, and what to do.

---

### Source file not found

**When it happens:** You typed a path to a file that does not exist or contains a typo.

**What you see:**

```
Error: Source file not found: /Users/jane/Downloads/export.xlsx
```

**What to do:** Check the path carefully, including the filename and extension. You can drag and drop the file from Finder (macOS) or Explorer (Windows) into the terminal to paste the correct path automatically.

---

### Unsupported file format

**When it happens:** You pointed the tool at a file with an extension other than `.xlsx` or `.csv` (for example, `.xls`, `.ods`, or `.txt`).

**What you see:**

```
Error: Unsupported file extension '.xls'. Expected .xlsx or .csv.
```

**What to do:** Open the file in Excel and use "Save As" to save it as either `.xlsx` or `.csv`, then run the tool again.

---

### Source file is empty (no rows)

**When it happens:** The file opened successfully but contained no data rows (just a header row, or nothing at all).

**What you see:**

```
Source file 'weekly_export.xlsx' contains no rows. Nothing to append. Exiting.
```

**What to do:** Verify the export from your source system actually contains data. Open the file manually to confirm.

---

### Master folder does not exist or is not a folder

**When it happens:** The path you entered for the master folder points to a file rather than a folder, or the folder does not exist.

**What you see:**

```
Error: '/Users/jane/Documents/master_data' is not a directory.
```

**What to do:** Make sure the folder exists and you typed the path to the folder itself, not to a file inside it.

---

### No master CSV found in the folder

**When it happens:** The folder you specified exists but contains no `.csv` files.

**What you see:**

```
No CSV files found in '/Users/jane/Documents/master_data'.
Path for new master file [/Users/jane/Documents/master_data/master.csv]:
```

**What to do:** This is not an error — it means this is the first run and a new master file will be created. Press Enter to accept the default path, or type a custom path for the new file.

If you expected a master file to be there, check that you pointed to the correct folder and that the file has a `.csv` extension.

---

### All incoming rows are duplicates

**When it happens:** Every row in your new export already exists in the master (you may be running the tool on the same export file twice).

**What you see after choosing option 2 (skip duplicates):**

```
  Dropped 1,432 duplicate row(s). 0 row(s) remain.

No rows to append after deduplication. Exiting.
```

**What to do:** Confirm you are using this week's new export file, not one you already appended. No data has been written to the master.

---

### No columns were mapped

**When it happens:** You skipped every column during the mapping step, so there is nothing to append.

**What you see:**

```
No columns mapped. Nothing to append. Exiting.
```

**What to do:** Re-run the tool and accept or assign at least one column during the mapping step.

---

### Override name not recognised

**When it happens:** During column mapping, you type a master column name to override the suggestion, but the tool cannot find it.

**What you see:**

```
    'emial' not found in master columns. Try again, or type 'skip'/'new'.
```

**What to do:** Check the spelling. Column name matching here is case-insensitive, but the name must otherwise be exact. Refer to the "Column Match Overview" table printed earlier in the session to see the exact master column names available.

---

### Encoding error (rare)

**When it happens:** The tool cannot read a CSV file because it contains special characters that are not in the standard UTF-8 encoding.

**What happens automatically:** The tool silently retries with Latin-1 encoding, which handles most Western European character sets. You will only see a warning in debug mode (`LOG_LEVEL=DEBUG`). If both encodings fail, you will see a Python traceback.

**What to do if you see a traceback related to encoding:** Open the file in Excel, then re-save it as CSV with UTF-8 encoding (in Excel, choose "CSV UTF-8 (Comma delimited)" from the "Save As" format list).

---

### Leftover `.tmp` file

**When it happens:** The tool was interrupted (e.g. power loss, force-quit) between writing the temporary file and replacing the master with it.

**What you see:** A file named `master.tmp` (or similar) sitting next to your master CSV.

**What to do:** It is safe to delete the `.tmp` file. Your original master CSV is intact — the swap had not yet happened when the interruption occurred. Re-run the tool normally.

---

## 9. Weekly Workflow

This is the intended usage pattern, designed to take a few minutes each week.

**Every week, when a new export arrives:**

1. Save the new export file somewhere accessible (your Downloads folder, a shared drive, etc.).
2. Open a terminal and activate the virtual environment:
   ```bash
   source ~/data_append/.venv/bin/activate
   ```
3. Run the tool:
   ```bash
   python main.py
   ```
4. When prompted for the **source file path**, enter the path to this week's new export.
5. When prompted for the **master folder path**, enter the path to the folder where your master CSV lives. The tool will automatically pick up the most recently modified CSV in that folder — you do not need to type the filename.
6. Select your columns, confirm the column mappings, and decide how to handle any duplicates.
7. The tool appends the new rows and exits. Your master CSV now contains everything from all previous weeks plus this week's new records.

**Tips for a smooth weekly run:**

- Keep your master CSV in a dedicated folder (e.g. `~/Documents/master_data/`) with nothing else in it. The tool picks the most recently modified CSV in the folder, so mixing other CSV files in that folder could cause the wrong file to be selected.
- After the tool runs, make a backup copy of the master CSV (or use a folder that is automatically synced to cloud storage). The tool writes safely, but a backup protects against accidental deletion.
- The column mapping step gets faster over time. If your export format is consistent week to week, you will likely just press Enter through every mapping confirmation.
- If you receive a file in `.xls` format (the older Excel format), save it as `.xlsx` before running the tool — `.xls` is not supported.
