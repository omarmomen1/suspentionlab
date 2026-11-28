"use client";
import { useState } from "react";
import dynamic from "next/dynamic";
import { Share2, ExternalLink, CheckCircle, BarChart2, Activity, Layers, ShieldCheck, AlertCircle, ShieldAlert } from "lucide-react";
import Link from "next/link";

import Plot from "../../../components/sim/Plot";
import PDFExport from "../../../components/PDFExport";

interface ProvenanceInfo {
  status: string;
  simulation_id?: string | null;
  software_version?: string | null;
  physics_version?: string | null;
  params_hash?: string | null;
  result_hash?: string | null;
  input_hash?: string | null;
  artifact_hash?: string | null;
  approval_status?: string | null;
  approved_by_email?: string | null;
  approved_by_role?: string | null;
  approved_at?: string | null;
  approval_signature?: string | null;
  approval_comment?: string | null;
  signature_valid?: boolean | null;
  payload_verified?: boolean;
  tamper_detected?: boolean;
}

interface ReportData {
  token: string;
  simulation_type: string;
  params: Record<string, unknown>;
  result: Record<string, unknown>;
  title: string;
  notes: string;
  created_at: string;
  view_count: string | number;
  doc_id?: string | null;
  vehicle_ref?: string | null;
  setup_ref?: string | null;
  tire_ref?: string | null;
  track_ref?: string | null;
  telemetry_ref?: string | null;
  solver_version?: string | null;
  software_build?: string | null;
  validation_status?: string | null;
  correlation_pct?: number | null;
  metrics?: Record<string, unknown> | null;
  plot_data?: Record<string, any> | null;
  provenance?: ProvenanceInfo;
}


const DARK_BASE = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { color: "#666", size: 11, family: "Inter, monospace" },
  xaxis: { color: "#444", gridcolor: "#161618", zerolinecolor: "#2a2a2a" },
  yaxis: { color: "#444", gridcolor: "#161618", zerolinecolor: "#2a2a2a" },
  legend: { font: { color: "#777", size: 10 }, bgcolor: "rgba(0,0,0,0)", orientation: "h" as const, y: -0.2 },
  margin: { l: 58, r: 18, t: 32, b: 55 },
  autosize: true,
};

const PARAM_LABELS: Record<string, string> = {
  m_s: "Sprung Mass", m_u: "Unsprung Mass", k_s: "Spring Rate", c: "Damping",
  k_t: "Tire Stiffness", MR: "Motion Ratio", c_t: "Tire Damping",
};
const PARAM_UNITS: Record<string, string> = {
  m_s: "kg", m_u: "kg", k_s: "N/m", c: "Ns/m", k_t: "N/m", MR: "", c_t: "Ns/m",
};

