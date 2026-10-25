"""
Build and package Phase 7.6 FMUs for both Windows 64-bit and Linux 64-bit.
Generates:
  - ActiveQuarterCarModel.fmu
  - ActiveSuspensionController.fmu
and outputs their SHA-256 hashes.
"""

import os
import sys
import shutil
import zipfile
import hashlib
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def build_model(
    model_name: str,
    src_c: Path,
    xml_path: Path,
    output_fmu: Path,
    mingw_gcc: str = r"C:\Users\omaar\AppData\Local\mingw64\mingw64\bin\gcc.exe"
):
    build_dir = PROJECT_ROOT / "build_fmu_temp" / model_name
    if build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    win64_dir = build_dir / "binaries" / "win64"
    linux64_dir = build_dir / "binaries" / "linux64"
    win64_dir.mkdir(parents=True, exist_ok=True)
    linux64_dir.mkdir(parents=True, exist_ok=True)

    include_dir = PROJECT_ROOT / "src" / "suspensionlab" / "interop" / "fmi" / "include"

    # 1. Compile win64 DLL
    win64_dll = win64_dir / f"{model_name}.dll"
    env = os.environ.copy()
    mingw_bin = str(Path(mingw_gcc).parent)
    env["PATH"] = mingw_bin + os.pathsep + env.get("PATH", "")

    cmd_win = [
        mingw_gcc, "-shared", "-O2", "-fPIC",
        "-Wl,--no-insert-timestamp",
        f"-I{include_dir}",
        str(src_c),
        "-o", str(win64_dll),
        "-lm"
    ]
    res_win = subprocess.run(cmd_win, env=env, capture_output=True, text=True)
    if res_win.returncode != 0:
        raise RuntimeError(f"Win64 compile failed for {model_name}: {res_win.stderr}")

    # 2. Compile linux64 SO via WSL
    linux64_so = linux64_dir / f"{model_name}.so"
    rel_src = src_c.relative_to(PROJECT_ROOT).as_posix()
    rel_out = linux64_so.relative_to(PROJECT_ROOT).as_posix()
    rel_inc = include_dir.relative_to(PROJECT_ROOT).as_posix()

    cmd_wsl = [
        "wsl", "-d", "Ubuntu-24.04", "bash", "-c",
        f"cd /mnt/d/project && gcc -shared -O2 -fPIC -Wl,--build-id=none -I{rel_inc} {rel_src} -o {rel_out} -lm"
    ]
    res_linux = subprocess.run(cmd_wsl, capture_output=True, text=True)
    if res_linux.returncode != 0:
        raise RuntimeError(f"Linux64 compile failed for {model_name}: {res_linux.stderr}")

    # 3. Create FMU archive with deterministic ZipInfo timestamps
    if output_fmu.exists():
        output_fmu.unlink()

    fixed_time = (2026, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(output_fmu, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for file_path, arcname in [
            (xml_path, "modelDescription.xml"),
            (win64_dll, f"binaries/win64/{model_name}.dll"),
            (linux64_so, f"binaries/linux64/{model_name}.so")
        ]:
            data = file_path.read_bytes()
            zinfo = zipfile.ZipInfo(filename=arcname, date_time=fixed_time)
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zinfo.external_attr = 0o755 << 16  # standard executable permissions
            z.writestr(zinfo, data)

    sha = compute_sha256(output_fmu)
    print(f"Created {output_fmu.name}: SHA256={sha}")
    return sha

def main():
    plant_src = PROJECT_ROOT / "src" / "suspensionlab" / "interop" / "models" / "active_quarter_car" / "ActiveQuarterCarModel.c"
    plant_xml = PROJECT_ROOT / "src" / "suspensionlab" / "interop" / "models" / "active_quarter_car" / "modelDescription.xml"
    plant_fmu = PROJECT_ROOT / "ActiveQuarterCarModel.fmu"

    ctrl_src = PROJECT_ROOT / "src" / "suspensionlab" / "interop" / "models" / "active_controller" / "ActiveSuspensionController.c"
    ctrl_xml = PROJECT_ROOT / "src" / "suspensionlab" / "interop" / "models" / "active_controller" / "modelDescription.xml"
    ctrl_fmu = PROJECT_ROOT / "ActiveSuspensionController.fmu"

    print("Building Phase 7.6 FMUs...")
    plant_sha = build_model("ActiveQuarterCarModel", plant_src, plant_xml, plant_fmu)
    ctrl_sha = build_model("ActiveSuspensionController", ctrl_src, ctrl_xml, ctrl_fmu)

    # Clean up test root files if any
    for tmp in [PROJECT_ROOT / "ActiveQuarterCarModel.dll", PROJECT_ROOT / "ActiveSuspensionController.dll",
                PROJECT_ROOT / "ActiveQuarterCarModel.so", PROJECT_ROOT / "ActiveSuspensionController.so"]:
        if tmp.exists():
            tmp.unlink()

    print("\nSummary of Generated FMU Hashes:")
    print(f"ActiveQuarterCarModel.fmu:       {plant_sha}")
    print(f"ActiveSuspensionController.fmu:  {ctrl_sha}")

if __name__ == "__main__":
    main()
