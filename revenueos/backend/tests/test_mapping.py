"""Column mapping must handle real-world header chaos in several languages."""

from __future__ import annotations

import pandas as pd
import pytest

from app.data.cleaning import apply_mapping
from app.data.mapping import detect_entity, lexical_score, map_columns, normalise
from app.data.schema import ENTITIES


def field_of(result, column: str) -> str | None:
    for mapping in result.mappings:
        if mapping.column == column:
            return mapping.field
    return None


class TestNormalisation:
    @pytest.mark.parametrize(
        "raw,expected",
        [("Nome Cliente", "nome cliente"), ("CUSTOMER_ID", "customer id"),
         ("Città", "citta"), ("Ultimo  Acquisto", "ultimo acquisto"),
         ("e-mail", "e mail")],
    )
    def test_normalises_case_accents_and_punctuation(self, raw, expected):
        assert normalise(raw) == expected


class TestItalianHeaders:
    """The primary market exports in Italian."""

    def test_maps_a_full_italian_customer_export(self):
        frame = pd.DataFrame({
            "Codice Cliente": ["C1", "C2", "C3"],
            "Nome": ["Giulia", "Marco", "Sofia"],
            "Cognome": ["Rossi", "Bianchi", "Conti"],
            "Email": ["g@x.it", "m@x.it", "s@x.it"],
            "Città": ["Milano", "Roma", "Firenze"],
            "Totale Speso": ["1.240,50", "890,00", "3.100,00"],
            "Numero Acquisti": ["4", "2", "9"],
            "Ultimo Acquisto": ["12/03/2026", "04/01/2026", "28/02/2026"],
        })
        result = map_columns(frame, "customers")

        assert field_of(result, "Codice Cliente") == "customer_id"
        assert field_of(result, "Nome") == "first_name"
        assert field_of(result, "Cognome") == "last_name"
        assert field_of(result, "Email") == "email"
        assert field_of(result, "Città") == "city"
        assert field_of(result, "Totale Speso") == "total_spend"
        assert field_of(result, "Numero Acquisti") == "order_count"
        assert field_of(result, "Ultimo Acquisto") == "last_purchase_date"
        assert not result.missing_required

    def test_maps_an_italian_inventory_export(self):
        frame = pd.DataFrame({
            "Codice Articolo": ["P1", "P2"],
            "Descrizione": ["Cappotto in lana", "Maglia cashmere"],
            "Categoria": ["Cappotti", "Maglieria"],
            "Marca": ["Max Mara", "Loro Piana"],
            "Prezzo": ["890,00", "420,00"],
            "Giacenza": ["3", "7"],
            "Taglia": ["M", "S"],
            "Colore": ["Nero", "Cammello"],
        })
        result = map_columns(frame, "inventory")
        assert field_of(result, "Codice Articolo") == "product_id"
        assert field_of(result, "Categoria") == "category"
        assert field_of(result, "Marca") == "brand"
        assert field_of(result, "Prezzo") == "price"
        assert field_of(result, "Giacenza") == "stock"
        assert field_of(result, "Taglia") == "size"
        assert field_of(result, "Colore") == "color"


class TestAlternativeNamings:
    @pytest.mark.parametrize(
        "header,expected",
        [
            ("cliente", "customer_id"),
            ("cust_id", "customer_id"),
            ("id_cliente", "customer_id"),
            ("customer", "customer_id"),
            ("Client ID", "customer_id"),
        ],
    )
    def test_customer_id_synonyms(self, header, expected):
        frame = pd.DataFrame({header: [f"C{i}" for i in range(20)]})
        assert field_of(map_columns(frame, "customers"), header) == expected

    def test_english_french_and_german_headers(self):
        frame = pd.DataFrame({
            "Kundennummer": [f"K{i}" for i in range(15)],
            "Nom": ["Dupont"] * 15,
            "Ville": ["Paris"] * 15,
            "Gesamtumsatz": ["1200"] * 15,
        })
        result = map_columns(frame, "customers")
        assert field_of(result, "Kundennummer") == "customer_id"
        assert field_of(result, "Ville") == "city"
        assert field_of(result, "Gesamtumsatz") == "total_spend"


