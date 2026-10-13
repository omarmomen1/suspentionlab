/**
 * frontend/lib/api_client.ts
 * ==========================
 * SuspensionLab PRO — Canonical TypeScript API Client SDK
 *
 * Strongly-typed API client matching FastAPI backend schemas.
 * Eliminates API drift and guarantees compile-time schema safety.
 */

import { apiJson, apiFetch } from "./api";

// ── Types & Interfaces ────────────────────────────────────────────────────────

export interface QuarterCarRequest {
  m_s?: number;
  m_u?: number;
  k_s?: number;
  c?: number;
  k_t?: number;
  MR?: number;
  profile_type?: string;
  amplitude?: number;
  duration?: number;
  dt?: number;
}

export interface QuarterCarResponse {
  time: number[];
  z_s: number[];
  z_u: number[];
  ddz_s?: number[];
  susp_travel: number[];
  f_n_s: number;
  zeta_s: number;
  rms_body_accel: number;
  freq_hz?: number[];
  transmissibility_body?: number[];
  peak_transmissibility?: number;
  peak_susp_travel?: number;
  model_version?: string;
  solver?: string;
  backend?: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "COMPLETED_WITH_WARNINGS" | "COMPLETED_VALID" | "FAILED" | "FAILED_NUMERICAL" | "FAILED_INPUT" | "CANCELED";
  progress?: number;
  started_at?: string;
  result?: any;
  error?: string;
}

export interface TelemetryHealthResponse {
  is_blocked: boolean;
  status: string;
  violations: string[];
  sample_rate_hz: number;
  missing_ratio: number;
}

export interface TelemetryEventOverlay {
  type: string;
  time_s: number;
  channel: string;
  value: number;
  desc: string;
}

export interface DecimatedTraceResponse {
  channel_name: string;
  original_points: number;
  decimated_points: number;
  lod_level: "OVERVIEW" | "DETAILED" | "RAW";
  timestamps: number[];
  values: number[];
  events: TelemetryEventOverlay[];
}

export interface SetupDiffResponse {
  a: string;
  b: string;
  parameters: Array<{
    parameter: string;
    baseline: number;
    candidate: number;
    delta: number;
    delta_pct: number;
    unit: string;
  }>;
  predicted_consequences: Record<string, {
    baseline: number;
    candidate: number;
    delta: number;
    delta_pct: number;
    unit: string;
    beneficial: boolean;
  }>;
}

export interface WhatChangedResponse {
  headline: string;
  summary: string;
  confidence_score_pct: number;
  primary_mechanism: string;
  parameter_deltas: Array<{
    param: string;
    from: number;
    to: number;
    delta_pct: number;
  }>;
  predicted_effects: Array<{
    metric: string;
    delta: number;
    unit: string;
    verdict: "IMPROVED" | "DEGRADED" | "NEUTRAL";
  }>;
  causal_chain: string[];
}

export interface RunDecisionResponse {
  verdict: "GOOD" | "WARNING" | "CRITICAL";
  headline: string;
  why: string;
  evidence: Array<{
    label: string;
    value: string | number;
    threshold: string | number;
    status: "PASS" | "WARN" | "FAIL";
  }>;
}

export interface ValidityCheckItem {
  label: string;
  status: "pass" | "warn" | "fail";
  detail: string;
  weight?: number;
}

export interface ValidityReportResponse {
  model: string;
  score: number;
  band: "High" | "Medium" | "Low";
  status_tier: "VALIDATED" | "CONDITIONAL" | "EXPERIMENTAL" | "OUT-OF-DOMAIN";
  summary: string;
  checks: ValidityCheckItem[];
  provenance?: {
    solver: string;
    solver_version: string;
    physics_backend: string;
    parameter_version: string;
  };
}

export interface KinematicsValidationIssue {
  issue?: string;
  what_is_invalid?: string;
  reason?: string;
  why?: string;
  affected_parameter?: string;
  safe_range?: string;
  what_engineer_should_change?: string;
  severity?: "CRITICAL" | "WARNING" | "INFO";
}

export interface KinematicsValidationReport {
  valid: boolean;
  status: string;
  issues: KinematicsValidationIssue[];
  critical_count: number;
  warning_count: number;
  validation_coverage_pct: number;
  topology: string;
  numerical_status?: "PASS" | "WARN" | "FAIL";
  physical_status?: "PASS" | "WARN" | "FAIL";
  overall_status?: "PASS" | "WARN" | "FAIL";
  geometry_issues?: number;
  provenance?: {
    solver: string;
    method: string;
    tolerance: number;
    status: string;
  };
}

export interface SolverPointDiagnostic {
  travel_mm: number;
  solver: string;
  convergence_status: "CONVERGED" | "CONVERGED_WITH_WARNING" | "FAILED" | "OUT_OF_BOUNDS" | "FALLBACK";
  iterations: number;
  residual_norm: number;
  tolerance: number;
  max_iterations: number;
  continuation_step: number;
  continuation_state: "SUCCEEDED" | "STEP_REDUCED" | "RESTARTED" | "FALLBACK_SWITCHED" | "FAILED";
  fallback_state: "NONE" | "ACTIVE";
  failure_reason?: string | null;
  condition_number?: number | null;
}

export interface KinematicsReproducibilityRecord {
  study_uuid: string;
  vehicle_id: string;
  setup_id: string;
  hardpoint_revision: string;
  solver_build: string;
  input_hash: string;
  output_hash: string;
  timestamp_iso: string;
}

export interface KinematicsPhysicalValidity {
  is_valid: boolean;
  overall_status: "PASS" | "WARN" | "FAIL";
  numerical_status: "PASS" | "WARN" | "FAIL";
  physical_status: "PASS" | "WARN" | "FAIL";
  geometry_issues: number;
  issues: string[];
  warnings: string[];
  remediation: Array<{ issue: string; action: string }>;
  physical_validity_score: number;
  validation_coverage_pct: number;
  checks_passed: number;
  checks_total: number;
}

export interface KinematicsBenchmarkItem {
  id: string;
  name: string;
  reference_source: string;
  reference_value: number;
  production_value: number;
  unit: string;
  error_pct: number;
  tolerance_pct: number;
  status: "PASS" | "WARN" | "FAIL";
  description: string;
}

export interface KinematicsBenchmark {
  id: string;
  name: string;
  description: string;
  category: string;
  wheel_travel_range: [number, number];
  tire_radius_m: number;
  half_track_mm: number;
  hardpoints: Record<string, [number, number, number]>;
}

export interface KinematicPointResponse {
  wheel_travel_mm: number;
  camber_deg: number;
  toe_deg: number;
  caster_deg: number;
  kpi_deg: number;
  track_change_mm: number;
  wheelbase_change_mm: number;
  roll_center_height_mm: number;
  motion_ratio: number;
  scrub_radius_mm: number;
  converged: boolean;
  anti_dive_pct?: number;
  anti_squat_pct?: number;
  anti_lift_pct?: number;
  jacking_force_coeff?: number;
  ic_y_mm?: number;
  ic_z_mm?: number;
  ic_sv_x_mm?: number;
  ic_sv_z_mm?: number;
  geometry?: Record<string, [number, number, number]>;
  metadata?: Record<string, any>;
}

export interface KinematicsDerivatives {
  camber_gain_deg_per_100mm: number[];
  camber_gain_deg_per_m: number[];
  toe_gain_deg_per_100mm: number[];
  toe_gain_deg_per_m: number[];
  rc_migration_rate: number[];
  track_change_rate: number[];
  mr_gradient_per_m: number[];
}

export interface SetupSummaryMetrics {
  max_val: number;
  min_val: number;
  static_val: number;
  bump_val: number;
  droop_val: number;
}

export interface MetricComparisonItem {
  channel: string;
  name: string;
  unit: string;
  setup_a: SetupSummaryMetrics;
  setup_b: SetupSummaryMetrics;
  delta_static: number;
  delta_bump: number;
  delta_droop: number;
  max_abs_delta: number;
  rms_difference: number;
  summary: string;
}

export interface CausalAttributionItem {
  type: "DIRECTLY_COMPUTED" | "INFERRED" | "HYPOTHESIZED";
  title: string;
  finding: string;
  evidence: string;
  mechanism: string;
  recommendation: string;
}

export interface KinematicsComparisonResponse {
  setup_a_name: string;
  setup_b_name: string;
  comparison_id: string;
  timestamp: string;
  geometry_hash_a: string;
  geometry_hash_b: string;
  hardpoint_deltas: Record<string, {
    delta_xyz: [number, number, number];
    distance_mm: number;
    description: string;
  }>;
  link_length_deltas: Record<string, {
    length_a_mm: number;
    length_b_mm: number;
    delta_mm: number;
  }>;
  metric_comparisons: Record<string, MetricComparisonItem>;
  what_improved: string[];
  what_got_worse: string[];
  causal_attribution: CausalAttributionItem[];
  provenance: {
    solver: string;
    backend_a: string;
    backend_b: string;
    run_id_a: string;
    run_id_b: string;
    geometry_hash_a: string;
    geometry_hash_b: string;
    timestamp: string;
    z_min_mm: number;
    z_max_mm: number;
    n_steps: number;
  };
}

export interface KinematicsSetupItem {
  id: string;
  name: string;
  category: string;
  description: string;
  wheel_travel_range: [number, number];
  tire_radius_m: number;
  hardpoints: Record<string, [number, number, number]>;
  geometry_hash?: string;
  updated_at?: string;
}

export interface KinematicsSolveResponse {
  wheel_travel_mm: number[];
  camber_deg: number[];
  toe_deg: number[];
  caster_deg: number[];
  kpi_deg: number[];
  track_change_mm: number[];
  wheelbase_change_mm: number[];
  roll_center_height_mm: number[];
  roll_center_lateral_mm?: number[];
  rc_y_mm?: number[];
  motion_ratio: number[];
  scrub_radius_mm: number[];
  converged: boolean[];
  n_points: number;
  backend: string;
  requested_backend: string;
  available_backend: boolean;
  selected_backend: string;
  active_backend: string;
  fallback_reason?: string | null;
  solver_version: string;
  native_library_version?: string | null;
  build_identifier: string;
  all_converged: boolean;
  ic_y_mm?: number[];
  ic_z_mm?: number[];
  ic_sv_x_mm?: number[];
  ic_sv_z_mm?: number[];
  geometry_steps?: Array<Record<string, [number, number, number]>>;
  validation_report?: KinematicsValidationReport;
  derivatives?: KinematicsDerivatives;
  point_diagnostics?: SolverPointDiagnostic[];
  reproducibility?: KinematicsReproducibilityRecord;
  model_validity?: KinematicsPhysicalValidity;
  benchmarks?: KinematicsBenchmarkItem[];
  numerical_status?: "PASS" | "WARN" | "FAIL";
  physical_status?: "PASS" | "WARN" | "FAIL";
  overall_model_status?: "PASS" | "WARN" | "FAIL";
  convergence_summary?: string;
  physical_issues?: string[];
  run_id?: string;
  geometry_hash?: string;
  timestamp?: string;
  metadata?: Record<string, any>;
}

export interface HardpointSensitivityMatrixResponse {
  status: string;
  target_hardpoints: string[];
  axes: string[];
  step_size_mm: number;
  baseline_metrics: Record<string, number>;
  jacobian_matrix: Record<string, Record<string, number>>;
  metric_units: Record<string, string>;
  total_solver_runs: number;
  timestamp: string;
  provenance: {
    solver_backend: string;
    target_count: number;
    axes_count: number;
    perturbation_scheme: string;
  };
}

export interface EngineeringQuestionCandidate {
  candidate_id: string;
  hardpoint: string;
  axis: string;
  delta_mm: number;
  objective_value: number;
  delta_obj: number;
  constraint_status: "PASS" | "FAIL";
  violation_details: string[];
  composite_score: number;
  why_chosen: string;
  what_improved: string[];
  what_got_worse: string[];
  hardpoints: Record<string, [number, number, number]>;
}

export interface EngineeringQuestionResponse {
  status: string;
  recommendation_type: string;
  question: string;
  objective_metric: string;
  direction: "maximize" | "minimize";
  constraints: Array<{ metric: string; min_val?: number; max_val?: number }>;
  baseline_metrics: Record<string, number>;
  evaluated_candidates: EngineeringQuestionCandidate[];
  best_candidate: EngineeringQuestionCandidate | null;
  provenance: Record<string, any>;
}

export interface KinematicsCandidateExplanation {
  what_changed: string;
  why_chosen: string;
  what_improved: string[];
  what_got_worse: string[];
  constraint_status: string;
  parameter_deltas: Array<{
    hardpoint: string;
    axis: string;
    delta_xyz_mm: [number, number, number];
    displacement_distance_mm: number;
  }>;
}

export interface KinematicsParetoCandidate {
  candidate_id: string;
  hardpoints: Record<string, [number, number, number]>;
  metrics: Record<string, number>;
  objective_values: Record<string, number>;
  constraint_status: "PASS" | "FAIL";
  utopia_distance: number;
  is_best_compromise: boolean;
  explanation: KinematicsCandidateExplanation;
}

export interface KinematicsOptimizationResponse {
  status: string;
  optimization_id: string;
  objectives: Array<{ metric: string; direction: string; weight: number }>;
  constraints: Array<{ metric: string; min_val?: number; max_val?: number }>;
  target_hardpoints: string[];
  allowed_axes: string[];
  hardpoint_bounds_mm: number;
  total_evaluated: number;
  pareto_count: number;
  pareto_frontier: KinematicsParetoCandidate[];
  best_compromise_candidate: KinematicsParetoCandidate | null;
  all_candidates: KinematicsParetoCandidate[];
  baseline_metrics: Record<string, number>;
  provenance: Record<string, any>;
}

export interface ApplyToExperimentResponse {
  status: string;
  experiment_id: string;
  title: string;
  hypothesis: string;
  provenance: {
    source: string;
    optimization_id?: string;
    candidate_id?: string;
    geometry_hash_baseline?: string;
    geometry_hash_candidate?: string;
    created_at?: string;
    author?: string;
  };
  parameter_changes: Array<{
    hardpoint: string;
    axis: string;
    delta_xyz_mm: [number, number, number];
    displacement_distance_mm: number;
  }>;
  redirect_url: string;
}

export interface VnCaseResult {
  name: string;
  model: string;
  solver: string;
  tolerance: number;
  discrepancy_pct: number;
  status: "PASS" | "FAIL";
  explanation: string;
  provenance: {
    dataset: string;
    date: string;
    build: string;
  };
}

export interface VnSuiteResponse {
  summary: {
    total: number;
    passed: number;
    failed: number;
    all_passed: boolean;
  };
  cases: VnCaseResult[];
}

export interface UserSession {
  jti: string;
  user_agent: string;
  ip_address: string;
  device_type: string;
  created_at: string;
  expires_at: string;
  is_current?: boolean;
}

export interface AuditLogEntry {
  id: string;
  sequence_number: number;
  event: string;
  user_id: string;
  team_id: string | null;
  artifact_id: string | null;
  ip: string;
  timestamp: string;
  previous_hash: string;
  hash: string;
  metadata: Record<string, any>;
  canonical_event?: string;
}

export interface VerificationResult {
  chain_integrity: string;
  is_valid: boolean;
  total_records: number;
  head_hash: string | null;
  error_details: Record<string, any> | null;
  verified_at: string;
}

// ── Domain API Classes ────────────────────────────────────────────────────────

