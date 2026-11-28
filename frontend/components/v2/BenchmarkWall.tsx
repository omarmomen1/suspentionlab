"use client";
import React, { useEffect, useState } from "react";
import StatusPill from "./StatusPill";
import ErrorCard from "./ErrorCard";
import EmptyState from "./EmptyState";

export interface BenchmarkCheck {
  test: string;
  verdict: string;
  measured: Record<string, number | string>;
  tolerance: Record<string, unknown>;
  reference: string;
}
export interface BenchmarkTile {
  id: string;
  name: string;
  description: string;
  verdict: string;
  checks: BenchmarkCheck[];
  pending?: Record<string, string>;
}
export interface BenchmarkStatusFile {
  schema_version: number;
  git_sha: string;
  generated_at: string;
  scope_note: string;
  benchmarks: BenchmarkTile[];
}

const fmt = (v: unknown): string => (typeof v === "number" ? (Number.isInteger(v) ? String(v) : String(Number(v.toPrecision(5)))) : String(v));

/** Live Benchmark Wall: one tile per benchmark, read from /benchmark-status.json (written by CI-backed pytest). */
export default function BenchmarkWall() {
  const [data, setData] = useState<BenchmarkStatusFile | null>(null);
  const [err, setErr] = useState<unknown>(null);

  useEffect(() => {
    let alive = true;
    // Public static file served by Next.js, not the backend API: apiFetch (auth + base URL) does not apply.
    // eslint-disable-next-line no-restricted-syntax
    fetch("/benchmark-status.json", { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<BenchmarkStatusFile>;
      })
      .then((j) => alive && setData(j))
      .catch((e) => alive && setErr(e));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <section data-testid="benchmark-wall" aria-labelledby="benchmark-wall-title" className="border-b border-hairline px-4 py-14 sm:px-6">
      <div className="mx-auto max-w-[1280px] space-y-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-signal">Benchmark Wall</p>
          <h2 id="benchmark-wall-title" className="mt-1 font-[var(--font-display)] text-2xl font-bold text-white">
            Solver checks, re-run on every pull request
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-gray-400">
            {data?.scope_note ?? "Each tile is a pytest result. A failing test turns its tile red."}
          </p>
        </div>
        {err !== null && <ErrorCard error={err} context="Benchmark status unavailable" />}
        {!data && err === null && <EmptyState kind="not_run" reason="Loading benchmark status" />}
        {data && (
          <>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {data.benchmarks.map((b) => (
                <article key={b.id} data-testid={`benchmark-tile-${b.id}`} className="rounded border border-hairline bg-panel p-4">
                  <header className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs text-zinc-400 v2-num">{b.id}</p>
                      <h3 className="text-base font-semibold text-white">{b.name}</h3>
                    </div>
                    <StatusPill status={b.verdict} />
                  </header>
                  <p className="mt-2 text-xs text-gray-400">{b.description}</p>
                  <dl className="mt-3 space-y-1 text-xs">
                    {b.checks.flatMap((c) =>
                      Object.entries(c.measured).map(([k, v]) => (
                        <div key={`${c.test}-${k}`} className="flex justify-between gap-3 border-t border-hairline pt-1">
                          <dt className="text-zinc-400">{k.replace(/_/g, " ")}</dt>
                          <dd className="text-gray-200 v2-num">{fmt(v)}</dd>
                        </div>
                      )),
                    )}
                  </dl>
                  {b.pending && (
                    <p className="mt-3 flex items-center gap-2 text-xs text-gray-400">
                      <StatusPill status="NOT_RUN" label="In progress" />
                      <span>
                        Calspan TTC fit: {b.pending.reason}
                      </span>
                    </p>
                  )}
                </article>
              ))}
            </div>
            <p className="text-xs text-zinc-400 v2-num">
              commit {data.git_sha.slice(0, 12)} · generated {data.generated_at}
            </p>
          </>
        )}
      </div>
    </section>
  );
}
