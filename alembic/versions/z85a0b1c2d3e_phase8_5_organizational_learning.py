"""phase8_5_organizational_learning

Revision ID: z85a0b1c2d3e
Revises: z84a0b1c2d3e
Create Date: 2026-11-04 05:00:00.000000

Phase 8.5: Organizational Engineering Learning, Cross-Case Pattern Discovery & Contradiction Intelligence:
- engineering_patterns table (persisted, tenant-isolated cross-case engineering patterns)
- contradiction_records table (persisted, tenant-isolated engineering contradiction records)
- organizational_learnings table (persisted, tenant-isolated authorized organizational learnings)
- Row-Level Security policies for enterprise tenant isolation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'z85a0b1c2d3e'
down_revision: Union[str, None] = 'z84a0b1c2d3e'
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

    # 1. Create engineering_patterns table
    if 'engineering_patterns' not in existing_tables:
        op.create_table(
            'engineering_patterns',
            sa.Column('id', uuid_type, primary_key=True),
            sa.Column('organization_id', uuid_type, nullable=False),
            sa.Column('team_id', uuid_type, nullable=True),
            sa.Column('created_by_user_id', uuid_type, nullable=True),
            sa.Column('pattern_code', sa.String(length=64), nullable=False),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('engineering_domain', sa.String(length=64), nullable=False),
            sa.Column('pattern_classification', sa.String(length=64), nullable=False),
            sa.Column('independence_classification', sa.String(length=64), nullable=False),
            sa.Column('contributing_outcome_ids', json_type, server_default='[]', nullable=False),
            sa.Column('contributing_case_ids', json_type, server_default='[]', nullable=False),
            sa.Column('independent_source_count', sa.Integer(), server_default='0', nullable=False),
            sa.Column('total_evidence_count', sa.Integer(), server_default='0', nullable=False),
            sa.Column('generalization_classification', sa.String(length=64), nullable=False),
            sa.Column('applicability_boundaries', json_type, server_default='{}', nullable=False),
            sa.Column('observed_kpi_impacts', json_type, server_default='{}', nullable=False),
            sa.Column('parameter_sensitivities', json_type, server_default='{}', nullable=False),
            sa.Column('pattern_manifest', json_type, server_default='{}', nullable=False),
            sa.Column('is_stale', sa.Boolean(), server_default=sa.text('0' if is_sqlite else 'false'), nullable=False),
            sa.Column('staleness_reason', sa.Text(), nullable=True),
            sa.Column('stale_detected_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('supersedes_pattern_id', uuid_type, sa.ForeignKey('engineering_patterns.id', ondelete='SET NULL'), nullable=True),
            sa.Column('superseded_by_pattern_id', uuid_type, sa.ForeignKey('engineering_patterns.id', ondelete='SET NULL'), nullable=True),
            sa.Column('pattern_schema_version', sa.String(length=32), server_default='1.0.0', nullable=False),
            sa.Column('pattern_policy_version', sa.String(length=32), server_default='8.5.0', nullable=False),
            sa.Column('canonical_pattern_hash', sa.String(length=64), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

        op.create_index('ix_eng_pattern_org_id', 'engineering_patterns', ['organization_id'])
        op.create_index('ix_eng_pattern_team_id', 'engineering_patterns', ['team_id'])
        op.create_index('ix_eng_pattern_code', 'engineering_patterns', ['pattern_code'])
        op.create_index('ix_eng_pattern_domain', 'engineering_patterns', ['engineering_domain'])
        op.create_index('ix_eng_pattern_class', 'engineering_patterns', ['pattern_classification'])
        op.create_index('ix_eng_pattern_indep', 'engineering_patterns', ['independence_classification'])
        op.create_index('ix_eng_pattern_gen', 'engineering_patterns', ['generalization_classification'])
        op.create_index('ix_eng_pattern_hash', 'engineering_patterns', ['canonical_pattern_hash'])
        op.create_index('ix_eng_pattern_stale', 'engineering_patterns', ['is_stale'])

    # 2. Create contradiction_records table
    if 'contradiction_records' not in existing_tables:
        op.create_table(
            'contradiction_records',
            sa.Column('id', uuid_type, primary_key=True),
            sa.Column('organization_id', uuid_type, nullable=False),
            sa.Column('team_id', uuid_type, nullable=True),
            sa.Column('created_by_user_id', uuid_type, nullable=True),
            sa.Column('contradiction_code', sa.String(length=64), nullable=False),
            sa.Column('contradiction_type', sa.String(length=64), nullable=False),
            sa.Column('engineering_domain', sa.String(length=64), nullable=False),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('primary_case_or_outcome_id', sa.String(length=128), nullable=False),
            sa.Column('conflicting_case_or_outcome_id', sa.String(length=128), nullable=False),
            sa.Column('primary_evidence_summary', json_type, server_default='{}', nullable=False),
            sa.Column('conflicting_evidence_summary', json_type, server_default='{}', nullable=False),
            sa.Column('divergence_metrics', json_type, server_default='{}', nullable=False),
            sa.Column('resolution_status', sa.String(length=64), server_default='UNRESOLVED', nullable=False),
            sa.Column('resolution_justification', sa.Text(), nullable=True),
            sa.Column('resolved_by_user_id', uuid_type, nullable=True),
            sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('canonical_contradiction_hash', sa.String(length=64), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

        op.create_index('ix_eng_contradiction_org_id', 'contradiction_records', ['organization_id'])
        op.create_index('ix_eng_contradiction_team_id', 'contradiction_records', ['team_id'])
        op.create_index('ix_eng_contradiction_code', 'contradiction_records', ['contradiction_code'])
        op.create_index('ix_eng_contradiction_type', 'contradiction_records', ['contradiction_type'])
        op.create_index('ix_eng_contradiction_domain', 'contradiction_records', ['engineering_domain'])
        op.create_index('ix_eng_contradiction_prim', 'contradiction_records', ['primary_case_or_outcome_id'])
        op.create_index('ix_eng_contradiction_conf', 'contradiction_records', ['conflicting_case_or_outcome_id'])
        op.create_index('ix_eng_contradiction_status', 'contradiction_records', ['resolution_status'])
        op.create_index('ix_eng_contradiction_hash', 'contradiction_records', ['canonical_contradiction_hash'])

    # 3. Create organizational_learnings table
    if 'organizational_learnings' not in existing_tables:
        op.create_table(
            'organizational_learnings',
            sa.Column('id', uuid_type, primary_key=True),
            sa.Column('organization_id', uuid_type, nullable=False),
            sa.Column('team_id', uuid_type, nullable=True),
            sa.Column('created_by_user_id', uuid_type, nullable=True),
            sa.Column('learning_code', sa.String(length=64), nullable=False),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('executive_summary', sa.Text(), nullable=False),
            sa.Column('engineering_findings', sa.Text(), nullable=False),
            sa.Column('engineering_domain', sa.String(length=64), nullable=False),
            sa.Column('pattern_id', uuid_type, sa.ForeignKey('engineering_patterns.id', ondelete='SET NULL'), nullable=True),
            sa.Column('underlying_outcome_ids', json_type, server_default='[]', nullable=False),
            sa.Column('generalization_classification', sa.String(length=64), nullable=False),
            sa.Column('authorized_operating_envelope', json_type, server_default='{}', nullable=False),
            sa.Column('counter_indications', json_type, server_default='[]', nullable=False),
            sa.Column('review_status', sa.String(length=32), server_default='DRAFT', nullable=False),
            sa.Column('reviewed_by_user_id', uuid_type, nullable=True),
            sa.Column('reviewed_by_name', sa.String(length=128), nullable=True),
            sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('review_notes', sa.Text(), nullable=True),
            sa.Column('supersedes_learning_id', uuid_type, sa.ForeignKey('organizational_learnings.id', ondelete='SET NULL'), nullable=True),
            sa.Column('superseded_by_learning_id', uuid_type, sa.ForeignKey('organizational_learnings.id', ondelete='SET NULL'), nullable=True),
            sa.Column('is_stale', sa.Boolean(), server_default=sa.text('0' if is_sqlite else 'false'), nullable=False),
            sa.Column('staleness_reason', sa.Text(), nullable=True),
            sa.Column('canonical_learning_hash', sa.String(length=64), nullable=False),
            sa.Column('learning_schema_version', sa.String(length=32), server_default='1.0.0', nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

        op.create_index('ix_org_learning_org_id', 'organizational_learnings', ['organization_id'])
        op.create_index('ix_org_learning_team_id', 'organizational_learnings', ['team_id'])
        op.create_index('ix_org_learning_code', 'organizational_learnings', ['learning_code'])
        op.create_index('ix_org_learning_domain', 'organizational_learnings', ['engineering_domain'])
        op.create_index('ix_org_learning_pattern_id', 'organizational_learnings', ['pattern_id'])
        op.create_index('ix_org_learning_status', 'organizational_learnings', ['review_status'])
        op.create_index('ix_org_learning_gen', 'organizational_learnings', ['generalization_classification'])
        op.create_index('ix_org_learning_hash', 'organizational_learnings', ['canonical_learning_hash'])
        op.create_index('ix_org_learning_stale', 'organizational_learnings', ['is_stale'])

    # 4. Enable Row-Level Security on PostgreSQL
    if not is_sqlite:
        for tbl in ['engineering_patterns', 'contradiction_records', 'organizational_learnings']:
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
        for tbl in ['organizational_learnings', 'contradiction_records', 'engineering_patterns']:
            op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation_policy ON {tbl};")

    op.drop_table('organizational_learnings')
    op.drop_table('contradiction_records')
    op.drop_table('engineering_patterns')
