import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

(globalThis as any).React = React;

vi.mock("next/link", () => ({
  default: ({ href, children, prefetch: _prefetch, ...props }: any) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
}));

vi.mock("next/dynamic", () => ({
  default: () => () => null,
}));

vi.mock("../components/sim/Plot", () => ({
  default: () => null,
}));

const MOCK_WORKSPACE: any = {
  mode: "DEMO",
  setMode: vi.fn(),
  vehicle: { id: "v1", name: "Formula Student EV", version: "v1", mass_kg: 275, wheelbase_m: 1.53 },
  setup: { id: "s1", name: "Baseline", version: "REV-01", k_spring_front: 35000, k_spring_rear: 38000, c_damper_front: 1800, c_damper_rear: 1900 },
  track: { id: "t1", name: "Michigan Autocross", length_m: 1200, track_temp_c: 28, weather: "Dry" },
  tire: { id: "tr1", name: "Hoosier R25B", nominal_pressure_kpa: 82 },
  simulation: { activeRunId: "RUN-1", solverInfo: { solver: "RK45", build: "2.0" } },
  validation: { status: "VALIDATED", score: 94, correlation_pct: 94 },
  telemetry: { sessionId: "SESS-1" },
  sessionName: "FP1",
  modelVersion: "v2.0",
  activeVehicleContext: {
    vehicle: "Formula Student EV",
    setup: "Baseline",
    setupVersion: "REV-01",
    track: "Michigan Autocross",
    modelVersion: "v2.0",
    telemetrySession: "FP1",
  },
  resetToDefaults: vi.fn(),
};

vi.mock("../contexts/WorkspaceContext", () => ({
  useWorkspace: () => MOCK_WORKSPACE,
}));

import { AuthContext, usePlanGate, type AuthUser } from "../contexts/AuthContext";
import PlanGate from "../components/PlanGate";
import PDFExport from "../components/PDFExport";
import DataExport from "../components/DataExport";
import KinematicsExportModal from "../components/kinematics/KinematicsExportModal";
import KinematicsOptimizerPanel from "../components/kinematics/KinematicsOptimizerPanel";
import TeamSettings from "../components/TeamSettings";
import PricingPage from "../app/pricing/page";
import HomePage from "../app/page";
import FullCarPage from "../app/full-car/page";
import HandlingPage from "../app/handling/page";
import CorrelationPage from "../app/correlation/page";
import ComparePage from "../app/compare/page";
import SetupSensitivityPage from "../app/setup-sensitivity/page";
import OptimizePage from "../app/optimize/page";
import EngineeringMemoryPage from "../app/engineering-memory/page";
import { getUserPlanLevel, isTrialExpired } from "../lib/planGate";

const FRONTEND_ROOT = path.resolve(import.meta.dirname, "..");
const REPO_ROOT = path.resolve(FRONTEND_ROOT, "..");

function makeUser(overrides: Partial<AuthUser> = {}): AuthUser {
  return {
    user_id: "user-1",
    email: "eng@team.io",
    name: "Test Engineer",
    plan: "FREE",
    onboarding_complete: true,
    ...overrides,
  };
}

function renderWithAuth(user: AuthUser | null, node: React.ReactElement): string {
  const ctxValue: any = {
    user,
    token: user ? "tok" : null,
    loading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    authHeader: () => ({}),
    fetchWithAuth: vi.fn(),
    can: () => false,
    refreshSession: vi.fn(),
  };
  return renderToStaticMarkup(
    React.createElement(AuthContext.Provider, { value: ctxValue }, node)
  );
}

function HookProbe({ required }: { required: "FREE" | "PRO" | "ENTERPRISE" }) {
  const allowed = usePlanGate(required);
  return React.createElement("span", null, allowed ? "ALLOWED" : "BLOCKED");
}

