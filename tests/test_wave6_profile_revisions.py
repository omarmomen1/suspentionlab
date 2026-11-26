"""Wave 6 §2: versioned setup revisions with diff and rollback."""
import pytest

from suspensionlab.backend.database.models.profile import compute_params_diff


def test_compute_params_diff_changed_added_removed():
    old = {"k_s": 25000, "c": 2000, "aero": {"front": 10, "rear": 20}, "legacy": 1}
    new = {"k_s": 30000, "c": 2000, "aero": {"front": 12, "rear": 20}, "extra": True}
    d = compute_params_diff(old, new)
    assert d["changed"]["k_s"] == {"old": 25000, "new": 30000}
    assert d["changed"]["aero.front"] == {"old": 10, "new": 12}
    assert "c" not in d["changed"]
    assert d["added"] == ["extra"]
    assert d["removed"] == ["legacy"]


@pytest.fixture
async def seeded_user(db_session):
    """Seed the users row the conftest mock_user authenticates as
    (vehicle_profiles.user_id has a FK to users.id)."""
    import uuid as _uuid
    from suspensionlab.backend.database.models.user import User
    u = User(
        id=_uuid.UUID("00000000-0000-0000-0000-000000000000"),
        email="test@suspensionlab.pro",
        password_hash="x",
        name="Test User",
        plan="pro",
        onboarding_complete=True,
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest.mark.asyncio
async def test_revision_history_diff_and_rollback(authenticated_client, seeded_user):
    create = await authenticated_client.post("/api/v1/profiles", json={
        "name": "wave6-rev-test", "vehicle_type": "QUARTER_CAR",
        "params": {"m_s": 300.0, "k_s": 25000.0, "c": 2000.0},
    })
    assert create.status_code in (200, 201), create.text[:300]
    pid = create.json()["id"]

    # Update params -> new revision with diff
    upd = await authenticated_client.put(f"/api/v1/profiles/{pid}", json={
        "params": {"m_s": 300.0, "k_s": 30000.0, "c": 2000.0},
    })
    assert upd.status_code == 200, upd.text[:300]

    revs = await authenticated_client.get(f"/api/v1/profiles/{pid}/revisions")
    assert revs.status_code == 200, revs.text[:300]
    data = revs.json()["revisions"]
    assert len(data) == 2
    newest, oldest = data[0], data[1]
    assert oldest["revision_number"] == 1 and oldest["parent_revision_id"] is None
    assert newest["revision_number"] == 2
    assert newest["parent_revision_id"] == oldest["id"]
    assert newest["param_diff"]["changed"]["k_s"] == {"old": 25000.0, "new": 30000.0}
    assert newest["author_name"] or newest["author_user_id"]
    assert newest["created_at"]

    # Diff endpoint between the two revisions
    diff = await authenticated_client.get(
        f"/api/v1/profiles/{pid}/diff?from_revision=1&to_revision=2"
    )
    assert diff.status_code == 200
    assert diff.json()["diff"]["changed"]["k_s"]["new"] == 30000.0

    # Rollback to revision 1, recorded as revision 3
    rb = await authenticated_client.post(f"/api/v1/profiles/{pid}/rollback/1")
    assert rb.status_code == 200, rb.text[:300]
    assert rb.json()["new_revision"] == 3
    assert rb.json()["params"]["k_s"] == 25000.0
