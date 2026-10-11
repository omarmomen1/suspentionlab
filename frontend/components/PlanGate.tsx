"use client";
import { useAuth } from "../contexts/AuthContext";
import Link from "next/link";

interface PlanGateProps {
  required: "PRO" | "ENTERPRISE";
  children: React.ReactNode;
  /** If true, renders an upgrade overlay placeholder rather than replacing inline */
  overlay?: boolean;
  feature?: string;
}

const PLAN_COPY = {
  PRO: {
    badge: "PRO",
    color: "text-ansys-yellow border-ansys-yellow/30 bg-ansys-yellow/5",
    desc: "Upgrade to Pro to unlock this feature.",
  },
  ENTERPRISE: {
    badge: "ENTERPRISE",
    color: "text-[#bf5af2] border-purple-500/30 bg-purple-900/10",
    desc: "This feature is available on the Enterprise plan.",
  },
};

export default function PlanGate({ required, children, overlay = false, feature }: PlanGateProps) {
  const { user } = useAuth();
  const LEVELS: Record<string, number> = { FREE: 0, PRO: 1, ENTERPRISE: 2, TRIAL: 1 };
  const userLevel = LEVELS[user?.plan ?? "FREE"] ?? 0;
  const requiredLevel = LEVELS[required] ?? 1;
  const hasAccess = userLevel >= requiredLevel;

  if (hasAccess) return <>{children}</>;

  const copy = PLAN_COPY[required];

  // SECURITY (P0-SEC-01): restricted content is NEVER rendered to the DOM.
  // The previous overlay mode rendered children hidden only by CSS
  // (opacity/blur/pointer-events), which any user could bypass via DevTools.
  // Overlay mode now renders an empty sized placeholder instead. Note the
  // server-side API still enforces the plan — this component is UX, not the gate.
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
          <p className="text-xs text-gray-400 mb-3 text-center max-w-[180px]">{copy.desc}</p>
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
      className={`flex flex-col items-center justify-center gap-3 p-8 rounded-xl border ${copy.color}`}
    >
      <span className={`text-[10px] font-bold tracking-[0.18em] uppercase border px-2.5 py-1 rounded-full ${copy.color}`}>
        {copy.badge} REQUIRED
      </span>
      <p className="text-sm text-gray-300 text-center max-w-sm">{copy.desc}</p>
      <Link href="/pricing"
        className="mt-1 text-xs font-bold px-4 py-2 bg-ansys-yellow text-black rounded-xl hover:brightness-110 transition-all">
        View Pricing & Upgrade
      </Link>
    </div>
  );
}
