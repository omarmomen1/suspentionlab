"""add_fk_indexes

Revision ID: z87a0b1c2d3e
Revises: z86a0b1c2d3e
Create Date: 2026-11-23 00:00:00.000000

Adds missing indexes on foreign key columns across models.
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'z87a0b1c2d3e'
down_revision: Union[str, None] = 'z86a0b1c2d3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEXES = [
    ("teams", "owner_id", "ix_teams_owner_id"),
    ("teams", "organization_id", "ix_teams_organization_id"),
    ("organization_invitations", "team_id", "ix_organization_invitations_team_id"),
    ("organization_invitations", "invited_by_user_id", "ix_organization_invitations_invited_by_user_id"),
    ("organization_invitations", "accepted_by_user_id", "ix_organization_invitations_accepted_by_user_id"),
    ("scim_groups", "team_id", "ix_scim_groups_team_id"),
    ("vehicle_profiles", "parent_id", "ix_vehicle_profiles_parent_id"),
    ("blind_engineering_sessions", "organization_id", "ix_blind_engineering_sessions_organization_id"),
    ("blind_comparison_results", "submission_id", "ix_blind_comparison_results_submission_id"),
    ("solver_exchange_artifacts", "organization_id", "ix_solver_exchange_artifacts_organization_id"),
    ("solver_exchange_operations", "organization_id", "ix_solver_exchange_operations_organization_id"),
    ("solver_exchange_operations", "input_artifact_id", "ix_solver_exchange_operations_input_artifact_id"),
    ("solver_exchange_operations", "output_artifact_id", "ix_solver_exchange_operations_output_artifact_id"),
    ("solver_execution_jobs", "organization_id", "ix_solver_execution_jobs_organization_id"),
    ("solver_execution_jobs", "input_artifact_id", "ix_solver_execution_jobs_input_artifact_id"),
    ("parameter_trust_fleet_reports", "organization_id", "ix_parameter_trust_fleet_reports_organization_id"),
    ("parameter_trust_assembly_impacts", "organization_id", "ix_parameter_trust_assembly_impacts_organization_id"),
    ("decision_parameter_dependencies", "organization_id", "ix_decision_parameter_dependencies_organization_id"),
    ("decision_exposure_assessments", "organization_id", "ix_decision_exposure_assessments_organization_id"),
    ("decision_robustness_analyses", "organization_id", "ix_decision_robustness_analyses_organization_id"),
    ("engineering_validation_plans", "parent_plan_id", "ix_engineering_validation_plans_parent_plan_id"),
    ("engineering_validation_plans", "exposure_assessment_id", "ix_engineering_validation_plans_exposure_assessment_id"),
    ("engineering_validation_plans", "robustness_analysis_id", "ix_engineering_validation_plans_robustness_analysis_id"),
    ("engineering_validation_plans", "criteria_authorized_by_user_id", "ix_engineering_validation_plans_criteria_authorized_by_user_id"),
    ("engineering_validation_plans", "authorized_by_user_id", "ix_engineering_validation_plans_authorized_by_user_id"),
    ("engineering_validation_plans", "organization_id", "ix_engineering_validation_plans_organization_id"),
    ("engineering_validation_plans", "created_by_user_id", "ix_engineering_validation_plans_created_by_user_id"),
    ("validation_evidence_items", "reviewed_by_user_id", "ix_validation_evidence_items_reviewed_by_user_id"),
    ("validation_evidence_items", "source_verification_id", "ix_validation_evidence_items_source_verification_id"),
    ("validation_evidence_items", "organization_id", "ix_validation_evidence_items_organization_id"),
    ("validation_evidence_items", "submitted_by_user_id", "ix_validation_evidence_items_submitted_by_user_id"),
    ("validation_evidence_closures", "superseded_by", "ix_validation_evidence_closures_superseded_by"),
    ("validation_evidence_closures", "organization_id", "ix_validation_evidence_closures_organization_id"),
    ("validation_evidence_closures", "evaluated_by_user_id", "ix_validation_evidence_closures_evaluated_by_user_id"),
    ("validation_decision_reassessments", "original_exposure_assessment_id", "ix_validation_decision_reassessments_orig_exp_id"),
    ("validation_decision_reassessments", "original_robustness_analysis_id", "ix_validation_decision_reassessments_orig_rob_id"),
    ("validation_decision_reassessments", "new_robustness_analysis_id", "ix_validation_decision_reassessments_new_rob_id"),
    ("validation_decision_reassessments", "superseded_by", "ix_validation_decision_reassessments_superseded_by"),
    ("validation_decision_reassessments", "organization_id", "ix_validation_decision_reassessments_organization_id"),
    ("validation_decision_reassessments", "reassessed_by_user_id", "ix_validation_decision_reassessments_reassessed_by_user_id"),
    ("source_verification_records", "verifier_user_id", "ix_source_verification_records_verifier_user_id"),
    ("source_verification_records", "revoked_by_user_id", "ix_source_verification_records_revoked_by_user_id"),
    ("source_verification_records", "organization_id", "ix_source_verification_records_organization_id"),
    ("engineering_decision_dossiers", "parent_dossier_id", "ix_engineering_decision_dossiers_parent_dossier_id"),
    ("engineering_decision_dossiers", "exposure_assessment_id", "ix_engineering_decision_dossiers_exposure_assessment_id"),
    ("engineering_decision_dossiers", "baseline_robustness_analysis_id", "ix_engineering_decision_dossiers_baseline_rob_id"),
    ("engineering_decision_dossiers", "closure_id", "ix_engineering_decision_dossiers_closure_id"),
    ("engineering_decision_dossiers", "reassessment_id", "ix_engineering_decision_dossiers_reassessment_id"),
    ("engineering_decision_dossiers", "reassessed_robustness_analysis_id", "ix_engineering_decision_dossiers_reassessed_rob_id"),
    ("engineering_decision_dossiers", "superseded_by", "ix_engineering_decision_dossiers_superseded_by"),
    ("engineering_decision_dossiers", "organization_id", "ix_engineering_decision_dossiers_organization_id"),
    ("engineering_decision_dossiers", "compiled_by_user_id", "ix_engineering_decision_dossiers_compiled_by_user_id"),
]

def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())
    for table_name, col_name, idx_name in INDEXES:
        if table_name in existing_tables:
            existing_indexes = {idx["name"] for idx in insp.get_indexes(table_name)}
            if idx_name not in existing_indexes:
                try:
                    op.create_index(idx_name, table_name, [col_name], if_not_exists=True)
                except Exception:
                    pass

def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())
    for table_name, _, idx_name in reversed(INDEXES):
        if table_name in existing_tables:
            try:
                op.drop_index(idx_name, table_name=table_name)
            except Exception:
                pass
