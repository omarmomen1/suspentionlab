"use client";
import React, { useState } from "react";
import { whyChainLevers, whyChainRows, type WhyChainResponse } from "../../../lib/v2/phase4";

export type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

export interface WhyChainPanelProps {
  setupAParams?: Record<string, any> | null;
  setupBParams?: Record<string, any> | null;
  track?: string;
  fetcher: FetchLike;
  /** Test hook: render a response without calling the API. */
  initialResult?: WhyChainResponse | null;
}

/** Renders each link as unit, solver source and numeric leaves. No prose is generated. */
export function WhyChainRows({ result }: { result: WhyChainResponse }) {
  const rows = whyChainRows(result);
  return (
    <ol data-testid="why-chain" data-complete={result.chain_complete ? "1" : "0"} className="v2-num m-0 p-0 list-none text-[11px] text-zinc-200">
      {rows.map((r) => (
        <li key={r.link} data-link={r.link} data-status={r.status} className="border-t border-white/10 py-1">
          <div className="flex gap-2"><span className="font-mono">{r.link}</span><span className={r.status === "NOT_MODELED" ? "text-[#d9534f]" : "text-[#C8F04B]"}>{r.status}</span></div>
          {r.status === "NOT_MODELED" ? (
            <div className="text-[#8a909a]">{r.reason ?? "no reason code"}</div>
          ) : (
            <>
              <div className="text-[#8a909a]">unit: {r.unit} · source: {r.source}</div>
              {r.numbers.map((n) => (
                <div key={n.path} data-path={n.path} data-value={String(n.value)}>{n.path || "value"}: {Number(n.value.toPrecision(5))}</div>
              ))}
            </>
          )}
        </li>
      ))}
    </ol>
  );
}

export default function WhyChainPanel({ setupAParams, setupBParams, track = "spa", fetcher, initialResult = null }: WhyChainPanelProps) {
  const [result, setResult] = useState<WhyChainResponse | null>(initialResult);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lv = whyChainLevers(setupAParams, setupBParams);
  const canRun = lv.changed.length > 0;

  const run = async () => {
    setBusy(true); setError(null);
    try {
      const res = await fetcher("/api/v1/lap-sim/why-chain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ setup_a: lv.setup_a, setup_b: lv.setup_b, track }),
      });
      if (!res.ok) {
        let d = `Why Chain failed (${res.status})`;
        try { const j = await res.json(); if (typeof j?.detail === "string") d = j.detail; } catch { /* keep default */ }
        throw new Error(d);
      }
      setResult((await res.json()) as WhyChainResponse);
    } catch (e: any) {
      setResult(null); setError(e?.message ?? "Why Chain failed");
    } finally { setBusy(false); }
  };

  return (
    <section data-testid="why-chain-panel" className="border border-white/10 bg-[#13181D] p-3">
      <div className="flex items-center gap-3">
        <h3 className="text-xs uppercase tracking-wide text-[#8a909a] m-0">Why Chain</h3>
        <button type="button" onClick={run} disabled={!canRun || busy} className="text-[11px] px-2 py-1 border border-white/10 text-zinc-200 disabled:opacity-40">
          {busy ? "Running" : "Compute Why Chain"}
        </button>
      </div>
      {!canRun && <p className="text-[11px] text-[#8a909a] mt-2 mb-0" data-testid="why-chain-disabled">Pin a baseline and change a spring, ARB or ride-height value to compare.</p>}
      {canRun && !result && !error && (
        <p className="text-[11px] text-[#8a909a] mt-2 mb-0">Levers sent: {lv.changed.join(", ")}. Vehicle values other than these use backend defaults. Spa-length solve, several seconds.</p>
      )}
      {error && <p role="alert" className="text-[11px] text-[#d9534f] mt-2 mb-0">{error}</p>}
      {result && <div className="mt-2"><WhyChainRows result={result} /></div>}
    </section>
  );
}
