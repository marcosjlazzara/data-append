"""
tests/test_pipeline.py — Functional tests for all non-interactive pipeline modules.

Covers: column_mapper, dedup, file_io (non-interactive functions only).
Interactive functions (prompt_*, pick_*) are excluded — they require terminal input.

Run with:
    python -m pytest tests/test_pipeline.py -v
or via the /test-pipeline Claude Code skill.
"""

import pandas as pd
import pytest
from pathlib import Path

from column_mapper import apply_column_mapping, compute_fuzzy_matches
from dedup import find_duplicate_rows, normalize_for_comparison
from file_io import append_to_master, load_source_file


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def source_cols():
    return ["First Name", "Last Name", "Email Address", "Company", "Revenue"]


@pytest.fixture
def master_cols():
    return ["first_name", "last_name", "email", "company_name"]


@pytest.fixture
def source_df():
    return pd.DataFrame({
        "First Name":    ["Alice", "Bob", "Charlie", "Diana", "Eve"],
        "Last Name":     ["Smith", "Jones", "Brown",  "Taylor", "Wilson"],
        "Email Address": ["alice@x.com", "bob@x.com", "charlie@x.com", "diana@x.com", "eve@x.com"],
        "Company":       ["Acme", "Beta", "Gamma", "Delta", "Epsilon"],
        "Revenue":       [1000, 2000, 3000, 4000, 5000],
    })


@pytest.fixture
def master_df():
    return pd.DataFrame({
        "first_name":   ["Alice", "Bob", "Zara"],
        "last_name":    ["Smith", "Jones", "Khan"],
        "email":        ["alice@x.com", "bob@x.com", "zara@x.com"],
        "company_name": ["Acme", "Beta", "Omega"],
    })


@pytest.fixture
def tmp_master_path(tmp_path):
    path = tmp_path / "master.csv"
    pd.DataFrame({
        "first_name": ["Alice", "Bob"],
        "last_name":  ["Smith", "Jones"],
    }).to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# compute_fuzzy_matches
# ---------------------------------------------------------------------------

class TestComputeFuzzyMatches:

    def test_high_confidence_match(self, source_cols, master_cols):
        matches = compute_fuzzy_matches(source_cols, master_cols)
        first = next(m for m in matches if m.source_col == "First Name")
        assert first.master_col == "first_name"
        # WRatio scores "First Name" vs "first_name" at ~70 (medium-confidence bucket,
        # not auto-accepted). Assert a suggestion is returned above the display cutoff.
        assert first.score >= 60

    def test_unrelated_column_returns_no_match(self, master_cols):
        # "Revenue" has no close match among name/email/company columns
        matches = compute_fuzzy_matches(["Revenue"], master_cols)
        assert matches[0].master_col is None
        assert matches[0].score == 0.0

    def test_one_match_object_per_source_col(self, source_cols, master_cols):
        matches = compute_fuzzy_matches(source_cols, master_cols)
        assert len(matches) == len(source_cols)

    def test_empty_source_returns_empty_list(self, master_cols):
        assert compute_fuzzy_matches([], master_cols) == []

    def test_score_cutoff_respected(self, master_cols):
        # A completely unrelated column should score below any reasonable cutoff
        matches = compute_fuzzy_matches(["XYZ_ZZZZ_999"], master_cols, score_cutoff=60.0)
        assert matches[0].master_col is None


# ---------------------------------------------------------------------------
# apply_column_mapping
# ---------------------------------------------------------------------------

class TestApplyColumnMapping:

    def test_renames_columns_to_master_names(self, source_df):
        mapping = {"First Name": "first_name", "Email Address": "email"}
        result = apply_column_mapping(source_df, mapping)
        assert "first_name" in result.columns
        assert "email" in result.columns
        assert "First Name" not in result.columns

    def test_subsets_to_mapped_columns_only(self, source_df):
        mapping = {"First Name": "first_name"}
        result = apply_column_mapping(source_df, mapping)
        assert list(result.columns) == ["first_name"]

    def test_output_always_has_clean_rangeindex(self, source_df):
        # Simulate a sliced DataFrame whose index does not start at 0
        sliced = source_df.iloc[2:]
        mapping = {"First Name": "first_name", "Last Name": "last_name"}
        result = apply_column_mapping(sliced, mapping)
        pd.testing.assert_index_equal(result.index, pd.RangeIndex(len(result)))

    def test_preserves_row_count(self, source_df):
        mapping = {"First Name": "first_name", "Last Name": "last_name"}
        result = apply_column_mapping(source_df, mapping)
        assert len(result) == len(source_df)

    def test_missing_mapped_col_is_skipped_gracefully(self, source_df):
        # "Nonexistent" is in the mapping but not in source_df — should not crash
        mapping = {"First Name": "first_name", "Nonexistent": "other"}
        result = apply_column_mapping(source_df, mapping)
        assert "first_name" in result.columns
        assert "other" not in result.columns