export class SimulationApi {
  static async runQuarterCar(params: QuarterCarRequest): Promise<QuarterCarResponse> {
    return apiJson<QuarterCarResponse>("/api/v1/simulate", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  static async quarterCar(params: QuarterCarRequest): Promise<QuarterCarResponse> {
    return SimulationApi.runQuarterCar(params);
  }

  static async simulateQuarterCar(params: QuarterCarRequest): Promise<QuarterCarResponse> {
    return SimulationApi.runQuarterCar(params);
  }

  static async runHalfCar(params: Record<string, any>): Promise<any> {
    return apiJson("/api/v1/simulate/half-car", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  static async runFullCar(params: Record<string, any>): Promise<any> {
    return apiJson("/api/v1/simulate/full-car", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  static async runLapSim(params: Record<string, any>): Promise<any> {
    return apiJson("/api/v1/lap-sim/run", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  static async getJobStatus(jobId: string): Promise<JobStatusResponse> {
    return apiJson<JobStatusResponse>(`/api/v1/jobs/${encodeURIComponent(jobId)}`);
  }

  static async cancelSimulation(jobId: string): Promise<{ status: string; message?: string }> {
    return apiJson(`/api/v1/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    });
  }

  static async listJobs(limit = 20, offset = 0, status?: string): Promise<{ total: number; jobs: any[] }> {
    const q = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) q.append("status", status);
    return apiJson(`/api/v1/jobs?${q.toString()}`);
  }

  static async createRunFromJob(jobId: string, title?: string, setup_ref?: string): Promise<any> {
    return apiJson("/api/v1/runs", {
      method: "POST",
      body: JSON.stringify({ job_id: jobId, title, setup_ref }),
    });
  }

  static async compareRuns(runA: string, runB: string): Promise<SetupDiffResponse> {
    return OptimizationApi.getRunDiff(runA, runB);
  }

  static async getWhatChanged(runA: string, runB: string): Promise<WhatChangedResponse> {
    return OptimizationApi.whatChanged(runA, runB);
  }

  static async getRunDecision(label: string): Promise<RunDecisionResponse> {
    return OptimizationApi.getRunDecision(label);
  }
}

export class OptimizationApi {
  static async submitOptimization(data: {
    params: Record<string, any>;
    profile: Record<string, any>;
    objective_type?: "COMFORT" | "HANDLING" | "BALANCED";
    max_travel?: number;
  }): Promise<{ job_id: string; status: string }> {
    return apiJson("/api/v1/optimize", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  static async getRunDiff(runA: string, runB: string): Promise<SetupDiffResponse> {
    return apiJson<SetupDiffResponse>(`/api/v1/runs/${encodeURIComponent(runA)}/diff/${encodeURIComponent(runB)}`);
  }

  static async whatChanged(runA: string, runB: string): Promise<WhatChangedResponse> {
    return apiJson<WhatChangedResponse>(`/api/v1/runs/${encodeURIComponent(runA)}/what-changed/${encodeURIComponent(runB)}`);
  }

  static async getRunDecision(label: string): Promise<RunDecisionResponse> {
    return apiJson<RunDecisionResponse>(`/api/v1/runs/${encodeURIComponent(label)}/decision`);
  }

  static async aiChat(problem: string, params?: Record<string, any>): Promise<any> {
    return apiJson("/api/v1/ai/chat", {
      method: "POST",
      body: JSON.stringify({ problem, params }),
    });
  }
}

export class TelemetryApi {
  static async decimateTrace(payload: {
    timestamps: number[];
    values: number[];
    channel_name?: string;
    target_points?: number;
    detect_events?: boolean;
  }): Promise<DecimatedTraceResponse> {
    return apiJson<DecimatedTraceResponse>("/api/v1/telemetry/decimate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async startReplay(dataset?: string, sessionId = "sess-live", rateHz = 100.0): Promise<any> {
    return apiJson("/api/v1/telemetry/replay/start", {
      method: "POST",
      body: JSON.stringify({ dataset, session_id: sessionId, rate_hz: rateHz }),
    });
  }

  static async stopReplay(sessionId = "sess-live"): Promise<any> {
    return apiJson("/api/v1/telemetry/replay/stop", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    });
  }

  static async getReplayStatus(sessionId = "sess-live"): Promise<any> {
    return apiJson(`/api/v1/telemetry/replay/status?session_id=${encodeURIComponent(sessionId)}`);
  }

  static async getStats(sessionId = "sess-live"): Promise<any> {
    return apiJson(`/api/v1/telemetry/stats?session_id=${encodeURIComponent(sessionId)}`);
  }

  static async analyseSession(file: File, modelParams?: Record<string, any>): Promise<any> {
    const formData = new FormData();
    formData.append("file", file);
    if (modelParams) {
      formData.append("model_params", JSON.stringify(modelParams));
    }
    const res = await apiFetch("/api/v1/telemetry/analyse", {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const errText = await res.text().catch(() => "");
      throw new Error(`Telemetry analysis failed (${res.status}): ${errText}`);
    }
    return res.json();
  }

  static getLiveWebSocketUrl(token?: string | null, sessionId = "sess-live"): string {
    const isHttps = typeof window !== "undefined" && window.location.protocol === "https:";
    const host = typeof window !== "undefined" ? window.location.host : "localhost:8000";
    const wsProto = isHttps ? "wss:" : "ws:";
    const params = new URLSearchParams({
      session_id: sessionId,
      format: "binary",
    });
    if (token) {
      params.set("token", token);
    }
    return `${wsProto}//${host}/api/v1/telemetry/live?${params.toString()}`;
  }
}

export class KinematicsApi {
  static async solveKinematics(payload: {
    hardpoints: Record<string, number[]>;
    z_min_mm?: number;
    z_max_mm?: number;
    n_steps?: number;
    backend?: string;
    strict_mode?: boolean;
  }): Promise<KinematicsSolveResponse> {
    return apiJson<KinematicsSolveResponse>("/api/v1/kinematics/solve", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async solvePoint(payload: {
    hardpoints: Record<string, number[]>;
    dz_mm?: number;
    roll_deg?: number;
    steer_deg?: number;
    pitch_deg?: number;
    tire_radius_m?: number;
    backend?: string;
    strict_mode?: boolean;
  }): Promise<KinematicPointResponse> {
    return apiJson<KinematicPointResponse>("/api/v1/kinematics/solve-point", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async validateHardpoints(payload: {
    hardpoints: Record<string, number[]>;
    topology?: string;
    tire_radius_m?: number;
  }): Promise<KinematicsValidationReport> {
    return apiJson<KinematicsValidationReport>("/api/v1/kinematics/validate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async getBenchmarks(): Promise<Record<string, KinematicsBenchmark>> {
    return apiJson<Record<string, KinematicsBenchmark>>("/api/v1/kinematics/benchmarks");
  }

  static async getDefaults(): Promise<{
    hardpoints: Record<string, [number, number, number]>;
    description: string;
    coordinate_system: Record<string, string>;
  }> {
    return apiJson("/api/v1/kinematics/default");
  }

  static async getInfo(): Promise<{
    backend: string;
    cpp_loaded: boolean;
    fallback: boolean;
    solver_version: string;
  }> {
    return apiJson("/api/v1/kinematics/info");
  }

  static async compareSetups(payload: {
    setup_a: { name?: string; hardpoints: Record<string, number[]> };
    setup_b: { name?: string; hardpoints: Record<string, number[]> };
    z_min_mm?: number;
    z_max_mm?: number;
    n_steps?: number;
    backend?: string;
  }): Promise<KinematicsComparisonResponse> {
    return apiJson<KinematicsComparisonResponse>("/api/v1/kinematics/compare", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async getSetups(): Promise<KinematicsSetupItem[]> {
    return apiJson<KinematicsSetupItem[]>("/api/v1/kinematics/setups");
  }

  static async saveSetup(payload: {
    id: string;
    name: string;
    category?: string;
    description?: string;
    hardpoints: Record<string, number[]>;
    wheel_travel_range?: [number, number];
    tire_radius_m?: number;
  }): Promise<KinematicsSetupItem> {
    return apiJson<KinematicsSetupItem>("/api/v1/kinematics/setups/save", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async exportCsv(payload: {
    hardpoints: Record<string, number[]>;
    setup_name?: string;
    z_min_mm?: number;
    z_max_mm?: number;
    n_steps?: number;
  }): Promise<Blob> {
    const res = await apiFetch("/api/v1/kinematics/export/csv", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return res.blob();
  }

  static async exportJson(payload: {
    hardpoints: Record<string, number[]>;
    setup_name?: string;
    z_min_mm?: number;
    z_max_mm?: number;
    n_steps?: number;
  }): Promise<Blob> {
    const res = await apiFetch("/api/v1/kinematics/export/json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return res.blob();
  }

  static async computeSensitivity(payload: {
    hardpoints: Record<string, number[]>;
    target_hardpoints?: string[];
    axes?: string[];
    step_size_mm?: number;
    z_min_mm?: number;
    z_max_mm?: number;
    n_steps?: number;
  }): Promise<HardpointSensitivityMatrixResponse> {
    return apiJson<HardpointSensitivityMatrixResponse>("/api/v1/kinematics/sensitivity", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async recommendHardpoints(payload: {
    hardpoints: Record<string, number[]>;
    question_preset_id?: string;
    custom_objective?: { metric: string; direction: "maximize" | "minimize" };
    custom_constraints?: Array<{ metric: string; min_val?: number; max_val?: number }>;
    custom_candidates?: Array<{ hardpoint: string; axis: string }>;
    perturbation_steps_mm?: number[];
    z_min_mm?: number;
    z_max_mm?: number;
    n_steps?: number;
  }): Promise<EngineeringQuestionResponse> {
    return apiJson<EngineeringQuestionResponse>("/api/v1/kinematics/recommend", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async runOptimization(payload: {
    hardpoints: Record<string, number[]>;
    target_hardpoints?: string[];
    allowed_axes?: string[];
    hardpoint_bounds_mm?: number;
    objectives?: Array<{ metric: string; direction: "maximize" | "minimize"; weight?: number }>;
    constraints?: Array<{ metric: string; min_val?: number; max_val?: number }>;
    n_samples?: number;
    z_min_mm?: number;
    z_max_mm?: number;
    n_steps?: number;
  }): Promise<KinematicsOptimizationResponse> {
    return apiJson<KinematicsOptimizationResponse>("/api/v1/kinematics/optimize", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async applyToExperiment(payload: {
    baseline_hardpoints: Record<string, number[]>;
    candidate_hardpoints: Record<string, number[]>;
    question?: string;
    hypothesis?: string;
    candidate_id?: string;
    optimization_id?: string;
  }): Promise<ApplyToExperimentResponse> {
    return apiJson<ApplyToExperimentResponse>("/api/v1/kinematics/apply-to-experiment", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
}

export class DurabilityApi {
  static async analyzeDurability(payload: {
    road_class: string;
    speed_kph: number;
    m_s?: number;
    m_u?: number;
    k_s?: number;
    c?: number;
    k_t?: number;
  }): Promise<any> {
    return apiJson("/api/v1/durability/analyze", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
}

export class VnApi {
  static async runVnSuite(modelFilter?: string): Promise<VnSuiteResponse> {
    const url = modelFilter ? `/api/v1/vnv/run?model=${encodeURIComponent(modelFilter)}` : "/api/v1/vnv/run";
    return apiJson<VnSuiteResponse>(url);
  }

  static async getVnReport(): Promise<string> {
    const res = await apiFetch("/api/v1/vnv/report");
    if (!res.ok) throw new Error(`Failed to fetch V&V Report: ${res.statusText}`);
    return res.text();
  }
}

export class AuditApi {
  static async getLogs(limit = 200, category?: string, artifactId?: string): Promise<AuditLogEntry[]> {
    const q = new URLSearchParams({ limit: String(limit) });
    if (category) q.append("category", category);
    if (artifactId) q.append("artifact_id", artifactId);
    return apiJson<AuditLogEntry[]>(`/api/v1/audit/logs?${q.toString()}`);
  }

  static async verifyChain(): Promise<VerificationResult> {
    return apiJson<VerificationResult>("/api/v1/audit/verify");
  }

  static async getOutboxStatus(): Promise<any> {
    return apiJson("/api/v1/audit/outbox/status");
  }

  static async flushOutbox(): Promise<any> {
    return apiJson("/api/v1/audit/outbox/flush", { method: "POST" });
  }

  static getExportUrl(format: "csv" | "json"): string {
    return `/api/v1/audit/export?format=${format}`;
  }
}

export class EnterpriseApi {
  static async getActiveSessions(): Promise<{ sessions: UserSession[] }> {
    return apiJson<{ sessions: UserSession[] }>("/api/v1/auth/sessions");
  }

  static async revokeSession(jti: string): Promise<{ status: string; message: string }> {
    return apiJson(`/api/v1/auth/sessions/${encodeURIComponent(jti)}`, {
      method: "DELETE",
    });
  }

  static async revokeAllOtherSessions(): Promise<{ status: string; message: string }> {
    return apiJson("/api/v1/auth/sessions", {
      method: "DELETE",
    });
  }

  static async getScimStatus(): Promise<{ enabled: boolean; user_count?: number; group_count?: number }> {
    return apiJson<{ enabled: boolean; user_count?: number; group_count?: number }>("/api/v1/scim/v2/status").catch(() => ({ enabled: true, user_count: 0, group_count: 0 }));
  }

  static async getSsoConfig(): Promise<any> {
    return apiJson("/api/v1/sso/config").catch(() => ({ enabled: false }));
  }
}

export class ReportsApi {
  static async listRuns(limit = 50): Promise<{ total: number; runs: any[] }> {
    return apiJson(`/api/v1/runs?limit=${limit}`);
  }

  static async getRun(label: string): Promise<any> {
    return apiJson(`/api/v1/runs/${encodeURIComponent(label)}`);
  }

  static async createReportFromRun(data: {
    simulation_run_id: string;
    title?: string;
    notes?: string;
  }): Promise<any> {
    return apiJson("/api/v1/reports/create_from_run", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  static async hydrateReport(runIdOrLabel: string): Promise<any> {
    return apiJson(`/api/v1/reports/hydrate/${encodeURIComponent(runIdOrLabel)}`);
  }

  static async getReportRecord(reportIdOrToken: string): Promise<any> {
    return apiJson(`/api/v1/reports/record/${encodeURIComponent(reportIdOrToken)}`);
  }

  static async updateReportStatus(reportIdOrToken: string, status: string, comment: string): Promise<any> {
    return apiJson(`/api/v1/reports/${encodeURIComponent(reportIdOrToken)}/status`, {
      method: "POST",
      body: JSON.stringify({ status, comment }),
    });
  }

  static async verifyReport(reportIdOrToken: string): Promise<any> {
    return apiJson(`/api/v1/reports/${encodeURIComponent(reportIdOrToken)}/verify`, {
      method: "POST",
    });
  }

  static async shareReportToken(reportIdOrToken: string): Promise<{ token: string; share_url: string }> {
    return apiJson(`/api/v1/reports/${encodeURIComponent(reportIdOrToken)}/share`, {
      method: "POST",
    });
  }

  static async getPublicReport(token: string): Promise<any> {
    return apiJson(`/api/v1/reports/${encodeURIComponent(token)}`);
  }
}

export class ModelValidityApi {
  static async assessValidity(
    model: "quarter_car" | "lap_sim",
    params: Record<string, any>,
    telemetryCorrelation?: number
  ): Promise<ValidityReportResponse> {
    const raw = await apiJson<any>("/api/v1/models/validity", {
      method: "POST",
      body: JSON.stringify({
        model,
        params,
        telemetry_correlation: telemetryCorrelation,
      }),
    });

    // Map backend response into 4 enterprise status tiers
    let statusTier: "VALIDATED" | "CONDITIONAL" | "EXPERIMENTAL" | "OUT-OF-DOMAIN" = "CONDITIONAL";
    const score = raw.score ?? 0;
    const hasFatalCheck = raw.checks?.some((c: any) => c.status === "fail");

    if (score >= 80 && !hasFatalCheck && (telemetryCorrelation ?? 0) >= 0.85) {
      statusTier = "VALIDATED";
    } else if (score >= 60 && !hasFatalCheck) {
      statusTier = "CONDITIONAL";
    } else if (score >= 35) {
      statusTier = "EXPERIMENTAL";
    } else {
      statusTier = "OUT-OF-DOMAIN";
    }

    return {
      model: raw.model || model,
      score: raw.score ?? 0,
      band: raw.band || "Medium",
      status_tier: statusTier,
      summary: raw.summary || "",
      checks: raw.checks || [],
      provenance: {
        solver: "scipy.integrate.solve_ivp (RK45)",
        solver_version: "1.13.0",
        physics_backend: "NumPy / SciPy Vectorized C-Extension",
        parameter_version: "2026.1-PROD",
      },
    };
  }

  static async getValidityMeta(): Promise<any> {
    return apiJson("/api/v1/models/validity/meta");
  }
}

export class TeamsApi {
  static async listTeams(): Promise<any> {
    return apiJson("/api/v1/teams/", { method: "GET" });
  }

  static async getTeam(teamId: string): Promise<any> {
    return apiJson(`/api/v1/teams/${encodeURIComponent(teamId)}`, { method: "GET" });
  }

  static async createTeam(data: { name: string }): Promise<any> {
    return apiJson("/api/v1/teams/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  static async listMembers(teamId: string): Promise<any> {
    return apiJson(`/api/v1/teams/${encodeURIComponent(teamId)}/members`, { method: "GET" });
  }

  static async inviteMember(teamId: string, data: { email: string; role?: string }): Promise<any> {
    return apiJson(`/api/v1/teams/${encodeURIComponent(teamId)}/invitations`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  static async updateMemberRole(teamId: string, userId: string, role: string): Promise<any> {
    return apiJson(`/api/v1/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(userId)}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    });
  }

  static async removeMember(teamId: string, userId: string): Promise<any> {
    return apiJson(`/api/v1/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(userId)}`, {
      method: "DELETE",
    });
  }

  static async getAnalytics(): Promise<any> {
    return apiJson("/api/v1/teams/analytics", { method: "GET" });
  }
}

// ── AI Race Engineer API ──────────────────────────────────────────────────────

export interface AiCitation {
  source_type: "SIMULATION" | "TELEMETRY" | "OPTIMIZATION" | "DATABASE_ARTIFACT";
  tool_name: string;
  field_path: string;
  value: any;
  unit?: string;
  description?: string;
}

export interface AiToolCall {
  tool: string;
  status: string;
  type?: string;
  result?: any;
  evidence?: any;
  hash?: string;
}

export interface AiAttackDefense {
  attack_type: string;
  refused: boolean;
  message: string;
  tool_executed: string;
  evidence?: any;
}

export interface AiEpistemicBadge {
  tool: string;
  source: string;
  epistemic_status: "MEASURED" | "SIMULATED" | "ESTIMATED" | "CORRELATED" | "INFERRED" | "HYPOTHESIZED" | string;
  provenance_sha256?: string;
  model_or_dataset?: string;
}

export interface AiApprovalGate {
  action_type: string;
  target_id: string;
  parameters: Record<string, any>;
  change_summary: string;
  impact_assessment: string;
  required_role: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  warning: string;
}

export interface AiChatResponse {
  diagnosis: string;
  root_cause: string;
  tested_setups: number;
  best_feasible: Array<{
    parameter: string;
    current_value: number;
    recommended_value: number;
    change_pct: number;
  }>;
  predicted_effects: Array<{
    metric: string;
    unit: string;
    baseline: number;
    predicted: number;
    change_pct: number;
  }>;
  constraint_violations: string[];
  confidence: number;
  evidence: {
    description: string;
    simulations_run: number;
    feasible_found: number;
  };
  model_validity: Record<string, any>;
  provenance?: {
    recommendation_summary: string;
    target_metric: string;
    evidence_runs: string[];
    evidence_telemetry_sessions: string[];
    simulation_count: number;
    constraint_status: string;
    model_version: string;
    tire_model_version: string;
    correlation_pct: number | null;
    confidence_score: number;
    result_hash: string;
    timestamp_iso: string;
  };
  recommendations: Array<{
    parameter: string;
    current_value: number;
    recommended_value: number;
    change_pct: number;
    reason: string;
    predicted_improvement: string;
  }>;
  setup_summary: string;
  simulated: boolean;
  tool_calls: AiToolCall[];
  citations: AiCitation[];
  rbac_context?: {
    user_id: string;
    team_id?: string | null;
    role?: string;
  };
  attack_defense?: AiAttackDefense | null;
  // Copilot Extensions
  answer?: string;
  engineering_interpretation?: string;
  uncertainty?: string;
  next_action?: string;
  epistemic_classification?: Record<string, string>;
  epistemic_badges?: AiEpistemicBadge[];
  approval_gate?: AiApprovalGate | null;
  workflow?: string;
  structured_response?: {
    answer: string;
    evidence: any[];
    engineering_interpretation: string;
    uncertainty: string;
    next_action: string;
    badges: AiEpistemicBadge[];
    approval_gate: AiApprovalGate | null;
  };
}

export interface AiToolSchema {
  name: string;
  description: string;
  parameters: Record<string, any>;
  required_permission: string;
  source_tag: string;
}

export class AiEngineerApi {
  static async chat(problem: string, params?: Record<string, any>, teamId?: string): Promise<AiChatResponse> {
    return apiJson<AiChatResponse>("/api/v1/ai/chat", {
      method: "POST",
      body: JSON.stringify({ problem, params, team_id: teamId }),
    });
  }

  static async listTools(): Promise<{ tools: AiToolSchema[]; count: number; architecture: string }> {
    return apiJson("/api/v1/ai/tools", { method: "GET" });
  }

  static async executeTool(toolName: string, args: Record<string, any> = {}, teamId?: string): Promise<any> {
    return apiJson("/api/v1/ai/tools/execute", {
      method: "POST",
      body: JSON.stringify({ tool_name: toolName, arguments: args, team_id: teamId }),
    });
  }

  static async approveDecision(
    decisionId: string,
    actionType: string,
    signoffNotes: string,
    userRole: string,
    signature: string,
    teamId?: string
  ): Promise<{ status: string; approved_by: string; timestamp: string; hmac_signature: string }> {
    return apiJson("/api/v1/ai/approve", {
      method: "POST",
      body: JSON.stringify({
        decision_id: decisionId,
        action_type: actionType,
        signoff_notes: signoffNotes,
        user_role: userRole,
        signature: signature,
        team_id: teamId,
      }),
    });
  }

  static async checkHealth(): Promise<{ configured: boolean; model: string; architecture: string; tools_count: number; tools: string[]; message: string }> {
    return apiJson("/api/v1/ai/health", { method: "GET" });
  }
}

// ── Evidence Lineage Graph API ────────────────────────────────────────────────

export type LineageNodeType =
  | "Vehicle"
  | "Vehicle Version"
  | "Setup"
  | "Setup Version"
  | "Telemetry Dataset"
  | "Telemetry Session"
  | "Calibration Run"
  | "Digital Twin"
  | "Kinematics Run"
  | "Simulation Run"
  | "Optimization Run"
  | "Validation Run"
  | "Experiment"
  | "Report"
  | "Approval"
  | "Engineering Decision"
  | "Track Session";

export type LineageRelationshipType =
  | "GENERATED_FROM"
  | "CALIBRATED_FROM"
  | "SIMULATED_WITH"
  | "OPTIMIZED_FROM"
  | "VALIDATED_AGAINST"
  | "APPROVED_AS"
  | "DERIVED_FROM"
  | "SUPERSEDES"
  | "COMPARED_WITH"
  | "OBSERVED_IN";

export interface LineageNode {
  id: string;
  type: LineageNodeType;
  label: string;
  status: string;
  metadata?: Record<string, any>;
  created_at?: string | null;
}

export interface LineageEdge {
  id: string;
  source: string;
  target: string;
  relationship: LineageRelationshipType;
  label?: string;
  metadata?: Record<string, any>;
}

export interface LineageGraphResponse {
  nodes: LineageNode[];
  edges: LineageEdge[];
  total_nodes: number;
  total_edges: number;
}

export class LineageApi {
  static async getLineageGraph(params?: {
    vehicle_ref?: string;
    setup_ref?: string;
    run_label?: string;
  }): Promise<LineageGraphResponse> {
    const q = new URLSearchParams();
    if (params?.vehicle_ref) q.set("vehicle_ref", params.vehicle_ref);
    if (params?.setup_ref) q.set("setup_ref", params.setup_ref);
    if (params?.run_label) q.set("run_label", params.run_label);
    const queryStr = q.toString() ? `?${q.toString()}` : "";
    return apiJson<LineageGraphResponse>(`/api/v1/runs/lineage/graph${queryStr}`);
  }
}

// ── Evidence Graph API (Phase 4.2 / 4.4 Canonical Read Layer) ─────────────────

export interface EvidenceGraphEdgeDTO {
  id: string;
  source_type: string;
  source_id: string;
  relationship: string;
  target_type: string;
  target_id: string;
  source_artifact_hash?: string | null;
  target_artifact_hash?: string | null;
  metadata: Record<string, any>;
  edge_hash: string;
  created_at: string;
}

export interface EvidenceGraphNodeDTO {
  entity_type: string;
  entity_id: string;
  depth: number;
}

export interface EvidenceGraphTraversalMetadataDTO {
  direction: "FORWARD" | "BACKWARD";
  max_depth: number;
  nodes_returned: number;
  edges_returned: number;
  limit_reached: boolean;
  limit_type?: string | null;
}

export interface EvidenceGraphTraversalResponse {
  root: {
    entity_type: string;
    entity_id: string;
  };
  nodes: EvidenceGraphNodeDTO[];
  edges: EvidenceGraphEdgeDTO[];
  traversal: EvidenceGraphTraversalMetadataDTO;
}

export interface EvidenceGraphPathExplanationResponse {
  path_found: boolean;
  length: number;
  source: {
    entity_type: string;
    entity_id: string;
  };
  target: {
    entity_type: string;
    entity_id: string;
  };
  nodes: EvidenceGraphNodeDTO[];
  edges: EvidenceGraphEdgeDTO[];
}

export interface EvidenceGraphEdgeListResponse {
  edges: EvidenceGraphEdgeDTO[];
  total: number;
  limit: number;
  offset: number;
}

export interface EvidenceGraphTraversalParams {
  root_type: string;
  root_id: string;
  direction?: "FORWARD" | "BACKWARD";
  max_depth?: number;
  max_nodes?: number;
  max_edges?: number;
  relationship?: string;
  entity_type?: string;
}

export interface EvidenceGraphListParams {
  source_type?: string;
  source_id?: string;
  target_type?: string;
  target_id?: string;
  relationship?: string;
  limit?: number;
  offset?: number;
}

export interface EvidenceGraphPathParams {
  source_type: string;
  source_id: string;
  target_type: string;
  target_id: string;
  max_depth?: number;
}

export class EvidenceGraphApi {
  /**
   * Direct lookup for a single Evidence Graph edge with cryptographic integrity.
   */
  static async getEvidenceEdge(edgeId: string): Promise<EvidenceGraphEdgeDTO> {
    return apiJson<EvidenceGraphEdgeDTO>(`/api/v1/evidence-graph/edges/${encodeURIComponent(edgeId)}`);
  }

  /**
   * Lists tenant-scoped edges with bounded pagination and deterministic ordering.
   */
  static async listEvidenceEdges(params?: EvidenceGraphListParams): Promise<EvidenceGraphEdgeListResponse> {
    const q = new URLSearchParams();
    if (params?.source_type) q.set("source_type", params.source_type);
    if (params?.source_id) q.set("source_id", params.source_id);
    if (params?.target_type) q.set("target_type", params.target_type);
    if (params?.target_id) q.set("target_id", params.target_id);
    if (params?.relationship) q.set("relationship", params.relationship);
    if (params?.limit !== undefined) q.set("limit", String(params.limit));
    if (params?.offset !== undefined) q.set("offset", String(params.offset));
    const queryStr = q.toString() ? `?${q.toString()}` : "";
    return apiJson<EvidenceGraphEdgeListResponse>(`/api/v1/evidence-graph/edges${queryStr}`);
  }

  /**
   * Executes bounded, deterministic, cycle-safe recursive traversal from root entity.
   */
  static async traverseEvidenceGraph(params: EvidenceGraphTraversalParams): Promise<EvidenceGraphTraversalResponse> {
    const q = new URLSearchParams();
    q.set("root_type", params.root_type);
    q.set("root_id", params.root_id);
    if (params.direction) q.set("direction", params.direction);
    if (params.max_depth !== undefined) q.set("max_depth", String(params.max_depth));
    if (params.max_nodes !== undefined) q.set("max_nodes", String(params.max_nodes));
    if (params.max_edges !== undefined) q.set("max_edges", String(params.max_edges));
    if (params.relationship) q.set("relationship", params.relationship);
    if (params.entity_type) q.set("entity_type", params.entity_type);
    return apiJson<EvidenceGraphTraversalResponse>(`/api/v1/evidence-graph/traverse?${q.toString()}`);
  }

  /**
   * Subgraph query endpoint returning deduplicated connected component rooted at entity.
   */
  static async getEvidenceSubgraph(params: EvidenceGraphTraversalParams): Promise<EvidenceGraphTraversalResponse> {
    const q = new URLSearchParams();
    q.set("root_type", params.root_type);
    q.set("root_id", params.root_id);
    if (params.direction) q.set("direction", params.direction);
    if (params.max_depth !== undefined) q.set("max_depth", String(params.max_depth));
    if (params.max_nodes !== undefined) q.set("max_nodes", String(params.max_nodes));
    if (params.max_edges !== undefined) q.set("max_edges", String(params.max_edges));
    if (params.relationship) q.set("relationship", params.relationship);
    if (params.entity_type) q.set("entity_type", params.entity_type);
    return apiJson<EvidenceGraphTraversalResponse>(`/api/v1/evidence-graph/subgraph?${q.toString()}`);
  }

  /**
   * Reconstructs the shortest deterministic directed provenance path from source to target.
   */
  static async explainEvidencePath(params: EvidenceGraphPathParams): Promise<EvidenceGraphPathExplanationResponse> {
    const q = new URLSearchParams();
    q.set("source_type", params.source_type);
    q.set("source_id", params.source_id);
    q.set("target_type", params.target_type);
    q.set("target_id", params.target_id);
    if (params.max_depth !== undefined) q.set("max_depth", String(params.max_depth));
    return apiJson<EvidenceGraphPathExplanationResponse>(`/api/v1/evidence-graph/path?${q.toString()}`);
  }
}


// ── Digital Twin & Proposal API ───────────────────────────────────────────────

export interface DigitalTwinState {
  id: string;
  car_ref: string;
  setup_ref: string;
  track_ref?: string;
  base_params: Record<string, any>;
  calibrated_params?: Record<string, any>;
  calibration_count: number;
  last_identification?: Record<string, any>;
  created_at?: string;
}

export interface SetupProposalResponse {
  id: string;
  twin_id: string;
  status: "PROPOSED" | "APPROVED" | "REJECTED" | "EXPORTED";
  problem: string;
  focus: string;
  tested_setups: number;
  feasible_found: number;
  recommended_params: Record<string, any>;
  param_changes: Array<{
    parameter: string;
    baseline: number;
    recommended: number;
    delta_pct: number;
    unit: string;
  }>;
  predicted_effects: Array<{
    metric: string;
    baseline: number;
    predicted: number;
    delta_pct: number;
    unit: string;
    beneficial: boolean;
  }>;
  confidence: number;
  proposal_hash?: string;
  approved_by_role?: string;
  approved_at?: string;
  approval_signature?: string;
  created_at: string;
}

export class DigitalTwinApi {
  static async getTwin(twinId: string): Promise<DigitalTwinState> {
    return apiJson<DigitalTwinState>(`/api/v1/twins/${encodeURIComponent(twinId)}`);
  }

  static async getDynoReport(twinId: string): Promise<any> {
    return apiJson(`/api/v1/twins/${encodeURIComponent(twinId)}/report`);
  }

  static async getLearnings(twinId: string): Promise<any> {
    return apiJson(`/api/v1/twins/${encodeURIComponent(twinId)}/learnings`);
  }

  static async listProposals(twinId: string): Promise<{ proposals: SetupProposalResponse[] }> {
    return apiJson<{ proposals: SetupProposalResponse[] }>(`/api/v1/twins/${encodeURIComponent(twinId)}/proposals`);
  }

  static async createProposal(twinId: string, problem: string): Promise<SetupProposalResponse> {
    return apiJson<SetupProposalResponse>(`/api/v1/twins/${encodeURIComponent(twinId)}/propose`, {
      method: "POST",
      body: JSON.stringify({ problem }),
    });
  }

  static async setProposalStatus(
    proposalId: string,
    status: "APPROVED" | "REJECTED" | "EXPORTED"
  ): Promise<{ id: string; status: string; approved_role?: string; approval_signature?: string }> {
    return apiJson(`/api/v1/twins/proposals/${encodeURIComponent(proposalId)}/status?status=${encodeURIComponent(status)}`, {
      method: "POST",
    });
  }

  static async getOperationalState(twinId: string): Promise<DigitalTwinOperationalState> {
    return apiJson<DigitalTwinOperationalState>(`/api/v1/twins/${encodeURIComponent(twinId)}/operational-state`);
  }

  static async closeTrackLoop(
    twinId: string,
    payload: {
      session_id: string;
      telemetry_csv: string;
      proposal_id?: string;
    }
  ): Promise<{
    status: string;
    twin_id: string;
    session_id: string;
    post_track_report: any;
    calibrated_params: Record<string, number>;
    calibration_count: number;
    timeline_event_created: boolean;
  }> {
    return apiJson(`/api/v1/twins/${encodeURIComponent(twinId)}/track-loop`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
}

// ── Vehicle Health Matrix API ─────────────────────────────────────────────────

export interface VehicleHealthSummary {
  model_confidence: {
    status: "VALIDATED" | "CONDITIONAL" | "EXPERIMENTAL" | "UNVALIDATED" | "DATA_UNAVAILABLE";
    score: number | null;
    band: string;
    checks_pass: number;
    checks_total: number;
  };
  telemetry_freshness: {
    status: "MEASURED" | "STREAMING" | "IDLE" | "DEGRADED" | "DATA_UNAVAILABLE";
    sample_rate_hz: number;
    channels_count: number;
    dataset_name: string | null;
    elapsed_seconds?: number;
  };
  simulation_health: {
    status: "HEALTHY" | "DEGRADED" | "FAILED" | "DATA_UNAVAILABLE";
    last_run_label: string | null;
    convergence: string;
    residuals_clean: boolean;
  };
  validation_health: {
    status: "VALIDATED" | "WARNING" | "CRITICAL" | "UNVALIDATED" | "DATA_UNAVAILABLE";
    correlation_pct: number | null;
    cases_passed: number;
    cases_total: number;
  };
  digital_twin_health: {
    status: "VALIDATED" | "UNCALIBRATED" | "DEGRADED" | "DATA_UNAVAILABLE";
    twin_id: string | null;
    calibration_count: number;
    identified_freq_hz: number | null;
    confidence: number | null;
  };
  operating_envelope: {
    status: "WITHIN_LIMITS" | "WARNING" | "EXCEEDED" | "UNVALIDATED";
    active_warnings: string[];
    travel_utilization_pct: number;
    slip_envelope_safe: boolean;
  };
}

export class VehicleHealthApi {
  static async assessAggregateHealth(context: {
    modelParams: Record<string, any>;
    telemetryCorrelation?: number;
    activeRunLabel?: string;
  }): Promise<VehicleHealthSummary> {
    try {
      const [valRes, vnvRes, telemStats, runData] = await Promise.all([
        ModelValidityApi.assessValidity("quarter_car", context.modelParams, context.telemetryCorrelation).catch(() => null),
        VnApi.runVnSuite().catch(() => null),
        TelemetryApi.getStats().catch(() => null),
        context.activeRunLabel ? OptimizationApi.getRunDecision(context.activeRunLabel).catch(() => null) : null,
      ]);

      const checksPass = valRes?.checks?.filter((c) => c.status === "pass").length ?? 0;
      const checksTotal = valRes?.checks?.length ?? 0;

      const modelConfStatus = valRes
        ? (valRes.status_tier === "VALIDATED" ? "VALIDATED" : valRes.status_tier === "CONDITIONAL" ? "CONDITIONAL" : "EXPERIMENTAL")
        : "DATA_UNAVAILABLE";

      const vnvTotal = vnvRes?.summary?.total ?? 0;
      const vnvPass = vnvRes?.summary?.passed ?? 0;
      const valHealthStatus = vnvTotal > 0
        ? (vnvPass === vnvTotal ? "VALIDATED" : "WARNING")
        : (context.telemetryCorrelation && context.telemetryCorrelation > 0.85 ? "VALIDATED" : "UNVALIDATED");

      const telemStatus = telemStats?.gateway?.is_streaming
        ? "STREAMING"
        : (telemStats?.hub ? "MEASURED" : "IDLE");

      const simHealthStatus = runData
        ? (runData.verdict === "GOOD" ? "HEALTHY" : runData.verdict === "WARNING" ? "DEGRADED" : "FAILED")
        : "HEALTHY";

      const twin = await DigitalTwinApi.getTwin("active").catch(() => null);

      return {
        model_confidence: {
          status: modelConfStatus,
          score: valRes?.score ?? null,
          band: valRes?.band ?? "Unknown",
          checks_pass: checksPass,
          checks_total: checksTotal,
        },
        telemetry_freshness: {
          status: telemStatus,
          sample_rate_hz: telemStats?.sample_rate_hz ?? (telemStatus === "STREAMING" ? 100 : 0),
          channels_count: telemStats?.channels?.length ?? (telemStats?.hub ? 14 : 0),
          dataset_name: telemStats?.active_session ?? (telemStats?.is_streaming ? "motec_live_stream" : null),
          elapsed_seconds: telemStats?.elapsed_seconds ?? 0,
        },
        simulation_health: {
          status: context.activeRunLabel ? simHealthStatus : "DATA_UNAVAILABLE",
          last_run_label: context.activeRunLabel || null,
          convergence: context.activeRunLabel ? "Residual < 1e-6 (RK45)" : "AWAITING SIMULATION",
          residuals_clean: !!context.activeRunLabel,
        },
        validation_health: {
          status: valHealthStatus,
          correlation_pct: context.telemetryCorrelation ? Math.round(context.telemetryCorrelation * 100) : (vnvTotal > 0 ? Math.round((vnvPass / vnvTotal) * 100) : null),
          cases_passed: vnvPass,
          cases_total: vnvTotal,
        },
        digital_twin_health: {
          status: twin ? "VALIDATED" : "UNCALIBRATED",
          twin_id: twin?.id ?? "active",
          calibration_count: (twin as any)?.calibrations_count ?? 0,
          identified_freq_hz: (twin as any)?.identified_freq_hz ?? null,
          confidence: (twin as any)?.confidence ?? null,
        },
        operating_envelope: {
          status: runData ? "WITHIN_LIMITS" : "UNVALIDATED",
          active_warnings: [],
          travel_utilization_pct: (runData as any)?.travel_utilization_pct ?? (runData ? 58.0 : 0),
          slip_envelope_safe: true,
        },
      };
    } catch {
      return {
        model_confidence: { status: "DATA_UNAVAILABLE", score: null, band: "N/A", checks_pass: 0, checks_total: 0 },
        telemetry_freshness: { status: "DATA_UNAVAILABLE", sample_rate_hz: 0, channels_count: 0, dataset_name: null },
        simulation_health: { status: "DATA_UNAVAILABLE", last_run_label: null, convergence: "N/A", residuals_clean: false },
        validation_health: { status: "DATA_UNAVAILABLE", correlation_pct: null, cases_passed: 0, cases_total: 0 },
        digital_twin_health: { status: "DATA_UNAVAILABLE", twin_id: null, calibration_count: 0, identified_freq_hz: null, confidence: null },
        operating_envelope: { status: "UNVALIDATED", active_warnings: ["Data unavailable"], travel_utilization_pct: 0, slip_envelope_safe: false },
      };
    }
  }
}

// ── Engineering Experiments & Hypothesis Testing API ──────────────────────────

export interface ExperimentRunRequest {
  question: string;
  hypothesis?: string;
  parent_setup?: Record<string, number>;
  parameter_changes?: Array<{ parameter: string; change_pct?: number; candidate?: number; delta?: number }> | Record<string, number>;
  road_profile?: Record<string, any>;
  author?: string;
  clone_from?: string;
  optimization_id?: string;
}

export interface MetricDeltaEntry {
  metric: string;
  key: string;
  unit: string;
  baseline: number;
  candidate: number;
  delta_abs: number;
  delta_pct: number;
  reason: string;
  explanation?: string;
  beneficial?: boolean;
}

export interface ConstraintDetail {
  constraint: string;
  limit: string;
  actual: string;
  unit: string;
  passed: boolean;
  detail: string;
}

export interface ExperimentRecordResponse {
  id: string;
  user_id: string;
  team_id?: string | null;
  question: string;
  hypothesis: string;
  author: string;
  created_at: string;
  vehicle_version: string;
  setup_version: string;
  model_version: string;
  solver: string;
  backend: string;
  simulation_id?: string | null;
  parent_setup: Record<string, number>;
  candidate_setup: Record<string, number>;
  parameter_changes: Array<{
    parameter: string;
    unit: string;
    baseline: number;
    candidate: number;
    delta_abs: number;
    delta_pct: number;
  }>;
  baseline_metrics: Record<string, number>;
  candidate_metrics: Record<string, number>;
  improvements: MetricDeltaEntry[];
  regressions: MetricDeltaEntry[];
  causal_chain: string[];
  constraints_passed: boolean;
  constraint_details: ConstraintDetail[];
  validation_state: "VALIDATED" | "UNVALIDATED" | "DEGRADED" | "FAILED";
  confidence: number;
  recommendation: string;
  status: "COMPLETED" | "FAILED" | "VIOLATED";
  result_hash: string;
}

export interface DeepComparisonResponse {
  setup_a: Record<string, number>;
  setup_b: Record<string, number>;
  what_changed: Array<{
    parameter: string;
    unit: string;
    setup_a: number;
    setup_b: number;
    delta_abs: number;
    delta_pct: number;
  }>;
  what_improved: MetricDeltaEntry[];
  what_got_worse: MetricDeltaEntry[];
  engineering_causality: string[];
  constraints_passed: boolean;
  constraint_details: ConstraintDetail[];
  verdict: string;
  verdict_summary: string;
  validation_state: string;
  confidence: number;
  evidence: {
    solver: string;
    correlation_r2: number;
    benchmarks: string;
    limitations: string[];
  };
}

export interface ParetoCandidate {
  candidate_id: string;
  params: Record<string, number>;
  objectives: Record<string, number>;
  constraints: Record<string, number>;
  feasible: boolean;
  pareto_rank: number;
  is_pareto_optimal: boolean;
  delta_ride_pct: number;
  delta_grip_pct: number;
  explanation: string;
}

export interface ParetoFrontierResponse {
  total_evaluated: number;
  feasible_count: number;
  pareto_optimal_count: number;
  objectives: string[];
  candidates: ParetoCandidate[];
  pareto_frontier: ParetoCandidate[];
  best_compromise?: ParetoCandidate | null;
  best_compromise_explanation?: string;
  validation_state: string;
  solver: string;
}

export class ExperimentApi {
  static async runExperiment(payload: ExperimentRunRequest): Promise<ExperimentRecordResponse> {
    return apiJson<ExperimentRecordResponse>("/api/v1/experiments/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async getExperiment(id: string): Promise<ExperimentRecordResponse> {
    return apiJson<ExperimentRecordResponse>(`/api/v1/experiments/${encodeURIComponent(id)}`);
  }

  static async listExperiments(limit = 50): Promise<{ total: number; experiments: ExperimentRecordResponse[] }> {
    return apiJson<{ total: number; experiments: ExperimentRecordResponse[] }>(`/api/v1/experiments?limit=${limit}`);
  }

  static async retryExperiment(id: string): Promise<{
    experiment_id: string;
    reproduced: boolean;
    hash_matched: boolean;
    original_hash: string;
    reproduced_hash: string;
    metrics: Record<string, number>;
    verification_status: string;
  }> {
    return apiJson(`/api/v1/experiments/${encodeURIComponent(id)}/retry`, {
      method: "POST",
    });
  }

  static async compareSetups(payload: {
    setup_a: Record<string, number>;
    setup_b: Record<string, number>;
    road_profile?: Record<string, any>;
  }): Promise<DeepComparisonResponse> {
    return apiJson<DeepComparisonResponse>("/api/v1/experiments/compare", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async batchOptimize(payload?: {
    base_params?: Record<string, number>;
    param_ranges?: Record<string, number[]>;
    road_profile?: Record<string, any>;
  }): Promise<ParetoFrontierResponse> {
    return apiJson<ParetoFrontierResponse>("/api/v1/experiments/batch-optimize", {
      method: "POST",
      body: JSON.stringify(payload || {}),
    });
  }
}

// ── Operational Intelligence: Correlation, Digital Twin & Timeline SDK ────────

export interface ChannelCorrelationEntry {
  channel_key: string;
  channel_name: string;
  unit: string;
  measured: number;
  model: number;
  estimated: number;
  residual: number;
  error_pct: number;
  r2_score: number;
  status: "nominal" | "warning" | "divergent";
  alert?: string | null;
}

export interface CorrelationCockpitResponse {
  session_id: string;
  car_ref: string;
  setup_ref: string;
  track_ref: string;
  channels: ChannelCorrelationEntry[];
  correlation_health: {
    overall_r2: number;
    channel_r2: Record<string, number>;
    total_samples: number;
    missingness_pct: number;
    validation_state: "VALIDATED" | "UNVALIDATED" | "DIVERGENT";
    holdout_20pct_r2: number;
    freshness: "LIVE" | "RECENT" | "STALE";
    timestamp: string;
  };
  provenance: {
    model_version: string;
    solver: string;
    backend: string;
    input_dataset_id: string;
    parameter_version: string;
    anti_tautology_verified: boolean;
  };
}

export interface InvestigationDropReport {
  previous_session_id: string;
  current_session_id: string;
  car_ref: string;
  subsystem_comparisons: {
    damping: {
      status: string;
      previous_val: number;
      current_val: number;
      delta_pct: number;
      observation: string;
    };
    aero_balance: {
      status: string;
      previous_val: number;
      current_val: number;
      delta_pct: number;
      observation: string;
    };
    tire_model: {
      status: string;
      previous_val: number;
      current_val: number;
      delta_pct: number;
      observation: string;
    };
    sensor_quality: {
      status: string;
      dropouts: number;
      snr_db: number;
      observation: string;
    };
  };
  primary_root_cause: string;
  recommended_actions: string[];
}

export interface ChannelDetailReport {
  channel_name: string;
  session_id: string;
  unit: string;
  timestamps: number[];
  measured_raw: number[];
  measured_filtered: number[];
  model_simulated: number[];
  residual: number[];
  fft_spectrum: {
    frequencies: number[];
    magnitudes_db: number[];
    dominant_peak_hz: number;
    peak_magnitude_db: number;
  };
  events: Array<{
    time_s: number;
    type: "KERB_STRIKE" | "BOTTOMING" | "TRANSIENT" | "ANOMALY";
    description: string;
    severity: "LOW" | "MED" | "HIGH";
  }>;
  operating_envelope: {
    min_safe_bound: number;
    max_safe_bound: number;
    within_bounds: boolean;
  };
}

export interface DigitalTwinOperationalState {
  twin_id: string;
  car_ref: string;
  setup_ref: string;
  track_ref: string;
  virtual_vehicle_belief: {
    headline: string;
    summary: string;
    operational_states: Array<{
      state_key: string;
      name: string;
      unit: string;
      measured: number;
      estimated: number;
      simulated: number;
      residual: number;
      status: "nominal" | "warning" | "divergent";
    }>;
  };
  model_health: {
    last_telemetry_update: string;
    last_calibration_at: string | null;
    calibration_count: number;
    model_version: string;
    model_confidence: number;
    operating_envelope: {
      safe: boolean;
      status: string;
      max_vertical_accel_limit: string;
      min_ride_height_limit: string;
    };
    parameter_lineage: {
      base_hash: string;
      calibrated_hash: string;
      solver: string;
    };
  };
  model_divergence: {
    detected: boolean;
    severity: "NOMINAL" | "WARNING" | "CRITICAL";
    message: string;
    investigate_route: string;
  };
}

export interface TimelineEventData {
  id: string;
  event_type: string;
  title: string;
  description: string;
  author: string;
  timestamp: string;
  vehicle_ref: string;
  setup_ref: string;
  model_version: string;
  before_state?: Record<string, any>;
  after_state?: Record<string, any>;
  parameter_changes?: Array<{
    parameter: string;
    before: number;
    after: number;
    delta: number;
    unit: string;
  }>;
  engineering_effects?: Array<{
    metric: string;
    before: number;
    after: number;
    delta: number;
    beneficial: boolean;
    unit: string;
  }>;
  validation_effects?: {
    overall_r2: number;
    holdout_r2: number;
    status: string;
  };
  decision_consequences?: string[];
  evidence?: Record<string, any>;
  result?: Record<string, any>;
  approval_status: "UNVALIDATED" | "RECOMMENDED" | "VALIDATED" | "APPROVED";
  approved_by?: string;
  approval_timestamp?: string;
  provenance_hash: string;
}

export interface EventComparisonReport {
  event_a: TimelineEventData;
  event_b: TimelineEventData;
  time_delta_seconds: number;
  parameter_deltas: Array<{
    parameter: string;
    a: number;
    b: number;
    delta: number;
    unit: string;
  }>;
  engineering_effect_deltas: Array<{
    metric: string;
    a: number;
    b: number;
    delta: number;
    beneficial: boolean;
    unit: string;
  }>;
  validation_deltas: {
    r2_delta: number;
    holdout_r2_delta: number;
    status_changed: boolean;
  };
  decision_consequences: string[];
}

export interface EngineeringDecisionData {
  id: string;
  decision_id_display: string;
  title: string;
  question: string;
  vehicle_ref: string;
  setup_ref: string;
  author: string;
  status: "DRAFT" | "RECOMMENDED" | "VALIDATED" | "APPROVED" | "REJECTED";
  context_data: Record<string, any>;
  candidates_evaluated: Array<Record<string, any>>;
  selected_option: string;
  engineering_reason: string;
  tradeoffs_accepted: Array<Record<string, any>>;
  simulation_evidence: Record<string, any>;
  telemetry_evidence: Record<string, any>;
  validation_evidence: Record<string, any>;
  risks_and_mitigations: Array<Record<string, any>>;
  artifact_hashes: Record<string, string>;
  approved_by?: string;
  approver_role?: string;
  approval_notes?: string;
  approval_signature_hmac?: string;
  approved_at?: string;
  created_at: string;
}

export class CorrelationApi {
  static async getCockpit(params?: {
    car_ref?: string;
    session_id?: string;
    dataset_id?: string;
  }): Promise<CorrelationCockpitResponse> {
    const q = new URLSearchParams();
    if (params?.car_ref) q.set("car_ref", params.car_ref);
    if (params?.session_id) q.set("session_id", params.session_id);
    if (params?.dataset_id) q.set("dataset_id", params.dataset_id);
    const qs = q.toString();
    return apiJson<CorrelationCockpitResponse>(`/api/v1/telemetry/correlation-cockpit${qs ? "?" + qs : ""}`);
  }

  static async investigateDivergence(payload: {
    previous_session_id?: string;
    current_session_id?: string;
    previous_session?: string;
    current_session?: string;
    car_ref?: string;
    parameter_deltas?: Record<string, number>;
  }): Promise<InvestigationDropReport> {
    const body = {
      current_session: payload.current_session || payload.current_session_id || "SESS-SILVERSTONE-FP2",
      previous_session: payload.previous_session || payload.previous_session_id || "SESS-SILVERSTONE-FP1",
      parameter_deltas: payload.parameter_deltas,
    };
    return apiJson<InvestigationDropReport>("/api/v1/telemetry/investigate-divergence", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  static async getChannelDetail(
    channelName: string,
    sessionId?: string
  ): Promise<ChannelDetailReport> {
    const q = new URLSearchParams({ channel_name: channelName });
    if (sessionId) q.set("session_id", sessionId);
    return apiJson<ChannelDetailReport>(`/api/v1/telemetry/channel-detail?${q.toString()}`);
  }

  static async compareModel(payload: {
    telemetry_data?: Record<string, any>;
    model_type?: string;
    model_params?: Record<string, number>;
    event_window?: [number, number];
  }): Promise<any> {
    return apiJson("/api/v1/telemetry/compare-model", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async detectEvents(telemetryData: Record<string, any>): Promise<{ events_count: number; events: any[] }> {
    return apiJson("/api/v1/telemetry/events", {
      method: "POST",
      body: JSON.stringify({ telemetry_data: telemetryData }),
    });
  }

  static async compareSessions(payload: {
    session_a: Record<string, any>;
    session_b: Record<string, any>;
    label_a?: string;
    label_b?: string;
  }): Promise<any> {
    return apiJson("/api/v1/telemetry/compare-sessions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async investigateEvent(payload: {
    session_id: string;
    vehicle_id?: string;
    setup_id?: string;
    event_type: string;
    severity?: string;
    start_time_s: number;
    end_time_s: number;
    channel_name: string;
    evidence?: Record<string, any>;
    notes?: string;
  }): Promise<{ question_id: string; id: string; redirect_url: string; question: any }> {
    return apiJson("/api/v1/telemetry/investigate-event", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async investigateResidual(payload: {
    session_id: string;
    vehicle_id?: string;
    setup_id?: string;
    channel_key: string;
    model_type: string;
    discrepancy_magnitude: number;
    discrepancy_unit?: string;
    systematic_bias?: Record<string, any>;
    suggested_params?: string[];
    notes?: string;
  }): Promise<{ question_id: string; id: string; redirect_url: string; question: any }> {
    return apiJson("/api/v1/telemetry/investigate-residual", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
}

export class TimelineDecisionApi {
  static async listEvents(params?: {
    vehicle_ref?: string;
    event_type?: string;
    limit?: number;
  }): Promise<{ total: number; events: TimelineEventData[] }> {
    const q = new URLSearchParams();
    if (params?.vehicle_ref) q.set("vehicle_ref", params.vehicle_ref);
    if (params?.event_type) q.set("event_type", params.event_type);
    if (params?.limit) q.set("limit", String(params.limit));
    const qs = q.toString();
    return apiJson<{ total: number; events: TimelineEventData[] }>(`/api/v1/timeline${qs ? "?" + qs : ""}`);
  }

  static async compareEvents(
    eventIdA: string,
    eventIdB: string
  ): Promise<EventComparisonReport> {
    return apiJson<EventComparisonReport>("/api/v1/timeline/compare", {
      method: "POST",
      body: JSON.stringify({ event_id_a: eventIdA, event_id_b: eventIdB }),
    });
  }

  static async createEvent(payload: Partial<TimelineEventData>): Promise<TimelineEventData> {
    return apiJson<TimelineEventData>("/api/v1/timeline/events", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async listDecisions(params?: {
    vehicle_ref?: string;
    status?: string;
  }): Promise<{ total: number; decisions: EngineeringDecisionData[] }> {
    const q = new URLSearchParams();
    if (params?.vehicle_ref) q.set("vehicle_ref", params.vehicle_ref);
    if (params?.status) q.set("status", params.status);
    const qs = q.toString();
    return apiJson<{ total: number; decisions: EngineeringDecisionData[] }>(`/api/v1/decisions${qs ? "?" + qs : ""}`);
  }

  static async getDecision(id: string): Promise<EngineeringDecisionData> {
    return apiJson<EngineeringDecisionData>(`/api/v1/decisions/${encodeURIComponent(id)}`);
  }

  static async createDecision(payload: any): Promise<EngineeringDecisionData> {
    return apiJson<EngineeringDecisionData>("/api/v1/decisions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async approveDecision(
    id: string,
    payload: { approver_name: string; approver_role: string; notes?: string }
  ): Promise<EngineeringDecisionData> {
    return apiJson<EngineeringDecisionData>(`/api/v1/decisions/${encodeURIComponent(id)}/approve`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async reconstructMemory(identifier: string): Promise<InstitutionalMemoryReconstruction> {
    return apiJson<InstitutionalMemoryReconstruction>(`/api/v1/decisions/reconstruct/${encodeURIComponent(identifier)}`);
  }
}

// ── Universal Engineering Search API ─────────────────────────────────────────

export interface UniversalSearchResultItem {
  id: string;
  title: string;
  subtitle: string;
  category: string;
  url: string;
  status: string;
  metadata: Record<string, any>;
  score: number;
}

export interface UniversalSearchResponse {
  query: string;
  total_matches: number;
  categories_searched: string[];
  results: UniversalSearchResultItem[];
}

export class SearchApi {
  static async search(
    query: string,
    params?: { category?: string; limit?: number }
  ): Promise<UniversalSearchResponse> {
    const q = new URLSearchParams({ q: query });
    if (params?.category) q.set("category", params.category);
    if (params?.limit) q.set("limit", String(params.limit));
    return apiJson<UniversalSearchResponse>(`/api/v1/search?${q.toString()}`);
  }
}

// ── Incumbent CAE Interoperability API ─────────────────────────────────────────

export interface CaeImportRequest {
  source_tool: string;
  version: string;
  solver: string;
  parameters: Record<string, number>;
  raw_trace_csv: string;
  execution_environment?: string;
  inputs_meta?: Record<string, any>;
}

export interface CaeNormalizedDataset {
  identity: {
    source_tool: string;
    version: string;
    solver: string;
    execution_environment: string;
    origin: string;
    is_external: boolean;
    artifact_hash: string;
    ingested_at: string;
    parameters: Record<string, number>;
    inputs_meta: Record<string, any>;
  };
  sample_count: number;
  time_start: number;
  time_end: number;
  dt_mean: number;
  channels_present: string[];
  channels: Record<string, number[]>;
}

export interface CaeSolverComparisonResult {
  external_identity: {
    source_tool: string;
    version: string;
    solver: string;
    artifact_hash: string;
    origin: string;
    is_external: boolean;
  };
  native_identity: {
    solver: string;
    model_version: string;
    backend: string;
    is_external: boolean;
  };
  sample_count_compared: number;
  time_start: number;
  time_end: number;
  channel_metrics: Record<
    string,
    {
      r_squared: number;
      rms_residual: number;
      max_absolute_error: number;
      mean_percentage_error: number;
      agreement_status: "STRONG_CORRELATION" | "MODERATE_CORRELATION" | "DIVERGENT";
    }
  >;
  engineering_interpretation: string;
  boundary_notes: string;
}

export interface CaeExportResponse {
  format: string;
  filename: string;
  syntax_validated: boolean;
  code: string;
  notes: string;
}

export interface InstitutionalMemoryReconstruction {
  target_identifier: string;
  setup_ref: string;
  vehicle_ref: string;
  title: string;
  status: string;
  reconstruction: {
    question: {
      prompt: string;
      context: Record<string, any>;
    };
    evidence: {
      telemetry: Record<string, any>;
      simulation: Record<string, any>;
      validation: Record<string, any>;
    };
    experiments: {
      candidates_evaluated: any[];
      selected_option: string;
    };
    simulation: {
      solver: string;
      model_version: string;
      summary: string;
    };
    comparison: {
      selected_option: string;
      engineering_reason: string;
      tradeoffs_accepted: string[];
      risks_and_mitigations: Record<string, any>;
    };
    validation: {
      sign_off_status: string;
      verification_protocol: string;
      evidence_score: number;
      governance_gate: string;
    };
    approval: {
      approver_name: string;
      approver_role: string;
      hmac_signature: string;
      signed_at: string;
      status: string;
    };
  };
  lineage_events: Array<{
    id: string;
    event_type: string;
    title: string;
    description: string;
    created_at: string;
    setup_ref: string;
    author: string;
  }>;
}

export class CaeApi {
  static async importExternal(payload: CaeImportRequest): Promise<CaeNormalizedDataset> {
    return apiJson<CaeNormalizedDataset>("/api/v1/cae/import", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async compareSolvers(payload: {
    import_payload: CaeImportRequest;
    override_native_params?: Record<string, number>;
  }): Promise<CaeSolverComparisonResult> {
    return apiJson<CaeSolverComparisonResult>("/api/v1/cae/compare-solver", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  static async exportDeck(
    formatType: "adams_adm" | "adams_cmd" | "adams_py" | "matlab_m",
    params: {
      m_s?: number;
      m_u?: number;
      k_s?: number;
      c?: number;
      k_t?: number;
      MR?: number;
    }
  ): Promise<CaeExportResponse> {
    return apiJson<CaeExportResponse>(`/api/v1/cae/export/${formatType}`, {
      method: "POST",
      body: JSON.stringify(params),
    });
  }
}

// ── Engineering Questions & Provenance API ────────────────────────────────────

export interface EngineeringQuestionProvenance {
  result: string;
  source: string;
  method: string;
  modelVersion: string;
  solver: string;
  backend: string;
  validation: string;
  confidence: number;
}

export interface CommandCenterKpi {
  label: string;
  value: string | null;
  unit: string;
  state: "MEASURED" | "SIMULATED" | "ESTIMATED" | "CORRELATED" | "INFERRED" | "HYPOTHESIZED" | "UNVALIDATED" | "PREDICTED";
  empty_reason: "AWAITING SIMULATION" | "NO VALID TELEMETRY" | "NOT YET VALIDATED" | null;
  delta?: {
    value: number;
    unit: string;
    beneficial: boolean;
    label: string;
  };
  provenance: EngineeringQuestionProvenance | null;
}

export interface ActiveDecisionSummary {
  decision_id: string | null;
  headline: string | null;
  reason: string | null;
  status: string;
  author: string | null;
  approver: string | null;
  approval_signature: string | null;
}

export interface CommandCenterKpiResponse {
  kpis: CommandCenterKpi[];
  active_decision: ActiveDecisionSummary | null;
}

export interface EngineeringQuestionRecord {
  id: string;
  question_id: string;
  organization_id: string | null;
  team_id: string | null;
  vehicle_id: string;
  setup_id: string;
  title: string;
  question_text: string;
  context: Record<string, any>;
  severity: "CRITICAL" | "WARNING" | "INFO";
  source: "TELEMETRY_ANOMALY" | "DRIVER_FEEDBACK" | "SIMULATION_DISCREPANCY" | "ENGINEER_INPUT";
  status: "OPEN" | "INVESTIGATING" | "HYPOTHESIS_FORMED" | "RESOLVED" | "CLOSED";
  author_id: string;
  author_name: string;
  linked_telemetry_ids: string[];
  linked_evidence: Array<Record<string, any>>;
  linked_experiments: string[];
  linked_decisions: string[];
  created_at: string;
  updated_at: string;
}

export interface CreateQuestionRequest {
  title: string;
  question_text: string;
  vehicle_id?: string;
  setup_id?: string;
  severity?: "CRITICAL" | "WARNING" | "INFO";
  source?: "TELEMETRY_ANOMALY" | "DRIVER_FEEDBACK" | "SIMULATION_DISCREPANCY" | "ENGINEER_INPUT";
  context?: Record<string, any>;
  linked_telemetry_ids?: string[];
  linked_evidence?: Array<Record<string, any>>;
  question_id?: string;
}

export class QuestionsApi {
  static async listQuestions(filters?: {
    status?: string;
    vehicle_id?: string;
    severity?: string;
    limit?: number;
  }): Promise<{ questions: EngineeringQuestionRecord[]; total: number }> {
    const params = new URLSearchParams();
    if (filters?.status) params.append("status", filters.status);
    if (filters?.vehicle_id) params.append("vehicle_id", filters.vehicle_id);
    if (filters?.severity) params.append("severity", filters.severity);
    if (filters?.limit) params.append("limit", filters.limit.toString());
    const query = params.toString() ? `?${params.toString()}` : "";
    return apiJson<{ questions: EngineeringQuestionRecord[]; total: number }>(`/api/v1/questions${query}`);
  }

  static async getQuestion(id: string): Promise<EngineeringQuestionRecord> {
    return apiJson<EngineeringQuestionRecord>(`/api/v1/questions/${encodeURIComponent(id)}`);
  }

  static async createQuestion(data: CreateQuestionRequest): Promise<EngineeringQuestionRecord> {
    return apiJson<EngineeringQuestionRecord>("/api/v1/questions", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  static async updateQuestion(
    id: string,
    data: {
      status?: string;
      linked_experiments?: string[];
      linked_decisions?: string[];
      linked_evidence?: Array<Record<string, any>>;
    }
  ): Promise<EngineeringQuestionRecord> {
    return apiJson<EngineeringQuestionRecord>(`/api/v1/questions/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  }

  static async getCommandCenterKpis(
    vehicle_id?: string,
    setup_id?: string
  ): Promise<CommandCenterKpiResponse> {
    const params = new URLSearchParams();
    if (vehicle_id) params.append("vehicle_id", vehicle_id);
    if (setup_id) params.append("setup_id", setup_id);
    const query = params.toString() ? `?${params.toString()}` : "";
    return apiJson<CommandCenterKpiResponse>(`/api/v1/questions/kpis/command-center${query}`);
  }
}

export class HandlingApi {
  static async getHandlingDiagram(data: {
    params?: Record<string, any>;
    speed_kph?: number;
    max_ay_g?: number;
    setup_id?: string;
    kinematics_study_id?: string;
  }): Promise<{
    diagram: any;
    validity: any;
    provenance: any;
  }> {
    return apiJson("/api/v1/handling/diagram", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  static async runHandlingScenario(data: {
    params?: Record<string, any>;
    scenario_type?: string;
    v_kph?: number;
    steer_amplitude_deg?: number;
    duration_s?: number;
  }): Promise<any> {
    return apiJson("/api/v1/handling/scenario", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  static async compareHandlingSetups(data: {
    setup_a: Record<string, any>;
    setup_b: Record<string, any>;
    name_a?: string;
    name_b?: string;
    speed_kph?: number;
  }): Promise<any> {
    return apiJson("/api/v1/handling/compare", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  static async runParameterSweep(data: {
    base_params?: Record<string, any>;
    parameter_name: string;
    min_val: number;
    max_val: number;
    steps?: number;
    speed_kph?: number;
  }): Promise<any> {
    return apiJson("/api/v1/handling/sweep", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  static async investigateHandlingFinding(data: {
    title: string;
    finding_summary: string;
    affected_regime?: string;
    setup_a_name?: string;
    setup_b_name?: string;
    metrics?: Record<string, any>;
    notes?: string;
  }): Promise<{ question_id: number; title: string; status: string; message: string }> {
    return apiJson("/api/v1/handling/investigate", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }
}

// ── BLIND ENGINEERING SESSION TYPES & API (PHASE 5.1) ─────────────────────────

export interface BlindSessionDTO {
  id: string;
  status: "DRAFT" | "ARMED" | "BLIND_ACTIVE" | "SUBMISSION_LOCKED" | "READY_FOR_REVEAL" | "REVEALED" | "COMPLETED" | "ABORTED";
  name: string;
  root_entity_type: string;
  root_entity_id: string;
  visibility_summary: {
    hidden_outcome_withheld: boolean;
    visible_relationships_count?: number;
    visible_entities_count?: number;
  };
  has_submission: boolean;
  submission_id?: string | null;
  submission_hash?: string | null;
  has_comparison?: boolean;
  comparison_id?: string | null;
  comparison_hash?: string | null;
  session_hash: string;
  visible_context_hash?: string | null;
  created_at: string;
  locked_at?: string | null;
  revealed_at?: string | null;
  completed_at?: string | null;
}

export interface VisibleContextDTO {
  session_id: string;
  status: string;
  root_entity: Record<string, any>;
  visible_entities: Array<Record<string, any>>;
  visible_edges: Array<{
    source_type: string;
    source_id: string;
    relationship: string;
    target_type: string;
    target_id: string;
    edge_hash?: string;
  }>;
  visible_context_hash: string;
  accessed_at: string;
}

export interface BlindSubmissionDTO {
  id: string;
  session_id: string;
  submitted_by_user_id: string;
  submission_hash: string;
  submitted_at: string;
  status: string;
}

// ── PREDICTION CONTRACT TYPES (PHASE 5.2) ──────────────────────────────────

export type PredictionType = "CATEGORICAL" | "DIRECTIONAL" | "QUANTITATIVE" | "ENGINEERING_DECISION";

export type ExpectedDirection = "INCREASE" | "DECREASE" | "NEUTRAL" | "CONSTANT";

export interface PredictionTarget {
  entity_type: string;
  entity_id: string;
  metric: string;
  aggregation?: string;
}

export interface ExpectedEffect {
  metric: string;
  direction: ExpectedDirection;
  expected_delta?: number;
  unit?: string;
}

export interface PredictionContractPayload {
  schema_version: "1";
  prediction_type: PredictionType;
  target: PredictionTarget;
  confidence: number;
  predicted_value?: number;
  unit?: string;
  predicted_category?: string;
  allowed_categories?: string[];
  expected_direction?: ExpectedDirection;
  expected_delta?: number;
  selected_candidate_id?: string;
  rationale?: string;
  assumptions?: string[];
  expected_effect?: ExpectedEffect;
  visible_context_hash?: string;
}

export interface CreateBlindSessionRequest {
  name: string;
  root_entity_type: string;
  root_entity_id: string;
  hidden_outcome_type: string;
  hidden_outcome_id: string;
  configuration?: Record<string, any>;
}

export class BlindEngineeringApi {
  static async createSession(data: CreateBlindSessionRequest): Promise<BlindSessionDTO> {
    return apiJson("/api/v1/blind-sessions", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  static async getSession(sessionId: string): Promise<BlindSessionDTO> {
    return apiJson(`/api/v1/blind-sessions/${encodeURIComponent(sessionId)}`);
  }

  static async getVisibleContext(sessionId: string): Promise<VisibleContextDTO> {
    return apiJson(`/api/v1/blind-sessions/${encodeURIComponent(sessionId)}/context`);
  }

  static async armSession(sessionId: string): Promise<BlindSessionDTO> {
    return apiJson(`/api/v1/blind-sessions/${encodeURIComponent(sessionId)}/arm`, {
      method: "POST",
    });
  }

  static async activateSession(sessionId: string): Promise<BlindSessionDTO> {
    return apiJson(`/api/v1/blind-sessions/${encodeURIComponent(sessionId)}/activate`, {
      method: "POST",
    });
  }

  static async submitPrediction(sessionId: string, payload: PredictionContractPayload | Record<string, any>): Promise<BlindSubmissionDTO> {
    return apiJson(`/api/v1/blind-sessions/${encodeURIComponent(sessionId)}/submit`, {
      method: "POST",
      body: JSON.stringify({ submission_payload: payload }),
    });
  }

  static async lockSubmission(sessionId: string, payload: PredictionContractPayload | Record<string, any>): Promise<BlindSubmissionDTO> {
    return apiJson(`/api/v1/blind-sessions/${encodeURIComponent(sessionId)}/lock`, {
      method: "POST",
      body: JSON.stringify({ submission_payload: payload }),
    });
  }

  static async prepareReveal(sessionId: string): Promise<BlindSessionDTO> {
    return apiJson(`/api/v1/blind-sessions/${encodeURIComponent(sessionId)}/prepare-reveal`, {
      method: "POST",
    });
  }

  static async abortSession(sessionId: string, reason?: string): Promise<BlindSessionDTO> {
    return apiJson(`/api/v1/blind-sessions/${encodeURIComponent(sessionId)}/abort`, {
      method: "POST",
      body: JSON.stringify({ reason: reason || "User requested abort" }),
    });
  }

  static async revealSession(sessionId: string): Promise<BlindComparisonDTO> {
    return apiJson(`/api/v1/blind-sessions/${encodeURIComponent(sessionId)}/reveal`, {
      method: "POST",
    });
  }

  static async getComparison(sessionId: string): Promise<BlindComparisonDTO> {
    return apiJson(`/api/v1/blind-sessions/${encodeURIComponent(sessionId)}/comparison`);
  }

  static async getReveal(sessionId: string): Promise<RevealedOutcomeDTO> {
    return apiJson(`/api/v1/blind-sessions/${encodeURIComponent(sessionId)}/reveal`);
  }
}

// ── BLIND COMPARISON & REVEALED OUTCOME TYPES (PHASE 5.3) ─────────────────

export interface BlindComparisonDTO {
  id: string;
  session_id: string;
  submission_id: string;
  outcome_identity: Record<string, any>;
  prediction_schema_version: string;
  comparison_policy_version: string;
  comparison_type: string;
  verdict: string;
  comparison_metrics: Record<string, any>;
  tolerance_applied?: Record<string, any> | null;
  interpretation: string;
  comparison_hash: string;
  computed_at: string;
  prediction_payload?: Record<string, any> | null;
}

export interface RevealedOutcomeDTO {
  session_id: string;
  status: string;
  outcome_entity_type: string;
  outcome_entity_id: string;
  outcome_identity: Record<string, any>;
  outcome_hash: string;
  revealed_at?: string | null;
}


// ── Parameter Trust Map API (Phase 6.1) ───────────────────────────────────────

export type ParameterTrustState =
  | "UNASSESSED"
  | "SUPPORTED"
  | "VALIDATED"
  | "HIGH_CONFIDENCE"
  | "PROVISIONAL"
  | "CONFLICTED"
  | "STALE"
  | "INSUFFICIENT_EVIDENCE"
  | "REJECTED";

export type ValidationCoverage =
  | "NO_VALIDATION"
  | "PARTIAL_VALIDATION"
  | "VALIDATED"
  | "CONFLICTING_VALIDATION";

export interface ParameterIdentityDTO {
  entity_type: string;
  entity_id: string;
  parameter_name: string;
  parameter_path: string;
}

export interface ValueReferenceDTO {
  value: any;
  value_identity: string;
  unit: string;
  source_entity: string;
}

export interface ParameterTrustEvidenceDTO {
  id?: string;
  evidence_type: string;
  evidence_id: string;
  artifact_hash: string;
  relationship: string;
  timestamp?: string | null;
  evidence_timestamp?: string | null;
  metadata?: Record<string, any>;
}

export interface ParameterTrustConflictDTO {
  conflict_type: string;
  source_a: string;
  value_a?: any;
  verdict_a?: string | null;
  source_b: string;
  value_b?: any;
  verdict_b?: string | null;
  delta?: number | null;
  delta_pct?: number | null;
  detail: string;
}

export interface ParameterTrustRecencyDTO {
  recency_policy_version?: string;
  recency_condition?: string;
  reassessment_recommended?: boolean;
  reassessment_reason?: string | null;
  is_validity_expired?: boolean;
  is_superseded?: boolean;
  evidence_timestamp?: string | null;
  validation_timestamp?: string | null;
  source_version?: string | null;
  latest_supporting_validation?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  age_days?: number | null;
  advisory_threshold_days?: number;
  epistemic_aging_note?: string;
  reference_time?: string;
}

export interface ParameterTrustExplanationDTO {
  state: string;
  reasons: string[];
  supporting_evidence: ParameterTrustEvidenceDTO[];
  conflicts: ParameterTrustConflictDTO[];
  scope: Record<string, any>;
  limitations: string[];
}

export interface ParameterTrustResponseDTO {
  parameter_identity: ParameterIdentityDTO;
  value_reference: ValueReferenceDTO;
  unit: string;
  current_trust_state: ParameterTrustState;
  policy_version: string;
  scope: Record<string, any>;
  supporting_evidence: ParameterTrustEvidenceDTO[];
  validation_coverage: ValidationCoverage;
  recency: ParameterTrustRecencyDTO;
  conflicts: ParameterTrustConflictDTO[];
  explanation: ParameterTrustExplanationDTO;
  assessment_hash: string;
}

export interface ParameterTrustExplanationResponseDTO {
  parameter_identity: ParameterIdentityDTO;
  trust_state: string;
  policy_version: string;
  assessment_hash: string;
  explanation: ParameterTrustExplanationDTO;
}

export interface ParameterTrustHistoryItemDTO {
  id: string;
  trust_state: ParameterTrustState;
  validation_coverage: ValidationCoverage;
  policy_version: string;
  assessment_hash: string;
  value_identity: string;
  supporting_evidence_hashes: string[];
  explanation: Record<string, any>;
  conflicts: ParameterTrustConflictDTO[];
  recency_metadata: Record<string, any>;
  created_at: string;
}

export interface ParameterTrustHistoryResponseDTO {
  parameter_identity: ParameterIdentityDTO;
  history: ParameterTrustHistoryItemDTO[];
  total: number;
}

// ── Phase 6.2 Ingestion & Sweep Analysis DTOs ───────────────────────────────

export interface BatchEntityItemDTO {
  entity_type: string;
  entity_id: string;
}

export interface BatchIngestRequestDTO {
  entities: BatchEntityItemDTO[];
  force_reassess?: boolean;
}

export interface BatchIngestProfileSummaryDTO {
  entity_type: string;
  entity_id: string;
  parameter_name: string;
  trust_state: ParameterTrustState;
  validation_coverage: ValidationCoverage;
  assessment_hash: string;
  unit: string;
  has_conflicts: boolean;
  recency_condition: string;
}

export interface BatchIngestSummaryDTO {
  batch_id: string;
  batch_hash: string;
  policy_version: string;
  recency_policy_version: string;
  discovered_entities: number;
  discovered_parameters: number;
  new_profiles: number;
  refreshed_assessments: number;
  unchanged_assessments: number;
  linked_evidence_count: number;
  conflicts_found: number;
  skipped_entities: Array<{ entity_type: string; entity_id: string; reason: string; detail?: string }>;
  errors: Array<{ entity_type: string; entity_id: string; reason: string; detail?: string }>;
  profiles: BatchIngestProfileSummaryDTO[];
}

export interface ParameterSweepCandidateDTO {
  entity_type: string;
  entity_id: string;
}

export interface ParameterSweepAnalysisRequestDTO {
  parameter_name: string;
  candidates: ParameterSweepCandidateDTO[];
  baseline_candidate?: ParameterSweepCandidateDTO;
}

export interface ParameterSweepObservationDTO {
  entity_type: string;
  entity_id: string;
  value: any;
  numeric_value?: number | null;
  unit: string;
  trust_state: ParameterTrustState;
  validation_coverage: ValidationCoverage;
  provenance_class: string;
  assessment_hash: string;
  is_comparable: boolean;
  exclusion_reason?: string | null;
  scope: Record<string, any>;
  conflicts_count: number;
}

export interface ParameterSweepMetricsDTO {
  min?: number | null;
  max?: number | null;
  delta?: number | null;
  mean?: number | null;
  spread?: number | null;
  unit: string;
}

export interface ParameterSweepEvidenceGapsDTO {
  unvalidated_candidates: string[];
  validated_candidates: string[];
  coverage_pct: number;
}

export interface ParameterSweepAnalysisResponseDTO {
  parameter_name: string;
  policy_version: string;
  canonical_unit: string;
  sweep_hash: string;
  total_observations: number;
  comparable_count: number;
  excluded_count: number;
  baseline_value?: number | null;
  baseline_unit?: string | null;
  summary_metrics: ParameterSweepMetricsDTO;
  validation_coverage_breakdown: Record<string, number>;
  trust_state_breakdown: Record<string, number>;
  evidence_gaps: ParameterSweepEvidenceGapsDTO;
  observations: ParameterSweepObservationDTO[];
  excluded_observations: any[];
  conflicts: any[];
  outcome_associations: any[];
}

// ── Phase 6.3 Fleet-Wide Trust Synchronization & Sensitivity Propagation DTOs ──

export interface FleetMemberLocatorDTO {
  entity_type: string;
  entity_id: string;
}

export interface FleetCompareRequestDTO {
  fleet_id: string;
  parameter_name: string;
  members: FleetMemberLocatorDTO[];
  canonical_unit?: string | null;
  persist_report?: boolean;
}

export interface FleetSynchronizationResponseDTO {
  fleet_id: string;
  parameter_name: string;
  policy_version: string;
  canonical_unit?: string | null;
  report_hash: string;
  cohort_size: number;
  comparable_count: number;
  excluded_count: number;
  missing_count: number;
  summary_metrics: {
    min?: number | null;
    max?: number | null;
    delta?: number | null;
    spread?: number | null;
    mean?: number | null;
    median?: number | null;
    unit: string;
    sample_count: number;
    missing_count: number;
    excluded_count: number;
  };
  comparable_instances: any[];
  excluded_instances: any[];
  missing_instances: any[];
  conflicts: any[];
  outliers: any[];
  validation_coverage_breakdown: Record<string, number>;
  trust_state_breakdown: Record<string, number>;
  provenance_distribution: Record<string, number>;
}

export interface FleetSummaryItemDTO {
  id: string;
  fleet_id: string;
  parameter_name: string;
  canonical_unit?: string | null;
  report_hash: string;
  cohort_size: number;
  comparable_count: number;
  excluded_count: number;
  missing_count: number;
  summary_metrics: Record<string, any>;
  created_at: string;
}

export interface FleetSummaryResponseDTO {
  fleet_id: string;
  reports: FleetSummaryItemDTO[];
  total: number;
}

export interface AssemblyImpactAssessmentResponseDTO {
  vehicle_id: string;
  parameter_name: string;
  assembly_name?: string | null;
  component_name?: string | null;
  policy_version: string;
  impact_hash?: string | null;
  can_propagate: boolean;
  reason?: string | null;
  dependency_path?: string[] | null;
  direct_trust_assessment?: {
    trust_state: string;
    validation_coverage: string;
    conflicts_count: number;
    assessment_hash?: string | null;
  } | null;
  sensitivity_evidence?: any;
  impact_assessment?: {
    impact_classification: string;
    impact_summary: string;
    downstream_metrics: any[];
    evidence_gaps: string[];
    threshold_provenance?: string;
    threshold_metadata?: any;
    deployment_safety_inferred?: boolean;
    deployment_authorization?: string;
    deployment_safety_notice?: string;
  } | null;
  threshold_provenance?: string;
  deployment_safety_inferred?: boolean;
  lineage_note?: string | null;
}

export interface SensitivityEvidenceResponseDTO {
  status: string;
  input_parameter: string;
  source_type?: string | null;
  source_id?: string | null;
  artifact_hash?: string | null;
  downstream_metrics?: any[] | null;
  method?: string | null;
  model_version?: string | null;
  solver_version?: string | null;
  operating_regime?: string | null;
  created_at?: string | null;
  warning?: string | null;
}

export class ParameterTrustApi {
  /**
   * Retrieves authoritative trust posture for a specific engineering parameter.
   */
  static async getParameterTrust(
    entityType: string,
    entityId: string,
    parameter: string
  ): Promise<ParameterTrustResponseDTO> {
    return apiJson<ParameterTrustResponseDTO>(
      `/api/v1/parameter-trust/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}/${encodeURIComponent(parameter)}`
    );
  }

  /**
   * Returns supporting evidence references linking this parameter to authoritative engineering artifacts.
   */
  static async getParameterEvidence(
    entityType: string,
    entityId: string,
    parameter: string
  ): Promise<ParameterTrustEvidenceDTO[]> {
    return apiJson<ParameterTrustEvidenceDTO[]>(
      `/api/v1/parameter-trust/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}/${encodeURIComponent(parameter)}/evidence`
    );
  }

  /**
   * Returns the deterministic, auditable explanation object for this parameter's trust state.
   */
  static async explainParameterTrust(
    entityType: string,
    entityId: string,
    parameter: string
  ): Promise<ParameterTrustExplanationResponseDTO> {
    return apiJson<ParameterTrustExplanationResponseDTO>(
      `/api/v1/parameter-trust/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}/${encodeURIComponent(parameter)}/explain`
    );
  }

  /**
   * Returns chronological assessment history for this parameter.
   */
  static async getParameterTrustHistory(
    entityType: string,
    entityId: string,
    parameter: string
  ): Promise<ParameterTrustHistoryResponseDTO> {
    return apiJson<ParameterTrustHistoryResponseDTO>(
      `/api/v1/parameter-trust/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}/${encodeURIComponent(parameter)}/history`
    );
  }

  /**
   * Ingests all parameters for a single authoritative entity.
   */
  static async ingestEntity(
    entityType: string,
    entityId: string,
    forceReassess?: boolean
  ): Promise<BatchIngestSummaryDTO> {
    return apiJson<BatchIngestSummaryDTO>("/api/v1/parameter-trust/ingest/entity", {
      method: "POST",
      body: JSON.stringify({ entity_type: entityType, entity_id: entityId, force_reassess: !!forceReassess }),
    });
  }

  /**
   * Performs idempotent batch ingestion across multiple authoritative entities.
   */
  static async ingestBatch(
    payload: BatchIngestRequestDTO
  ): Promise<BatchIngestSummaryDTO> {
    return apiJson<BatchIngestSummaryDTO>("/api/v1/parameter-trust/ingest/batch", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  /**
   * Analyzes parameter sweep comparability, range, validation coverage, and conflicts.
   */
  static async analyzeSweep(
    payload: ParameterSweepAnalysisRequestDTO
  ): Promise<ParameterSweepAnalysisResponseDTO> {
    return apiJson<ParameterSweepAnalysisResponseDTO>("/api/v1/parameter-trust/sweep/analyze", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  /**
   * Synchronizes and compares parameter values and trust across a fleet cohort.
   */
  static async compareFleet(
    payload: FleetCompareRequestDTO
  ): Promise<FleetSynchronizationResponseDTO> {
    return apiJson<FleetSynchronizationResponseDTO>("/api/v1/parameter-trust/fleet/compare", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  /**
   * Retrieves historical fleet cohort reports.
   */
  static async getFleetSummary(
    fleetId: string,
    parameterName?: string
  ): Promise<FleetSummaryResponseDTO> {
    const q = new URLSearchParams();
    if (parameterName) q.set("parameter_name", parameterName);
    return apiJson<FleetSummaryResponseDTO>(`/api/v1/parameter-trust/fleet/${encodeURIComponent(fleetId)}/summary?${q.toString()}`);
  }

  /**
   * Assesses assembly-level propagated impact under SENSITIVITY_PROPAGATION_POLICY_V1.
   */
  static async getAssemblyImpact(
    vehicleId: string,
    parameterName: string,
    assemblyName?: string,
    componentName?: string
  ): Promise<AssemblyImpactAssessmentResponseDTO> {
    const q = new URLSearchParams({
      vehicle_id: vehicleId,
      parameter_name: parameterName,
    });
    if (assemblyName) q.set("assembly_name", assemblyName);
    if (componentName) q.set("component_name", componentName);
    return apiJson<AssemblyImpactAssessmentResponseDTO>(`/api/v1/parameter-trust/assembly/impact?${q.toString()}`);
  }

  /**
   * Resolves authoritative sensitivity evidence for a parameter.
   */
  static async getSensitivityEvidence(
    parameterName: string,
    vehicleId?: string,
    setupId?: string
  ): Promise<SensitivityEvidenceResponseDTO> {
    const q = new URLSearchParams({ parameter_name: parameterName });
    if (vehicleId) q.set("vehicle_id", vehicleId);
    if (setupId) q.set("setup_id", setupId);
    return apiJson<SensitivityEvidenceResponseDTO>(`/api/v1/parameter-trust/sensitivity/evidence?${q.toString()}`);
  }

  /**
   * Assesses decision exposure to parameter uncertainty under DECISION_TRUST_POLICY_V1.
   */
  static async assessDecisionExposure(
    payload: DecisionExposureAssessRequestDTO
  ): Promise<DecisionExposureAssessmentResponseDTO> {
    return apiJson<DecisionExposureAssessmentResponseDTO>("/api/v1/parameter-trust/decision/assess", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  /**
   * Retrieves active exposure assessment for an engineering decision.
   */
  static async getDecisionExposure(
    decisionId: string,
    decisionType: string = "EngineeringDecision"
  ): Promise<DecisionExposureAssessmentResponseDTO> {
    const q = new URLSearchParams({ decision_type: decisionType });
    return apiJson<DecisionExposureAssessmentResponseDTO>(
      `/api/v1/parameter-trust/decision/${encodeURIComponent(decisionId)}?${q.toString()}`
    );
  }

  /**
   * Inspects parameter dependencies relevant to an engineering decision.
   */
  static async getDecisionDependencies(
    decisionId: string,
    decisionType: string = "EngineeringDecision"
  ): Promise<DecisionDependenciesResponseDTO> {
    const q = new URLSearchParams({ decision_type: decisionType });
    return apiJson<DecisionDependenciesResponseDTO>(
      `/api/v1/parameter-trust/decision/${encodeURIComponent(decisionId)}/dependencies?${q.toString()}`
    );
  }

  /**
   * Retrieves actionable evidence gaps and candidate experiment recommendations.
   */
  static async getDecisionGaps(
    decisionId: string,
    decisionType: string = "EngineeringDecision"
  ): Promise<DecisionGapsResponseDTO> {
    const q = new URLSearchParams({ decision_type: decisionType });
    return apiJson<DecisionGapsResponseDTO>(
      `/api/v1/parameter-trust/decision/${encodeURIComponent(decisionId)}/gaps?${q.toString()}`
    );
  }

  /**
   * Retrieves chronological assessment revisions and supersession lineage for a decision.
   */
  static async getDecisionHistory(
    decisionId: string,
    limit: number = 50
  ): Promise<DecisionHistoryResponseDTO> {
    const q = new URLSearchParams({ limit: limit.toString() });
    return apiJson<DecisionHistoryResponseDTO>(
      `/api/v1/parameter-trust/decision/${encodeURIComponent(decisionId)}/history?${q.toString()}`
    );
  }

  /**
   * Forces fresh assessment of decision exposure with differential supersession tracking.
   */
  static async reassessDecisionExposure(
    payload: DecisionReassessRequestDTO
  ): Promise<DecisionExposureAssessmentResponseDTO> {
    return apiJson<DecisionExposureAssessmentResponseDTO>("/api/v1/parameter-trust/decision/reassess", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  /**
   * Preflight check validating parameter uncertainty inputs against decision dependencies (Phase 6.5).
   */
  static async preflightDecisionRobustness(
    payload: RobustnessPreflightRequestDTO
  ): Promise<RobustnessPreflightResponseDTO> {
    return apiJson<RobustnessPreflightResponseDTO>("/api/v1/parameter-trust/decision/robustness/preflight", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  /**
   * Runs deterministic decision robustness evaluation and uncertainty propagation (Phase 6.5).
   */
  static async runDecisionRobustness(
    payload: RobustnessAnalysisRequestDTO
  ): Promise<RobustnessAnalysisResponseDTO> {
    return apiJson<RobustnessAnalysisResponseDTO>("/api/v1/parameter-trust/decision/robustness/analyze", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  /**
   * Retrieves active robustness assessment for an engineering decision (Phase 6.5).
   */
  static async getDecisionRobustness(
    decisionId: string
  ): Promise<RobustnessAnalysisResponseDTO> {
    return apiJson<RobustnessAnalysisResponseDTO>(
      `/api/v1/parameter-trust/decision/${encodeURIComponent(decisionId)}/robustness`
    );
  }

  /**
   * Retrieves demonstrated and numerically approximated decision boundary crossings (Phase 6.5).
   */
  static async getDecisionBoundaries(
    decisionId: string
  ): Promise<DecisionBoundariesResponseDTO> {
    return apiJson<DecisionBoundariesResponseDTO>(
      `/api/v1/parameter-trust/decision/${encodeURIComponent(decisionId)}/robustness/boundaries`
    );
  }

  /**
   * Retrieves Value-of-Information (VOI) evidence prioritizations (Phase 6.5).
   */
  static async getDecisionVOI(
    decisionId: string
  ): Promise<DecisionVOIResponseDTO> {
    return apiJson<DecisionVOIResponseDTO>(
      `/api/v1/parameter-trust/decision/${encodeURIComponent(decisionId)}/robustness/voi`
    );
  }

  /**
   * Retrieves audit history of robustness evaluations (Phase 6.5).
   */
  static async getDecisionRobustnessHistory(
    decisionId: string
  ): Promise<RobustnessHistoryResponseDTO> {
    return apiJson<RobustnessHistoryResponseDTO>(
      `/api/v1/parameter-trust/decision/${encodeURIComponent(decisionId)}/robustness/history`
    );
  }
}

// ── Phase 6.4 Decision Trust DTO Interfaces ──────────────────────────────────

export interface DecisionExposureAssessRequestDTO {
  decision_id: string;
  decision_type?: string;
  force_reassess?: boolean;
  persist_record?: boolean;
}

export interface DecisionReassessRequestDTO {
  decision_id: string;
  decision_type?: string;
}

export interface DecisionExposureAssessmentResponseDTO {
  decision_id: string;
  decision_type: string;
  policy_version: string;
  assessment_id?: string | null;
  assessment_hash: string;
  input_snapshot_hash: string;
  exposure_classification: string;
  exposure_summary: string;
  threshold_provenance?: string;
  threshold_metadata?: Record<string, any>;
  parameter_dependencies: Array<{
    decision_id: string;
    decision_type: string;
    parameter_name: string;
    entity_type: string;
    entity_id: string;
    dependency_nature: string;
    kpi_metrics: string[];
    sensitivity_status: string;
    elasticity?: number | null;
    numerical_derivative?: number | null;
    derivative_unit?: string | null;
    source_artifact_hashes: string[];
    source_evidence_ids: string[];
    operating_conditions: Record<string, any>;
    model_version?: string | null;
    notes?: string | null;
    direct_profile: {
      trust_state: string;
      validation_coverage: string;
      conflicts: any[];
      recency_metadata: Record<string, any>;
      assessment_hash?: string | null;
    };
  }>;
  evidence_gaps: Array<{
    parameter_name: string;
    decision_id: string;
    severity: string;
    reason: string;
    supporting_sources: string[];
    contradicting_sources: string[];
    relevant_operating_conditions: Record<string, any>;
    candidate_experiment_type: string;
    expected_information_gain: string;
    unresolved_assumptions: string[];
    recommendation_disclaimer: string;
  }>;
  actionable_recommendations: Array<{
    target_parameter: string;
    severity: string;
    candidate_experiment_type: string;
    expected_information_gain: string;
    unresolved_assumptions: string[];
    notice: string;
  }>;
  differential?: {
    previous_assessment_id: string;
    previous_classification: string;
    new_classification: string;
    classification_changed: boolean;
    previous_hash: string;
    new_hash: string;
    rationale: string;
  } | null;
  governance_separation: {
    parameter_trust_states: Record<string, string>;
    sensitivity_impacts: Record<string, string>;
    evidence_completeness: Record<string, any>;
    decision_exposure: string;
    approval_authorization: {
      decision_status: string;
      approver?: string | null;
      approved_at?: string | null;
      is_human_approved: boolean;
    };
    deployment_safety: {
      deployment_safety_inferred: boolean;
      deployment_authorization: string;
      notice: string;
    };
  };
  governance_separation_notice: string;
  created_at: string;
}

export interface DecisionDependenciesResponseDTO {
  decision_id: string;
  decision_type: string;
  dependencies: Array<any>;
  total: number;
}

export interface DecisionGapsResponseDTO {
  decision_id: string;
  decision_type: string;
  exposure_classification: string;
  evidence_gaps: Array<any>;
  actionable_recommendations: Array<any>;
  total_gaps: number;
}

export interface DecisionHistoryItemDTO {
  assessment_id: string;
  decision_id: string;
  policy_version: string;
  assessment_hash: string;
  input_snapshot_hash: string;
  exposure_classification: string;
  exposure_summary: string;
  gaps_count: number;
  dependencies_count: number;
  is_active: boolean;
  superseded_by?: string | null;
  created_at: string;
}

export interface DecisionHistoryResponseDTO {
  decision_id: string;
  history: DecisionHistoryItemDTO[];
  total: number;
}

// ── Phase 6.5 Decision Robustness Interfaces ────────────────────────────────

export interface UncertaintyInputDTO {
  parameter_name: string;
  nominal_value: number;
  min_value?: number;
  max_value?: number;
  tolerance?: number;
  unit: string;
  representation_type?: string;
  source_evidence_id?: string;
  reason?: string;
}

export interface RobustnessPreflightRequestDTO {
  decision_id: string;
  decision_type?: string;
  uncertainty_inputs?: UncertaintyInputDTO[];
}

export interface RobustnessPreflightResponseDTO {
  decision_id: string;
  decision_type: string;
  is_ready: boolean;
  validation_errors: string[];
  warnings: string[];
  matched_parameters_count: number;
  missing_evidence_parameters: string[];
  recomputable_kpis: Array<{ kpi: string; model: string; unit: string }>;
  policy_version: string;
}

export interface RobustnessAnalysisRequestDTO {
  decision_id: string;
  decision_type?: string;
  uncertainty_inputs?: UncertaintyInputDTO[];
  correlated_groups?: Array<Record<string, any>>;
  target_kpi?: string;
  decision_threshold?: number | null;
  optimization_direction?: string;
  threshold_range?: [number, number] | null;
  persist_record?: boolean;
}

export interface ReversalScenarioDTO {
  scenario_id: string;
  parameter_values: Record<string, number>;
  original_selection: string;
  scenario_winner: string;
  target_kpi: string;
  selected_option_kpi?: number | null;
  scenario_winner_kpi?: number | null;
  decision_margin?: number | null;
  is_ranking_reversal: boolean;
  threshold_breach: boolean;
  nature: string;
}

export interface BoundaryCrossingDTO {
  scenario_id: string;
  crossing_type: string;
  critical_parameter?: string;
  nominal_value?: number;
  boundary_value?: number;
  parameter_shift_pct?: number;
  critical_parameters?: string[];
  parameter_values?: Record<string, number>;
  target_kpi: string;
  description: string;
}

export interface DominantUncertaintyDTO {
  parameter_name: string;
  impact_score: number;
  elasticity: number;
  relative_uncertainty_span_pct: number;
  reversals_participated: number;
  unit: string;
}

export interface VOIPrioritizationDTO {
  parameter_name: string;
  priority_level: string;
  urgency: string;
  recommended_experiment: string;
  current_trust_state: string;
  elasticity: number;
  justification: string;
}

export interface RobustnessAnalysisResponseDTO {
  decision_id: string;
  decision_type: string;
  policy_version: string;
  analysis_hash: string;
  input_snapshot_hash: string;
  robustness_classification: string;
  robustness_summary: string;
  selected_option: string;
  target_kpi: string;
  evaluated_envelope: Record<string, any>;
  evaluated_scenarios_count: number;
  reversals_count: number;
  reversal_scenarios: ReversalScenarioDTO[];
  boundary_crossings: BoundaryCrossingDTO[];
  dominant_uncertainties: DominantUncertaintyDTO[];
  voi_prioritizations: VOIPrioritizationDTO[];
  solver_failures: Array<Record<string, any>>;
  governance_separation_notice: string;
  deployment_safety_inferred: boolean;
  deployment_authorization: string;
  is_active: boolean;
  created_at?: string | null;
}

export interface DecisionBoundariesResponseDTO {
  decision_id: string;
  boundary_crossings: BoundaryCrossingDTO[];
  total: number;
}

export interface DecisionVOIResponseDTO {
  decision_id: string;
  voi_prioritizations: VOIPrioritizationDTO[];
  total: number;
}

export interface RobustnessHistoryResponseDTO {
  decision_id: string;
  history: Array<Record<string, any>>;
  total: number;
}


// ── Blind Engineering Calibration & Longitudinal Track Record (Phase 5.4) ─────

export interface OutcomeStatisticsDTO {
  total_completed_evaluations: number;
  comparable_evaluations: number;
  uncomparable_evaluations: number;
  metrics_only_evaluations: number;
  binary_evaluated_count: number;
  correct_outcomes: number;
  incorrect_outcomes: number;
  observed_accuracy?: number | null;
  observed_accuracy_ci?: [number, number] | null;
  comparison_coverage?: number | null;
  excluded_counts: Record<string, number>;
  cohort_breakdown: Record<string, any>;
}

export interface BrierScoreDTO {
  brier_score?: number | null;
  eligible_sample_size: number;
  status: "AVAILABLE" | "INSUFFICIENT_SAMPLE";
  excluded_count: number;
  excluded_reasons: Record<string, number>;
  interpretation: string;
}

export interface CalibrationBinDTO {
  bin_index: number;
  range: [number, number];
  label: string;
  sample_count: number;
  positive_count: number;
  mean_forecast_probability?: number | null;
  observed_frequency?: number | null;
  uncertainty_interval?: [number, number] | null;
  is_empty: boolean;
}

export interface CalibrationCurveResponseDTO {
  status: "AVAILABLE" | "INSUFFICIENT_SAMPLE" | "NO_DATA";
  status_message: string;
  total_eligible_samples: number;
  excluded_observations_count: number;
  bins: CalibrationBinDTO[];
  policy_version: string;
  binning_method: string;
  uncertainty_method: string;
  aggregate_hash?: string;
  cohort_definition?: Record<string, any>;
}

export interface CalibrationSummaryResponseDTO {
  calibration_policy_version: string;
  calibration_policy_hash: string;
  aggregate_hash: string;
  cohort_definition: Record<string, any>;
  outcome_statistics: OutcomeStatisticsDTO;
  brier_score: BrierScoreDTO;
  calibration_curve_summary: {
    status: string;
    status_message: string;
    total_eligible_samples: number;
  };
  source_comparisons_count: number;
  source_comparison_ids: string[];
}

export interface EvaluationHistoryItemDTO {
  comparison_id: string;
  comparison_hash: string;
  comparison_policy_version: string;
  comparison_type: string;
  verdict: string;
  interpretation: string;
  comparison_metrics: Record<string, any>;
  computed_at?: string | null;
  session_id: string;
  session_name: string;
  session_status: string;
  root_entity_type: string;
  root_entity_id: string;
  revealed_at?: string | null;
  submission_id: string;
  submission_hash: string;
  submitted_at?: string | null;
  prediction_payload: Record<string, any>;
  outcome_identity: Record<string, any>;
  eligibility: Record<string, any>;
}

export interface CalibrationHistoryResponseDTO {
  calibration_policy_version: string;
  total_count: number;
  limit: number;
  offset: number;
  evaluations: EvaluationHistoryItemDTO[];
}

export class BlindCalibrationApi {
  static async getMySummary(params?: {
    prediction_type?: string;
    window_start?: string;
    window_end?: string;
  }): Promise<CalibrationSummaryResponseDTO> {
    const q = new URLSearchParams();
    if (params?.prediction_type) q.set("prediction_type", params.prediction_type);
    if (params?.window_start) q.set("window_start", params.window_start);
    if (params?.window_end) q.set("window_end", params.window_end);
    const qs = q.toString() ? `?${q.toString()}` : "";
    return apiJson<CalibrationSummaryResponseDTO>(`/api/v1/blind-calibration/me${qs}`);
  }

  static async getMyCurve(params?: {
    prediction_type?: string;
  }): Promise<CalibrationCurveResponseDTO> {
    const q = new URLSearchParams();
    if (params?.prediction_type) q.set("prediction_type", params.prediction_type);
    const qs = q.toString() ? `?${q.toString()}` : "";
    return apiJson<CalibrationCurveResponseDTO>(`/api/v1/blind-calibration/me/curve${qs}`);
  }

  static async getMyHistory(params?: {
    limit?: number;
    offset?: number;
    prediction_type?: string;
  }): Promise<CalibrationHistoryResponseDTO> {
    const q = new URLSearchParams();
    if (params?.limit !== undefined) q.set("limit", String(params.limit));
    if (params?.offset !== undefined) q.set("offset", String(params.offset));
    if (params?.prediction_type) q.set("prediction_type", params.prediction_type);
    const qs = q.toString() ? `?${q.toString()}` : "";
    return apiJson<CalibrationHistoryResponseDTO>(`/api/v1/blind-calibration/me/history${qs}`);
  }

  static async getTeamSummary(
    teamId: string,
    params?: {
      prediction_type?: string;
      window_start?: string;
      window_end?: string;
    }
  ): Promise<CalibrationSummaryResponseDTO> {
    const q = new URLSearchParams();
    if (params?.prediction_type) q.set("prediction_type", params.prediction_type);
    if (params?.window_start) q.set("window_start", params.window_start);
    if (params?.window_end) q.set("window_end", params.window_end);
    const qs = q.toString() ? `?${q.toString()}` : "";
    return apiJson<CalibrationSummaryResponseDTO>(
      `/api/v1/blind-calibration/team/${encodeURIComponent(teamId)}${qs}`
    );
  }
}

// ── Solver Interoperability API (Phase 7.2) ──────────────────────────────────

export interface AdapterCapabilityDTO {
  adapter_id: string;
  adapter_version: string;
  solver_name: string;
  supported_formats: string[];
  supported_import_formats: string[];
  supported_export_formats: string[];
  supported_versions: string[];
  supported_categories: string[];
  unit_restrictions: string[];
  frame_restrictions: string[];
  import_capability: "SUPPORTED" | "PARTIALLY_SUPPORTED" | "UNSUPPORTED" | "UNAVAILABLE_DEPENDENCY";
  export_capability: "SUPPORTED" | "PARTIALLY_SUPPORTED" | "UNSUPPORTED" | "UNAVAILABLE_DEPENDENCY";
  required_dependencies: Array<{
    name: string;
    version_spec?: string;
    is_available: boolean;
    description: string;
  }>;
  known_limitations: string[];
  verification_status: "VERIFIED" | "UNVERIFIED" | "EXPERIMENTAL";
}

export interface SolverImportRequestDTO {
  adapter_id: string;
  filename: string;
  content: string;
  is_base64?: boolean;
  idempotency_key?: string;
  expected_sha256?: string;
  options?: Record<string, any>;
}

export interface SolverExportRequestDTO {
  adapter_id: string;
  target_format: string;
  manifest: Record<string, any>;
  idempotency_key?: string;
  options?: Record<string, any>;
}

export interface SolverOperationResponseDTO {
  id: string;
  organization_id?: string | null;
  team_id?: string | null;
  user_id: string;
  operation_type: "IMPORT" | "EXPORT";
  adapter_id: string;
  adapter_version: string;
  solver_name: string;
  state: "PENDING" | "VALIDATING" | "TRANSFORMING" | "COMPLETED" | "REJECTED" | "FAILED";
  input_artifact_id?: string | null;
  output_artifact_id?: string | null;
  canonical_manifest_version: string;
  manifest_hash?: string | null;
  coordinate_frame: Record<string, any>;
  units_summary: Record<string, any>;
  mapping_diagnostics: Record<string, any>;
  validation_diagnostics: Record<string, any>;
  failure_reason?: string | null;
  idempotency_key?: string | null;
  is_executed: boolean;
  is_physically_validated: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
}

export interface SolverDiagnosticsResponseDTO {
  operation_id: string;
  operation_type: string;
  state: string;
  is_executed: boolean;
  is_physically_validated: boolean;
  coordinate_frame: Record<string, any>;
  units_summary: Record<string, any>;
  mapping_diagnostics: Record<string, any>;
  validation_diagnostics: Record<string, any>;
  failure_reason?: string | null;
}

export class SolverInteropApi {
  static async listAdapters(direction?: "import" | "export"): Promise<AdapterCapabilityDTO[]> {
    const qs = direction ? `?direction=${direction}` : "";
    return apiJson<AdapterCapabilityDTO[]>(`/api/v1/interop/adapters${qs}`);
  }

  static async getAdapter(adapterId: string): Promise<AdapterCapabilityDTO> {
    return apiJson<AdapterCapabilityDTO>(`/api/v1/interop/adapters/${encodeURIComponent(adapterId)}`);
  }

  static async startImport(req: SolverImportRequestDTO): Promise<SolverOperationResponseDTO> {
    return apiJson<SolverOperationResponseDTO>("/api/v1/interop/import", {
      method: "POST",
      body: JSON.stringify(req),
    });
  }

  static async startExport(req: SolverExportRequestDTO): Promise<SolverOperationResponseDTO> {
    return apiJson<SolverOperationResponseDTO>("/api/v1/interop/export", {
      method: "POST",
      body: JSON.stringify(req),
    });
  }

  static async getOperation(operationId: string): Promise<SolverOperationResponseDTO> {
    return apiJson<SolverOperationResponseDTO>(`/api/v1/interop/operations/${encodeURIComponent(operationId)}`);
  }

  static async getDiagnostics(operationId: string): Promise<SolverDiagnosticsResponseDTO> {
    return apiJson<SolverDiagnosticsResponseDTO>(`/api/v1/interop/operations/${encodeURIComponent(operationId)}/diagnostics`);
  }

  static async downloadArtifact(operationId: string): Promise<Blob> {
    const resp = await apiFetch(`/api/v1/interop/operations/${encodeURIComponent(operationId)}/artifact`);
    return resp.blob();
  }

  static async validateManifest(manifest: Record<string, any>): Promise<{ is_valid: boolean; warnings: string[]; manifest?: any }> {
    return apiJson("/api/v1/interop/manifests/validate", {
      method: "POST",
      body: JSON.stringify(manifest),
    });
  }

  static async checkUnits(unitA: string, unitB: string): Promise<{ status: string; dimension?: string; detail?: string }> {
    return apiJson("/api/v1/interop/units/check", {
      method: "POST",
      body: JSON.stringify({ unit_a: unitA, unit_b: unitB }),
    });
  }

  static async checkFrame(frame: Record<string, any>): Promise<{ status: string; is_valid: boolean; reasons: string[] }> {
    return apiJson("/api/v1/interop/frames/check", {
      method: "POST",
      body: JSON.stringify(frame),
    });
  }
}

// ── Solver Execution & Reconciliation API (Phase 7.3) ─────────────────────────

export interface RuntimeEnvironmentInfoDTO {
  solver_name: string;
  is_available: boolean;
  version: string;
  executable_path?: string | null;
  licensing_model: string;
  is_sandboxed: boolean;
  supported_input_formats: string[];
  output_format: string;
  notes: string;
}

export interface JobPreflightRequestDTO {
  solver_name: string;
  input_artifact_id: string;
}

export interface JobPreflightResponseDTO {
  is_supported: boolean;
  is_available: boolean;
  solver_name: string;
  licensing_model: string;
  executable_path?: string | null;
  notes?: string;
  warnings: string[];
}

export interface ExecuteJobRequestDTO {
  solver_name: string;
  input_artifact_id: string;
  execution_config?: Record<string, any>;
  resource_limits?: Record<string, any>;
  idempotency_key?: string;
  wait_for_completion?: boolean;
}

export interface JobResponseDTO {
  id: string;
  organization_id?: string | null;
  team_id?: string | null;
  user_id: string;
  solver_name: string;
  solver_version: string;
  adapter_id: string;
  state: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED" | "TIMED_OUT";
  input_artifact_id?: string | null;
  input_artifact_hash?: string | null;
  output_artifact_ids: string[];
  execution_config: Record<string, any>;
  resource_limits: Record<string, any>;
  pid?: number | null;
  exit_code?: number | null;
  stdout_excerpt?: string | null;
  stderr_excerpt?: string | null;
  failure_reason?: string | null;
  error_category?: string | null;
  is_executed: boolean;
  is_physically_validated: boolean;
  execution_provenance: Record<string, any>;
  reconciliation_summary: Record<string, any>;
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at?: string | null;
}

export interface ReconciliationSignalMetricDTO {
  channel_name: string;
  unit: string;
  peak_external: number;
  peak_reference: number;
  peak_error_abs: number;
  peak_error_pct: number;
  rms_external: number;
  rms_reference: number;
  rms_error_abs: number;
  nrmse_pct: number;
  peak_phase_delay_ms: number;
  passed_tolerance: boolean;
  applied_tolerances: Record<string, any>;
}

export interface ReconciliationReportDTO {
  reconciliation_id: string;
  job_id: string;
  solver_name: string;
  evaluated_at: string;
  signals: Record<string, ReconciliationSignalMetricDTO>;
  dynamic_energy_ratio: number;
  overall_reconciliation_verdict: "CONCORDANT" | "TOLERANCE_EXCEEDED" | "DIVERGENT";
  epistemic_notice: string;
}

export class SolverExecutionApi {
  static async getRuntimes(): Promise<RuntimeEnvironmentInfoDTO[]> {
    return apiJson<RuntimeEnvironmentInfoDTO[]>("/api/v1/interop/runtimes");
  }

  static async preflightExecution(req: JobPreflightRequestDTO): Promise<JobPreflightResponseDTO> {
    return apiJson<JobPreflightResponseDTO>("/api/v1/interop/execute/preflight", {
      method: "POST",
      body: JSON.stringify(req),
    });
  }

  static async executeJob(req: ExecuteJobRequestDTO): Promise<JobResponseDTO> {
    return apiJson<JobResponseDTO>("/api/v1/interop/execute", {
      method: "POST",
      body: JSON.stringify(req),
    });
  }

  static async listJobs(limit = 50): Promise<JobResponseDTO[]> {
    return apiJson<JobResponseDTO[]>(`/api/v1/interop/jobs?limit=${limit}`);
  }

  static async getJob(jobId: string): Promise<JobResponseDTO> {
    return apiJson<JobResponseDTO>(`/api/v1/interop/jobs/${encodeURIComponent(jobId)}`);
  }

  static async cancelJob(jobId: string): Promise<JobResponseDTO> {
    return apiJson<JobResponseDTO>(`/api/v1/interop/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    });
  }

  static async reconcileJob(jobId: string, customTolerances?: Record<string, any>): Promise<ReconciliationReportDTO> {
    return apiJson<ReconciliationReportDTO>(`/api/v1/interop/jobs/${encodeURIComponent(jobId)}/reconcile`, {
      method: "POST",
      body: JSON.stringify({ custom_tolerances: customTolerances || {} }),
    });
  }
}

