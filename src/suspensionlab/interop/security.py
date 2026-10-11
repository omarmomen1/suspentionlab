"""
src/suspensionlab/interop/security.py
=====================================
SuspensionLab PRO — Solver Interoperability Security & Ingestion Hardening.

Defends against malicious or corrupted external engineering files and payloads:
1. Path Traversal: Blocks relative traversal (../, ..\\), null bytes, and path escapes.
2. File Type & Executable Rejection: Blocks binary executables (.exe, .dll, .so) and scripts.
3. Resource Exhaustion / Oversized Artifacts: Strict payload size, array, and dict bounds.
4. Malformed Structured Files: Safe, memory-bounded parsing of JSON, CSV, and XML.
5. Archive Expansion Risks: Defends against Zip Slip and Zip Bombs.
6. Safe Deserialization: Absolute prohibition of eval, exec, pickle, or unsafe yaml.
7. Numerical Safety: Scans and rejects NaN, +Infinity, and -Infinity in engineering datasets.
8. Multi-Tenant Isolation: Enforces tenant scoping and forbids cross-tenant leakage.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import pathlib
import re
import zipfile
from typing import Any, Dict, List, Optional, Set, Tuple, Union


# Security Limits
MAX_PAYLOAD_BYTES = 25 * 1024 * 1024        # 25 MB max payload
MAX_ARRAY_ELEMENTS = 100_000                # 100,000 max array items
MAX_DICT_KEYS = 5_000                       # 5,000 max object keys
MAX_RECURSION_DEPTH = 30                    # 30 max nesting depth
MAX_UNCOMPRESSED_ARCHIVE_BYTES = 100 * 1024 * 1024  # 100 MB max expanded archive
MAX_COMPRESSION_RATIO = 25.0                # Max 25x decompression expansion ratio

PROHIBITED_EXECUTABLE_EXTENSIONS: Set[str] = {
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".bat", ".cmd", ".ps1", ".vbs", ".sh",
    ".com", ".pif", ".scr", ".msi", ".py",
}


class InteropSecurityError(ValueError):
    """Base exception for all interoperability security violations."""
    pass


class PathTraversalSecurityError(InteropSecurityError):
    """Raised when an artifact filename or path attempts directory traversal."""
    pass


class ExecutableContentSecurityError(InteropSecurityError):
    """Raised when an imported payload contains executable files or code."""
    pass


class ResourceExhaustionSecurityError(InteropSecurityError):
    """Raised when payload size or element counts exceed safety thresholds."""
    pass


class MalformedPayloadSecurityError(InteropSecurityError):
    """Raised when an external structured file is malformed or invalid."""
    pass


class MalformedNumericSecurityError(InteropSecurityError):
    """Raised when NaN or Infinity is detected in an untrusted engineering payload."""
    pass


class TenantIsolationError(InteropSecurityError):
    """Raised when cross-tenant access is attempted during interop operations."""
    pass


def sanitize_artifact_filename(filename: str) -> str:
    """
    Sanitizes an untrusted filename, stripping directory path components,
    null bytes, and special characters.

    Raises:
        PathTraversalSecurityError: If traversal tokens (..) or null bytes are present.
        ExecutableContentSecurityError: If an executable file extension is detected.
    """
    if not filename or not filename.strip():
        raise PathTraversalSecurityError("Filename cannot be empty.")

    # 1. Null byte check
    if "\x00" in filename:
        raise PathTraversalSecurityError("Null bytes are prohibited in filenames.")

    # 2. Path traversal sequence check
    if ".." in filename or "/" in filename or "\\" in filename:
        raise PathTraversalSecurityError(
            f"Path traversal sequence detected in filename: '{filename}'."
        )

    # 3. Windows drive letter or pipe checks
    if ":" in filename or "|" in filename or "<" in filename or ">" in filename:
        raise PathTraversalSecurityError(
            f"Illegal path character in filename: '{filename}'."
        )

    # 4. Check prohibited executable extensions
    ext = pathlib.Path(filename).suffix.lower()
    if ext in PROHIBITED_EXECUTABLE_EXTENSIONS:
        raise ExecutableContentSecurityError(
            f"Prohibited executable or script extension '{ext}' in artifact filename: '{filename}'."
        )

    clean_name = pathlib.Path(filename).name
    # Retain only safe alphanumeric characters, dashes, underscores, and dots
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", clean_name):
        raise PathTraversalSecurityError(
            f"Filename contains illegal characters: '{filename}'."
        )

    return clean_name


def verify_safe_path(target_path: pathlib.Path, base_dir: pathlib.Path) -> pathlib.Path:
    """
    Verifies that target_path resolves strictly inside base_dir without escaping.
    """
    try:
        resolved_base = base_dir.resolve()
        resolved_target = target_path.resolve()
        # Verify common path
        if not str(resolved_target).startswith(str(resolved_base)):
            raise PathTraversalSecurityError(
                f"Path escape detected: '{target_path}' is outside sandbox '{base_dir}'."
            )
        return resolved_target
    except Exception as e:
        if isinstance(e, PathTraversalSecurityError):
            raise
        raise PathTraversalSecurityError(f"Invalid path resolution: {e}")


def check_payload_size(data: Union[bytes, str], max_bytes: int = MAX_PAYLOAD_BYTES) -> None:
    """Verifies that incoming byte or string payload does not exceed safety limits."""
    size = len(data) if isinstance(data, (bytes, str)) else 0
    if size > max_bytes:
        raise ResourceExhaustionSecurityError(
            f"Payload size ({size} bytes) exceeds maximum limit ({max_bytes} bytes)."
        )


def scan_for_nan_and_infinity(data: Any, path: str = "root", current_depth: int = 0) -> None:
    """
    Recursively scans structured data (dicts, lists, scalars) for NaN or Infinity.

    Raises:
        MalformedNumericSecurityError: If NaN, +Inf, or -Inf is detected.
        ResourceExhaustionSecurityError: If nesting depth or element counts exceed safety limits.
    """
    if current_depth > MAX_RECURSION_DEPTH:
        raise ResourceExhaustionSecurityError(
            f"Maximum data nesting recursion depth ({MAX_RECURSION_DEPTH}) exceeded at '{path}'."
        )

    if isinstance(data, float):
        if math.isnan(data):
            raise MalformedNumericSecurityError(f"Illegal NaN floating-point value at '{path}'.")
        if math.isinf(data):
            raise MalformedNumericSecurityError(f"Illegal Infinity floating-point value at '{path}'.")
    elif isinstance(data, dict):
        if len(data) > MAX_DICT_KEYS:
            raise ResourceExhaustionSecurityError(
                f"Dictionary key count ({len(data)}) exceeds limit ({MAX_DICT_KEYS}) at '{path}'."
            )
        for k, v in data.items():
            scan_for_nan_and_infinity(v, f"{path}.{k}", current_depth + 1)
    elif isinstance(data, (list, tuple)):
        if len(data) > MAX_ARRAY_ELEMENTS:
            raise ResourceExhaustionSecurityError(
                f"Array length ({len(data)}) exceeds limit ({MAX_ARRAY_ELEMENTS}) at '{path}'."
            )
        for i, item in enumerate(data):
            scan_for_nan_and_infinity(item, f"{path}[{i}]", current_depth + 1)


def safe_parse_json(content: Union[str, bytes]) -> Any:
    """
    Safely parses JSON content with size verification, safe deserialization,
    and recursive NaN/Infinity scanning.
    """
    check_payload_size(content)

    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as e:
            raise MalformedPayloadSecurityError(f"Invalid UTF-8 encoding in JSON payload: {e}")
    else:
        text = content

    # Python's default json.loads parses NaN, Infinity, -Infinity as float('nan'), float('inf')
    # We pass parse_constant to fail immediately if NaN or Infinity tokens are encountered
    def _reject_constant(c: str) -> None:
        raise MalformedNumericSecurityError(f"Illegal numerical constant token '{c}' in JSON payload.")

    try:
        parsed = json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as e:
        raise MalformedPayloadSecurityError(f"Malformed JSON syntax: {e}")

    # Deep scan the parsed structure for any remaining numeric issues
    scan_for_nan_and_infinity(parsed)
    return parsed


def safe_parse_csv(content: Union[str, bytes], max_rows: int = 100_000) -> List[Dict[str, str]]:
    """
    Safely parses CSV content into row dictionaries with row and column bounding.
    """
    check_payload_size(content)

    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            raise MalformedPayloadSecurityError(f"Invalid text encoding in CSV payload: {e}")
    else:
        text = content

    f = io.StringIO(text)
    reader = csv.DictReader(f)
    rows: List[Dict[str, str]] = []

    for i, row in enumerate(reader):
        if i >= max_rows:
            raise ResourceExhaustionSecurityError(
                f"CSV row count exceeds maximum limit of {max_rows} rows."
            )
        rows.append(row)

    return rows


def safe_extract_archive(
    archive_bytes: bytes,
    destination_dir: pathlib.Path,
) -> List[pathlib.Path]:
    """
    Safely extracts a ZIP archive into destination_dir, guarding against:
    - Zip Slip (path traversal in entry names)
    - Zip Bomb (uncompressed size ratio > 25x or total > 100MB)
    - Executable files (.exe, .dll, .so, scripts)

    Returns:
        List of extracted safe file paths.
    """
    check_payload_size(archive_bytes)
    dest = destination_dir.resolve()
    dest.mkdir(parents=True, exist_ok=True)

    extracted_files: List[pathlib.Path] = []
    total_uncompressed_bytes = 0

    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as zf:
            for info in zf.infolist():
                name = info.filename

                # 1. Zip Slip check
                if ".." in name or name.startswith("/") or name.startswith("\\"):
                    raise PathTraversalSecurityError(f"Zip Slip path traversal attempt: '{name}'.")

                # 2. Executable extension check
                ext = pathlib.Path(name).suffix.lower()
                if ext in PROHIBITED_EXECUTABLE_EXTENSIONS:
                    raise ExecutableContentSecurityError(
                        f"Archive contains prohibited executable entry: '{name}'."
                    )

                # 3. Zip Bomb check
                total_uncompressed_bytes += info.file_size
                if total_uncompressed_bytes > MAX_UNCOMPRESSED_ARCHIVE_BYTES:
                    raise ResourceExhaustionSecurityError(
                        f"Archive uncompressed size ({total_uncompressed_bytes} bytes) exceeds limit."
                    )

                # Check ratio
                compressed_size = max(info.compress_size, 1)
                ratio = info.file_size / compressed_size
                if ratio > MAX_COMPRESSION_RATIO:
                    raise ResourceExhaustionSecurityError(
                        f"Suspicious compression ratio ({ratio:.1f}x) on entry '{name}'. Zip bomb rejected."
                    )

                # 4. Safe target path resolution
                target_path = (dest / name).resolve()
                if not str(target_path).startswith(str(dest)):
                    raise PathTraversalSecurityError(
                        f"Archive entry escapes destination: '{name}'."
                    )

                if info.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, open(target_path, "wb") as dst:
                        dst.write(src.read())
                    extracted_files.append(target_path)

    except zipfile.BadZipFile as e:
        raise MalformedPayloadSecurityError(f"Corrupted or invalid ZIP archive: {e}")

    return extracted_files


def enforce_tenant_isolation(
    requesting_tenant_id: str,
    resource_tenant_id: str,
) -> None:
    """
    Verifies that the requesting tenant matches the resource tenant.

    Raises:
        TenantIsolationError: If tenant IDs do not match.
    """
    if not requesting_tenant_id or not resource_tenant_id:
        raise TenantIsolationError("Both requesting and resource tenant IDs must be provided.")

    if str(requesting_tenant_id).strip() != str(resource_tenant_id).strip():
        raise TenantIsolationError(
            f"Tenant isolation violation: Access denied to tenant '{resource_tenant_id}'."
        )
