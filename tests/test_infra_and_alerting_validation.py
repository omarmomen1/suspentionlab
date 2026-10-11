"""
tests/test_infra_and_alerting_validation.py
===========================================
Tests for Infrastructure, Kubernetes PDB and KEDA selectors, and Alerting validation (Findings 51-59).
"""

import os
import pytest
import yaml

from suspensionlab.backend.observability import validate_alerting_configuration


def test_alerting_configuration_validation(monkeypatch):
    # 1. In dev with alerts disabled -> valid
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("ENABLE_EXTERNAL_ALERTS", "false")
    status = validate_alerting_configuration(raise_on_error=False)
    assert status["is_valid"]

    # 2. In prod with empty credentials -> invalid
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ENABLE_EXTERNAL_ALERTS", "true")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
    monkeypatch.setenv("PAGERDUTY_ROUTING_KEY", "")
    status_prod_bad = validate_alerting_configuration(raise_on_error=False)
    assert not status_prod_bad["is_valid"]
    assert len(status_prod_bad["errors"]) > 0

    # 3. In prod with valid credentials -> valid
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T00/B00/X00REAL")
    status_prod_good = validate_alerting_configuration(raise_on_error=False)
    assert status_prod_good["is_valid"]


def test_k8s_worker_deployment_and_pdb_selector_match():
    # Read worker deployment and extract matchLabels
    with open("k8s/suspensionlab-chart/templates/workers/deployment.yaml", "r", encoding="utf-8") as f:
        deploy_content = f.read()
    
    # Read worker PDB and extract matchLabels
    with open("k8s/suspensionlab-chart/templates/workers/pdb.yaml", "r", encoding="utf-8") as f:
        pdb_content = f.read()

    import re
    deploy_match = re.search(r"selector:\s+matchLabels:\s+app:\s*(\S+)\s+component:\s*(\S+)", deploy_content)
    pdb_match = re.search(r"selector:\s+matchLabels:\s+app:\s*(\S+)\s+component:\s*(\S+)", pdb_content)

    assert deploy_match is not None, "Deployment selector matchLabels not found"
    assert pdb_match is not None, "PDB selector matchLabels not found"
    assert deploy_match.group(1) == pdb_match.group(1) == "suspensionlab"
    assert deploy_match.group(2) == pdb_match.group(2) == "worker"



def test_frontend_package_json_scripts_and_dependencies():
    import json
    with open("frontend/package.json", "r", encoding="utf-8") as f:
        pkg = json.load(f)
    
    required_scripts = ["dev", "build", "type-check", "lint", "test"]
    for script_name in required_scripts:
        assert script_name in pkg.get("scripts", {}), f"Missing '{script_name}' in frontend scripts"
    
    assert "vitest" in pkg.get("devDependencies", {})
    assert "typescript" in pkg.get("devDependencies", {})



def test_validate_production_configuration(monkeypatch):
    from suspensionlab.backend.observability import validate_production_configuration
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@db:5432/suspensionlab")
    monkeypatch.setenv("SECRET_KEY", "REPLACE_WITH_ACTUAL_SECRET")
    
    res_bad = validate_production_configuration(raise_on_error=False)
    assert not res_bad["is_valid"]
    assert any("SECRET_KEY" in err for err in res_bad["errors"])

    monkeypatch.setenv("SECRET_KEY", "7b689a9f4c32b508f7d6a5991823901b")
    res_good = validate_production_configuration(raise_on_error=False)
    assert res_good["is_valid"]


def test_engineering_data_classification_policies():
    """Verify data classification export & sharing policies (Finding 86)."""
    from suspensionlab.backend.security.permissions import (
        DataClassification,
        can_share_externally,
        can_export_artifact,
    )

    # Public artifacts can be shared and exported
    assert can_share_externally(DataClassification.PUBLIC)
    assert can_export_artifact(DataClassification.PUBLIC, "engineer")

    # Confidential artifacts cannot be shared externally
    assert not can_share_externally(DataClassification.CONFIDENTIAL)
    assert can_export_artifact(DataClassification.CONFIDENTIAL, "engineer")
    assert not can_export_artifact(DataClassification.CONFIDENTIAL, "viewer")

    # Restricted artifacts (e.g. F1 tire models / aero maps) cannot be exported by standard engineers
    assert not can_share_externally(DataClassification.RESTRICTED)
    assert not can_export_artifact(DataClassification.RESTRICTED, "engineer")
    assert not can_export_artifact(DataClassification.RESTRICTED, "viewer")
    assert can_export_artifact(DataClassification.RESTRICTED, "owner")
    assert can_export_artifact(DataClassification.RESTRICTED, "super_admin")


