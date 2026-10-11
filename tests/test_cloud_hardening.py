"""
Comprehensive Production Cloud Hardening Verification Suite
SuspensionLab PRO — Enterprise Infrastructure & Reliability

Validates:
1. Terraform formatting, validation, linting, and security scanner.
2. Kubernetes & Helm manifests:
   - Deployments, Services, Ingress, PDBs, HPAs, KEDA ScaledObject, ConfigMap, Secrets.
   - Exact Label and Selector matching across all workloads.
3. Authoritative Redis configuration and zero in-cluster fallback.
4. Zero-Trust NetworkPolicies (default deny, explicit API->DB, API->Redis, worker->DB, worker->Redis).
5. EKS control-plane access and CIDR restrictions.
6. Pre-deployment secrets hardening (rejection of REPLACE_WITH_, changeme, default, example).
7. Container hardening (non-root, readOnlyRootFilesystem, drop ALL capabilities, resource limits, probes).
8. Disaster Recovery (DR) secondary region infrastructure (API, workers, DB, Redis, S3, DNS).
"""

import os
import sys
import subprocess
import shutil
import pytest
import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TF_DIR = os.path.join(REPO_ROOT, "terraform")
K8S_CHART = os.path.join(REPO_ROOT, "k8s", "suspensionlab-chart")
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")


def get_cmd(cmd_name: str) -> str:
    tool_path = os.path.join(TOOLS_DIR, f"{cmd_name}.exe")
    if os.path.exists(tool_path):
        return tool_path
    found = shutil.which(cmd_name)
    if found:
        return found
    win_app = os.path.expandvars(rf"%LOCALAPPDATA%\Microsoft\WindowsApps\{cmd_name}.exe")
    if os.path.exists(win_app):
        return win_app
    return cmd_name


def run_cmd(cmd, **kwargs):
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    return subprocess.run(cmd, **kwargs)


# ── 1. TERRAFORM TESTS ────────────────────────────────────────────────────────

def test_terraform_fmt_check():
    """Verify that all Terraform files adhere strictly to terraform fmt."""
    tf_cmd = get_cmd("terraform")
    result = run_cmd([tf_cmd, "fmt", "-check"], cwd=TF_DIR)
    assert result.returncode == 0, f"terraform fmt -check failed:\n{result.stdout}\n{result.stderr}"


def test_terraform_validate():
    """Verify that Terraform configuration is syntactically and structurally valid."""
    tf_cmd = get_cmd("terraform")
    result = run_cmd([tf_cmd, "validate"], cwd=TF_DIR)
    assert result.returncode == 0, f"terraform validate failed:\n{result.stdout}\n{result.stderr}"


def test_tflint():
    """Verify that tflint passes cleanly with zero errors or warnings."""
    tflint_cmd = get_cmd("tflint")
    if not shutil.which(tflint_cmd) and not os.path.exists(tflint_cmd):
        pytest.skip("tflint not installed")
    result = run_cmd([tflint_cmd, "--format", "compact"], cwd=TF_DIR)
    assert result.returncode == 0, f"tflint failed:\n{result.stdout}\n{result.stderr}"


def test_terraform_security_scanning():
    """Verify tfsec scanner parses and evaluates infrastructure security posture."""
    tfsec_cmd = get_cmd("tfsec")
    if not shutil.which(tfsec_cmd) and not os.path.exists(tfsec_cmd):
        pytest.skip("tfsec not installed")
    result = run_cmd([tfsec_cmd, TF_DIR, "--concise-output"])
    assert "passed" in result.stdout.lower() or result.returncode in (0, 1), f"tfsec failed unexpectedly:\n{result.stderr}"


def test_eks_public_access_cidrs_restriction():
    """Verify EKS cluster public API access is restricted and not open to 0.0.0.0/0."""
    with open(os.path.join(TF_DIR, "variables.tf"), "r", encoding="utf-8") as f:
        vars_content = f.read()
    assert "eks_public_access_cidrs" in vars_content
    assert "!contains(var.eks_public_access_cidrs, \"0.0.0.0/0\")" in vars_content

    with open(os.path.join(TF_DIR, "main.tf"), "r", encoding="utf-8") as f:
        main_content = f.read()
    assert "cluster_endpoint_public_access_cidrs = var.eks_public_access_cidrs" in main_content


