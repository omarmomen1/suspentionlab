import { describe, it, expect, vi, beforeEach } from "vitest";
import { AiEngineerApi } from "../lib/api_client";
import * as apiModule from "../lib/api";

describe("Canonical AI Race Engineer API Client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("AiEngineerApi.chat dispatches POST /api/v1/ai/chat and parses rich response", async () => {
    const mockResponse = {
      diagnosis: "Under-damped body oscillation",
      root_cause: "Damping coefficient is insufficient for effective spring rate",
      tested_setups: 20,
      best_feasible: [
        {
          parameter: "c",
          current_value: 2050,
          recommended_value: 2450,
          change_pct: 19.51,
        },
      ],
      predicted_effects: [
        {
          metric: "Ride Comfort (ISO Wk RMS)",
          unit: "m/s²",
          baseline: 1.45,
          predicted: 1.12,
          change_pct: -22.76,
        },
      ],
      constraint_violations: [],
      confidence: 0.88,
      evidence: {
        description: "20 setups simulated on ISO road",
        simulations_run: 21,
        feasible_found: 18,
      },
      model_validity: { tier: "VALIDATED", score: 92.5 },
      provenance: {
        recommendation_summary: "1 parameter change selected",
        target_metric: "Optimize comfort",
        evidence_runs: ["Sim-1", "Sim-2"],
        evidence_telemetry_sessions: [],
        simulation_count: 21,
        constraint_status: "PASS",
        model_version: "QuarterCar-2DOF-ISO8608",
        tire_model_version: "Pacejka-MF52-v5",
        correlation_pct: null,
        confidence_score: 0.88,
        result_hash: "a1b2c3d4e5f67890",
        timestamp_iso: "2026-09-03T16:00:00Z",
      },
      recommendations: [],
      setup_summary: "Increasing damping coefficient by 19.5% improves comfort by 22.8%.",
      simulated: true,
      tool_calls: [{ tool: "run_simulation", status: "SUCCESS" }],
      citations: [
        {
          source_type: "SIMULATION",
          tool_name: "run_simulation",
          field_path: "f_n_s",
          value: 1.34,
        },
      ],
      attack_defense: null,
    };

    const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockResponse);

    const res = await AiEngineerApi.chat("Excessive bounce over apex curbs");

    expect(spy).toHaveBeenCalledWith(
      "/api/v1/ai/chat",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          problem: "Excessive bounce over apex curbs",
          params: undefined,
          team_id: undefined,
        }),
      })
    );
    expect(res.confidence).toBe(0.88);
    expect(res.best_feasible).toHaveLength(1);
    expect(res.citations[0].source_type).toBe("SIMULATION");
    expect(res.provenance?.result_hash).toBe("a1b2c3d4e5f67890");
  });

  it("AiEngineerApi.listTools requests /api/v1/ai/tools and returns 11 schemas", async () => {
    const mockTools = {
      tools: [
        {
          name: "run_simulation",
          description: "Run quarter car simulation",
          parameters: {},
          required_permission: "simulation:run",
          source_tag: "SIMULATION",
        },
        {
          name: "get_constraints",
          description: "Get physical constraints",
          parameters: {},
          required_permission: "vehicle:read",
          source_tag: "DATABASE_ARTIFACT",
        },
      ],
      count: 2,
      architecture: "LLM-as-Interface",
    };

    const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockTools);

    const res = await AiEngineerApi.listTools();

    expect(spy).toHaveBeenCalledWith("/api/v1/ai/tools", { method: "GET" });
    expect(res.count).toBe(2);
    expect(res.tools[0].name).toBe("run_simulation");
  });

  it("AiEngineerApi.executeTool dispatches POST /api/v1/ai/tools/execute", async () => {
    const mockExec = {
      status: "SUCCESS",
      tool_name: "get_constraints",
      result: { is_feasible: true },
    };

    const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockExec);

    const res = await AiEngineerApi.executeTool("get_constraints", { active_params: { k_s: 35000 } });

    expect(spy).toHaveBeenCalledWith(
      "/api/v1/ai/tools/execute",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          tool_name: "get_constraints",
          arguments: { active_params: { k_s: 35000 } },
          team_id: undefined,
        }),
      })
    );
    expect(res.status).toBe("SUCCESS");
  });

  it("AiEngineerApi.approveDecision dispatches POST /api/v1/ai/approve", async () => {
    const mockApprove = {
      status: "APPROVED",
      approved_by: "Chief Engineer",
      timestamp: "2026-09-08T01:30:00Z",
      hmac_signature: "mock-sha256-hmac-signature",
    };

    const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockApprove);

    const res = await AiEngineerApi.approveDecision(
      "decision-setup-v24",
      "SETUP_PARAMETER_MODIFICATION",
      "Sign-off verified with track conditions",
      "CHIEF_RACE_ENGINEER",
      "hmac-sig-12345",
      "team-squad-1"
    );

    expect(spy).toHaveBeenCalledWith(
      "/api/v1/ai/approve",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          decision_id: "decision-setup-v24",
          action_type: "SETUP_PARAMETER_MODIFICATION",
          signoff_notes: "Sign-off verified with track conditions",
          user_role: "CHIEF_RACE_ENGINEER",
          signature: "hmac-sig-12345",
          team_id: "team-squad-1",
        }),
      })
    );
    expect(res.status).toBe("APPROVED");
    expect(res.hmac_signature).toBe("mock-sha256-hmac-signature");
  });

  it("AiEngineerApi parses copilot 5-part contract and epistemic badges", async () => {
    const mockCopilotResponse = {
      diagnosis: "Front tire saturation in Turn 7 due to load transfer",
      root_cause: "Excessive front roll resistance",
      tested_setups: 5,
      best_feasible: [],
      predicted_effects: [],
      constraint_violations: [],
      confidence: 0.94,
      evidence: { description: "Telemetry correlated with simulation", simulations_run: 3, feasible_found: 3 },
      model_validity: {},
      recommendations: [],
      setup_summary: "Front tire saturation is driven by high dynamic roll stiffness.",
      simulated: true,
      tool_calls: [],
      citations: [],
      answer: "Front tire saturation in Turn 7 is driven by lateral load transfer exceeding the grip limit.",
      engineering_interpretation: "Dynamic roll stiffness distribution places excessive normal load on the outside front tire.",
      uncertainty: "Quarter-car model does not resolve aero map variation in yaw.",
      next_action: "Reduce front anti-roll bar stiffness by 8% or decrease front spring rate.",
      epistemic_classification: {
        telemetry_run: "MEASURED",
        simulation_run: "SIMULATED",
        correlation: "CORRELATED",
      },
      epistemic_badges: [
        {
          tool: "query_telemetry",
          source: "MEASURED",
          epistemic_status: "MEASURED",
          provenance_sha256: "aabbccddeeff",
        },
        {
          tool: "run_simulation",
          source: "SIMULATED",
          epistemic_status: "SIMULATED",
          provenance_sha256: "112233445566",
        },
      ],
      approval_gate: {
        action_type: "PARAMETER_CHANGE",
        target_id: "setup-v24",
        parameters: { k_s: 32000 },
        change_summary: "Reduce front spring rate to 32000 N/m",
        impact_assessment: "Predicted to reduce peak front slip ratio by 14%",
        required_role: "CHIEF_RACE_ENGINEER",
        status: "PENDING",
        warning: "Requires physical track sign-off before upload to car",
      },
    };

    vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockCopilotResponse);

    const res = await AiEngineerApi.chat("Why is front tire saturation increasing in Turn 7?");

    expect(res.answer).toContain("Front tire saturation in Turn 7");
    expect(res.epistemic_badges).toHaveLength(2);
    expect(res.epistemic_badges?.[0].epistemic_status).toBe("MEASURED");
    expect(res.approval_gate?.status).toBe("PENDING");
  });
});
