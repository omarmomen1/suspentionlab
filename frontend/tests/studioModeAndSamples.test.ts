import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

(globalThis as any).React = React;

vi.mock("next/navigation", () => ({
  usePathname: () => "/kinematics",
}));

vi.mock("next/link", () => ({
  default: ({ href, children, prefetch: _prefetch, ...props }: any) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: null,
    loading: false,
    logout: vi.fn(),
    fetchWithAuth: vi.fn(),
  }),
}));

import Navbar from "../components/Navbar";
import MobileNav from "../components/MobileNav";
import SampleDemoTelemetryBadge from "../components/engineering/SampleDemoTelemetryBadge";
import TelemetryChart from "../components/engineering/TelemetryChart";
import {
  STUDIO_TOOLS,
  isStudioModeEnabled,
  isToolGroupActive,
} from "../lib/navigation";
import {
  SAMPLE_TELEMETRY_DATASETS,
  isSampleTelemetryFilename,
} from "../lib/sampleTelemetry";
import nextConfig from "../next.config.mjs";

const FRONTEND_ROOT = path.resolve(import.meta.dirname, "..");

describe("NEXT_PUBLIC_STUDIO_MODE Navigation Feature Flag", () => {
  const originalEnv = process.env.NEXT_PUBLIC_STUDIO_MODE;

  beforeEach(() => {
    delete process.env.NEXT_PUBLIC_STUDIO_MODE;
  });

  afterEach(() => {
    if (originalEnv === undefined) {
      delete process.env.NEXT_PUBLIC_STUDIO_MODE;
    } else {
      process.env.NEXT_PUBLIC_STUDIO_MODE = originalEnv;
    }
  });

  it("reads NEXT_PUBLIC_STUDIO_MODE strictly as === 'true'", () => {
    expect(isStudioModeEnabled()).toBe(false);
    process.env.NEXT_PUBLIC_STUDIO_MODE = "false";
    expect(isStudioModeEnabled()).toBe(false);
    process.env.NEXT_PUBLIC_STUDIO_MODE = "true";
    expect(isStudioModeEnabled()).toBe(true);
  });

  it("defines the exact 6 Studio engineering tools and all 10 routes", () => {
    expect(STUDIO_TOOLS).toHaveLength(6);
    const routeList = STUDIO_TOOLS.flatMap((t) => t.routes.map((r) => r.href));
    expect(routeList).toEqual([
      "/kinematics",
      "/quarter-car",
      "/full-car",
      "/handling",
      "/correlation",
      "/compare",
      "/setup-sensitivity",
      "/optimize",
      "/engineering-memory",
      "/report",
    ]);
    expect(
      isToolGroupActive("/timeline", STUDIO_TOOLS[5].routes)
    ).toBe(true);
    expect(
      isToolGroupActive("/engineering-memory", STUDIO_TOOLS[5].routes)
    ).toBe(true);
  });

  it("renders only the 6 Studio tools in Navbar when NEXT_PUBLIC_STUDIO_MODE=true", () => {
    process.env.NEXT_PUBLIC_STUDIO_MODE = "true";
    const html = renderToStaticMarkup(React.createElement(Navbar));

    expect(html).toContain('data-studio-mode="true"');
    expect(html).toContain("3D Kinematics");
    expect(html).toContain("Hardpoints");
    expect(html).toContain("Quarter-Car");
    expect(html).toContain("Damper Studio");
    expect(html).toContain("Full-Car");
    expect(html).toContain("Handling");
    expect(html).toContain("Correlation");
    expect(html).toContain("Optimizer");
    expect(html).toContain("Engineering");
    expect(html).toContain("Reports");

    expect(html).toContain('href="/kinematics"');
    expect(html).toContain('href="/quarter-car"');
    expect(html).toContain('href="/full-car"');
    expect(html).toContain('href="/correlation"');
    expect(html).toContain('href="/setup-sensitivity"');
    expect(html).toContain('href="/engineering-memory"');

    // Legacy & non-studio nav links must be hidden, while /pricing remains visible as an upgrade CTA
    expect(html).not.toContain('href="/garage"');
    expect(html).not.toContain('href="/experiment"');
    expect(html).not.toContain('href="/docs"');
    expect(html).toContain('href="/pricing"');
    expect(html).toContain("bg-ansys-yellow");
    expect(html).not.toContain('id="analyze-solvers-dropdown-btn"');
    expect(html).not.toContain('id="validation-dropdown-btn"');
  });

  it("renders full 7-stage executive navigation in Navbar when Studio Mode is disabled", () => {
    delete process.env.NEXT_PUBLIC_STUDIO_MODE;
    const html = renderToStaticMarkup(React.createElement(Navbar));

    expect(html).not.toContain('data-studio-mode="true"');
    expect(html).toContain('href="/garage"');
    expect(html).toContain('href="/experiment"');
    expect(html).toContain('id="analyze-solvers-dropdown-btn"');
    expect(html).toContain('id="validation-dropdown-btn"');
    expect(html).toContain('href="/docs"');
    expect(html).toContain('href="/pricing"');
  });

  it("renders only the 6 Studio tools (all 10 routes) in MobileNav when NEXT_PUBLIC_STUDIO_MODE=true", () => {
    process.env.NEXT_PUBLIC_STUDIO_MODE = "true";
    const html = renderToStaticMarkup(
      React.createElement(MobileNav, { defaultOpen: true })
    );

    expect(html).toContain('data-studio-mode="true"');
    expect(html).toContain("3D Kinematics &amp; Hardpoints");
    expect(html).toContain("Quarter-Car &amp; Damper Studio");
    expect(html).toContain("Full-Car &amp; Handling");
    expect(html).toContain("Telemetry &amp; Setup Correlation");
    expect(html).toContain("Setup Sensitivity &amp; Optimizer");
    expect(html).toContain("Engineering Memory &amp; Reports");

    for (const href of [
      "/kinematics",
      "/quarter-car",
      "/full-car",
      "/handling",
      "/correlation",
      "/compare",
      "/setup-sensitivity",
      "/optimize",
      "/engineering-memory",
      "/report",
    ]) {
      expect(html).toContain(`href="${href}"`);
    }

    // Upgrade / Pricing CTA remains visible in Studio Mode
    expect(html).toContain('href="/pricing"');
    expect(html).toContain("Upgrade / Pricing");
    expect(html).toContain("bg-ansys-yellow");

    // Legacy drawer links must be omitted in Studio Mode
    expect(html).not.toContain('href="/garage"');
    expect(html).not.toContain('href="/cae"');
    expect(html).not.toContain('href="/nvh"');
    expect(html).not.toContain('href="/durability"');
    expect(html).not.toContain('href="/ai-engineer"');
  });

  it("renders full MobileNav sections when Studio Mode is disabled", () => {
    delete process.env.NEXT_PUBLIC_STUDIO_MODE;
    const html = renderToStaticMarkup(
      React.createElement(MobileNav, { defaultOpen: true })
    );

    expect(html).not.toContain('data-studio-mode="true"');
    expect(html).toContain('href="/garage"');
    expect(html).toContain('href="/cae"');
    expect(html).toContain('href="/half-car"');
    expect(html).toContain('href="/nvh"');
  });
});

