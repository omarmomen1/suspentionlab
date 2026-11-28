"use client";
import { useState } from "react";
import { FileText, Loader2, FileDown } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import PDFExport from "./PDFExport";

/**
 * Dyno Day in a Box (Tier A2).
 *
 * Pulls the chief-engineer report for a calibrated Digital Twin — identified
 * ride frequency & damping, confidence, model-validity assessment, and a
 * SHA-256 provenance hash — and renders it as a printable panel that
 * PDFExport captures into a branded, hand-to-your-race-director document.
 */

interface TwinReport {
  twin: {
    id: string; car_ref: string; setup_ref: string;
    track_ref: string | null; calibration_count: number;
    last_calibration_at: string | null;
  };
  identification: {
    sprung_freq_hz: number | null;
    damping_ratio: number | null;
    confidence: number | null;
  };
  parameters: { base: Record<string, unknown>; calibrated: Record<string, unknown> };
  validity: { summary?: string; score?: number; checks?: { name: string; status: string }[] };
  generated_at: string;
  provenance: { algorithm: string; hash: string; note: string };
}

export default function DynoDayReport() {
  const { fetchWithAuth } = useAuth();
  const [twinId, setTwinId] = useState("");
  const [report, setReport] = useState<TwinReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = async () => {
    if (!twinId.trim()) return;
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const res = await fetchWithAuth(`/api/v1/twins/${twinId.trim()}/report`);
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        throw new Error(body || `Report request failed (${res.status})`);
      }
      setReport((await res.json()) as TwinReport);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate report");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex items-center gap-2">
        <input
          value={twinId}
          onChange={(e) => setTwinId(e.target.value)}
          placeholder="Twin ID (from POST /twins)"
          aria-label="Digital Twin ID"
          className="flex-1 bg-slate-900/60 border border-slate-800 rounded-lg px-3 py-2 text-sm
            text-slate-200 placeholder-slate-600 focus:outline-none focus:border-amber-500/50"
        />
        <button
          onClick={generate}
          disabled={!twinId.trim() || loading}
          className="flex items-center space-x-2 border border-amber-600/40 text-amber-500
            hover:bg-signal/10 px-4 py-2 rounded-lg text-sm font-medium transition-all
            disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
          <span>Dyno Day Report</span>
        </button>
      </div>
      {error && (
        <div className="flex items-center space-x-2 text-red-400 text-sm bg-red-400/10 px-4 py-2 rounded-md">
          <span>{error}</span>
        </div>
      )}

      {/* Printable report panel */}
      {report && (
        <div className="space-y-3">
          <div id="dyno-report" className="rounded-xl border border-slate-800 bg-[#0d0d0f] p-6 space-y-5">
            <header className="flex items-start justify-between border-b border-slate-800 pb-4">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-amber-500 font-bold">SuspensionLab Pro</p>
                <h3 className="text-lg font-bold text-white mt-1">Dyno Day Report</h3>
                <p className="text-xs text-zinc-400 mt-0.5">
                  {report.twin.car_ref} · {report.twin.setup_ref}
                  {report.twin.track_ref ? ` · ${report.twin.track_ref}` : ""}
                </p>
              </div>
              <div className="text-right text-xs text-zinc-300">
                <p>{new Date(report.generated_at).toLocaleString()}</p>
                <p>Calibrations: {report.twin.calibration_count}</p>
              </div>
            </header>

            <section className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {[
                { label: "Sprung ride frequency", value: report.identification.sprung_freq_hz != null ? `${report.identification.sprung_freq_hz.toFixed(3)} Hz` : "—" },
                { label: "Damping ratio ζ", value: report.identification.damping_ratio != null ? report.identification.damping_ratio.toFixed(3) : "—" },
                { label: "Identification confidence", value: report.identification.confidence != null ? `${Math.round(report.identification.confidence * 100)}%` : "—" },
              ].map((kpi) => (
                <div key={kpi.label} className="rounded-lg border border-slate-800 bg-slate-900/30 p-3">
                  <p className="text-xs uppercase tracking-wider text-zinc-400">{kpi.label}</p>
                  <p className="text-xl font-bold text-white mt-1">{kpi.value}</p>
                </div>
              ))}
            </section>

            {report.validity?.summary && (
              <section>
                <p className="text-xs uppercase tracking-wider text-zinc-400 mb-1">Model validity</p>
                <p className="text-xs text-slate-300">{report.validity.summary}</p>
              </section>
            )}

            <section>
              <p className="text-xs uppercase tracking-wider text-zinc-400 mb-1">Provenance</p>
              <p className="text-xs font-sans leading-relaxed text-slate-400 break-all">
                {report.provenance.algorithm}: {report.provenance.hash}
              </p>
            </section>
          </div>

          <PDFExport
            captureId="dyno-report"
            fileName={`dyno-day-${report.twin.car_ref}-${report.twin.setup_ref}`}
            title={`Dyno Day Report — ${report.twin.car_ref}`}
          />
        </div>
      )}
    </div>
  );
}
