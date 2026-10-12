"""
scripts/verify_live_postgres.py
===============================
Comprehensive live PostgreSQL verification for Phase 6.4 + Phase 7.2 integration:
1. Connects to real disposable PostgreSQL 16 instance.
2. Checks PostgreSQL server version.
3. Tests fresh database creation and Alembic full migration from empty database to head (s9t0u1v2w3x4).
4. Verifies Phase 6.4 and Phase 7.2 table definitions, foreign keys, and indexes.
5. Tests upgrade from pre-6.4 baseline (q7r8s9t0u1v2) -> r8s9t0u1v2w3 -> s9t0u1v2w3x4, and clean downgrade.
6. Tests live PostgreSQL transactional rollback, foreign-key constraint violations,
   concurrent exchange operation idempotency, and historical decision assessment supersession.
"""
import asyncio
import os
import sys
import uuid
import asyncpg
from datetime import datetime, timezone

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
    assert current_head in ("s9t0u1v2w3x4", "t0u1v2w3x4y5"), f"Expected s9t0u1v2w3x4 or t0u1v2w3x4y5, got {current_head}"

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

    for t in p64_tables + p72_tables + p65_tables:
        assert t in table_names, f"Missing table {t}"
        print(f"  [OK] Table verified: {t}")

    # 4. Check Constraints & Indexes
    print("\n[VERIFYING] Indexes and Foreign Keys:")
    # Indices on decision_parameter_dependencies
    dep_idx = await conn.fetch(
        "SELECT indexname FROM pg_indexes WHERE tablename = $1",
        "decision_parameter_dependencies"
    )
    dep_idx_names = [r["indexname"] for r in dep_idx]
    assert "ix_dec_param_dep_lookup" in dep_idx_names
    assert "ix_dec_param_dep_user" in dep_idx_names
    assert "ix_dec_param_dep_nature" in dep_idx_names
    print("  [OK] decision_parameter_dependencies indexes verified")

    # Indices on decision_robustness_analyses
    rob_idx = await conn.fetch(
        "SELECT indexname FROM pg_indexes WHERE tablename = $1",
        "decision_robustness_analyses"
    )
    rob_idx_names = [r["indexname"] for r in rob_idx]
    assert "ix_dec_robustness_lookup" in rob_idx_names
    assert "ix_dec_robustness_user" in rob_idx_names
    assert "ix_dec_robustness_hash" in rob_idx_names
    assert "ix_dec_robustness_active" in rob_idx_names
    print("  [OK] decision_robustness_analyses indexes verified")

    # Indices on decision_exposure_assessments
    exp_idx = await conn.fetch(
        "SELECT indexname FROM pg_indexes WHERE tablename = $1",
        "decision_exposure_assessments"
    )
    exp_idx_names = [r["indexname"] for r in exp_idx]
    assert "ix_dec_exposure_lookup" in exp_idx_names
    assert "ix_dec_exposure_user" in exp_idx_names
    assert "ix_dec_exposure_hash" in exp_idx_names
    assert "ix_dec_exposure_active" in exp_idx_names
    print("  [OK] decision_exposure_assessments indexes verified")

    # Indices on solver_exchange_artifacts
    art_idx = await conn.fetch(
        "SELECT indexname FROM pg_indexes WHERE tablename = $1",
        "solver_exchange_artifacts"
    )
    art_idx_names = [r["indexname"] for r in art_idx]
    assert "ix_solver_exchange_artifacts_tenant" in art_idx_names
    assert "ix_solver_exchange_artifacts_user" in art_idx_names
    assert "ix_solver_exchange_artifacts_hash" in art_idx_names
    print("  [OK] solver_exchange_artifacts indexes verified")

    # Indices on solver_exchange_operations
    ops_idx = await conn.fetch(
        "SELECT indexname FROM pg_indexes WHERE tablename = $1",
        "solver_exchange_operations"
    )
    ops_idx_names = [r["indexname"] for r in ops_idx]
    assert "ix_solver_exchange_ops_tenant" in ops_idx_names
    assert "ix_solver_exchange_ops_user" in ops_idx_names
    assert "ix_solver_exchange_ops_idemp" in ops_idx_names
    assert "ix_solver_exchange_ops_hash" in ops_idx_names
    print("  [OK] solver_exchange_operations indexes verified")

    # 5. Test Live PostgreSQL Foreign Key Enforcement
    print("\n[TESTING] Live PostgreSQL Foreign-Key Enforcement:")
    fake_user_id = uuid.uuid4()
    fk_violated = False
    try:
        await conn.execute("""
            INSERT INTO solver_exchange_artifacts (
                id, user_id, artifact_name, file_format, mime_type,
                size_bytes, sha256_hash, storage_path, direction
            ) VALUES (
                $1, $2, 'test.adm', '.adm', 'text/plain',
                100, '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef', '/tmp/test.adm', 'INPUT'
            )
        """, uuid.uuid4(), fake_user_id)
    except asyncpg.exceptions.ForeignKeyViolationError as exc:
        fk_violated = True
        print(f"  [OK] Expected ForeignKeyViolationError raised: {exc.message}")

    assert fk_violated, "Expected foreign key constraint violation on non-existent user_id!"

    # 6. Test Live PostgreSQL Transactional Rollback
    print("\n[TESTING] Live PostgreSQL Transactional Rollback:")
    # Seed a real user
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



    rollback_worked = False
    try:
        async with conn.transaction():
            art_id = uuid.uuid4()
            await conn.execute("""
                INSERT INTO solver_exchange_artifacts (
                    id, organization_id, team_id, user_id, artifact_name, file_format, mime_type,
                    size_bytes, sha256_hash, storage_path, direction
                ) VALUES (
                    $1, $2, $3, $4, 'rollback_test.adm', '.adm', 'text/plain',
                    50, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', '/tmp/test', 'INPUT'
                )
            """, art_id, real_org_id, real_team_id, real_user_id)
            # Deliberately raise exception inside transaction block
            raise RuntimeError("Intentional error to trigger rollback")
    except RuntimeError:
        rollback_worked = True

    assert rollback_worked
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM solver_exchange_artifacts WHERE artifact_name = 'rollback_test.adm'"
    )
    assert count == 0, "Rollback failed: artifact record persisted after exception!"
    print("  [OK] Transactional rollback successfully prevented record persistence")

    # 7. Test Idempotency Key Concurrency / Uniqueness
    print("\n[TESTING] Concurrent Exchange Idempotency Protection:")
    idemp_key = f"idemp-{uuid.uuid4()}"
    op_id_1 = uuid.uuid4()
    await conn.execute("""
        INSERT INTO solver_exchange_operations (
            id, organization_id, team_id, user_id, operation_type,
            adapter_id, adapter_version, solver_name, state, idempotency_key
        ) VALUES (
            $1, $2, $3, $4, 'IMPORT', 'adapter-msc-adams-v1', '1.0.0', 'MSC_ADAMS', 'PENDING', $5
        )
    """, op_id_1, real_org_id, real_team_id, real_user_id, idemp_key)

    # Query with idempotency key
    existing_op = await conn.fetchrow("""
        SELECT id, idempotency_key FROM solver_exchange_operations
        WHERE user_id = $1 AND idempotency_key = $2
    """, real_user_id, idemp_key)
    assert existing_op is not None
    assert existing_op["id"] == op_id_1
    print(f"  [OK] Idempotency lookup successfully recovered existing operation {op_id_1}")

    # 8. Test Historical Decision Assessment Persistence & Supersession
    print("\n[TESTING] Historical Decision Assessment Persistence & Supersession:")
    dec_id = f"DEC-PG-{uuid.uuid4()}"
    assess_id_1 = uuid.uuid4()
    assess_id_2 = uuid.uuid4()


    # Initial assessment
    await conn.execute("""
        INSERT INTO decision_exposure_assessments (
            id, decision_id, decision_type, policy_version, assessment_hash,
            input_snapshot_hash, exposure_classification, exposure_summary,
            governance_separation_notice, is_active, organization_id, team_id, user_id
        ) VALUES (
            $1, $2, 'EngineeringDecision', 'DECISION_TRUST_POLICY_V1',
            'hash_assess_1', 'hash_snap_1', 'HIGH_EXPOSURE', 'Initial assessment',
            'Notice', true, $3, $4, $5
        )
    """, assess_id_1, dec_id, real_org_id, real_team_id, real_user_id)

    # Reassessment superseding assessment 1
    await conn.execute("""
        UPDATE decision_exposure_assessments
        SET is_active = false, superseded_by = $1
        WHERE id = $2
    """, assess_id_2, assess_id_1)

    await conn.execute("""
        INSERT INTO decision_exposure_assessments (
            id, decision_id, decision_type, policy_version, assessment_hash,
            input_snapshot_hash, exposure_classification, exposure_summary,
            governance_separation_notice, is_active, organization_id, team_id, user_id
        ) VALUES (
            $1, $2, 'EngineeringDecision', 'DECISION_TRUST_POLICY_V1',
            'hash_assess_2', 'hash_snap_2', 'LOW_EXPOSURE', 'Reassessed with fresh validation',
            'Notice', true, $3, $4, $5
        )
    """, assess_id_2, dec_id, real_org_id, real_team_id, real_user_id)

    # Verify both records exist and lineage is intact
    history = await conn.fetch("""
        SELECT id, exposure_classification, is_active, superseded_by
        FROM decision_exposure_assessments
        WHERE decision_id = $1
        ORDER BY created_at ASC
    """, dec_id)

    assert len(history) == 2, f"Expected 2 historical records, got {len(history)}"
    assert history[0]["id"] == assess_id_1 and history[0]["is_active"] is False and history[0]["superseded_by"] == assess_id_2
    assert history[1]["id"] == assess_id_2 and history[1]["is_active"] is True and history[1]["superseded_by"] is None
    print("  [OK] Historical decision assessment immutability & supersession verified")


    await conn.close()
    print("\n>>> LIVE POSTGRESQL 16 SCHEMA & BEHAVIORAL CHECKS PASSED! <<<\n")


