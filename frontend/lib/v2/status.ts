/**
 * V2 truth model: six display states and the single canonical adapter from
 * backend status strings.
 *
 * Source enums (src/suspensionlab): PhysicsValidityStatus, confidence_banner
 * ValidityStatus, LapSimulationOutcome, TelemetryPipelineStatus, plus the
 * kinematics benchmark and Wave 5A-2/5B statuses NOT_EVALUATED, UNVERIFIED,
 * PASS, WARN, FAIL. tests/test_v2_status_enum_coverage.py fails if a backend
 * enum value is missing here, and the unit tests fail if a key maps twice.
 *
 * Rule: an unknown or empty status is NOT_RUN. It is never upgraded to VERIFIED.
 */
export const V2_STATES = ["NOT_RUN", "RUNNING", "VERIFIED", "WARNING", "OUT_OF_DOMAIN", "FAILED"] as const;
export type V2Status = (typeof V2_STATES)[number];

export const V2_LABEL: Record<V2Status, string> = {
  NOT_RUN: "Not run",
  RUNNING: "Running",
  VERIFIED: "Verified",
  WARNING: "Warning",
  OUT_OF_DOMAIN: "Out of domain",
  FAILED: "Failed",
};

// One entry per backend value. Keys are unique by construction of an object literal;
// a duplicate key would be a TypeScript error under strict mode.
export const BACKEND_STATUS_MAP: Readonly<Record<string, V2Status>> = {
  // VERIFIED
  PASS: "VERIFIED", PASSED: "VERIFIED", VERIFIED: "VERIFIED", VALIDATED: "VERIFIED",
  EMPIRICALLY_VALIDATED: "VERIFIED", LAP_COMPLETED: "VERIFIED", ACCEPTED: "VERIFIED",
  SUCCESS: "VERIFIED", COMPLETED: "VERIFIED", APPROVED: "VERIFIED", OK: "VERIFIED",
  // WARNING: usable, with caveats
  WARN: "WARNING", WARNING: "WARNING", DEGRADED: "WARNING", CONDITIONAL: "WARNING",
  CORRELATED: "WARNING", MODEL_SUPPORTED: "WARNING", ACCEPTED_WITH_WARNINGS: "WARNING",
  PARTIAL: "WARNING", INCONCLUSIVE: "WARNING", SIMULATION_ESTIMATE: "WARNING",
  // OUT_OF_DOMAIN: the model does not cover this case
  OUT_OF_DOMAIN: "OUT_OF_DOMAIN", EXTRAPOLATED: "OUT_OF_DOMAIN", UNSUPPORTED: "OUT_OF_DOMAIN",
  NOT_MODELED: "OUT_OF_DOMAIN", NOT_SUPPORTED: "OUT_OF_DOMAIN", UNIDENTIFIABLE: "OUT_OF_DOMAIN",
  // FAILED: ran, and the result must not be trusted
  FAIL: "FAILED", FAILED: "FAILED", ERROR: "FAILED", REJECTED: "FAILED",
  PHYSICAL_INSTABILITY: "FAILED", NUMERICAL_FAILURE: "FAILED", NUMERICALLY_FAILED: "FAILED",
  PROCESSING_FAILED: "FAILED", ANALYSIS_INVALID: "FAILED", TERMINATED: "FAILED", VIOLATION: "FAILED",
  // RUNNING
  RUNNING: "RUNNING", PROCESSING: "RUNNING",
  // NOT_RUN: nothing to verify against yet
  NOT_RUN: "NOT_RUN", NOT_EVALUATED: "NOT_RUN", UNVERIFIED: "NOT_RUN", UNVALIDATED: "NOT_RUN",
  DATA_MISSING: "NOT_RUN", PENDING: "NOT_RUN", QUEUED: "NOT_RUN", UNKNOWN: "NOT_RUN",
  IN_PROGRESS: "NOT_RUN",
};

/** Single canonical adapter. Never throws; unknown input is NOT_RUN. */
export function mapBackendStatusToV2(raw: unknown): V2Status {
  if (typeof raw !== "string") return "NOT_RUN";
  const key = raw.trim().toUpperCase().replace(/[\s-]+/g, "_");
  if (!key) return "NOT_RUN";
  if (key in BACKEND_STATUS_MAP) return BACKEND_STATUS_MAP[key];
  // Compound values such as NOT_MODELED_RIGID_SPHERICAL_JOINTS keep their prefix meaning.
  if (key.startsWith("NOT_MODELED")) return "OUT_OF_DOMAIN";
  return "NOT_RUN";
}

/**
 * Status for an API result object. Honours the lap-sim contract: an incomplete
 * lap is FAILED even when a stale solver_converged flag says true.
 */
export function mapResultToV2(res: unknown): V2Status {
  if (!res || typeof res !== "object") return "NOT_RUN";
  const o = res as Record<string, unknown>;
  if (o.lap_completed === false) return "FAILED";
  for (const k of ["status", "outcome", "validity_status", "physical_status"]) {
    if (typeof o[k] === "string" && o[k]) return mapBackendStatusToV2(o[k]);
  }
  return "NOT_RUN";
}
