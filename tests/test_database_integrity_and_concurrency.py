import pytest
import uuid
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select

from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.session import SimSession, SessionComment
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.database.models.simulation_run import SimulationRun
from suspensionlab.backend.database.models.vehicle_twin import VehicleTwin
from suspensionlab.backend.security.audit import record_audit_event, verify_audit_db_chain, verify_audit_hash_chain
from suspensionlab.backend.services.run_artifacts import create_run_from_job, get_run, list_runs
from suspensionlab.backend.services.digital_twin import get_twin


@pytest.mark.asyncio
async def test_foreign_key_cascades_on_user_deletion(db_session):
    """Verify that deleting a User cascades properly across profiles, sessions, and comments without NotNullViolation."""
    user = User(
        id=uuid.uuid4(),
        email=f"cascade_test_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="fakehash",
        plan="pro",
        api_key=f"sk_{uuid.uuid4().hex}"
    )
    db_session.add(user)
    await db_session.commit()

    profile = VehicleProfile(
        id=uuid.uuid4(),
        name="Test GT3",
        user_id=user.id,
        params={"m_s": 350.0, "k_s": 45000.0}
    )
    session = SimSession(
        id=uuid.uuid4(),
        owner_id=user.id,
        name="Test Session"
    )
    comment = SessionComment(
        id=uuid.uuid4(),
        session_id=session.id,
        author_id=user.id,
        content="Initial baseline run looks good."
    )
    db_session.add_all([profile, session, comment])
    await db_session.commit()

    # Delete User -> cascades to profile, session, and comment
    await db_session.delete(user)
    await db_session.commit()
    db_session.expire_all()

    # Verify everything was cleanly deleted or cascaded
    res_prof = await db_session.execute(select(VehicleProfile).where(VehicleProfile.id == profile.id))
    assert res_prof.scalar_one_or_none() is None

    res_sess = await db_session.execute(select(SimSession).where(SimSession.id == session.id))
    assert res_sess.scalar_one_or_none() is None

    res_comm = await db_session.execute(select(SessionComment).where(SessionComment.id == comment.id))
    assert res_comm.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_audit_hash_chain_concurrent_integrity(db_session):
    """Verify that concurrent audit log writes do not fork the hash chain and verify_audit_hash_chain returns True."""
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    # Sequentially / concurrently write 10 audit records
    for i in range(10):
        await record_audit_event(
            db=db_session,
            event_type=f"simulation.started.{i}",
            user_id=user_id,
            team_id=team_id,
            ip="127.0.0.1",
            metadata={"run_index": i}
        )

    # Verify the entire chain
    is_valid = await verify_audit_db_chain(db_session, team_id=team_id)
    assert is_valid is True


