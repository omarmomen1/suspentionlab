"use client";
import React, { useEffect, useMemo, useState } from "react";
import LedgerTable, { type LedgerRow } from "./LedgerTable";

export interface LedgerDockProps {
  rows: LedgerRow[];
  caption?: string;
  /** Called whenever the pinned set or the rows change, with the pinned rows in table order. */
  onPinnedChange?: (rows: LedgerRow[]) => void;
  /** Show pin toggles. Set false where nothing consumes pinned rows. Default true. */
  pinnable?: boolean;
}

/**
 * Ledger with its own baseline and pin state. "Set baseline" snapshots the current values so
 * Δ Base is real (value minus snapshot). Without a baseline the delta column says Not available.
 */
export default function LedgerDock({ rows, caption, onPinnedChange, pinnable = true }: LedgerDockProps) {
  const [baseline, setBaseline] = useState<Record<string, number | null> | null>(null);
  const [pinned, setPinned] = useState<string[]>([]);

  const withBase = useMemo(
    () => rows.map((r) => ({ ...r, base: baseline ? (baseline[r.id] ?? null) : null })),
    [rows, baseline],
  );

  useEffect(() => {
    onPinnedChange?.(withBase.filter((r) => pinned.includes(r.id)));
  }, [withBase, pinned, onPinnedChange]);

  if (rows.length === 0) return null;
  return (
    <section data-testid="ledger-dock" className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-[10px] font-semibold uppercase tracking-[0.18em] text-gray-400">Ledger</h3>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setBaseline(Object.fromEntries(rows.map((r) => [r.id, typeof r.value === "number" && Number.isFinite(r.value) ? r.value : null])))}
            className="rounded border border-hairline px-2 py-1 text-[10px] font-semibold text-gray-300 hover:bg-white/[0.06]"
          >
            Set baseline
          </button>
          {baseline && (
            <button type="button" onClick={() => setBaseline(null)} className="rounded border border-hairline px-2 py-1 text-[10px] text-gray-400 hover:bg-white/[0.06]">
              Clear baseline
            </button>
          )}
          {pinnable && <span className="self-center text-[10px] text-gray-500">{pinned.length} pinned for PDF</span>}
        </div>
      </div>
      <LedgerTable
        rows={withBase}
        caption={caption}
        pinnedIds={pinned}
        onTogglePin={!pinnable ? undefined : (row) => setPinned((p) => (p.includes(row.id) ? p.filter((x) => x !== row.id) : [...p, row.id]))}
      />
    </section>
  );
}
