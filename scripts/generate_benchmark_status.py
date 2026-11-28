#!/usr/bin/env python3
"""Run tests/physics_benchmarks and write frontend/public/benchmark-status.json.

Every tile comes from a pytest result: a red test is a red tile, with no manual
step. The JSON records measured values, tolerances, git SHA and timestamp.

  python scripts/generate_benchmark_status.py           # run and write
  python scripts/generate_benchmark_status.py --check   # CI: fail if the committed
                                                        # JSON differs from a fresh run
                                                        # (verdicts and measured values;
                                                        # sha and timestamp are ignored)
Exit code is non-zero when any benchmark fails or, with --check, the file is stale.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "public" / "benchmark-status.json"
SCHEMA_VERSION = 2

# id -> (test file, [(test function prefix, check label)])
BENCHMARKS = [
    ("B-01", "test_b01_quarter_car_eigenanalysis.py", "Quarter-car eigenanalysis",
     "Solver vs exact coupled 2-DOF characteristic roots. The uncoupled sqrt(k_w/m_s)/2pi value is "
     "reported separately as an approximation."),
    ("B-02", "test_b02_damper_cycle_energy.py", "Damper cycle energy",
     "Linear c_eff = c and bilinear (c_c + c_r)/2 through the Wave 5A phase integral."),
    ("B-03", "test_b03_tire_cornering_sign.py", "Tire cornering sign",
     "Standard .tir with PKY1 = -15.0 gives positive cornering stiffness. Calspan TTC fit is IN_PROGRESS."),
    ("B-04", "test_b04_full_car_heave.py", "Full-car heave mode",
     "Symmetric 4-corner heave vs the exact quarter-car hand calculation, plus roll/pitch symmetry."),
]


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def run() -> dict:
    with tempfile.TemporaryDirectory() as td:
        rec = pathlib.Path(td) / "records.json"
        env = dict(os.environ, BENCH_RECORD_PATH=str(rec))
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/physics_benchmarks/", "-q", "--tb=short", "-p", "no:cacheprovider"],
            cwd=ROOT, env=env, text=True, capture_output=True,
        )
        records = json.loads(rec.read_text()) if rec.exists() else {}
    tiles = []
    for bid, fname, title, desc in BENCHMARKS:
        checks = []
        for nodeid, r in sorted(records.items()):
            if nodeid.split("::")[0].endswith(fname):
                checks.append({
                    "test": nodeid.split("::")[1],
                    "verdict": r.get("verdict", "FAIL"),
                    "measured": _norm_val(r.get("measured", {})),
                    "tolerance": r.get("tolerance", {}),
                    "reference": r.get("reference", ""),
                })
        pending = [r.get("pending") for n, r in records.items() if n.split("::")[0].endswith(fname) and r.get("pending")]
        verdict = "FAIL" if (not checks or any(c["verdict"] != "PASS" for c in checks)) else "PASS"
        tile = {"id": bid, "name": title, "description": desc, "verdict": verdict, "checks": checks}
        if pending:
            tile["pending"] = pending[0]
        tiles.append(tile)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "scripts/generate_benchmark_status.py",
        "git_sha": _git_sha(),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "pytest_exit_code": proc.returncode,
        "scope_note": ("Solver self-consistency benchmarks against exact analytical references. "
                       "Not a validation against measured vehicle data."),
        "benchmarks": tiles,
        "_pytest_tail": proc.stdout[-600:] if proc.returncode else "",
    }


def _norm_val(v):
    if isinstance(v, float):
        if abs(v) < 1e-6:
            return 0.0
        return round(v, 6)
    if isinstance(v, dict):
        return {k: _norm_val(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_norm_val(val) for val in v]
    return v


def _stable(d: dict):
    return [(t["id"], t["verdict"], [(c["test"], c["verdict"], _norm_val(c["measured"])) for c in t["checks"]]) for t in d["benchmarks"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    data = run()
    tail = data.pop("_pytest_tail")
    failed = any(t["verdict"] != "PASS" for t in data["benchmarks"])
    if args.check:
        if not OUT.exists():
            print("benchmark-status.json missing; run scripts/generate_benchmark_status.py")
            return 1
        if _stable(json.loads(OUT.read_text(encoding="utf-8"))) != _stable(data):
            print("benchmark-status.json is stale; run scripts/generate_benchmark_status.py and commit it")
            return 1
        print("benchmark-status.json matches a fresh run")
        return 1 if failed else 0
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: " + ", ".join(f"{t['id']}={t['verdict']}" for t in data["benchmarks"]))
    if tail:
        print(tail)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
