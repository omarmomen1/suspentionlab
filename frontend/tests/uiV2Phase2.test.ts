import { describe, it, expect } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";
import StudioShell, { ShellLeft, ShellCenter, ShellRight } from "../components/v2/StudioShell";
import VerdictRail from "../components/v2/VerdictRail";
import LedgerTable, { ledgerDelta } from "../components/v2/instruments/LedgerTable";
import BlueprintSVG from "../components/v2/instruments/BlueprintSVG";
import DamperScope from "../components/v2/instruments/DamperScope";
import DifferenceRibbon from "../components/v2/instruments/DifferenceRibbon";
import EnvelopePlot from "../components/v2/instruments/EnvelopePlot";
import { damperWorkLoop, travelBudget, trapezoid, cornerDeltasFromCumulative } from "../lib/v2/instruments";
import { verdictStatus } from "../lib/v2/status";

(globalThis as any).React = React;
const root = path.resolve(import.meta.dirname, "..");
const read = (p: string) => fs.readFileSync(path.join(root, p), "utf8");
const h = React.createElement;

describe("StudioShell and VerdictRail", () => {
  it("renders three regions and the mobile tab switcher", () => {
    const html = renderToStaticMarkup(
      h(StudioShell, null, h(ShellLeft, null, "LEFTX"), h(ShellCenter, null, "CENTERX"), h(ShellRight, null, "RIGHTX")),
    );
    for (const t of ["LEFTX", "CENTERX", "RIGHTX", "Parameters", "Results", "Verdict"]) expect(html).toContain(t);
    expect(html).toContain('role="tablist"');
  });
  it("VerdictRail shows Not available for null heroes, never 0", () => {
    const html = renderToStaticMarkup(
      h(VerdictRail, { status: "NOT_RUN", heroes: [{ label: "Camber", value: null, unit: "deg" }, { label: "MR", value: 0.7, decimals: 2 }] }),
    );
    expect(html).toContain("Not available");
    expect(html).toContain("0.70");
  });
  it("is wired into all four studio pages", () => {
    for (const p of ["kinematics", "quarter-car", "full-car", "handling"]) {
      const s = read(`app/${p}/page.tsx`);
      expect(s, p).toContain("StudioShell");
      expect(s, p).toContain("VerdictRail");
    }
  });
});

describe("LedgerTable", () => {
  const rows = [
    { id: "a", parameter: "Ride freq", value: 1.5, unit: "Hz", base: 1.2, status: "PASS", source: "run 1" },
    { id: "b", parameter: "Peak travel", value: null, unit: "mm", base: null, status: null, source: "run 1" },
  ];
  it("has the six columns and honest empties", () => {
    const html = renderToStaticMarkup(h(LedgerTable, { rows }));
    for (const c of ["Parameter", "Value", "Unit", "Δ Base", "Status", "Source"]) expect(html).toContain(c);
    expect(html).toContain("Not available");
  });
  it("delta is null without a base, not 0", () => {
    expect(ledgerDelta({ value: 1, base: null })).toBeNull();
    expect(ledgerDelta({ value: 1.5, base: 1.2 })).toBeCloseTo(0.3, 9);
  });
});

describe("BlueprintSVG", () => {
  const geo: any = {
    UWI_fwd: [100, 250, 380], UWI_aft: [-100, 250, 380], UWO: [0, 600, 340],
    LWI_fwd: [100, 200, 150], LWI_aft: [-100, 200, 150], LWO: [0, 640, 130],
    WC: [0, 700, 280], CP: [0, 700, 0],
  };
  it("labels ΔY, no ΔX, no baked -89 mm RC, no 0.9-1.1 band", () => {
    const html = renderToStaticMarkup(
      h(BlueprintSVG, { geometry: geo, staticGeometry: geo, travelMm: 0, rollCenterHeightMm: 40, icYMm: 100, icZMm: 50, motionRatio: 0.7, motionRatioBand: [0.6, 0.85], travelValues: [-10, 0, 10], travelIdx: 1 }),
    );
    expect(html).toContain("ΔY");
    expect(html).not.toContain("ΔX");
    expect(html).not.toContain("-89");
    expect(html).not.toMatch(/0\.9\s*[–-]\s*1\.1/);
    expect(html).toContain("0.60");
  });
  it("source has no hardcoded -89 or 25 deg KPI", () => {
    const s = read("components/v2/instruments/BlueprintSVG.tsx");
    expect(s).not.toMatch(/-89/);
    expect(s).not.toMatch(/25\s*°/);
  });
  it("kinematics page offers the 2D/3D toggle and keeps the 3D rig", () => {
    const s = read("app/kinematics/page.tsx");
    expect(s).toContain("2D Blueprint");
    expect(s).toContain("3D Rig");
    expect(s).toContain("SuspensionKinematics3D");
    expect(s).toContain("staticAlignmentFor");
  });
});

