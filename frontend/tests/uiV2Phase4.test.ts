import { describe, it, expect } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";
import FourFootprintsSVG from "../components/v2/instruments/FourFootprintsSVG";
import MotionRatioField from "../components/v2/instruments/MotionRatioField";
import { WhyChainRows } from "../components/v2/instruments/WhyChainPanel";
import { AttitudeReadout } from "../components/v2/instruments/AttitudeModel3D";
import { TerrainReadout, terrainReadout, TERRAIN_DISCLAIMER } from "../components/v2/instruments/TerrainElevation3D";
import {
  cornerLoadsAt, maxCornerLoadN, attitudeAt, exaggeratedPose, mrFieldCells, whyChainLevers, whyChainRows,
  type SteerGridResponse, type WhyChainResponse,
} from "../lib/v2/phase4";

(globalThis as any).React = React;
const root = path.resolve(import.meta.dirname, "..");
const fx = (n: string) => JSON.parse(fs.readFileSync(path.join(root, "tests/fixtures", n), "utf8"));
const read = (p: string) => fs.readFileSync(path.join(root, p), "utf8");
const h = React.createElement;

// Fixtures are real solver outputs (full_car.py, solve_steer_grid, compute_why_chain), not hand-written numbers.
const car = fx("phase4_full_car.json");
const lp = { m_s: car.params.m_s, m_uf: car.params.m_uf, m_ur: car.params.m_ur, a: car.params.a, b: car.params.b, k_tf: car.params.k_tf, k_tr: car.params.k_tr };

describe("FourFootprintsSVG wiring", () => {
  it("rebuilds the solver's own tire-load KPIs from the returned series", () => {
    const n = car.result.time.length;
    let min = Infinity;
    let sq = 0;
    const staticF = cornerLoadsAt(car.result, lp, 0)!.staticFrontN;
    for (let i = 0; i < n; i++) {
      const c = cornerLoadsAt(car.result, lp, i)!;
      min = Math.min(min, c.fl, c.fr, c.rl, c.rr);
      sq += (c.fl - staticF) ** 2;
    }
    expect(min).toBeCloseTo(car.result.minimum_Fz, 6);
    expect(Math.sqrt(sq / n)).toBeCloseTo(car.result.rms_tire_load_fl, 6);
  });

  it("draws one bar per corner whose height is linear in Fz, with the number printed", () => {
    const idx = 400;
    const html = renderToStaticMarkup(h(FourFootprintsSVG, { result: car.result, params: lp, index: idx }));
    const c = cornerLoadsAt(car.result, lp, idx)!;
    const scale = maxCornerLoadN(car.result, lp)!;
    for (const k of ["fl", "fr", "rl", "rr"] as const) {
      const g = html.match(new RegExp(`<g data-corner="${k}" data-fz="([0-9.]+)"`));
      expect(g).not.toBeNull();
      expect(Number(g![1])).toBeCloseTo(c[k], 2);
      const bar = html.match(new RegExp(`data-bar="${k}" x="[0-9.]+" y="[0-9.]+" width="[0-9.]+" height="([0-9.]+)"`));
      expect(Number(bar![1])).toBeCloseTo((c[k] / scale) * 110, 2);
      expect(html).toContain(`${Math.round(c[k])} N`);
    }
    // load-transfer pairing is the left-minus-right difference of the real loads
    expect(html).toContain(`Front L-R ${Math.round(c.frontLeftMinusRightN)} N`);
    expect(html).toContain(`Rear L-R ${Math.round(c.rearLeftMinusRightN)} N`);
  });

  it("states what is not modeled and never draws a slip angle", () => {
    const html = renderToStaticMarkup(h(FourFootprintsSVG, { result: car.result, params: lp, index: 10 }));
    expect(html).toContain("Slip angle and lateral force: not modeled");
    expect(html).not.toMatch(/°/);
  });

  it("shows Not run when there is no series, instead of zero loads", () => {
    const html = renderToStaticMarkup(h(FourFootprintsSVG, { result: {}, params: lp, index: 0 }));
    expect(html).toContain("Not run");
    expect(html).not.toContain("data-corner");
  });

  it("flags a corner with Fz clamped at 0 as contact lost", () => {
    const res = { ...car.result, z_ufl: [...car.result.z_ufl] };
    res.z_ufl[5] = res.z_rfl[5] + 1.0; // unsprung mass 1 m above the road: tire force negative, clamped to 0
    const c = cornerLoadsAt(res, lp, 5)!;
    expect(c.fl).toBe(0);
    expect(c.liftedCorners).toContain("fl");
    const html = renderToStaticMarkup(h(FourFootprintsSVG, { result: res, params: lp, index: 5 }));
    expect(html).toContain("Contact lost (Fz = 0): FL");
  });
});

