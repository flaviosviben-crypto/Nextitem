"""Shared fixtures. The demo dataset doubles as the integration corpus."""

from __future__ import annotations

import os
import tempfile

# Point the store at a throwaway directory *before* any app module is imported,
# so a test run can never touch (or delete) a real workspace's database.
os.environ["REVENUEOS_DATA_DIR"] = tempfile.mkdtemp(prefix="revenueos-test-")

import pandas as pd
import pytest

from app.analytics.customer_scoring import build_customer_metrics
from app.analytics.inventory import build_inventory_metrics
from app.analytics.matching import build_context
from app.analytics.rfm import compute_rfm
from app.data.cleaning import apply_mapping
from app.data.mapping import map_columns
from app.demo.generator import generate_demo_dataset


@pytest.fixture(scope="session")
def raw_demo() -> dict[str, pd.DataFrame]:
    return generate_demo_dataset(n_customers=60, n_products=120)


@pytest.fixture(scope="session")
def tables(raw_demo) -> dict[str, pd.DataFrame]:
    """The demo data pushed through the real mapping + cleaning pipeline."""
    out = {}
    for entity, frame in raw_demo.items():
        mapping = map_columns(frame, entity)
        out[entity], _ = apply_mapping(frame, entity, mapping.as_field_map())
    return out


@pytest.fixture(scope="session")
def metrics(tables) -> pd.DataFrame:
    return compute_rfm(build_customer_metrics(tables["customers"], tables["transactions"]))


@pytest.fixture(scope="session")
def products(tables) -> pd.DataFrame:
    return build_inventory_metrics(tables["inventory"], tables["transactions"])


@pytest.fixture(scope="session")
def ctx(products, metrics):
    return build_context(products, metrics)
