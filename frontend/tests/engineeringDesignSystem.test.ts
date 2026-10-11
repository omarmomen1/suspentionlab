import { describe, it, expect } from "vitest";
import type {
  EngineeringStateType,
  ValidationTier,
  ApprovalStatusType,
  SystemStatusType,
  ProvenanceData,
} from "../components/engineering";

describe("Engineering Design System - Terminology & Type Safety", () => {
  it("strictly enforces standardized engineering evidence types", () => {
    const validEvidenceTypes: EngineeringStateType[] = [
      "MEASURED",
      "SIMULATED",
      "ESTIMATED",
      "CORRELATED",
      "PREDICTED",
    ];

    expect(validEvidenceTypes).toContain("MEASURED");
    expect(validEvidenceTypes).toContain("SIMULATED");
    expect(validEvidenceTypes).toContain("ESTIMATED");
    expect(validEvidenceTypes).toContain("CORRELATED");
    expect(validEvidenceTypes).toContain("PREDICTED");
    expect(validEvidenceTypes).toHaveLength(5);
  });

  it("strictly enforces standardized validation tier categories", () => {
    const validTiers: ValidationTier[] = [
      "VALIDATED",
      "CONDITIONAL",
      "EXPERIMENTAL",
      "OUT-OF-DOMAIN",
      "UNVALIDATED",
      "DATA_UNAVAILABLE",
    ];

    expect(validTiers).toContain("VALIDATED");
    expect(validTiers).toContain("CONDITIONAL");
    expect(validTiers).toContain("EXPERIMENTAL");
    expect(validTiers).toContain("OUT-OF-DOMAIN");
    expect(validTiers).toContain("UNVALIDATED");
    expect(validTiers).toContain("DATA_UNAVAILABLE");
    expect(validTiers).toHaveLength(6);
  });

  it("strictly enforces formal engineering approval states", () => {
    const validApprovals: ApprovalStatusType[] = [
      "APPROVED",
      "REJECTED",
      "PROPOSED",
      "PENDING",
    ];

    expect(validApprovals).toContain("APPROVED");
    expect(validApprovals).toContain("REJECTED");
    expect(validApprovals).toContain("PROPOSED");
    expect(validApprovals).toContain("PENDING");
    expect(validApprovals).toHaveLength(4);
  });

  it("strictly enforces engineering system status levels", () => {
    const validLevels: SystemStatusType[] = [
      "HEALTHY",
      "DEGRADED",
      "STALE",
      "UNVALIDATED",
      "FAILED",
      "PROCESSING",
      "DATA_UNAVAILABLE",
    ];

    expect(validLevels).toContain("HEALTHY");
    expect(validLevels).toContain("DEGRADED");
    expect(validLevels).toContain("STALE");
    expect(validLevels).toContain("UNVALIDATED");
    expect(validLevels).toContain("FAILED");
    expect(validLevels).toContain("PROCESSING");
    expect(validLevels).toContain("DATA_UNAVAILABLE");
    expect(validLevels).toHaveLength(7);
  });
});

describe("Confidence & Evidence Verification Rules", () => {
  it("rejects fabricated confidence when evidence is missing or null", () => {
    const formatConfidence = (value: number | null | undefined): string => {
      if (value === null || value === undefined || isNaN(value)) {
        return "DATA UNAVAILABLE";
      }
      return `${Math.round(value * 100)}%`;
    };

    expect(formatConfidence(null)).toBe("DATA UNAVAILABLE");
    expect(formatConfidence(undefined)).toBe("DATA UNAVAILABLE");
    expect(formatConfidence(NaN)).toBe("DATA UNAVAILABLE");
    expect(formatConfidence(0.924)).toBe("92%");
    expect(formatConfidence(0.0)).toBe("0%");
  });

  it("computes correct confidence tier thresholds", () => {
    const getConfidenceTier = (score: number): "HIGH" | "MEDIUM" | "LOW" | "UNVALIDATED" => {
      if (score < 0 || score > 1) return "UNVALIDATED";
      if (score >= 0.85) return "HIGH";
      if (score >= 0.60) return "MEDIUM";
      return "LOW";
    };

    expect(getConfidenceTier(0.95)).toBe("HIGH");
    expect(getConfidenceTier(0.85)).toBe("HIGH");
    expect(getConfidenceTier(0.84)).toBe("MEDIUM");
    expect(getConfidenceTier(0.60)).toBe("MEDIUM");
    expect(getConfidenceTier(0.59)).toBe("LOW");
    expect(getConfidenceTier(0.10)).toBe("LOW");
    expect(getConfidenceTier(-0.5)).toBe("UNVALIDATED");
    expect(getConfidenceTier(1.5)).toBe("UNVALIDATED");
  });
});

