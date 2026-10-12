import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  SolverExecutionApi,
  RuntimeEnvironmentInfoDTO,
  JobResponseDTO,
  JobPreflightResponseDTO,
  ReconciliationReportDTO,
} from "../lib/api_client";
import * as apiModule from "../lib/api";

describe("SolverExecutionApi & Reconciliation Frontend Unit Tests (Phase 7.3)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("API Surface & Method Signatures", () => {
    it("SolverExecutionApi exposes all execution lifecycle and reconciliation methods", () => {
      const methodNames = Object.getOwnPropertyNames(SolverExecutionApi).filter(
        (m) =>
          typeof (SolverExecutionApi as any)[m] === "function" &&
          m !== "prototype" &&
          m !== "name" &&
          m !== "length"
      );

      expect(methodNames).toContain("getRuntimes");
      expect(methodNames).toContain("preflightExecution");
      expect(methodNames).toContain("executeJob");
      expect(methodNames).toContain("listJobs");
      expect(methodNames).toContain("getJob");
      expect(methodNames).toContain("cancelJob");
      expect(methodNames).toContain("reconcileJob");
    });
  });

  describe("Runtime Feasibility Gate", () => {
    it("getRuntimes truthfully reports available open-source runtimes and unavailable proprietary ones", async () => {
      const mockRuntimes: RuntimeEnvironmentInfoDTO[] = [
        {
          solver_name: "FMI_COSIMULATION",
          is_available: true,
          version: "0.3.31",
          executable_path: "D:\\project\\venv\\Scripts\\fmpy.exe",
          licensing_model: "Open-Source (BSD-2-Clause)",
          is_sandboxed: true,
          supported_input_formats: [".fmu"],
          output_format: "text/csv",
          notes: "FMPy CLI runner available",
        },
        {
          solver_name: "EXTERNAL_CAE_SOLVER",
          is_available: true,
          version: "1.0.0",
          executable_path: "python -m suspensionlab.interop.runners.external_cae_solver",
          licensing_model: "Open-Source (BSD-3-Clause)",
          is_sandboxed: true,
          supported_input_formats: [".json", ".adm"],
          output_format: "text/csv",
          notes: "Standalone 2-DOF vehicle dynamics solver",
        },
        {
          solver_name: "MSC_ADAMS",
          is_available: false,
          version: "Unknown",
          executable_path: null,
          licensing_model: "Proprietary",
          is_sandboxed: true,
          supported_input_formats: [".adm"],
          output_format: "text/plain",
          notes: "Host environment lacks MSC Adams installation",
        },
        {
          solver_name: "MATLAB_SIMULINK",
          is_available: false,
          version: "Unknown",
          executable_path: null,
          licensing_model: "Proprietary",
          is_sandboxed: true,
          supported_input_formats: [".m", ".slx"],
          output_format: "text/plain",
          notes: "Host environment lacks MATLAB/Simulink installation",
        },
      ];

      const apiJsonSpy = vi.spyOn(apiModule, "apiJson").mockResolvedValue(mockRuntimes);

      const res = await SolverExecutionApi.getRuntimes();
      expect(apiJsonSpy).toHaveBeenCalledWith("/api/v1/interop/runtimes");
      expect(res).toHaveLength(4);

      const fmi = res.find((r) => r.solver_name === "FMI_COSIMULATION");
      expect(fmi?.is_available).toBe(true);

      const adams = res.find((r) => r.solver_name === "MSC_ADAMS");
      expect(adams?.is_available).toBe(false);

      const matlab = res.find((r) => r.solver_name === "MATLAB_SIMULINK");
      expect(matlab?.is_available).toBe(false);
    });

    it("preflightExecution returns warnings when solver is unavailable or unsupported", async () => {
      const mockPreflight: JobPreflightResponseDTO = {
        is_supported: true,
        is_available: false,
        solver_name: "MSC_ADAMS",
        licensing_model: "Proprietary",
        executable_path: null,
        warnings: ["Solver 'MSC_ADAMS' is not installed on this host environment."],
      };

      const apiJsonSpy = vi.spyOn(apiModule, "apiJson").mockResolvedValue(mockPreflight);

      const res = await SolverExecutionApi.preflightExecution({
        solver_name: "MSC_ADAMS",
        input_artifact_id: "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      });

      expect(apiJsonSpy).toHaveBeenCalledWith(
        "/api/v1/interop/execute/preflight",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            solver_name: "MSC_ADAMS",
            input_artifact_id: "3fa85f64-5717-4562-b3fc-2c963f66afa6",
          }),
        })
      );
      expect(res.is_available).toBe(false);
      expect(res.warnings).toHaveLength(1);
    });
  });

  describe("Execution Lifecycle & Epistemic Invariants", () => {
    it("executeJob dispatches job and strictly preserves is_physically_validated=false", async () => {
      const mockJob: JobResponseDTO = {
        id: "job-1234-uuid",
        user_id: "user-5678",
        solver_name: "FMI_COSIMULATION",
        solver_version: "0.3.31",
        adapter_id: "adapter-fmi-v2",
        state: "COMPLETED",
        input_artifact_id: "art-input-uuid",
        input_artifact_hash: "abcd1234efgh5678",
        output_artifact_ids: ["art-out-uuid-1"],
        execution_config: { stop_time: 2.0, step_size: 0.001 },
        resource_limits: { timeout_seconds: 30, max_memory_mb: 512 },
        pid: 14208,
        exit_code: 0,
        stdout_excerpt: "Simulation finished successfully.",
        stderr_excerpt: "",
        is_executed: true,
        is_physically_validated: false,
        execution_provenance: { working_dir: "data/solver_runs/job-1234-uuid" },
        reconciliation_summary: {},
        created_at: "2026-10-12T10:00:00Z",
        completed_at: "2026-10-12T10:00:02Z",
      };

      const apiJsonSpy = vi.spyOn(apiModule, "apiJson").mockResolvedValue(mockJob);

      const job = await SolverExecutionApi.executeJob({
        solver_name: "FMI_COSIMULATION",
        input_artifact_id: "art-input-uuid",
        execution_config: { stop_time: 2.0, step_size: 0.001 },
        wait_for_completion: true,
      });

      expect(apiJsonSpy).toHaveBeenCalledWith(
        "/api/v1/interop/execute",
        expect.objectContaining({
          method: "POST",
        })
      );
      expect(job.state).toBe("COMPLETED");
      expect(job.is_executed).toBe(true);
      expect(job.is_physically_validated).toBe(false);
      expect(job.exit_code).toBe(0);
    });

    it("cancelJob dispatches cancellation request to targeted endpoint", async () => {
      const mockJob: JobResponseDTO = {
        id: "job-cancel-uuid",
        user_id: "user-5678",
        solver_name: "EXTERNAL_CAE_SOLVER",
        solver_version: "1.0.0",
        adapter_id: "adapter-external-cae-v1",
        state: "CANCELLED",
        output_artifact_ids: [],
        execution_config: {},
        resource_limits: {},
        is_executed: false,
        is_physically_validated: false,
        execution_provenance: {},
        reconciliation_summary: {},
        failure_reason: "Job cancelled by user request.",
      };

      const apiJsonSpy = vi.spyOn(apiModule, "apiJson").mockResolvedValue(mockJob);

      const res = await SolverExecutionApi.cancelJob("job-cancel-uuid");
      expect(apiJsonSpy).toHaveBeenCalledWith(
        "/api/v1/interop/jobs/job-cancel-uuid/cancel",
        expect.objectContaining({ method: "POST" })
      );
      expect(res.state).toBe("CANCELLED");
      expect(res.is_executed).toBe(false);
    });

    it("listJobs and getJob query correct endpoints", async () => {
      const listSpy = vi.spyOn(apiModule, "apiJson").mockResolvedValue([]);
      await SolverExecutionApi.listJobs(10);
      expect(listSpy).toHaveBeenCalledWith("/api/v1/interop/jobs?limit=10");

      const getSpy = vi.spyOn(apiModule, "apiJson").mockResolvedValue({ id: "job-xyz" });
      await SolverExecutionApi.getJob("job-xyz");
      expect(getSpy).toHaveBeenCalledWith("/api/v1/interop/jobs/job-xyz");
    });
  });

  describe("Numerical Result Reconciliation", () => {
    it("reconcileJob returns structured metric report with explicit epistemic notice", async () => {
      const mockReport: ReconciliationReportDTO = {
        reconciliation_id: "rec-uuid-1",
        job_id: "job-1234-uuid",
        solver_name: "FMI_COSIMULATION",
        evaluated_at: "2026-10-12T10:00:05Z",
        dynamic_energy_ratio: 1.002,
        overall_reconciliation_verdict: "CONCORDANT",
        epistemic_notice:
          "NUMERICAL RECONCILIATION NOTICE: Metrics demonstrate numerical concordance between external solver output and independent analytical 2-DOF reference dynamics. This DOES NOT constitute physical vehicle validation.",
        signals: {
          z_s: {
            channel_name: "z_s",
            unit: "m",
            peak_external: 0.048,
            peak_reference: 0.0482,
            peak_error_abs: 0.0002,
            peak_error_pct: 0.41,
            rms_external: 0.012,
            rms_reference: 0.0121,
            rms_error_abs: 0.0001,
            nrmse_pct: 0.83,
            peak_phase_delay_ms: 1.2,
            passed_tolerance: true,
            applied_tolerances: { max_nrmse_pct: 5.0 },
          },
        },
      };

      const apiJsonSpy = vi.spyOn(apiModule, "apiJson").mockResolvedValue(mockReport);

      const report = await SolverExecutionApi.reconcileJob("job-1234-uuid", { max_nrmse_pct: 5.0 });

      expect(apiJsonSpy).toHaveBeenCalledWith(
        "/api/v1/interop/jobs/job-1234-uuid/reconcile",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ custom_tolerances: { max_nrmse_pct: 5.0 } }),
        })
      );
      expect(report.overall_reconciliation_verdict).toBe("CONCORDANT");
      expect(report.signals.z_s.passed_tolerance).toBe(true);
      expect(report.epistemic_notice).toContain("DOES NOT constitute physical vehicle validation");
    });
  });
});
