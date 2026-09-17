#!/usr/bin/env python3
"""
tools/lint_secrets.py
Enterprise AST Linter & Regression Guardrail against Secret Fallbacks.

Scans Python source code for insecure secret fallbacks, permissive defaults,
and hardcoded development credentials.

Exit codes:
  0: Clean code (zero violations found)
  1: Insecure secret fallback violations detected
  2: Command-line or syntax parsing error

Usage:
  python tools/lint_secrets.py src/
  python tools/lint_secrets.py src/ --format json
  python tools/lint_secrets.py src/ --verbose
"""

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class SecretLinter:
    """Security AST linter rule engine."""

    SENSITIVE_EXACT: Set[str] = {
        "secret", "api_key", "apikey", "jwt_secret", "jwt_key", "private_key",
        "signing_key", "webhook_secret", "password", "passwd", "auth_token",
        "access_token", "refresh_token", "scim_token", "bearer_token", "hmac_secret",
        "encryption_key", "master_key", "stripe_secret", "gemini_api_key",
        "scim_bearer_token", "oidc_client_secret", "decision_hmac_secret",
        "stripe_webhook_secret",
    }

    SENSITIVE_PREFIXES: Tuple[str, ...] = (
        "secret_", "api_key_", "jwt_", "signing_", "webhook_",
        "private_key_", "hmac_", "auth_key_"
    )

    SENSITIVE_SUFFIXES: Tuple[str, ...] = (
        "_secret", "_api_key", "_key_secret", "_signing_key",
        "_private_key", "_token_secret", "_password", "_passwd"
    )

    SENSITIVE_SUBSTRINGS: Tuple[str, ...] = (
        "secret", "password", "passwd", "credential",
        "private_key", "signing_key", "webhook_secret"
    )

    EXCLUDE_TERMS: Set[str] = {
        "cancellation_token", "tokenizer", "tokenize", "token_count", "token_type",
        "key_name", "sort_key", "cache_key", "dict_key", "primary_key", "foreign_key",
        "kid", "jwt_active_key", "active_kid", "key_file", "key_id", "git_commit",
        "build_id", "environment", "port", "host", "username", "event_type",
        "content_type", "public_key", "public_key_pem", "public_key_hex"
    }

    KNOWN_WEAK_SECRETS: Tuple[str, ...] = (
        "dev_secret", "dev_jwt", "dev_key", "changeme", "suspensionlab-hmac",
        "default_secret", "test_secret", "admin123", "secret123"
    )

    DEFAULT_EXCLUDES: Set[str] = {
        ".git", ".venv", "venv", "__pycache__", "build", "dist",
        "node_modules", ".pytest_cache", ".hypothesis"
    }

    @classmethod
    def is_sensitive(cls, name: Optional[str]) -> bool:
        """Determines whether an identifier represents a sensitive secret/credential."""
        if not name or not isinstance(name, str):
            return False
        norm = name.strip().lower()
        if norm in cls.EXCLUDE_TERMS:
            return False
        if any(norm.endswith(b) for b in ("_match", "_valid", "_verified", "_ok", "_status", "_check", "_result", "_passed", "_success", "_matches")):
            return False
        if any(norm.startswith(b) for b in ("is_", "has_", "verify_", "check_")):
            return False
        for ex in cls.EXCLUDE_TERMS:
            if norm.startswith(ex + "_") or norm.endswith("_" + ex):
                return False
        if norm in cls.SENSITIVE_EXACT:
            return True
        if any(norm.startswith(p) for p in cls.SENSITIVE_PREFIXES):
            return True
        if any(norm.endswith(s) for s in cls.SENSITIVE_SUFFIXES):
            return True
        if any(sub in norm for sub in cls.SENSITIVE_SUBSTRINGS):
            return True
        if ("key" in norm or "token" in norm) and any(
            w in norm for w in ("api", "jwt", "auth", "sign", "secr", "priv", "bearer", "scim", "pass")
        ):
            return True
        return False

    @staticmethod
    def is_none_constant(node: Any) -> bool:
        return isinstance(node, ast.Constant) and node.value is None

    @staticmethod
    def is_ellipsis(node: Any) -> bool:
        return isinstance(node, ast.Constant) and node.value is Ellipsis


