"""
enable PostgreSQL Row-Level Security, organizations, and scim_groups

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-09-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'j0e1f2a3b4c5'
down_revision = 'i9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create organizations table
    op.create_table(
        'organizations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(255), nullable=False),
        sa.Column('plan', sa.String(20), server_default='ENTERPRISE', nullable=False),
        sa.Column('billing_customer_id', sa.String(255), nullable=True),
        sa.Column('billing_subscription_id', sa.String(255), nullable=True),
        sa.Column('subscription_status', sa.String(50), server_default='active', nullable=False),
        sa.Column('max_seats', sa.Integer(), server_default='50', nullable=False),
        sa.Column('max_teams', sa.Integer(), server_default='10', nullable=False),
        sa.Column('data_region', sa.String(32), server_default='eu-central', nullable=False),
        sa.Column('data_retention_days', sa.Integer(), server_default='365', nullable=False),
        sa.Column('telemetry_retention_days', sa.Integer(), server_default='90', nullable=False),
        sa.Column('audit_retention_days', sa.Integer(), server_default='2555', nullable=False),
        sa.Column('auto_archive_enabled', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('allowed_auth_providers', sa.String(255), server_default='local,oidc,saml', nullable=False),
        sa.Column('saml_enabled', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('saml_idp_entity_id', sa.String(512), nullable=True),
        sa.Column('saml_idp_sso_url', sa.String(1024), nullable=True),
        sa.Column('saml_idp_x509_cert', sa.Text(), nullable=True),
        sa.Column('saml_sp_entity_id', sa.String(512), nullable=True),
        sa.Column('scim_enabled', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('scim_token_prefix', sa.String(32), nullable=True),
        sa.Column('scim_token_hash', sa.String(255), nullable=True),
        sa.Column('scim_token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_orgs_slug', 'organizations', ['slug'], unique=True)
    op.create_index('ix_orgs_billing_customer', 'organizations', ['billing_customer_id'])

    # 2. Add organization_id to teams
    with op.batch_alter_table('teams', schema=None) as batch_op:
        batch_op.add_column(sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True))
        batch_op.create_foreign_key('fk_teams_organization', 'organizations', ['organization_id'], ['id'], ondelete='CASCADE')

    # 3. Add organization_id and org_role to users
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column('org_role', sa.String(32), server_default='MEMBER', nullable=True))
        batch_op.create_foreign_key('fk_users_organization', 'organizations', ['organization_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_users_organization_id', ['organization_id'])

    # 4. Add organization_id to audit_logs and engineering_audit_logs
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True))
        batch_op.create_foreign_key('fk_audit_logs_organization', 'organizations', ['organization_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_audit_logs_org_ts', ['organization_id', 'timestamp'])

    with op.batch_alter_table('engineering_audit_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True))
        batch_op.create_foreign_key('fk_eng_audit_organization', 'organizations', ['organization_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_eng_audit_org_ts', ['organization_id', 'created_at'])

    # 5. Create scim_groups and scim_group_members tables
    op.create_table(
        'scim_groups',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('external_id', sa.String(255), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('target_role', sa.String(50), server_default='Engineer', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_scim_groups_org_display', 'scim_groups', ['organization_id', 'display_name'], unique=True)

    op.create_table(
        'scim_group_members',
        sa.Column('group_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['group_id'], ['scim_groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('group_id', 'user_id'),
    )

    # 6. Apply PostgreSQL Row-Level Security if running on PostgreSQL engine
    bind = op.get_bind()
    if bind and "postgres" in bind.dialect.name:
        from suspensionlab.backend.database.rls import TENANT_TABLES, generate_table_rls_sql
        res = bind.execute(sa.text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
        existing_tables = {row[0] for row in res}
        for table in TENANT_TABLES:
            if table in existing_tables:
                for stmt in generate_table_rls_sql(table):
                    op.execute(sa.text(stmt))


def downgrade() -> None:
    op.drop_table('scim_group_members')
    op.drop_table('scim_groups')

    with op.batch_alter_table('engineering_audit_logs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_eng_audit_organization', type_='foreignkey')
        batch_op.drop_index('ix_eng_audit_org_ts')
        batch_op.drop_column('organization_id')

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_audit_logs_organization', type_='foreignkey')
        batch_op.drop_index('ix_audit_logs_org_ts')
        batch_op.drop_column('organization_id')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_organization', type_='foreignkey')
        batch_op.drop_index('ix_users_organization_id')
        batch_op.drop_column('org_role')
        batch_op.drop_column('organization_id')

    with op.batch_alter_table('teams', schema=None) as batch_op:
        batch_op.drop_constraint('fk_teams_organization', type_='foreignkey')
        batch_op.drop_column('organization_id')

    op.drop_index('ix_orgs_billing_customer', table_name='organizations')
    op.drop_index('ix_orgs_slug', table_name='organizations')
    op.drop_table('organizations')