describe("DamperScope", () => {
  const n = 200, dt = 0.01, w = 2 * Math.PI * 2, X = 0.01;
  const t = Array.from({ length: n }, (_, i) => i * dt);
  const zS = t.map(() => 0);
  const zU = t.map((tt) => -X * Math.sin(w * tt));
  const dzS = t.map(() => 0);
  const dzU = t.map((tt) => -X * w * Math.cos(w * tt));
  const travel = t.map((tt) => X * Math.sin(w * tt));
  it("shows force vs displacement and % of sim duration, never % of lap", () => {
    const html = renderToStaticMarkup(h(DamperScope, { time: t, zS, zU, dzS, dzU, suspTravelM: travel, damper: { c: 1500, MR: 1 } }));
    expect(html).toContain("Work loop: force vs displacement");
    expect(html).toContain("% of sim duration");
    expect(html).not.toContain("% of lap");
  });
  it("work loop energy matches c * integral v^2 dt", () => {
    const c = 1500;
    const loop = damperWorkLoop(zS, zU, dzS, dzU, { c, MR: 1 });
    const v2 = loop.v_mps.map((v) => v * v);
    const expected = c * (trapezoid(t, v2) as number);
    expect(loop.energy_J as number).toBeCloseTo(expected, 0);
    // 4 cycles at 2 Hz over 2 s: 4 * pi * c * w * X^2 (within 2% for sampling)
    const analytic = 4 * Math.PI * c * w * X * X;
    expect(Math.abs((loop.energy_J as number) - analytic) / analytic).toBeLessThan(0.02);
  });
  it("travel budget is a share of sim duration", () => {
    const b = travelBudget([0, 1, 2, 3, 4], [0, 0.09, 0.09, 0, 0], 80);
    expect(b).not.toBeNull();
    expect(b!.contact_pct_of_sim_duration).toBeGreaterThan(0);
    expect(b!.contact_pct_of_sim_duration).toBeLessThanOrEqual(100);
  });
});

describe("DifferenceRibbon, EnvelopePlot, lap-sim", () => {
  it("renders per-corner bars and a total", () => {
    const html = renderToStaticMarkup(h(DifferenceRibbon, { deltas: [{ corner: "T1", delta_s: -0.05 }, { corner: "T2", delta_s: 0.02 }] }));
    expect(html).toContain("T1");
    expect(html).toContain("-0.030 s");
  });
  it("shows an empty state with no corners", () => {
    expect(renderToStaticMarkup(h(DifferenceRibbon, { deltas: [] }))).toContain("No corner list");
  });
  it("EnvelopePlot carries an optimism disclaimer and no usage percentages", () => {
    const html = renderToStaticMarkup(h(EnvelopePlot, { latG: [0.5, 1], longG: [0, 0.2], limits: { latG: 1.4, accelG: 1, brakeG: 1.5 } }));
    expect(html.toLowerCase()).toContain("optimis");
    expect(html).not.toMatch(/Usage by Phase/i);
  });
  it("LapDeltaView keeps the >10% mismatch guard", () => {
    const s = read("components/sim/LapDeltaView.tsx");
    expect(s).toMatch(/incompatible/i);
    expect(s).toContain("DifferenceRibbon");
  });
  it("lap-sim keeps the fast core solve and has abortable GGV compute", () => {
    const s = read("app/lap-sim/page.tsx");
    expect(s).toContain("include_surface: false");
    expect(s).toContain("AbortController");
    expect(s).toContain("Compute GGV Surface");
    expect(s).toContain("Cancel");
  });
});

