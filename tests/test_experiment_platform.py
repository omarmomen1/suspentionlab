"""
tests/test_experiment_platform.py
=================================
Automated backend verification for the Engineering Experiment + Compare + Optimization platform.
Tests:
- Experiment creation and execution with real physics
- Mandatory tradeoff exposure ("What Got Worse" alongside "What Improved")
- Physical engineering causality chain generation
- Deterministic reproducibility from stored experiment definition
- Deep comparison ("Why is B better than A?")
- Multi-objective Pareto frontier batch optimization
- Input validation & physical boundaries
- Multi-tenant isolation & access control
"""
import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_experiment_creation_and_execution(authenticated_client: AsyncClient):
    payload = {
        "question": "What happens if I increase front roll stiffness by 10%?",
        "hypothesis": "Increasing front spring rate improves platform stability at the cost of curb harshness.",
        "parent_setup": {
            "m_s": 320.0,
            "m_u": 45.0,
            "k_s": 35000.0,
            "c": 2200.0,
            "k_t": 220000.0,
            "MR": 0.85,
        },
        "parameter_changes": [
            {"parameter": "k_s", "change_pct": 10.0}
        ],
        "author": "Marcus Vance (Senior Dynamics Engineer)",
    }

    resp = await authenticated_client.post("/api/v1/experiments/run", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()

    # Core metadata
    assert "id" in data
    assert data["question"] == payload["question"]
    assert data["author"] == payload["author"]
    assert data["validation_state"] == "UNVALIDATED"
    assert data["status"] in ("COMPLETED", "VIOLATED")
    assert "result_hash" in data
    assert len(data["result_hash"]) == 64

    # Parameter diffs
    assert len(data["parameter_changes"]) >= 1
    ks_change = next(c for c in data["parameter_changes"] if c["parameter"] == "k_s")
    assert ks_change["baseline"] == 35000.0
    assert ks_change["candidate"] == 38500.0
    assert ks_change["delta_pct"] == 10.0
    assert ks_change["unit"] == "N/m"

    # Real simulation metrics
    assert "baseline_metrics" in data
    assert "candidate_metrics" in data
    assert data["candidate_metrics"]["ride_freq_hz"] > data["baseline_metrics"]["ride_freq_hz"]

    # Improvements & Mandatory Regressions (Tradeoffs)
    assert isinstance(data["improvements"], list)
    assert isinstance(data["regressions"], list)
    # Tradeoffs must not be empty when spring rate is stiffened
    assert len(data["regressions"]) >= 1
    for reg in data["regressions"]:
        assert "metric" in reg
        assert "delta_pct" in reg
        assert "reason" in reg

    # Engineering causality chain
    assert isinstance(data["causal_chain"], list)
    assert len(data["causal_chain"]) >= 2
    chain_str = " ".join(data["causal_chain"])
    assert "spring stiffness" in chain_str or "frequency" in chain_str

    # Constraints
    assert "constraints_passed" in data
    assert isinstance(data["constraint_details"], list)
    assert len(data["constraint_details"]) >= 2


@pytest.mark.asyncio
async def test_experiment_reproducibility_and_retry(authenticated_client: AsyncClient):
    # 1. Run initial experiment
    payload = {
        "question": "What happens if damping is decreased by 15%?",
        "parent_setup": {
            "m_s": 300.0,
            "m_u": 40.0,
            "k_s": 32000.0,
            "c": 2400.0,
        },
        "parameter_changes": [
            {"parameter": "c", "change_pct": -15.0}
        ],
    }
    resp1 = await authenticated_client.post("/api/v1/experiments/run", json=payload)
    assert resp1.status_code == 201
    exp_data = resp1.json()
    exp_id = exp_data["id"]
    original_hash = exp_data["result_hash"]

    # 2. Get by ID
    get_resp = await authenticated_client.get(f"/api/v1/experiments/{exp_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == exp_id

    # 3. Retry / verify reproducibility
    retry_resp = await authenticated_client.post(f"/api/v1/experiments/{exp_id}/retry")
    assert retry_resp.status_code == 200
    retry_data = retry_resp.json()
    assert retry_data["reproduced"] is True
    assert retry_data["hash_matched"] is True
    assert retry_data["original_hash"] == original_hash
    assert retry_data["verification_status"] == "REPRODUCED_VERIFIED"


@pytest.mark.asyncio
async def test_deep_setup_comparison_why_b_is_better(authenticated_client: AsyncClient):
    payload = {
        "setup_a": {
            "m_s": 320.0,
            "k_s": 35000.0,
            "c": 2200.0,
        },
        "setup_b": {
            "m_s": 320.0,
            "k_s": 42000.0,
            "c": 2600.0,
        },
    }

    resp = await authenticated_client.post("/api/v1/experiments/compare", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    # Must explicitly address all comparison dimensions
    assert "what_changed" in data
    assert "what_improved" in data
    assert "what_got_worse" in data  # MANDATORY
    assert "engineering_causality" in data
    assert "evidence" in data
    assert "verdict" in data
    assert "confidence" in data

    # Parameter diffs in engineering units
    assert len(data["what_changed"]) >= 2
    for change in data["what_changed"]:
        assert "parameter" in change
        assert "unit" in change
        assert "delta_pct" in change

    # Regressions must expose tradeoffs
    assert len(data["what_got_worse"]) >= 1


@pytest.mark.asyncio
async def test_multi_objective_pareto_batch_optimization(authenticated_client: AsyncClient):
    payload = {
        "base_params": {
            "m_s": 320.0,
            "m_u": 45.0,
            "k_s": 35000.0,
            "c": 2200.0,
        },
        "param_ranges": {
            "k_s": [25000.0, 45000.0, 4],
            "c": [1600.0, 2800.0, 4],
        },
    }

    resp = await authenticated_client.post("/api/v1/experiments/batch-optimize", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_evaluated"] == 16  # 4 x 4
    assert data["feasible_count"] > 0
    assert data["pareto_optimal_count"] > 0
    assert len(data["candidates"]) == data["feasible_count"]
    assert len(data["pareto_frontier"]) == data["pareto_optimal_count"]

    # Best compromise point
    assert data["best_compromise"] is not None
    assert "best_compromise_explanation" in data
    assert "Utopia point" in data["best_compromise_explanation"]


@pytest.mark.asyncio
async def test_experiment_physical_domain_errors(authenticated_client: AsyncClient):
    # Invalid negative mass
    bad_payload = {
        "question": "What happens with negative sprung mass?",
        "parent_setup": {
            "m_s": -300.0,
            "k_s": 35000.0,
            "c": 2200.0,
        },
    }
    resp = await authenticated_client.post("/api/v1/experiments/run", json=bad_payload)
    assert resp.status_code == 400
    assert "must be a strictly positive value" in resp.json()["detail"] or "mass" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_experiment_tenant_isolation(client: AsyncClient, mock_user):
    from suspensionlab.backend.security.auth import verify_api_key, UserContext
    from suspensionlab.backend.api.main import app

    # User 1 creates an experiment
    user1 = UserContext(
        user_id="11111111-1111-1111-1111-111111111111",
        plan="pro",
        email="user1@suspensionlab.pro",
        name="User One",
        onboarding_complete=True,
        team_id=None,
    )
    app.dependency_overrides[verify_api_key] = lambda: user1

    payload = {
        "question": "User 1 private hypothesis",
        "parent_setup": {"k_s": 35000.0, "c": 2200.0},
    }
    resp1 = await client.post("/api/v1/experiments/run", json=payload)
    assert resp1.status_code == 201
    exp_id = resp1.json()["id"]

    # User 2 tries to access User 1's experiment
    user2 = UserContext(
        user_id="22222222-2222-2222-2222-222222222222",
        plan="pro",
        email="user2@suspensionlab.pro",
        name="User Two",
        onboarding_complete=True,
        team_id=None,
    )
    app.dependency_overrides[verify_api_key] = lambda: user2

    resp2 = await client.get(f"/api/v1/experiments/{exp_id}")
    assert resp2.status_code == 403
    assert "Access denied" in resp2.json()["detail"]

    app.dependency_overrides.pop(verify_api_key, None)
