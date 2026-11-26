import { describe, it, expect } from "vitest";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";
import StatusPill from "../components/v2/StatusPill";
import EmptyState, { valueOrEmpty } from "../components/v2/EmptyState";
import ErrorCard from "../components/v2/ErrorCard";
import RunBadge from "../components/v2/RunBadge";
import { BACKEND_STATUS_MAP, V2_STATES, mapBackendStatusToV2, mapResultToV2 } from "../lib/v2/status";
import { formatApiError } from "../lib/api_client";

(globalThis as any).React = React;
const root = path.resolve(import.meta.dirname, "..");
const read = (p: string) => fs.readFileSync(path.join(root, p), "utf8");

describe("V2 tokens", () => {
  it("defines the exact palette in globals.css", () => {
    const css = read("app/globals.css").toLowerCase();
    for (const [n, hex] of Object.entries({
      carbon: "#0c0f12", panel: "#13181d", signal: "#c8f04b", verified: "#4ad991",
      warning: "#ffb84d", fault: "#ff5c5c", measured: "#57c8dc",
    })) expect(css, n).toContain(`--color-${n}: ${hex};`);
  });
  it("V2 components and landing use no gradients, glass or glow", () => {
    const files = ["components/v2/StatusPill.tsx", "components/v2/EmptyState.tsx", "components/v2/ErrorCard.tsx",
      "components/v2/RunBadge.tsx", "components/v2/BenchmarkWall.tsx", "app/page.tsx"];
    for (const f of files) {
      expect(read(f), f).not.toMatch(/gradient|backdrop-blur|shadow-\[|blur-/);
    }
  });
});

describe("mapBackendStatusToV2", () => {
  it("maps the Wave 5A-2/5B statuses without contradiction", () => {
    expect(mapBackendStatusToV2("NOT_EVALUATED")).toBe("NOT_RUN");
    expect(mapBackendStatusToV2("UNVERIFIED")).toBe("NOT_RUN");
    expect(mapBackendStatusToV2("PASS")).toBe("VERIFIED");
    expect(mapBackendStatusToV2("WARN")).toBe("WARNING");
    expect(mapBackendStatusToV2("FAIL")).toBe("FAILED");
    expect(mapBackendStatusToV2("NOT_MODELED")).toBe("OUT_OF_DOMAIN");
    expect(mapBackendStatusToV2("NOT_MODELED_RIGID_SPHERICAL_JOINTS")).toBe("OUT_OF_DOMAIN");
    expect(mapBackendStatusToV2("RUNNING")).toBe("RUNNING");
  });
  it("is case and separator tolerant", () => {
    expect(mapBackendStatusToV2("pass")).toBe("VERIFIED");
    expect(mapBackendStatusToV2("not evaluated")).toBe("NOT_RUN");
    expect(mapBackendStatusToV2("terminated")).toBe("FAILED");
  });
  it("never upgrades unknown or empty input to VERIFIED", () => {
    for (const v of ["SOMETHING_NEW", "", "   ", null, undefined, 42, {}]) {
      expect(mapBackendStatusToV2(v as unknown)).toBe("NOT_RUN");
    }
  });
  it("every map value is one of the six states and each key appears once in the source", () => {
    for (const v of Object.values(BACKEND_STATUS_MAP)) expect(V2_STATES).toContain(v);
    const src = read("lib/v2/status.ts");
    const body = src.slice(src.indexOf("BACKEND_STATUS_MAP"), src.indexOf("export function mapBackendStatusToV2"));
    const keys = [...body.matchAll(/\b([A-Z][A-Z0-9_]+):\s*"/g)].map((m) => m[1]);
    expect(new Set(keys).size).toBe(keys.length);
  });
  it("incomplete lap is FAILED even with a stale converged flag", () => {
    expect(mapResultToV2({ lap_completed: false, solver_converged: true, status: "terminated" })).toBe("FAILED");
    expect(mapResultToV2({ lap_completed: true, status: "PASS" })).toBe("VERIFIED");
    expect(mapResultToV2(null)).toBe("NOT_RUN");
  });
});

describe("v2 primitives", () => {
  it("StatusPill renders the mapped state and label", () => {
    const html = renderToStaticMarkup(React.createElement(StatusPill, { status: "WARN" }));
    expect(html).toContain('data-status="WARNING"');
    expect(html).toContain("Warning");
    const nr = renderToStaticMarkup(React.createElement(StatusPill, { status: "UNVERIFIED" }));
    expect(nr).toContain('data-status="NOT_RUN"');
    expect(nr).toContain("Backend status: UNVERIFIED");
  });
  it("EmptyState says Not available / Not run and never prints 0.00 or +0.0%", () => {
    expect(renderToStaticMarkup(React.createElement(EmptyState))).toContain("Not available");
    expect(renderToStaticMarkup(React.createElement(EmptyState, { kind: "not_run" }))).toContain("Not run");
    const out = renderToStaticMarkup(React.createElement("span", null, valueOrEmpty(null, (n) => n.toFixed(2))));
    expect(out).toContain("Not available");
    expect(out).not.toContain("0.00");
    expect(renderToStaticMarkup(React.createElement("span", null, valueOrEmpty(Number.NaN, (n) => `${n}%`)))).not.toContain("NaN");
    expect(renderToStaticMarkup(React.createElement("span", null, valueOrEmpty(1.5, (n) => n.toFixed(2))))).toContain("1.50");
  });
  it("ErrorCard shows the formatApiError text, never [object Object]", () => {
    const err = { detail: { code: "FULL_CAR_DIVERGED", message: "Full-car solver diverged" } };
    const html = renderToStaticMarkup(React.createElement(ErrorCard, { error: err, context: "Run" }));
    expect(html).toContain(formatApiError(err, "Run").replace(/&/g, "&amp;"));
    expect(html).not.toContain("[object Object]");
    expect(read("components/v2/ErrorCard.tsx")).toContain("formatApiError");
  });
  it("ErrorCard raw trace toggle is development-only", () => {
    expect(read("components/v2/ErrorCard.tsx")).toContain('process.env.NODE_ENV !== "production"');
  });
  it("RunBadge shows build and run id, puts full hashes in the hover title, and hides when empty", () => {
    const sha = "a".repeat(64);
    const html = renderToStaticMarkup(React.createElement(RunBadge, { solverVersion: "2.1.0+abc1234", runId: "swp-123", inputSha256: sha, outputSha256: "b".repeat(64) }));
    expect(html).toContain("2.1.0+abc1234");
    expect(html).toContain(`Input SHA-256: ${sha}`);
    expect(html).toContain("Output SHA-256: " + "b".repeat(64));
    expect(renderToStaticMarkup(React.createElement(RunBadge, {}))).toBe("");
  });
});

describe("benchmark-status.json", () => {
  const status = JSON.parse(read("public/benchmark-status.json"));
  it("has B-01..B-04 with verdicts, measured values, tolerances, sha and timestamp", () => {
    expect(status.benchmarks.map((b: { id: string }) => b.id)).toEqual(["B-01", "B-02", "B-03", "B-04"]);
    expect(status.git_sha).toMatch(/^[0-9a-f]{40}$|^unknown$/);
    expect(Number.isNaN(Date.parse(status.generated_at))).toBe(false);
    for (const b of status.benchmarks) {
      expect(["PASS", "FAIL"]).toContain(b.verdict);
      expect(b.checks.length).toBeGreaterThan(0);
      for (const c of b.checks) {
        expect(Object.keys(c.measured).length).toBeGreaterThan(0);
        expect(Object.keys(c.tolerance).length).toBeGreaterThan(0);
      }
    }
  });
  it("B-01 documents the uncoupled value as an approximation, B-03 Calspan as pending", () => {
    const b01 = status.benchmarks[0].checks[0];
    expect(b01.measured.uncoupled_sqrt_kw_over_ms_hz).toBeCloseTo(1.235, 2);
    expect(b01.reference).toMatch(/approximation/i);
    expect(b01.reference).not.toMatch(/exact closed-form 2-DOF/i);
    expect(status.benchmarks[2].pending.calspan_ttc_fit).toBe("IN_PROGRESS");
  });
  it("makes no real-vehicle validation claim", () => {
    expect(status.scope_note).toMatch(/not a validation against measured/i);
  });
});

describe("Landing V2 truthfulness", () => {
  const page = read("app/page.tsx");
  it("reads the live status file and has no Twin Replay button", () => {
    expect(read("components/v2/BenchmarkWall.tsx")).toContain("/benchmark-status.json");
    expect(page).toContain("BenchmarkWall");
    expect(page).not.toMatch(/twin\s*replay/i);
  });
  it("free-tier copy matches auth behaviour (account required, 401 auth_required)", () => {
    expect(page).toMatch(/you need an account/i);
    expect(page).toContain("401 auth_required");
    expect(page).not.toMatch(/no sign-?up|without signing in|no account/i);
  });
  it("shows open pricing Free / Pro $79/mo / Team $499/yr", () => {
    expect(page).toContain('price: "$0"');
    expect(page).toContain('price: "$79/mo"');
    expect(page).toContain('price: "$499/yr"');
  });
  it("pricing page states the free plan needs an account and reads Gumroad links from env", () => {
    const pricing = read("app/pricing/page.tsx");
    expect(pricing).toMatch(/Free account required/);
    expect(pricing).toContain("NEXT_PUBLIC_GUMROAD_PRO_URL");
    expect(pricing).not.toMatch(/gumroad\.com\/l\//); // no hard-coded checkout link
  });
});
