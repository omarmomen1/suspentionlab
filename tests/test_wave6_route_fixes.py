"""Wave 6 review fixes: route-level provenance on POST /api/v1/kinematics/solve."""
import copy
import re

import pytest

from suspensionlab.physics.kinematics import DEFAULT_HARDPOINTS
from suspensionlab.physics.provenance import get_build_stamp


def _payload(**static):
    hp = copy.deepcopy(DEFAULT_HARDPOINTS)
    hp.update(static)
    return {"hardpoints": hp, "z_min_mm": -20.0, "z_max_mm": 20.0, "n_steps": 5}


@pytest.mark.asyncio
async def test_kinematics_solve_returns_real_provenance(authenticated_client):
    r = await authenticated_client.post("/api/v1/kinematics/solve", json=_payload())
    assert r.status_code == 200, r.text
    d = r.json()
    assert re.fullmatch(r"[0-9a-f]{64}", d["input_sha256"]), d["input_sha256"]
    assert d["run_id"].startswith("swp-") and len(d["run_id"]) > 4
    short = (get_build_stamp()["git_commit"] or "nogit")[:12]
    assert d["solver_version"].endswith(f"+{short}"), d["solver_version"]

    # Same inputs -> same hash; run_id differs per run.
    r2 = await authenticated_client.post("/api/v1/kinematics/solve", json=_payload())
    assert r2.json()["input_sha256"] == d["input_sha256"]
    assert r2.json()["run_id"] != d["run_id"]

    # Changing static camber (a hardpoint-set field) changes the hash.
    r3 = await authenticated_client.post(
        "/api/v1/kinematics/solve", json=_payload(static_camber_deg=-1.2))
    assert r3.status_code == 200, r3.text
    assert r3.json()["input_sha256"] != d["input_sha256"]