describe("PlanGate & usePlanGate Expired Trial Enforcement", () => {
  const futureDate = new Date(Date.now() + 3 * 86400_000).toISOString();
  const pastDate = new Date(Date.now() - 3600_000).toISOString();

  it("allows active TRIAL users on PRO gates but blocks them on ENTERPRISE gates", () => {
    const activeTrial = makeUser({
      plan: "TRIAL",
      is_trial: true,
      trial_status: "ACTIVE",
      trial_expires_at: futureDate,
    });

    expect(isTrialExpired(activeTrial)).toBe(false);
    expect(getUserPlanLevel(activeTrial)).toBe(1);

    const proHtml = renderWithAuth(
      activeTrial,
      React.createElement(PlanGate, {
        required: "PRO",
        children: React.createElement("span", null, "PRO_SECRET"),
      })
    );
    expect(proHtml).toContain("PRO_SECRET");

    const entHtml = renderWithAuth(
      activeTrial,
      React.createElement(PlanGate, {
        required: "ENTERPRISE",
        children: React.createElement("span", null, "ENT_SECRET"),
      })
    );
    expect(entHtml).not.toContain("ENT_SECRET");
    expect(entHtml).toContain("ENTERPRISE REQUIRED");

    expect(renderWithAuth(activeTrial, React.createElement(HookProbe, { required: "PRO" }))).toContain("ALLOWED");
    expect(renderWithAuth(activeTrial, React.createElement(HookProbe, { required: "ENTERPRISE" }))).toContain("BLOCKED");
  });

  it("drops expired trials to FREE (0) when trial_status is EXPIRED", () => {
    const expiredByStatus = makeUser({
      plan: "TRIAL",
      is_trial: true,
      trial_status: "EXPIRED",
      trial_expires_at: futureDate,
    });

    expect(isTrialExpired(expiredByStatus)).toBe(true);
    expect(getUserPlanLevel(expiredByStatus)).toBe(0);

    const proHtml = renderWithAuth(
      expiredByStatus,
      React.createElement(PlanGate, {
        required: "PRO",
        children: React.createElement("span", null, "PRO_SECRET"),
      })
    );
    expect(proHtml).not.toContain("PRO_SECRET");
    expect(proHtml).toContain("PRO REQUIRED");

    expect(renderWithAuth(expiredByStatus, React.createElement(HookProbe, { required: "PRO" }))).toContain("BLOCKED");
    expect(renderWithAuth(expiredByStatus, React.createElement(HookProbe, { required: "FREE" }))).toContain("ALLOWED");
  });

  it("drops expired trials to FREE (0) when trial_expires_at is in the past", () => {
    const expiredByDate = makeUser({
      plan: "TRIAL",
      is_trial: true,
      trial_status: "ACTIVE",
      trial_expires_at: pastDate,
    });

    expect(isTrialExpired(expiredByDate)).toBe(true);
    expect(getUserPlanLevel(expiredByDate)).toBe(0);

    const proHtml = renderWithAuth(
      expiredByDate,
      React.createElement(PlanGate, {
        required: "PRO",
        overlay: true,
        children: React.createElement("span", null, "PRO_SECRET"),
      })
    );
    expect(proHtml).not.toContain("PRO_SECRET");
    expect(proHtml).toContain("Upgrade Plan");
    expect(renderWithAuth(expiredByDate, React.createElement(HookProbe, { required: "PRO" }))).toContain("BLOCKED");
  });

  it("enforces standard FREE, PRO, and ENTERPRISE hierarchy", () => {
    const freeUser = makeUser({ plan: "FREE", is_trial: false });
    const proUser = makeUser({ plan: "PRO", is_trial: false });
    const entUser = makeUser({ plan: "ENTERPRISE", is_trial: false });

    expect(renderWithAuth(freeUser, React.createElement(HookProbe, { required: "PRO" }))).toContain("BLOCKED");
    expect(renderWithAuth(proUser, React.createElement(HookProbe, { required: "PRO" }))).toContain("ALLOWED");
    expect(renderWithAuth(proUser, React.createElement(HookProbe, { required: "ENTERPRISE" }))).toContain("BLOCKED");
    expect(renderWithAuth(entUser, React.createElement(HookProbe, { required: "ENTERPRISE" }))).toContain("ALLOWED");
  });

  it("strictly gates testuser@ email addresses as FREE without hardcoded bypass", () => {
    const testUser = makeUser({ email: "testuser@suspensionlab.com", plan: "FREE" });
    expect(getUserPlanLevel(testUser)).toBe(0);
    expect(renderWithAuth(testUser, React.createElement(HookProbe, { required: "PRO" }))).toContain("BLOCKED");
    expect(renderWithAuth(testUser, React.createElement(HookProbe, { required: "FREE" }))).toContain("ALLOWED");

    const testUserPrefix = makeUser({ email: "testuser999@domain.org", plan: "FREE" });
    expect(getUserPlanLevel(testUserPrefix)).toBe(0);
    expect(renderWithAuth(testUserPrefix, React.createElement(HookProbe, { required: "PRO" }))).toContain("BLOCKED");
  });
});

