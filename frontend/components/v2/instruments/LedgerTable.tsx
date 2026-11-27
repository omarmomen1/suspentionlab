"use client";
import React from "react";
import StatusPill from "../StatusPill";
import EmptyState from "../EmptyState";

export interface LedgerRow {
  id: string;
  parameter: string;
  /** null/undefined/NaN renders "Not available". */
  value: number | null | undefined;
  unit: string;
  /** Baseline value in the same unit. Without it the delta is "Not available". */
  base?: number | null;
  /** Backend status string or V2 state; missing means NOT_RUN. */
  status?: string | null;
  /** Where the number comes from, e.g. "solver run swp-123" or "user input". */
  source: string;
  decimals?: number;
}

export interface LedgerTableProps {
  rows: LedgerRow[];
  caption?: string;
  /** Row ids currently pinned for the PDF export. */
  pinnedIds?: string[];
  onTogglePin?: (row: LedgerRow) => void;
}

const fin = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

/** Signed difference value - base, or null when either side is missing. Never a fake 0. */
export function ledgerDelta(row: Pick<LedgerRow, "value" | "base">): number | null {
  return fin(row.value) && fin(row.base) ? row.value - row.base : null;
}

/** Dense, unit-labelled ledger: Parameter | Value | Unit | Δ Base | Status | Source. */
export default function LedgerTable({ rows, caption, pinnedIds = [], onTogglePin }: LedgerTableProps) {
  return (
    <div data-testid="ledger-table" className="overflow-x-auto rounded border border-hairline bg-panel">
      <table className="w-full min-w-[560px] text-left text-[11px]">
        {caption && <caption className="p-2 text-left text-[10px] uppercase tracking-wider text-gray-500">{caption}</caption>}
        <thead>
          <tr className="border-b border-hairline text-[10px] uppercase tracking-wider text-gray-500">
            {onTogglePin && <th className="w-8 p-2" aria-label="Pin" />}
            <th className="p-2">Parameter</th>
            <th className="p-2 text-right">Value</th>
            <th className="p-2">Unit</th>
            <th className="p-2 text-right">Δ Base</th>
            <th className="p-2">Status</th>
            <th className="p-2">Source</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const d = ledgerDelta(r);
            const dp = r.decimals ?? 2;
            const pinned = pinnedIds.includes(r.id);
            return (
              <tr key={r.id} data-row-id={r.id} className="border-b border-hairline last:border-b-0 text-gray-300">
                {onTogglePin && (
                  <td className="p-2">
                    <button
                      type="button"
                      aria-pressed={pinned}
                      aria-label={`${pinned ? "Unpin" : "Pin"} ${r.parameter}`}
                      onClick={() => onTogglePin(r)}
                      className={`h-4 w-4 rounded-sm border ${pinned ? "border-signal bg-signal" : "border-hairline bg-transparent"}`}
                    />
                  </td>
                )}
                <td className="p-2 text-white">{r.parameter}</td>
                <td className="p-2 text-right">
                  {fin(r.value) ? <span className="v2-num">{r.value.toFixed(dp)}</span> : <EmptyState />}
                </td>
                <td className="p-2 text-gray-400">{r.unit}</td>
                <td className="p-2 text-right">
                  {d === null ? <EmptyState /> : <span className="v2-num">{`${d > 0 ? "+" : ""}${d.toFixed(dp)}`}</span>}
                </td>
                <td className="p-2"><StatusPill status={r.status ?? null} /></td>
                <td className="p-2 text-gray-500">{r.source}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