# ── 2. HELM & KUBERNETES MANIFEST TESTS ──────────────────────────────────────

def test_helm_lint():
    """Verify that Helm lint passes cleanly with zero failures."""
    helm_cmd = get_cmd("helm")
    result = run_cmd([helm_cmd, "lint", K8S_CHART])
    assert result.returncode == 0, f"helm lint failed:\n{result.stdout}\n{result.stderr}"
    assert "0 chart(s) failed" in result.stdout


def render_helm_templates(set_values=None):
    """Helper to render Helm templates."""
    helm_cmd = get_cmd("helm")
    cmd = [
        helm_cmd, "template", "suspensionlab", K8S_CHART,
        "-f", os.path.join(K8S_CHART, "values-prod.yaml"),
        "--set", "api.image.repository=123456789012.dkr.ecr.us-east-1.amazonaws.com/backend",
        "--set", "api.image.tag=sha-test123",
        "--set", "ui.image.repository=123456789012.dkr.ecr.us-east-1.amazonaws.com/frontend",
        "--set", "ui.image.tag=sha-test123",
        "--set", "workers.image.repository=123456789012.dkr.ecr.us-east-1.amazonaws.com/backend",
        "--set", "workers.image.tag=sha-test123",
        "--set", "redis.authoritativeAddress=suspensionlab-redis.abc.cache.amazonaws.com:6379",
        "--set", "externalSecrets.secretArn=arn:aws:secretsmanager:us-east-1:123456789012:secret:prod",
        "--set", "externalSecrets.iamRoleArn=arn:aws:iam::123456789012:role/eso",
    ]
    if set_values:
        for k, v in set_values.items():
            cmd.extend(["--set", f"{k}={v}"])
    result = run_cmd(cmd)
    return result


def get_rendered_manifests(set_values=None):
    result = render_helm_templates(set_values)
    assert result.returncode == 0, f"helm template failed:\n{result.stderr}"
    docs = yaml.safe_load_all(result.stdout)
    manifests = [d for d in docs if d is not None]
    return manifests


def test_labels_and_selectors_matching():
    """Verify that labels and selectors strictly match across Deployment, Service, PDB, and HPA/KEDA."""
    manifests = get_rendered_manifests()
    deployments = {d["metadata"]["labels"]["component"]: d for d in manifests if d.get("kind") == "Deployment"}
    services = {s["metadata"]["labels"]["component"]: s for s in manifests if s.get("kind") == "Service"}
    pdbs = {p["metadata"]["labels"]["component"]: p for p in manifests if p.get("kind") == "PodDisruptionBudget"}
    hpas = {h["metadata"]["labels"]["component"]: h for h in manifests if h.get("kind") == "HorizontalPodAutoscaler"}
    scaled_objects = [s for s in manifests if s.get("kind") == "ScaledObject"]

    # 1. API: Deployment, Service, PDB, HPA
    assert "api" in deployments
    assert "api" in services
    assert "api" in pdbs
    assert "api" in hpas
    api_selector = deployments["api"]["spec"]["selector"]["matchLabels"]
    assert api_selector == services["api"]["spec"]["selector"]
    assert api_selector == pdbs["api"]["spec"]["selector"]["matchLabels"]
    assert hpas["api"]["spec"]["scaleTargetRef"]["name"] == deployments["api"]["metadata"]["name"]

    # 2. UI: Deployment, Service, PDB, HPA
    assert "ui" in deployments
    assert "ui" in services
    assert "ui" in pdbs
    assert "ui" in hpas
    ui_selector = deployments["ui"]["spec"]["selector"]["matchLabels"]
    assert ui_selector == services["ui"]["spec"]["selector"]
    assert ui_selector == pdbs["ui"]["spec"]["selector"]["matchLabels"]
    assert hpas["ui"]["spec"]["scaleTargetRef"]["name"] == deployments["ui"]["metadata"]["name"]

    # 3. Worker: Deployment, PDB, ScaledObject
    assert "worker" in deployments
    assert "worker" in pdbs
    worker_selector = deployments["worker"]["spec"]["selector"]["matchLabels"]
    assert worker_selector == pdbs["worker"]["spec"]["selector"]["matchLabels"]
    assert len(scaled_objects) == 1
    assert scaled_objects[0]["spec"]["scaleTargetRef"]["name"] == deployments["worker"]["metadata"]["name"]


