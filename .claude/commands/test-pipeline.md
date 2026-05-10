# test-pipeline

Runs the project's functional test suite against all non-interactive pipeline modules and reports results.

## What this tests

- `compute_fuzzy_matches` — match quality, cutoffs, empty inputs
- `apply_column_mapping` — renaming, subsetting, RangeIndex invariant, missing columns
- `normalize_for_comparison` — whitespace, casing, NaN handling, no mutation of originals
- `find_duplicate_rows` — detection accuracy, case insensitivity, master rows never flagged, positional index validity
- `append_to_master` — new file creation, original preserved, row counts, return type, duplicate column safety
- `load_source_file` — CSV loading, missing file error, unsupported extension error, parse_dates=False

Interactive functions (`prompt_*`, `pick_*`) are not tested here — they require terminal input.

## Steps

1. Verify `tests/test_pipeline.py` exists. If it does not, stop and tell the user.

2. Check that pytest is available by running:
   ```
   python -m pytest --version
   ```
   If it fails with ModuleNotFoundError, run `pip install pytest` first.

3. Run the full test suite from the project root:
   ```
   python -m pytest tests/test_pipeline.py -v --tb=short
   ```
   If that fails due to import errors, the venv is likely inactive. Prepend `source .venv/bin/activate &&` and retry.

4. Report results clearly:
   - Total tests run, passed, failed, errored
   - For each failure: test name, the exact assertion that failed, and a plain-English explanation of what it means for the pipeline
   - If all pass: confirm which modules are clean and note anything worth watching

5. If any test fails, check whether the failure is in the test itself (wrong fixture, stale assumption) or in the production code, and say which it is.
