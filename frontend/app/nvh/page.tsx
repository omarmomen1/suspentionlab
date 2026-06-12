"use client";
import { useState, useMemo, Suspense } from "react";
import dynamic from "next/dynamic";
import { Settings2, Activity, Play, Waves, BarChart2 } from "lucide-react";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const DARK_BASE = {
  paper_bgcolor: "transparent",
  plot_bgcolor:  "transparent",
  font:          { color: "#666", size: 11, family: "Inter, monospace" },
  xaxis:         { color: "#444", gridcolor: "#161618", zerolinecolor: "#2a2a2a", tickfont: { color: "#555", size: 10 } },
  yaxis:         { color: "#444", gridcolor: "#161618", zerolinecolor: "#2a2a2a", tickfont: { color: "#555", size: 10 } },
  legend:        { font: { color: "#777", size: 10 }, bgcolor: "rgba(0,0,0,0)", orientation: "h" as const, y: -0.15 },
  margin:        { l: 58, r: 18, t: 32, b: 55 },
  autosize:      true,
  hoverlabel:    { bgcolor: "#0d0d0f", bordercolor: "#333", font: { color: "#ccc", size: 11 } },
};

function darkLayout(overrides: Record<string, unknown> = {}) {
  return { ...DARK_BASE, ...overrides };
}

type Status = "good" | "warn" | "bad" | "neutral";

function KPICard({ label, value, unit, sub, status = "neutral" }: { label: string; value: number | string; unit?: string; sub?: string; status?: Status; }) {
  const colours: Record<Status, string> = { good: "text-emerald-400", warn: "text-amber-400", bad: "text-red-400", neutral: "text-white" };
  const borders: Record<Status, string> = { good: "border-emerald-900/40 bg-emerald-950/10", warn: "border-amber-900/40 bg-amber-950/10", bad: "border-red-900/40 bg-red-950/10", neutral: "border-[#252525]" };
  return (
    <div className={`bg-[#141416] border ${borders[status]} rounded-xl p-3 flex flex-col gap-0.5`}>
      <span className="text-[9px] font-bold tracking-[0.16em] text-gray-600 uppercase">{label}</span>
      <span className={`text-[1.1rem] font-bold font-mono leading-tight ${colours[status]}`}>
        {typeof value === "number" ? value.toFixed(1) : value}
        {unit && <span className="text-[11px] font-normal text-gray-600 ml-1">{unit}</span>}
      </span>
      {sub && <span className="text-[9px] text-gray-700 leading-tight mt-0.5">{sub}</span>}
    </div>
  );
}

function ParamSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h3 className="text-[9px] font-bold text-gray-700 uppercase tracking-[0.16em] pb-1.5 border-b border-[#1e1e1e]">
        {title}
      </h3>
      {children}
    </div>
  );
}

function ParameterInput({ label, val, unit, step = 1, min, onChange }: { label: string; val: number; unit: string; step?: number; min?: number; onChange: (v: number) => void; }) {
  return (
    <div className="flex justify-between items-center gap-2">
      <label className="text-[11px] text-gray-500 flex-1 min-w-0 leading-tight">{label}</label>
      <div className="relative shrink-0">
        <input type="number" step={step} value={val} min={min} onChange={(e) => onChange(Number(e.target.value))}
          className="bg-[#0d0d0d] border border-[#252525] text-[11px] rounded-lg px-2 py-1.5 text-white w-28 text-right pr-9 focus:outline-none focus:border-ansys-yellow/60 focus:ring-1 focus:ring-ansys-yellow/15 transition-all"
        />
        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[9px] text-gray-700 pointer-events-none">{unit}</span>
      </div>
    </div>
  );
}

function PlotBox({ children }: { children: React.ReactNode }) {
  return <div className="flex-1 min-w-0 min-h-0 relative">{children}</div>;
}