describe("Free Hook + Pro/Enterprise Paywalls Across Studio Tools", () => {
  const freeUser = makeUser({ plan: "FREE" });
  const proUser = makeUser({ plan: "PRO" });
  const futureDate = new Date(Date.now() + 3 * 86400_000).toISOString();
  const activeTrial = makeUser({ plan: "TRIAL", is_trial: true, trial_status: "ACTIVE", trial_expires_at: futureDate });
  const entUser = makeUser({ plan: "ENTERPRISE" });

  it("gates PDFExport, DataExport, KinematicsExportModal, and KinematicsOptimizerPanel to PRO/TRIAL", () => {
    const pdfFree = renderWithAuth(freeUser, React.createElement(PDFExport));
    expect(pdfFree).not.toContain("Export 3-Page Vector PDF");
    expect(pdfFree).toContain('href="/pricing"');
    expect(renderWithAuth(activeTrial, React.createElement(PDFExport))).toContain("Export 3-Page Vector PDF");

    const dataFree = renderWithAuth(freeUser, React.createElement(DataExport, { results: { time: [0, 1] } }));
    expect(dataFree).not.toContain("Generating .m");
    expect(dataFree).toContain('href="/pricing"');
    expect(renderWithAuth(proUser, React.createElement(DataExport, { results: { time: [0, 1] } }))).toContain("Export MATLAB");

    const modalProps = {
      isOpen: true,
      onClose: () => {},
      hardpoints: { UWI_fwd: [0, 0, 0] },
      setupName: "Baseline",
      zMin: -25,
      zMax: 25,
      nSteps: 11,
    };
    const modalFree = renderWithAuth(freeUser, React.createElement(KinematicsExportModal, modalProps));
    expect(modalFree).toContain("PRO REQUIRED");
    expect(modalFree).not.toContain("Download CSV");
    const modalPro = renderWithAuth(proUser, React.createElement(KinematicsExportModal, modalProps));
    expect(modalPro).toContain("Download CSV");
    expect(modalPro).toContain("Download JSON");

    const optProps = {
      hardpoints: { UWI_fwd: [0, 0, 0] as [number, number, number] },
      onApplyCandidate: () => {},
    };
    expect(renderWithAuth(freeUser, React.createElement(KinematicsOptimizerPanel, optProps))).toContain("PRO REQUIRED");
    expect(renderWithAuth(proUser, React.createElement(KinematicsOptimizerPanel, optProps))).toContain("Run Multi-Objective Optimization");

    // Verify PDFExport unapproved draft banner never renders [ APPROVED ]
    const pdfSrc = fs.readFileSync(path.join(FRONTEND_ROOT, "components", "PDFExport.tsx"), "utf-8");
    expect(pdfSrc).not.toContain('pdf.text(`[ ${approval?.status || "UNAPPROVED"} ]`');
    expect(pdfSrc).toMatch(/rawStatus\.toUpperCase\(\)\s*!==\s*"APPROVED"\s*\?\s*rawStatus\s*:\s*"UNAPPROVED"/);
  });

  it("gates /full-car, /handling, /correlation, /compare, /setup-sensitivity, and /optimize to PRO", () => {
    const proPages = [
      FullCarPage,
      HandlingPage,
      CorrelationPage,
      ComparePage,
      SetupSensitivityPage,
      OptimizePage,
    ];
    for (const PageComp of proPages) {
      const htmlFree = renderWithAuth(freeUser, React.createElement(PageComp));
      expect(htmlFree).toContain("PRO REQUIRED");
      expect(htmlFree).toContain('href="/pricing"');
    }
  });

  it("gates /engineering-memory and TeamSettings to ENTERPRISE", () => {
    expect(renderWithAuth(proUser, React.createElement(EngineeringMemoryPage))).toContain("ENTERPRISE REQUIRED");
    expect(renderWithAuth(proUser, React.createElement(TeamSettings))).toContain("ENTERPRISE REQUIRED");
    expect(renderWithAuth(entUser, React.createElement(TeamSettings))).toContain("Loading team workspace");
  });
});

