"""CSV ingestion and schema detection."""
from __future__ import annotations

from app.data import cleaning, ingestion
from app.data.mapping import detect_mapping, mapping_to_dict
from app.data.values import parse_date, parse_number


def _map(kind, text):
    parsed = ingestion.parse_csv(text)
    mapping = detect_mapping(kind, parsed.headers, parsed.rows)
    return parsed, {m.field: m.header for m in mapping if m.field}, mapping


def test_detects_semicolon_and_european_decimals():
    text = (
        "Nome Cliente;Ultimo Acquisto;Spesa Totale;N Ordini\n"
        "Giulia Rossi;12/05/2026;1.234,56;7\n"
        "Marco Bianchi;03/01/2026;980,00;3\n"
    )
    parsed, fields, _ = _map("customers", text)
    assert parsed.delimiter == ";"
    assert fields.get("name") == "Nome Cliente"
    assert fields.get("last_purchase_date") == "Ultimo Acquisto"
    assert fields.get("num_purchases") == "N Ordini"

    rows = cleaning.build_customers(parsed.rows, fields)
    assert rows[0]["total_spend"] == 1234.56
    assert rows[0]["last_purchase_date"] == parse_date("2026-05-12")


def test_maps_english_headers():
    text = (
        "Customer ID,Full Name,Email,Last Order Date,Lifetime Spend,Orders,Marketing Consent\n"
        "C1,Anna Verdi,anna@example.com,2026-04-02,4820.00,9,Yes\n"
        "C2,Sara Neri,sara@example.com,2026-01-11,1220.50,3,No\n"
    )
    _, fields, _ = _map("customers", text)
    assert fields["customer_id"] == "Customer ID"
    assert fields["email"] == "Email"
    assert fields["marketing_consent"] == "Marketing Consent"
    assert fields["total_spend"] == "Lifetime Spend"


def test_values_override_a_misleading_header():
    """A column named 'Date' holding emails must not be mapped as a date."""
    text = (
        "Customer ID,Date\n"
        "C1,anna@example.com\n"
        "C2,sara@example.com\n"
        "C3,luca@example.com\n"
    )
    _, fields, mappings = _map("customers", text)
    assert fields.get("date") is None
    date_mapping = next(m for m in mappings if m.header == "Date")
    assert date_mapping.field != "date"


def test_tab_and_utf16_are_handled():
    raw = "sku\tproduct name\tprice\tstock\nA1\tWool Coat\t890\t3\n".encode("utf-16")
    parsed = ingestion.parse_csv(raw)
    assert parsed.delimiter == "\t"
    assert parsed.encoding == "utf-16"
    assert parsed.rows[0]["price"] == "890"


def test_preamble_rows_are_skipped():
    text = (
        "Export generated 2026-08-17\n"
        "Boutique Milano\n"
        "sku,product name,price,stock\n"
        "A1,Wool Coat,890,3\n"
        "A2,Silk Blouse,320,5\n"
    )
    parsed = ingestion.parse_csv(text)
    assert parsed.skipped_preamble == 2
    assert parsed.headers[:2] == ["sku", "product name"]
    assert len(parsed.rows) == 2


def test_headerless_file_does_not_crash():
    parsed = ingestion.parse_csv("C1,120.5,2026-01-01\nC2,80,2026-02-01\n")
    assert parsed.had_header is False
    assert parsed.headers[0] == "Column 1"
    assert len(parsed.rows) == 2


def test_empty_and_garbage_files_degrade_gracefully():
    assert ingestion.parse_csv(b"").rows == []
    assert ingestion.parse_csv("   \n  \n").rows == []
    # Binary noise must not raise.
    ingestion.parse_csv(b"\x00\x01\x02\x03garbage")


def test_ragged_rows_are_padded():
    text = "a,b,c\n1,2,3\n4,5\n6,7,8,9\n"
    parsed = ingestion.parse_csv(text)
    assert len(parsed.rows) == 3
    assert all(len(r) == len(parsed.headers) for r in parsed.rows)


def test_number_parsing_conventions():
    assert parse_number("1.234,56") == 1234.56
    assert parse_number("1,234.56") == 1234.56
    assert parse_number("€ 1 234,56") == 1234.56
    assert parse_number("(250)") == -250
    assert parse_number("") is None
    assert parse_number("abc") is None
    assert parse_number("15%") == 0.15


def test_date_parsing_prefers_day_first():
    assert parse_date("05/03/2026").month == 3     # European reading
    assert parse_date("13/03/2026").day == 13      # unambiguous
    assert parse_date("2026-03-05").day == 5
    assert parse_date("not a date") is None


def test_transaction_line_total_is_derived_when_missing():
    text = (
        "order,customer,date,qty,unit price,discount\n"
        "O1,C1,2026-02-01,2,100.00,0.10\n"
    )
    parsed, fields, _ = _map("transactions", text)
    rows = cleaning.build_transactions(parsed.rows, fields)
    assert rows[0]["line_total"] == 180.0   # 2 x 100 less 10%


def test_missing_values_stay_none_not_zero():
    text = "Customer ID,Full Name,Lifetime Spend\nC1,Anna,\nC2,Sara,500\n"
    parsed, fields, _ = _map("customers", text)
    rows = cleaning.build_customers(parsed.rows, fields)
    assert rows[0]["total_spend"] is None      # never fabricated as 0
    assert rows[1]["total_spend"] == 500
