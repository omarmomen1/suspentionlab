"""phase6_8_decision_release_governance

Revision ID: z9a0b1c2d3e4
Revises: y8z9a0b1c2d3
Create Date: 2026-10-25 06:30:00.000000

Phase 6.8: Engineering Decision Release, Evidence Change Impact & Controlled Governance:
- engineering_decision_releases table
- evidence_change_impacts table
- indexes for tenant isolation, decision lookup, and governance standing
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'z9a0b1c2d3e4'
down_revision: Union[str, None] = 'y8z9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID_TYPE = postgresql.UUID(as_uuid=True).with_variant(sa.Uuid(), 'sqlite')
JSON_TYPE = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite')

GOVERNANCE_RELEASE_SEPARATION_NOTICE = (
    "ENGINEERING DECISION RELEASE NOTICE: This release represents an authorized engineering conclusion "
    "within the specified operational envelope, supported by traceable parameter trust, sealed criteria, "
    "and verified evidence dossiers. This record DOES NOT constitute vehicle roadworthiness, ISO 26262 "
    "functional safety certification, physical vehicle validation, or deployment authorization. "
    "Deployment authorization requires independent statutory sign-off. STRICT NON-ELEVATION POLICY ENFORCED."
)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = insp.get_table_names()

    # 1. engineering_decision_releases
    if 'engineering_decision_releases' not in existing_tables:
        op.create_table(
            'engineering_decision_releases',
            sa.Column('id', UUID_TYPE, primary_key=True),
            sa.Column('release_number', sa.String(length=64), nullable=False, unique=True),
            sa.Column('decision_id', sa.String(length=128), nullable=False),
            sa.Column('decision_revision', sa.Integer(), server_default='1', nullable=False),
            sa.Column('dossier_id', UUID_TYPE, sa.ForeignKey('engineering_decision_dossiers.id', ondelete='RESTRICT'), nullable=False),
            sa.Column('dossier_hash', sa.String(length=64), nullable=False),
            sa.Column('robustness_analysis_id', UUID_TYPE, sa.ForeignKey('decision_robustness_analyses.id', ondelete='SET NULL'), nullable=True),
            sa.Column('robustness_hash', sa.String(length=64), nullable=True),
            sa.Column('validation_criteria_versions', JSON_TYPE, server_default='[]', nullable=False),
            sa.Column('accepted_evidence_items', JSON_TYPE, server_default='[]', nullable=False),
            sa.Column('source_verification_identities', JSON_TYPE, server_default='[]', nullable=False),
            sa.Column('evidence_gap_closure_statuses', JSON_TYPE, server_default='{}', nullable=False),
            sa.Column('operating_conditions', JSON_TYPE, server_default='{}', nullable=False),
            sa.Column('unresolved_limitations', JSON_TYPE, server_default='[]', nullable=False),
            sa.Column('author_id', UUID_TYPE, sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
            sa.Column('author_role', sa.String(length=64), nullable=False),
            sa.Column('reviewer_id', UUID_TYPE, sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('reviewer_role', sa.String(length=64), nullable=True),
            sa.Column('second_reviewer_id', UUID_TYPE, sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('second_reviewer_role', sa.String(length=64), nullable=True),
            sa.Column('consequence_level', sa.String(length=32), server_default='STANDARD', nullable=False),
            sa.Column('release_status', sa.String(length=64), server_default='DRAFT', nullable=False),
            sa.Column('current_standing', sa.String(length=64), server_default='UNDETERMINED', nullable=False),
            sa.Column('current_standing_reason', sa.Text(), nullable=True),
            sa.Column('standing_updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('approval_policy_version', sa.String(length=32), server_default='1.0.0', nullable=False),
            sa.Column('release_timestamp', sa.DateTime(timezone=True), nullable=True),
            sa.Column('canonical_release_hash', sa.String(length=64), nullable=False),
            sa.Column('release_audit_trail', JSON_TYPE, server_default='[]', nullable=False),
            sa.Column('governance_separation_notice', sa.Text(), server_default=GOVERNANCE_RELEASE_SEPARATION_NOTICE, nullable=False),
            sa.Column('deployment_safety_inferred', sa.Boolean(), server_default='false', nullable=False),
            sa.Column('deployment_authorization_status', sa.String(length=32), server_default='NOT_ESTABLISHED', nullable=False),
            sa.Column('iso_26262_functional_safety_inferred', sa.Boolean(), server_default='false', nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
            sa.Column('prior_release_id', UUID_TYPE, sa.ForeignKey('engineering_decision_releases.id', ondelete='SET NULL'), nullable=True),
            sa.Column('superseded_by_id', UUID_TYPE, sa.ForeignKey('engineering_decision_releases.id', ondelete='SET NULL'), nullable=True),
            sa.Column('lineage_depth', sa.Integer(), server_default='0', nullable=False),
            sa.Column('organization_id', UUID_TYPE, sa.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True),
            sa.Column('team_id', UUID_TYPE, sa.ForeignKey('teams.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        )
        op.create_index('ix_release_number', 'engineering_decision_releases', ['release_number'])
        op.create_index('ix_release_decision_id', 'engineering_decision_releases', ['decision_id'])
        op.create_index('ix_release_dossier_id', 'engineering_decision_releases', ['dossier_id'])
        op.create_index('ix_release_status', 'engineering_decision_releases', ['release_status'])
        op.create_index('ix_release_standing', 'engineering_decision_releases', ['current_standing'])
        op.create_index('ix_release_active', 'engineering_decision_releases', ['is_active'])
        op.create_index('ix_release_tenant', 'engineering_decision_releases', ['organization_id', 'team_id'])

    # 2. evidence_change_impacts
    if 'evidence_change_impacts' not in existing_tables:
        op.create_table(
            'evidence_change_impacts',
            sa.Column('id', UUID_TYPE, primary_key=True),
            sa.Column('impact_assessment_number', sa.String(length=64), nullable=False, unique=True),
            sa.Column('release_id', UUID_TYPE, sa.ForeignKey('engineering_decision_releases.id', ondelete='CASCADE'), nullable=False),
            sa.Column('decision_id', sa.String(length=128), nullable=False),
            sa.Column('trigger_type', sa.String(length=64), nullable=False),
            sa.Column('trigger_entity_type', sa.String(length=64), nullable=False),
            sa.Column('trigger_entity_id', sa.String(length=128), nullable=False),
            sa.Column('historical_release_hash', sa.String(length=64), nullable=False),
            sa.Column('previous_evidence_status', sa.String(length=64), nullable=False),
            sa.Column('current_evidence_status', sa.String(length=64), nullable=False),
            sa.Column('impact_classification', sa.String(length=64), nullable=False),
            sa.Column('affected_conclusions_scope', JSON_TYPE, server_default='{}', nullable=False),
            sa.Column('explanation', sa.Text(), nullable=False),
            sa.Column('required_action', sa.String(length=64), nullable=False),
            sa.Column('resulting_standing', sa.String(length=64), nullable=False),
            sa.Column('assessment_hash', sa.String(length=64), nullable=False),
            sa.Column('assessed_by_user_id', UUID_TYPE, sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('organization_id', UUID_TYPE, sa.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True),
            sa.Column('team_id', UUID_TYPE, sa.ForeignKey('teams.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        )
        op.create_index('ix_impact_number', 'evidence_change_impacts', ['impact_assessment_number'])
        op.create_index('ix_impact_release_id', 'evidence_change_impacts', ['release_id'])
        op.create_index('ix_impact_decision_id', 'evidence_change_impacts', ['decision_id'])
        op.create_index('ix_impact_trigger', 'evidence_change_impacts', ['trigger_type', 'trigger_entity_type'])
        op.create_index('ix_impact_classification', 'evidence_change_impacts', ['impact_classification'])
        op.create_index('ix_impact_tenant', 'evidence_change_impacts', ['organization_id', 'team_id'])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = insp.get_table_names()
    if 'evidence_change_impacts' in existing_tables:
        op.drop_table('evidence_change_impacts')
    if 'engineering_decision_releases' in existing_tables:
        op.drop_table('engineering_decision_releases')

