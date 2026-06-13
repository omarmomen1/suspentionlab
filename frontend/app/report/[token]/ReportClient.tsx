"use client";
import { useState } from "react";
import dynamic from "next/dynamic";
import { Share2, ExternalLink, CheckCircle, BarChart2, Activity, Layers } from "lucide-react";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface ReportData {
  token: string;
  simulation_type: string;
  params: Record<string, unknown>;
  result: Record<string, unknown>;
  title: string;
  notes: string;
  created_at: string;
  view_count: string;
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
      name: "Body", line: { color: "#f2a900", width: 1.5 }, type: "scatter" as const,
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
              <span className="text-[11px] text-gray-600 uppercase tracking-widest font-medium">SuspensionLab Report</span>
              <span className="text-gray-700">·</span>
              <span className="text-[11px] text-gray-600">{date}</span>
              <span className="text-gray-700">·</span>
              <span className="text-[11px] text-gray-600">{report.view_count} views</span>
            </div>
            <h1 className="text-2xl font-bold text-white">{report.title}</h1>
            {report.notes && <p className="text-sm text-gray-500 mt-1">{report.notes}</p>}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={handleCopyLink}
              className="flex items-center gap-2 px-4 py-2 rounded-xl border border-[#222] text-sm text-gray-400 hover:border-[#333] hover:text-white transition-all"
            >
              {copied ? <CheckCircle size={14} className="text-green-400" /> : <Share2 size={14} />}
              {copied ? "Copied!" : "Copy Link"}
            </button>
            <a
              href="/"
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-[#f2a900] text-black text-sm font-bold hover:brightness-110 transition-all"
            >
              <ExternalLink size={14} />
              Try SuspensionLab
            </a>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {/* KPI Cards */}
        <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
          {kpis.map(({ label, value }) => (
            <div key={label} className="rounded-xl border border-[#1a1a1a] bg-[#080808] p-4">
              <p className="text-[10px] text-gray-600 mb-1">{label}</p>
              <p className="text-sm font-bold text-white">{value}</p>
            </div>
          ))}
        </div>

        {/* Plots */}
        {hasTimeDomain && (
          <div className="rounded-2xl border border-[#1a1a1a] bg-[#080808] p-5">
            <div className="flex items-center gap-2 mb-4">
              <Activity size={14} className="text-gray-500" />
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
              <BarChart2 size={14} className="text-gray-500" />
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
            <Layers size={14} className="text-gray-500" />
            <h3 className="text-sm font-semibold text-gray-300">Simulation Parameters</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {Object.entries(p).filter(([k]) => k in PARAM_LABELS).map(([k, v]) => (
              <div key={k} className="flex justify-between items-center py-2 border-b border-[#111]">
                <span className="text-xs text-gray-500">{PARAM_LABELS[k] || k}</span>
                <span className="text-xs font-mono font-semibold text-white">
                  {typeof v === "number" ? v.toLocaleString() : String(v)} {PARAM_UNITS[k] || ""}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* CTA */}
        <div className="rounded-2xl border border-[#f2a900]/20 bg-[#f2a900]/5 p-6 text-center space-y-3">
          <h3 className="text-lg font-bold text-white">Run your own suspension simulations</h3>
          <p className="text-sm text-gray-400">SuspensionLab — Professional vehicle dynamics simulation in your browser. No MATLAB required.</p>
          <a
            href="/"
            className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl bg-[#f2a900] text-black font-bold text-sm hover:brightness-110 transition-all"
          >
            <ExternalLink size={14} />
            Start Free at SuspensionLab
          </a>
        </div>
      </div>
    </div>
  );
}
