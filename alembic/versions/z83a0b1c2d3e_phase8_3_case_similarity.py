"""phase8_3_case_similarity

Revision ID: z83a0b1c2d3e
Revises: z81a0b1c2d3e
Create Date: 2026-10-28 18:20:00.000000

Phase 8.3: Engineering Case Similarity, Physical Applicability & Evidence-Based Knowledge Transfer:
- engineering_case_comparisons table (persisted, tenant-isolated physical case comparison assessments)
- Row-Level Security policies for enterprise tenant isolation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'z83a0b1c2d3e'
down_revision: Union[str, None] = 'z81a0b1c2d3e'
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

    # 1. Create engineering_case_comparisons table
    if 'engineering_case_comparisons' not in existing_tables:
        op.create_table(
            'engineering_case_comparisons',
            sa.Column('id', uuid_type, primary_key=True),
            sa.Column('organization_id', uuid_type, nullable=False),
            sa.Column('team_id', uuid_type, nullable=True),
            sa.Column('created_by_user_id', uuid_type, nullable=True),
            sa.Column('current_case_id', sa.String(length=128), nullable=False),
            sa.Column('current_case_type', sa.String(length=64), server_default='CURRENT_ENGINEERING_CASE', nullable=False),
            sa.Column('historical_memory_id', uuid_type, sa.ForeignKey('engineering_memory_records.id', ondelete='CASCADE'), nullable=False),
            sa.Column('historical_snapshot_hash', sa.String(length=64), nullable=False),
            sa.Column('comparison_policy_version', sa.String(length=32), server_default='8.3.0', nullable=False),
            sa.Column('overall_applicability', sa.String(length=64), nullable=False),
            sa.Column('physical_similarity_score', sa.Float(), server_default='0.0', nullable=False),
            sa.Column('evidence_quality_score', sa.Float(), server_default='0.0', nullable=False),
            sa.Column('can_transfer_knowledge', sa.Boolean(), server_default=sa.text('0' if is_sqlite else 'false'), nullable=False),
            sa.Column('is_stale', sa.Boolean(), server_default=sa.text('0' if is_sqlite else 'false'), nullable=False),
            sa.Column('staleness_reason', sa.Text(), nullable=True),
            sa.Column('current_case_summary', json_type, server_default='{}', nullable=False),
            sa.Column('historical_case_summary', json_type, server_default='{}', nullable=False),
            sa.Column('parameter_comparisons', json_type, server_default='[]', nullable=False),
            sa.Column('operating_scope_comparisons', json_type, server_default='[]', nullable=False),
            sa.Column('evidence_quality_comparison', json_type, server_default='{}', nullable=False),
            sa.Column('transfer_guardrails', json_type, server_default='{}', nullable=False),
            sa.Column('explanation', json_type, server_default='{}', nullable=False),
            sa.Column('comparison_hash', sa.String(length=64), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

        op.create_index('ix_eng_case_comp_org_id', 'engineering_case_comparisons', ['organization_id'])
        op.create_index('ix_eng_case_comp_team_id', 'engineering_case_comparisons', ['team_id'])
        op.create_index('ix_eng_case_comp_curr_case', 'engineering_case_comparisons', ['current_case_id'])
        op.create_index('ix_eng_case_comp_hist_mem', 'engineering_case_comparisons', ['historical_memory_id'])
        op.create_index('ix_eng_case_comp_hash', 'engineering_case_comparisons', ['comparison_hash'])
        op.create_index('ix_eng_case_comp_app', 'engineering_case_comparisons', ['overall_applicability'])
        op.create_index('ix_eng_case_comp_stale', 'engineering_case_comparisons', ['is_stale'])

    # 2. Enable Row-Level Security on PostgreSQL
    if not is_sqlite:
        tbl = 'engineering_case_comparisons'
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
    insp = sa.inspect(bind)
    existing_tables = insp.get_table_names()

    if 'engineering_case_comparisons' in existing_tables:
        if not is_sqlite:
            op.execute("DROP POLICY IF EXISTS engineering_case_comparisons_tenant_isolation_policy ON engineering_case_comparisons;")
        op.drop_index('ix_eng_case_comp_stale', table_name='engineering_case_comparisons')
        op.drop_index('ix_eng_case_comp_app', table_name='engineering_case_comparisons')
        op.drop_index('ix_eng_case_comp_hash', table_name='engineering_case_comparisons')
        op.drop_index('ix_eng_case_comp_hist_mem', table_name='engineering_case_comparisons')
        op.drop_index('ix_eng_case_comp_curr_case', table_name='engineering_case_comparisons')
        op.drop_index('ix_eng_case_comp_team_id', table_name='engineering_case_comparisons')
        op.drop_index('ix_eng_case_comp_org_id', table_name='engineering_case_comparisons')
        op.drop_table('engineering_case_comparisons')
