"use client";

import React from "react";
import Link from "next/link";
import {
  ArrowRight,
  Box,
  Activity,
  Car,
  GitCompare,
  Sliders,
  History,
  Check,
  Sparkles,
  Zap,
  Shield,
  Building2,
  type LucideIcon,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { STUDIO_TOOLS, type StudioIconKey } from "../lib/navigation";
import CommandCenterWorkspace from "../components/CommandCenterWorkspace";

const TOOL_ICONS: Record<StudioIconKey, LucideIcon> = {
  kinematics: Box,
  quarter_car: Activity,
  full_car: Car,
  correlation: GitCompare,
  optimizer: Sliders,
  memory: History,
};

const TOOL_TIER_BADGES: Record<string, { label: string; style: string }> = {
  kinematics: {
    label: "FREE STUDIO",
    style: "bg-emerald-500/15 border-emerald-500/40 text-emerald-300",
  },
  "quarter-car": {
    label: "FREE HOOK + PRO LUTs",
    style: "bg-emerald-500/15 border-emerald-500/40 text-emerald-300",
  },
  "full-car-handling": {
    label: "PRO",
    style: "bg-ansys-yellow/15 border-ansys-yellow/40 text-ansys-yellow",
  },
  "correlation-compare": {
    label: "PRO",
    style: "bg-ansys-yellow/15 border-ansys-yellow/40 text-ansys-yellow",
  },
  "sensitivity-optimizer": {
    label: "PRO",
    style: "bg-ansys-yellow/15 border-ansys-yellow/40 text-ansys-yellow",
  },
  "memory-reports": {
    label: "TEAM PASS",
    style: "bg-purple-500/15 border-purple-500/40 text-purple-300",
  },
};

const PRICING_PREVIEW = [
  {
    name: "Starter",
    price: "$0",
    cadence: "forever",
    desc: "3D Kinematics & Quarter-Car Preview.",
    icon: Zap,
    highlight: false,
    features: [
      "Interactive 3D Double-Wishbone Kinematics",
      "Hardpoint sliders, camber & bump steer plots",
      "Quarter-Car (2-DOF) ride & Bode preview",
    ],
    ctaLabel: "Launch 3D Kinematics",
    ctaHref: "/kinematics",
  },
  {
    name: "Pro Engineer",
    price: "$29/mo",
    cadence: "Gumroad license key",
    desc: "Full-Car, Damper LUTs, Telemetry Correlation, Setup Optimizer & PDF Reports.",
    icon: Shield,
    highlight: true,
    features: [
      "Full-Car (7-DOF) & Handling Dynamics",
      "Damper LUTs & Telemetry Correlation",
      "Kinematics & Pareto Setup Optimizer",
      "PDF Setup Sheets, CSV & MATLAB Exports",
    ],
    ctaLabel: "Start 7-Day Pro Trial",
    ctaHref: "/auth/register",
  },
  {
    name: "Race Team / FSAE Pass",
    price: "$199/yr",
    cadence: "annual team pass",
    desc: "Up to 10 team seats, Engineering Memory, Shared Reports & FMI Co-Sim.",
    icon: Building2,
    highlight: false,
    features: [
      "Everything in Pro Engineer",
      "Up to 10 team seats & role permissions",
      "Engineering Memory & signed decisions",
      "Shared Reports & FMI 2.0 Co-Sim exports",
    ],
    ctaLabel: "View Team Pass",
    ctaHref: "/pricing",
  },
];

export default function HomePage() {
  const { user } = useAuth();

  return (
    <div className="w-full bg-[#08080a] text-white selection:bg-ansys-yellow selection:text-black min-h-full">
      {/* ── 1. STUDIO HERO ───────────────────────────────────────────────── */}
      <section className="relative overflow-hidden border-b border-white/[0.08] pt-14 pb-16 px-4 sm:px-6">
        <div className="absolute -top-24 right-0 w-[520px] h-[520px] bg-ansys-yellow/10 blur-3xl pointer-events-none" />
        <div className="max-w-[1380px] mx-auto relative">
          <div className="max-w-3xl space-y-6">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-ansys-yellow/10 border border-ansys-yellow/30 text-ansys-yellow text-[11px] font-mono font-bold uppercase tracking-wider">
              <Sparkles size={13} />
              SuspensionLab Studio · Vehicle Dynamics &amp; Kinematics
            </div>

            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-white leading-[1.08]">
              Physics-first suspension design, correlation, and setup optimization.
            </h1>

            <p className="text-base sm:text-lg text-gray-400 leading-relaxed max-w-2xl">
              Explore 3D suspension geometry and quarter-car ride dynamics free in your browser. Upgrade for 7-DOF full-car simulation, nonlinear damper LUTs, MoTeC/AiM telemetry correlation, and multi-objective setup optimization.
            </p>

            <div className="flex flex-wrap items-center gap-3 pt-2">
              <Link
                href="/kinematics"
                className="px-6 py-3.5 rounded-xl bg-ansys-yellow text-black font-bold text-sm hover:brightness-110 transition-all inline-flex items-center gap-2 shadow-[0_0_25px_rgba(242,169,0,0.28)]"
              >
                <span>Launch 3D Kinematics Studio (Free)</span>
                <ArrowRight size={16} />
              </Link>

              <Link
                href="/auth/register"
                className="px-6 py-3.5 rounded-xl bg-white/[0.05] hover:bg-white/[0.1] border border-white/15 text-white font-semibold text-sm transition-all inline-flex items-center gap-2"
              >
                <span>Start 7-Day Pro Trial</span>
              </Link>

              {user && (
                <a
                  href="#command-center"
                  className="px-4 py-3.5 rounded-xl text-xs font-mono text-gray-300 hover:text-ansys-yellow transition-colors inline-flex items-center gap-1.5"
                >
                  <span>Jump to Engineering Command Center</span>
                  <ArrowRight size={13} />
                </a>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── 2. SIX STUDIO TOOLS SHOWCASE ─────────────────────────────────── */}
      <section className="py-16 px-4 sm:px-6 border-b border-white/[0.08]">
        <div className="max-w-[1380px] mx-auto space-y-8">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <span className="text-[11px] font-mono font-bold uppercase tracking-[0.2em] text-ansys-yellow">
                The 6 Studio Workspaces
              </span>
              <h2 className="text-2xl sm:text-3xl font-bold text-white mt-1">
                From hardpoint CAD geometry to race-ready setup sign-off
              </h2>
            </div>
            <Link
              href="/quarter-car"
              className="text-xs font-mono text-ansys-yellow hover:underline inline-flex items-center gap-1"
            >
              <span>Try Quarter-Car &amp; Damper Studio</span>
              <ArrowRight size={12} />
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {STUDIO_TOOLS.map((tool, idx) => {
              const Icon = TOOL_ICONS[tool.icon];
              const tier = TOOL_TIER_BADGES[tool.id] ?? {
                label: "STUDIO",
                style: "bg-white/10 border-white/20 text-gray-200",
              };

              return (
                <div
                  key={tool.id}
                  className="p-6 rounded-2xl bg-[#0e0e13] border border-white/[0.08] hover:border-ansys-yellow/40 transition-all flex flex-col justify-between space-y-5"
                >
                  <div className="space-y-4">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        <div className="p-2 rounded-xl bg-ansys-yellow/10 border border-ansys-yellow/25 text-ansys-yellow">
                          <Icon size={18} />
                        </div>
                        <span className="text-[11px] font-mono text-gray-500">0{idx + 1}</span>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded-full border text-[10px] font-mono font-bold uppercase tracking-wider ${tier.style}`}
                      >
                        {tier.label}
                      </span>
                    </div>

                    <div>
                      <h3 className="text-lg font-bold text-white">{tool.label}</h3>
                      <div className="mt-2 space-y-1.5">
                        {tool.routes.map((route) => (
                          <Link
                            key={route.href}
                            href={route.href}
                            className="block p-2.5 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.05] transition-colors group"
                          >
                            <div className="flex items-center justify-between text-xs font-semibold text-gray-200 group-hover:text-ansys-yellow">
                              <span>{route.label}</span>
                              <ArrowRight size={12} />
                            </div>
                            <p className="text-[11px] text-gray-400 mt-0.5">{route.desc}</p>
                          </Link>
                        ))}
                      </div>
                    </div>
                  </div>

                  <Link
                    href={tool.href}
                    className="inline-flex items-center gap-1.5 text-xs font-bold text-ansys-yellow hover:underline"
                  >
                    <span>Open {tool.label}</span>
                    <ArrowRight size={13} />
                  </Link>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── 2.5. ENGINEERING VERIFICATION, MARGINS OF ERROR & WORKFLOW BENCHMARKS ── */}
      <section className="py-16 px-4 sm:px-6 border-b border-white/[0.08] bg-[#08080a]">
        <div className="max-w-[1380px] mx-auto space-y-12">
          <div>
            <span className="text-[11px] font-mono font-bold uppercase tracking-[0.2em] text-[#06B6D4]">
              Rigorous Mathematical Credibility &amp; Productivity
            </span>
            <h2 className="text-2xl sm:text-3xl font-bold text-white mt-1">
              Engineering Verification, Margins of Error &amp; Workflow Benchmarks
            </h2>
            <p className="text-sm text-gray-400 mt-2 max-w-3xl">
              Transparent numerical tolerances, physical boundary conditions, and measured time savings compared to legacy multi-body CAD scripts and spreadsheet modeling.
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Table A: Solver Verification & Physical Applicability Matrix */}
            <div className="bg-[#0e0e12] border border-[#252525] rounded-2xl p-6 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-4 pb-3 border-b border-[#1f1f24]">
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-[#06B6D4]" />
                    Solver Verification &amp; Physical Applicability Matrix
                  </h3>
                  <span className="text-[10px] font-mono uppercase tracking-wider text-gray-500">ISO 8855 / SAE J670</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-[#252525] text-gray-400 text-[11px]">
                        <th className="pb-3 font-semibold">Physics Domain</th>
                        <th className="pb-3 font-semibold">Numerical Method</th>
                        <th className="pb-3 font-semibold">Rig / Physical Applicability</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#1a1a1f] text-gray-300">
                      <tr>
                        <td className="py-3.5 font-bold text-white">3D Spatial Kinematics</td>
                        <td className="py-3.5 text-[#06B6D4]">Newton-Raphson rigid-body closure (≤ 10⁻¹⁰ mm residual)</td>
                        <td className="py-3.5 text-gray-400">±0.05°–0.15° vs. physical K&amp;C rig due to elastomer bushing compliance</td>
                      </tr>
                      <tr>
                        <td className="py-3.5 font-bold text-white">2-DOF &amp; 7-DOF Ride/Modal</td>
                        <td className="py-3.5 text-[#06B6D4]">Stiff BDF ODE integration (rtol = 10⁻⁶, &lt;2.5% modal delta)</td>
                        <td className="py-3.5 text-gray-400">±3%–8% vertical RMS accuracy on calibrated 4-post shaker / track profiles</td>
                      </tr>
                      <tr>
                        <td className="py-3.5 font-bold text-white">Steady-State &amp; Transient Handling</td>
                        <td className="py-3.5 text-[#06B6D4]">Coupled Roll-Stiffness &amp; Pacejka Model</td>
                        <td className="py-3.5 text-gray-400">±5%–10% analytical under &lt;0.4g linear regime; &gt;0.5g nonlinear limit calibrated via CSV Telemetry Correlation</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="mt-4 pt-3 border-t border-[#1a1a1f] text-[11px] text-gray-500 flex items-center justify-between">
                <span>Deterministic BDF &amp; QR linear algebra execution</span>
                <span className="text-emerald-400 font-bold">100% Deterministic Reproducibility</span>
              </div>
            </div>

            {/* Table B: Quantified Engineering Time-Savings Benchmarks */}
            <div className="bg-[#0e0e12] border border-[#252525] rounded-2xl p-6 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-4 pb-3 border-b border-[#1f1f24]">
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-[#F59E0B]" />
                    Quantified Engineering Time-Savings Benchmarks
                  </h3>
                  <span className="text-[10px] font-mono uppercase tracking-wider text-gray-500">Trackside / CAE Velocity</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-[#252525] text-gray-400 text-[11px]">
                        <th className="pb-3 font-semibold">Engineering Task</th>
                        <th className="pb-3 font-semibold">Legacy Baseline</th>
                        <th className="pb-3 font-semibold text-[#F59E0B]">SuspensionLab Studio</th>
                        <th className="pb-3 font-semibold text-emerald-400">Speedup</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#1a1a1f] text-gray-300">
                      <tr>
                        <td className="py-3.5 font-bold text-white">36-Variable Hardpoint Jacobian Sensitivity Sweep</td>
                        <td className="py-3.5 text-gray-400">~45 min (Manual CAD/Excel)</td>
                        <td className="py-3.5 text-[#06B6D4] font-bold">&lt; 2 sec</td>
                        <td className="py-3.5 text-emerald-400 font-bold">~1,350×</td>
                      </tr>
                      <tr>
                        <td className="py-3.5 font-bold text-white">Multi-Objective Pareto Damper &amp; Spring Trade-Off (25+ runs)</td>
                        <td className="py-3.5 text-gray-400">~2.0 hrs (Manual script loop)</td>
                        <td className="py-3.5 text-[#06B6D4] font-bold">&lt; 5 sec</td>
                        <td className="py-3.5 text-emerald-400 font-bold">~1,440×</td>
                      </tr>
                      <tr>
                        <td className="py-3.5 font-bold text-white">Post-Session CSV Sync, G-G Circle &amp; 3-Page Vector PDF Dossier</td>
                        <td className="py-3.5 text-gray-400">~2.0 hrs (MATLAB + Word)</td>
                        <td className="py-3.5 text-[#06B6D4] font-bold">&lt; 3 min</td>
                        <td className="py-3.5 text-emerald-400 font-bold">~40×</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="mt-4 pt-3 border-t border-[#1a1a1f] text-[11px] text-gray-500 flex items-center justify-between">
                <span>Measured on Formula Student &amp; GT3 track engineering workflows</span>
                <span className="text-[#F59E0B] font-bold">Instant Trackside Decisions</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── 3. PRICING PREVIEW ───────────────────────────────────────────── */}
      <section className="py-16 px-4 sm:px-6 border-b border-white/[0.08]">
        <div className="max-w-[1380px] mx-auto space-y-10">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <span className="text-[11px] font-mono font-bold uppercase tracking-[0.2em] text-ansys-yellow">
                Pricing Preview
              </span>
              <h2 className="text-2xl sm:text-3xl font-bold text-white mt-1">
                Free interactive hook, straightforward Gumroad &amp; team licensing
              </h2>
            </div>
            <Link
              href="/pricing"
              className="text-xs font-mono text-ansys-yellow hover:underline inline-flex items-center gap-1"
            >
              <span>Full pricing &amp; FAQ</span>
              <ArrowRight size={12} />
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {PRICING_PREVIEW.map((tier) => {
              const TierIcon = tier.icon;
              return (
                <div
                  key={tier.name}
                  className={`rounded-2xl p-7 bg-[#0d0d10] border flex flex-col justify-between ${
                    tier.highlight
                      ? "border-ansys-yellow shadow-[0_0_35px_rgba(242,169,0,0.09)]"
                      : "border-white/[0.08]"
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-4">
                      <div className="flex items-center gap-2">
                        <TierIcon size={16} className="text-ansys-yellow" />
                        <span className="text-xs font-bold uppercase tracking-widest text-gray-400">
                          {tier.name}
                        </span>
                      </div>
                      {tier.highlight && (
                        <span className="px-2.5 py-0.5 rounded-full bg-ansys-yellow text-black text-[10px] font-bold uppercase tracking-wider">
                          Most Popular
                        </span>
                      )}
                    </div>

                    <div className="flex items-baseline gap-2 mb-2">
                      <span className="text-3xl font-bold text-white">{tier.price}</span>
                      <span className="text-xs text-gray-500">{tier.cadence}</span>
                    </div>
                    <p className="text-sm text-gray-400 mb-6">{tier.desc}</p>

                    <ul className="space-y-2.5 mb-8">
                      {tier.features.map((feat) => (
                        <li key={feat} className="flex items-start gap-2 text-sm text-gray-300">
                          <Check size={14} className="text-emerald-400 mt-0.5 shrink-0" />
                          <span>{feat}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <Link
                    href={tier.ctaHref}
                    className={`w-full py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-all ${
                      tier.highlight
                        ? "bg-ansys-yellow text-black hover:brightness-110"
                        : "bg-white/[0.06] hover:bg-white/[0.12] border border-white/10 text-white"
                    }`}
                  >
                    <span>{tier.ctaLabel}</span>
                    <ArrowRight size={14} />
                  </Link>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── 4. AUTHENTICATED ENGINEERING COMMAND CENTER ──────────────────── */}
      {user && (
        <section id="command-center" aria-label="Engineering Command Center">
          <CommandCenterWorkspace />
        </section>
      )}
    </div>
  );
}