# ---------------------------------------------------------------------------
# normalize_for_comparison
# ---------------------------------------------------------------------------

class TestNormalizeForComparison:

    def test_strips_leading_and_trailing_whitespace(self):
        df = pd.DataFrame({"name": ["  Alice  ", " Bob"]})
        result = normalize_for_comparison(df)
        assert result["name"].tolist() == ["alice", "bob"]

    def test_lowercases_strings(self):
        df = pd.DataFrame({"name": ["ALICE", "Bob", "cHaRliE"]})
        result = normalize_for_comparison(df)
        assert result["name"].tolist() == ["alice", "bob", "charlie"]

    def test_nan_stays_nan_after_normalisation(self):
        # NaN is not converted to the string "nan" — it stays NaN.
        # pandas duplicated() treats two NaN cells as equal, so dedup still works.
        df = pd.DataFrame({"name": [None, "alice"]})
        result = normalize_for_comparison(df)
        assert pd.isna(result["name"].iloc[0])

    def test_numeric_columns_are_not_modified(self):
        df = pd.DataFrame({"score": [1, 2, 3]})
        result = normalize_for_comparison(df)
        assert result["score"].tolist() == [1, 2, 3]

    def test_does_not_mutate_original_dataframe(self):
        df = pd.DataFrame({"name": ["ALICE"]})
        _ = normalize_for_comparison(df)
        assert df["name"].iloc[0] == "ALICE"

    def test_mixed_column_types_handled(self):
        df = pd.DataFrame({"name": ["ALICE", "Bob"], "score": [10, 20]})
        result = normalize_for_comparison(df)
        assert result["name"].tolist() == ["alice", "bob"]
        assert result["score"].tolist() == [10, 20]


# ---------------------------------------------------------------------------
# find_duplicate_rows
# ---------------------------------------------------------------------------

class TestFindDuplicateRows:

    def test_detects_one_exact_duplicate(self, master_df):
        incoming = pd.DataFrame({
            "first_name":   ["Alice",   "Charlie"],
            "last_name":    ["Smith",   "Brown"],
            "email":        ["alice@x.com", "charlie@x.com"],
            "company_name": ["Acme",    "Gamma"],
        })
        dupes = find_duplicate_rows(incoming, master_df)
        assert len(dupes) == 1
        assert 0 in dupes  # Alice is at position 0 of incoming

    def test_master_rows_are_never_flagged(self, master_df):
        # When incoming == master, all incoming rows should be flagged (they duplicate master)
        dupes = find_duplicate_rows(master_df.copy(), master_df)
        assert len(dupes) == len(master_df)

    def test_empty_master_returns_empty_index(self, source_df):
        dupes = find_duplicate_rows(source_df, pd.DataFrame())
        assert len(dupes) == 0

    def test_no_duplicates_returns_empty_index(self, master_df):
        incoming = pd.DataFrame({
            "first_name":   ["Zach"],
            "last_name":    ["Morris"],
            "email":        ["zach@x.com"],
            "company_name": ["NewCo"],
        })
        dupes = find_duplicate_rows(incoming, master_df)
        assert len(dupes) == 0

    def test_detection_is_case_insensitive(self, master_df):
        # "ALICE" / "SMITH" should match "Alice" / "Smith" after normalisation
        incoming = pd.DataFrame({
            "first_name":   ["ALICE"],
            "last_name":    ["SMITH"],
            "email":        ["alice@x.com"],
            "company_name": ["Acme"],
        })
        dupes = find_duplicate_rows(incoming, master_df)
        assert len(dupes) == 1

    def test_no_common_columns_returns_empty_index(self):
        incoming = pd.DataFrame({"x": [1, 2]})
        master   = pd.DataFrame({"y": [3, 4]})
        dupes = find_duplicate_rows(incoming, master)
        assert len(dupes) == 0

    def test_returned_positions_are_valid_incoming_indices(self, master_df):
        incoming = pd.DataFrame({
            "first_name":   ["Alice", "Charlie", "Bob"],
            "last_name":    ["Smith", "Brown",   "Jones"],
            "email":        ["alice@x.com", "charlie@x.com", "bob@x.com"],
            "company_name": ["Acme", "Gamma", "Beta"],
        })
        dupes = find_duplicate_rows(incoming, master_df)
        for pos in dupes:
            assert 0 <= pos < len(incoming)


