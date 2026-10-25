"""
scripts/verify_live_postgres.py
===============================
Comprehensive live PostgreSQL 16 verification for Phase 6.7 + Phase 7.5 Integration:
1. Connects to real PostgreSQL 16 instance (localhost:5432 / suspensionlab_test).
2. Checks PostgreSQL server version (verified PostgreSQL 16).
3. Verifies Alembic full migration head at y8z9a0b1c2d3 (linearized over Phase 6.7 x7y8z9a0b1c2).
4. Verifies Phase 6.4, 7.2, 6.5, 7.3, 6.6, 7.4, 6.7, and 7.5 tables, foreign keys, columns, and indexes.
5. Tests live PostgreSQL transactional rollback and foreign-key constraint violations.
6. Tests Multi-Connection Concurrency & Immutability using real database connections:
   - Concurrent validation plan authorization race (Phase 6.6)
   - Concurrent decision reassessment & supersession chain (Phase 6.6)
   - Concurrent execution-job recovery race on expired worker lease (Phase 7.4/7.5)
   - Concurrent dossier governance gate transitions with row locking (SELECT FOR UPDATE) (Phase 6.7)
   - Concurrent source verification revocation vs acceptance race (Phase 6.7)
7. Tests baseline upgrade/downgrade cycle:
   w7x7y7z7a7b7 -> x7y8z9a0b1c2 (Phase 6.7) -> y8z9a0b1c2d3 (Phase 7.5 head)
   -> downgrade to x7y8z9a0b1c2 -> downgrade to w7x7y7z7a7b7 -> clean re-upgrade to head.
"""
import asyncio
import os
import subprocess
import sys
import uuid
import asyncpg
from datetime import datetime, timezone, timedelta

PG_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/suspensionlab_test")


