"""add evidence graph edges

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'm3n4o5p6q7r8'
down_revision = 'l2m3n4o5p6q7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create evidence_graph_edges table
    op.create_table(
        'evidence_graph_edges',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_type', sa.String(length=64), nullable=False),
        sa.Column('source_id', sa.String(length=128), nullable=False),
        sa.Column('relationship', sa.String(length=64), nullable=False),
        sa.Column('target_type', sa.String(length=64), nullable=False),
        sa.Column('target_id', sa.String(length=128), nullable=False),
        sa.Column('source_artifact_hash', sa.String(length=64), nullable=True),
        sa.Column('target_artifact_hash', sa.String(length=64), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('edge_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('team_id', 'source_type', 'source_id', 'relationship', 'target_type', 'target_id', name='uq_evidence_graph_edge'),
    )

    # 2. Traversal and audit indices
    op.create_index('ix_edges_source', 'evidence_graph_edges', ['team_id', 'source_type', 'source_id'])
    op.create_index('ix_edges_target', 'evidence_graph_edges', ['team_id', 'target_type', 'target_id'])
    op.create_index('ix_edges_rel', 'evidence_graph_edges', ['team_id', 'relationship'])
    op.create_index('ix_edges_user', 'evidence_graph_edges', ['created_by_user_id'])
    op.create_index('ix_edges_org', 'evidence_graph_edges', ['organization_id'])
    op.create_index('ix_edges_edge_hash', 'evidence_graph_edges', ['edge_hash'])
    op.create_index('ix_edges_created_at', 'evidence_graph_edges', ['created_at'])

    # 3. Apply PostgreSQL Row-Level Security if running on PostgreSQL engine
    bind = op.get_bind()
    if bind and "postgres" in bind.dialect.name:
        from suspensionlab.backend.database.rls import generate_table_rls_sql
        for stmt in generate_table_rls_sql('evidence_graph_edges'):
            op.execute(sa.text(stmt))


def downgrade() -> None:
    op.drop_index('ix_edges_created_at', table_name='evidence_graph_edges')
    op.drop_index('ix_edges_edge_hash', table_name='evidence_graph_edges')
    op.drop_index('ix_edges_org', table_name='evidence_graph_edges')
    op.drop_index('ix_edges_user', table_name='evidence_graph_edges')
    op.drop_index('ix_edges_rel', table_name='evidence_graph_edges')
    op.drop_index('ix_edges_target', table_name='evidence_graph_edges')
    op.drop_index('ix_edges_source', table_name='evidence_graph_edges')
    op.drop_table('evidence_graph_edges')
