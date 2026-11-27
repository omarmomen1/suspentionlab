"use client";
import React from "react";

export interface RunBadgeProps {
  /** Build-stamped solver version, e.g. "2.1.0+abc1234". */
  solverVersion?: string | null;
  runId?: string | null;
  inputSha256?: string | null;
  outputSha256?: string | null;
  className?: string;
}

const short = (v: string, n = 8): string => (v.length > n + 3 ? `${v.slice(0, n)}...` : v);

/**
 * Compact provenance chip. Shows solver build and run ID; the full input and
 * output SHA-256 are on hover. Renders nothing when there is no provenance.
 */
export default function RunBadge({ solverVersion, runId, inputSha256, outputSha256, className = "" }: RunBadgeProps) {
  const sv = solverVersion?.trim();
  const rid = runId?.trim();
  const ish = inputSha256?.trim();
  const osh = outputSha256?.trim();
  if (!sv && !rid && !ish && !osh) return null;
  const title = [
    sv && `Solver build: ${sv}`,
    rid && `Run ID: ${rid}`,
    ish && `Input SHA-256: ${ish}`,
    osh && `Output SHA-256: ${osh}`,
  ].filter(Boolean).join("\n");
  return (
    <span
      data-testid="run-badge"
      title={title}
      tabIndex={0}
      className={`inline-flex items-center gap-2 rounded border border-hairline bg-panel px-2 py-0.5 text-[10px] text-gray-400 v2-num ${className}`}
    >
      {sv && <span>{sv}</span>}
      {rid && <span>run {short(rid, 12)}</span>}
      {ish && <span>in {short(ish)}</span>}
      {osh && <span>out {short(osh)}</span>}
    </span>
  );
}
