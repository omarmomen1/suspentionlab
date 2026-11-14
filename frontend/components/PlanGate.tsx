"use client";
import { useAuth } from "../contexts/AuthContext";
import { getUserPlanLevel, PLAN_LEVELS } from "../lib/planGate";
import Link from "next/link";

interface PlanGateProps {
  required: "PRO" | "ENTERPRISE";
  children: React.ReactNode;
  /** If true, renders an upgrade overlay placeholder rather than replacing inline */
  overlay?: boolean;
  /** If true, renders a compact inline pill suitable for toolbars */
  compact?: boolean;
  feature?: string;
}

const PLAN_COPY = {
  PRO: {
    badge: "PRO",
    color: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    desc: "Upgrade to Pro Engineer ($79/mo) to unlock full telemetry, multi-body solvers, and exports.",
  },
  ENTERPRISE: {
    badge: "ENTERPRISE",
    color: "text-cyan-400 border-cyan-500/30 bg-cyan-950/20",
    desc: "This capability is included with the Race Team & Consultancy Pass ($499/yr — Up to 10 Seats) for institutional setup lineage and signed approvals.",
  },
};

const PRO_DELIVERABLES = [
  {
    code: "01",
    title: "7-DOF Full-Car & Bicycle Solvers",
    detail: "Coupled pitch, roll, heave, lateral load transfer & understeer gradient sweeps",
  },
  {
    code: "02",
    title: "MoTeC / AiM CSV Telemetry Correlation",
    detail: "100 Hz PCHIP monotonic alignment, channel health & ODE vs. DAQ overlay",
  },
  {
    code: "03",
    title: "Multi-Objective Pareto Optimizer",
    detail: "Automated non-dominated hardpoint, spring & damper frontier search",
  },
  {
    code: "04",
    title: "3-Page Vector PDF & MATLAB Exports",
    detail: "Sign-off engineering dossiers, kinematics CSV/JSON & MAT-compatible outputs",
  },
];