function NVHDashboard() {
  const [params, setParams] = useState({
    m_s: 300.0,
    m_u: 35.0,
    k_s: 25000.0,
    c: 1500.0,
    k_t: 200000.0,
    bushing_stiffness: 1000000.0
  });

  const results = useMemo(() => {
    const freqs = Array.from({ length: 500 }, (_, i) => 0.1 + (i * 249.9) / 499);
    const tx_mag = new Float32Array(500);
    const a_weighted_db = new Float32Array(500);

    for (let i = 0; i < freqs.length; i++) {
      const f = freqs[i];
      const w = 2 * Math.PI * f;

      const z11_r = -params.m_s * w * w + params.k_s;
      const z11_i = w * params.c;

      const z12_r = -params.k_s;
      const z12_i = -w * params.c;

      const z22_r = -params.m_u * w * w + params.k_s + params.k_t + params.bushing_stiffness;
      const z22_i = w * params.c;

      const det_r = z11_r * z22_r - z11_i * z22_i - (z12_r * z12_r - z12_i * z12_i);
      const det_i = z11_r * z22_i + z11_i * z22_r - (z12_r * z12_i + z12_i * z12_r);
      const abs_det = Math.sqrt(det_r * det_r + det_i * det_i);

      let tx = 0;
      if (abs_det > 1e-10) {
        const coef = (params.k_t * params.bushing_stiffness) / (params.k_t + params.bushing_stiffness);
        const num_r = coef * z12_r;
        const num_i = coef * z12_i;
        const abs_num = Math.sqrt(num_r * num_r + num_i * num_i);
        tx = abs_num / abs_det;
      }

      tx_mag[i] = tx;

      const f2 = f * f;
      const r_a = (148693636 * f2 * f2) / ((f2 + 424.36) * Math.sqrt((f2 + 11599.29) * (f2 + 544496.41)) * (f2 + 148693636));
      const a_weight = r_a > 0 ? 20 * Math.log10(r_a) + 2.0 : -100;
      const db = 20 * Math.log10(Math.max(tx, 1e-6));
      a_weighted_db[i] = db + a_weight;
    }

    let max_boom = -Infinity;
    let max_roar = -Infinity;
    for (let i = 0; i < freqs.length; i++) {
      if (freqs[i] >= 30 && freqs[i] <= 50) max_boom = Math.max(max_boom, a_weighted_db[i]);
      if (freqs[i] >= 100 && freqs[i] <= 200) max_roar = Math.max(max_roar, a_weighted_db[i]);
    }

    return { freqs, tx_mag, a_weighted_db, max_boom, max_roar };
  }, [params]);

  return (
    <div className="h-full flex flex-col p-5 pt-3 gap-3 min-h-0">
      <div className="flex items-center justify-between shrink-0 pb-3 border-b border-[#1e1e1e]">
        <div className="flex flex-col">
          <span className="text-[9px] font-bold tracking-[0.25em] text-ansys-yellow uppercase">High-Frequency Analyzer (0-250 Hz)</span>
          <h1 className="text-2xl font-semibold tracking-tight text-white leading-tight">Acoustic NVH</h1>
        </div>
      </div>

      <div className="flex flex-1 gap-4 overflow-hidden min-h-0">
        <div className="w-60 shrink-0 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-y-auto custom-scrollbar">
          <div className="px-4 py-3 border-b border-[#1e1e1e] sticky top-0 bg-[#0d0d0f] z-10"><h2 className="text-xs font-semibold text-gray-300 flex items-center gap-2"><Settings2 size={13} className="text-ansys-yellow" /> Parameters</h2></div>
          <div className="p-4 space-y-5">
            <ParamSection title="Mass & Stiffness">
              <ParameterInput label="Sprung Mass" val={params.m_s} unit="kg" onChange={(v) => setParams({ ...params, m_s: v })} />
              <ParameterInput label="Unsprung Mass" val={params.m_u} unit="kg" onChange={(v) => setParams({ ...params, m_u: v })} />
              <ParameterInput label="Spring Rate" val={params.k_s} unit="N/m" step={500} onChange={(v) => setParams({ ...params, k_s: v })} />
              <ParameterInput label="Damping" val={params.c} unit="Ns/m" step={50} onChange={(v) => setParams({ ...params, c: v })} />
              <ParameterInput label="Tire Stiffness" val={params.k_t} unit="N/m" step={10000} onChange={(v) => setParams({ ...params, k_t: v })} />
            </ParamSection>
            <ParamSection title="Elastokinematics">
              <ParameterInput label="Bushing Stiffness" val={params.bushing_stiffness} unit="N/m" step={100000} onChange={(v) => setParams({ ...params, bushing_stiffness: v })} />
            </ParamSection>
          </div>
        </div>

        <div className="flex-1 flex flex-col gap-3 min-w-0 overflow-hidden">
          <div className="grid grid-cols-4 gap-2 shrink-0">
            <KPICard label="Peak Cabin Boom" value={results.max_boom} unit="dBA" sub="30-50 Hz Region" status={results.max_boom > 40 ? "warn" : "good"} />
            <KPICard label="Peak Cavity Roar" value={results.max_roar} unit="dBA" sub="100-200 Hz Region" status={results.max_roar > 45 ? "warn" : "good"} />
          </div>

          <div className="flex gap-1.5 shrink-0">
            <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-ansys-yellow text-black shadow-[0_0_12px_rgba(242,169,0,0.2)]">
              <Waves size={12} /> Spectrogram
            </button>
          </div>

          <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-hidden min-h-0">
            <div className="grid grid-cols-1 grid-rows-1 h-full gap-px bg-[#181818]">
              <PlotBox>
                <Plot
                  data={[
                    { x: Array.from(results.freqs), y: Array.from(results.tx_mag), type: "scatter", mode: "lines", name: "Structural Transmissibility", line: { color: "#00aeff", width: 2 } },
                    { x: Array.from(results.freqs), y: Array.from(results.a_weighted_db), type: "scatter", mode: "lines", name: "Acoustic Response (dBA)", yaxis: "y2", line: { color: "#ff2d55", width: 2 } }
                  ]}
                  layout={darkLayout({
                    title: { text: "High-Frequency NVH Spectrogram (0 - 250 Hz)", font: { color: "#888", size: 11 } },
                    xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#444", size: 10 } } },
                    yaxis: { ...DARK_BASE.yaxis, title: { text: "Transmissibility (m/m)", font: { color: "#444", size: 10 } }, type: "log", color: "#00aeff" },
                    yaxis2: { title: { text: "Acoustic Noise (dBA)", font: { color: "#444", size: 10 } }, overlaying: "y", side: "right", color: "#ff2d55", showgrid: false },
                    shapes: [
                      { type: "rect", xref: "x", yref: "paper", x0: 30, x1: 50, y0: 0, y1: 1, fillcolor: "rgba(242,169,0,0.08)", line: { width: 0 }, layer: "below" },
                      { type: "rect", xref: "x", yref: "paper", x0: 100, x1: 200, y0: 0, y1: 1, fillcolor: "rgba(0,174,255,0.08)", line: { width: 0 }, layer: "below" }
                    ],
                    annotations: [
                      { x: 40, y: 0.95, xref: "x", yref: "paper", text: "Booming (30-50Hz)", showarrow: false, font: { color: "rgba(242,169,0,0.8)", size: 10 } },
                      { x: 150, y: 0.95, xref: "x", yref: "paper", text: "Cavity Resonance (100-200Hz)", showarrow: false, font: { color: "rgba(0,174,255,0.8)", size: 10 } }
                    ]
                  })}
                  useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: false }}
                />
              </PlotBox>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div className="h-full flex items-center justify-center text-gray-600 text-sm">Loading environment…</div>}>
      <NVHDashboard />
    </Suspense>
  );
}
