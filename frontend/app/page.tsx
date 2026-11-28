"use client";

import React from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useAuth } from "../contexts/AuthContext";
import { NAV_V2 } from "../lib/navigation";
import CommandCenterWorkspace from "../components/CommandCenterWorkspace";
import BenchmarkWall from "../components/v2/BenchmarkWall";
import StatusPill from "../components/v2/StatusPill";

const LandingHero3D = dynamic(() => import("../components/v2/LandingHero3D"), {
  ssr: false,
  loading: () => <div className="h-[360px] border border-hairline bg-panel" />,
});

// Claims ledger. Every row names its evidence.
// No benchmark in this repository compares against measured vehicle data.
const CLAIMS: { claim: string; status: string; evidence: string }[] = [
  { claim: "Quarter-car modal frequencies match the exact coupled 2-DOF roots (< 0.5%)", status: "VERIFIED", evidence: "Benchmark B-01" },
  { claim: "Damper cycle energy: linear c_eff = c, bilinear (c_c + c_r)/2", status: "VERIFIED", evidence: "Benchmark B-02" },
  { claim: "Standard .tir files (PKY1 = -15) give positive cornering stiffness", status: "VERIFIED", evidence: "Benchmark B-03" },
  { claim: "Full-car heave mode matches the hand calculation on a symmetric car", status: "VERIFIED", evidence: "Benchmark B-04" },
  { claim: "Tire model fit against Calspan TTC data", status: "NOT_RUN", evidence: "In progress, needs a licensed dataset" },
  { claim: "Validated against measured vehicle data", status: "NOT_RUN", evidence: "No such comparison exists yet" },
  { claim: "Elastokinematic toe compliance", status: "OUT_OF_DOMAIN", evidence: "Not modeled (rigid links and joints)" },
];

const PRICING = [
  {
    name: "Free",
    price: "$0",
    cadence: "free account required",
    desc: "3D Kinematics and Quarter-Car preview. You sign in first: the studios and the solvers need an account.",
    cta: "Create a free account",
    href: "/auth/register",
    primary: false,
  },
  {
    name: "Pro",
    price: "$79/mo",
    cadence: "license key",
    desc: "Full-Car, damper LUTs, telemetry correlation, setup optimizer and PDF reports.",
    cta: "View Pro & Team Passes ($79/mo)",
    href: "/pricing",
    primary: true,
  },
  {
    name: "Team",
    price: "$499/yr",
    cadence: "up to 10 seats",
    desc: "Everything in Pro, plus engineering memory, shared reports and FMI co-sim exports.",
    cta: "See Team details",
    href: "/pricing",
    primary: false,
  },
];