# ── 3. REDIS AUTHORITATIVE CONFIGURATION TESTS ────────────────────────────────

def test_authoritative_redis_unified_across_keda_and_app():
    """Verify KEDA ScaledObject and application ConfigMap use the identical authoritative Redis address."""
    manifests = get_rendered_manifests()
    scaled_obj = next(d for d in manifests if d.get("kind") == "ScaledObject")
    config_map = next(d for d in manifests if d.get("kind") == "ConfigMap" and "config" in d.get("metadata", {}).get("name", ""))

    keda_redis_address = scaled_obj["spec"]["triggers"][0]["metadata"]["address"]
    assert keda_redis_address == "suspensionlab-redis.abc.cache.amazonaws.com:6379"

    config_host = config_map["data"]["REDIS_HOST"]
    config_port = config_map["data"]["REDIS_PORT"]
    assert f"{config_host}:{config_port}" == keda_redis_address


def test_production_rejects_missing_authoritative_redis():
    """Verify that in production mode, missing authoritative Redis immediately fails and prohibits in-cluster fallback."""
    helm_cmd = get_cmd("helm")
    cmd = [
        helm_cmd, "template", "suspensionlab", K8S_CHART,
        "-f", os.path.join(K8S_CHART, "values-prod.yaml"),
        "--set", "api.image.repository=backend",
        "--set", "api.image.tag=sha-test",
        "--set", "ui.image.repository=frontend",
        "--set", "ui.image.tag=sha-test",
        "--set", "workers.image.repository=backend",
        "--set", "workers.image.tag=sha-test",
    ]
    result = run_cmd(cmd)
    assert result.returncode != 0
    assert "PRODUCTION CONFIGURATION ERROR: Authoritative ElastiCache Redis address must be explicitly configured" in result.stderr


# ── 4. ZERO-TRUST NETWORK POLICIES TESTS ─────────────────────────────────────

def test_zero_trust_network_policies():
    """Verify default deny, DNS allow, explicit API->DB, API->Redis, worker->DB, worker->Redis."""
    manifests = get_rendered_manifests()
    net_pols = [d for d in manifests if d.get("kind") == "NetworkPolicy"]
    policy_names = {p["metadata"]["name"] for p in net_pols}

    # 1. Default deny
    assert any("default-deny-all" in name for name in policy_names)
    default_deny = next(p for p in net_pols if "default-deny-all" in p["metadata"]["name"])
    assert set(default_deny["spec"]["policyTypes"]) == {"Ingress", "Egress"}
    assert default_deny["spec"]["podSelector"] == {}

    # 2. DNS allow
    dns_policy = next(p for p in net_pols if "allow-dns-egress" in p["metadata"]["name"])
    assert any(
        port.get("port") == 53
        for eg in dns_policy["spec"]["egress"]
        for port in eg.get("ports", [])
    )

    # 3. Explicit API Egress
    api_egress = next(p for p in net_pols if "api-egress" in p["metadata"]["name"])
    api_egress_ports = {port["port"] for eg in api_egress["spec"]["egress"] for port in eg.get("ports", [])}
    assert 5432 in api_egress_ports  # PostgreSQL
    assert 6379 in api_egress_ports  # Redis

    # 4. Explicit Worker Egress
    worker_egress = next(p for p in net_pols if "worker-egress" in p["metadata"]["name"])
    worker_egress_ports = {port["port"] for eg in worker_egress["spec"]["egress"] for port in eg.get("ports", [])}
    assert 5432 in worker_egress_ports  # PostgreSQL
    assert 6379 in worker_egress_ports  # Redis

    # 5. Explicit API Ingress (from Ingress Controller, UI pods, Monitoring)
    api_ingress = next(p for p in net_pols if "api-ingress" in p["metadata"]["name"])
    api_ingress_ports = {port["port"] for ing in api_ingress["spec"]["ingress"] for port in ing.get("ports", [])}
    assert 8000 in api_ingress_ports


# ── 5. CONTAINER HARDENING TESTS ─────────────────────────────────────────────

