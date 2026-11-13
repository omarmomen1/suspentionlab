"""phase8_4_outcome_tracking

Revision ID: z84a0b1c2d3e
Revises: z83a0b1c2d3e
Create Date: 2026-10-30 04:30:00.000000

Phase 8.4: Engineering Outcome Tracking, Post-Decision Reconciliation & Evidence-Grounded Lessons Learned:
- engineering_outcomes table (persisted, tenant-isolated outcome reconciliation assessments)
- engineering_lessons table (persisted, tenant-isolated organizational engineering lessons)
- Row-Level Security policies for enterprise tenant isolation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'z84a0b1c2d3e'
down_revision: Union[str, None] = 'z83a0b1c2d3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    insp = sa.inspect(bind)

    # Dialect-aware types
    json_type = sa.JSON() if is_sqlite else postgresql.JSONB()
    uuid_type = sa.Uuid() if is_sqlite else postgresql.UUID(as_uuid=True)

    existing_tables = insp.get_table_names()

    # 1. Create engineering_outcomes table
    if 'engineering_outcomes' not in existing_tables:
        op.create_table(
            'engineering_outcomes',
            sa.Column('id', uuid_type, primary_key=True),
            sa.Column('organization_id', uuid_type, nullable=False),
            sa.Column('team_id', uuid_type, nullable=True),
            sa.Column('created_by_user_id', uuid_type, nullable=True),
            sa.Column('outcome_code', sa.String(length=64), nullable=False),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('engineering_investigation_id', sa.String(length=64), nullable=True),
            sa.Column('decision_id', sa.String(length=64), nullable=True),
            sa.Column('decision_release_id', uuid_type, nullable=True),
            sa.Column('memory_id', uuid_type, sa.ForeignKey('engineering_memory_records.id', ondelete='SET NULL'), nullable=True),
            sa.Column('baseline_setup_id', sa.String(length=64), nullable=True),
            sa.Column('candidate_setup_id', sa.String(length=64), nullable=True),
            sa.Column('vehicle_id', sa.String(length=64), nullable=True),
            sa.Column('target_kpi_name', sa.String(length=128), nullable=False),
            sa.Column('kpi_definition', sa.Text(), nullable=True),
            sa.Column('physical_units', sa.String(length=32), nullable=False),
            sa.Column('predeclared_acceptance_criterion', json_type, server_default='{}', nullable=False),
            sa.Column('frozen_prediction', json_type, server_default='{}', nullable=False),
            sa.Column('observation_dataset_id', sa.String(length=128), nullable=False),
            sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('observed_value', sa.Float(), nullable=False),
            sa.Column('observed_uncertainty', json_type, server_default='{}', nullable=False),
            sa.Column('observation_source_type', sa.String(length=64), server_default='PHYSICAL_TRACK_TELEMETRY', nullable=False),
            sa.Column('is_physical_observation', sa.Boolean(), server_default=sa.text('1' if is_sqlite else 'true'), nullable=False),
            sa.Column('is_independent_validation', sa.Boolean(), server_default=sa.text('1' if is_sqlite else 'true'), nullable=False),
            sa.Column('observed_operating_conditions', json_type, server_default='{}', nullable=False),
            sa.Column('model_version', sa.String(length=64), nullable=True),
            sa.Column('parameter_version', sa.String(length=64), nullable=True),
            sa.Column('difference_abs', sa.Float(), nullable=True),
            sa.Column('difference_pct', sa.Float(), nullable=True),
            sa.Column('observed_delta_from_baseline', sa.Float(), nullable=True),
            sa.Column('observed_delta_pct_from_baseline', sa.Float(), nullable=True),
            sa.Column('acceptance_criterion_met', sa.String(length=32), server_default='INDETERMINATE', nullable=False),
            sa.Column('confounders_detected', json_type, server_default='[]', nullable=False),
            sa.Column('causal_attribution_valid', sa.Boolean(), server_default=sa.text('0' if is_sqlite else 'false'), nullable=False),
            sa.Column('outcome_classification', sa.String(length=64), nullable=False),
            sa.Column('missing_evidence', json_type, server_default='[]', nullable=False),
            sa.Column('contradictions_detected', json_type, server_default='[]', nullable=False),
            sa.Column('explicit_limitations', json_type, server_default='[]', nullable=False),
            sa.Column('reconciliation_summary', json_type, server_default='{}', nullable=False),
            sa.Column('outcome_schema_version', sa.String(length=32), server_default='1.0.0', nullable=False),
            sa.Column('reconciliation_policy_version', sa.String(length=32), server_default='8.4.0', nullable=False),
            sa.Column('canonical_outcome_hash', sa.String(length=64), nullable=False),
            sa.Column('source_artifact_hashes', json_type, server_default='{}', nullable=False),
            sa.Column('is_stale', sa.Boolean(), server_default=sa.text('0' if is_sqlite else 'false'), nullable=False),
            sa.Column('staleness_reason', sa.Text(), nullable=True),
            sa.Column('stale_detected_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('supersedes_outcome_id', uuid_type, sa.ForeignKey('engineering_outcomes.id', ondelete='SET NULL'), nullable=True),
            sa.Column('superseded_by_outcome_id', uuid_type, sa.ForeignKey('engineering_outcomes.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

        op.create_index('ix_eng_outcome_org_id', 'engineering_outcomes', ['organization_id'])
        op.create_index('ix_eng_outcome_team_id', 'engineering_outcomes', ['team_id'])
        op.create_index('ix_eng_outcome_code', 'engineering_outcomes', ['outcome_code'])
        op.create_index('ix_eng_outcome_inv_id', 'engineering_outcomes', ['engineering_investigation_id'])
        op.create_index('ix_eng_outcome_dec_id', 'engineering_outcomes', ['decision_id'])
        op.create_index('ix_eng_outcome_rel_id', 'engineering_outcomes', ['decision_release_id'])
        op.create_index('ix_eng_outcome_mem_id', 'engineering_outcomes', ['memory_id'])
        op.create_index('ix_eng_outcome_kpi', 'engineering_outcomes', ['target_kpi_name'])
        op.create_index('ix_eng_outcome_class', 'engineering_outcomes', ['outcome_classification'])
        op.create_index('ix_eng_outcome_hash', 'engineering_outcomes', ['canonical_outcome_hash'])
        op.create_index('ix_eng_outcome_stale', 'engineering_outcomes', ['is_stale'])

    # 2. Create engineering_lessons table
    if 'engineering_lessons' not in existing_tables:
        op.create_table(
            'engineering_lessons',
            sa.Column('id', uuid_type, primary_key=True),
            sa.Column('organization_id', uuid_type, nullable=False),
            sa.Column('team_id', uuid_type, nullable=True),
            sa.Column('created_by_user_id', uuid_type, nullable=True),
            sa.Column('lesson_code', sa.String(length=64), nullable=False),
            sa.Column('outcome_id', uuid_type, sa.ForeignKey('engineering_outcomes.id', ondelete='CASCADE'), nullable=False),
            sa.Column('decision_id', sa.String(length=64), nullable=True),
            sa.Column('investigation_id', sa.String(length=64), nullable=True),
            sa.Column('memory_id', uuid_type, sa.ForeignKey('engineering_memory_records.id', ondelete='SET NULL'), nullable=True),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('summary', sa.Text(), nullable=False),
            sa.Column('detailed_findings', sa.Text(), nullable=False),
            sa.Column('lesson_classification', sa.String(length=64), nullable=False),
            sa.Column('evidence_references', json_type, server_default='[]', nullable=False),
            sa.Column('valid_operating_scope', json_type, server_default='{}', nullable=False),
            sa.Column('key_assumptions', json_type, server_default='[]', nullable=False),
            sa.Column('known_limitations', json_type, server_default='[]', nullable=False),
            sa.Column('conflicting_evidence', json_type, server_default='[]', nullable=False),
            sa.Column('review_status', sa.String(length=32), server_default='DRAFT', nullable=False),
            sa.Column('reviewed_by_user_id', uuid_type, nullable=True),
            sa.Column('reviewed_by_name', sa.String(length=128), nullable=True),
            sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('review_notes', sa.Text(), nullable=True),
            sa.Column('lesson_schema_version', sa.String(length=32), server_default='1.0.0', nullable=False),
            sa.Column('canonical_lesson_hash', sa.String(length=64), nullable=False),
            sa.Column('supersedes_lesson_id', uuid_type, sa.ForeignKey('engineering_lessons.id', ondelete='SET NULL'), nullable=True),
            sa.Column('superseded_by_lesson_id', uuid_type, sa.ForeignKey('engineering_lessons.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

        op.create_index('ix_eng_lesson_org_id', 'engineering_lessons', ['organization_id'])
        op.create_index('ix_eng_lesson_team_id', 'engineering_lessons', ['team_id'])
        op.create_index('ix_eng_lesson_code', 'engineering_lessons', ['lesson_code'])
        op.create_index('ix_eng_lesson_outcome_id', 'engineering_lessons', ['outcome_id'])
        op.create_index('ix_eng_lesson_dec_id', 'engineering_lessons', ['decision_id'])
        op.create_index('ix_eng_lesson_inv_id', 'engineering_lessons', ['investigation_id'])
        op.create_index('ix_eng_lesson_class', 'engineering_lessons', ['lesson_classification'])
        op.create_index('ix_eng_lesson_status', 'engineering_lessons', ['review_status'])
        op.create_index('ix_eng_lesson_hash', 'engineering_lessons', ['canonical_lesson_hash'])

    # 3. Enable Row-Level Security on PostgreSQL
    if not is_sqlite:
        for tbl in ['engineering_outcomes', 'engineering_lessons']:
            op.execute(f"ALTER TABLE IF EXISTS {tbl} ENABLE ROW LEVEL SECURITY;")
            op.execute(f"ALTER TABLE IF EXISTS {tbl} FORCE ROW LEVEL SECURITY;")
            op.execute(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies 
                        WHERE tablename = '{tbl}' AND policyname = '{tbl}_tenant_isolation_policy'
                    ) THEN
                        CREATE POLICY {tbl}_tenant_isolation_policy ON {tbl}
                            USING (
                                organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid
                            )
                            WITH CHECK (
                                organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid
                            );
                    END IF;
                END
                $$;
            """)


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if not is_sqlite:
        for tbl in ['engineering_lessons', 'engineering_outcomes']:
            op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation_policy ON {tbl};")

    op.drop_table('engineering_lessons')
    op.drop_table('engineering_outcomes')
