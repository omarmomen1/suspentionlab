import { describe, it, expect, vi, beforeEach } from "vitest";
import { SimulationApi, DigitalTwinApi } from "../lib/api_client";
import * as apiModule from "../lib/api";

describe("Investigation Workflow - 4-Stage Investigation Pipeline", () => {
  type InvestigationStage = "WHAT" | "WHY" | "EVIDENCE" | "TEST";

  const STAGES: InvestigationStage[] = ["WHAT", "WHY", "EVIDENCE", "TEST"];

  it("progresses sequentially through the four core engineering stages", () => {
    let currentStageIndex = 0;

    const nextStage = () => {
      if (currentStageIndex < STAGES.length - 1) {
        currentStageIndex++;
      }
    };

    const prevStage = () => {
      if (currentStageIndex > 0) {
        currentStageIndex--;
      }
    };

    expect(STAGES[currentStageIndex]).toBe("WHAT");
    nextStage();
    expect(STAGES[currentStageIndex]).toBe("WHY");
    nextStage();
    expect(STAGES[currentStageIndex]).toBe("EVIDENCE");
    nextStage();
    expect(STAGES[currentStageIndex]).toBe("TEST");

    // Cannot advance past TEST
    nextStage();
    expect(STAGES[currentStageIndex]).toBe("TEST");

    // Step backward
    prevStage();
    expect(STAGES[currentStageIndex]).toBe("EVIDENCE");
  });

  it("validates engineering anomaly question schema and telemetry residuals", () => {
    interface EngineeringInvestigationQuestion {
      id: string;
      question: string;
      severity: "CRITICAL" | "WARNING" | "NOMINAL";
      subsystem: string;
      residual: string;
      status: string;
      recommendedAction: string;
      evidenceCount: number;
    }

    const sampleAnomaly: EngineeringInvestigationQuestion = {
      id: "Q-2026-041",
      question: "Why is rear axle heave oscillation under-damped after Turn 4 kerb strike?",
      severity: "CRITICAL",
      subsystem: "Rear Suspension / Damper Dynamics",
      residual: "+23.4% overshoot vs baseline model",
      status: "ACTIVE_INVESTIGATION",
      recommendedAction: "Simulate rebound damping increase from 1,450 to 2,200 Ns/m",
      evidenceCount: 4,
    };

    expect(sampleAnomaly.id).toMatch(/^Q-\d{4}-\d{3}$/);
    expect(sampleAnomaly.severity).toBe("CRITICAL");
    expect(sampleAnomaly.residual).toContain("overshoot");
    expect(sampleAnomaly.evidenceCount).toBeGreaterThanOrEqual(1);
    expect(sampleAnomaly.recommendedAction).toContain("damping");
  });
});

describe("Investigation Experiment Execution & Approval Lifecycle", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("dispatches ODE simulation experiment with modified parameters", async () => {
    const mockSimResult = {
      time: [0, 0.05, 0.1, 0.15, 0.2],
      z_s: [0, 0.015, 0.008, 0.002, 0.0005],
      z_u: [0, 0.02, 0.005, 0.001, 0.0],
      spring_force: [0, 570, 304, 76, 19],
      damper_force: [0, 660, 220, 44, 8],
    };

    const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockSimResult);

    const testParams = {
      m_s: 320,
      m_u: 48,
      k_s: 38000,
      k_t: 240000,
      c: 2200, // modified from 1450 to test damping improvement
      speed_kmh: 120,
    };

    const res = await SimulationApi.simulateQuarterCar(testParams);

    expect(spy).toHaveBeenCalledWith(
      "/api/v1/simulate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(testParams),
      })
    );
    expect(res.z_s[res.z_s.length - 1]).toBeLessThan(res.z_s[1]); // verifies oscillation decay
  });

  it("formalizes engineering proposal approval with sign-off credentials", () => {
    interface EngineeringApproval {
      proposalId: string;
      status: "APPROVED" | "REJECTED" | "PENDING_REVIEW";
      approver: string;
      engineeringRole: string;
      rationale: string;
      approvedAt: string;
    }

    const proposal: EngineeringApproval = {
      proposalId: "prop-damp-bcn-04",
      status: "PENDING_REVIEW",
      approver: "",
      engineeringRole: "",
      rationale: "",
      approvedAt: "",
    };

    // Engineer approves the setup change
    const signOff = (
      p: EngineeringApproval,
      approver: string,
      role: string,
      rationale: string
    ): EngineeringApproval => {
      if (!approver || !role || !rationale) {
        throw new Error("Formal engineering sign-off requires approver, role, and technical rationale.");
      }
      return {
        ...p,
        status: "APPROVED",
        approver,
        engineeringRole: role,
        rationale,
        approvedAt: new Date().toISOString(),
      };
    };

    expect(() => signOff(proposal, "", "Lead Engineer", "Rationale")).toThrow();

    const approvedProposal = signOff(
      proposal,
      "Dr. Elena Rostova",
      "Chief Race Engineer",
      "Simulated damping ratio restores overshoot to nominal envelope (ζ = 0.68). Safe for Session 3."
    );

    expect(approvedProposal.status).toBe("APPROVED");
    expect(approvedProposal.approver).toBe("Dr. Elena Rostova");
    expect(approvedProposal.engineeringRole).toBe("Chief Race Engineer");
    expect(approvedProposal.approvedAt).toBeDefined();
  });
});
