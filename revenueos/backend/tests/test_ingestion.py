"""Ingestion must survive whatever a POS export throws at it."""

from __future__ import annotations

import pytest

from app.data.ingestion import IngestionError, detect_delimiter, parse_number, read_table
from app.data.parsing import detect_dayfirst, parse_date, size_distance, normalise_color


class TestNumberParsing:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("1.234,56", 1234.56),      # European
            ("1,234.56", 1234.56),      # US
            ("€ 1.234,56", 1234.56),    # currency symbol + European
            ("1 234,56", 1234.56),      # space thousands
            ("€890", 890.0),
            ("45%", 45.0),
            ("(120)", -120.0),          # accounting negative
            ("1.234.567", 1234567.0),   # multiple European thousands
            ("0,5", 0.5),
            ("-89.5", -89.5),
            ("890", 890.0),
        ],
    )
    def test_parses_every_common_convention(self, raw, expected):
        assert parse_number(raw) == pytest.approx(expected)

    @pytest.mark.parametrize("raw", ["", "-", "n/a", "N/A", "null", "NaN", None, "abc"])
    def test_missing_becomes_none_never_zero(self, raw):
        # This is the rule the whole product depends on: unknown != 0.
        assert parse_number(raw) is None


class TestDelimiterDetection:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("a,b,c\n1,2,3\n4,5,6", ","),
            ("a;b;c\n1;2;3\n4;5;6", ";"),
            ("a\tb\tc\n1\t2\t3", "\t"),
            ("a|b|c\n1|2|3\n4|5|6", "|"),
        ],
    )
    def test_detects_delimiter(self, text, expected):
        assert detect_delimiter(text) == expected

    def test_prefers_the_consistent_delimiter(self):
        # commas appear inside the semicolon-separated values
        text = "name;note\nRossi;hello, world\nBianchi;a, b, c"
        assert detect_delimiter(text) == ";"


class TestDateParsing:
    def test_day_first_detected_from_evidence(self):
        assert detect_dayfirst(["25/03/2026", "14/02/2026"]) is True
        assert detect_dayfirst(["03/25/2026", "02/14/2026"]) is False

    def test_ambiguous_dates_default_to_european(self):
        assert detect_dayfirst(["03/04/2026", "05/06/2026"]) is True

    @pytest.mark.parametrize(
        "raw",
        ["2026-03-12", "12/03/2026", "12-03-2026", "12.03.2026", "12 Mar 2026",
         "2026-03-12 14:30:00"],
    )
    def test_parses_common_formats(self, raw):
        parsed = parse_date(raw)
        assert parsed is not None and parsed.year == 2026 and parsed.month == 3

    @pytest.mark.parametrize("raw", ["", "-", "0000-00-00", "not a date", None])
    def test_junk_dates_become_none(self, raw):
        assert parse_date(raw) is None


class TestReadTable:
    def test_reads_semicolon_european_csv(self):
        raw = "Nome Cliente;Totale;Ultimo Acquisto\nRossi;1.240,50;12/03/2026\n".encode()
        frame, report = read_table(raw, "clienti.csv")
        assert report.delimiter == ";"
        assert list(frame.columns) == ["Nome Cliente", "Totale", "Ultimo Acquisto"]
        assert len(frame) == 1

    def test_skips_preamble_rows_above_the_header(self):
        raw = (
            "Export generated 12/03/2026\n"
            "\n"
            "customer_id,name,total\n"
            "1,Rossi,100\n2,Bianchi,200\n"
        ).encode()
        frame, report = read_table(raw, "export.csv")
        assert report.header_row > 0
        assert "customer_id" in frame.columns
        assert len(frame) == 2

    def test_handles_cp1252_encoding(self):
        raw = "name,city\nCaf\xe9,M\xfcnchen\n".encode("cp1252")
        frame, report = read_table(raw, "latin.csv")
        assert report.encoding in {"cp1252", "latin-1"}
        assert len(frame) == 1

    def test_duplicate_headers_are_renamed_not_dropped(self):
        raw = b"name,name,total\nA,B,10\n"
        frame, report = read_table(raw, "dupes.csv")
        assert len(frame.columns) == 3
        assert report.renamed_duplicates

    def test_empty_columns_are_dropped(self):
        raw = b"a,b,c\n1,,3\n4,,6\n"
        frame, report = read_table(raw, "empty.csv")
        assert "b" in report.dropped_empty_columns
        assert list(frame.columns) == ["a", "c"]

    def test_a_row_wider_than_the_header_is_kept_not_dropped(self):
        """An unquoted delimiter inside a value must not destroy the file.

        Regression: pandas' on_bad_lines="skip" silently discarded every row
        wider than the header, leaving a file with almost no data and no warning.
        """
        raw = (
            "codice;nome;taglie;note\n"
            "A1;Rossi;M; 40;prima nota\n"      # an extra ';' inside "taglie"
            "A2;Bianchi;L; 43;\n"
            "A3;Conti;S;terza nota\n"
        ).encode()
        frame, report = read_table(raw, "ragged.csv")

        assert len(frame) == 3, "no row may be dropped without being reported"
        assert frame["codice"].tolist() == ["A1", "A2", "A3"]
        assert frame["nome"].tolist() == ["Rossi", "Bianchi", "Conti"]
        # the overflow lands in a named extra column rather than shifting values
        assert any(c.startswith("column_") for c in frame.columns)
        assert any("more values than the header" in w for w in report.warnings)

    def test_short_rows_are_padded_not_shifted(self):
        raw = b"a,b,c\n1,2,3\n4,5\n"
        frame, _ = read_table(raw, "short.csv")
        assert len(frame) == 2
        assert frame["a"].tolist() == ["1", "4"]
        assert frame["b"].tolist() == ["2", "5"]

    def test_empty_file_raises_a_clear_error(self):
        with pytest.raises(IngestionError):
            read_table(b"", "empty.csv")

    def test_headers_without_rows_do_not_crash(self):
        frame, report = read_table(b"customer_id,name\n", "headers.csv")
        assert len(frame) == 0
        assert report.warnings


class TestFashionValues:
    def test_size_distance_is_zero_for_identical_sizes(self):
        assert size_distance("M", "M") == 0.0

    def test_numeric_and_letter_sizes_are_comparable(self):
        # IT 42 maps to M, so this must not read as "incompatible"
        assert size_distance("42", "M") == 0.0

    def test_adjacent_sizes_are_close_not_far(self):
        assert 0 < size_distance("M", "L") < 0.5

    def test_incomparable_sizes_return_none_not_a_penalty(self):
        assert size_distance(None, "M") is None
        assert size_distance("M", None) is None

    @pytest.mark.parametrize(
        "raw,expected",
        [("Nero", "black"), ("NOIR", "black"), ("Cammello", "camel"),
         ("bianco", "white"), ("Testa di moro", "brown")],
    )
    def test_colours_normalise_across_languages(self, raw, expected):
        assert normalise_color(raw) == expected
