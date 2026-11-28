"use client";
import React from "react";
import { ShieldCheck } from "lucide-react";

export interface TrustBadgeProps {
  /** Build-stamped solver version (e.g. "2.1.0-simd+git:abc123def456"). */
  solverVersion?: string | null;
  /** Server-issued run identifier. */
  runId?: string | null;
  /** SHA-256 of the exact solver inputs. */
  inputSha256?: string | null;
  /** Extra class for the outer footer. */
  className?: string;
}

const truncate = (v: string, head = 8, tail = 4): string =>
  v.length > head + tail + 3 ? `${v.slice(0, head)}...${v.slice(-tail)}` : v;

/**
 * Wave 6: compact provenance "Trust Badge" shown as a footer on solver
 * figures and reports. Renders nothing when no provenance fields are present,
 * so callers can mount it unconditionally on any result object.
 */
export default function TrustBadge({ solverVersion, runId, inputSha256, className = "" }: TrustBadgeProps) {
  const sv = solverVersion?.trim();
  const rid = runId?.trim();
  const sha = inputSha256?.trim();
  if (!sv && !rid && !sha) return null;

  return (
    <footer
      data-testid="trust-badge"
      className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-mono text-zinc-400 print:text-gray-600 ${className}`}
    >
      <span className="inline-flex items-center gap-1 text-emerald-500 print:text-emerald-700">
        <ShieldCheck size={12} aria-hidden />
        <span className="font-semibold tracking-wide uppercase">Verified provenance</span>
      </span>
      {sv && <span title={`Solver version: ${sv}`}>solver {truncate(sv, 20, 0)}</span>}
      {rid && <span title={`Run ID: ${rid}`}>run {truncate(rid, 12, 0)}</span>}
      {sha && <span title={`Input SHA-256: ${sha}`}>input {truncate(sha)}</span>}
    </footer>
  );
}
