import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";

const FRONTEND_ROOT = path.resolve(__dirname, "..");
const readFrontend = (rel: string) => fs.readFileSync(path.join(FRONTEND_ROOT, rel), "utf8");

describe("Sprint 2 Visuals & P0/P1 Frontend Fixes", () => {
  it("Landing page mounts LandingHero3D dynamically without SSR", () => {
    const src = readFrontend("app/page.tsx");
    expect(src).toContain('import("../components/v2/LandingHero3D")');
    expect(src).toContain("ssr: false");
    expect(src).toContain("<LandingHero3D />");
  });

  it("Lap-Sim defaults Spa elevation ON and TerrainElevation3D uses larger high-contrast viewport", () => {
    const lapSrc = readFrontend("app/lap-sim/page.tsx");
    expect(lapSrc).toContain("const [includeElevation, setIncludeElevation] = useState<boolean>(true);");
    expect(lapSrc.indexOf('data-testid="terrain-section"')).toBeLessThan(lapSrc.indexOf("<EnvelopePlot"));

    const terrSrc = readFrontend("components/v2/instruments/TerrainElevation3D.tsx");
    expect(terrSrc).toContain("h-[360px] lg:h-[420px]");
    expect(terrSrc).not.toContain("h-[240px]");
  });

  it("Full-Car defaults to Footprints & Attitude at index 0 with lime tab styling", () => {
    const fcSrc = readFrontend("app/full-car/page.tsx");
    const tabsMatch = fcSrc.match(/const TABS = \[\s*\{ label: "([^"]+)"/);
    expect(tabsMatch?.[1]).toBe("Footprints & Attitude");
    expect(fcSrc).not.toContain("bg-ansys-yellow");
  });

  it("Kinematics surfaces Motion Ratio heatmap in primary workspace tab and first in MR tab", () => {
    const kinSrc = readFrontend("app/kinematics/page.tsx");
    expect(kinSrc).toContain('data-testid="workspace-mr-field-card"');
    expect(kinSrc).toContain("computeMrField();");
    expect(kinSrc.indexOf('data-testid="mr-field-card"')).toBeLessThan(
      kinSrc.indexOf('"Damper Motion Ratio (Spring / Wheel Deflection Rate) vs Wheel Travel"')
    );
  });

  it("P1 PDF, Legal & Credibility literals removed", () => {
    const pdfSrc = readFrontend("components/PDFExport.tsx");
    expect(pdfSrc).not.toContain("Compliance Certificate");
    expect(pdfSrc).not.toContain("VERIFIED PROVENANCE");
    expect(pdfSrc).not.toContain("0.9945");
    expect(pdfSrc).not.toContain("Crest Factor: 2.14");

    const reportSrc = readFrontend("app/report/page.tsx");
    expect(reportSrc).not.toContain("8-Hour Daily Limit: PASS");

    const privacySrc = readFrontend("app/legal/privacy/page.tsx");
    expect(privacySrc).not.toContain("Railway.app");
    expect(privacySrc).toContain("Vercel");

    const invSrc = readFrontend("app/investigate/page.tsx");
    expect(invSrc).not.toContain('confidence={0.88} sourceTag="Active Telemetry R²"');
    expect(invSrc).not.toContain("confidence: 0.90");

    const twinSrc = readFrontend("app/digital-twin/page.tsx");
    expect(twinSrc).not.toContain(">Measured (DAQ)<");
    expect(twinSrc).toContain("SAMPLE");
  });
});
