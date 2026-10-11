"""
tests/test_audit_governance_tamper_evident.py
=============================================
Authoritative Test Suite for Tamper-Evident Engineering Governance.

Strict adherence to NON-NEGOTIABLE ENGINEERING RULES:
  - No mocks for real cryptographic operations or verification
  - Exact formula: H_n = SHA256(H_{n-1} || Canonical(Event_n))
  - Detects event modification, deletion, out-of-order sequence, and concurrent forks
  - Tests transactional outbox guaranteed delivery and idempotency
  - Verifies all 11 engineering governance event categories
"""
import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, asc, delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from suspensionlab.backend.database.core import Base
from suspensionlab.backend.database.models.audit import AuditLog, AuditOutbox
from suspensionlab.backend.security.audit import (
    serialize_canonical_event,
    build_canonical_audit_envelope,
    compute_audit_hash,
    record_audit_event,
    verify_audit_hash_chain,
    verify_audit_hash_chain_detailed,
    verify_audit_db_chain,
    verify_audit_db_chain_detailed,
    enqueue_audit_event,
    process_audit_outbox,
    normalize_timestamp,
)


@pytest_asyncio.fixture
async def test_db():
    """Isolated in-memory SQLite database with fresh schema for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# 1. CANONICAL EVENT SERIALIZATION (RFC 8785) & DETERMINISM
# ─────────────────────────────────────────────────────────────────────────────

def test_canonical_event_serialization_deterministic():
    """Verify key ordering, whitespace normalization, and deterministic hashing."""
    obj1 = {"b": 2, "a": 1, "z": [3, 2, 1], "c": {"nested_b": True, "nested_a": "alpha"}}
    obj2 = {"a": 1, "z": [3, 2, 1], "c": {"nested_a": "alpha", "nested_b": True}, "b": 2}

    ser1 = serialize_canonical_event(obj1)
    ser2 = serialize_canonical_event(obj2)

    assert ser1 == ser2, "Canonical serialization must be strictly independent of dictionary key insertion order"
    assert " " not in ser1.replace("alpha", ""), "Canonical serialization must omit superfluous whitespace"

    hash1 = hashlib.sha256(ser1.encode("utf-8")).hexdigest()
    hash2 = hashlib.sha256(ser2.encode("utf-8")).hexdigest()
    assert hash1 == hash2


def test_timestamp_normalization_consistency():
    """Verify UTC normalization across aware, naive, and ISO string formats."""
    aware = datetime(2026, 9, 3, 14, 30, 0, 123456, tzinfo=timezone.utc)
    naive = datetime(2026, 9, 3, 14, 30, 0, 123456)
    iso_str = "2026-09-03T14:30:00.123456Z"

    norm_aware = normalize_timestamp(aware)
    norm_naive = normalize_timestamp(naive)
    norm_iso = normalize_timestamp(iso_str)

    assert norm_aware == norm_naive == norm_iso == "2026-09-03T14:30:00.123456Z"


# ─────────────────────────────────────────────────────────────────────────────
# 2. HASH CHAIN CRYPTOGRAPHY & MONOTONICITY
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_hash_chain_formula_and_monotonic_sequence(test_db: AsyncSession):
    """Verify H_n = SHA256(H_{n-1} || Canonical(Event_n)) and sequence numbers."""
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    # Insert 5 events sequentially
    events = [
        ("VEHICLE_CREATED", {"name": "Formula Student 2026"}),
        ("SETUP_CHANGED", {"k_s": 42000.0, "c": 3200.0}),
        ("SIMULATION_RUN_CREATED", {"run_id": "RUN-000101"}),
        ("OPTIMIZATION_SUBMITTED", {"objective": "MINIMIZE_RMS_ACCEL"}),
        ("REPORT_APPROVAL_SIGN_OFF", {"decision": "APPROVED", "signer": "Chief Engineer"}),
    ]

    for ev_type, meta in events:
        await record_audit_event(
            db=test_db,
            event_type=ev_type,
            user_id=user_id,
            team_id=team_id,
            ip="10.0.0.1",
            metadata=meta,
        )

    # Read back rows ordered by sequence
    rows = (await test_db.execute(select(AuditLog).order_by(asc(AuditLog.sequence_number)))).scalars().all()
    assert len(rows) == 5

    # Verify monotonic sequence numbers
    for i, row in enumerate(rows, start=1):
        assert row.sequence_number == i

    # Genesis check
    assert rows[0].previous_hash == "GENESIS"

    # Manually recompute each block using SHA256(H_{n-1} || Canonical(Event_n))
    for i in range(len(rows)):
        prev_h = rows[i - 1].hash if i > 0 else "GENESIS"
        assert rows[i].previous_hash == prev_h

        env = build_canonical_audit_envelope(
            event_type=rows[i].event,
            user_id=str(rows[i].user_id) if rows[i].user_id else None,
            team_id=str(rows[i].team_id) if rows[i].team_id else None,
            ip=rows[i].ip,
            artifact_id=rows[i].artifact_id,
            sequence_number=rows[i].sequence_number,
            timestamp=rows[i].timestamp,
            event_data=rows[i].event_data,
        )
        expected_hash = compute_audit_hash(prev_h, env)
        assert rows[i].hash == expected_hash

    # Full automated chain verification
    is_valid, details = await verify_audit_db_chain_detailed(test_db, team_id=team_id)
    assert is_valid is True
    assert details["total_records"] == 5
    assert details["head_hash"] == rows[-1].hash


# ─────────────────────────────────────────────────────────────────────────────
# 3. FAILURE DETECTION: EVENT MODIFICATION (PAYLOAD TAMPER)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_failure_detection_event_payload_tampered(test_db: AsyncSession):
    """
    FAILURE TEST: An adversary mutates an event payload in the database.
    VERIFY: Verification MUST detect the modification and pinpoint the failed sequence.
    """
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    for i in range(5):
        await record_audit_event(
            db=test_db,
            event_type=f"audit.step.{i}",
            user_id=user_id,
            team_id=team_id,
            ip="192.168.1.50",
            metadata={"step": i, "temperature": 85.0 + i},
        )

    rows = (await test_db.execute(select(AuditLog).order_by(asc(AuditLog.sequence_number)))).scalars().all()
    assert len(rows) == 5

    # Prior to tampering: chain is 100% valid
    valid_before, _ = await verify_audit_db_chain_detailed(test_db, team_id=team_id)
    assert valid_before is True

    # TAMPER: Change metadata of record #2 (index 2) directly in DB
    tampered_row = rows[2]
    tampered_row.event_data = {"step": 2, "temperature": 999.9}  # altered value!
    await test_db.commit()

    # VERIFY DETECTION: verification must fail with TAMPER_PAYLOAD_MISMATCH at sequence #3
    is_valid, details = await verify_audit_db_chain_detailed(test_db, team_id=team_id)
    assert is_valid is False
    assert details["error"] == "TAMPER_PAYLOAD_MISMATCH"
    assert details["failed_sequence_number"] == 3
    assert details["recorded_hash"] == tampered_row.hash
    assert details["expected_hash"] != tampered_row.hash


# ─────────────────────────────────────────────────────────────────────────────
# 4. FAILURE DETECTION: HASH FORGERY
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_failure_detection_hash_forgery(test_db: AsyncSession):
    """
    FAILURE TEST: An attacker alters a record's hash to hide changes or forge state.
    VERIFY: Verification detects previous_hash link break on subsequent block.
    """
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    for i in range(4):
        await record_audit_event(
            db=test_db,
            event_type=f"auth.audit.{i}",
            user_id=user_id,
            team_id=team_id,
            ip="127.0.0.1",
            metadata={"cycle": i},
        )

    rows = (await test_db.execute(select(AuditLog).order_by(asc(AuditLog.sequence_number)))).scalars().all()

    # TAMPER: Corrupt hash of row index 1
    rows[1].hash = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    await test_db.commit()

    is_valid, details = await verify_audit_db_chain_detailed(test_db, team_id=team_id)
    assert is_valid is False
    # Will fail either on row 1 recalculation or row 2 previous_hash check
    assert details["error"] in ("TAMPER_PAYLOAD_MISMATCH", "CHAIN_BROKEN_PREVIOUS_HASH_MISMATCH")


# ─────────────────────────────────────────────────────────────────────────────
# 5. FAILURE DETECTION: EVENT DELETION / SEQUENCE GAP
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_failure_detection_event_deletion_detected(test_db: AsyncSession):
    """
    FAILURE TEST: An attacker deletes an intermediate audit log to conceal unauthorized activity.
    VERIFY: Verification detects both the sequence gap and the cryptographic hash mismatch.
    """
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    for i in range(6):
        await record_audit_event(
            db=test_db,
            event_type=f"operation.{i}",
            user_id=user_id,
            team_id=team_id,
            ip="10.1.1.1",
            metadata={"op_id": i},
        )

    # Initial check: valid
    assert (await verify_audit_db_chain(test_db, team_id=team_id)) is True

    # TAMPER: Delete record with sequence_number = 3
    await test_db.execute(delete(AuditLog).where(AuditLog.sequence_number == 3))
    await test_db.commit()

    # VERIFY DETECTION
    is_valid, details = await verify_audit_db_chain_detailed(test_db, team_id=team_id)
    assert is_valid is False
    assert details["error"] == "SEQUENCE_GAP_DETECTED"
    assert details["expected_sequence"] == 3
    assert details["found_sequence"] == 4


# ─────────────────────────────────────────────────────────────────────────────
# 6. CONCURRENCY & FORK PREVENTION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_concurrency_fork_prevention_under_high_load(test_db: AsyncSession):
    """
    CONCURRENCY TEST: 30 parallel coroutines submit audit events simultaneously.
    VERIFY:
      - Strictly monotonic sequence numbers: 1 through 30 with ZERO duplicates
      - ZERO sequence gaps or forks
      - Entire chain validates cryptographically from Genesis to Head
    """
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())
    total_events = 30

    tasks = [
        record_audit_event(
            db=test_db,
            event_type=f"concurrent.sim.{i}",
            user_id=user_id,
            team_id=team_id,
            ip="10.0.0.5",
            artifact_id=f"RUN-{i:04d}",
            metadata={"sim_index": i},
        )
        for i in range(total_events)
    ]

    results = await asyncio.gather(*tasks)
    assert len(results) == total_events

    # Read back all records
    res = await test_db.execute(
        select(AuditLog)
        .where(AuditLog.team_id == uuid.UUID(team_id))
        .order_by(asc(AuditLog.sequence_number))
    )
    rows = res.scalars().all()
    assert len(rows) == total_events

    # Verify strictly monotonic sequences without duplicates
    sequences = [r.sequence_number for r in rows]
    expected_sequences = list(range(1, total_events + 1))
    assert sequences == expected_sequences, f"Expected sequences {expected_sequences}, got {sequences}"

    # Verify no duplicate sequence numbers
    assert len(set(sequences)) == total_events

    # Verify complete cryptographic integrity
    is_valid, details = await verify_audit_db_chain_detailed(test_db, team_id=team_id)
    assert is_valid is True, f"Chain verification failed with details: {details}"
    assert details["total_records"] == total_events


# ─────────────────────────────────────────────────────────────────────────────
# 7. TRANSACTIONAL OUTBOX & GUARANTEED DELIVERY
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_transactional_outbox_guaranteed_delivery_and_idempotency(test_db: AsyncSession):
    """
    OUTBOX TEST: Verify transactional outbox enqueuing, sequential processing,
    and deduplication via idempotency keys.
    """
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())
    idempotency_key_1 = f"idem-{uuid.uuid4()}"

    # 1. Enqueue 3 events into outbox
    ob1 = await enqueue_audit_event(
        db=test_db,
        event_type="JOB_QUEUED",
        user_id=user_id,
        team_id=team_id,
        artifact_id="JOB-001",
        metadata={"priority": "high"},
        idempotency_key=idempotency_key_1,
    )
    assert ob1.status == "PENDING"

    # Idempotent re-enqueue with the same key should return existing entry without creating duplicate
    ob1_duplicate = await enqueue_audit_event(
        db=test_db,
        event_type="JOB_QUEUED",
        user_id=user_id,
        team_id=team_id,
        artifact_id="JOB-001",
        metadata={"priority": "high"},
        idempotency_key=idempotency_key_1,
    )
    assert ob1.id == ob1_duplicate.id

    ob2 = await enqueue_audit_event(
        db=test_db,
        event_type="JOB_STARTED",
        user_id=user_id,
        team_id=team_id,
        artifact_id="JOB-001",
        metadata={"worker_id": "w-1"},
    )
    ob3 = await enqueue_audit_event(
        db=test_db,
        event_type="JOB_COMPLETED",
        user_id=user_id,
        team_id=team_id,
        artifact_id="JOB-001",
        metadata={"duration_ms": 1420},
    )

    # Check outbox has exactly 3 pending records
    pending_res = await test_db.execute(select(AuditOutbox).where(AuditOutbox.status == "PENDING"))
    pending_records = pending_res.scalars().all()
    assert len(pending_records) == 3

    # 2. Process outbox
    metrics = await process_audit_outbox(test_db, max_batch=10)
    assert metrics["processed"] == 3
    assert metrics["failed"] == 0

    # 3. Check outbox records are now PROCESSED
    processed_res = await test_db.execute(select(AuditOutbox).where(AuditOutbox.status == "PROCESSED"))
    processed_records = processed_res.scalars().all()
    assert len(processed_records) == 3

    # 4. Check audit_logs now contains the 3 corresponding rows linked in the hash chain
    audit_rows = (await test_db.execute(select(AuditLog).order_by(asc(AuditLog.sequence_number)))).scalars().all()
    assert len(audit_rows) == 3
    assert [r.event for r in audit_rows] == ["JOB_QUEUED", "JOB_STARTED", "JOB_COMPLETED"]

    # 5. Verify cryptographic validity of processed chain
    is_valid, _ = await verify_audit_db_chain_detailed(test_db, team_id=team_id)
    assert is_valid is True


# ─────────────────────────────────────────────────────────────────────────────
# 8. ALL 11 ENGINEERING GOVERNANCE EVENTS VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_eleven_engineering_governance_events(test_db: AsyncSession):
    """
    VERIFY: Every single one of the 11 required engineering events:
      1. vehicle change
      2. setup change
      3. simulation
      4. optimization
      5. validation
      6. approval
      7. report
      8. export
      9. share
      10. deletion
      11. role change
    is recorded with metadata, sequence number, and verifiable cryptographic integrity.
    """
    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    governance_events = [
        ("VEHICLE_CREATED", "profile-99", {"name": "LMP1 Endurance", "mass": 900.0}),
        ("SETUP_CHANGED", "profile-99", {"stiffness_delta_pct": 5.2}),
        ("SIMULATION_RUN_CREATED", "RUN-000210", {"type": "quarter_car", "rms_accel": 0.45}),
        ("OPTIMIZATION_SUBMITTED", "OPT-5501", {"algorithm": "NSGA-II", "generations": 50}),
        ("VALIDATION_EXECUTED", "VNV-SUITE", {"passed_cases": 12, "failed_cases": 0}),
        ("REPORT_APPROVAL_SIGN_OFF", "DOC-2026-99", {"signoff": "APPROVED", "signature": "HMAC_SIG_OK"}),
        ("REPORT_GENERATED", "ISO-2631-REP", {"comfort_rating": "A"}),
        ("EXPORT_GENERATED", "QuarterCar.fmu", {"format": "fmu", "version": "2.0"}),
        ("REPORT_SHARED", "SHARE-TOKEN-77", {"visibility": "public_authenticated"}),
        ("VEHICLE_DELETED", "profile-99", {"reason": "superseded_by_v2"}),
        ("TEAM_ROLE_CHANGED", user_id, {"old_role": "ENGINEER", "new_role": "ADMIN"}),
    ]

    for event_type, artifact_id, meta in governance_events:
        await record_audit_event(
            db=test_db,
            event_type=event_type,
            user_id=user_id,
            team_id=team_id,
            artifact_id=artifact_id,
            metadata=meta,
        )

    rows = (await test_db.execute(select(AuditLog).order_by(asc(AuditLog.sequence_number)))).scalars().all()
    assert len(rows) == 11

    # Verify all event names in order
    recorded_events = [r.event for r in rows]
    expected_events = [e[0] for e in governance_events]
    assert recorded_events == expected_events

    # Verify all sequence numbers from 1 to 11
    assert [r.sequence_number for r in rows] == list(range(1, 12))

    # Verify complete cryptographic integrity
    is_valid, details = await verify_audit_db_chain_detailed(test_db, team_id=team_id)
    assert is_valid is True
    assert details["total_records"] == 11


# ─────────────────────────────────────────────────────────────────────────────
# 9. AUDIT API ENDPOINTS VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_api_routes_end_to_end(test_db: AsyncSession):
    """
    VERIFY: Full HTTP API route logic:
      - /api/v1/audit/logs (with search, category, artifact filters)
      - /api/v1/audit/verify (cryptographic verification)
      - /api/v1/audit/outbox/status & /api/v1/audit/outbox/flush
      - /api/v1/audit/export (CSV & JSON)
    """
    from unittest.mock import MagicMock
    from suspensionlab.backend.api.routes.audit_routes import (
        get_audit_logs,
        verify_chain,
        get_outbox_status,
        flush_outbox,
        export_audit_logs,
    )
    from suspensionlab.shared.models import PlanTier

    user_id = str(uuid.uuid4())
    team_id = str(uuid.uuid4())

    mock_user = MagicMock()
    mock_user.user_id = user_id
    mock_user.team_id = team_id
    mock_user.plan = PlanTier.ENTERPRISE

    # 1. Populate some events
    await record_audit_event(
        db=test_db,
        event_type="SIMULATION_RUN_CREATED",
        user_id=user_id,
        team_id=team_id,
        artifact_id="RUN-000500",
        metadata={"lap_time": 78.4},
    )
    await record_audit_event(
        db=test_db,
        event_type="EXPORT_GENERATED",
        user_id=user_id,
        team_id=team_id,
        artifact_id="model.fmu",
        metadata={"format": "fmu"},
    )

    # 2. Test get_audit_logs
    logs = await get_audit_logs(skip=0, limit=10, user=mock_user, db=test_db)
    assert len(logs) == 2
    assert logs[0].artifact_id in ("RUN-000500", "model.fmu")

    # Test filtering by artifact
    filtered_logs = await get_audit_logs(skip=0, limit=10, artifact_id="RUN-000500", user=mock_user, db=test_db)
    assert len(filtered_logs) == 1
    assert filtered_logs[0].artifact_id == "RUN-000500"

    # 3. Test verify_chain endpoint
    verif = await verify_chain(user=mock_user, db=test_db)
    assert verif.chain_integrity == "VERIFIED_VALID"
    assert verif.is_valid is True
    assert verif.total_records == 2

    # 4. Test outbox endpoints
    await enqueue_audit_event(
        db=test_db,
        event_type="ASYNC_EVENT",
        user_id=user_id,
        team_id=team_id,
        metadata={"data": 123},
    )
    status_resp = await get_outbox_status(user=mock_user, db=test_db)
    assert status_resp.pending == 1

    flush_resp = await flush_outbox(max_batch=10, user=mock_user, db=test_db)
    assert flush_resp["status"] == "ok"
    assert flush_resp["processed_metrics"]["processed"] == 1

    status_after = await get_outbox_status(user=mock_user, db=test_db)
    assert status_after.pending == 0
    assert status_after.processed >= 1

    # 5. Test export_audit_logs (CSV)
    csv_resp = await export_audit_logs(format="csv", user=mock_user, db=test_db)
    assert csv_resp.headers["X-Audit-Chain-Integrity"] == "VERIFIED_VALID"

    # Test export_audit_logs (JSON)
    json_resp = await export_audit_logs(format="json", user=mock_user, db=test_db)
    body = json.loads(json_resp.body.decode("utf-8"))
    assert body["chain_integrity"] == "VERIFIED_VALID"
    assert body["total_records"] == 3
    assert body["verification_algorithm"] == "SHA-256 Tamper-Evident Hash Chain"