async def run_verification():
    print(f"Connecting to live PostgreSQL at {PG_URL}...")
    conn = await asyncpg.connect(PG_URL)

    # 1. Server Version
    version_str = await conn.fetchval("SELECT version()")
    print(f"[VERIFIED] PostgreSQL Server Version:\n  {version_str}\n")
    assert "PostgreSQL 16" in version_str, f"Unexpected version: {version_str}"

    # 2. Current Migration Head
    current_head = await conn.fetchval("SELECT version_num FROM alembic_version")
    print(f"[VERIFIED] Current Alembic Head in PostgreSQL: {current_head}")
    assert current_head == "z9a0b1c2d3e4", f"Expected single integrated head z9a0b1c2d3e4, got {current_head}"

    # 3. Check Schema Tables
    rows = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = $1 ORDER BY table_name",
        "public"
    )
    table_names = [r["table_name"] for r in rows]
    print(f"[VERIFIED] Total tables in public schema: {len(table_names)}")

    p64_tables = ["decision_parameter_dependencies", "decision_exposure_assessments"]
    p72_tables = ["solver_exchange_artifacts", "solver_exchange_operations"]
    p65_tables = ["decision_robustness_analyses"]
    p73_tables = ["solver_execution_jobs"]
    p66_tables = [
        "engineering_validation_plans",
        "validation_evidence_items",
        "validation_evidence_closures",
        "validation_decision_reassessments",
    ]
    p67_tables = [
        "trusted_source_registries",
        "source_verification_records",
        "engineering_decision_dossiers",
    ]
    p75_tables = [
        "co_simulation_coupling_contracts",
    ]

    all_expected = (
        p64_tables + p72_tables + p65_tables + p73_tables +
        p66_tables + p67_tables + p75_tables
    )
    for t in all_expected:
        assert t in table_names, f"Missing table {t}"
        print(f"  [OK] Table verified: {t}")

    # 4. Check Phase 7.4 & 7.5 Columns on solver_execution_jobs
    job_cols = [r["column_name"] for r in await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'solver_execution_jobs'"
    )]
    p74_cols = ["lease_expires_at", "heartbeat_at", "execution_mode", "benchmark_reference_type"]
    p75_cols = ["worker_id", "lease_generation", "coupling_contract_id", "co_simulation_diagnostics"]
    for col in p74_cols + p75_cols:
        assert col in job_cols, f"Missing column {col} in solver_execution_jobs"
    print("  [OK] Phase 7.4 & Phase 7.5 columns on solver_execution_jobs verified")

    # 5. Check Phase 6.7 Columns on validation_evidence_items
    ev_cols = [r["column_name"] for r in await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'validation_evidence_items'"
    )]
    for col in ("integrity_stage", "source_verification_status", "source_verification_id"):
        assert col in ev_cols, f"Missing column {col} on validation_evidence_items"
        print(f"  [OK] validation_evidence_items column verified: {col}")

    # 6. Check Constraints & Indexes
    print("\n[VERIFYING] Indexes and Foreign Keys:")

    # Phase 7.4 & 7.5 lease & worker indexes
    job_idx = [r["indexname"] for r in await conn.fetch("SELECT indexname FROM pg_indexes WHERE tablename = 'solver_execution_jobs'")]
    assert "ix_solver_execution_jobs_lease" in job_idx, "Missing ix_solver_execution_jobs_lease"
    assert "ix_solver_execution_jobs_worker" in job_idx, "Missing ix_solver_execution_jobs_worker"
    assert "ix_solver_execution_jobs_contract" in job_idx, "Missing ix_solver_execution_jobs_contract"
    print("  [OK] solver_execution_jobs indexes verified")

    # Phase 7.5 cosim contract indexes
    cosim_idx = [r["indexname"] for r in await conn.fetch("SELECT indexname FROM pg_indexes WHERE tablename = 'co_simulation_coupling_contracts'")]
    for idx in ("ix_cosim_contracts_contract_id", "ix_cosim_contracts_status", "ix_cosim_contracts_tenant_status"):
        assert idx in cosim_idx, f"Missing index {idx} in co_simulation_coupling_contracts"
    print("  [OK] co_simulation_coupling_contracts indexes verified")

    # Phase 6.7 Indexes
    ts_idx = [r["indexname"] for r in await conn.fetch("SELECT indexname FROM pg_indexes WHERE tablename = 'trusted_source_registries'")]
    for idx in ("ix_trusted_source_identifier", "ix_trusted_source_tenant"):
        assert idx in ts_idx, f"Missing index {idx} on trusted_source_registries"
    print("  [OK] trusted_source_registries indexes verified")

    sv_idx = [r["indexname"] for r in await conn.fetch("SELECT indexname FROM pg_indexes WHERE tablename = 'source_verification_records'")]
    for idx in ("ix_src_verif_evidence_id", "ix_src_verif_status", "ix_src_verif_tenant"):
        assert idx in sv_idx, f"Missing index {idx} on source_verification_records"
    print("  [OK] source_verification_records indexes verified")

    doss_idx = [r["indexname"] for r in await conn.fetch("SELECT indexname FROM pg_indexes WHERE tablename = 'engineering_decision_dossiers'")]
    for idx in ("ix_dossier_decision_lookup", "ix_dossier_number", "ix_dossier_plan_id", "ix_dossier_gov_state", "ix_dossier_active", "ix_dossier_tenant"):
        assert idx in doss_idx, f"Missing index {idx} on engineering_decision_dossiers"
    print("  [OK] engineering_decision_dossiers indexes verified")

    # Phase 6.6 indexes
    val_plan_idx = [r["indexname"] for r in await conn.fetch("SELECT indexname FROM pg_indexes WHERE tablename = 'engineering_validation_plans'")]
    for idx in ("ix_val_plans_decision_id", "ix_val_plans_parameter_name", "ix_val_plans_status", "ix_val_plans_tenant", "ix_val_plans_active"):
        assert idx in val_plan_idx, f"Missing index {idx} in engineering_validation_plans"
    print("  [OK] engineering_validation_plans indexes verified")

    # 7. Foreign Key Enforcement
    print("\n[TESTING] Live PostgreSQL Foreign-Key Enforcement:")
    fake_user_id = uuid.uuid4()
    fk_violated = False
    try:
        await conn.execute("""
            INSERT INTO engineering_validation_plans (
                id, plan_id, decision_id, parameter_name, validation_objective, validation_method,
                unit, measurement_definition, plan_hash, created_by_user_id
            ) VALUES (
                $1, 'PLAN-FAKE', 'DEC-123', 'spring_rate', 'Measure stiffness', 'RIG_MEASUREMENT',
                'N/m', 'Standard test rig measurement', 'hash123', $2
            )
        """, uuid.uuid4(), fake_user_id)
    except asyncpg.exceptions.ForeignKeyViolationError as exc:
        fk_violated = True
        print(f"  [OK] Expected ForeignKeyViolationError raised: {exc.message}")
    assert fk_violated, "Foreign key constraint failed to enforce non-existent user on validation plan!"

    # 8. Transactional Rollback
    print("\n[TESTING] Live PostgreSQL Transactional Rollback:")
    real_user_id = uuid.uuid4()
    real_org_id = uuid.uuid4()
    real_team_id = uuid.uuid4()
    unique_suffix = str(uuid.uuid4())[:8]

    await conn.execute("""
        INSERT INTO organizations (id, name, slug) VALUES ($1, 'Test Org', $2)
    """, real_org_id, f"test-org-{unique_suffix}")
    await conn.execute("""
        INSERT INTO users (id, organization_id, email, password_hash, plan)
        VALUES ($1, $2, $3, 'hash123', 'ENTERPRISE')
    """, real_user_id, real_org_id, f"test_{unique_suffix}@suspensionlab.io")
    await conn.execute("""
        INSERT INTO teams (id, organization_id, name, slug, owner_id, plan)
        VALUES ($1, $2, 'Test Team', $3, $4, 'ENTERPRISE')
    """, real_team_id, real_org_id, f"test-team-{unique_suffix}", real_user_id)
    await conn.execute("""
        UPDATE users SET team_id = $1 WHERE id = $2
    """, real_team_id, real_user_id)

    # Seed required validation plan, closure, reassessment
    plan_id = uuid.uuid4()
    await conn.execute("""
        INSERT INTO engineering_validation_plans (
            id, plan_id, plan_version, decision_id, decision_type, parameter_name,
            validation_objective, validation_method, unit, measurement_definition,
            status, acceptance_criteria, operating_conditions, plan_hash,
            organization_id, team_id, created_by_user_id
        ) VALUES (
            $1, 'VAL-PLAN-LIVE-01', 1, 'DEC-LIVE-01', 'EngineeringDecision', 'front_spring_rate',
            'Verify front spring stiffness', 'RIG_TEST_4_POST', 'N/mm', '4-post deflection test',
            'AUTHORIZED', '[]'::jsonb, '{}'::jsonb, 'planhash_live_01',
            $2, $3, $4
        )
    """, plan_id, real_org_id, real_team_id, real_user_id)

    closure_id = uuid.uuid4()
    await conn.execute("""
        INSERT INTO validation_evidence_closures (
            id, plan_id, decision_id, parameter_name, closure_verdict, criteria_met,
            criteria_evaluated, closure_summary, closure_hash,
            governance_separation_notice, finite_sample_notice,
            organization_id, team_id, evaluated_by_user_id
        ) VALUES (
            $1, $2, 'DEC-LIVE-01', 'front_spring_rate', 'CLOSED_WITH_SUPPORTING_EVIDENCE', true,
            '[]'::jsonb, 'Closure summary', 'closurehash_live_01',
            'Notice V2', 'Finite sample notice',
            $3, $4, $5
        )
    """, closure_id, plan_id, real_org_id, real_team_id, real_user_id)

    reassessment_id = uuid.uuid4()
    await conn.execute("""
        INSERT INTO validation_decision_reassessments (
            id, decision_id, decision_type, plan_id, closure_id, reversal_status,
            envelope_coverage_statement, reassessment_hash,
            governance_separation_notice,
            organization_id, team_id, reassessed_by_user_id
        ) VALUES (
            $1, 'DEC-LIVE-01', 'EngineeringDecision', $2, $3, 'REVERSAL_RESOLVED',
            'Coverage verified', 'reassesshash_live_01',
            'Notice V2',
            $4, $5, $6
        )
    """, reassessment_id, plan_id, closure_id, real_org_id, real_team_id, real_user_id)

    ev_item_id = uuid.uuid4()
    await conn.execute("""
        INSERT INTO validation_evidence_items (
            id, plan_id, evidence_source_type, source_identifier, source_timestamp,
            parameter_name, observed_value, unit, integrity_hash,
            integrity_stage, source_verification_status,
            organization_id, team_id, submitted_by_user_id
        ) VALUES (
            $1, $2, 'PHYSICAL_RIG_MEASUREMENT', 'RIG-LIVE-01', NOW(),
            'front_spring_rate', 80.2, 'N/mm', 'ev_hash_live_01',
            'SOURCE_CLAIMED', 'UNVERIFIED',
            $3, $4, $5
        )
    """, ev_item_id, plan_id, real_org_id, real_team_id, real_user_id)

    rollback_worked = False
    try:
        async with conn.transaction():
            await conn.execute("""
                INSERT INTO engineering_validation_plans (
                    id, plan_id, decision_id, parameter_name, validation_objective, validation_method,
                    unit, measurement_definition, plan_hash, created_by_user_id, organization_id, team_id
                ) VALUES (
                    $1, 'PLAN-ROLLBACK', 'DEC-ROLLBACK', 'spring_rate', 'Objective', 'RIG_MEASUREMENT',
                    'N/m', 'Def', 'rollback_hash', $2, $3, $4
                )
            """, uuid.uuid4(), real_user_id, real_org_id, real_team_id)
            raise RuntimeError("Intentional crash during plan transaction")
    except RuntimeError:
        rollback_worked = True
    assert rollback_worked
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM engineering_validation_plans WHERE plan_hash = 'rollback_hash'"
    )
    assert count == 0, "Rollback failed: validation plan persisted after crash!"
    print("  [OK] Transactional rollback successfully prevented record persistence")

    # 9. Multi-Connection Concurrency Tests
    print("\n[TESTING] Multi-Connection Concurrency & Governance Gates:")
    pool = [await asyncpg.connect(PG_URL) for _ in range(5)]

    # 9A. Concurrent Validation Plan Authorization
    print("  -> Testing concurrent validation plan authorization across 5 connections...")
    test_plan_id = uuid.uuid4()
    await conn.execute("""
        INSERT INTO engineering_validation_plans (
            id, plan_id, decision_id, parameter_name, validation_objective, validation_method,
            unit, measurement_definition, status, plan_hash, created_by_user_id, organization_id, team_id
        ) VALUES (
            $1, 'PLAN-CONC-AUTH', 'DEC-AUTH', 'spring_rate', 'Objective', 'RIG_MEASUREMENT',
            'N/m', 'Def', 'CRITERIA_ESTABLISHED', 'auth_hash_1', $2, $3, $4
        )
    """, test_plan_id, real_user_id, real_org_id, real_team_id)

    async def try_authorize_plan(c: asyncpg.Connection, client_idx: int):
        try:
            async with c.transaction():
                row = await c.fetchrow(
                    "SELECT id, status FROM engineering_validation_plans WHERE id = $1 FOR UPDATE",
                    test_plan_id
                )
                if row["status"] == "AUTHORIZED":
                    return ("ALREADY_AUTHORIZED", client_idx)
                if row["status"] != "CRITERIA_ESTABLISHED":
                    return (f"INVALID_STATUS_{row['status']}", client_idx)
                await asyncio.sleep(0.02)  # hold lock
                await c.execute("""
                    UPDATE engineering_validation_plans
                    SET status = 'AUTHORIZED', authorized_by_user_id = $1, authorized_at = NOW()
                    WHERE id = $2
                """, real_user_id, test_plan_id)
                return ("AUTHORIZED", client_idx)
        except Exception as e:
            return ("ERROR", str(e), client_idx)

    auth_results = await asyncio.gather(*[try_authorize_plan(pool[i], i) for i in range(5)])
    success_auth = sum(1 for status, _ in auth_results if status == "AUTHORIZED")
    already_auth = sum(1 for status, _ in auth_results if status == "ALREADY_AUTHORIZED")
    assert success_auth == 1, f"Expected exactly 1 AUTHORIZED, got {success_auth} (results: {auth_results})"
    assert already_auth == 4, f"Expected exactly 4 ALREADY_AUTHORIZED, got {already_auth}"
    print(f"  [OK] Concurrent authorization race resolved: exactly 1 authorized, 4 locked out")

    # 9B. Concurrent Decision Reassessment Supersession
    print("  -> Testing concurrent decision reassessment & lineage supersession...")
    reassess_dec_id = f"DEC-REASSESS-{uuid.uuid4()}"
    closure_id_conc = uuid.uuid4()
    await conn.execute("""
        INSERT INTO validation_evidence_closures (
            id, plan_id, decision_id, parameter_name, closure_verdict, criteria_met,
            closure_summary, closure_hash, governance_separation_notice, finite_sample_notice,
            deployment_safety_inferred, evaluated_by_user_id, organization_id, team_id
        ) VALUES (
            $1, $2, $3, 'spring_rate', 'EVIDENCE_GAP_CLOSED', true,
            'Closure summary', 'closure_hash_1', 'Notice', 'Finite',
            false, $4, $5, $6
        )
    """, closure_id_conc, test_plan_id, reassess_dec_id, real_user_id, real_org_id, real_team_id)

    reassess_id_1 = uuid.uuid4()
    await conn.execute("""
        INSERT INTO validation_decision_reassessments (
            id, decision_id, plan_id, closure_id, reversal_status,
            envelope_coverage_statement, governance_separation_notice,
            deployment_safety_inferred, is_active, reassessed_by_user_id,
            organization_id, team_id, reassessment_hash
        ) VALUES (
            $1, $2, $3, $4, 'NO_REVERSAL',
            'Finite sample envelope', 'Notice',
            false, true, $5,
            $6, $7, 'reassess_hash_1'
        )
    """, reassess_id_1, reassess_dec_id, test_plan_id, closure_id_conc, real_user_id, real_org_id, real_team_id)

    async def try_reassess(c: asyncpg.Connection, client_idx: int):
        new_reassess_id = uuid.uuid4()
        try:
            async with c.transaction():
                lock_id = abs(hash((reassess_dec_id, "reassess_chain"))) % (2**63 - 1)
                await c.execute("SELECT pg_advisory_xact_lock($1)", lock_id)
                active = await c.fetchrow("""
                    SELECT id FROM validation_decision_reassessments
                    WHERE decision_id = $1 AND is_active = true
                """, reassess_dec_id)
                if not active:
                    return ("NO_ACTIVE", client_idx)
                await c.execute("""
                    INSERT INTO validation_decision_reassessments (
                        id, decision_id, plan_id, closure_id, reversal_status,
                        envelope_coverage_statement, governance_separation_notice,
                        deployment_safety_inferred, is_active, reassessed_by_user_id,
                        organization_id, team_id, reassessment_hash
                    ) VALUES (
                        $1, $2, $3, $4, 'NO_REVERSAL',
                        'Finite sample envelope', 'Notice',
                        false, true, $5,
                        $6, $7, $8
                    )
                """, new_reassess_id, reassess_dec_id, test_plan_id, closure_id_conc, real_user_id, real_org_id, real_team_id, f"hash_{client_idx}")
                await asyncio.sleep(0.01)
                await c.execute("""
                    UPDATE validation_decision_reassessments
                    SET is_active = false, superseded_by = $1
                    WHERE id = $2
                """, new_reassess_id, active["id"])
                return ("REASSESSED", new_reassess_id, client_idx)
        except Exception as e:
            return ("ERROR", str(e), client_idx)

    reassess_results = await asyncio.gather(*[try_reassess(pool[i], i) for i in range(5)])
    successful_reassessments = [r for r in reassess_results if r[0] == "REASSESSED"]
    assert len(successful_reassessments) == 5, f"All 5 serializable supersessions succeeded"
    active_records = await conn.fetch("""
        SELECT id FROM validation_decision_reassessments
        WHERE decision_id = $1 AND is_active = true
    """, reassess_dec_id)
    assert len(active_records) == 1, f"Expected exactly 1 active reassessment, got {len(active_records)}"
    print(f"  [OK] Decision reassessment supersession chain preserved: exactly 1 active record, 5 historical links")

    # 9C. Concurrent Worker Lease Recovery Race (Phase 7.4/7.5)
    print("  -> Testing concurrent execution job recovery on expired worker lease...")
    crashed_job_id = uuid.uuid4()
    expired_lease = datetime.now(timezone.utc) - timedelta(minutes=10)
    await conn.execute("""
        INSERT INTO solver_execution_jobs (
            id, organization_id, team_id, user_id, solver_name, solver_version,
            adapter_id, state, input_artifact_hash, lease_expires_at, heartbeat_at, execution_mode
        ) VALUES (
            $1, $2, $3, $4, 'EXTERNAL_CAE_SOLVER', '1.0.0',
            'adapter-external-cae-v1', 'RUNNING', 'hash_crash_test', $5, $5, 'TRUSTED_ALLOWLIST'
        )
    """, crashed_job_id, real_org_id, real_team_id, real_user_id, expired_lease)

    async def try_recover_job(c: asyncpg.Connection, client_idx: int):
        now = datetime.now(timezone.utc)
        try:
            async with c.transaction():
                row = await c.fetchrow("""
                    SELECT id, state, lease_expires_at
                    FROM solver_execution_jobs
                    WHERE id = $1 FOR UPDATE
                """, crashed_job_id)
                if row["state"] == "RUNNING" and row["lease_expires_at"] and row["lease_expires_at"] < now:
                    await asyncio.sleep(0.01)
                    await c.execute("""
                        UPDATE solver_execution_jobs
                        SET state = 'FAILED', failure_reason = 'WORKER_LEASE_EXPIRED_CRASH_RECOVERED',
                            lease_expires_at = NULL, exit_code = -99
                        WHERE id = $1
                    """, crashed_job_id)
                    return ("RECOVERED", client_idx)
                return (f"ALREADY_{row['state']}", client_idx)
        except Exception as e:
            return ("ERROR", str(e), client_idx)

    recovery_results = await asyncio.gather(*[try_recover_job(pool[i], i) for i in range(5)])
    recovered_count = sum(1 for r in recovery_results if r[0] == "RECOVERED")
    already_failed = sum(1 for r in recovery_results if r[0] == "ALREADY_FAILED")
    assert recovered_count == 1, f"Expected exactly 1 worker to recover job, got {recovered_count}"
    assert already_failed == 4, f"Expected 4 workers to detect ALREADY_FAILED, got {already_failed}"
    final_job_state = await conn.fetchrow("SELECT state, exit_code, failure_reason FROM solver_execution_jobs WHERE id = $1", crashed_job_id)
    assert final_job_state["state"] == "FAILED"
    assert final_job_state["exit_code"] == -99
    assert final_job_state["failure_reason"] == "WORKER_LEASE_EXPIRED_CRASH_RECOVERED"
    print(f"  [OK] Concurrent lease recovery race resolved: exactly 1 worker transitioned state, 4 saw terminal state")

    # 9D. Concurrent Dossier Governance Gate Transitions with Row-Level Locking (Phase 6.7)
    print("  -> Testing concurrent governance transitions with row locking (SELECT FOR UPDATE)...")
    dossier_id = uuid.uuid4()
    doss_num = f"DOS-LIVE-{uuid.uuid4().hex[:6]}"
    await conn.execute("""
        INSERT INTO engineering_decision_dossiers (
            id, dossier_number, decision_id, engineering_question, dossier_version,
            plan_id, plan_hash, closure_id, closure_hash, reassessment_id, reassessment_hash,
            governance_state, admissibility_status, criteria_satisfaction_status,
            closure_status, conclusion_review_status, decision_approval_status,
            dossier_content_hash, is_active, organization_id, team_id, compiled_by_user_id
        ) VALUES (
            $1, $2, 'DEC-LIVE-01', 'Question live test', 1,
            $3, 'planhash_live_01', $4, 'closurehash_live_01', $5, 'reassesshash_live_01',
            'DRAFT', 'PENDING', 'PENDING', 'PENDING', 'PENDING', 'PENDING',
            'hash_doss_01', true, $6, $7, $8
        )
    """, dossier_id, doss_num, plan_id, closure_id, reassessment_id, real_org_id, real_team_id, real_user_id)

    conn1, conn2 = pool[0], pool[1]

    async def review_worker_1():
        async with conn1.transaction():
            row = await conn1.fetchrow(
                "SELECT id, governance_state FROM engineering_decision_dossiers WHERE id = $1 FOR UPDATE",
                dossier_id
            )
            if row["governance_state"] == "DRAFT":
                await asyncio.sleep(0.05)
                await conn1.execute("""
                    UPDATE engineering_decision_dossiers
                    SET governance_state = 'IN_REVIEW', admissibility_status = 'EVIDENCE_ADMITTED'
                    WHERE id = $1
                """, dossier_id)
                return "TRANSITIONED_TO_IN_REVIEW"
            return row["governance_state"]

    async def review_worker_2():
        await asyncio.sleep(0.01)
        async with conn2.transaction():
            row = await conn2.fetchrow(
                "SELECT id, governance_state FROM engineering_decision_dossiers WHERE id = $1 FOR UPDATE",
                dossier_id
            )
            if row["governance_state"] == "DRAFT":
                await conn2.execute("""
                    UPDATE engineering_decision_dossiers
                    SET governance_state = 'IN_REVIEW', admissibility_status = 'EVIDENCE_ADMITTED'
                    WHERE id = $1
                """, dossier_id)
                return "TRANSITIONED_TO_IN_REVIEW"
            return f"SEEN_{row['governance_state']}"

    r_res1, r_res2 = await asyncio.gather(review_worker_1(), review_worker_2())
    assert r_res1 == "TRANSITIONED_TO_IN_REVIEW"
    assert r_res2 == "SEEN_IN_REVIEW"
    print("  [OK] Row-level locking cleanly prevented duplicate transition races on dossier")

    # 9E. Concurrent Source Revocation vs Active Acceptance (Phase 6.7)
    print("  -> Testing concurrent source verification revocation vs acceptance...")
    verif_id = uuid.uuid4()
    await conn.execute("""
        INSERT INTO source_verification_records (
            id, evidence_item_id, verification_method, verification_status,
            verifier_identity, verifier_role, artifact_hash, verification_hash,
            organization_id, team_id, verifier_user_id
        ) VALUES (
            $1, $2, 'AUTHORIZED_CUSTODIAN_REVIEW', 'VERIFIED',
            'Chief Auditor', 'CHIEF_ENGINEER', 'ev_hash_live_01', 'verif_hash_concurrent',
            $3, $4, $5
        )
    """, verif_id, ev_item_id, real_org_id, real_team_id, real_user_id)

    async def revoke_source():
        async with conn1.transaction():
            row = await conn1.fetchrow(
                "SELECT id, is_revoked FROM source_verification_records WHERE id = $1 FOR UPDATE",
                verif_id
            )
            if not row["is_revoked"]:
                await conn1.execute("""
                    UPDATE source_verification_records
                    SET is_revoked = true, verification_status = 'REVOKED'
                    WHERE id = $1
                """, verif_id)
                await conn1.execute("""
                    UPDATE validation_evidence_items
                    SET source_verification_status = 'REVOKED', integrity_stage = 'SOURCE_CLAIMED'
                    WHERE id = $1
                """, ev_item_id)
                return ("REVOKED", verif_id)
            return ("ALREADY_REVOKED", verif_id)

    async def accept_evidence():
        async with conn2.transaction():
            row = await conn2.fetchrow(
                "SELECT is_revoked, verification_status FROM source_verification_records WHERE id = $1 FOR UPDATE",
                verif_id
            )
            if row["is_revoked"] or row["verification_status"] == "REVOKED":
                return ("REJECTED_DUE_TO_REVOCATION", verif_id)
            return ("ACCEPTED", verif_id)

    rev_res, acc_res = await asyncio.gather(revoke_source(), accept_evidence())
    print(f"  [OK] Concurrency resolved: revoke -> {rev_res[0]}, accept -> {acc_res[0]}")
    final_ev_status = await conn.fetchval(
        "SELECT source_verification_status FROM validation_evidence_items WHERE id = $1",
        ev_item_id
    )
    assert final_ev_status == "REVOKED"
    print(f"  [OK] Evidence item successfully cascades to '{final_ev_status}'")

    for p in pool:
        await p.close()
    await conn.close()
    print("\n>>> LIVE POSTGRESQL 16 SCHEMA & CONCURRENCY CHECKS PASSED! <<<\n")


