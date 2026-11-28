import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const read = (p: string) => fs.readFileSync(path.join(root, p), "utf8");

function walkTsx(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkTsx(full));
    else if (entry.name.endsWith(".tsx")) out.push(full);
  }
  return out;
}

describe("Enterprise Cleanup — Typography, Lime Sweep & Security Headers", () => {
  it("eliminates ansys-yellow tokens and micro-text (<12px Tailwind classes) in app/ and components/", () => {
    const files = [...walkTsx(path.join(root, "app")), ...walkTsx(path.join(root, "components"))];
    for (const f of files) {
      const content = fs.readFileSync(f, "utf8");
      const rel = path.relative(root, f);
      expect(content, `${rel} still contains ansys-yellow`).not.toContain("ansys-yellow");
      expect(content, `${rel} still contains micro-text class`).not.toMatch(/text-\[(?:8|9|10|11)px\]/);
    }
  });

  it("enforces readable carbon theme, lime focus ring, and contrast floor in layout/globals", () => {
    const css = read("app/globals.css");
    expect(css).toContain("--background: #0C0F12;");
    expect(css).toContain("outline: 2px solid #C8F04B !important;");
    const layout = read("app/layout.tsx");
    expect(layout).toContain("antialiased");
    expect(layout).toContain("selection:bg-signal");
  });

  it("adds security headers in next.config.mjs", () => {
    const cfg = read("next.config.mjs");
    expect(cfg).toContain("async headers()");
    expect(cfg).toContain("X-Content-Type-Options");
    expect(cfg).toContain("X-Frame-Options");
    expect(cfg).toContain("Referrer-Policy");
    expect(cfg).toContain("Permissions-Policy");
  });

  it("provides distinct <title> metadata layout.tsx on all key studio routes", () => {
    const routes = [
      "quarter-car", "kinematics", "full-car", "half-car", "lap-sim", "handling",
      "optimize", "compare", "durability", "nvh", "yaw-dynamics", "experiment",
      "garage", "settings", "onboarding", "docs", "evaluation", "timeline",
    ];
    for (const r of routes) {
      const lp = path.join(root, "app", r, "layout.tsx");
      expect(fs.existsSync(lp), `missing layout.tsx for /${r}`).toBe(true);
      const txt = fs.readFileSync(lp, "utf8");
      expect(txt).toContain("| SuspensionLab");
    }
  });
});

describe("Enterprise Cleanup — Studio P1 Remediation", () => {
  it("distinguishes uncoupled preview from coupled 4-state eigenvalues in quarter-car & DataExport", () => {
    const qc = read("app/quarter-car/page.tsx");
    expect(qc).toContain("Analytical Preview (Uncoupled 1-DOF: k_w / m_s)");
    expect(qc).toContain("State-Space Summary (Coupled 4-State Eigenvalues)");
    expect(qc).toContain("Sprung ƒₙ (coupled)");
    expect(qc).toContain('apiFetch("/api/v1/profiles/"');
    expect(read("components/DataExport.tsx")).toContain("coupled 4-state ODE eigenvalues");
  });

  it("aligns /experiment q1 to k_s, adds NO_CHANGE in /compare, cleans /vnv and /nvh", () => {
    const exp = read("app/experiment/page.tsx");
    expect(exp).toContain("What happens if I increase front spring rate (k_s) by 10%?");
    expect(read("app/compare/page.tsx")).toContain("NO_CHANGE");
    const vnv = read("app/vnv/page.tsx");
    expect(vnv).not.toContain("ISO 16331");
    expect(vnv).not.toContain("DIN 70000");
    const nvh = read("app/nvh/page.tsx");
    expect(nvh).toContain("A-Weighted Transfer Gain (dB)");
    expect(nvh).not.toContain("Acoustic Noise (dBA)");
  });

  it("sets realistic defaults & infeasible grip banner in /yaw-dynamics and aero/saturation guard in /handling", () => {
    const yaw = read("app/yaw-dynamics/page.tsx");
    expect(yaw).toContain("v_ms:      27.78");
    expect(yaw).toContain("radius_m:  100.0");
    expect(yaw).toContain('data-testid="yaw-infeasible-warning"');

    const handling = read("app/handling/page.tsx");
    expect(handling).toContain("C_l: 1.65");
    expect(handling).toContain("assumptionsWarnings");
    expect(handling).toContain("mu_util_f");
  });

  it("removes nested <main> in /kinematics and escalates KinematicsModelValidity on benchmark failures", () => {
    const kin = read("app/kinematics/page.tsx");
    expect(kin).not.toContain("<main");
    expect(kin).not.toContain("</main>");
    const val = read("components/kinematics/KinematicsModelValidity.tsx");
    expect(val).toContain("failedBenchmarksCount");
    expect(val).toContain("warnBenchmarksCount");
  });

  it("honestly labels /durability constants and updates /onboarding, /docs, /settings, /evaluation, /timeline", () => {
    const dur = read("app/durability/page.tsx");
    expect(dur).toContain("SCHEMATIC / PLACEHOLDER CONSTANTS");
    expect(dur).toContain("Schematic Proxy D");

    const onb = read("app/onboarding/page.tsx");
    expect(onb).toContain(`"You're all set"`);
    expect(onb).not.toContain("You&apos;re all set");
    expect(onb).toContain("isPaidPlan");
    expect(onb).toContain("bg-signal");

    const docs = read("app/docs/page.tsx");
    expect(docs).toContain("BDF (Implicit Backward Differentiation Formula)");
    expect(docs).toContain("I_x·φ̈");

    const settings = read("app/settings/page.tsx");
    expect(settings).toContain("Contact Sales");
    expect(settings).not.toContain("Upgrade to Enterprise");

    const evalPage = read("app/evaluation/page.tsx");
    expect(evalPage).toContain("!trial");
    expect(evalPage).toContain("Standard Workspace");

    expect(read("app/timeline/page.tsx")).not.toContain("James Wilson");
    expect(read("components/engineering/DecisionLoopCockpit.tsx")).not.toContain("James Wilson");
    expect(read("components/engineering/DecisionLoopCockpit.tsx")).not.toContain("Session 381");
  });
});
