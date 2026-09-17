"""
tests/test_secret_linter.py
Automated Regression Test Suite for Secret Fallback Guardrails.

Verifies:
1. AST Linter successfully catches all 7 secret fallback categories (SEC001-SEC007).
2. AST Linter produces zero false positives on benign configurations.
3. AST Linter respects inline suppression pragmas.
4. CLI subprocess invocation returns exit code 1 on violations, 0 on clean code.
5. All source files in src/ pass with zero secret fallback violations (post-hardening).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure repository root is in sys.path for direct module imports
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.lint_secrets import (
    SecretLinter,
    format_report_text,
    main as linter_main,
    scan_directory,
    scan_source_code,
)


class TestSecretVisitorRules:
    """Unit tests validating AST detection for each security rule."""

    def test_sec001_os_getenv_with_default(self):
        code = 'jwt_sec = os.getenv("JWT_SECRET_KEY", "insecure_default_secret")'
        violations = scan_source_code(code)
        assert len(violations) == 1
        assert violations[0]["code"] == "SEC001"
        assert "JWT_SECRET_KEY" in violations[0]["message"]

    def test_sec001_os_getenv_keyword_default(self):
        code = 'token = os.getenv("SCIM_BEARER_TOKEN", default="bearer-fallback")'
        violations = scan_source_code(code)
        assert len(violations) == 1
        assert violations[0]["code"] == "SEC001"

    def test_sec002_os_environ_get_with_default(self):
        code = 'api_key = os.environ.get("API_KEY", "dev_api_key_12345")'
        violations = scan_source_code(code)
        assert len(violations) == 1
        assert violations[0]["code"] == "SEC002"
        assert "API_KEY" in violations[0]["message"]

    def test_sec003_dict_get_with_sensitive_key(self):
        code = 'val = config.get("SECRET_KEY", "default_secret_xyz")'
        violations = scan_source_code(code)
        assert len(violations) == 1
        assert violations[0]["code"] == "SEC003"
        assert "SECRET_KEY" in violations[0]["message"]

    def test_sec004_getattr_with_sensitive_default(self):
        code = 'sec = getattr(settings, "jwt_secret", "fallback_secret_token")'
        violations = scan_source_code(code)
        assert len(violations) == 1
        assert violations[0]["code"] == "SEC004"
        assert "jwt_secret" in violations[0]["message"]

    def test_sec005_boolean_or_fallback_expression(self):
        code = 'token = secret_key or "hardcoded_token_fallback"'
        violations = scan_source_code(code)
        assert any(v["code"] == "SEC005" for v in violations)

    def test_sec005_boolean_or_assignment_target(self):
        code = 'JWT_SECRET = fetch_key() or "default_jwt_secret"'
        violations = scan_source_code(code)
        assert any(v["code"] == "SEC005" for v in violations)

    def test_sec006_pydantic_field_literal_default(self):
        code = """
class AppSettings(BaseSettings):
    api_key: str = "dev_secret_key"
"""
        violations = scan_source_code(code)
        assert len(violations) == 1
        assert violations[0]["code"] == "SEC006"
        assert "api_key" in violations[0]["message"]

    def test_sec006_pydantic_field_call_default(self):
        code = """
class SecurityConfig(BaseModel):
    signing_secret: str = Field(default="dev_signing_key_123")
"""
        violations = scan_source_code(code)
        assert len(violations) == 1
        assert violations[0]["code"] == "SEC006"

    def test_sec007_hardcoded_weak_secret_assignment(self):
        code = 'keys["v1"] = "dev_jwt_secret_key_suspensionlab_2026_dev_mode_only_safe"'
        violations = scan_source_code(code)
        assert any(v["code"] == "SEC007" for v in violations)


class TestBenignPatterns:
    """Negative tests verifying that legitimate code patterns are NOT flagged."""

    def test_os_getenv_non_sensitive_keys(self):
        code = """
