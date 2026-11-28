"use client";

/**
 * components/NextStepLink.tsx
 * Compact contextual "Next Step ->" workflow link shown on the core studio
 * pages (3D Kinematics -> Quarter-Car -> Full-Car / Lap Sim -> Investigate ->
 * Memory & PDF). Driven by STUDIO_WORKFLOW_CHAIN in lib/navigation.ts so the
 * chain is defined in exactly one place. Renders nothing off-chain.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { nextStepFor } from "../lib/navigation";

export default function NextStepLink() {
  const pathname = usePathname();
  const next = nextStepFor(pathname);
  if (!next) return null;
  return (
    <Link
      href={next.href}
      className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-400 hover:text-signal transition-colors"
      aria-label={`Next step: ${next.label}`}
    >
      <span className="uppercase tracking-widest text-xs text-zinc-300">Next Step</span>
      <span>{next.label}</span>
      <ArrowRight size={12} />
    </Link>
  );
}
