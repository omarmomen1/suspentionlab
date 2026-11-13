"""phase8_1_engineering_memory

Revision ID: z81a0b1c2d3e
Revises: z76a0b1c2d3e
Create Date: 2026-10-25 06:45:00.000000

Phase 8.1: Engineering Memory Foundation, Canonical Case Records & Historical Evidence Indexing:
- engineering_memory_records table (durable, tenant-isolated canonical memory snapshots)
- engineering_memory_source_links table (granular evidence provenance links with verification standing)
- engineering_memory_index_entries table (tenant-scoped grounded knowledge search index)
- GIN full-text search indexes on PostgreSQL
- Row-Level Security policies for enterprise tenant isolation
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'z81a0b1c2d3e'
down_revision: Union[str, None] = 'z76a0b1c2d3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    insp = sa.inspect(bind)

    # Dialect-aware types
    json_type = sa.JSON() if is_sqlite else postgresql.JSONB()
    uuid_type = sa.Uuid() if is_sqlite else postgresql.UUID(as_uuid=True)
    tsvector_type = sa.Text() if is_sqlite else postgresql.TSVECTOR()

    existing_tables = insp.get_table_names()

    # 1. Create engineering_memory_records table
    if 'engineering_memory_records' not in existing_tables:
        op.create_table(
            'engineering_memory_records',
            sa.Column('id', uuid_type, primary_key=True),
            sa.Column('organization_id', uuid_type, nullable=False),
            sa.Column('team_id', uuid_type, nullable=True),
            sa.Column('created_by_user_id', uuid_type, nullable=True),
            sa.Column('source_case_id', sa.String(length=128), nullable=False),
            sa.Column('source_entity_type', sa.String(length=64), nullable=False),
            sa.Column('memory_type', sa.String(length=64), server_default='ENGINEERING_CASE_MEMORY', nullable=False),
            sa.Column('schema_version', sa.String(length=32), server_default='1.0.0', nullable=False),
            sa.Column('reconstruction_policy_version', sa.String(length=32), server_default='MEM_REC_V1', nullable=False),
            sa.Column('engineering_domain', sa.String(length=64), nullable=False),
            sa.Column('title', sa.String(length=255), nullable=False),
            sa.Column('problem_statement', sa.Text(), nullable=True),
            sa.Column('decision_outcome', sa.String(length=64), server_default='PENDING', nullable=False),
            sa.Column('validation_status', sa.String(length=64), server_default='OUTCOME_NOT_OBSERVED', nullable=False),
            sa.Column('observed_subsequent_outcome', sa.Text(), server_default='OUTCOME_NOT_OBSERVED', nullable=False),
            sa.Column('source_validity_status', sa.String(length=64), server_default='VALID', nullable=False),
            sa.Column('canonical_content_hash', sa.String(length=64), nullable=False),
            sa.Column('source_snapshot_identity', json_type, server_default='{}', nullable=False),
            sa.Column('canonical_payload', json_type, server_default='{}', nullable=False),
            sa.Column('source_event_occurred_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('is_current_snapshot', sa.Boolean(), server_default=sa.text('1' if is_sqlite else 'true'), nullable=False),
            sa.Column('supersedes_memory_id', uuid_type, sa.ForeignKey('engineering_memory_records.id', ondelete='SET NULL'), nullable=True),
            sa.Column('superseded_by_memory_id', uuid_type, sa.ForeignKey('engineering_memory_records.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        )

        op.create_index('ix_eng_mem_org_id', 'engineering_memory_records', ['organization_id'])
        op.create_index('ix_eng_mem_team_id', 'engineering_memory_records', ['team_id'])
        op.create_index('ix_eng_mem_source_case_id', 'engineering_memory_records', ['source_case_id'])
        op.create_index('ix_eng_mem_domain', 'engineering_memory_records', ['engineering_domain'])
        op.create_index('ix_eng_mem_type', 'engineering_memory_records', ['memory_type'])
        op.create_index('ix_eng_mem_content_hash', 'engineering_memory_records', ['canonical_content_hash'])
        op.create_index('ix_eng_mem_is_current', 'engineering_memory_records', ['is_current_snapshot'])
        op.create_index('ix_eng_mem_org_current', 'engineering_memory_records', ['organization_id', 'is_current_snapshot'])

    # 2. Create engineering_memory_source_links table
    if 'engineering_memory_source_links' not in existing_tables:
        op.create_table(
            'engineering_memory_source_links',
            sa.Column('id', uuid_type, primary_key=True),
            sa.Column('memory_record_id', uuid_type, sa.ForeignKey('engineering_memory_records.id', ondelete='CASCADE'), nullable=False),
            sa.Column('organization_id', uuid_type, nullable=False),
            sa.Column('source_type', sa.String(length=64), nullable=False),
            sa.Column('source_id', sa.String(length=128), nullable=False),
            sa.Column('relationship', sa.String(length=64), nullable=False),
            sa.Column('source_artifact_hash', sa.String(length=64), nullable=True),
            sa.Column('is_verified', sa.Boolean(), server_default=sa.text('0' if is_sqlite else 'false'), nullable=False),
            sa.Column('is_revoked', sa.Boolean(), server_default=sa.text('0' if is_sqlite else 'false'), nullable=False),
            sa.Column('source_event_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('link_metadata', json_type, server_default='{}', nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

        op.create_index('ix_eng_mem_link_mem_id', 'engineering_memory_source_links', ['memory_record_id'])
        op.create_index('ix_eng_mem_link_org_id', 'engineering_memory_source_links', ['organization_id'])
        op.create_index('ix_eng_mem_link_source', 'engineering_memory_source_links', ['source_type', 'source_id'])
        op.create_index('ix_eng_mem_link_rel', 'engineering_memory_source_links', ['relationship'])

    # 3. Create engineering_memory_index_entries table
    if 'engineering_memory_index_entries' not in existing_tables:
        op.create_table(
            'engineering_memory_index_entries',
            sa.Column('id', uuid_type, primary_key=True),
            sa.Column('memory_record_id', uuid_type, sa.ForeignKey('engineering_memory_records.id', ondelete='CASCADE'), nullable=False),
            sa.Column('organization_id', uuid_type, nullable=False),
            sa.Column('team_id', uuid_type, nullable=True),
            sa.Column('field_name', sa.String(length=64), nullable=False),
            sa.Column('token_content', sa.Text(), nullable=False),
            sa.Column('source_type', sa.String(length=64), nullable=False),
            sa.Column('source_id', sa.String(length=128), nullable=False),
            sa.Column('search_vector', tsvector_type, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

        op.create_index('ix_eng_mem_idx_mem_id', 'engineering_memory_index_entries', ['memory_record_id'])
        op.create_index('ix_eng_mem_idx_org_id', 'engineering_memory_index_entries', ['organization_id'])
        op.create_index('ix_eng_mem_idx_team_id', 'engineering_memory_index_entries', ['team_id'])
        op.create_index('ix_eng_mem_idx_field', 'engineering_memory_index_entries', ['field_name'])

        if not is_sqlite:
            # PostgreSQL full-text search GIN index
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_eng_mem_idx_search_vector 
                ON engineering_memory_index_entries USING GIN (search_vector);
            """)

    # 4. Enable Row-Level Security on PostgreSQL
    if not is_sqlite:
        for tbl in ['engineering_memory_records', 'engineering_memory_source_links', 'engineering_memory_index_entries']:
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

    # Drop in reverse foreign key order
    if 'engineering_memory_index_entries' in existing_tables:
        if not is_sqlite:
            op.execute("DROP POLICY IF EXISTS engineering_memory_index_entries_tenant_isolation_policy ON engineering_memory_index_entries;")
            op.execute("DROP INDEX IF EXISTS ix_eng_mem_idx_search_vector;")
        op.drop_index('ix_eng_mem_idx_field', table_name='engineering_memory_index_entries')
        op.drop_index('ix_eng_mem_idx_team_id', table_name='engineering_memory_index_entries')
        op.drop_index('ix_eng_mem_idx_org_id', table_name='engineering_memory_index_entries')
        op.drop_index('ix_eng_mem_idx_mem_id', table_name='engineering_memory_index_entries')
        op.drop_table('engineering_memory_index_entries')

    if 'engineering_memory_source_links' in existing_tables:
        if not is_sqlite:
            op.execute("DROP POLICY IF EXISTS engineering_memory_source_links_tenant_isolation_policy ON engineering_memory_source_links;")
        op.drop_index('ix_eng_mem_link_rel', table_name='engineering_memory_source_links')
        op.drop_index('ix_eng_mem_link_source', table_name='engineering_memory_source_links')
        op.drop_index('ix_eng_mem_link_org_id', table_name='engineering_memory_source_links')
        op.drop_index('ix_eng_mem_link_mem_id', table_name='engineering_memory_source_links')
        op.drop_table('engineering_memory_source_links')

    if 'engineering_memory_records' in existing_tables:
        if not is_sqlite:
            op.execute("DROP POLICY IF EXISTS engineering_memory_records_tenant_isolation_policy ON engineering_memory_records;")
        op.drop_index('ix_eng_mem_org_current', table_name='engineering_memory_records')
        op.drop_index('ix_eng_mem_is_current', table_name='engineering_memory_records')
        op.drop_index('ix_eng_mem_content_hash', table_name='engineering_memory_records')
        op.drop_index('ix_eng_mem_type', table_name='engineering_memory_records')
        op.drop_index('ix_eng_mem_domain', table_name='engineering_memory_records')
        op.drop_index('ix_eng_mem_source_case_id', table_name='engineering_memory_records')
        op.drop_index('ix_eng_mem_team_id', table_name='engineering_memory_records')
        op.drop_index('ix_eng_mem_org_id', table_name='engineering_memory_records')
        op.drop_table('engineering_memory_records')