describe("Attitude model data", () => {
  it("reads true heave, roll and pitch from the 7-DOF series and labels the x10", () => {
    const i = 300;
    const a = attitudeAt(car.result, i)!;
    expect(a.heave_mm).toBeCloseTo(car.result.z_s[i] * 1000, 9);
    expect(a.roll_deg).toBeCloseTo((car.result.phi[i] * 180) / Math.PI, 9);
    expect(a.pitch_deg).toBeCloseTo((car.result.theta[i] * 180) / Math.PI, 9);
    const p = exaggeratedPose(a);
    expect(p.roll_deg).toBeCloseTo(a.roll_deg * 10, 9);
    const html = renderToStaticMarkup(h(AttitudeReadout, { result: car.result, index: i }));
    expect(html).toContain("×10 exaggeration");
    expect(html).toContain(`${a.roll_deg.toFixed(3)}°`);
    expect(html).toContain(`${a.heave_mm.toFixed(2)} mm`);
  });
  it("returns null, not zeros, without the series", () => {
    expect(attitudeAt({}, 0)).toBeNull();
    expect(renderToStaticMarkup(h(AttitudeReadout, { result: {}, index: 0 }))).toContain("Not run");
  });
});

describe("MotionRatioField", () => {
  const grid = fx("phase4_steer_grid.json") as SteerGridResponse;
  it("fixture really contains unreachable cells (None)", () => {
    expect(grid.motion_ratio.flat().some((v) => v === null)).toBe(true);
  });
  it("draws one cell per (rack, bump); None cells are hatched with no number", () => {
    const html = renderToStaticMarkup(h(MotionRatioField, { data: grid }));
    const cells = [...html.matchAll(/<g data-cell="true" data-row="(\d+)" data-col="(\d+)" data-reachable="([01])"( data-mr="([0-9.-]+)")?/g)];
    expect(cells.length).toBe(grid.rack_travel_mm.length * grid.bump_mm.length);
    for (const m of cells) {
      const r = Number(m[1]), c = Number(m[2]);
      const v = grid.motion_ratio[r][c];
      if (v === null) {
        expect(m[3]).toBe("0");
        expect(m[5]).toBeUndefined();
      } else {
        expect(m[3]).toBe("1");
        expect(Number(m[5])).toBeCloseTo(v, 4);
      }
    }
    const { unreachable, min, max } = mrFieldCells(grid);
    expect(html).toContain(`${unreachable} hatched cells: unreachable`);
    expect(html).toContain(`MR range ${min!.toFixed(3)} to ${max!.toFixed(3)}`);
    expect(html).toContain("Clearances: NOT_MODELED");
  });
  it("shows Not run before any solve", () => {
    expect(renderToStaticMarkup(h(MotionRatioField, { data: null }))).toContain("Not run");
  });
  it("puts +rack at the top row", () => {
    const html = renderToStaticMarkup(h(MotionRatioField, { data: grid }));
    const y = (r: number) => Number(html.match(new RegExp(`data-row="${r}" data-col="0"[^>]*><rect x="[0-9.]+" y="([0-9.]+)"`))![1]);
    expect(y(grid.rack_travel_mm.length - 1)).toBeLessThan(y(0));
  });
});