describe("Sample Telemetry Renames, Badge & Legacy Route Cleanup", () => {
  it("renames public sample CSVs to sample_silverstone_gt3.csv and sample_spa_gt3.csv", () => {
    const samplesDir = path.join(FRONTEND_ROOT, "public", "samples");
    expect(fs.existsSync(path.join(samplesDir, "sample_silverstone_gt3.csv"))).toBe(true);
    expect(fs.existsSync(path.join(samplesDir, "sample_spa_gt3.csv"))).toBe(true);
    expect(fs.existsSync(path.join(samplesDir, "aim_silverstone_session.csv"))).toBe(false);
    expect(fs.existsSync(path.join(samplesDir, "motec_spa_session.csv"))).toBe(false);

    expect(SAMPLE_TELEMETRY_DATASETS.map((d) => d.filename)).toEqual([
      "sample_spa_gt3.csv",
      "sample_silverstone_gt3.csv",
    ]);
    expect(isSampleTelemetryFilename("sample_spa_gt3.csv")).toBe(true);
    expect(isSampleTelemetryFilename("sample_silverstone_gt3.csv")).toBe(true);
    expect(isSampleTelemetryFilename("real_car_run_01.csv")).toBe(false);
  });

  it("renders the [Sample Demo Telemetry] badge on SampleDemoTelemetryBadge and demo TelemetryChart", () => {
    const badgeHtml = renderToStaticMarkup(
      React.createElement(SampleDemoTelemetryBadge)
    );
    expect(badgeHtml).toContain("Sample Demo Telemetry");

    const demoChartHtml = renderToStaticMarkup(
      React.createElement(TelemetryChart, { title: "Demo Trace" })
    );
    expect(demoChartHtml).toContain("Sample Demo Telemetry");
    expect(demoChartHtml).not.toContain("MEASURED (MoTeC)");

    const realChartHtml = renderToStaticMarkup(
      React.createElement(TelemetryChart, {
        title: "Real Run",
        timestamps: [0, 0.1, 0.2],
        measured: [10, 12, 11],
        simulated: [10, 11.8, 11.2],
      })
    );
    expect(realChartHtml).not.toContain("Sample Demo Telemetry");
  });

  it("removes legacy alternative-to-msc-adams page, redirects it, and provides /engineering-memory", async () => {
    expect(
      fs.existsSync(path.join(FRONTEND_ROOT, "app", "alternative-to-msc-adams", "page.tsx"))
    ).toBe(false);
    expect(
      fs.existsSync(path.join(FRONTEND_ROOT, "app", "engineering-memory", "page.tsx"))
    ).toBe(true);

    const redirects = await nextConfig.redirects?.();
    expect(redirects).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          source: "/alternative-to-msc-adams",
          destination: "/",
        }),
      ])
    );
  });
});
