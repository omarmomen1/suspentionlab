"""
physics/fmi_builder.py
======================
SuspensionLab PRO — FMI 2.0 Build & Packaging Automation Pipeline.

Orchestrates cross-platform compilation of the FMI 2.0 Co-Simulation C kernel:
- Windows x64 DLL (binaries/win64/QuarterCarRideModel.dll)
- Linux x64 SO (binaries/linux64/QuarterCarRideModel.so)
- Linux ARM64 SO (binaries/linux-arm64/QuarterCarRideModel.so)

Generates:
- Standard modelDescription.xml
- Canonical FMI documentation (documentation/index.html)
- Packaged model.fmu / QuarterCarRideModel.fmu archive
"""

from __future__ import annotations

import os
import sys
import shutil
import zipfile
import pathlib
import datetime
import subprocess
from typing import Dict, Optional, Tuple

from suspensionlab.physics.fmi_exporter import create_quarter_car_fmi_description

FMI_DIR = pathlib.Path(__file__).parent / "fmi"
SRC_C = FMI_DIR / "src" / "QuarterCarRideModel.c"
INC_DIR = FMI_DIR / "include"


def find_c_compiler() -> Tuple[str, str]:
    """
    Locate a C compiler capable of building shared libraries.
    Prefers zig cc (hermetic cross-compiler), then clang/gcc, then msvc.
    Returns (compiler_exe, compiler_type).
    """
    # 1. Check ziglang in python environment
    try:
        import ziglang
        zig_pkg = pathlib.Path(ziglang.__file__).parent
        zig_exe = zig_pkg / ("zig.exe" if sys.platform == "win32" else "zig")
        if zig_exe.exists():
            return str(zig_exe), "zig"
    except ImportError:
        pass

    # 2. Check zig on PATH
    zig_path = shutil.which("zig")
    if zig_path:
        return zig_path, "zig"

    # 3. Check clang
    clang_path = shutil.which("clang")
    if clang_path:
        return clang_path, "clang"

    # 4. Check gcc
    gcc_path = shutil.which("gcc")
    if gcc_path:
        return gcc_path, "gcc"

    # 5. Check cl.exe (MSVC)
    cl_path = shutil.which("cl")
    if cl_path:
        return cl_path, "msvc"

    raise RuntimeError(
        "No suitable C compiler found for FMI binary build. "
        "Install ziglang (`pip install ziglang`), LLVM/Clang, GCC, or MSVC."
    )


def compile_binary(
    target_platform: str,
    output_file: pathlib.Path,
    compiler_exe: Optional[str] = None,
    compiler_type: Optional[str] = None,
) -> pathlib.Path:
    """
    Compile QuarterCarRideModel into a shared library for target_platform.
    target_platform: 'win64', 'linux64', or 'linux-arm64'
    """
    if compiler_exe is None or compiler_type is None:
        compiler_exe, compiler_type = find_c_compiler()

    output_file.parent.mkdir(parents=True, exist_ok=True)

    if compiler_type == "zig":
        target_map = {
            "win64": "x86_64-windows",
            "linux64": "x86_64-linux-gnu",
            "linux-arm64": "aarch64-linux-gnu",
            "linuxaarch64": "aarch64-linux-gnu",
        }
        zig_target = target_map.get(target_platform)
        if not zig_target:
            raise ValueError(f"Unsupported target platform for zig: {target_platform}")

        cmd = [
            compiler_exe, "cc",
            "-target", zig_target,
            "-shared",
            "-O2",
            f"-I{INC_DIR}",
            str(SRC_C),
            "-o", str(output_file),
        ]
        if "linux" in target_platform:
            cmd.insert(4, "-fPIC")

        res = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(
                f"Failed to compile FMI binary for {target_platform}:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
            )
        return output_file

    elif compiler_type in ("clang", "gcc"):
        # Native or configured cross-compiler
        cmd = [
            compiler_exe,
            "-shared",
            "-O2",
            "-fPIC",
            f"-I{INC_DIR}",
            str(SRC_C),
            "-o", str(output_file),
        ]
        res = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(
                f"Failed to compile with {compiler_type}:\n{res.stderr}"
            )
        return output_file

    else:
        raise NotImplementedError(f"Compiler {compiler_type} not yet implemented for cross-target.")


