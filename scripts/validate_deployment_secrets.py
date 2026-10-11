"""
Pre-Deployment Secret Hardening Validator
SuspensionLab PRO — Production Cloud Hardening

Strictly validates configurations prior to deployment.
Rejects placeholder strings:
  - REPLACE_WITH_
  - changeme
  - default
  - example
in secret and credential values across Terraform, Helm, Kubernetes, and Environment files.
"""

import os
import sys
import re
import argparse
import yaml
from typing import List, Dict, Tuple, Any

PROHIBITED_PATTERNS = [
    re.compile(r"REPLACE_WITH_", re.IGNORECASE),
    re.compile(r"changeme", re.IGNORECASE),
    re.compile(r"^default$", re.IGNORECASE),
    re.compile(r"^example$", re.IGNORECASE),
    re.compile(r"\bexample\.(com|org|net)\b", re.IGNORECASE),
]

SECRET_FIELD_REGEX = re.compile(
    r"(secret|password|key|token|auth|credential|api_key|webhook)", re.IGNORECASE
)

IGNORE_EXTENSIONS = {".pyc", ".png", ".jpg", ".fmu", ".zip", ".exe", ".o", ".dll", ".so", ".lock"}
IGNORE_DIRS = {".git", ".pytest_cache", "__pycache__", "node_modules", "dist", "build", ".terraform", "venv"}


def is_prohibited_value(val_str: str) -> Tuple[bool, str]:
    if not isinstance(val_str, str):
        return False, ""
    s = val_str.strip()
    if not s:
        return False, ""
    if "REPLACE_WITH_" in s.upper():
        return True, "REPLACE_WITH_"
    if "changeme" in s.lower():
        return True, "changeme"
    if s.lower() in ("default", "example", "changeme", "placeholder"):
        return True, s
    if re.search(r"example\.(com|org|net)", s, re.IGNORECASE):
        return True, "example domain"
    return False, ""


def check_yaml_obj(obj: Any, path: str, file_path: str, violations: List[Dict[str, str]]):
    if isinstance(obj, dict):
        for k, v in obj.items():
            current_path = f"{path}.{k}" if path else str(k)
            if isinstance(v, (dict, list)):
                check_yaml_obj(v, current_path, file_path, violations)
            elif isinstance(v, str):
                if SECRET_FIELD_REGEX.search(str(k)):
                    bad, pattern = is_prohibited_value(v)
                    if bad:
                        violations.append({
                            "file": file_path,
                            "field": current_path,
                            "pattern": pattern,
                            "value": v,
                        })
                else:
                    # Even if not explicitly named secret, check for explicit REPLACE_WITH_ or changeme
                    if "REPLACE_WITH_" in v.upper() or "changeme" in v.lower():
                        violations.append({
                            "file": file_path,
                            "field": current_path,
                            "pattern": "REPLACE_WITH_" if "REPLACE_WITH_" in v.upper() else "changeme",
                            "value": v,
                        })
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            check_yaml_obj(item, f"{path}[{i}]", file_path, violations)


def scan_yaml_file(file_path: str) -> List[Dict[str, str]]:
    violations = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            # Remove Helm templating blocks before yaml parsing if it is a template
            clean_content = re.sub(r"\{\{.*?\}\}", "HELM_TEMPLATE", content, flags=re.DOTALL)
            docs = yaml.safe_load_all(clean_content)
            for doc in docs:
                if doc:
                    check_yaml_obj(doc, "", file_path, violations)
    except Exception:
        # Fallback to line scanner
        violations.extend(scan_text_file(file_path))
    return violations


def scan_text_file(file_path: str) -> List[Dict[str, str]]:
    violations = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line_no, line in enumerate(f, start=1):
                stripped = line.strip()
                # Skip comments and meta-validations
                if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
                    continue
                if "regex(" in stripped or "error_message" in stripped or "validate" in stripped or "contains" in stripped:
                    continue
                if "| default" in stripped:
                    continue

                # Check key-value assignments
                m = re.search(r'([A-Za-z0-9_\-\.]+)\s*[:=]\s*["\']?([^"\'\n\r#]+)["\']?', stripped)
                if m:
                    k, v = m.group(1), m.group(2).strip()
                    if SECRET_FIELD_REGEX.search(k):
                        bad, pattern = is_prohibited_value(v)
                        if bad:
                            violations.append({
                                "file": file_path,
                                "field": f"line {line_no} ({k})",
                                "pattern": pattern,
                                "value": v,
                            })
                    elif "REPLACE_WITH_" in v.upper() or "changeme" in v.lower():
                        violations.append({
                            "file": file_path,
                            "field": f"line {line_no} ({k})",
                            "pattern": "REPLACE_WITH_" if "REPLACE_WITH_" in v.upper() else "changeme",
                            "value": v,
                        })
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
    return violations


def scan_file(file_path: str) -> List[Dict[str, str]]:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in {".yaml", ".yml"}:
        return scan_yaml_file(file_path)
    return scan_text_file(file_path)


def scan_directory(directory: str) -> List[Dict[str, str]]:
    all_violations = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in IGNORE_EXTENSIONS or f.startswith("."):
                continue
            full_path = os.path.join(root, f)
            all_violations.extend(scan_file(full_path))
    return all_violations


def validate_production_secrets(paths: List[str]) -> Tuple[bool, List[Dict[str, str]]]:
    violations = []
    for p in paths:
        if os.path.isfile(p):
            violations.extend(scan_file(p))
        elif os.path.isdir(p):
            violations.extend(scan_directory(p))
    return len(violations) == 0, violations


def main():
    parser = argparse.ArgumentParser(description="Pre-deployment Production Secrets Hardening Validator")
    parser.add_argument("--scan-dir", action="append", help="Directory to scan", default=[])
    parser.add_argument("--file", action="append", help="File to scan", default=[])
    parser.add_argument("--check-string", help="Check single string value for prohibited patterns")
    args = parser.parse_args()

    if args.check_string:
        bad, pattern = is_prohibited_value(args.check_string)
        if bad:
            print(f"VIOLATION: Prohibited pattern '{pattern}' found in value: '{args.check_string}'")
            sys.exit(1)
        print("Value is clean.")
        sys.exit(0)

    targets = args.scan_dir + args.file
    if not targets:
        targets = ["terraform", "k8s"]

    success, violations = validate_production_secrets(targets)
    if not success:
        print("=" * 70, file=sys.stderr)
        print("SECURITY FAILURE: Prohibited placeholder secrets detected!", file=sys.stderr)
        print("Production deployment strictly prohibits REPLACE_WITH_, changeme, default, and example.", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        for v in violations:
            print(f"  [!] {v['file']} -> Field: {v.get('field', 'unknown')} | Matched: {v['pattern']} | Value: {v.get('value', '')}", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        sys.exit(1)
    else:
        print("[SUCCESS] All scanned configurations passed secret hardening validation. Zero prohibited placeholders detected.")
        sys.exit(0)


if __name__ == "__main__":
    main()