def test_keda_scaledobject_redis_trigger_and_tls():
    """Verify KEDA ScaledObject correctly monitors production Redis with TLS and queue target."""
    with open("k8s/suspensionlab-chart/templates/workers/scaledobject.yaml", "r", encoding="utf-8") as f:
        content = f.read()

    assert "type: redis" in content
    assert "enableTLS" in content
    assert "listName:" in content
    assert "listLength:" in content
    assert "{{ .Release.Namespace }}" in content


def test_network_policy_egress_allows_vpc_cidr():
    """Verify NetworkPolicy allows egress to VPC CIDR 10.0.0.0/16 for RDS (5432) and Redis (6379)."""
    with open("k8s/suspensionlab-chart/templates/networkpolicy.yaml", "r", encoding="utf-8") as f:
        content = f.read()

    assert "10.0.0.0/16" in content
    assert "5432" in content
    assert "6379" in content
    assert "{{ .Release.Namespace }}" in content


def test_api_and_ui_deployments_probes_and_security_context():
    """Verify API and UI deployments contain liveness, readiness, and startup probes with non-root security context."""
    with open("k8s/suspensionlab-chart/templates/api/deployment.yaml", "r", encoding="utf-8") as f:
        api_deploy = f.read()
    with open("k8s/suspensionlab-chart/templates/ui/deployment.yaml", "r", encoding="utf-8") as f:
        ui_deploy = f.read()

    # API probes & security
    assert "startupProbe:" in api_deploy
    assert "livenessProbe:" in api_deploy
    assert "readinessProbe:" in api_deploy
    assert "runAsNonRoot: true" in api_deploy
    assert "seccompProfile:" in api_deploy

    # UI probes & security
    assert "startupProbe:" in ui_deploy
    assert "livenessProbe:" in ui_deploy
    assert "readinessProbe:" in ui_deploy
    assert "runAsNonRoot: true" in ui_deploy
    assert "seccompProfile:" in ui_deploy


def test_api_service_port_named_http_for_servicemonitor():
    """Verify API service exposes named port 'http' to match ServiceMonitor."""
    with open("k8s/suspensionlab-chart/templates/api/service.yaml", "r", encoding="utf-8") as f:
        svc_content = f.read()
    with open("k8s/suspensionlab-chart/templates/monitoring/servicemonitor.yaml", "r", encoding="utf-8") as f:
        sm_content = f.read()

    assert "name: http" in svc_content
    assert "port: http" in sm_content


def test_ui_hpa_template_exists_and_valid():
    """Verify UI HorizontalPodAutoscaler template exists and matches configuration."""
    assert os.path.exists("k8s/suspensionlab-chart/templates/ui/hpa.yaml")
    with open("k8s/suspensionlab-chart/templates/ui/hpa.yaml", "r", encoding="utf-8") as f:
        content = f.read()

    assert "kind: HorizontalPodAutoscaler" in content
    assert "{{ .Release.Name }}-ui-hpa" in content
    assert "Deployment" in content


def test_sweeper_cronjob_has_secrets_and_resources():
    """Verify Sweeper CronJob mounts secrets, specifies resources, and sets concurrencyPolicy: Forbid."""
    with open("k8s/suspensionlab-chart/templates/cron/sweeper-cronjob.yaml", "r", encoding="utf-8") as f:
        content = f.read()

    assert "secretRef:" in content
    assert "concurrencyPolicy: Forbid" in content
    assert "resources:" in content
    assert "runAsNonRoot: true" in content


def test_worker_pdb_uses_max_unavailable():
    """Verify Worker PDB uses maxUnavailable: 1 to prevent deadlock during scale-to-zero."""
    with open("k8s/suspensionlab-chart/templates/workers/pdb.yaml", "r", encoding="utf-8") as f:
        content = f.read()

    assert "maxUnavailable: 1" in content
    assert "minAvailable" not in content


def test_dockerfiles_non_root_multistage_exec_cmd():
    """Verify root Dockerfile and Dockerfile.backend use multi-stage, non-root USER, and exec CMD."""
    for df_path in ["Dockerfile", "Dockerfile.backend"]:
        with open(df_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "AS builder" in content
        assert "USER appuser" in content
        assert 'CMD ["python", "-m", "uvicorn"' in content
        assert "ENV PYTHONUNBUFFERED=1" in content


def test_terraform_secondary_eks_and_ecr_replication():
    """Verify Terraform configuration includes secondary EKS pilot light and ECR cross-region replication."""
    with open("terraform/main.tf", "r", encoding="utf-8") as f:
        content = f.read()

    assert "aws_ecr_replication_configuration" in content
    assert "module \"eks_secondary\"" in content
    assert "cluster_endpoint_public_access" in content
    assert "auth_token_enabled" not in content