export default function HomePage() {
  const { user } = useAuth();

  return (
    <div className="min-h-full w-full bg-carbon text-white selection:bg-signal selection:text-carbon">
      {/* 1. Hero */}
      <section className="border-b border-hairline px-4 pb-16 pt-14 sm:px-6">
        <div className="mx-auto grid max-w-[1280px] grid-cols-1 gap-10 lg:grid-cols-12">
          <div className="space-y-6 lg:col-span-7">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-signal">SuspensionLab Studio</p>
            <h1 className="font-[var(--font-display)] text-3xl font-bold leading-[1.1] tracking-tight sm:text-4xl lg:text-5xl">
              Suspension kinematics, ride and handling solvers, and a lap simulator in your browser.
            </h1>
            <p className="max-w-2xl text-base leading-relaxed text-gray-400">
              Design double-wishbone geometry from hardpoints, solve ride and handling models, and run closed-loop lap
              simulations. Every result carries its solver build, run ID and input hash.
            </p>
            <div className="flex flex-wrap items-center gap-3 pt-1">
              <Link href="/lap-sim" className="rounded border border-signal bg-signal px-5 py-3 text-sm font-bold text-carbon transition-colors hover:bg-[#d6f56e]">
                Launch ApexSim Lap Studio -&gt;
              </Link>
              <Link href="/kinematics" className="rounded border border-hairline bg-panel px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-white/[0.06]">
                Open Kinematics Sandbox -&gt;
              </Link>
              <Link href="/pricing" className="px-2 py-3 text-xs text-gray-400 transition-colors hover:text-signal">
                View Pro &amp; Team Passes ($79/mo)
              </Link>
            </div>
            {!user && (
              <p data-testid="free-tier-auth-note" className="text-xs text-gray-400">
                The Free plan costs nothing, but you need an account: solving requires sign-in, and signed-out requests are
                rejected with 401 auth_required.
              </p>
            )}
            {user && (
              <a href="#command-center" className="inline-block text-xs text-gray-300 hover:text-signal">
                Jump to Engineering Command Center
              </a>
            )}
          </div>

          {/* Interactive 3D double-wishbone schematic on desktop; flat proof card below lg */}
          <aside aria-label="What runs today" className="lg:col-span-5">
            <div className="hidden lg:block">
              <LandingHero3D />
              <details className="mt-3 rounded border border-hairline bg-panel px-4 py-3 text-xs">
                <summary className="cursor-pointer font-semibold uppercase tracking-[0.14em] text-gray-300 hover:text-signal">
                  What runs today — solver capabilities
                </summary>
                <ul className="mt-3 space-y-2.5 text-xs">
                  {[
                    ["3D double-wishbone kinematics", "Camber gain, bump steer, roll center from hardpoints"],
                    ["Quarter-car, half-car and 7-DOF full-car", "Modal frequencies, Bode plots, ISO 2631 comfort"],
                    ["ApexSim lap studio", "Closed-loop multi-pass solver with bottoming detection"],
                    ["Telemetry correlation and investigation", "Measured data against simulation, stage by stage"],
                  ].map(([t, d]) => (
                    <li key={t} className="border-t border-hairline pt-2 first:border-t-0 first:pt-0">
                      <p className="font-semibold text-white">{t}</p>
                      <p className="text-gray-400">{d}</p>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-[11px] text-gray-500">Live checks are on the Benchmark Wall below.</p>
              </details>
            </div>

            <div className="lg:hidden rounded border border-hairline bg-panel p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">What runs today</p>
              <ul className="mt-3 space-y-3 text-sm">
                {[
                  ["3D double-wishbone kinematics", "Camber gain, bump steer, roll center from hardpoints"],
                  ["Quarter-car, half-car and 7-DOF full-car", "Modal frequencies, Bode plots, ISO 2631 comfort"],
                  ["ApexSim lap studio", "Closed-loop multi-pass solver with bottoming detection"],
                  ["Telemetry correlation and investigation", "Measured data against simulation, stage by stage"],
                ].map(([t, d]) => (
                  <li key={t} className="border-t border-hairline pt-3 first:border-t-0 first:pt-0">
                    <p className="font-semibold text-white">{t}</p>
                    <p className="text-xs text-gray-400">{d}</p>
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-[11px] text-gray-500">Live checks are on the Benchmark Wall below.</p>
            </div>
          </aside>
        </div>
      </section>

      {/* 2. Live Benchmark Wall (reads /benchmark-status.json) */}
      <BenchmarkWall />

      {/* 3. Claims ledger */}
      <section aria-labelledby="claims-title" className="border-b border-hairline px-4 py-14 sm:px-6">
        <div className="mx-auto max-w-[1280px] space-y-5">
          <h2 id="claims-title" className="font-[var(--font-display)] text-2xl font-bold">Claims ledger</h2>
          <p className="max-w-3xl text-sm text-gray-400">
            What we claim, what we check it against, and what is still open. We make no on-track or
            real-vehicle validation claims.
          </p>
          <div className="overflow-x-auto rounded border border-hairline bg-panel">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-hairline text-[11px] text-gray-400">
                  <th className="p-3">Claim</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {CLAIMS.map((c) => (
                  <tr key={c.claim} className="border-b border-hairline last:border-b-0 text-gray-300">
                    <td className="p-3">{c.claim}</td>
                    <td className="p-3"><StatusPill status={c.status} /></td>
                    <td className="p-3 text-gray-400">{c.evidence}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* 4. Workspace map (same groups as the navigation) */}
      <section aria-labelledby="studios-title" className="border-b border-hairline px-4 py-14 sm:px-6">
        <div className="mx-auto max-w-[1280px] space-y-5">
          <h2 id="studios-title" className="font-[var(--font-display)] text-2xl font-bold">Workspace</h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {NAV_V2.filter((g) => g.id !== "overview").map((g) => (
              <div key={g.id} className="rounded border border-hairline bg-panel p-4">
                <h3 className="text-sm font-semibold text-white">{g.label}</h3>
                <ul className="mt-2 space-y-1 text-xs">
                  {g.routes.map((r) => (
                    <li key={r.href}>
                      <Link href={r.href} className="text-gray-300 hover:text-signal">{r.label}</Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 5. Open pricing */}
      <section aria-labelledby="pricing-title" className="px-4 py-14 sm:px-6">
        <div className="mx-auto max-w-[1280px] space-y-5">
          <h2 id="pricing-title" className="font-[var(--font-display)] text-2xl font-bold">Pricing</h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {PRICING.map((t) => (
              <div key={t.name} className={`flex flex-col justify-between rounded border bg-panel p-5 ${t.primary ? "border-signal" : "border-hairline"}`}>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-gray-400">{t.name}</p>
                  <p className="mt-2 flex items-baseline gap-2">
                    <span className="text-3xl font-bold text-white v2-num">{t.price}</span>
                    <span className="text-xs text-gray-500">{t.cadence}</span>
                  </p>
                  <p className="mt-3 text-sm text-gray-400">{t.desc}</p>
                </div>
                <Link
                  href={t.href}
                  className={`mt-6 rounded border px-4 py-2.5 text-center text-sm font-bold transition-colors ${
                    t.primary ? "border-signal bg-signal text-carbon hover:bg-[#d6f56e]" : "border-hairline text-white hover:bg-white/[0.06]"
                  }`}
                >
                  {t.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {user && (
        <section id="command-center" aria-label="Engineering Command Center">
          <CommandCenterWorkspace />
        </section>
      )}
    </div>
  );
}
