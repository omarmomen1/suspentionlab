"""Every backend status enum value must be mapped in frontend/lib/v2/status.ts,
so a new backend status cannot silently fall through to NOT_RUN."""
import pathlib
import re

from suspensionlab.physics.confidence_banner import ValidityStatus
from suspensionlab.physics.dynamic_lap_sim import LapSimulationOutcome
from suspensionlab.physics.telemetry_health import TelemetryPipelineStatus
from suspensionlab.physics.validity import PhysicsValidityStatus

STATUS_TS = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "lib" / "v2" / "status.ts"
EXTRA = {"PASS", "WARN", "FAIL", "NOT_EVALUATED", "UNVERIFIED", "NOT_MODELED"}  # Wave 5A-2/5B + kinematics benchmark


def _mapped():
    src = STATUS_TS.read_text(encoding="utf-8")
    body = src[src.index("BACKEND_STATUS_MAP"):src.index("export function mapBackendStatusToV2")]
    return re.findall(r"\b([A-Z][A-Z0-9_]+):\s*\"", body)


def test_no_key_is_mapped_twice():
    keys = _mapped()
    assert len(keys) == len(set(keys))


def test_backend_status_enums_are_all_mapped():
    mapped = set(_mapped())
    missing = [f"{e.__name__}.{m.value}" for e in
               (PhysicsValidityStatus, ValidityStatus, LapSimulationOutcome, TelemetryPipelineStatus)
               for m in e if m.value not in mapped]
    missing += sorted(EXTRA - mapped)
    assert not missing, missing