# ---------------------------------------------------------------------------
# append_to_master
# ---------------------------------------------------------------------------

class TestAppendToMaster:

    def test_creates_new_file_with_timestamp_in_name(self, tmp_master_path):
        master   = pd.read_csv(tmp_master_path)
        new_rows = pd.DataFrame({"first_name": ["Charlie"], "last_name": ["Brown"]})
        _, new_path = append_to_master(master, new_rows, tmp_master_path)
        assert new_path.exists()
        assert new_path != tmp_master_path
        assert tmp_master_path.stem in new_path.stem

    def test_original_master_file_is_not_modified(self, tmp_master_path):
        original_content = tmp_master_path.read_text()
        master   = pd.read_csv(tmp_master_path)
        new_rows = pd.DataFrame({"first_name": ["Charlie"], "last_name": ["Brown"]})
        append_to_master(master, new_rows, tmp_master_path)
        assert tmp_master_path.read_text() == original_content

    def test_correct_row_count_in_output(self, tmp_master_path):
        master   = pd.read_csv(tmp_master_path)
        new_rows = pd.DataFrame({
            "first_name": ["Charlie", "Diana"],
            "last_name":  ["Brown",   "Taylor"],
        })
        rows_written, new_path = append_to_master(master, new_rows, tmp_master_path)
        result = pd.read_csv(new_path)
        assert rows_written == 2
        assert len(result) == len(master) + 2

    def test_returns_int_and_path_tuple(self, tmp_master_path):
        master   = pd.read_csv(tmp_master_path)
        new_rows = pd.DataFrame({"first_name": ["X"], "last_name": ["Y"]})
        result   = append_to_master(master, new_rows, tmp_master_path)
        assert isinstance(result, tuple) and len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], Path)

    def test_empty_master_produces_correct_output(self, tmp_path):
        path     = tmp_path / "master.csv"
        path.write_text("")
        new_rows = pd.DataFrame({"first_name": ["Alice"], "last_name": ["Smith"]})
        rows_written, new_path = append_to_master(pd.DataFrame(), new_rows, path)
        result = pd.read_csv(new_path)
        assert rows_written == 1
        assert len(result) == 1

    def test_duplicate_columns_in_input_do_not_crash(self, tmp_master_path):
        master = pd.read_csv(tmp_master_path)
        # Manually inject a duplicate column into new_rows
        new_rows = pd.DataFrame([[" Charlie", "Brown"]], columns=["first_name", "first_name"])
        # Should not raise — duplicate cols are stripped before concat
        _, new_path = append_to_master(master, new_rows, tmp_master_path)
        assert new_path.exists()


# ---------------------------------------------------------------------------
# load_source_file
# ---------------------------------------------------------------------------

class TestLoadSourceFile:

    def test_loads_csv_correctly(self, tmp_path):
        path = tmp_path / "source.csv"
        pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_csv(path, index=False)
        df = load_source_file(path)
        assert len(df) == 2
        assert list(df.columns) == ["a", "b"]

    def test_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_source_file(tmp_path / "missing.csv")

    def test_raises_on_unsupported_extension(self, tmp_path):
        path = tmp_path / "file.xls"
        path.write_text("dummy")
        with pytest.raises(ValueError, match="Unsupported file extension"):
            load_source_file(path)

    def test_parse_dates_false_preserves_date_like_strings(self, tmp_path):
        path = tmp_path / "dates.csv"
        pd.DataFrame({"date": ["2026-04-30", "2026-05-01"]}).to_csv(path, index=False)
        df = load_source_file(path)
        # Must not be coerced to datetime64 — may be object or StringDtype depending on pandas version
        assert not pd.api.types.is_datetime64_any_dtype(df["date"])