def generate_fmi_documentation(model_name: str = "QuarterCarRideModel") -> str:
    """Generate canonical HTML documentation for the FMU package."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{model_name} — FMI 2.0 Co-Simulation Documentation</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 40px; color: #24292e; line-height: 1.6; }}
    h1, h2, h3 {{ color: #0366d6; }}
    table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
    th, td {{ border: 1px solid #e1e4e8; padding: 8px 12px; text-align: left; }}
    th {{ background-color: #f6f8fa; }}
    code {{ background-color: #f6f8fa; padding: 2px 4px; border-radius: 3px; font-family: Consolas, monospace; }}
    .badge {{ display: inline-block; padding: 4px 8px; font-size: 12px; font-weight: 600; border-radius: 4px; background-color: #28a745; color: white; }}
  </style>
</head>
<body>
  <h1>{model_name} <span class="badge">FMI 2.0 Co-Simulation</span></h1>
  <p><strong>Generated by:</strong> SuspensionLab PRO Industrial CAE Suite</p>
  <p><strong>Generation Date:</strong> {timestamp}</p>
  <p><strong>FMI Standard:</strong> Functional Mock-up Interface 2.0 for Co-Simulation</p>
  <p><strong>Model GUID:</strong> <code>{{8c3f4e21-9a7b-4d61-b531-ec72f0941ab2}}</code></p>

  <h2>1. Mathematical Formulation</h2>
  <p>The model simulates a 2-DOF linear Quarter Car vehicle suspension:</p>
  <p>
    <code>m_s &middot; &z_s'' + c_w &middot; (&z_s' - &z_u') + k_w &middot; (z_s - z_u) = 0</code><br>
    <code>m_u &middot; &z_u'' + c_w &middot; (&z_u' - &z_s') + k_w &middot; (z_u - z_s) + k_t &middot; (z_u - z_road) = 0</code>
  </p>
  <p>Where wheel rates are derived from motion ratio (MR): <code>k_w = k_s &middot; MR&sup2;</code>, <code>c_w = c &middot; MR&sup2;</code>.</p>

  <h2>2. Variables & Causality</h2>
  <table>
    <thead>
      <tr>
        <th>Name</th>
        <th>VR</th>
        <th>Causality</th>
        <th>Variability</th>
        <th>Unit</th>
        <th>Description</th>
      </tr>
    </thead>
    <tbody>
      <tr><td><code>m_s</code></td><td>1</td><td>parameter</td><td>fixed</td><td>kg</td><td>Sprung mass</td></tr>
      <tr><td><code>m_u</code></td><td>2</td><td>parameter</td><td>fixed</td><td>kg</td><td>Unsprung mass</td></tr>
      <tr><td><code>k_s</code></td><td>3</td><td>parameter</td><td>fixed</td><td>N/m</td><td>Suspension spring stiffness</td></tr>
      <tr><td><code>c</code></td><td>4</td><td>parameter</td><td>fixed</td><td>Ns/m</td><td>Damper damping rate</td></tr>
      <tr><td><code>k_t</code></td><td>5</td><td>parameter</td><td>fixed</td><td>N/m</td><td>Tire vertical stiffness</td></tr>
      <tr><td><code>MR</code></td><td>6</td><td>parameter</td><td>fixed</td><td>-</td><td>Motion ratio (spring travel / wheel travel)</td></tr>
      <tr><td><code>c_t</code></td><td>7</td><td>parameter</td><td>fixed</td><td>Ns/m</td><td>Tire damping rate</td></tr>
      <tr><td><code>z_road</code></td><td>10</td><td>input</td><td>continuous</td><td>m</td><td>Vertical road displacement excitation</td></tr>
      <tr><td><code>dz_road</code></td><td>11</td><td>input</td><td>continuous</td><td>m/s</td><td>Vertical road velocity</td></tr>
      <tr><td><code>z_s</code></td><td>20</td><td>output</td><td>continuous</td><td>m</td><td>Sprung mass vertical displacement</td></tr>
      <tr><td><code>z_u</code></td><td>21</td><td>output</td><td>continuous</td><td>m</td><td>Unsprung mass vertical displacement</td></tr>
      <tr><td><code>susp_travel</code></td><td>22</td><td>output</td><td>continuous</td><td>m</td><td>Suspension stroke deflection (z_s - z_u)</td></tr>
      <tr><td><code>tire_load_dynamic</code></td><td>23</td><td>output</td><td>continuous</td><td>N</td><td>Dynamic contact load variation</td></tr>
      <tr><td><code>body_accel</code></td><td>24</td><td>output</td><td>continuous</td><td>m/s2</td><td>Sprung mass vertical acceleration</td></tr>
      <tr><td><code>time</code></td><td>25</td><td>output</td><td>continuous</td><td>s</td><td>Internal simulation time</td></tr>
    </tbody>
  </table>

  <h2>3. Integration & Solvers</h2>
  <p>The internal Co-Simulation solver utilizes a sub-stepped 4th-order Runge-Kutta (RK4) integrator with a maximum internal sub-step of 0.5 ms for numerical stability across stiff transients.</p>
</body>
</html>
"""
    return html


