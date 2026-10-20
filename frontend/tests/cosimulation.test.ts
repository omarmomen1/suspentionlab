import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  CoSimulationApi,
  CoSimContractDTO,
  CoSimPreflightReportDTO,
  CoSimCapabilitiesDTO,
  FMICapabilityReportDTO,
} from "../lib/api_client";
import * as apiModule from "../lib/api";

describe("CoSimulationApi & Multi-Domain Interoperability Frontend Unit Tests (Phase 7.5)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("API Surface & Method Signatures", () => {
    it("CoSimulationApi exposes all co-simulation lifecycle methods", () => {
      const methodNames = Object.getOwnPropertyNames(CoSimulationApi).filter(
        (m) =>
          typeof (CoSimulationApi as any)[m] === "function" &&
          m !== "prototype" &&
          m !== "name" &&
          m !== "length"
      );

      expect(methodNames).toContain("getCapabilities");
      expect(methodNames).toContain("inspectFmu");
      expect(methodNames).toContain("createContract");
      expect(methodNames).toContain("listContracts");
      expect(methodNames).toContain("getContract");
      expect(methodNames).toContain("preflightContract");
      expect(methodNames).toContain("executeCoupled");
      expect(methodNames).toContain("getDiagnostics");
      expect(methodNames).toContain("heartbeat");
    });
  });

  describe("FMI Capability Discovery & Epistemic Boundaries", () => {
    it("getCapabilities returns vetted FMUs and truthful status flags", async () => {
      const mockCaps: CoSimCapabilitiesDTO = {
        vetted_fmus: [
          {
            filename: "QuarterCarRideModel.fmu",
            hash_sha256: "b45508a65cbe5b274ffab0d5ceaa2d9c02ea9a0a09e0a055ad58f161f32a67a0",
            model_name: "QuarterCarRideModel",
            path: "D:\\project\\artifacts\\QuarterCarRideModel.fmu",
          },
        ],
        internal_components: [
          {
            name: "RoadProfileGenerator",
            description: "Analytical road elevation profile generator",
            signals: { outputs: ["z_r"] },
          },
        ],
        supported_policies: ["GAUSS_SEIDEL", "JACOBI"],
        supported_interpolation: ["ZERO_ORDER_HOLD", "FIRST_ORDER_HOLD"],
        truthful_status: {
          two_fmu_cosimulation_verified: true,
          untrusted_fmu_isolation_verified: false,
          fmu_state_rollback_supported: false,
        },
      };

      const apiJsonSpy = vi.spyOn(apiModule, "apiJson").mockResolvedValue(mockCaps);

      const res = await CoSimulationApi.getCapabilities();
      expect(apiJsonSpy).toHaveBeenCalledWith("/api/v1/interop/cosim/capabilities");
      expect(res.vetted_fmus).toHaveLength(1);
      expect(res.truthful_status.two_fmu_cosimulation_verified).toBe(true);
      expect(res.truthful_status.untrusted_fmu_isolation_verified).toBe(false);
      expect(res.truthful_status.fmu_state_rollback_supported).toBe(false);
    });

    it("inspectFmu truthfully audits FMI capabilities and limits", async () => {
      const mockReport: FMICapabilityReportDTO = {
        fmi_version: "2.0",
        model_name: "QuarterCarRideModel",
        guid: "{quarter-car-guid-1234}",
        generation_tool: "PythonFMU 0.8.0",
        supports_model_exchange: false,
        supports_cosimulation: true,
        can_handle_variable_communication_step_size: true,
        can_interpolate_inputs: true,
        max_output_derivative_order: 0,
        can_run_asynchronuously: false,
        can_be_instantiated_only_once_per_process: false,
        can_not_use_memory_management_functions: true,
        can_get_and_set_fmu_state: false,
        can_serialize_fmu_state: false,
        provides_directional_derivative: false,
        variables: [
          { name: "z_r", causality: "input", variability: "continuous", data_type: "Real", unit: "m" },
          { name: "z_s", causality: "output", variability: "continuous", data_type: "Real", unit: "m" },
        ],
        available_binaries: ["win64", "linux64"],
        feedthrough_matrix: {},
        algebraic_loop_risk: false,
        truthful_limitations: [
          "State rollback is NOT supported (canGetAndSetFMUstate=False)",
          "Model Exchange is NOT supported",
        ],
      };

      const apiJsonSpy = vi.spyOn(apiModule, "apiJson").mockResolvedValue(mockReport);

      const res = await CoSimulationApi.inspectFmu();
      expect(apiJsonSpy).toHaveBeenCalledWith("/api/v1/interop/cosim/fmu-capabilities");
      expect(res.supports_cosimulation).toBe(true);
      expect(res.can_get_and_set_fmu_state).toBe(false);
      expect(res.variables).toHaveLength(2);
    });
  });

  describe("Contract Preflight & Execution", () => {
    it("preflightContract validates causality, units, and algebraic loops", async () => {
      const mockPreflight: CoSimPreflightReportDTO = {
        valid: true,
        errors: [],
        warnings: [],
        algebraic_loops: [],
        causality_violations: [],
        unit_mismatches: [],
        operating_bounds_status: "VERIFIED",
        time_sync_feasibility: "FEASIBLE",
      };

      const apiJsonSpy = vi.spyOn(apiModule, "apiJson").mockResolvedValue(mockPreflight);

      const res = await CoSimulationApi.preflightContract("contract-123");
      expect(apiJsonSpy).toHaveBeenCalledWith("/api/v1/interop/cosim/contracts/contract-123/preflight", {
        method: "POST",
      });
      expect(res.valid).toBe(true);
      expect(res.algebraic_loops).toHaveLength(0);
    });

    it("executeCoupled triggers coupled run with worker fencing tokens", async () => {
      const mockJob = {
        id: "job-cosim-456",
        user_id: "user-1",
        solver_name: "CO_SIMULATION_ORCHESTRATOR",
        solver_version: "2.0.0",
        adapter_id: "adapter-cosim-master-v1",
        state: "COMPLETED" as const,
        output_artifact_ids: ["artifact-output-789"],
        execution_config: { t_end: 1.0, communication_step_size: 0.005 },
        resource_limits: { timeout_seconds: 60 },
        is_executed: true,
        is_physically_validated: false,
        worker_id: "worker-proc-101",
        lease_generation: 1,
        coupling_contract_id: "contract-123",
        co_simulation_diagnostics: {
          steps_completed: 200,
          communication_step_size: 0.005,
          final_energy_ratio: 0.9998,
        },
        execution_provenance: {},
        reconciliation_summary: {},
      };

      const apiJsonSpy = vi.spyOn(apiModule, "apiJson").mockResolvedValue(mockJob);

      const res = await CoSimulationApi.executeCoupled("contract-123", { t_end: 1.0 });
      expect(apiJsonSpy).toHaveBeenCalledWith("/api/v1/interop/cosim/contracts/contract-123/execute", {
        method: "POST",
        body: JSON.stringify({ t_end: 1.0 }),
      });
      expect(res.state).toBe("COMPLETED");
      expect(res.worker_id).toBe("worker-proc-101");
      expect(res.lease_generation).toBe(1);
      expect(res.co_simulation_diagnostics?.steps_completed).toBe(200);
    });
  });
});