class TestValueEvidence:
    def test_cell_contents_override_a_misleading_header(self):
        """A column called "Codice" holding emails must not become an ID."""
        frame = pd.DataFrame({
            "Codice": [f"user{i}@example.com" for i in range(30)],
            "Cliente": [f"C{i}" for i in range(30)],
        })
        result = map_columns(frame, "customers")
        assert field_of(result, "Codice") == "email"

    def test_low_confidence_columns_are_flagged_not_silently_guessed(self):
        frame = pd.DataFrame({
            "customer_id": [f"C{i}" for i in range(20)],
            "xyzzy": ["foo"] * 20,
        })
        result = map_columns(frame, "customers")
        mapping = next(m for m in result.mappings if m.column == "xyzzy")
        assert mapping.status in {"review", "unmapped"}

    def test_every_mapping_carries_a_human_readable_rationale(self):
        frame = pd.DataFrame({
            "Nome Cliente": ["Rossi"] * 10,
            "Totale": ["100,00"] * 10,
        })
        for mapping in map_columns(frame, "customers").mappings:
            assert mapping.rationale


class TestEntityDetection:
    def test_detects_each_entity_from_headers_alone(self, raw_demo):
        for entity, frame in raw_demo.items():
            detected, confidence, _ = detect_entity(frame)
            assert detected == entity, f"{entity} was detected as {detected}"
            assert confidence > 0.5

    def test_detects_a_minimal_transaction_file(self):
        frame = pd.DataFrame({
            "Data": ["12/03/2026"] * 10,
            "Cliente": [f"C{i}" for i in range(10)],
            "Importo": ["120,00"] * 10,
        })
        detected, _, _ = detect_entity(frame)
        assert detected == "transactions"


class TestPartialData:
    """The product must degrade, never break, when fields are absent."""

    def test_customers_with_only_id_and_name(self):
        frame = pd.DataFrame({"id": [f"C{i}" for i in range(10)],
                              "name": [f"Person {i}" for i in range(10)]})
        result = map_columns(frame, "customers")
        clean, report = apply_mapping(frame, "customers", result.as_field_map())
        assert len(clean) == 10
        assert clean["display_name"].notna().all()
        # absent metrics stay absent rather than becoming zero
        assert clean["total_spend"].isna().all()

    def test_missing_customer_id_generates_stable_keys(self):
        frame = pd.DataFrame({
            "name": ["Rossi", "Bianchi"],
            "email": ["a@x.it", "b@x.it"],
        })
        result = map_columns(frame, "customers")
        clean, report = apply_mapping(frame, "customers", result.as_field_map())
        assert clean["customer_id"].notna().all()
        assert clean["customer_id"].nunique() == 2
        assert any("synthetic" in note.lower() for note in report.notes)

    def test_duplicate_customers_are_collapsed_and_reported(self):
        frame = pd.DataFrame({
            "customer_id": ["C1", "C1", "C2"],
            "name": ["Rossi", "Rossi", "Bianchi"],
        })
        result = map_columns(frame, "customers")
        clean, report = apply_mapping(frame, "customers", result.as_field_map())
        assert len(clean) == 2
        assert report.dropped_duplicates == 1


class TestCleaning:
    def test_line_totals_are_reconstructed_from_price_and_quantity(self):
        frame = pd.DataFrame({
            "customer_id": ["C1", "C2"],
            "date": ["01/03/2026", "02/03/2026"],
            "unit_price": ["100,00", "200,00"],
            "quantity": ["2", "1"],
            "discount": ["10", "0"],
        })
        result = map_columns(frame, "transactions")
        clean, report = apply_mapping(frame, "transactions", result.as_field_map())
        assert clean["net_amount"].iloc[0] == pytest.approx(180.0)
        assert clean["net_amount"].iloc[1] == pytest.approx(200.0)

    def test_margin_is_derived_from_price_and_cost(self):
        frame = pd.DataFrame({
            "product_id": ["P1"],
            "name": ["Coat"],
            "price": ["100,00"],
            "cost": ["40,00"],
            "stock": ["3"],
        })
        result = map_columns(frame, "inventory")
        clean, _ = apply_mapping(frame, "inventory", result.as_field_map())
        assert clean["margin"].iloc[0] == pytest.approx(60.0)

    def test_missing_price_stays_nan_and_never_becomes_zero(self):
        frame = pd.DataFrame({
            "product_id": ["P1", "P2"],
            "name": ["A", "B"],
            "price": ["100,00", ""],
            "stock": ["3", "1"],
        })
        result = map_columns(frame, "inventory")
        clean, _ = apply_mapping(frame, "inventory", result.as_field_map())
        assert pd.isna(clean["price"].iloc[1])
        assert clean["price"].iloc[1] != 0
