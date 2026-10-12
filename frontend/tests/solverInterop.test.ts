import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  SolverInteropApi,
  AdapterCapabilityDTO,
  SolverOperationResponseDTO,
  SolverDiagnosticsResponseDTO,
} from "../lib/api_client";
import * as apiModule from "../lib/api";

describe("SolverInteropApi & Epistemic Boundaries Frontend Unit Tests (Phase 7.2)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("API Surface & Epistemic Contracts", () => {
    it("SolverInteropApi exposes all lifecycle, discovery, and preflight methods", () => {
      const methodNames = Object.getOwnPropertyNames(SolverInteropApi).filter(
        (m) =>
          typeof (SolverInteropApi as any)[m] === "function" &&
          m !== "prototype" &&
          m !== "name" &&
          m !== "length"
      );

      expect(methodNames).toContain("listAdapters");
      expect(methodNames).toContain("getAdapter");
      expect(methodNames).toContain("startImport");
      expect(methodNames).toContain("startExport");
      expect(methodNames).toContain("getOperation");
      expect(methodNames).toContain("getDiagnostics");
      expect(methodNames).toContain("downloadArtifact");
      expect(methodNames).toContain("validateManifest");
      expect(methodNames).toContain("checkUnits");
      expect(methodNames).toContain("checkFrame");
    });

    it("Strictly omits any external solver execution invocation methods", () => {
      const methodNames = Object.getOwnPropertyNames(SolverInteropApi).filter(
        (m) => typeof (SolverInteropApi as any)[m] === "function"
      );

      for (const name of methodNames) {
        const lower = name.toLowerCase();
        expect(lower).not.toContain("runsolver");
        expect(lower).not.toContain("executesolver");
        expect(lower).not.toContain("runadams");
        expect(lower).not.toContain("runmatlab");
        expect(lower).not.toContain("runcosimulation");
      }
    });
  });

  describe("Adapter Capability Discovery", () => {
    it("listAdapters queries backend with optional direction filter", async () => {
      const mockAdapters: AdapterCapabilityDTO[] = [
        {
          adapter_id: "adapter-msc-adams-v1",
          adapter_version: "1.0.0",
          solver_name: "MSC_ADAMS",
          supported_formats: [".adm", ".cmd", ".py"],
          supported_import_formats: [".adm"],
          supported_export_formats: [".adm", ".cmd", ".py"],
          supported_versions: ["2024"],
          supported_categories: ["PARAMETERS"],
          unit_restrictions: ["SI"],
          frame_restrictions: ["ISO_8855"],
          import_capability: "PARTIALLY_SUPPORTED",
          export_capability: "SUPPORTED",
          required_dependencies: [
            {
              name: "msc-adams-solver",
              is_available: false,
              description: "MSC Adams runtime",
            },
          ],
          known_limitations: ["Command files (.cmd) and Python scripts (.py) are strictly export-only."],
          verification_status: "VERIFIED",
        },
      ];

      const apiJsonSpy = vi.spyOn(apiModule, "apiJson").mockResolvedValue(mockAdapters);

      const result = await SolverInteropApi.listAdapters("export");
      expect(apiJsonSpy).toHaveBeenCalledWith("/api/v1/interop/adapters?direction=export");
      expect(result).toHaveLength(1);
      expect(result[0].solver_name).toBe("MSC_ADAMS");
      expect(result[0].required_dependencies[0].is_available).toBe(false);
    });

    it("getAdapter retrieves granular specifications for a target adapter", async () => {
      const mockAdapter: AdapterCapabilityDTO = {
        adapter_id: "adapter-canonical-json-v1",
        adapter_version: "1.0.0",
        solver_name: "CANONICAL_JSON",
        supported_formats: [".json"],
        supported_import_formats: [".json"],
        supported_export_formats: [".json"],
        supported_versions: ["1.0.0"],
        supported_categories: ["PARAMETERS", "GEOMETRY"],
        unit_restrictions: [],
        frame_restrictions: [],
        import_capability: "SUPPORTED",
        export_capability: "SUPPORTED",
        required_dependencies: [],
        known_limitations: [],
        verification_status: "VERIFIED",
      };

      vi.spyOn(apiModule, "apiJson").mockResolvedValue(mockAdapter);

      const result = await SolverInteropApi.getAdapter("adapter-canonical-json-v1");
      expect(result.solver_name).toBe("CANONICAL_JSON");
      expect(result.import_capability).toBe("SUPPORTED");
      expect(result.export_capability).toBe("SUPPORTED");
    });
  });

  describe("Operational Ingestion & Export Lifecycle", () => {
    it("startImport submits request and preserves epistemic invariants: is_executed=false, is_physically_validated=false", async () => {
      const mockOp: SolverOperationResponseDTO = {
        id: "op-uuid-1",
        user_id: "user-uuid-1",
        operation_type: "IMPORT",
        adapter_id: "adapter-msc-adams-v1",
        adapter_version: "1.0.0",
        solver_name: "MSC_ADAMS",
        state: "COMPLETED",
        canonical_manifest_version: "1.0.0",
        manifest_hash: "hash123",
        coordinate_frame: { name: "ISO_8855" },
        units_summary: { m_s: { unit: "kg", dimension: "MASS" } },
        mapping_diagnostics: { imported_parameters_count: 5 },
        validation_diagnostics: { is_valid: true, warnings: [] },
        is_executed: false,
        is_physically_validated: false,
        created_at: "2026-10-12T01:00:00Z",
      };

      const apiJsonSpy = vi.spyOn(apiModule, "apiJson").mockResolvedValue(mockOp);

      const res = await SolverInteropApi.startImport({
        adapter_id: "adapter-msc-adams-v1",
        filename: "test.adm",
        content: "! ADAMS dataset\nPART/1, MASS=300",
      });

      expect(apiJsonSpy).toHaveBeenCalledWith(
        "/api/v1/interop/import",
        expect.objectContaining({
          method: "POST",
        })
      );
      expect(res.state).toBe("COMPLETED");
      expect(res.is_executed).toBe(false);
      expect(res.is_physically_validated).toBe(false);
    });

    it("startExport submits manifest and confirms epistemic invariant is_executed=false", async () => {
      const mockOp: SolverOperationResponseDTO = {
        id: "op-uuid-2",
        user_id: "user-uuid-1",
        operation_type: "EXPORT",
        adapter_id: "adapter-canonical-json-v1",
        adapter_version: "1.0.0",
        solver_name: "CANONICAL_JSON",
        state: "COMPLETED",
        canonical_manifest_version: "1.0.0",
        coordinate_frame: {},
        units_summary: {},
        mapping_diagnostics: {},
        validation_diagnostics: { is_valid: true, warnings: [] },
        is_executed: false,
        is_physically_validated: false,
      };

      vi.spyOn(apiModule, "apiJson").mockResolvedValue(mockOp);

      const res = await SolverInteropApi.startExport({
        adapter_id: "adapter-canonical-json-v1",
        target_format: ".json",
        manifest: { engineering_model_id: "MDL-1" },
      });

      expect(res.operation_type).toBe("EXPORT");
      expect(res.is_executed).toBe(false);
      expect(res.is_physically_validated).toBe(false);
    });

    it("getDiagnostics returns granular parameter lineage and epistemic flags", async () => {
      const mockDiag: SolverDiagnosticsResponseDTO = {
        operation_id: "op-uuid-1",
        operation_type: "IMPORT",
        state: "COMPLETED",
        is_executed: false,
        is_physically_validated: false,
        coordinate_frame: { name: "ISO_8855" },
        units_summary: { m_s: { unit: "kg" } },
        mapping_diagnostics: {
          imported_parameters_count: 3,
          parameter_names: ["c", "k_s", "m_s"],
          unmapped: [],
          lossy: [],
        },
        validation_diagnostics: { is_valid: true },
      };

      vi.spyOn(apiModule, "apiJson").mockResolvedValue(mockDiag);

      const diag = await SolverInteropApi.getDiagnostics("op-uuid-1");
      expect(diag.is_executed).toBe(false);
      expect(diag.is_physically_validated).toBe(false);
      expect(diag.mapping_diagnostics.imported_parameters_count).toBe(3);
    });
  });

  describe("Preflight Validation Endpoints", () => {
    it("checkUnits accurately parses dimensional compatibility", async () => {
      vi.spyOn(apiModule, "apiJson").mockResolvedValue({
        status: "IDENTICAL",
        dimension: "MASS",
        detail: "Identical units.",
      });

      const res = await SolverInteropApi.checkUnits("kg", "kg");
      expect(res.status).toBe("IDENTICAL");
      expect(res.dimension).toBe("MASS");
    });

    it("checkFrame checks coordinate frame orthogonality", async () => {
      vi.spyOn(apiModule, "apiJson").mockResolvedValue({
        status: "VALID",
        is_valid: true,
        reasons: [],
      });

      const res = await SolverInteropApi.checkFrame({
        name: "ISO_8855",
        x_axis: "FORWARD",
        y_axis: "LEFT",
        z_axis: "UP",
        handedness: "RIGHT_HANDED",
      });
      expect(res.is_valid).toBe(true);
    });
  });
});