class SecretVisitor(ast.NodeVisitor):
    """AST visitor that checks for secret fallback patterns."""

    def __init__(self, filename: str, source_lines: List[str]):
        self.filename = filename
        self.source_lines = source_lines
        self.violations: List[Dict[str, Any]] = []
        self._seen: Set[Tuple[str, int, int, str]] = set()

    def _is_suppressed(self, lineno: int, code: str) -> bool:
        if 1 <= lineno <= len(self.source_lines):
            line = self.source_lines[lineno - 1]
            if "# noqa" in line or "# lint-secrets: ignore" in line or "# pragma: allow-secret-fallback" in line:
                if "# noqa" in line:
                    parts = line.split("# noqa", 1)[1].strip()
                    if not parts or code.lower() in parts.lower():
                        return True
                else:
                    return True
        return False

    def add_violation(self, code: str, node: ast.AST, message: str) -> None:
        lineno = getattr(node, "lineno", 1)
        col_offset = getattr(node, "col_offset", 0)
        dedup_key = (self.filename, lineno, col_offset, code)
        if dedup_key in self._seen:
            return
        self._seen.add(dedup_key)
        if not self._is_suppressed(lineno, code):
            self.violations.append({
                "file": self.filename,
                "line": lineno,
                "col": col_offset,
                "code": code,
                "message": message,
            })

    def visit_Call(self, node: ast.Call) -> None:
        # SEC001: os.getenv(key, default) or getenv(key, default)
        is_getenv = False
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
            and node.func.attr == "getenv"
        ):
            is_getenv = True
        elif isinstance(node.func, ast.Name) and node.func.id == "getenv":
            is_getenv = True

        if is_getenv and node.args:
            key_arg = node.args[0]
            key_name = key_arg.value if isinstance(key_arg, ast.Constant) and isinstance(key_arg.value, str) else ""
            if not key_name and isinstance(key_arg, ast.Name):
                key_name = key_arg.id

            default_val = None
            if len(node.args) >= 2:
                default_val = node.args[1]
            for kw in node.keywords:
                if kw.arg == "default":
                    default_val = kw.value

            if SecretLinter.is_sensitive(key_name) and default_val is not None and not SecretLinter.is_none_constant(default_val):
                self.add_violation(
                    "SEC001", node,
                    f"os.getenv() provides fallback default for sensitive key {key_name!r}"
                )

        # SEC002: os.environ.get(key, default)
        is_environ_get = False
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            val = node.func.value
            if isinstance(val, ast.Attribute) and isinstance(val.value, ast.Name) and val.value.id == "os" and val.attr == "environ":
                is_environ_get = True
            elif isinstance(val, ast.Name) and val.id == "environ":
                is_environ_get = True

        if is_environ_get and node.args:
            key_arg = node.args[0]
            key_name = key_arg.value if isinstance(key_arg, ast.Constant) and isinstance(key_arg.value, str) else ""
            if not key_name and isinstance(key_arg, ast.Name):
                key_name = key_arg.id

            default_val = None
            if len(node.args) >= 2:
                default_val = node.args[1]
            for kw in node.keywords:
                if kw.arg == "default":
                    default_val = kw.value

            if SecretLinter.is_sensitive(key_name) and default_val is not None and not SecretLinter.is_none_constant(default_val):
                self.add_violation(
                    "SEC002", node,
                    f"os.environ.get() provides fallback default for sensitive key {key_name!r}"
                )

        # SEC003: dict.get() for sensitive / SECRET_* keys with default
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and not is_environ_get:
            caller_name = ""
            if isinstance(node.func.value, ast.Name):
                caller_name = node.func.value.id
            elif isinstance(node.func.value, ast.Attribute):
                caller_name = node.func.value.attr

            if caller_name not in ("headers", "cookies", "query_params", "params"):
                if node.args:
                    key_arg = node.args[0]
                    key_name = key_arg.value if isinstance(key_arg, ast.Constant) and isinstance(key_arg.value, str) else ""
                    default_val = None
                    if len(node.args) >= 2:
                        default_val = node.args[1]
                    for kw in node.keywords:
                        if kw.arg == "default":
                            default_val = kw.value

                    if SecretLinter.is_sensitive(key_name) and default_val is not None and not SecretLinter.is_none_constant(default_val):
                        self.add_violation(
                            "SEC003", node,
                            f"dict.get() provides fallback default for sensitive key {key_name!r}"
                        )

        # SEC004: getattr(obj, 'secret_key', default)
        if isinstance(node.func, ast.Name) and node.func.id == "getattr":
            if len(node.args) >= 3:
                attr_arg = node.args[1]
                default_arg = node.args[2]
                attr_name = attr_arg.value if isinstance(attr_arg, ast.Constant) and isinstance(attr_arg.value, str) else ""
                if SecretLinter.is_sensitive(attr_name) and not SecretLinter.is_none_constant(default_arg):
                    self.add_violation(
                        "SEC004", node,
                        f"getattr() provides fallback default for sensitive attribute {attr_name!r}"
                    )

        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        # SEC005: Boolean Or fallback on sensitive secrets (e.g. secret_key or "default")
        if isinstance(node.op, ast.Or):
            for i, val in enumerate(node.values[:-1]):
                is_left_sensitive = False
                if isinstance(val, ast.Name) and SecretLinter.is_sensitive(val.id):
                    is_left_sensitive = True
                elif isinstance(val, ast.Call):
                    if isinstance(val.func, ast.Attribute) and val.func.attr in ("getenv", "get"):
                        if val.args and isinstance(val.args[0], ast.Constant) and SecretLinter.is_sensitive(str(val.args[0].value)):
                            is_left_sensitive = True
                    elif isinstance(val.func, ast.Name) and val.func.id == "getenv":
                        if val.args and isinstance(val.args[0], ast.Constant) and SecretLinter.is_sensitive(str(val.args[0].value)):
                            is_left_sensitive = True

                if is_left_sensitive:
                    right = node.values[i + 1]
                    if not SecretLinter.is_none_constant(right):
                        self.add_violation("SEC005", node, "Boolean Or fallback expression used on sensitive secret")

        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        # SEC006: Pydantic Field default values for sensitive keys
        target_name = ""
        if isinstance(node.target, ast.Name):
            target_name = node.target.id
        elif isinstance(node.target, ast.Attribute):
            target_name = node.target.attr

        if SecretLinter.is_sensitive(target_name) and node.value is not None:
            if (
                isinstance(node.value, ast.Constant)
                and not SecretLinter.is_none_constant(node.value)
                and not SecretLinter.is_ellipsis(node.value)
            ):
                self.add_violation(
                    "SEC006", node,
                    f"Type-annotated field {target_name!r} has hardcoded fallback default value"
                )
            elif isinstance(node.value, ast.Call):
                func = node.value.func
                is_field = (isinstance(func, ast.Name) and func.id == "Field") or (
                    isinstance(func, ast.Attribute) and func.attr == "Field"
                )
                if is_field:
                    has_default = False
                    if node.value.args and not SecretLinter.is_ellipsis(node.value.args[0]) and not SecretLinter.is_none_constant(node.value.args[0]):
                        has_default = True
                    for kw in node.value.keywords:
                        if kw.arg == "default" and not SecretLinter.is_ellipsis(kw.value) and not SecretLinter.is_none_constant(kw.value):
                            has_default = True
                    if has_default:
                        self.add_violation(
                            "SEC006", node,
                            f"Pydantic Field {target_name!r} has hardcoded fallback default value"
                        )

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # SEC005 / SEC007: Assignment of dev secrets or Or fallbacks
        for target in node.targets:
            target_name = ""
            if isinstance(target, ast.Name):
                target_name = target.id
            elif isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
                target_name = str(target.slice.value)

            # SEC007: Check for hardcoded development secrets
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                val_str = node.value.value.lower()
                if any(w in val_str for w in SecretLinter.KNOWN_WEAK_SECRETS):
                    self.add_violation(
                        "SEC007", node,
                        f"Hardcoded insecure/development secret value assigned: {val_str[:25]}..."
                    )

            # SEC005: Assignment to sensitive variable with Or fallback
            if SecretLinter.is_sensitive(target_name) and isinstance(node.value, ast.BoolOp) and isinstance(node.value.op, ast.Or):
                right = node.value.values[-1]
                if not SecretLinter.is_none_constant(right):
                    self.add_violation(
                        "SEC005", node,
                        f"Boolean Or fallback assigned to sensitive variable {target_name!r}"
                    )

        self.generic_visit(node)


