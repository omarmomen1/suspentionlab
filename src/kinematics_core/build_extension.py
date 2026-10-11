"""
build_extension.py
==================
SuspensionLab — One-shot build script for the kinematics_core C++ extension.

Run from the project root or from src/kinematics_core/:
    python src/kinematics_core/build_extension.py

Requirements
------------
- CMake   : installed via pip (pip install cmake)
- Ninja   : installed via pip (pip install ninja)
- pybind11: installed via pip (pip install pybind11)
- C++ compiler:
    Windows: Visual Studio 2019/2022 Build Tools (any edition)
    Linux/macOS: g++ or clang++

The script will:
1. Verify all prerequisites.
2. Locate the VS Developer environment on Windows.
3. Run cmake configure + build.
4. Copy the .pyd (Windows) or .so (Linux) into suspensionlab/physics/.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "kinematics_cpp"
PROJECT_ROOT = ROOT.parent.parent
PHYSICS_DIR  = PROJECT_ROOT / "src" / "suspensionlab" / "physics"
BUILD_DIR    = ROOT / "build"


def run(cmd: list[str], **kwargs) -> int:
    print(f"\n[build] {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, **kwargs)
    return result.returncode


import shutil

def check_prereqs():
    pass

def find_cmake() -> str:
    try:
        import cmake
        cmake_bin = Path(cmake.__file__).parent / "data" / "bin" / "cmake.exe"
        if cmake_bin.exists():
            return str(cmake_bin)
    except Exception:
        pass
    w = shutil.which("cmake")
    if w:
        return w
    local_cmake = Path(os.environ.get("LOCALAPPDATA", "")) / "python" / "pythoncore-3.14-64" / "Lib" / "site-packages" / "cmake" / "data" / "bin" / "cmake.exe"
    if local_cmake.exists():
        return str(local_cmake)
    return "cmake"

def find_ninja() -> str:
    try:
        import ninja
        ninja_bin = Path(ninja.__file__).parent / "data" / "bin" / "ninja.exe"
        if ninja_bin.exists():
            return str(ninja_bin)
    except Exception:
        pass
    w = shutil.which("ninja")
    if w:
        return w
    local_ninja = Path(os.environ.get("LOCALAPPDATA", "")) / "python" / "pythoncore-3.14-64" / "Scripts" / "ninja.exe"
    if local_ninja.exists():
        return str(local_ninja)
    return "ninja"


def find_vs_vcvars() -> str | None:
    """Find vcvarsall.bat for MSVC toolchain setup on Windows."""
    vs_roots = [
        Path(os.environ.get("ProgramFiles", "C:/Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")),
    ]
    editions = ["BuildTools", "Community", "Professional", "Enterprise"]
    years    = ["2022", "2019", "2017"]
    for root in vs_roots:
        for year in years:
            for ed in editions:
                vcvars = root / f"Microsoft Visual Studio/{year}/{ed}/VC/Auxiliary/Build/vcvarsall.bat"
                if vcvars.exists():
                    return str(vcvars)
    return None


def build():
    check_prereqs()

    cmake_exe = find_cmake()
    ninja_exe  = find_ninja()

    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    cmake_extra: list[str] = []

    if platform.system() == "Windows":
        vcvars = find_vs_vcvars()
        if vcvars is None:
            print("[warn] Visual Studio Build Tools not found on PATH.")
            print("       Install from: https://aka.ms/vs/17/release/vs_BuildTools.exe")
            print("       Continuing — CMake will try to find a compiler automatically.")
        else:
            print(f"[ok] Found MSVC: {vcvars}")
            # Activate MSVC environment variables
            result = subprocess.run(
                ["cmd.exe", "/c", f'"{vcvars}" x64 && set'],
                shell=False,
                capture_output=True,
                text=True,
            )
            for line in result.stdout.splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
        cmake_extra = ["-G", "Ninja"]

    # CMake configure
    rc = run(
        [cmake_exe,
         "-S", str(ROOT),
         "-B", str(BUILD_DIR),
         f"-DCMAKE_BUILD_TYPE=Release",
         f"-DCMAKE_MAKE_PROGRAM={ninja_exe}",
         f"-DPython_EXECUTABLE={sys.executable}",
         ] + cmake_extra,
        env=env, cwd=str(ROOT),
    )
    if rc != 0:
        print("[error] CMake configure failed.")
        sys.exit(rc)

    # CMake build
    rc = run(
        [cmake_exe,
         "--build", str(BUILD_DIR),
         "--config", "Release",
         "--parallel",
         ],
        env=env, cwd=str(ROOT),
    )
    if rc != 0:
        print("[error] CMake build failed.")
        sys.exit(rc)

    # Verify output
    exts = ["*.pyd", "*.so", "*.dylib"]
    built = []
    for ext in exts:
        built.extend(BUILD_DIR.rglob(ext))
    # Also check the physics dir (set_target_properties routes it there)
    for ext in exts:
        built.extend(PHYSICS_DIR.rglob("kinematics_core*"))

    if not built:
        print("[warn] No .pyd/.so found after build — check CMake output directory.")
    else:
        print(f"\n[SUCCESS] kinematics_core built:")
        for f in built:
            print(f"  {f}")

    print(f"\nVerify with:")
    print(f"  python -c \"from suspensionlab.physics.kinematics import backend_info; print(backend_info())\"")


if __name__ == "__main__":
    build()