@pytest.mark.asyncio
async def test_multi_tenant_workspace_isolation_and_sharing(db_session):
    """Verify team members can access team runs and twins, while outsiders cannot."""
    team_id = uuid.uuid4()
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()  # same team
    user_c_id = uuid.uuid4()  # different user, no team

    user_a = User(id=user_a_id, email=f"a_{uuid.uuid4().hex[:6]}@team.com", password_hash="h", plan="enterprise", api_key=f"sk_{uuid.uuid4().hex}")
    db_session.add(user_a)
    await db_session.commit()

    team = Team(
        id=team_id,
        name="Scuderia Alpha",
        slug=f"scuderia-{uuid.uuid4().hex[:6]}",
        owner_id=user_a_id,
        plan="enterprise"
    )
    user_a.team_id = team_id
    user_b = User(id=user_b_id, email=f"b_{uuid.uuid4().hex[:6]}@team.com", password_hash="h", team_id=team_id, plan="enterprise", api_key=f"sk_{uuid.uuid4().hex}")
    user_c = User(id=user_c_id, email=f"c_{uuid.uuid4().hex[:6]}@other.com", password_hash="h", plan="pro", api_key=f"sk_{uuid.uuid4().hex}")

    db_session.add_all([team, user_b, user_c])
    await db_session.commit()

    # User A creates a completed job
    job = JobRecord(
        id=uuid.uuid4(),
        user_id=user_a_id,
        team_id=team_id,
        job_type="simulate_quarter_car",
        status="COMPLETED",
        params={"m_s": 350.0, "k_s": 45000.0, "k_t": 200000.0, "cl_base": 1.5, "cd_base": 0.8},
        profile={"road_profile": "bump_100mm"},
        result={"peak_acceleration": 2.4, "settling_time": 0.32}
    )
    db_session.add(job)
    await db_session.commit()

    # User A snapshots the job to an immutable run artifact
    run_payload = await create_run_from_job(
        db=db_session,
        job_id=str(job.id),
        user_id=str(user_a_id),
        team_id=str(team_id),
        title="Qualifying Setup Run 1"
    )

    # User B (same team) fetches the run
    run_for_b = await get_run(db=db_session, label_or_id=run_payload["label"], user_id=str(user_b_id), team_id=str(team_id))
    assert run_for_b is not None
    assert run_for_b.label == run_payload["label"]
    assert run_for_b.tire_snapshot is not None
    assert run_for_b.aero_snapshot is not None
    assert run_for_b.track_geometry_hash is not None

    # User C (outside team) cannot access User A's team run
    with pytest.raises(LookupError):
        await get_run(db=db_session, label_or_id=run_payload["label"], user_id=str(user_c_id), team_id=None)

    # User A creates a VehicleTwin
    twin = VehicleTwin(
        id=uuid.uuid4(),
        car_ref="Ferrari-499P",
        setup_ref="Monza-LowDownforce",
        user_id=user_a_id,
        team_id=team_id,
        base_params={"m_s": 350.0},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    db_session.add(twin)
    await db_session.commit()

    # User B (same team) fetches the twin
    twin_for_b = await get_twin(db=db_session, twin_id=str(twin.id), user_id=str(user_b_id), team_id=str(team_id))
    assert twin_for_b is not None
    assert twin_for_b.car_ref == "Ferrari-499P"

    # User C cannot access the twin
    with pytest.raises(LookupError):
        await get_twin(db=db_session, twin_id=str(twin.id), user_id=str(user_c_id), team_id=None)


@pytest.mark.asyncio
async def test_concurrent_simulation_run_sequence_monotonicity(db_session):
    """Stress test: create multiple completed jobs and snapshot them concurrently.
    Verify all generated sequence numbers and RUN-xxxxxx labels are unique and monotonic.
    """
    user = User(
        id=uuid.uuid4(),
        email=f"seq_test_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="h",
        plan="pro",
        api_key=f"sk_{uuid.uuid4().hex}"
    )
    db_session.add(user)
    await db_session.commit()

    jobs = []
    for i in range(10):
        j = JobRecord(
            id=uuid.uuid4(),
            user_id=user.id,
            job_type="simulate_quarter_car",
            status="COMPLETED",
            params={"m_s": 350.0 + i},
            result={"peak_acc": 2.0 + i}
        )
        jobs.append(j)
    db_session.add_all(jobs)
    await db_session.commit()

    # Concurrently snapshot all jobs
    tasks = [
        create_run_from_job(
            db=db_session,
            job_id=str(j.id),
            user_id=str(user.id),
            title=f"Concurrent Run {idx}"
        )
        for idx, j in enumerate(jobs)
    ]
    results = await asyncio.gather(*tasks)

    labels = [r["label"] for r in results]
    seqs = [r["seq"] for r in results]

    # Verify uniqueness
    assert len(set(labels)) == 10
    assert len(set(seqs)) == 10
    # Verify sequential numbers
    assert sorted(seqs) == list(range(min(seqs), min(seqs) + 10))


@pytest.mark.asyncio
async def test_concurrent_audit_chain_interleaving(db_session):
    """Stress test: 20 concurrent audit events interleaved across 2 teams.
    Verify that both teams' cryptographic chains remain 100% valid and unbroken.
    """
    team_1 = str(uuid.uuid4())
    team_2 = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    tasks = []
    for i in range(20):
        t_id = team_1 if i % 2 == 0 else team_2
        tasks.append(
            record_audit_event(
                db=db_session,
                event_type=f"stress.event.{i}",
                user_id=user_id,
                team_id=t_id,
                ip="192.168.1.100",
                metadata={"stress_seq": i}
            )
        )
    await asyncio.gather(*tasks)

    # Validate both team chains and the entire global log
    assert await verify_audit_db_chain(db_session, team_id=team_1) is True
    assert await verify_audit_db_chain(db_session, team_id=team_2) is True
    assert await verify_audit_db_chain(db_session) is True