port = os.getenv("PORT", "8000")
env = os.getenv("ENVIRONMENT", "DEV")
commit = os.getenv("GIT_COMMIT", "BUILD-REL-2026.1")
rate_limit = os.getenv("RATE_LIMIT_SIMULATE", "300/minute")
"""
        violations = scan_source_code(code)
        assert len(violations) == 0

    def test_os_getenv_without_default(self):
        code = """
# Safe pattern: fetch key without fallback; None returned if absent
secret = os.getenv("JWT_SECRET_KEY")
password = os.environ.get("METRICS_PASSWORD")
"""
        violations = scan_source_code(code)
        assert len(violations) == 0

    def test_pydantic_required_fields(self):
        code = """
class CleanSettings(BaseSettings):
    api_key: str
    signing_key: str = Field(...)
    optional_token: Optional[str] = None
"""
        violations = scan_source_code(code)
        assert len(violations) == 0

    def test_http_request_container_lookups(self):
        code = """
# Getting client request headers or cookies is not a server credential fallback
token = request.cookies.get("sl_token")
auth = request.headers.get("Authorization", "")
anon_id = request.headers.get("X-API-Key", "anonymous")
"""
        violations = scan_source_code(code)
        assert len(violations) == 0

    def test_non_secret_token_words(self):
        code = """
tok = cancel_tok or cancellation_token
idx = sort_key or "default_key"
c_key = cache_key or "entity_cache"
"""
        violations = scan_source_code(code)
        assert len(violations) == 0


class TestInlineSuppression:
    """Verifies suppression directives function correctly."""

    def test_noqa_suppression(self):
        code = 'secret = os.getenv("JWT_SECRET_KEY", "default")  # noqa: SEC001'
        violations = scan_source_code(code)
        assert len(violations) == 0

    def test_pragma_suppression(self):
        code = 'sec = getattr(cfg, "api_key", "test")  # pragma: allow-secret-fallback'
        violations = scan_source_code(code)
        assert len(violations) == 0


class TestCLIExecution:
    """Subprocess integration tests for CLI interface."""

    def test_cli_detects_violation_and_exits_nonzero(self, tmp_path):
        bad_file = tmp_path / "bad_config.py"
        bad_file.write_text(
            'STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_insecure_fallback")\n',
            encoding="utf-8"
        )
        res = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "lint_secrets.py"), str(bad_file)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True
        )
        assert res.returncode == 1
        assert "SEC001" in res.stdout
        assert "STRIPE_WEBHOOK_SECRET" in res.stdout

    def test_cli_json_format_output(self, tmp_path):
        bad_file = tmp_path / "bad_settings.py"
        bad_file.write_text('api_key: str = "dev_secret_key"\n', encoding="utf-8")
        res = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "lint_secrets.py"), str(bad_file), "--format", "json"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True
        )
        assert res.returncode == 1
        payload = json.loads(res.stdout)
        assert payload["clean"] is False
        assert payload["total_violations"] >= 1
        assert payload["violations"][0]["code"] == "SEC006"

    def test_cli_clean_file_exits_zero(self, tmp_path):
        clean_file = tmp_path / "clean_config.py"
        clean_file.write_text(
            'DATABASE_URL = os.getenv("DATABASE_URL")\n'
            'PORT = int(os.getenv("PORT", "8000"))\n',
            encoding="utf-8"
        )
        res = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "lint_secrets.py"), str(clean_file)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True
        )
        assert res.returncode == 0
        assert "SUCCESS" in res.stdout


class TestProjectSourceIntegrity:
    """Ensures that the entire src/ tree complies with strict fail-closed standards."""

    def test_src_contains_zero_secret_fallbacks(self):
        """
        Scans all source code in src/.
        Fails if any secret fallback or hardcoded development secret is present.
        """
        violations, file_count = scan_directory(REPO_ROOT / "src")
        if violations:
            formatted = format_report_text(violations)
            pytest.fail(
                f"Secret fallback regression detected in src/ ({len(violations)} violation(s) across {file_count} files):\n\n"
                f"{formatted}\n\n"
                "Remediation: Remove all hardcoded secret defaults. Require explicit configuration and fail closed."
            )
        assert len(violations) == 0
        assert file_count > 100
