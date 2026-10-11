import { describe, it, expect } from "vitest";
import { resolveValidityTier, ValidityReport } from "../components/ModelValidity";

describe("4-Tier Model Validity Engine", () => {
  it("should classify high score without fatal checks as VALIDATED", () => {
    const report: ValidityReport = {
      score: 92,
      checks: [
        { label: "Tire Slip Envelope", status: "pass", detail: "alpha < 6 deg" },
        { label: "Damper Linearity", status: "pass", detail: "dyno match" },
      ],
    };

    expect(resolveValidityTier(report)).toBe("VALIDATED");
  });

  it("should classify medium score (60-79) as CONDITIONAL", () => {
    const report: ValidityReport = {
      score: 72,
      checks: [
        { label: "Tire Slip Envelope", status: "pass", detail: "nominal" },
        { label: "Aero Sensitivity", status: "warn", detail: "simplified rake" },
      ],
    };

    expect(resolveValidityTier(report)).toBe("CONDITIONAL");
  });

  it("should classify exploratory score (35-59) as EXPERIMENTAL", () => {
    const report: ValidityReport = {
      score: 45,
      checks: [
        { label: "Tire Model", status: "warn", detail: "linear tire approximation" },
      ],
    };

    expect(resolveValidityTier(report)).toBe("EXPERIMENTAL");
  });

  it("should classify low score (<35) or fatal violation as OUT-OF-DOMAIN", () => {
    const lowScoreReport: ValidityReport = {
      score: 22,
      checks: [
        { label: "Tire Model", status: "fail", detail: "extreme tire slip angle saturation" },
      ],
    };

    const fatalReport: ValidityReport = {
      score: 88,
      checks: [
        { label: "Ride Height", status: "fail", detail: "chassis floor bottoming on track surface" },
      ],
    };

    expect(resolveValidityTier(lowScoreReport)).toBe("OUT-OF-DOMAIN");
    expect(resolveValidityTier(fatalReport)).toBe("OUT-OF-DOMAIN");
  });

  it("should respect explicit status_tier if provided by backend", () => {
    const report: ValidityReport = {
      score: 95,
      status_tier: "CONDITIONAL",
      checks: [],
    };

    expect(resolveValidityTier(report)).toBe("CONDITIONAL");
  });
});
