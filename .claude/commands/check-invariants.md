# check-invariants

Statically verifies that the five code invariants documented in SYSTEM_OVERVIEW.md are still present in the source files. Run this after any refactor to confirm no invariant was accidentally removed.

This is a code inspection, not a runtime test — it reads source files directly and takes under a second to run.

## What it checks

1. `reset_index(drop=True)` is present in `apply_column_mapping` — without it, dedup silently drops the wrong rows
2. `parse_dates=False` is present on every `read_csv` and `read_excel` call — without it, date-like values are silently coerced to datetime64
3. `~df.columns.duplicated()` guard appears before every `pd.concat` in `file_io.py` and `dedup.py` — without it, source files with duplicate column names crash or corrupt the output
4. `norm_master` appears before `norm_incoming` in the dedup `pd.concat` — reversing the order means master rows get flagged as duplicates
5. `append_to_master` returns an `(int, Path)` tuple — any other return type breaks the two-value unpack in `main.py`

## Steps

1. Run the invariant checker:
   ```
   python scripts/check_invariants.py
   ```

2. Report results:
   - For each PASS: one line confirming the invariant is present
   - For each FAIL: what is missing, what silent corruption it causes, where to restore it, and the exact line(s) of code to put back

3. If all pass: confirm the codebase is clean.

4. If any fail: do not suggest workarounds — the invariant must be restored exactly as specified. Explain why in plain English before showing the fix.
