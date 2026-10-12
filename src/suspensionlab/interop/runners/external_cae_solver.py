"""
src/suspensionlab/interop/runners/external_cae_solver.py
========================================================
SuspensionLab PRO — Independent Standalone External CAE Dynamics Solver CLI.

A standalone, nonprivileged executable simulation runner for 2-DOF vehicle dynamics.
Executes in an isolated subprocess sandbox without mutating application state.
Reads standard model input decks (.json, .adm), numerically integrates equations of motion,
and emits standard time-series CSV and execution metadata.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import pathlib
import sys
import time
from typing import Dict, Tuple


def solve_rk4_quarter_car(
    m_s: float,
    m_u: float,
    k_s: float,
    c: float,
    k_t: float,
    MR: float = 1.0,
    c_t: float = 0.0,
    duration: float = 2.0,
    dt: float = 0.002,
    bump_height: float = 0.05,
    bump_time: float = 0.1,
) -> Tuple[list[float], list[float], list[float], list[float], list[float], list[float]]:
    """
    Numerically integrates 2-DOF linear quarter-car system using 4th-order Runge-Kutta.
    """
    k_w = k_s * (MR ** 2)
    c_w = c * (MR ** 2)

    def road_profile(t: float) -> Tuple[float, float]:
        if t >= bump_time:
            return (bump_height, 0.0)
        return (0.0, 0.0)

    def derivatives(t: float, state: list[float]) -> list[float]:
        z_s, dz_s, z_u, dz_u = state
        z_r, dz_r = road_profile(t)

        f_susp = k_w * (z_s - z_u) + c_w * (dz_s - dz_u)
        f_tire = k_t * (z_u - z_r) + c_t * (dz_u - dz_r)

        ddz_s = -f_susp / m_s
        ddz_u = (f_susp - f_tire) / m_u

        return [dz_s, ddz_s, dz_u, ddz_u]

    times: list[float] = []
    z_s_arr: list[float] = []
    z_u_arr: list[float] = []
    susp_travel_arr: list[float] = []
    tire_load_arr: list[float] = []
    body_accel_arr: list[float] = []

    steps = int(math.ceil(duration / dt))
    t = 0.0
    state = [0.0, 0.0, 0.0, 0.0]  # [z_s, dz_s, z_u, dz_u]

    for _ in range(steps + 1):
        z_s, dz_s, z_u, dz_u = state
        z_r, _ = road_profile(t)
        deriv = derivatives(t, state)

        times.append(t)
        z_s_arr.append(z_s)
        z_u_arr.append(z_u)
        susp_travel_arr.append(z_s - z_u)
        tire_load_arr.append(k_t * (z_u - z_r))
        body_accel_arr.append(deriv[1])

        # RK4 Step
        k1 = deriv
        s1 = [state[i] + 0.5 * dt * k1[i] for i in range(4)]
        k2 = derivatives(t + 0.5 * dt, s1)
        s2 = [state[i] + 0.5 * dt * k2[i] for i in range(4)]
        k3 = derivatives(t + 0.5 * dt, s2)
        s3 = [state[i] + dt * k3[i] for i in range(4)]
        k4 = derivatives(t + dt, s3)

        state = [
            state[i] + (dt / 6.0) * (k1[i] + 2.0 * k2[i] + 2.0 * k3[i] + k4[i])
            for i in range(4)
        ]
        t += dt

    return times, z_s_arr, z_u_arr, susp_travel_arr, tire_load_arr, body_accel_arr


def parse_parameters_from_file(input_path: pathlib.Path) -> Dict[str, float]:
    """
    Parses quarter car parameters from input artifact (.json canonical manifest or .adm deck).
    """
    params = {
        "m_s": 300.0,
        "m_u": 40.0,
        "k_s": 25000.0,
        "c": 1500.0,
        "k_t": 190000.0,
        "MR": 1.0,
        "c_t": 0.0,
    }

    if not input_path.exists():
        return params

    text = input_path.read_text(encoding="utf-8", errors="replace")

    if input_path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
            if "parameters" in data and isinstance(data["parameters"], dict):
                for k, v in data["parameters"].items():
                    val = v.get("value") if isinstance(v, dict) else v
                    if val is not None and k in params:
                        params[k] = float(val)
            elif "m_s" in data:
                for k in params:
                    if k in data:
                        params[k] = float(data[k])
        except Exception:
            pass

    elif input_path.suffix.lower() == ".adm":
        # Parse basic MSC Adams dataset tokens
        for line in text.splitlines():
            line = line.strip().upper()
            if "MASS" in line and "=" in line:
                try:
                    parts = line.split("MASS")[-1].split("=")[-1].strip().split(",")
                    val = float(parts[0])
                    if "PART/101" in text or "SPRUNG" in line:
                        params["m_s"] = val
                    elif "PART/102" in text or "UNSPRUNG" in line:
                        params["m_u"] = val
                except Exception:
                    pass

    return params


def main() -> int:
    parser = argparse.ArgumentParser(description="SuspensionLab Independent Standalone CAE Dynamics Solver")
    parser.add_argument("--input", required=True, help="Input model deck path (.json or .adm)")
    parser.add_argument("--output", required=True, help="Output simulation CSV path")
    parser.add_argument("--metadata-output", default=None, help="Output metadata JSON path")
    parser.add_argument("--duration", type=float, default=2.0, help="Simulation duration in seconds")
    parser.add_argument("--step", type=float, default=0.002, help="Time step in seconds")
    parser.add_argument("--bump-height", type=float, default=0.05, help="Step road bump excitation in meters")
    parser.add_argument("--bump-time", type=float, default=0.1, help="Time of road excitation step in seconds")
    parser.add_argument("--simulate-crash", action="store_true", help="Simulate a fatal solver runtime crash")
    parser.add_argument("--simulate-timeout", action="store_true", help="Simulate a stalled solver hanging indefinitely")

    args = parser.parse_args()

    if args.simulate_crash:
        sys.stderr.write("FATAL: Segmentation fault in solver numerical kernel.\n")
        return 139

    if args.simulate_timeout:
        time.sleep(120.0)
        return 0

    t_start = time.time()
    in_file = pathlib.Path(args.input)
    out_file = pathlib.Path(args.output)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    params = parse_parameters_from_file(in_file)

    times, z_s, z_u, susp_travel, tire_load, body_accel = solve_rk4_quarter_car(
        m_s=params["m_s"],
        m_u=params["m_u"],
        k_s=params["k_s"],
        c=params["c"],
        k_t=params["k_t"],
        MR=params["MR"],
        c_t=params["c_t"],
        duration=args.duration,
        dt=args.step,
        bump_height=args.bump_height,
        bump_time=args.bump_time,
    )

    # Write CSV using FMPy compatible column headers
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "z_s", "z_u", "susp_travel", "tire_load_dynamic", "body_accel"])
        for i in range(len(times)):
            writer.writerow([
                f"{times[i]:.6f}",
                f"{z_s[i]:.6f}",
                f"{z_u[i]:.6f}",
                f"{susp_travel[i]:.6f}",
                f"{tire_load[i]:.6f}",
                f"{body_accel[i]:.6f}",
            ])

    t_end = time.time()

    if args.metadata_output:
        meta_file = pathlib.Path(args.metadata_output)
        meta_file.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "solver_name": "EXTERNAL_CAE_SOLVER",
            "solver_version": "1.0.0",
            "execution_time_seconds": t_end - t_start,
            "total_timesteps": len(times),
            "parameters_used": params,
            "output_rows": len(times),
        }
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"EXTERNAL_CAE_SOLVER_RUNNER: Simulation completed successfully. Timesteps={len(times)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