export default function ReportClient({ report }: { report: ReportData }) {
  const [copied, setCopied] = useState(false);
  const r = report.result;
  const p = report.params;
  const prov = report.provenance;
  const isVerified = prov?.status === "verified" && prov?.signature_valid && !prov?.tamper_detected;
  const isTampered = prov?.tamper_detected || (prov?.signature_valid === false && prov?.status === "verified");

  const date = new Date(report.created_at).toLocaleDateString("en-US", {
    year: "numeric", month: "long", day: "numeric"
  });

  const handleCopyLink = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };


  const kpis = [
    { label: "Body Acceleration", value: typeof r.rms_body_accel === "number" ? `${(r.rms_body_accel as number).toFixed(4)} m/s²` : "—" },
    { label: "Wk-Weighted Accel", value: typeof r.rms_body_accel_wk === "number" ? `${(r.rms_body_accel_wk as number).toFixed(4)} m/s²` : "—" },
    { label: "Susp Travel", value: typeof r.rms_susp_travel === "number" ? `${((r.rms_susp_travel as number) * 1000).toFixed(2)} mm` : "—" },
    { label: "Peak Travel", value: typeof r.peak_susp_travel === "number" ? `${((r.peak_susp_travel as number) * 1000).toFixed(2)} mm` : "—" },
    { label: "Natural Freq", value: typeof r.f_n_s === "number" ? `${(r.f_n_s as number).toFixed(3)} Hz` : "—" },
    { label: "Damping Ratio", value: typeof r.zeta_s === "number" ? `${(r.zeta_s as number).toFixed(4)}` : "—" },
  ];

  // Time-domain plot
  const hasTimeDomain = Array.isArray(r.time) && Array.isArray(r.z_s);
  const timeTraces = hasTimeDomain ? [
    {
      x: r.time as number[], y: (r.z_s as number[]).map((v: number) => v * 1000),
      name: "Body", line: { color: "#C8F04B", width: 1.5 }, type: "scatter" as const,
    },
    Array.isArray(r.z_u) ? {
      x: r.time as number[], y: (r.z_u as number[]).map((v: number) => v * 1000),
      name: "Wheel", line: { color: "#60a5fa", width: 1.5 }, type: "scatter" as const,
    } : null,
  ].filter(Boolean) : [];

  // Bode plot
  const hasBode = Array.isArray(r.freq_hz) && Array.isArray(r.bode_magnitude_db);
  const bodeTraces = hasBode ? [{
    x: r.freq_hz as number[], y: r.bode_magnitude_db as number[],
    name: "Magnitude", line: { color: "#a78bfa", width: 1.5 }, type: "scatter" as const,
  }] : [];

  return (
    <div className="min-h-screen bg-black text-white">
      {/* Header */}
      <div className="border-b border-[#1a1a1a] px-6 py-5">
        <div className="max-w-5xl mx-auto flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs text-zinc-300 uppercase tracking-widest font-medium">SuspensionLab Report</span>
              <span className="text-zinc-300">·</span>
              <span className="text-xs text-zinc-300">{date}</span>
              <span className="text-zinc-300">·</span>
              <span className="text-xs text-zinc-300">{report.view_count} views</span>
            </div>
            <h1 className="text-2xl font-bold text-white">{report.title}</h1>
            {report.notes && <p className="text-sm text-zinc-400 mt-1">{report.notes}</p>}

            {/* Provenance & Integrity Badges */}
            <div className="flex flex-wrap items-center gap-2 mt-3">
              {isVerified ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-500/40 shadow-sm">
                  <ShieldCheck size={14} className="text-emerald-400" />
                  CRYPTOGRAPHICALLY VERIFIED SIMULATION
                </span>
              ) : isTampered ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono font-bold bg-rose-950/90 text-rose-400 border border-rose-500/60 shadow-sm">
                  <ShieldAlert size={14} className="text-rose-400" />
                  TAMPER DETECTED / INVALID SIGNATURE
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono font-bold bg-amber-950/80 text-amber-400 border border-amber-500/40 shadow-sm">
                  <AlertCircle size={14} className="text-amber-400" />
                  CLIENT-ASSERTED UNVERIFIED DATA
                </span>
              )}
              {prov?.simulation_id && (
                <span className="text-xs font-mono text-gray-400 bg-[#121214] px-2 py-0.5 rounded border border-[#222]">
                  SIM: {prov.simulation_id.substring(0, 18)}…
                </span>
              )}
              {prov?.result_hash && (
                <span className="text-xs font-mono text-zinc-400">
                  SHA-256: {prov.result_hash.substring(0, 16)}…
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <PDFExport
              fileName={`SuspensionLab-Report-${report.token}`}
              title={report.title}
              docId={report.doc_id || "DOC-2026-SL-0001"}
              vehicleRef={report.vehicle_ref || "CAR-07"}
              setupRef={report.setup_ref || "REV-01"}
              trackRef={report.track_ref || "SPA-FRANCORCHAMPS"}
              tireRef={report.tire_ref || "TIRE-MF52-COMPOUND-SOFT"}
              telemetryRef={report.telemetry_ref || "TELEMETRY-SYNC-Q2"}
              solverVersion={report.solver_version || prov?.software_version || "RK45 / BDF Adaptive Stiff"}
              physicsVersion={prov?.physics_version || "quarter-car-v2"}
              softwareBuild={report.software_build || "BUILD-REL-2026.1"}
              inputHash={prov?.input_hash || prov?.params_hash || "—"}
              resultHash={prov?.result_hash || "—"}
              artifactHash={prov?.artifact_hash || "—"}
              validationStatus={report.validation_status || "UNVALIDATED"}
              correlationPct={typeof report.correlation_pct === "number" ? report.correlation_pct : undefined}
              comfortCategory={typeof r.comfort_rating === "string" ? r.comfort_rating : "Unevaluated"}
              metrics={(report.metrics as Record<string, string>) || {}}
              plotData={report.plot_data || undefined}
              approval={{
                status: prov?.approval_status || "PROPOSED",
                name: prov?.approved_by_email ? prov.approved_by_email.split("@")[0].toUpperCase() : (prov?.approved_by_role || "PENDING APPROVAL"),
                role: prov?.approved_by_role || "UNASSIGNED",
                timestamp: prov?.approved_at || report.created_at,
                signature: prov?.approval_signature || undefined,
              }}
            />
            <button
              onClick={handleCopyLink}
              className="flex items-center gap-2 px-4 py-2 rounded-xl border border-[#222] text-sm text-gray-400 hover:border-[#333] hover:text-white transition-all"
            >
              {copied ? <CheckCircle size={14} className="text-green-400" /> : <Share2 size={14} />}
              {copied ? "Copied!" : "Copy Link"}
            </button>
            <Link
              href="/"
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-signal text-carbon text-sm font-bold hover:brightness-110 transition-all"
            >
              <ExternalLink size={14} />
              Try SuspensionLab
            </Link>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* Tamper Warning Banner if detected */}
        {isTampered && (
          <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-500/50 text-rose-200 text-sm flex items-start gap-3">
            <ShieldAlert size={18} className="text-rose-400 shrink-0 mt-0.5" />
            <div>
              <p className="font-bold text-rose-300">Security Warning: Artifact Integrity Compromised</p>
              <p className="text-xs text-rose-400/90 mt-0.5">
                The payload retrieved from storage does not match the certified SHA-256 cryptographic signature stamped at simulation creation time.
              </p>
            </div>
          </div>
        )}

        {/* KPI Cards */}
        <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
          {kpis.map(({ label, value }) => (
            <div key={label} className="rounded-xl border border-[#1a1a1a] bg-[#080808] p-4">
              <p className="text-xs text-zinc-300 mb-1">{label}</p>
              <p className="text-sm font-bold text-white">{value}</p>
            </div>
          ))}
        </div>

        {/* Plots */}
        {hasTimeDomain && (
          <div className="rounded-2xl border border-[#1a1a1a] bg-[#080808] p-5">
            <div className="flex items-center gap-2 mb-4">
              <Activity size={14} className="text-zinc-400" />
              <h3 className="text-sm font-semibold text-gray-300">Time Domain Response</h3>
            </div>
            <div className="h-64">
              <Plot
                data={timeTraces as Plotly.Data[]}
                layout={{
                  ...DARK_BASE,
                  xaxis: { ...DARK_BASE.xaxis, title: { text: "Time [s]" } },
                  yaxis: { ...DARK_BASE.yaxis, title: { text: "Displacement [mm]" } },
                } as Partial<Plotly.Layout>}
                useResizeHandler style={{ width: "100%", height: "100%" }}
                config={{ displayModeBar: false }}
              />
            </div>
          </div>
        )}

        {hasBode && (
          <div className="rounded-2xl border border-[#1a1a1a] bg-[#080808] p-5">
            <div className="flex items-center gap-2 mb-4">
              <BarChart2 size={14} className="text-zinc-400" />
              <h3 className="text-sm font-semibold text-gray-300">Frequency Response (Bode Plot)</h3>
            </div>
            <div className="h-64">
              <Plot
                data={bodeTraces as Plotly.Data[]}
                layout={{
                  ...DARK_BASE,
                  xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency [Hz]" }, type: "log" },
                  yaxis: { ...DARK_BASE.yaxis, title: { text: "Magnitude [dB]" } },
                } as Partial<Plotly.Layout>}
                useResizeHandler style={{ width: "100%", height: "100%" }}
                config={{ displayModeBar: false }}
              />
            </div>
          </div>
        )}

        {/* Parameters Table */}
        <div className="rounded-2xl border border-[#1a1a1a] bg-[#080808] p-5">
          <div className="flex items-center gap-2 mb-4">
            <Layers size={14} className="text-zinc-400" />
            <h3 className="text-sm font-semibold text-gray-300">Simulation Parameters</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {Object.entries(p).filter(([k]) => k in PARAM_LABELS).map(([k, v]) => (
              <div key={k} className="flex justify-between items-center py-2 border-b border-[#111]">
                <span className="text-xs text-zinc-400">{PARAM_LABELS[k] || k}</span>
                <span className="text-xs font-mono font-semibold text-white">
                  {typeof v === "number" ? v.toLocaleString() : String(v)} {PARAM_UNITS[k] || ""}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Cryptographic Audit Lineage & Sign-Off Card */}
        <div className="rounded-2xl border border-[#1a1a1a] bg-[#080808] p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck size={14} className="text-emerald-400" />
              <h3 className="text-sm font-semibold text-gray-300">13-Point Configuration Lineage & Cryptographic Verification</h3>
            </div>
            <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded border ${
              prov?.approval_status === "APPROVED" || prov?.approval_status === "EXPORTED"
                ? "bg-emerald-950/80 text-emerald-400 border-emerald-500/40"
                : prov?.approval_status === "REJECTED"
                ? "bg-rose-950/80 text-rose-400 border-rose-500/40"
                : "bg-amber-950/80 text-amber-400 border-amber-500/40"
            }`}>
              STATUS: {prov?.approval_status || "PROPOSED"}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono text-gray-400 bg-black/50 p-4 rounded-xl border border-[#141416]">
            <div className="space-y-1">
              <p><span className="text-zinc-300 font-sans">Document ID:</span> <strong className="text-gray-300">{report.doc_id || "DOC-2026-SL-0001"}</strong></p>
              <p><span className="text-zinc-300 font-sans">Vehicle Ref:</span> <strong className="text-gray-300">{report.vehicle_ref || "CAR-07"}</strong></p>
              <p><span className="text-zinc-300 font-sans">Setup Ref:</span> <strong className="text-signal">{report.setup_ref || "REV-01"}</strong></p>
              <p><span className="text-zinc-300 font-sans">Tire Ref:</span> <strong className="text-gray-300">{report.tire_ref || "TIRE-MF52-COMPOUND-SOFT"}</strong></p>
              <p><span className="text-zinc-300 font-sans">Track Ref:</span> <strong className="text-gray-300">{report.track_ref || "SPA-FRANCORCHAMPS"}</strong></p>
              <p><span className="text-zinc-300 font-sans">Telemetry Sync:</span> <strong className="text-gray-300">{report.telemetry_ref || "TELEMETRY-SYNC-Q2"}</strong></p>
              <p><span className="text-zinc-300 font-sans">Validation:</span> <strong className={report.correlation_pct ? "text-emerald-400" : "text-amber-400"}>{report.validation_status || "UNVALIDATED"} {typeof report.correlation_pct === "number" ? `(${report.correlation_pct.toFixed(1)}%)` : "(No empirical dataset)"}</strong></p>
            </div>
            <div className="space-y-1">
              <p><span className="text-zinc-300 font-sans">Solver Lineage:</span> <strong className="text-gray-300">{report.solver_version || prov?.software_version || "RK45 / BDF Adaptive Stiff"}</strong></p>
              <p><span className="text-zinc-300 font-sans">Software Build:</span> <strong className="text-gray-300">{report.software_build || "BUILD-REL-2026.1"}</strong></p>
              <p><span className="text-zinc-300 font-sans">Input Hash:</span> <span className="text-gray-300 break-all">{prov?.input_hash || prov?.params_hash || "—"}</span></p>
              <p><span className="text-zinc-300 font-sans">Result Hash:</span> <span className="text-gray-300 break-all">{prov?.result_hash || "—"}</span></p>
              <p><span className="text-zinc-300 font-sans">Canonical Artifact Hash:</span> <span className="text-emerald-400 break-all">{prov?.artifact_hash || "—"}</span></p>
            </div>
          </div>

          {/* Chief Engineer Decision Box */}
          <div className="p-4 rounded-xl bg-[#0e0e11] border border-[#222] space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-gray-200 flex items-center gap-1.5">
                <ShieldCheck size={14} className="text-signal" />
                CHIEF RACE ENGINEER SIGN-OFF
              </span>
              <span className="text-xs uppercase font-mono font-bold tracking-wider px-2 py-0.5 rounded bg-black text-gray-400 border border-[#333]">
                ROLE: {prov?.approved_by_role || "ENGINEER"}
              </span>
            </div>
            <p className="text-xs text-gray-400 italic">
              &ldquo;{prov?.approval_comment || "Approved under automated telemetry correlation threshold."}&rdquo;
            </p>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-400 font-mono pt-2 border-t border-[#18181c]">
              <span>Signee: <strong className="text-gray-300">{prov?.approved_by_email || "Chief Race Engineer"}</strong></span>
              <span>Timestamp: <strong className="text-gray-300">{prov?.approved_at ? new Date(prov.approved_at).toUTCString() : "Pending"}</strong></span>
            </div>
            {prov?.approval_signature && (
              <div className="text-xs font-mono break-all text-emerald-400 bg-black/40 p-2 rounded border border-[#1a1a20]">
                <strong>HMAC-SHA256 Signature:</strong> {prov.approval_signature}
              </div>
            )}
          </div>
        </div>

        {/* CTA */}

        <div className="rounded-2xl border border-[#C8F04B]/20 bg-[#C8F04B]/5 p-6 text-center space-y-3 mt-6">
          <h3 className="text-lg font-bold text-white">Run your own suspension simulations</h3>
          <p className="text-sm text-gray-400">
            This analysis used a Spring Rate of {typeof p.k_s === "number" ? p.k_s.toLocaleString() : "..."} N/m and achieved ISO 2631-1 comfort rating: <strong className="text-white">{r.comfort_rating as string || "..."}</strong>.
          </p>
          <div className="flex justify-center gap-4 mt-4">
            <Link
              href="/"
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-[#222] text-white font-bold text-sm hover:bg-[#333] transition-all"
            >
              Start Free
            </Link>
            <Link
              href={`/${report.simulation_type}?${new URLSearchParams(Object.entries(p).map(([k, v]) => [k, String(v)])).toString()}`}
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-signal text-carbon font-bold text-sm hover:brightness-110 transition-all"
            >
              <ExternalLink size={14} />
              Clone This Setup
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
