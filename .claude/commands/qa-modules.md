# qa-modules

Runs a deep QA analysis across all four pipeline modules in parallel using the python-qa-elite agent. Surfaces failure modes, edge case gaps, logging weaknesses, and implementation alternatives ranked by severity.

Use this before significant merges, before handing code to someone else, or after an unexpected production issue.

## Steps

1. Read all four source files in full:
   - `main.py`
   - `file_io.py`
   - `column_mapper.py`
   - `dedup.py`

2. Spawn four python-qa-elite agents **in parallel** (all four in a single message), one per module. Each agent prompt must include:

   - The full source code of the module being reviewed
   - The module's role in the pipeline (from the architecture below)
   - The contracts it must honour with the other modules
   - The four specific things to analyse (below)

   **Pipeline architecture context to include in every agent prompt:**
   ```
   This is a four-module Python pipeline that appends weekly export files to a master CSV.
   - main.py: orchestrator. Owns tkinter file/folder dialogs and pipeline sequencing.
   - file_io.py: all disk I/O. Reads source and master files, writes new timestamped master.
   - column_mapper.py: fuzzy column matching (rapidfuzz WRatio) and interactive mapping.
   - dedup.py: duplicate detection by value comparison after normalisation.
   End users are non-technical. The pipeline runs interactively with no config files.
   ```

   **Contracts to include per module:**

   - `main.py`: Must unpack `(int, Path)` from `append_to_master`. Must call `reset_index` result from `apply_column_mapping` before passing to dedup. Driver Name is inserted at column position 0 after `apply_column_mapping`.
   - `file_io.py`: `append_to_master` must return `(int, Path)`. Must never overwrite the original master. All reads must use `parse_dates=False`. Must deduplicate columns before `pd.concat`.
   - `column_mapper.py`: `apply_column_mapping` must always call `reset_index(drop=True)` on its output — required for dedup positional arithmetic. Score threshold 80 for auto-accept, 60 for display cutoff.
   - `dedup.py`: `find_duplicate_rows` returns positional integers into a clean RangeIndex DataFrame. Master rows must always be placed first in `pd.concat`. `normalize_for_comparison` must handle both `object` and `pd.StringDtype` columns.

   **Four things to analyse for each module:**
   1. **Failure modes** — inputs or runtime conditions that would cause a crash or silent wrong result. Include the exact scenario and what goes wrong.
   2. **Edge case gaps** — boundary conditions the code handles in the happy path but not at the edges. Be specific about what input triggers it.
   3. **Logging gaps** — important decisions or state changes that happen with no log output, making production debugging harder than it needs to be.
   4. **Implementation alternatives** — one or two spots where the current approach is fragile or unnecessarily complex, with a concrete simpler alternative shown as code.

   Ask each agent to return findings as a structured list, each item with: severity (High / Medium / Low), category (one of the four above), and a clear description. High = silent data corruption or crash; Medium = wrong result in edge case or misleading behaviour; Low = code quality or debuggability improvement.

3. Wait for all four agents to return, then consolidate:
   - Deduplicate any findings that overlap across modules
   - Sort all findings by severity: High first, then Medium, then Low
   - Present as a single ranked report with the module name next to each finding

4. End with a one-paragraph summary: overall code health, the most urgent thing to fix, and whether any finding warrants immediate action before the next production run.
