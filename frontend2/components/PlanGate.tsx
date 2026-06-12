"use client";
import { useAuth } from "../contexts/AuthContext";
import Link from "next/link";

interface PlanGateProps {
  required: "PRO" | "ENTERPRISE";
  children: React.ReactNode;
  /** If true, renders children blurred with an overlay rather than replacing them */
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
  const LEVELS = { FREE: 0, PRO: 1, ENTERPRISE: 2 };
  const userLevel = LEVELS[user?.plan ?? "FREE"] ?? 0;
  const requiredLevel = LEVELS[required] ?? 1;
  const hasAccess = userLevel >= requiredLevel;

  if (hasAccess) return <>{children}</>;

  const copy = PLAN_COPY[required];

  if (overlay) {
    return (
      <div className="relative">
        <div className="pointer-events-none select-none opacity-30 blur-sm">{children}</div>
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/60 rounded-xl border border-white/5">
          <span className={`text-[10px] font-bold tracking-[0.18em] uppercase border px-2.5 py-1 rounded-full mb-2 ${copy.color}`}>
            {copy.badge}
          </span>
          {feature && <p className="text-xs text-gray-400 mb-1">{feature}</p>}
          <p className="text-xs text-gray-500 mb-3 text-center max-w-[180px]">{copy.desc}</p>
          <Link href="/pricing"
            className="text-xs font-bold px-3 py-1.5 bg-ansys-yellow text-black rounded-lg hover:brightness-110 transition-all">
            Upgrade Plan →
          </Link>
        </div>
      </div>
    );
  }

  return (
    <Link href="/pricing"
      className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-semibold hover:opacity-80 transition-opacity cursor-pointer h-10 ${copy.color}`}>
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
      </svg>
      {copy.badge} REQUIRED
    </Link>
  );
}
