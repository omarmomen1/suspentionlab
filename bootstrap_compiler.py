r"""
bootstrap_compiler.py
=====================
SuspensionLab - Kinematics C++ Extension Builder.
Detects MSVC (preferred) or MinGW and builds kinematics_core.pyd.

Run with the Python that has cmake/ninja/pybind11:
    python bootstrap_compiler.py
"""

import subprocess
import sys
import os
import pathlib
import time

PY = sys.executable
NINJA_EXE = None
CMAKE_EXE = None
GCC_EXE = None
GPP_EXE = None

SRC_DIR   = pathlib.Path(__file__).parent / "src" / "kinematics_core"
PHYS_DIR  = pathlib.Path(__file__).parent / "src" / "suspensionlab" / "physics"


# ─────────────────────────────────────────────────────────────────────────────
# Step 0: Install build dependencies
# ─────────────────────────────────────────────────────────────────────────────
def pip_install(*pkgs):
    r = subprocess.run(
        [PY, "-m", "pip", "install", "--quiet", *pkgs],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"  pip install {pkgs} failed:\n{r.stderr.strip()}")
    else:
        print(f"  {', '.join(pkgs)}: OK")


print(f"Python: {PY}")
print(f"Version: {sys.version[:50]}")
print()

print("[1] Installing build tools...")
pip_install("cmake", "ninja", "pybind11", "py7zr")


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Locate cmake and ninja
# ─────────────────────────────────────────────────────────────────────────────
import site

def find_script(name):
    """Find a script installed via pip (in Scripts/ or data/bin/)."""
    scripts_dir = pathlib.Path(PY).parent / "Scripts"
    candidate = scripts_dir / (name + ".exe")
    if candidate.exists():
        return str(candidate)
    for sp in site.getsitepackages():
        for p in pathlib.Path(sp).rglob(f"{name}.exe"):
            return str(p)
    return name  # fallback: hope it's on PATH


CMAKE_EXE = find_script("cmake")
NINJA_EXE = find_script("ninja")
print(f"\n[2] Build tools:")
print(f"    cmake: {CMAKE_EXE}")
print(f"    ninja: {NINJA_EXE}")

# Verify
r = subprocess.run([CMAKE_EXE, "--version"], capture_output=True, text=True)
print(f"    cmake version: {r.stdout.splitlines()[0] if r.stdout else r.stderr.strip()}")
r = subprocess.run([NINJA_EXE, "--version"], capture_output=True, text=True)
print(f"    ninja version: {r.stdout.strip() or r.stderr.strip()}")


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Detect MSVC (preferred) or MinGW
# ─────────────────────────────────────────────────────────────────────────────
print("\n[3] Detecting C++ compiler...")

MSVC_ENV = {}
USE_MSVC = False
MINGW_BIN = None

# Try to find MSVC via vswhere
VSWHERE = pathlib.Path(
    os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
    "Microsoft Visual Studio", "Installer", "vswhere.exe"
)

if VSWHERE.exists():
    r = subprocess.run(
        [str(VSWHERE), "-latest", "-requires",
         "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
         "-property", "installationPath"],
        capture_output=True, text=True
    )
    vs_path = r.stdout.strip()
    if vs_path:
        vcvars = pathlib.Path(vs_path) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
        if vcvars.exists():
            # Extract env vars from vcvars64.bat
            env_cmd = f'"{vcvars}" && set'
            r2 = subprocess.run(env_cmd, shell=True, capture_output=True, text=True)
            for line in r2.stdout.splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    MSVC_ENV[k] = v
            USE_MSVC = True
            print(f"    MSVC found via vswhere: {vs_path}")
        else:
            print(f"    vswhere found VS at {vs_path} but vcvars64.bat missing")
    else:
        print("    vswhere: no VS with VC tools found")
else:
    print(f"    vswhere not found at {VSWHERE}")