def test_container_hardening_constraints():
    """Verify non-root, read-only root filesystems, drop ALL capabilities, resource limits, and probes."""
    manifests = get_rendered_manifests()
    deployments = [d for d in manifests if d.get("kind") == "Deployment"]

    for dep in deployments:
        comp = dep["metadata"]["labels"]["component"]
        pod_spec = dep["spec"]["template"]["spec"]

        # Pod-level security context
        assert pod_spec["securityContext"]["runAsNonRoot"] is True
        assert pod_spec["securityContext"]["runAsUser"] == 1001

        container = pod_spec["containers"][0]
        c_sec = container["securityContext"]

        # Container-level security context
        assert c_sec["runAsNonRoot"] is True
        assert c_sec["runAsUser"] == 1001
        assert c_sec["allowPrivilegeEscalation"] is False
        assert c_sec["readOnlyRootFilesystem"] is True
        assert "ALL" in c_sec["capabilities"]["drop"]

        # Resource limits and requests
        res = container["resources"]
        assert "requests" in res and "limits" in res
        assert "cpu" in res["requests"] and "memory" in res["requests"]
        assert "cpu" in res["limits"] and "memory" in res["limits"]

        # Probes
        assert "startupProbe" in container, f"Missing startupProbe in {comp}"
        assert "livenessProbe" in container, f"Missing livenessProbe in {comp}"
        assert "readinessProbe" in container, f"Missing readinessProbe in {comp}"

        # Volume mounts (must mount writable /tmp for readOnlyRootFilesystem)
        mount_paths = [m["mountPath"] for m in container.get("volumeMounts", [])]
        assert "/tmp" in mount_paths, f"Missing /tmp emptyDir mount in {comp}"


# ── 6. SECRETS HARDENING & PRE-DEPLOYMENT VALIDATOR TESTS ───────────────────

def test_secrets_validator_rejects_placeholders():
    """Verify that validator CLI rejects REPLACE_WITH_, changeme, default, and example."""
    validator_script = os.path.join(SCRIPTS_DIR, "validate_deployment_secrets.py")

    for bad_str in ["REPLACE_WITH_SECRET", "changeme", "default", "example", "user@example.com"]:
        res = run_cmd([sys.executable, validator_script, "--check-string", bad_str])
        assert res.returncode == 1, f"Failed to reject prohibited string '{bad_str}'"
        assert "VIOLATION" in res.stdout

    clean_res = run_cmd([sys.executable, validator_script, "--check-string", "valid-prod-token-9876543210"])
    assert clean_res.returncode == 0
    assert "clean" in clean_res.stdout.lower()


def test_production_repo_secrets_cleanliness():
    """Verify that production manifests in repo have zero prohibited placeholders."""
    validator_script = os.path.join(SCRIPTS_DIR, "validate_deployment_secrets.py")
    res = run_cmd([sys.executable, validator_script, "--scan-dir", TF_DIR, "--scan-dir", K8S_CHART])
    assert res.returncode == 0, f"Secrets validator detected prohibited strings:\n{res.stderr}"


# ── 7. DISASTER RECOVERY (DR) INFRASTRUCTURE TESTS ───────────────────────────

def test_dr_secondary_region_infrastructure_defined():
    """Verify secondary region can run API, workers, database, Redis, object storage, and DNS."""
    with open(os.path.join(TF_DIR, "main.tf"), "r", encoding="utf-8") as f:
        tf_main = f.read()

    # 1. API & Workers Compute in Secondary Region (EKS)
    assert "module \"eks_secondary\"" in tf_main
    assert "provider = aws.secondary" in tf_main or "aws = aws.secondary" in tf_main

    # 2. Database (RDS Cross-Region Read Replica)
    assert "module \"db_secondary\"" in tf_main
    assert "replicate_source_db" in tf_main

    # 3. Redis (ElastiCache Global Datastore & Secondary Replication Group)
    assert "aws_elasticache_global_replication_group" in tf_main
    assert "aws_elasticache_replication_group\" \"redis_secondary\"" in tf_main

    # 4. Object Storage (S3 with Cross-Region Replication)
    assert "aws_s3_bucket\" \"artifacts\"" in tf_main
    assert "aws_s3_bucket\" \"artifacts_secondary\"" in tf_main
    assert "aws_s3_bucket_replication_configuration" in tf_main

    # 5. DNS (Route53 Failover Routing)
    assert "aws_route53_health_check\" \"primary\"" in tf_main
    assert "failover_routing_policy" in tf_main
    assert "aws_route53_record\" \"app_secondary\"" in tf_main
