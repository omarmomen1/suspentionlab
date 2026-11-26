"use client";
import React from "react";
import StatusPill from "./StatusPill";
import EmptyState from "./EmptyState";
import RunBadge from "./RunBadge";
import TrustBadge from "../TrustBadge";

export interface VerdictHero {
  label: string;
  /** Numeric or preformatted value. null/undefined/NaN renders "Not available", never 0. */
  value: number | string | null | undefined;
  unit?: string;
  decimals?: number;
}

export interface VerdictRailProps {
  /** Any backend status string or V2 state. Missing means NOT_RUN. */
  status: string | null | undefined;
  statusDetail?: string;
  /** Overrides the pill text (the state colour stays truthful). */
  statusLabel?: string;
  heroes: VerdictHero[];
  solverVersion?: string | null;
  runId?: string | null;
  inputSha256?: string | null;
  outputSha256?: string | null;
  /** "run" (default) shows RunBadge; "trust" shows the Wave 6 TrustBadge footer. */
  badge?: "run" | "trust";
  action?: { label: string; onClick: () => void; loading?: boolean; disabled?: boolean };
  /** Extra notes or links (for example NextStepLink). */
  children?: React.ReactNode;
}

function formatHero(h: VerdictHero): string | null {
  const v = h.value;
  if (v === null || v === undefined) return null;
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return null;
    return h.decimals !== undefined ? v.toFixed(h.decimals) : String(v);
  }
  return v.trim() === "" ? null : v;
}

/** Right-hand verdict: one status pill, hero numbers with units, provenance and the primary solver action. */
export default function VerdictRail({
  status, statusDetail, statusLabel, heroes, solverVersion, runId, inputSha256, outputSha256, badge = "run", action, children,
}: VerdictRailProps) {
  return (
    <aside data-testid="verdict-rail" aria-label="Verdict" className="flex flex-col gap-3 rounded border border-hairline bg-panel p-4">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-gray-400">Verdict</span>
        <StatusPill status={status} detail={statusDetail} label={statusLabel} />
      </div>
      <dl className="space-y-2.5">
        {heroes.map((h) => {
          const text = formatHero(h);
          return (
            <div key={h.label} className="border-t border-hairline pt-2 first:border-t-0 first:pt-0">
              <dt className="text-[10px] uppercase tracking-wider text-gray-500">{h.label}</dt>
              <dd className="mt-0.5">
                {text === null ? (
                  <EmptyState kind="unavailable" />
                ) : (
                  <span className="v2-num text-xl font-semibold text-white">
                    {text}
                    {h.unit ? <span className="ml-1 text-xs font-normal text-gray-400">{h.unit}</span> : null}
                  </span>
                )}
              </dd>
            </div>
          );
        })}
      </dl>
      {badge === "trust"
        ? <TrustBadge solverVersion={solverVersion} runId={runId} inputSha256={inputSha256} />
        : <RunBadge solverVersion={solverVersion} runId={runId} inputSha256={inputSha256} outputSha256={outputSha256} />}
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          disabled={action.disabled || action.loading}
          data-testid="verdict-action"
          className="rounded border border-signal bg-signal px-4 py-2.5 text-sm font-bold text-carbon transition-colors hover:bg-[#d6f56e] disabled:cursor-not-allowed disabled:border-hairline disabled:bg-transparent disabled:text-gray-500"
        >
          {action.loading ? "Solving..." : action.label}
        </button>
      )}
      {children}
    </aside>
  );
}