# Fall back to MinGW
if not USE_MSVC:
    mingw_candidates = [
        pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "mingw64" / "mingw64" / "bin" / "g++.exe",
        pathlib.Path("C:/mingw64/bin/g++.exe"),
    ]
    for candidate in mingw_candidates:
        if candidate.exists():
            GPP_EXE = str(candidate)
            GCC_EXE = str(candidate.parent / "gcc.exe")
            MINGW_BIN = str(candidate.parent)
            print(f"    MinGW g++ found: {GPP_EXE}")
            r = subprocess.run([GPP_EXE, "--version"], capture_output=True, text=True)
            print(f"    {r.stdout.splitlines()[0] if r.stdout else r.stderr.strip()}")
            print()
            print("    WARNING: MinGW builds .pyd files that are ABI-incompatible with")
            print("             MSVC-built Python (crash on import). Install VS Build Tools")
            print("             for a working build. MinGW build will be skipped.")
            print("    Run: install_msvc_and_build.bat")
            sys.exit(1)
    print("    No C++ compiler found!")
    print()
    print("  To install MSVC (required):")
    print("  1. Double-click: D:\\project\\install_msvc_and_build.bat")
    print("  2. Click YES on the UAC (admin) prompt")
    print("  3. Wait ~5 minutes for install")
    print("  4. Re-run: python bootstrap_compiler.py")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: CMake configure
# ─────────────────────────────────────────────────────────────────────────────
BUILD_DIR = SRC_DIR / "_build_msvc"
BUILD_DIR.mkdir(parents=True, exist_ok=True)

print(f"\n[4] CMake configure (MSVC) -> {BUILD_DIR}")

# Merge MSVC env with current env
env = os.environ.copy()
env.update(MSVC_ENV)

configure_cmd = [
    CMAKE_EXE,
    "-S", str(SRC_DIR),
    "-B", str(BUILD_DIR),
    "-DCMAKE_BUILD_TYPE=Release",
    f"-DCMAKE_MAKE_PROGRAM={NINJA_EXE}",
    f"-DPython_EXECUTABLE={PY}",
    "-G", "Ninja",
]

r = subprocess.run(configure_cmd, env=env, capture_output=True, text=True)
print(r.stdout[-3000:] if r.stdout else "")
if r.returncode != 0:
    print("CONFIGURE FAILED:")
    print(r.stderr[-3000:])
    sys.exit(r.returncode)
print("    Configure: OK")


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: CMake build
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n[5] CMake build...")

build_cmd = [CMAKE_EXE, "--build", str(BUILD_DIR), "--config", "Release", "--parallel"]
r = subprocess.run(build_cmd, env=env, capture_output=True, text=True)
print(r.stdout[-4000:] if r.stdout else "")
if r.returncode != 0:
    print("BUILD FAILED:")
    print(r.stderr[-4000:])
    sys.exit(r.returncode)
print("    Build: OK")


# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Verify
# ─────────────────────────────────────────────────────────────────────────────
built = (
    list(PHYS_DIR.glob("kinematics_core*.pyd")) +
    list(PHYS_DIR.glob("kinematics_core*.so"))
)
if not built:
    built = list(BUILD_DIR.rglob("kinematics_core*.pyd"))

if built:
    print(f"\n[SUCCESS] Extension built:")
    for f in built:
        print(f"    {f}  ({f.stat().st_size / 1e3:.0f} kB)")
else:
    print("\n[WARN] No .pyd found. Check CMake output directory.")

print("\n[6] Verifying Python import...")
verify_script = f"""
import sys, os, pathlib
phys = pathlib.Path(r'{PHYS_DIR}')
if hasattr(os, 'add_dll_directory'):
    os.add_dll_directory(str(phys))
sys.path.insert(0, str(phys))
from suspensionlab.physics.kinematics import solve_kinematics, backend_info, DEFAULT_HARDPOINTS
info = backend_info()
print('Backend:', info['backend'])
print('C++ active:', info['cpp_available'])
curves = solve_kinematics(DEFAULT_HARDPOINTS, z_min_mm=-60, z_max_mm=60, n_steps=25)
d = curves.to_dict()
print(f'Steps: {{len(d["wheel_travel_mm"])}}, all converged: {{all(d["converged"])}}')
print(f'RC at neutral: {{d["roll_center_height_mm"][12]:.1f}} mm')
if info['cpp_available']:
    print('C++ BACKEND ACTIVE - BUILD SUCCESSFUL!')
else:
    print('WARNING: C++ backend not active despite successful build. Check import path.')
"""

r = subprocess.run([PY, "-c", verify_script], capture_output=True, text=True, cwd=str(BUILD_DIR.parent.parent.parent))
print(r.stdout)
if r.stderr:
    print("STDERR:", r.stderr[-2000:])
