"""
create_audit_zip.py
===================
SuspensionLab PRO — Enterprise Audit Packaging & Integrity Verification Engine.

Packages the complete application source code, configuration, documentation,
test suites, and verification datasets for external technical and compliance audits.
Generates cryptographic SHA-256 checksums for independent audit provenance.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import time
import zipfile
from pathlib import Path


def create_audit_bundle(
    source_dir: str | Path,
    primary_zip_path: str | Path,
    secondary_zip_path: str | Path | None = None,
) -> tuple[Path, str, int, int, int]:
    source_path = Path(source_dir).resolve()
    dest_path = Path(primary_zip_path).resolve()
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Temporary staging zip to avoid reading from or writing to partial zip
    temp_zip_path = dest_path.with_suffix(".tmp.zip")
    if temp_zip_path.exists():
        temp_zip_path.unlink()

    exclude_dirs = {
        "data",
        ".git",
        "node_modules",
        "venv",
        ".venv",
        "build",
        "_build",
        "_build_gcc",
        "CMakeFiles",
        "dist",
        ".pytest_cache",
        ".hypothesis",
        "__pycache__",
        ".agents",
        ".claude",
        "scratch",
        "playwright-report",
        "test-results",
        ".terraform",
        "tools",
        ".next",
    }

    exclude_extensions = {
        ".zip",
        ".tar",
        ".gz",
        ".pyc",
        ".pyo",
        ".pyd",
        ".whl",
        ".so",
        ".dll",
        ".exe",
        ".o",
        ".obj",
        ".log",
        ".tmp",
        ".tsbuildinfo",
        ".pem",
        ".key",
        ".db",
        ".sqlite",
        ".sqlite3",
    }

    exclude_files = {
        ".cf_test.log",
        ".trial_backend.log",
        ".trial_frontend.log",
        ".trial_tunnel.log",
    }

    print(f"[PACKAGER] Scanning {source_path}...")
    file_list: list[tuple[Path, str]] = []
    uncompressed_bytes = 0

    for root, dirs, files in os.walk(source_path):
        # In-place directory filtering — never recurse into excluded directories
        dirs[:] = [
            d
            for d in dirs
            if d not in exclude_dirs
            and d.lower() != "data"
            and not d.startswith(".next")
            and d != ".git"
            and d != "node_modules"
        ]

        for file in files:
            if file in exclude_files:
                continue

            # Exclude real environment and secret files (.env* except .env*.example)
            file_lower = file.lower()
            if (file_lower.startswith(".env") or ".env." in file_lower) and not file_lower.endswith(".example"):
                continue

            file_path = Path(root) / file
            suffix = file_path.suffix.lower()

            if suffix in exclude_extensions:
                continue

            if file.endswith(".zip"):
                continue

            rel_path = file_path.relative_to(source_path)
            rel_str = str(rel_path).replace("\\", "/")

            # Guard against data/ folder leakage regardless of traversal path
            if rel_str.startswith("data/") or "/data/" in rel_str:
                continue

            # Guard against key and certificate leaks
            if rel_str.endswith(".pem") or rel_str.endswith(".key"):
                continue

            file_size = file_path.stat().st_size
            uncompressed_bytes += file_size
            file_list.append((file_path, rel_str))

    file_list.sort(key=lambda x: x[1])
    print(f"[PACKAGER] Found {len(file_list)} audit files ({uncompressed_bytes / (1024*1024):.2f} MB uncompressed).")
    print(f"[PACKAGER] Compressing into {dest_path.name}...")

    t0 = time.time()
    with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
        for idx, (fpath, rstr) in enumerate(file_list, start=1):
            zipf.write(fpath, rstr)
            if idx % 100 == 0 or idx == len(file_list):
                print(f"  [{idx}/{len(file_list)}] Added {rstr}")

    duration = time.time() - t0

    # Atomic replace
    if dest_path.exists():
        dest_path.unlink()
    temp_zip_path.rename(dest_path)

    compressed_bytes = dest_path.stat().st_size
    print(f"[PACKAGER] Packaging completed in {duration:.2f}s.")
    print(f"[PACKAGER] Compressed size: {compressed_bytes / (1024*1024):.2f} MB")

    # Compute SHA-256
    print("[PACKAGER] Computing SHA-256 checksum...")
    hasher = hashlib.sha256()
    with open(dest_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)
    sha256_digest = hasher.hexdigest()
    print(f"[PACKAGER] SHA-256: {sha256_digest}")

    # Write SHA-256 checksum file
    checksum_file = dest_path.with_suffix(".zip.sha256")
    checksum_file.write_text(f"{sha256_digest}  {dest_path.name}\n", encoding="utf-8")
    print(f"[PACKAGER] Wrote checksum manifest: {checksum_file}")

    # Optional secondary copy (e.g. Downloads folder)
    if secondary_zip_path:
        sec_path = Path(secondary_zip_path).resolve()
        sec_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest_path, sec_path)
        sec_sha = sec_path.with_suffix(".zip.sha256")
        sec_sha.write_text(f"{sha256_digest}  {sec_path.name}\n", encoding="utf-8")
        print(f"[PACKAGER] Secondary copy placed at: {sec_path}")

    return dest_path, sha256_digest, len(file_list), uncompressed_bytes, compressed_bytes


if __name__ == "__main__":
    src = Path(r"d:\project")
    dest_local = src / "suspensionlab_audit_bundle.zip"
    dest_downloads = Path(r"C:\Users\omaar\Downloads\suspensionlab_audit_bundle.zip")

    create_audit_bundle(
        source_dir=src,
        primary_zip_path=dest_local,
        secondary_zip_path=dest_downloads,
    )