def build_fmu(
    output_fmu_path: pathlib.Path,
    model_name: str = "QuarterCarRideModel",
    targets: Optional[list[str]] = None,
) -> pathlib.Path:
    """
    Full build and packaging pipeline.
    Builds binaries, writes modelDescription.xml and documentation, and produces a valid .fmu file.
    """
    if targets is None:
        targets = ["win64", "linux64", "linux-arm64"]

    compiler_exe, compiler_type = find_c_compiler()

    output_fmu_path = pathlib.Path(output_fmu_path)
    output_fmu_path.parent.mkdir(parents=True, exist_ok=True)

    # Temporary build staging directory
    staging_dir = output_fmu_path.parent / f"_staging_{model_name}_{int(datetime.datetime.now().timestamp())}"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. modelDescription.xml
        fmi_desc = create_quarter_car_fmi_description(model_name)
        xml_content = fmi_desc.generate_xml()
        xml_path = staging_dir / "modelDescription.xml"
        xml_path.write_text(xml_content, encoding="utf-8")

        # 2. Documentation
        doc_dir = staging_dir / "documentation"
        doc_dir.mkdir(parents=True, exist_ok=True)
        doc_html = generate_fmi_documentation(model_name)
        (doc_dir / "index.html").write_text(doc_html, encoding="utf-8")

        # 3. Resources
        resources_dir = staging_dir / "resources"
        resources_dir.mkdir(parents=True, exist_ok=True)
        (resources_dir / "model_info.json").write_text(
            '{"name": "' + model_name + '", "author": "SuspensionLab PRO", "standard": "FMI 2.0"}\n',
            encoding="utf-8"
        )

        # 4. Binaries
        for target in targets:
            bin_dir = staging_dir / "binaries" / target
            bin_dir.mkdir(parents=True, exist_ok=True)

            if target == "win64":
                out_binary = bin_dir / f"{model_name}.dll"
            else:
                out_binary = bin_dir / f"{model_name}.so"

            compile_binary(
                target_platform=target,
                output_file=out_binary,
                compiler_exe=compiler_exe,
                compiler_type=compiler_type,
            )

        # 5. Package as ZIP with .fmu extension (FMI standard specification)
        with zipfile.ZipFile(output_fmu_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(staging_dir):
                for f in files:
                    file_path = pathlib.Path(root) / f
                    arcname = file_path.relative_to(staging_dir)
                    zf.write(file_path, arcname)

    finally:
        # Clean up staging directory
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

    return output_fmu_path


if __name__ == "__main__":
    out = pathlib.Path("QuarterCarRideModel.fmu")
    fmu_file = build_fmu(out)
    print(f"Built FMU successfully: {fmu_file} ({fmu_file.stat().st_size} bytes)")