export default function PlanGate({ required, children, overlay = false, compact = false, feature }: PlanGateProps) {
  const { user, loading } = useAuth();
  const userLevel = getUserPlanLevel(user);
  const requiredLevel = PLAN_LEVELS[required] ?? 1;
  const hasAccess = userLevel >= requiredLevel;

  if (loading) {
    if (compact) {
      return (
        <span
          aria-busy="true"
          className="inline-flex items-center px-2 py-0.5 rounded bg-slate-800/60 border border-slate-700/50 text-[10px] font-mono text-slate-400 animate-pulse"
        >
          Checking access...
        </span>
      );
    }
    return (
      <div
        aria-busy="true"
        className="w-full min-h-[160px] rounded-xl bg-slate-900/40 border border-slate-800/60 p-6 flex items-center justify-center animate-pulse"
      >
        <span className="text-xs font-mono text-slate-400 tracking-wide">
          Verifying workspace access...
        </span>
      </div>
    );
  }

  if (hasAccess) return <>{children}</>;

  const copy = PLAN_COPY[required];

  // SECURITY (P0-SEC-01): restricted content is NEVER rendered to the DOM.
  // The previous overlay mode rendered children hidden only by CSS
  // (opacity/blur/pointer-events), which any user could bypass via DevTools.
  // Overlay mode now renders an empty sized placeholder instead. Note the
  // server-side API still enforces the plan — this component is UX, not the gate.
  if (compact) {
    return (
      <Link
        href="/pricing"
        role="region"
        aria-label={`${required} Plan required: ${feature || copy.desc}`}
        title={copy.desc}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all hover:brightness-110 ${copy.color}`}
      >
        <span className="text-[10px] font-bold tracking-[0.14em] uppercase">{copy.badge}</span>
        {feature && <span className="text-gray-200">· {feature}</span>}
      </Link>
    );
  }

  if (overlay) {
    return (
      <div
        role="region"
        aria-label={`${required} Plan required: ${feature || copy.desc}`}
        className="relative min-h-[240px]"
      >
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/60 rounded-xl border border-white/5 backdrop-blur-sm">
          <span className={`text-[10px] font-bold tracking-[0.18em] uppercase border px-2.5 py-1 rounded-full mb-2 ${copy.color}`}>
            {copy.badge}
          </span>
          {feature && <p className="text-xs text-gray-300 mb-1">{feature}</p>}
          <p className="text-xs text-gray-400 mb-3 text-center max-w-[200px]">{copy.desc}</p>
          <Link href="/pricing"
            className="text-xs font-bold px-3 py-1.5 bg-ansys-yellow text-black rounded-lg hover:brightness-110 transition-all">
            Upgrade Plan
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div
      role="region"
      aria-label={`${required} Plan required`}
      className="my-8 mx-auto max-w-2xl rounded-2xl bg-[#0e0f14] border border-[#232736] p-6 sm:p-8 shadow-2xl space-y-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] pb-4">
        <div className="space-y-1">
          <span className={`inline-flex items-center text-[10px] font-mono font-bold tracking-[0.18em] uppercase border px-2.5 py-0.5 rounded-full ${copy.color}`}>
            {copy.badge} REQUIRED
          </span>
          {feature && <h2 className="text-base sm:text-lg font-bold text-white tracking-tight pt-1">{feature}</h2>}
        </div>
        <div className="text-right font-mono">
          <div className="text-xs font-bold text-amber-400">
            {required === "ENTERPRISE" ? "$499 / yr" : "$79 / mo"}
          </div>
          <div className="text-[10px] text-slate-400">
            {required === "ENTERPRISE" ? "Up to 10 Seats" : "License key required"}
          </div>
        </div>
      </div>

      <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">{copy.desc}</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {PRO_DELIVERABLES.map((item) => (
          <div
            key={item.code}
            className="p-3 rounded-xl bg-[#090a0e] border border-[#1d202b] space-y-1"
          >
            <div className="flex items-center gap-2 font-mono text-[10px] text-cyan-400 uppercase tracking-wider font-bold">
              <span>[{item.code}]</span>
              <span className="text-slate-100 font-sans text-xs tracking-normal normal-case font-semibold">
                {item.title}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 leading-snug">{item.detail}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-white/[0.06]">
        {required === "ENTERPRISE" ? (
          process.env.NEXT_PUBLIC_GUMROAD_TEAM_URL ? (
            <a
              href={process.env.NEXT_PUBLIC_GUMROAD_TEAM_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black text-xs font-bold tracking-wide transition-all shadow-md"
            >
              Unlock Race Team Pass ($499/yr) -&gt;
            </a>
          ) : (
            <Link
              href="/pricing"
              className="inline-flex items-center justify-center px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black text-xs font-bold tracking-wide transition-all shadow-md"
            >
              Unlock Race Team Pass ($499/yr) -&gt;
            </Link>
          )
        ) : process.env.NEXT_PUBLIC_GUMROAD_PRO_URL ? (
          <a
            href={process.env.NEXT_PUBLIC_GUMROAD_PRO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black text-xs font-bold tracking-wide transition-all shadow-md"
          >
            Unlock Pro Pass on Gumroad ($79/mo) -&gt;
          </a>
        ) : (
          <Link
            href="/pricing"
            className="inline-flex items-center justify-center px-5 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-400 text-black text-xs font-bold tracking-wide transition-all shadow-md"
          >
            Unlock Pro Pass on Gumroad ($79/mo) -&gt;
          </Link>
        )}
        <Link
          href="/settings#billing"
          className="inline-flex items-center justify-center px-4 py-2.5 rounded-xl bg-[#14161f] hover:bg-[#1c1f2b] border border-[#282c3d] text-slate-200 text-xs font-semibold transition-all"
        >
          Already have a License Key? Activate -&gt;
        </Link>
      </div>
    </div>
  );
}
