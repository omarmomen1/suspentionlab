import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { validateQCarParams, DEFAULT_QCAR_PARAMS } from "../lib/qcarParams";

const FRONTEND_ROOT = path.resolve(__dirname, "..");

function readFrontend(relPath: string): string {
  return fs.readFileSync(path.join(FRONTEND_ROOT, relPath), "utf8");
}

describe("Sprint 1 Fixes — Frontend Verification", () => {
  it("Item 1: Primary CTAs use single lime signal accent without competing orange/yellow buttons", () => {
    const filesToCheck = [
      "components/Navbar.tsx",
      "components/UserMenu.tsx",
      "components/MobileNav.tsx",
      "components/engineering/ExperimentButton.tsx",
      "components/sim/LapDeltaView.tsx",
      "app/quarter-car/page.tsx",
      "app/kinematics/page.tsx",
      "app/optimize/page.tsx",
      "app/pricing/page.tsx",
    ];
    for (const rel of filesToCheck) {
      const src = readFrontend(rel);
      expect(src).not.toMatch(/bg-ansys-yellow[^"\n]*text-black/);
      expect(src).not.toMatch(/\bbg-\[#f2a900\]/);
      expect(src).not.toMatch(/\bbg-amber-500\b[^"\n]*text-black/);
      expect(src).toMatch(/\bbg-signal\b/);
    }
  });

  it("Item 2: Quarter-Car validation rejects k_s<=0 and c<=0 and guards Infinity static deflection", () => {
    expect(validateQCarParams({ ...DEFAULT_QCAR_PARAMS, k_s: 0 })).toMatch(/Spring Rate/i);
    expect(validateQCarParams({ ...DEFAULT_QCAR_PARAMS, c: 0 })).toMatch(/Damping/);
    expect(validateQCarParams({ ...DEFAULT_QCAR_PARAMS, c: -50 })).toMatch(/Damping/);
    expect(validateQCarParams(DEFAULT_QCAR_PARAMS)).toBeNull();

    const qcarPage = readFrontend("app/quarter-car/page.tsx");
    expect(qcarPage).toContain('data-testid="qcar-param-error"');
    expect(qcarPage).toContain("kw > 0 && Number.isFinite(kw)");
  });

  it("Item 3: Kinematics page defaults to GT3 Touring preset hardpoints", () => {
    const kinPage = readFrontend("app/kinematics/page.tsx");
    expect(kinPage).toContain('const [selectedPreset, setSelectedPreset] = useState<string>("gt3_touring")');
    expect(kinPage).toContain("WC: [-7.05, 758.0, 330.0]");
    expect(kinPage).toContain("CP: [-7.05, 758.0, 0.0]");
  });

  it("Item 4: Correlation CSV upload requires recognizable time + telemetry channels", () => {
    const corrPage = readFrontend("app/correlation/page.tsx");
    expect(corrPage).toContain("RECOGNIZED_TELEMETRY_CHANNELS");
    expect(corrPage).toContain('data-testid="telemetry-schema-error"');
    expect(corrPage).toContain("Telemetry CSV schema rejected");
  });

  it("Item 5: Optimize page defaults match widened Pareto frontier grid", () => {
    const optPage = readFrontend("app/optimize/page.tsx");
    expect(optPage).toContain("const [ksMin, setKsMin] = useState<number>(15000)");
    expect(optPage).toContain("const [ksMax, setKsMax] = useState<number>(55000)");
    expect(optPage).toContain("const [cMin, setCMin] = useState<number>(900)");
    expect(optPage).toContain("const [cMax, setCMax] = useState<number>(3900)");
  });

  it("Item 6: Report page removes fake placeholder deltas and supports baseline comparison", () => {
    const reportPage = readFrontend("app/report/page.tsx");
    const pdfExport = readFrontend("components/PDFExport.tsx");
    for (const fake of ["-0.087 s", "+1.8 %", "+3.1 %", "Residual MAE: 1.41 mm", "+0.000 s (Baseline)"]) {
      expect(reportPage).not.toContain(fake);
      expect(pdfExport).not.toContain(fake);
    }
    expect(reportPage).toContain("Baseline run (no comparison)");
  });

  it("Item 7 & 8: AI Engineer avoids Object.entries(predicted_effects) and surfaces 403 approval errors", () => {
    const aiPage = readFrontend("app/ai-engineer/page.tsx");
    expect(aiPage).not.toContain("Object.entries(result.predicted_effects)");
    expect(aiPage).not.toContain("RK45-ODE-v2.4");
    expect(aiPage).toContain("telemetry_session_id: workspace.telemetry.sessionId");
    expect(aiPage).toContain('data-testid="ai-approve-error"');
    expect(aiPage).toContain("403");
  });
});
