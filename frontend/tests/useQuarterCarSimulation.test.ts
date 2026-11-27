import { describe, it, expect } from "vitest";
import {
  validateQCarParams,
  buildQCarPayload,
  DEFAULT_QCAR_PARAMS,
  type QCarParams,
} from "../lib/qcarParams";

const VALID: QCarParams = {
  m_s: 300, m_u: 35, k_s: 25000, c: 2050,
  k_t: 200000, MR: 0.85, c_t: 0,
  road_profile: "step", amplitude: 0.05, frequency: 2,
  duration: 5, iso_class: "B", speed_mps: 20,
  damper_curve_v: null, damper_curve_f: null,
};

describe("validateQCarParams", () => {
  it("accepts physically valid parameters", () => {
    expect(validateQCarParams(VALID)).toBeNull();
  });

  it("rejects non-positive sprung mass", () => {
    expect(validateQCarParams({ ...VALID, m_s: 0 })).toMatch(/Sprung Mass/);
    expect(validateQCarParams({ ...VALID, m_s: -10 })).toMatch(/Sprung Mass/);
  });

  it("rejects non-positive unsprung mass", () => {
    expect(validateQCarParams({ ...VALID, m_u: 0 })).toMatch(/Unsprung Mass/);
  });

  it("rejects zero or negative spring rate and damping", () => {
    expect(validateQCarParams({ ...VALID, k_s: 0 })).toMatch(/Spring Rate/);
    expect(validateQCarParams({ ...VALID, k_s: -1 })).toMatch(/Spring Rate/);
    expect(validateQCarParams({ ...VALID, c: -1 })).toMatch(/Damping/);
    expect(validateQCarParams({ ...VALID, c: 0 })).toMatch(/Damping/);
  });
});

describe("buildQCarPayload", () => {
  it("splits parameters into params + profile sections", () => {
    const payload = buildQCarPayload(VALID);
    expect(payload.params.m_s).toBe(300);
    expect(payload.params.k_s).toBe(25000);
    expect(payload.params.MR).toBe(0.85);
    expect(payload.profile.profile_type).toBe("step");
    expect(payload.profile.iso_class).toBe("B");
    expect(payload.profile.speed_mps).toBe(20);
  });

  it("passes damper LUT curves through when present", () => {
    const withLut = {
      ...VALID,
      damper_curve_v: [0, 0.1, 0.5],
      damper_curve_f: [0, 500, 2000],
    };
    const payload = buildQCarPayload(withLut);
    expect(payload.params.damper_curve_v).toEqual([0, 0.1, 0.5]);
    expect(payload.params.damper_curve_f).toEqual([0, 500, 2000]);
  });

  it("produces a JSON-serialisable object", () => {
    const payload = buildQCarPayload(VALID);
    expect(() => JSON.stringify(payload)).not.toThrow();
  });
});