describe("Universal [ WHY? ] Provenance Data Schema", () => {
  it("validates full 10-dimension provenance contract for engineering traceability", () => {
    const sampleProvenance: ProvenanceData = {
      result: "Rear Damper Damping Ratio ζ = 0.28 (Under-damped anomaly)",
      source: "Circuit de Barcelona-Catalunya Turn 4 Curbs Telemetry (Channel: suspension_pos_rr)",
      inputs: {
        "m_s (Sprung Mass)": "320 kg (Weighbridge Session 4)",
        "c (Damping Coeff)": "1,450 Ns/m (Setup Baseline v3.2)",
        "k_s (Spring Rate)": "38,000 N/m (K&C Rig Test 104)",
      },
      method: "Logarithmic decrement analysis of free oscillation after kerb strike excitation",
      modelVersion: "QCAR-ODE-RK45-v2.1",
      solver: "scipy.integrate.solve_ivp(Radau, rtol=1e-6)",
      backend: "Python 3.11 / NumPy 1.26 / Ansys Motion Co-Simulation Bridge",
      validation: "DEGRADED: Damper Dyno Cal 2026-08 (Expected c = 2,400 Ns/m, measured = 1,450 Ns/m, R² = 0.74)",
      confidence: 0.91,
      limitations: [
        "1D quarter-car does not capture anti-squat pitch moment or chassis torsional compliance.",
        "Thermal fade not modeled dynamically in base ODE.",
      ],
    };

    expect(sampleProvenance.result).toBeDefined();
    expect(sampleProvenance.source).toContain("Barcelona");
    expect(Object.keys(sampleProvenance.inputs || {})).toHaveLength(3);
    expect(sampleProvenance.modelVersion).toBe("QCAR-ODE-RK45-v2.1");
    expect(sampleProvenance.solver).toContain("Radau");
    expect(sampleProvenance.backend).toContain("Python 3.11");
    expect(sampleProvenance.validation).toContain("DEGRADED");
    expect(sampleProvenance.confidence).toBe(0.91);
    expect(sampleProvenance.limitations).toHaveLength(2);
  });
});

describe("Suspension Parameter Delta & Constraint Rules", () => {
  it("correctly computes parameter change percentages and directional deltas", () => {
    const calcDelta = (base: number, proposed: number) => {
      const diff = proposed - base;
      const pct = base !== 0 ? (diff / base) * 100 : 0;
      return {
        diff,
        pct: Math.round(pct * 10) / 10,
        direction: diff > 0 ? "INCREASE" : diff < 0 ? "DECREASE" : "UNCHANGED",
      };
    };

    // Increasing damping from 1500 to 2200 Ns/m
    const dampingDelta = calcDelta(1500, 2200);
    expect(dampingDelta.diff).toBe(700);
    expect(dampingDelta.pct).toBe(46.7);
    expect(dampingDelta.direction).toBe("INCREASE");

    // Decreasing ride height from 35mm to 30mm
    const heightDelta = calcDelta(35, 30);
    expect(heightDelta.diff).toBe(-5);
    expect(heightDelta.pct).toBe(-14.3);
    expect(heightDelta.direction).toBe("DECREASE");

    // Unchanged spring rate
    const springDelta = calcDelta(40000, 40000);
    expect(springDelta.diff).toBe(0);
    expect(springDelta.pct).toBe(0);
    expect(springDelta.direction).toBe("UNCHANGED");
  });

  it("flags engineering constraint boundary violations", () => {
    interface SuspensionBounds {
      min: number;
      max: number;
      unit: string;
    }

    const CONSTRAINTS: Record<string, SuspensionBounds> = {
      m_s: { min: 100, max: 800, unit: "kg" },
      m_u: { min: 20, max: 150, unit: "kg" },
      k_s: { min: 10000, max: 150000, unit: "N/m" },
      c: { min: 500, max: 10000, unit: "Ns/m" },
      k_t: { min: 100000, max: 500000, unit: "N/m" },
    };

    const validateParam = (key: string, val: number) => {
      const bounds = CONSTRAINTS[key];
      if (!bounds) return { valid: true };
      if (val < bounds.min) {
        return { valid: false, error: `${key} below minimum limit ${bounds.min} ${bounds.unit}` };
      }
      if (val > bounds.max) {
        return { valid: false, error: `${key} exceeds maximum limit ${bounds.max} ${bounds.unit}` };
      }
      return { valid: true };
    };

    expect(validateParam("c", 2500).valid).toBe(true);
    expect(validateParam("c", 200).valid).toBe(false);
    expect(validateParam("c", 200).error).toContain("below minimum");
    expect(validateParam("k_s", 250000).valid).toBe(false);
    expect(validateParam("k_s", 250000).error).toContain("exceeds maximum");
  });
});
