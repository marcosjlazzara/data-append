# validate-output

Validates the most recently created output CSV in the Outputs/ folder, or a specific file if a path is provided.

Run after every real pipeline run to confirm the output is clean before sharing or archiving it.

## What it checks

1. **Filename pattern** — follows `<stem>_YYYY-MM-DD_HH-MM-SS.csv` (confirms the file was produced by the pipeline, not manually copied)
2. **Has data rows** — file is not empty or header-only
3. **Driver Name column** — present and populated in at least some rows; reports how many appended vs pre-existing rows exist
4. **No fully duplicate rows** — detects possible double-appends
5. **No all-NaN columns** — warns if any column is entirely empty, which usually means a column mapping went wrong

## Steps

1. Run the validation script:
   ```
   python scripts/validate_output.py
   ```
   Or for a specific file:
   ```
   python scripts/validate_output.py "Outputs/filename.csv"
   ```

2. Report results:
   - For each PASS: one line confirming what was verified
   - For each FAIL: plain-English explanation of what failed and what most likely caused it
   - Summary line: all clear, or N checks failed

3. If any check fails, suggest the most likely fix based on the failure message:
   - Missing Driver Name column → pipeline was run before the Driver Name feature was added; the column will appear in future runs
   - Entirely-NaN Driver Name → the file may be an old master with no appended rows yet
   - Duplicate rows → the same source file may have been appended twice; re-run with dedup option 2 to remove them
   - All-NaN column → a source column was mapped to a master column but the source column had no data; check the mapping

4. If the Outputs/ directory is missing or empty, say so and stop.