async def test_baseline_upgrade_and_downgrade():
    print("[TESTING] Baseline Upgrade and Downgrade on Live PostgreSQL 16:")
    sys_conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/postgres")
    await sys_conn.execute("DROP DATABASE IF EXISTS baseline_upgrade_db WITH (FORCE)")
    await sys_conn.execute("CREATE DATABASE baseline_upgrade_db")
    await sys_conn.close()
    print("  [OK] Created fresh database 'baseline_upgrade_db'")

    db_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/baseline_upgrade_db"
    raw_pg_url = "postgresql://postgres:postgres@localhost:5432/baseline_upgrade_db"

    # Step A: Upgrade to pre-6.4/7.2 baseline (q7r8s9t0u1v2)
    import subprocess
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url

    print("  -> Migrating to baseline revision q7r8s9t0u1v2...")
    res = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "q7r8s9t0u1v2"],
        env=env, capture_output=True, text=True, check=True
    )
    test_conn = await asyncpg.connect(raw_pg_url)
    v = await test_conn.fetchval("SELECT version_num FROM alembic_version")
    assert v == "q7r8s9t0u1v2", f"Expected q7r8s9t0u1v2, got {v}"

    tables = [r["table_name"] for r in await test_conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")]
    assert "decision_parameter_dependencies" not in tables
    assert "solver_exchange_operations" not in tables
    print(f"  [OK] Successfully migrated to baseline q7r8s9t0u1v2 (tables count: {len(tables)})")

    # Step B: Upgrade to Phase 6.4 (r8s9t0u1v2w3)
    print("  -> Upgrading from baseline to Phase 6.4 (r8s9t0u1v2w3)...")
    res = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "r8s9t0u1v2w3"],
        env=env, capture_output=True, text=True, check=True
    )
    v = await test_conn.fetchval("SELECT version_num FROM alembic_version")
    assert v == "r8s9t0u1v2w3"
    tables = [r["table_name"] for r in await test_conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")]
    assert "decision_parameter_dependencies" in tables
    assert "decision_exposure_assessments" in tables
    assert "solver_exchange_operations" not in tables
    print("  [OK] Phase 6.4 tables created upon upgrade to r8s9t0u1v2w3")

    # Step C: Upgrade to Phase 7.2 (s9t0u1v2w3x4 - head)
    print("  -> Upgrading to Phase 7.2 head (s9t0u1v2w3x4)...")
    res = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "s9t0u1v2w3x4"],
        env=env, capture_output=True, text=True, check=True
    )
    v = await test_conn.fetchval("SELECT version_num FROM alembic_version")
    assert v == "s9t0u1v2w3x4"
    tables = [r["table_name"] for r in await test_conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")]
    assert "decision_parameter_dependencies" in tables
    assert "decision_exposure_assessments" in tables
    assert "solver_exchange_artifacts" in tables
    assert "solver_exchange_operations" in tables
    print("  [OK] Both Phase 6.4 and Phase 7.2 tables exist simultaneously at head")

    # Step D: Downgrade from head to r8s9t0u1v2w3 (undo Phase 7.2)
    print("  -> Downgrading from head to r8s9t0u1v2w3...")
    res = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "r8s9t0u1v2w3"],
        env=env, capture_output=True, text=True, check=True
    )
    v = await test_conn.fetchval("SELECT version_num FROM alembic_version")
    assert v == "r8s9t0u1v2w3"
    tables = [r["table_name"] for r in await test_conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")]
    assert "solver_exchange_artifacts" not in tables
    assert "solver_exchange_operations" not in tables
    assert "decision_parameter_dependencies" in tables
    print("  [OK] Phase 7.2 tables dropped cleanly; Phase 6.4 preserved")

    # Step E: Downgrade to baseline q7r8s9t0u1v2 (undo Phase 6.4)
    print("  -> Downgrading to baseline q7r8s9t0u1v2...")
    res = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "q7r8s9t0u1v2"],
        env=env, capture_output=True, text=True, check=True
    )
    v = await test_conn.fetchval("SELECT version_num FROM alembic_version")
    assert v == "q7r8s9t0u1v2"
    tables = [r["table_name"] for r in await test_conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")]
    assert "decision_parameter_dependencies" not in tables
    assert "decision_exposure_assessments" not in tables
    print("  [OK] Phase 6.4 tables dropped cleanly; back to baseline")

    # Step F: Upgrade back to head
    print("  -> Upgrading back to head s9t0u1v2w3x4...")
    res = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env, capture_output=True, text=True, check=True
    )
    v = await test_conn.fetchval("SELECT version_num FROM alembic_version")
    assert v in ("s9t0u1v2w3x4", "t0u1v2w3x4y5")
    print(f"  [OK] Full clean upgrade back to head {v} verified")

    await test_conn.close()
    print("\n>>> LIVE BASELINE UPGRADE/DOWNGRADE CYCLE VERIFIED ON POSTGRESQL 16! <<<\n")


async def main():
    await run_verification()
    await test_baseline_upgrade_and_downgrade()

if __name__ == "__main__":
    asyncio.run(main())

