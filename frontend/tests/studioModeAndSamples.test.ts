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
  NAV_V2,
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

  const V2_GROUP_LABELS = ["Overview", "Studios", "ApexSim", "Telemetry", "Optimize", "Reports", "AI Engineer"];
  const groupOf = (href: string) => NAV_V2.find((g) => g.routes.some((r) => r.href === href))?.label;

  it("defines the 7 V2 workspace groups and keeps every Wave 5 route reachable", () => {
    expect(NAV_V2.map((g) => g.label)).toEqual(V2_GROUP_LABELS);
    const routeList = NAV_V2.flatMap((g) => g.routes.map((r) => r.href));
    expect(new Set(routeList).size).toBe(routeList.length); // no duplicate entries
    for (const href of [
      "/kinematics", "/quarter-car", "/half-car", "/full-car", "/handling", "/yaw-dynamics", "/active",
      "/nvh", "/lap-sim", "/correlation", "/investigate", "/digital-twin", "/experiment", "/optimize",
      "/compare", "/setup-sensitivity", "/report", "/cae", "/engineering-memory", "/vnv", "/audit",
      "/ai-engineer", "/garage", "/docs", "/pricing",
    ]) {
      expect(routeList, href).toContain(href);
    }
    for (const href of routeList) {
      expect(fs.existsSync(path.join(FRONTEND_ROOT, "app", href, "page.tsx")), href).toBe(true);
    }
  });

  it("keeps Investigation Room under Telemetry and CAE Interop under Reports", () => {
    expect(groupOf("/investigate")).toBe("Telemetry");
    expect(groupOf("/cae")).toBe("Reports");
    const reports = NAV_V2.find((g) => g.label === "Reports")!;
    expect(isToolGroupActive("/timeline", reports.routes)).toBe(true);
    expect(isToolGroupActive("/engineering-memory", reports.routes)).toBe(true);
  });

  it("renders the V2 groups in Navbar in both modes, with overflow-visible dropdowns", () => {
    for (const mode of [undefined, "true"]) {
      if (mode === undefined) delete process.env.NEXT_PUBLIC_STUDIO_MODE;
      else process.env.NEXT_PUBLIC_STUDIO_MODE = mode;
      const html = renderToStaticMarkup(React.createElement(Navbar));
      expect(html).toContain('data-nav-version="v2"');
      expect(html).toContain("overflow-visible");
      for (const label of V2_GROUP_LABELS) expect(html).toContain(label);
      for (const href of ["/garage", "/kinematics", "/lap-sim", "/correlation", "/optimize", "/report", "/ai-engineer", "/pricing"]) {
        expect(html).toContain(`href="${href}"`);
      }
      expect(html).not.toContain('id="analyze-solvers-dropdown-btn"');
      expect(html).not.toContain('id="validation-dropdown-btn"');
    }
  });

  it("keeps the search trigger and the mobile drawer mounted in the Navbar", () => {
    const src = fs.readFileSync(path.join(FRONTEND_ROOT, "components", "Navbar.tsx"), "utf-8");
    expect(src).toContain("<GlobalSearchTrigger />");
    expect(src).toContain("<MobileNav />");
  });

  it("renders every V2 route in MobileNav", () => {
    const html = renderToStaticMarkup(React.createElement(MobileNav, { defaultOpen: true }));
    for (const g of NAV_V2) for (const r of g.routes) expect(html, r.href).toContain(`href="${r.href}"`);
    expect(html).toContain("Upgrade / Pricing");
    expect(html).toContain('href="/investigate"');
    expect(html).toContain('href="/cae"');
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

describe("NAV_V2 route integrity (data, not markup)", () => {
  const all = NAV_V2.flatMap((g) => g.routes.map((r) => ({ group: g.id, ...r })));
  it("every group and route has a non-empty label and an absolute href", () => {
    for (const g of NAV_V2) {
      expect(g.label.trim().length, g.id).toBeGreaterThan(0);
      expect(g.href.startsWith("/"), g.id).toBe(true);
    }
    for (const r of all) {
      expect(r.label.trim().length, r.href).toBeGreaterThan(0);
      expect(r.href.startsWith("/"), r.label).toBe(true);
    }
  });
  it("has no duplicate route hrefs and no duplicate group ids", () => {
    const hrefs = all.map((r) => r.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    const ids = NAV_V2.map((g) => g.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
  it("/investigate sits under Telemetry and /cae under Reports, with real page files", () => {
    const inv = all.find((r) => r.href === "/investigate");
    const cae = all.find((r) => r.href === "/cae");
    expect(inv?.group).toBe("telemetry");
    expect(cae?.group).toBe("reports");
    for (const r of all) {
      if (r.href === "/") continue;
      const page = path.join(FRONTEND_ROOT, "app", ...r.href.split("/").filter(Boolean), "page.tsx");
      expect(fs.existsSync(page), `${r.href} has no app page`).toBe(true);
    }
  });
});
