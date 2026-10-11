"""add blind engineering tables

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'n4o5p6q7r8s9'
down_revision = 'm3n4o5p6q7r8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create blind_engineering_sessions table
    op.create_table(
        'blind_engineering_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='DRAFT'),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('root_entity_type', sa.String(length=64), nullable=False),
        sa.Column('root_entity_id', sa.String(length=128), nullable=False),
        sa.Column('hidden_outcome_type', sa.String(length=64), nullable=False),
        sa.Column('hidden_outcome_id', sa.String(length=128), nullable=False),
        sa.Column('configuration', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('session_hash', sa.String(length=64), nullable=False),
        sa.Column('visible_context_hash', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revealed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('aborted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
    )

    op.create_index('ix_blind_sessions_team_created', 'blind_engineering_sessions', ['team_id', 'created_at'])
    op.create_index('ix_blind_sessions_user_created', 'blind_engineering_sessions', ['created_by_user_id', 'created_at'])
    op.create_index('ix_blind_sessions_status', 'blind_engineering_sessions', ['status'])
    op.create_index('ix_blind_sessions_session_hash', 'blind_engineering_sessions', ['session_hash'])

    # 2. Create blind_submissions table
    op.create_table(
        'blind_submissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('submitted_by_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('submission_payload', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=False),
        sa.Column('submission_hash', sa.String(length=64), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='LOCKED'),
        sa.ForeignKeyConstraint(['session_id'], ['blind_engineering_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['submitted_by_user_id'], ['users.id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('session_id', name='uq_blind_session_submission'),
    )

    op.create_index('ix_blind_submissions_sess_user', 'blind_submissions', ['session_id', 'submitted_by_user_id'])
    op.create_index('ix_blind_submissions_hash', 'blind_submissions', ['submission_hash'])

    # 3. Apply PostgreSQL Row-Level Security if running on PostgreSQL engine
    bind = op.get_bind()
    if bind and "postgres" in bind.dialect.name:
        from suspensionlab.backend.database.rls import generate_table_rls_sql
        for stmt in generate_table_rls_sql('blind_engineering_sessions'):
            op.execute(sa.text(stmt))
        for stmt in generate_table_rls_sql('blind_submissions'):
            op.execute(sa.text(stmt))


def downgrade() -> None:
    op.drop_index('ix_blind_submissions_hash', table_name='blind_submissions')
    op.drop_index('ix_blind_submissions_sess_user', table_name='blind_submissions')
    op.drop_table('blind_submissions')

    op.drop_index('ix_blind_sessions_session_hash', table_name='blind_engineering_sessions')
    op.drop_index('ix_blind_sessions_status', table_name='blind_engineering_sessions')
    op.drop_index('ix_blind_sessions_user_created', table_name='blind_engineering_sessions')
    op.drop_index('ix_blind_sessions_team_created', table_name='blind_engineering_sessions')
    op.drop_table('blind_engineering_sessions')