describe("PricingPage Gumroad Studio Tiers", () => {
  const origProUrl = process.env.NEXT_PUBLIC_GUMROAD_PRO_URL;
  const origTeamUrl = process.env.NEXT_PUBLIC_GUMROAD_TEAM_URL;

  beforeEach(() => {
    delete process.env.NEXT_PUBLIC_GUMROAD_PRO_URL;
    delete process.env.NEXT_PUBLIC_GUMROAD_TEAM_URL;
  });

  afterEach(() => {
    if (origProUrl === undefined) delete process.env.NEXT_PUBLIC_GUMROAD_PRO_URL;
    else process.env.NEXT_PUBLIC_GUMROAD_PRO_URL = origProUrl;

    if (origTeamUrl === undefined) delete process.env.NEXT_PUBLIC_GUMROAD_TEAM_URL;
    else process.env.NEXT_PUBLIC_GUMROAD_TEAM_URL = origTeamUrl;
  });

  it("renders updated tiers, prices, and footer text without Lemon Squeezy", () => {
    const html = renderWithAuth(null, React.createElement(PricingPage));

    expect(html).not.toContain("Lemon Squeezy");
    expect(html).toContain("Instant license key delivery via Gumroad or direct team invoicing.");
    expect(html).toContain("Starter");
    expect(html).toContain("3D Kinematics &amp; Quarter-Car Preview");
    expect(html).toContain("Pro Engineer");
    expect(html).toContain("$79");
    expect(html).toContain("Full-Car, Damper LUTs, Telemetry Correlation, Setup Optimizer &amp; PDF Reports");
    expect(html).toContain("Race Team &amp; Consultancy Pass");
    expect(html).toContain("$499");
    expect(html).toContain("Up to 10 Seats");
    expect(html).toContain('href="/settings#billing"');
    expect(html).not.toContain("Buy on Gumroad ($79)");
  });

  it("renders Gumroad checkout links in new tab when NEXT_PUBLIC_GUMROAD_* env vars are set", () => {
    process.env.NEXT_PUBLIC_GUMROAD_PRO_URL = "https://gumroad.com/l/suspensionlab-pro";
    process.env.NEXT_PUBLIC_GUMROAD_TEAM_URL = "https://gumroad.com/l/suspensionlab-team";

    const html = renderWithAuth(makeUser({ plan: "FREE" }), React.createElement(PricingPage));

    expect(html).toContain("Buy on Gumroad ($79)");
    expect(html).toContain('href="https://gumroad.com/l/suspensionlab-pro"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain("Activate License Key →");
    expect(html).toContain('href="/settings#billing"');
    expect(html).toContain('href="https://gumroad.com/l/suspensionlab-team"');
  });
});

describe("Landing Page, Offline Fonts, Settings #billing & Env Files", () => {
  it("renders SuspensionLab Studio landing page with hero CTAs, 6 Studio tools, and pricing preview", () => {
    const html = renderWithAuth(null, React.createElement(HomePage));
    expect(html).toContain("Launch ApexSim Lap Studio");
    expect(html).toContain('href="/lap-sim"');
    expect(html).toContain("Open Free 3D Kinematics Sandbox");
    expect(html).toContain('href="/kinematics"');
    expect(html).toContain("View Pro &amp; Team Passes ($79/mo)");
    expect(html).toContain('href="/pricing"');
    expect(html).toContain("3D Kinematics &amp; Hardpoints");
    expect(html).toContain("Quarter-Car &amp; Damper Studio");
    expect(html).toContain("Full-Car &amp; Handling");
    expect(html).toContain("Telemetry &amp; Setup Correlation");
    expect(html).toContain("Setup Sensitivity &amp; Optimizer");
    expect(html).toContain("Engineering Memory &amp; Reports");
    expect(html).toContain("$0");
    expect(html).toContain("$79/mo");
    expect(html).toContain("$499/yr");
    expect(html).not.toContain("Engineering Command Center");
  });

  it("uses local/system CSS fonts in layout.tsx and globals.css instead of next/font/google", () => {
    const layoutSrc = fs.readFileSync(path.join(FRONTEND_ROOT, "app", "layout.tsx"), "utf-8");
    const globalsSrc = fs.readFileSync(path.join(FRONTEND_ROOT, "app", "globals.css"), "utf-8");
    expect(layoutSrc).not.toContain("next/font/google");
    expect(globalsSrc).toContain("--font-inter");
    expect(globalsSrc).toContain("--font-jetbrains-mono");
    expect(globalsSrc).toContain("JetBrains Mono");
  });

  it("places Gumroad CTA above license key input in settings/page.tsx", () => {
    const settingsSrc = fs.readFileSync(
      path.join(FRONTEND_ROOT, "app", "settings", "page.tsx"),
      "utf-8"
    );
    const ctaIdx = settingsSrc.indexOf("Don’t have a license key yet? Get Pro on Gumroad →");
    const inputIdx = settingsSrc.indexOf("value={gumroadKey}");
    expect(ctaIdx).toBeGreaterThan(-1);
    expect(inputIdx).toBeGreaterThan(ctaIdx);
    expect(settingsSrc).toContain("NEXT_PUBLIC_GUMROAD_PRO_URL");
  });

  it("includes Gumroad URLs and permalink in frontend/.env.local, .env.example, and .env.railway.example", () => {
    const envFiles = [
      path.join(FRONTEND_ROOT, ".env.local"),
      path.join(REPO_ROOT, ".env.example"),
      path.join(REPO_ROOT, ".env.railway.example"),
    ];
    for (const file of envFiles) {
      const text = fs.readFileSync(file, "utf-8");
      expect(text).toContain("NEXT_PUBLIC_GUMROAD_PRO_URL=");
      expect(text).toContain("NEXT_PUBLIC_GUMROAD_TEAM_URL=");
      expect(text).toContain("GUMROAD_PRODUCT_PERMALINK=suspensionlab-pro");
    }
  });
});
