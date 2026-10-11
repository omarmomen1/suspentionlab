import sys
import os

print(f"Python version: {sys.version}")
print(f"UID: {os.getuid() if hasattr(os, 'getuid') else 'N/A'}")
print(f"Environment: {os.environ.get('ENVIRONMENT', 'NOT_SET')}")

import suspensionlab.physics.kinematics as pk

print(f"pk._HAVE_CPP: {pk._HAVE_CPP}")
print(f"pk._kc: {pk._kc}")

if not pk._HAVE_CPP:
    print("FATAL: C++ kinematics solver failed to load!", file=sys.stderr)
    sys.exit(1)

from suspensionlab.physics.kinematics_facade import CppKinematicsBackend

hardpoints = {
    "chassis_upper_front": [100.0, 400.0, 400.0],
    "chassis_upper_rear": [-100.0, 400.0, 400.0],
    "upright_upper": [0.0, 600.0, 450.0],
    "chassis_lower_front": [100.0, 300.0, 200.0],
    "chassis_lower_rear": [-100.0, 300.0, 200.0],
    "upright_lower": [0.0, 600.0, 200.0],
    "chassis_tie_rod": [100.0, 300.0, 300.0],
    "upright_tie_rod": [100.0, 600.0, 300.0],
    "wheel_center": [0.0, 650.0, 330.0],
}

backend = CppKinematicsBackend(strict_mode=True)
pt = backend.solve_single(hardpoints, dz_mm=10.0)

print(f"Backend: {pt.active_backend}")
print(f"Solver version: {pt.solver_version}")
print(f"Build ID: {pt.build_identifier}")
print(f"Converged: {pt.converged}")
residual = pt.metadata.get("runtime_proof", {}).get("residual_norm")
print(f"Residual: {residual}")
print(f"Camber: {pt.camber_deg:.4f} deg")
print(f"Toe: {pt.toe_deg:.4f} deg")

assert pt.converged, "Solver did not converge!"
assert residual is not None and residual < 1e-10, f"Residual {residual} exceeds 1e-10"
assert pt.active_backend == "cpp", f"Solver backend was {pt.active_backend}, expected cpp"
assert "kinematics-core-v3.0-authoritative-cpp20" in pt.solver_version, "Unexpected solver version"

# Strict mode rejection test: verify that if C++ is not available, strict_mode=True rejects
try:
    saved_kc = pk._kc
    pk._kc = None
    fail_backend = CppKinematicsBackend(strict_mode=True)
    fail_backend.solve_single(hardpoints, dz_mm=10.0)
    assert False, "Failed to reject missing C++ in strict mode!"
except RuntimeError as exc:
    print(f"Verified strict mode rejection: {exc}")
finally:
    pk._kc = saved_kc

print("ALL CONTAINER NATIVE SOLVER CHECKS PASSED!")