describe("WhyChainPanel", () => {
  const complete = fx("phase4_why_chain_complete.json") as WhyChainResponse;
  const stopped = fx("phase4_why_chain_stopped.json") as WhyChainResponse;
  it("renders every link of a complete chain with unit, source and its numbers", () => {
    const html = renderToStaticMarkup(h(WhyChainRows, { result: complete }));
    expect(html).toContain('data-complete="1"');
    for (const l of complete.chain) {
      expect(html).toContain(`data-link="${l.link}" data-status="OK"`);
      expect(html).toContain(l.solver_source!);
    }
    const rows = whyChainRows(complete);
    const apex = rows.find((r) => r.link === "qss_apex_speed")!.numbers.find((n) => n.path === "apex_speed_ms.delta")!;
    expect(html).toContain(`data-path="apex_speed_ms.delta" data-value="${apex.value}"`);
  });
  it("stops cleanly: NOT_MODELED links carry a reason code and no numbers", () => {
    const html = renderToStaticMarkup(h(WhyChainRows, { result: stopped }));
    expect(html).toContain('data-complete="0"');
    expect(html).toContain('data-link="input_delta" data-status="OK"');
    const nm = [...html.matchAll(/data-status="NOT_MODELED"/g)].length;
    expect(nm).toBe(stopped.chain.length - 1);
    expect(html).toContain("LEVER_HAS_NO_PATH_TO_ROLL_STIFFNESS");
    for (const r of whyChainRows(stopped).slice(1)) expect(r.numbers).toEqual([]);
  });
  it("sends only changed levers, converted from UI N/mm to backend N/m", () => {
    const lv = whyChainLevers({ front_arb: 45, rear_arb: 30, mass: 1300 }, { front_arb: 60, rear_arb: 30, mass: 1400, static_rh_front_mm: 50 });
    expect(lv.setup_a).toEqual({ k_arb_front_n_m: 45000 });
    expect(lv.setup_b).toEqual({ k_arb_front_n_m: 60000 });
    expect(lv.changed).toEqual(["k_arb_front_n_m"]);
    expect(whyChainLevers({ front_arb: 45 }, { front_arb: 45 }).changed).toEqual([]);
  });
});

describe("Terrain readout", () => {
  it("shows the coarse-station disclaimer for a real profile and flat for z = 0", () => {
    const html = renderToStaticMarkup(h(TerrainReadout, { trace: { z_m: [418, 424, 419], vertical_g: [0, 0.2, -0.1], compression_mm: [1, 2, 3] } }));
    expect(html).toContain(TERRAIN_DISCLAIMER);
    expect(html).toContain("-0.100 to 0.200 g");
    const flat = renderToStaticMarkup(h(TerrainReadout, { trace: { z_m: [0, 0, 0], vertical_g: [0, 0, 0], compression_mm: [1, 1, 1] } }));
    expect(flat).toContain("Flat track: z = 0");
    expect(renderToStaticMarkup(h(TerrainReadout, { trace: {} }))).toContain("Not available");
    expect(terrainReadout({ z_m: [1, 2, 3] })!.vg).toBeNull();
  });
});

describe("One WebGL canvas per route", () => {
  const canvasUsers = (rel: string) => {
    const src = read(rel);
    return [...src.matchAll(/dynamic\(\(\) => import\("([^"]+)"\)/g)].map((m) => m[1]);
  };
  it("full-car mounts one 3D component, loaded client-side only", () => {
    const src = read("app/full-car/page.tsx");
    expect(canvasUsers("app/full-car/page.tsx").filter((p) => /3D$/.test(p))).toEqual(["../../components/v2/instruments/AttitudeModel3D"]);
    expect(src).toMatch(/ssr: false/);
  });
  it("lap-sim mounts one 3D component; kinematics adds none beyond its existing one", () => {
    expect(canvasUsers("app/lap-sim/page.tsx").filter((p) => /3D$/.test(p))).toEqual(["../../components/v2/instruments/TerrainElevation3D"]);
    expect(read("app/kinematics/page.tsx")).not.toMatch(/from "@react-three/);
    expect(read("components/v2/instruments/MotionRatioField.tsx")).not.toMatch(/three/i);
    expect(read("components/v2/instruments/FourFootprintsSVG.tsx")).not.toMatch(/three/i);
  });
});