def scan_source_code(source: str, filename: str = "<string>") -> List[Dict[str, Any]]:
    """Parses and lints Python source code string for secret fallback violations."""
    source_lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [{
            "file": filename,
            "line": exc.lineno or 1,
            "col": exc.offset or 0,
            "code": "SYNTAX_ERROR",
            "message": f"SyntaxError: {exc.msg}",
        }]
    visitor = SecretVisitor(filename, source_lines)
    visitor.visit(tree)
    return visitor.violations


def scan_file(filepath: Path) -> List[Dict[str, Any]]:
    """Scans a single Python file for violations."""
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return [{
            "file": str(filepath),
            "line": 1,
            "col": 0,
            "code": "IO_ERROR",
            "message": f"Failed to read file: {exc}",
        }]
    return scan_source_code(content, str(filepath))


def scan_directory(
    target: Path,
    exclude_dirs: Optional[Set[str]] = None,
    verbose: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    """Recursively scans a directory for Python files and aggregates violations."""
    if exclude_dirs is None:
        exclude_dirs = SecretLinter.DEFAULT_EXCLUDES

    all_violations: List[Dict[str, Any]] = []
    scanned_files_count = 0

    if target.is_file():
        if target.suffix == ".py":
            scanned_files_count += 1
            all_violations.extend(scan_file(target))
        return all_violations, scanned_files_count

    for root, dirs, files in os.walk(target):
        # Prune excluded directories in-place
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith("_build") and not d.endswith(".egg-info")]

        for file in sorted(files):
            if file.endswith(".py"):
                p = Path(root) / file
                scanned_files_count += 1
                violations = scan_file(p)
                all_violations.extend(violations)
                if verbose and violations:
                    print(f"  [!] {p}: {len(violations)} violation(s)", file=sys.stderr)

    return all_violations, scanned_files_count


