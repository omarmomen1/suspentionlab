"""Phase 3H.3 Product Terminology Governance Tests.

Verifies:
1. Strict 3-tier product naming taxonomy:
   - Path A: ACTUATOR_REPLAY
   - Current Path B: GEAR_CONDITIONED_POWERTRAIN_PREDICTION
   - Future Path: AUTONOMOUS_POWERTRAIN_PREDICTION
2. Strict prohibition against mislabeling fixed-gear boundary conditions.
"""

import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
JSON_FILE = DATA_DIR / "phase3h3_product_terminology.json"


@pytest.fixture(scope="module")
def term_data():
    assert JSON_FILE.exists(), f"Missing deliverable: {JSON_FILE}"
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def test_product_terminology_hierarchy(term_data):
    """Verify exact 3-tier product terminology taxonomy."""
    tax = term_data["taxonomy"]
    assert tax["Path_A"]["certified_name"] == "ACTUATOR_REPLAY"
    assert tax["Current_Path_B"]["certified_name"] == "GEAR_CONDITIONED_POWERTRAIN_PREDICTION"
    assert tax["Future_Path"]["certified_name"] == "AUTONOMOUS_POWERTRAIN_PREDICTION"


def test_prohibitions_enforced(term_data):
    """Verify strict prohibitions are listed."""
    prohibs = term_data["strict_prohibitions"]
    assert any("endogenous transmission prediction" in p.lower() for p in prohibs)