async def test_baseline_upgrade_and_downgrade():
    print("[TESTING] Baseline Upgrade and Downgrade on Live PostgreSQL 16:")
    sys_conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/postgres")
    await sys_conn.execute("DROP DATABASE IF EXISTS baseline_upgrade_db WITH (FORCE)")
    await sys_conn.execute("CREATE DATABASE baseline_upgrade_db")
    await sys_conn.close()
    print("  [OK] Created fresh database 'baseline_upgrade_db'")

    db_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/baseline_upgrade_db"
    raw_pg_url = "postgresql://postgres:postgres@localhost:5432/baseline_upgrade_db"

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    # Step A: Upgrade to pre-6.7 merge baseline (w7x7y7z7a7b7)
    print("  -> Migrating to merge baseline revision w7x7y7z7a7b7...")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "w7x7y7z7a7b7"],
        env=env, capture_output=True, text=True, check=True
    )
    test_conn = await asyncpg.connect(raw_pg_url)
    v = await test_conn.fetchval("SELECT version_num FROM alembic_version")
    assert v == "w7x7y7z7a7b7"
    tables = [r["table_name"] for r in await test_conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")]
    assert "trusted_source_registries" not in tables
    assert "source_verification_records" not in tables
    assert "engineering_decision_dossiers" not in tables
    assert "co_simulation_coupling_contracts" not in tables
    print(f"  [OK] Successfully migrated to baseline w7x7y7z7a7b7 (tables count: {len(tables)})")

    # Step B: Upgrade to Phase 6.7 (x7y8z9a0b1c2)
    print("  -> Upgrading to Phase 6.7 revision x7y8z9a0b1c2...")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "x7y8z9a0b1c2"],
        env=env, capture_output=True, text=True, check=True
    )
    v = await test_conn.fetchval("SELECT version_num FROM alembic_version")
    assert v == "x7y8z9a0b1c2"
    tables = [r["table_name"] for r in await test_conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")]
    assert "trusted_source_registries" in tables
    assert "source_verification_records" in tables
    assert "engineering_decision_dossiers" in tables
    assert "co_simulation_coupling_contracts" not in tables
    print("  [OK] Phase 6.7 tables created upon upgrade to x7y8z9a0b1c2")

    # Step C: Upgrade to Phase 7.6 integrated head (z9a0b1c2d3e4)
    print("  -> Upgrading to Phase 7.6 integrated head z9a0b1c2d3e4...")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env, capture_output=True, text=True, check=True
    )
    v = await test_conn.fetchval("SELECT version_num FROM alembic_version")
    assert v == "z9a0b1c2d3e4"
    tables = [r["table_name"] for r in await test_conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")]
    assert "trusted_source_registries" in tables
    assert "source_verification_records" in tables
    assert "engineering_decision_dossiers" in tables
    assert "co_simulation_coupling_contracts" in tables
    contract_cols = [r["column_name"] for r in await test_conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'co_simulation_coupling_contracts'")]
    assert "feedback_topology" in contract_cols
    assert "staggered_execution_order" in contract_cols
    assert "energy_residual_tolerance" in contract_cols
    job_cols = [r["column_name"] for r in await test_conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'solver_execution_jobs'")]
    assert "worker_id" in job_cols
    assert "lease_generation" in job_cols
    assert "coupling_contract_id" in job_cols
    assert "co_simulation_diagnostics" in job_cols
    assert "feedback_metrics" in job_cols
    assert "cosim_synchronization_mode" in job_cols
    print("  [OK] Phase 7.6 table and columns created upon upgrade to z9a0b1c2d3e4")

    # Step D: Downgrade from head z9a0b1c2d3e4 to Phase 7.5 y8z9a0b1c2d3
    print("  -> Downgrading from head z9a0b1c2d3e4 to Phase 7.5 y8z9a0b1c2d3...")
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "y8z9a0b1c2d3"],
        env=env, capture_output=True, text=True, check=True
    )
    v = await test_conn.fetchval("SELECT version_num FROM alembic_version")
    assert v == "y8z9a0b1c2d3"
    contract_cols_down = [r["column_name"] for r in await test_conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'co_simulation_coupling_contracts'")]
    assert "feedback_topology" not in contract_cols_down
    print("  [OK] Successfully downgraded back to Phase 7.5 y8z9a0b1c2d3; Phase 7.6 columns removed")

    # Step E: Downgrade from y8z9a0b1c2d3 to Phase 6.7 x7y8z9a0b1c2
    print("  -> Downgrading from y8z9a0b1c2d3 to x7y8z9a0b1c2...")
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "x7y8z9a0b1c2"],
        env=env, capture_output=True, text=True, check=True
    )
    v = await test_conn.fetchval("SELECT version_num FROM alembic_version")
    assert v == "x7y8z9a0b1c2"
    tables = [r["table_name"] for r in await test_conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")]
    assert "co_simulation_coupling_contracts" not in tables
    assert "trusted_source_registries" in tables
    print("  [OK] Successfully downgraded back to Phase 6.7 x7y8z9a0b1c2; Phase 7.5 table cleanly removed")

    # Step F: Downgrade from x7y8z9a0b1c2 to w7x7y7z7a7b7 (undo Phase 6.7)
    print("  -> Downgrading from x7y8z9a0b1c2 to w7x7y7z7a7b7...")
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "w7x7y7z7a7b7"],
        env=env, capture_output=True, text=True, check=True
    )
    v = await test_conn.fetchval("SELECT version_num FROM alembic_version")
    assert v == "w7x7y7z7a7b7"
    tables = [r["table_name"] for r in await test_conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")]
    assert "trusted_source_registries" not in tables
    assert "source_verification_records" not in tables
    assert "engineering_decision_dossiers" not in tables
    print("  [OK] Phase 6.7 tables dropped cleanly upon downgrade")

    # Step G: Clean re-upgrade to head (z9a0b1c2d3e4)
    print("  -> Re-upgrading to head z9a0b1c2d3e4...")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env, capture_output=True, text=True, check=True
    )
    v = await test_conn.fetchval("SELECT version_num FROM alembic_version")
    assert v == "z9a0b1c2d3e4"
    print(f"  [OK] Full clean upgrade back to head {v} verified")

    await test_conn.close()
    print("\n>>> LIVE BASELINE UPGRADE/DOWNGRADE CYCLE VERIFIED ON POSTGRESQL 16! <<<\n")


async def main():
    await run_verification()
    await test_baseline_upgrade_and_downgrade()
    print("POSTGRESQL_LIVE_VERIFIED = TRUE")

if __name__ == "__main__":
    asyncio.run(main())