def format_report_text(violations: List[Dict[str, Any]]) -> str:
    """Formats violations into standard UNIX linter output."""
    lines = []
    for v in violations:
        lines.append(f"{v['file']}:{v['line']}:{v['col']}: [{v['code']}] {v['message']}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lint_secrets",
        description="Static AST linter detecting fallback secrets and insecure credential defaults."
    )
    parser.add_argument(
        "targets",
        nargs="*",
        default=["src"],
        help="Directories or Python files to scan (default: src/)"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--ignore-dir",
        action="append",
        default=[],
        help="Additional directories to ignore"
    )

    args = parser.parse_args(argv)

    exclude_dirs = set(SecretLinter.DEFAULT_EXCLUDES)
    for ig in args.ignore_dir:
        exclude_dirs.add(ig)

    total_violations: List[Dict[str, Any]] = []
    total_files = 0

    for target_str in args.targets:
        target_path = Path(target_str)
        if not target_path.exists():
            print(f"Error: Target path '{target_str}' does not exist.", file=sys.stderr)
            return 2

        violations, file_count = scan_directory(target_path, exclude_dirs, verbose=args.verbose)
        total_violations.extend(violations)
        total_files += file_count

    if args.format == "json":
        output = {
            "scanned_files": total_files,
            "total_violations": len(total_violations),
            "clean": len(total_violations) == 0,
            "violations": total_violations,
        }
        print(json.dumps(output, indent=2))
    else:
        if total_violations:
            print(format_report_text(total_violations))
            print(f"\nFAILURE: Found {len(total_violations)} secret fallback violation(s) across {total_files} file(s).")
        else:
            print(f"SUCCESS: Scanned {total_files} file(s). Zero secret fallback violations found.")

    return 0 if len(total_violations) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
