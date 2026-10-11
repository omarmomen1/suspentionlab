import os
import shutil
import fnmatch
from pathlib import Path

EXCLUDE_DIRS = {
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

EXCLUDE_PATTERNS = {
    "*.pem",
    "*.key",
    "*.db",
    "*.db-shm",
    "*.db-wal",
    "*.sqlite*",
    "*.log",
    "*.tmp",
    "*.pyc",
    "*.pyo",
    "*.pyd",
}

def should_exclude(rel_path: Path) -> bool:
    for part in rel_path.parts:
        if part in EXCLUDE_DIRS or part.startswith(".next"):
            return True

    name = rel_path.name
    # Handle .env files: allow .env*.example, exclude all other .env*
    if name.startswith(".env"):
        if not name.endswith(".example"):
            return True

    for pat in EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(name, pat):
            return True

    return False

def copy_with_exclusions(src: Path, dst: Path):
    if src.is_file():
        if not should_exclude(src.relative_to(src.parent)):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return

    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".next")]
        root_path = Path(root)

        for file in files:
            file_path = root_path / file
            rel_file = file_path.relative_to(src.parent if src.is_dir() else src)
            if should_exclude(rel_file):
                continue

            target_path = dst / file_path.relative_to(src)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, target_path)

def main():
    staging_dir = Path('_zip_staging')
    downloads_dir = Path(os.environ.get('USERPROFILE', '.')) / 'Downloads'
    downloads_dir.mkdir(parents=True, exist_ok=True)
    out_zip = downloads_dir / 'SuspensionLab_v1'
    
    # Ensure clean staging directory
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    
    # Specific items to package for audit
    includes = [
        'src',
        'benchmark_mc.py',
        'validate_rk4.py',
        'requirements.txt',
        'project_summary.md',
        'README.md'
    ]
    
    for item in includes:
        p = Path(item)
        if p.exists():
            if p.is_dir():
                copy_with_exclusions(p, staging_dir / item)
            else:
                copy_with_exclusions(p, staging_dir / p.name)
                
    # Create the zip archive
    shutil.make_archive(str(out_zip), 'zip', str(staging_dir))
    print(f"Successfully packaged project to {out_zip}.zip (excluding data/, .env*, *.pem, *.key, *.db)")
    
    # Cleanup staging area
    shutil.rmtree(staging_dir)

if __name__ == '__main__':
    main()
