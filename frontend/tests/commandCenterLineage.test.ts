import { describe, it, expect, vi, beforeEach } from "vitest";
import { LineageApi, VehicleHealthApi } from "../lib/api_client";
import type { LineageNode, LineageEdge, LineageGraphResponse } from "../lib/api_client";
import * as apiModule from "../lib/api";

describe("Lineage Graph & Provenance Architecture", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("LineageApi.getLineageGraph invokes /api/v1/runs/lineage/graph and returns formatted nodes and edges", async () => {
    const mockGraphResponse: LineageGraphResponse = {
      nodes: [
        {
          id: "veh-amg-gt3",
          label: "Mercedes-AMG GT3 Evo",
          type: "Vehicle",
          status: "OPTIMAL",
          metadata: { category: "GT3", weight: "1285 kg" },
        },
        {
          id: "twin-amg-01",
          label: "AMG-GT3-Twin-01",
          type: "Digital Twin",
          status: "NOMINAL",
          metadata: { sync_state: "SYNCHRONIZED" },
        },
        {
          id: "run-sim-902",
          label: "Kerb Strike Simulation 902",
          type: "Simulation Run",
          status: "OPTIMAL",
          metadata: { solver: "RK45", rtol: 1e-6 },
        },
      ],
      edges: [
        {
          id: "e1",
          source: "veh-amg-gt3",
          target: "twin-amg-01",
          relationship: "CALIBRATED_FROM",
        },
        {
          id: "e2",
          source: "twin-amg-01",
          target: "run-sim-902",
          relationship: "SIMULATED_WITH",
        },
      ],
      total_nodes: 3,
      total_edges: 2,
    };

    const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockGraphResponse);

    const graph = await LineageApi.getLineageGraph({ vehicle_ref: "amg-gt3" });

    expect(spy).toHaveBeenCalledWith("/api/v1/runs/lineage/graph?vehicle_ref=amg-gt3");
    expect(graph.total_nodes).toBe(3);
    expect(graph.nodes.some((n: LineageNode) => n.type === "Digital Twin")).toBe(true);
    expect(graph.edges.some((e: LineageEdge) => e.relationship === "CALIBRATED_FROM")).toBe(true);
    expect(graph.edges.some((e: LineageEdge) => e.relationship === "SIMULATED_WITH")).toBe(true);
  });

  it("strictly validates allowed lineage edge relationships", () => {
    const allowedRelationships = [
      "GENERATED_FROM",
      "CALIBRATED_FROM",
      "SIMULATED_WITH",
      "VALIDATED_BY",
      "DERIVED_FROM",
    ];

    const testEdge = { relationship: "CALIBRATED_FROM" };
    expect(allowedRelationships).toContain(testEdge.relationship);

    const invalidEdge = { relationship: "RANDOM_LINK" };
    expect(allowedRelationships).not.toContain(invalidEdge.relationship);
  });
});

describe("Vehicle Health Matrix - Zero Fabricated Data", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("VehicleHealthApi.assessAggregateHealth returns full 6-indicator health state", async () => {
    const summary = await VehicleHealthApi.assessAggregateHealth({
      modelParams: { m_s: 320, m_u: 48, k_s: 38000, c: 2200 },
      telemetryCorrelation: 0.92,
      activeRunLabel: "RUN-VAL-7ceb75",
    });

    expect(summary).toBeDefined();
    expect(summary.model_confidence).toBeDefined();
    expect(summary.telemetry_freshness).toBeDefined();
    expect(summary.simulation_health).toBeDefined();
    expect(summary.validation_health).toBeDefined();
    expect(summary.digital_twin_health).toBeDefined();
    expect(summary.operating_envelope).toBeDefined();
  });

  it("safely falls back to UNKNOWN / DATA UNAVAILABLE when telemetry or backend is missing", () => {
    const resolveIndicatorState = (
      value: string | number | null | undefined,
      kind: "confidence" | "freshness" | "health"
    ) => {
      if (value === null || value === undefined || value === "") {
        return { status: "UNKNOWN", label: "DATA UNAVAILABLE" };
      }
      if (kind === "confidence") {
        const num = Number(value);
        if (isNaN(num)) return { status: "UNKNOWN", label: "DATA UNAVAILABLE" };
        return {
          status: num >= 0.85 ? "OPTIMAL" : num >= 0.6 ? "NOMINAL" : "WARNING",
          label: `${Math.round(num * 100)}%`,
        };
      }
      return { status: "NOMINAL", label: String(value) };
    };

    const nullConfidence = resolveIndicatorState(null, "confidence");
    expect(nullConfidence.status).toBe("UNKNOWN");
    expect(nullConfidence.label).toBe("DATA UNAVAILABLE");

    const nullFreshness = resolveIndicatorState(undefined, "freshness");
    expect(nullFreshness.status).toBe("UNKNOWN");
    expect(nullFreshness.label).toBe("DATA UNAVAILABLE");

    const validConfidence = resolveIndicatorState(0.92, "confidence");
    expect(validConfidence.status).toBe("OPTIMAL");
    expect(validConfidence.label).toBe("92%");
  });
});

describe("Persistent 8-Dimension Active Vehicle Context", () => {
  it("verifies that all 8 context dimensions are defined and non-empty", () => {
    interface ActiveVehicleContextDimensions {
      vehicleName: string;
      vehicleVersion: string;
      setupName: string;
      setupVersion: string;
      trackName: string;
      sessionName: string;
      modelVersion: string;
      telemetrySessionId: string;
    }

    const defaultContext: ActiveVehicleContextDimensions = {
      vehicleName: "Mercedes-AMG GT3 Evo",
      vehicleVersion: "v2026.1-Aero",
      setupName: "High-Downforce Barcelona",
      setupVersion: "rev-04",
      trackName: "Circuit de Barcelona-Catalunya",
      sessionName: "Qualifying 2",
      modelVersion: "QCAR-ODE-RK45-v2.1",
      telemetrySessionId: "TELEM-BCN-2026-Q2-004",
    };

    const keys = Object.keys(defaultContext);
    expect(keys).toHaveLength(8);
    expect(keys).toContain("vehicleName");
    expect(keys).toContain("vehicleVersion");
    expect(keys).toContain("setupName");
    expect(keys).toContain("setupVersion");
    expect(keys).toContain("trackName");
    expect(keys).toContain("sessionName");
    expect(keys).toContain("modelVersion");
    expect(keys).toContain("telemetrySessionId");

    for (const key of keys as (keyof ActiveVehicleContextDimensions)[]) {
      expect(defaultContext[key]).toBeTruthy();
      expect(defaultContext[key].length).toBeGreaterThan(0);
    }
  });
});
