"""phase 6.3 fleet trust reports and assembly impact tables

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-10-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'q7r8s9t0u1v2'
down_revision = 'p6q7r8s9t0u1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create parameter_trust_fleet_reports table
    op.create_table(
        'parameter_trust_fleet_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), primary_key=True),
        sa.Column('fleet_id', sa.String(length=128), nullable=False),
        sa.Column('parameter_name', sa.String(length=128), nullable=False),
        sa.Column('canonical_unit', sa.String(length=32), nullable=False, server_default=''),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('policy_version', sa.String(length=32), nullable=False, server_default='FLEET_TRUST_POLICY_V1'),
        sa.Column('report_hash', sa.String(length=64), nullable=False),
        sa.Column('cohort_size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('comparable_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('excluded_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('missing_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('summary_metrics', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('comparable_instances', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('excluded_instances', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('missing_instances', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('conflicts', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('outliers', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('validation_coverage_breakdown', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('trust_state_breakdown', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('provenance_distribution', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    )
    op.create_index('ix_fleet_report_fleet_lookup', 'parameter_trust_fleet_reports', ['team_id', 'fleet_id', 'parameter_name'])
    op.create_index('ix_fleet_report_user_lookup', 'parameter_trust_fleet_reports', ['user_id', 'fleet_id', 'parameter_name'])
    op.create_index('ix_fleet_report_hash', 'parameter_trust_fleet_reports', ['report_hash'])

    # 2. Create parameter_trust_assembly_impacts table
    op.create_table(
        'parameter_trust_assembly_impacts',
        sa.Column('id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), primary_key=True),
        sa.Column('vehicle_id', sa.String(length=128), nullable=False),
        sa.Column('assembly_name', sa.String(length=64), nullable=False),
        sa.Column('component_name', sa.String(length=64), nullable=False),
        sa.Column('parameter_name', sa.String(length=128), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite'), nullable=False),
        sa.Column('policy_version', sa.String(length=32), nullable=False, server_default='SENSITIVITY_PROPAGATION_POLICY_V1'),
        sa.Column('impact_hash', sa.String(length=64), nullable=False),
        sa.Column('direct_trust_state', sa.String(length=32), nullable=False),
        sa.Column('validation_coverage', sa.String(length=32), nullable=False),
        sa.Column('sensitivity_status', sa.String(length=32), nullable=False),
        sa.Column('sensitivity_source', sa.String(length=128), nullable=True),
        sa.Column('sensitivity_unit', sa.String(length=64), nullable=True),
        sa.Column('sensitivity_magnitude', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=True),
        sa.Column('impact_classification', sa.String(length=64), nullable=False),
        sa.Column('downstream_metrics', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('dependency_path', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('evidence_gaps', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    )
    op.create_index('ix_assembly_impact_veh_lookup', 'parameter_trust_assembly_impacts', ['team_id', 'vehicle_id', 'assembly_name', 'parameter_name'])
    op.create_index('ix_assembly_impact_user_lookup', 'parameter_trust_assembly_impacts', ['user_id', 'vehicle_id', 'assembly_name', 'parameter_name'])
    op.create_index('ix_assembly_impact_hash', 'parameter_trust_assembly_impacts', ['impact_hash'])


def downgrade() -> None:
    op.drop_table('parameter_trust_assembly_impacts')
    op.drop_table('parameter_trust_fleet_reports')