describe("verdictStatus", () => {
  it("never reports VERIFIED without a report", () => {
    expect(verdictStatus({ isRunning: false, error: null, hasResults: true }).status).toBe("WARNING");
    expect(verdictStatus({ isRunning: true, error: null, hasResults: false }).status).toBe("RUNNING");
    expect(verdictStatus({ isRunning: false, error: "x", hasResults: false }).status).toBe("FAILED");
    expect(verdictStatus({ isRunning: false, error: null, hasResults: false }).status).toBe("NOT_RUN");
  });
});

describe("Phase 2 components obey the flat-surface rule", () => {
  it("no gradients, blur or glow", () => {
    const files = ["StudioShell", "VerdictRail", "instruments/LedgerTable", "instruments/LedgerDock", "instruments/BlueprintSVG",
      "instruments/DamperScope", "instruments/DifferenceRibbon", "instruments/EnvelopePlot"];
    for (const f of files) expect(read(`components/v2/${f}.tsx`), f).not.toMatch(/gradient|backdrop-blur|shadow-\[|blur-/);
  });
});

// ---------------------------------------------------------------------------
// Hardening: coordinate math and data wiring, computed from rendered output.
// ---------------------------------------------------------------------------
import { GT3_MOTION_RATIO_BAND } from "../lib/v2/instruments";

const nums = (html: string, re: RegExp) => [...html.matchAll(re.global ? re : new RegExp(re.source, re.flags + "g"))].map((m) => m.slice(1).map(Number));
const joints = (html: string) => nums(html, /<circle cx="([-\d.]+)" cy="([-\d.]+)" r="3" fill="#0C0F12"/g);

describe("BlueprintSVG coordinate math (rendered numbers)", () => {
  const base: any = {
    UWI_fwd: [100, 250, 380], UWI_aft: [-100, 250, 380], UWO: [0, 600, 340],
    LWI_fwd: [100, 200, 150], LWI_aft: [-100, 200, 150], LWO: [0, 640, 130],
    WC: [0, 700, 280], CP: [0, 700, 0],
  };
  const render = (g: any, extra: any = {}) =>
    renderToStaticMarkup(h(BlueprintSVG, { geometry: g, staticGeometry: base, travelMm: 0, motionRatio: 0.7, motionRatioBand: GT3_MOTION_RATIO_BAND, ...extra }));

  it("Y runs left to right and Z runs bottom to top, scale is uniform", () => {
    const j = joints(render(base)); // order: UWI mid, LWI mid, UWO, LWO, WC
    expect(j.length).toBe(5);
    const [uwi, lwi, uwo, lwo, wc] = j;
    // Y horizontal: larger Y -> larger cx
    expect(uwo[0]).toBeGreaterThan(uwi[0]);
    expect(wc[0]).toBeGreaterThan(uwo[0]);
    // Z vertical: larger Z -> smaller cy
    expect(uwi[1]).toBeLessThan(lwi[1]);
    expect(wc[1]).toBeLessThan(lwo[1]);
    // uniform scale: px per mm identical on both axes
    const sy = (wc[0] - uwi[0]) / (700 - 250);
    const sz = (wc[1] - uwi[1]) / (380 - 280);
    expect(sy).toBeCloseTo(sz, 4);
    // exact mapping against the input coordinates
    expect((uwo[0] - uwi[0]) / sy).toBeCloseTo(600 - 250, 2);
    expect((lwo[1] - uwo[1]) / sy).toBeCloseTo(340 - 130, 2);
  });

  it("the contact patch sits on the ground line (z = 0)", () => {
    const html = render(base);
    const ground = nums(html, /<line x1="0" y1="([-\d.]+)" x2="520" y2="([-\d.]+)"/)[0];
    const cp = nums(html, /<circle cx="([-\d.]+)" cy="([-\d.]+)" r="3" fill="#FFB84D"/)[0];
    expect(cp[1]).toBeCloseTo(ground[0], 3);
    for (const [, cy] of joints(html)) expect(cy).toBeLessThan(ground[0]);
  });

  it("moving a hardpoint outward shifts only that joint, by exactly dY x scale", () => {
    const a = joints(render(base));
    const moved = { ...base, UWO: [0, 620, 340] };
    const b = joints(render(moved));
    const s = (a[4][0] - a[0][0]) / (700 - 250);
    expect(b[2][0] - a[2][0]).toBeCloseTo(20 * s, 3);
    expect(b[2][1]).toBeCloseTo(a[2][1], 6);
    for (const i of [0, 1, 3, 4]) { expect(b[i][0]).toBeCloseTo(a[i][0], 6); expect(b[i][1]).toBeCloseTo(a[i][1], 6); }
  });

  it("a travel step (wheel centre up 30 mm) lifts the wheel centre by 30 x scale", () => {
    const a = joints(render(base));
    const up = { ...base, WC: [0, 700, 310], UWO: [0, 600, 370] };
    const b = joints(render(up));
    const s = (a[4][0] - a[0][0]) / (700 - 250);
    expect(a[4][1] - b[4][1]).toBeCloseTo(30 * s, 3);
    expect(a[2][1] - b[2][1]).toBeCloseTo(30 * s, 3);
  });

  it("RC and IC are plotted from the supplied solver values, and omitted when absent", () => {
    const withRc = render(base, { rollCenterHeightMm: 40, rollCenterLateralMm: 5, icYMm: 400, icZMm: 100 });
    const rc = nums(withRc, /data-testid="blueprint-rc"><circle cx="([-\d.]+)" cy="([-\d.]+)"/)[0];
    const ground = nums(withRc, /<line x1="0" y1="([-\d.]+)" x2="520"/)[0][0];
    const s = (joints(withRc)[4][0] - joints(withRc)[0][0]) / 450;
    expect(ground - rc[1]).toBeCloseTo(40 * s, 3);
    expect(withRc).toContain('data-testid="blueprint-ic"');
    const none = render(base);
    expect(none).not.toContain("blueprint-rc");
    expect(none).not.toContain("blueprint-ic");
    expect(none).toContain("Not available");
  });

  it("uses the 0.60 to 0.85 GT3 band, never 0.9 to 1.1, and flags out-of-band values", () => {
    expect(GT3_MOTION_RATIO_BAND).toEqual([0.6, 0.85]);
    const inBand = render(base, { motionRatio: 0.7 });
    expect(inBand).toContain("0.60 to 0.85");
    expect(inBand).toContain("inside");
    expect(render(base, { motionRatio: 0.95 })).toContain("outside");
    expect(inBand).not.toMatch(/0\.90? to 1\.10?/);
    expect(read("app/kinematics/page.tsx")).toContain("motionRatioBand={GT3_MOTION_RATIO_BAND}");
  });

  it("labels ΔY and shows the real offsets computed from static vs current geometry", () => {
    const html = render({ ...base, WC: [0, 712.5, 280] });
    expect(html).toContain("ΔY wheel centre");
    expect(html).toContain("12.5");
    expect(html).not.toContain("ΔX");
  });

  it("incomplete geometry gives an explicit empty state, not a drawing", () => {
    const html = renderToStaticMarkup(h(BlueprintSVG, { geometry: { WC: [0, 1, 2] } as any, travelMm: 0 }));
    expect(html).toContain("Not run");
    expect(html).not.toContain("<svg");
  });
});

describe("DamperScope data wiring", () => {
  const n = 120, dt = 0.01, w = 2 * Math.PI * 2, X = 0.01;
  const t = Array.from({ length: n }, (_, i) => i * dt);
  const mk = (amp: number) => ({
    zS: t.map(() => 0), zU: t.map((tt) => -amp * Math.sin(w * tt)),
    dzS: t.map(() => 0), dzU: t.map((tt) => -amp * w * Math.cos(w * tt)),
    suspTravelM: t.map((tt) => amp * Math.sin(w * tt)),
  });
  const render = (amp: number, c = 1500) => renderToStaticMarkup(h(DamperScope, { time: t, ...mk(amp), damper: { c, MR: 1 } }));

  it("work loop plots force (N) against displacement (mm) from the arrays", () => {
    const loop = damperWorkLoop(mk(X).zS, mk(X).zU, mk(X).dzS, mk(X).dzU, { c: 1500, MR: 1 });
    // x is shaft displacement in mm, F = c v, so F peak = c w X and x peak = X*1000 mm
    expect(Math.max(...loop.x_mm)).toBeCloseTo(X * 1000, 0);
    expect(Math.max(...loop.force_N)).toBeCloseTo(1500 * w * X, 0);
    // F against x for a viscous damper encloses area: not a straight line (needs phase offset)
    const html = render(X);
    expect(html).toContain("Work loop: force vs displacement");
    expect(html).toContain("Shaft displacement (mm)");
    expect(html).toContain("Damper force (N)");
    expect(html).not.toMatch(/velocity vs displacement/i);
  });

  it("energy readout equals the integral of c v^2 dt from the same arrays", () => {
    const a = mk(X);
    const loop = damperWorkLoop(a.zS, a.zU, a.dzS, a.dzU, { c: 1500, MR: 1 });
    const expected = 1500 * (trapezoid(t, a.dzU.map((v) => v * v)) as number);
    expect(Math.abs((loop.energy_J as number) - expected) / expected).toBeLessThan(0.01);
    expect(render(X)).toContain(`${(loop.energy_J as number).toFixed(1)} J`);
  });

  it("a different damper coefficient changes the plotted force, so nothing is hardcoded", () => {
    // plotted pixels are auto-scaled, so the energy readout is where magnitude shows up
    const e = (html: string) => Number(html.match(/work-loop-energy">([\d.]+) J/)![1]);
    expect(e(render(X, 3000)) / e(render(X, 1500))).toBeCloseTo(2, 1);
    expect(e(render(2 * X, 1500)) / e(render(X, 1500))).toBeCloseTo(4, 1);
  });

  it("travel budget reads % of sim duration from the supplied travel", () => {
    // amplitude 0.1 m exceeds the 80 mm limit for part of each cycle
    const html = render(0.1);
    const m = html.match(/data-testid="stop-contact">([\d.]+)% of sim duration/);
    expect(m).not.toBeNull();
    expect(Number(m![1])).toBeGreaterThan(0);
    expect(Number(m![1])).toBeLessThan(100);
    // small amplitude never reaches the stop
    expect(render(0.01)).toContain('data-testid="stop-contact">0.0% of sim duration');
    expect(html).not.toContain("% of lap");
  });

  it("no NaN or Infinity in any rendered coordinate, including zero-motion input", () => {
    const z = t.map(() => 0);
    const html = renderToStaticMarkup(h(DamperScope, { time: t, zS: z, zU: z, dzS: z, dzU: z, suspTravelM: z, damper: { c: 1500, MR: 1 } }));
    expect(html).not.toMatch(/NaN|Infinity/);
  });

  it("empty arrays give an explicit empty state", () => {
    const html = renderToStaticMarkup(h(DamperScope, { time: [], zS: [], zU: [], dzS: [], dzU: [], suspTravelM: [], damper: { c: 1500, MR: 1 } }));
    expect(html).toContain("No solver traces yet");
    expect(html).not.toContain("<svg");
  });

  it("a damper LUT is interpolated and flagged as an unverified convention", () => {
    const html = renderToStaticMarkup(h(DamperScope, { time: t, ...mk(X), damper: { c: 0, MR: 1, curve_v: [-1, 0, 1], curve_f: [-2000, 0, 2000] } }));
    expect(html).toContain("damper-curve-note");
    expect(html).toContain("not verified");
  });
});

describe("LedgerTable, DifferenceRibbon, EnvelopePlot data wiring", () => {
  it("ledger shows computed deltas with sign and never a fake zero for a missing value", () => {
    const html = renderToStaticMarkup(h(LedgerTable, { rows: [
      { id: "a", parameter: "P1", value: 10, unit: "mm", base: 8, status: "PASS", source: "run", decimals: 1 },
      { id: "b", parameter: "P2", value: NaN, unit: "mm", base: 8, status: "PASS", source: "run" },
      { id: "c", parameter: "P3", value: 5, unit: "mm", base: undefined, status: undefined, source: "run" },
    ] }));
    expect(html).toContain("+2.0");
    expect(html).not.toMatch(/NaN/);
    expect(ledgerDelta({ value: NaN, base: 8 })).toBeNull();
    expect(ledgerDelta({ value: 5, base: undefined })).toBeNull();
    expect((html.match(/Not available/g) ?? []).length).toBeGreaterThanOrEqual(3);
  });

  it("ribbon bar widths scale with the deltas and the total is their sum", () => {
    const html = renderToStaticMarkup(h(DifferenceRibbon, { deltas: [{ corner: "A", delta_s: -0.2 }, { corner: "B", delta_s: 0.1 }, { corner: "C", delta_s: Number.NaN }] }));
    const widths = nums(html, /width:([\d.]+)%/g).map((m) => m[0]);
    expect(widths.length).toBe(2); // NaN row dropped
    expect(widths[0]).toBeCloseTo(50, 3);
    expect(widths[1]).toBeCloseTo(25, 3);
    expect(html).toContain("-0.100 s");
    expect(html).not.toMatch(/NaN/);
  });

  it("cornerDeltasFromCumulative differences the cumulative trace between zone edges", () => {
    // cumulative delta grows 0.01 s per 10 m
    const d = Array.from({ length: 11 }, (_, i) => i * 10);
    const c = d.map((x) => x * 0.001);
    const out = cornerDeltasFromCumulative(d, c, [{ corner: "T1", start_m: 20, end_m: 60 }, { corner: "bad", start_m: 50, end_m: 40 }]);
    expect(out).toHaveLength(1);
    expect(out[0].delta_s).toBeCloseTo(0.04, 9);
  });

  it("envelope plots samples at the right pixel positions and draws an ellipse only from supplied limits", () => {
    const html = renderToStaticMarkup(h(EnvelopePlot, { latG: [1], longG: [0], limits: { latG: 1.5, accelG: 1, brakeG: 1.2 } }));
    const dots = nums(html, /<circle cx="([-\d.]+)" cy="([-\d.]+)" r="1.2"/g);
    expect(dots).toHaveLength(1);
    // zero longitudinal sits on the horizontal axis line
    const axis = nums(html, /<line x1="30" y1="([-\d.]+)" x2="270"/)[0][0];
    expect(dots[0][1]).toBeCloseTo(axis, 1);
    // positive lateral is right of the vertical axis
    const vAxis = nums(html, /<line x1="([-\d.]+)" y1="30" x2="[-\d.]+" y2="270"/)[0][0];
    expect(dots[0][0]).toBeGreaterThan(vAxis);
    expect(html).toContain("limit-ellipse");
    const noLim = renderToStaticMarkup(h(EnvelopePlot, { latG: [1], longG: [0], limits: null }));
    expect(noLim).not.toContain("limit-ellipse");
    expect(noLim).toContain("Not available");
  });

  it("envelope with no samples is an empty state; NaN samples are dropped", () => {
    expect(renderToStaticMarkup(h(EnvelopePlot, { latG: [], longG: [] }))).toContain("No G samples");
    const html = renderToStaticMarkup(h(EnvelopePlot, { latG: [NaN, 1], longG: [0, 0] }));
    expect(html).not.toMatch(/NaN/);
    expect(nums(html, /<circle cx="([-\d.]+)" cy="([-\d.]+)" r="1.2"/g)).toHaveLength(1);
  });
});
