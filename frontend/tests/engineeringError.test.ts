import { describe, it, expect } from "vitest";
import { parseEngineeringError } from "../components/sim/EngineeringErrorDisplay";

describe("Engineering Solver Diagnostics & RFC 7807 Parser", () => {
  it("should parse negative sprung mass violation into actionable guidance", () => {
    const rawError = {
      detail: "Validation failed: Sprung mass cannot be negative (received m_s = -450 kg)",
      request_id: "req-phys-991",
    };

    const parsed = parseEngineeringError(rawError);

    expect(parsed.severity).toBe("VALIDATION");
    expect(parsed.cause).toContain("Physical mass");
    expect(parsed.impact).toContain("singularity");
    expect(parsed.nextAction).toContain("sprung mass");
    expect(parsed.what).toContain("Inertial");
    expect(parsed.where).toContain("m_s");
    expect(parsed.code).toBe("INERTIA_INVALID");
    expect(parsed.requestId).toBe("req-phys-991");
  });

  it("should detect undamped oscillator resonance condition", () => {
    const rawError = "Divergence: Undamped system detected with c = 0 Ns/m causing pure imaginary poles.";

    const parsed = parseEngineeringError(rawError);

    expect(parsed.severity).toBe("DIVERGENCE");
    expect(parsed.code).toBe("UNDAMPED_RESONANCE");
    expect(parsed.cause).toContain("damping coefficient");
    expect(parsed.impact).toContain("unbounded state resonance");
    expect(parsed.nextAction).toContain("damping coefficient");
    expect(parsed.what).toContain("Damped Harmonic Oscillator");
  });

  it("should identify numerical ODE integrator step size underflow", () => {
    const rawError = {
      detail: "scipy.integrate.solve_ivp failed: Step size underflow in RK45 integrator. System matrix is stiff.",
      request_id: "req-rk45-div",
    };

    const parsed = parseEngineeringError(rawError);

    expect(parsed.severity).toBe("DIVERGENCE");
    expect(parsed.code).toBe("SOLVER_DIVERGENCE");
    expect(parsed.cause).toContain("Adaptive step size underflow");
    expect(parsed.impact).toContain("RK45 integrator halted");
    expect(parsed.nextAction).toContain("Radau/BDF");
    expect(parsed.what).toContain("Adaptive ODE Integrator");
  });

  it("should identify rate limit / worker quota exhaustion", () => {
    const rawError = "HTTP 429: Worker rate limit exceeded. Concurrency quota full.";

    const parsed = parseEngineeringError(rawError);

    expect(parsed.severity).toBe("SYSTEM");
    expect(parsed.code).toBe("QUOTA_EXCEEDED");
    expect(parsed.cause).toContain("limit");
    expect(parsed.impact).toContain("throttled");
    expect(parsed.nextAction).toContain("Wait");
    expect(parsed.what).toContain("Compute Governance");
  });

  it("should parse structured RFC 7807 pydantic errors with parameter locations", () => {
    const pydanticError = {
      detail: JSON.stringify({
        errors: [
          {
            loc: ["body", "k_spring_front"],
            msg: "ensure this value is greater than 0",
            type: "value_error.number.not_gt",
          },
        ],
        request_id: "req-pyd-102",
      }),
    };

    const parsed = parseEngineeringError(pydanticError);

    expect(parsed.severity).toBe("VALIDATION");
    expect(parsed.where).toBe("body -> k_spring_front");
    expect(parsed.cause).toContain("greater than 0");
    expect(parsed.impact).toContain("Payload rejected");
    expect(parsed.nextAction).toContain("Review input parameter");
    expect(parsed.requestId).toBe("req-pyd-102");
  });
});
