import { describe, it, expect } from "vitest";
import { DEFAULT_HERO_GEOMETRY as G, solvePose, wheelTravelMm } from "../components/v2/LandingHero3D";

const d = (a: number[], b: number[]) => Math.hypot(a[0] - b[0], a[1] - b[1]);

describe("LandingHero3D linkage solve", () => {
  it("rest pose reproduces the hardpoints", () => {
    const p = solvePose(G, 0)!;
    expect(d(p.uwo, G.uwo)).toBeLessThan(1e-6);
    expect(d(p.wc, G.wc)).toBeLessThan(1e-6);
  });
  it("keeps every rigid length constant through bump and droop", () => {
    for (const a of [-0.1, -0.05, 0.05, 0.1]) {
      const p = solvePose(G, a)!;
      expect(p).not.toBeNull();
      expect(d(p.uwo, G.uwi)).toBeCloseTo(d(G.uwo, G.uwi), 6);
      expect(d(p.lwo, G.lwi)).toBeCloseTo(d(G.lwo, G.lwi), 6);
      expect(d(p.uwo, p.lwo)).toBeCloseTo(d(G.uwo, G.lwo), 6);
      expect(d(p.wc, p.lwo)).toBeCloseTo(d(G.wc, G.lwo), 6);
    }
  });
  it("positive arm rotation lifts the wheel", () => {
    expect(wheelTravelMm(G, 0.05)!).toBeGreaterThan(0);
    expect(wheelTravelMm(G, -0.05)!).toBeLessThan(0);
  });
});
