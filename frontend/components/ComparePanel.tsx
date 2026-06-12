"use client";
import { useState, useRef } from "react";
import { SplitSquareHorizontal, X, TrendingUp, Upload } from "lucide-react";
import dynamic from "next/dynamic";
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const DARK = {
  paper_bgcolor: "transparent", plot_bgcolor: "transparent",
  font: { color: "#555", size: 10 },
  xaxis: { color: "#444", gridcolor: "#1a1a1a", zerolinecolor: "#2a2a2a" },
  yaxis: { color: "#444", gridcolor: "#1a1a1a", zerolinecolor: "#2a2a2a" },
  legend: { font: { color: "#666", size: 9 }, bgcolor: "rgba(0,0,0,0)" },
  margin: { l: 48, r: 12, t: 30, b: 40 },
  autosize: true,
};

interface SimResult {
  time: number[];
  z_s: number[];
  z_u: number[];
  ddz_s: number[];
  susp_travel: number[];
  freq_hz: number[];
  transmissibility_body: number[];
  rms_body_accel: number;
  peak_transmissibility: number;
  peak_susp_travel: number;
  f_n_s: number;
  zeta_s: number;
  [key: string]: unknown;
}

interface ComparePanelProps {
  current: SimResult | null;
}

export default function ComparePanel({ current }: ComparePanelProps) {
  const [baseline, setBaseline] = useState<SimResult | null>(null);
  const [open,     setOpen]     = useState(false);

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-[#141416] border border-[#252525]
          hover:bg-[#1e1e20] rounded-lg text-xs font-medium transition-colors">
        <SplitSquareHorizontal size={13} className="text-[#0af]" /> Compare
      </button>
    );
  }

  const delta = (key: keyof SimResult, label: string, unit = "") => {
    if (!baseline || !current) return null;
    const bv = baseline[key] as number;
    const cv = current[key] as number;
    if (typeof bv !== "number" || typeof cv !== "number") return null;
    const diff = cv - bv;
    const pct  = bv !== 0 ? ((diff / Math.abs(bv)) * 100) : 0;
    const better = diff < 0; // lower = better for all our metrics
    return (
      <div className="flex justify-between items-center py-1.5 border-b border-[#1a1a1a]">
        <span className="text-[10px] text-gray-600">{label}</span>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-gray-500">{bv.toFixed(3)}</span>
          <span className="text-[9px] text-gray-700">→</span>
          <span className="text-[10px] font-mono text-white">{cv.toFixed(3)}</span>
          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
            better ? "bg-emerald-950 text-emerald-400" : "bg-red-950 text-red-400"
          }`}>
            {diff >= 0 ? "+" : ""}{pct.toFixed(1)}%{unit}
          </span>
        </div>
      </div>
    );
  };

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-[440px] bg-[#0a0a0c] border-l border-[#1e1e1e]
      flex flex-col shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-[#1e1e1e] shrink-0">
        <div className="flex items-center gap-2">
          <SplitSquareHorizontal size={14} className="text-[#0af]" />
          <span className="text-sm font-semibold text-white">Comparison Mode</span>
        </div>
        <button onClick={() => setOpen(false)} className="text-gray-600 hover:text-white transition-colors">
          <X size={14} />
        </button>
      </div>

      {/* Set Baseline */}
      <div className="px-5 py-3 border-b border-[#1e1e1e] shrink-0">
        {!baseline ? (
          <div className="text-center py-2">
            <p className="text-xs text-gray-600 mb-2">Run a simulation first, then pin it as the baseline.</p>
            <button onClick={() => current && setBaseline(current)}
              disabled={!current}
              className="px-4 py-1.5 bg-[#0af]/10 border border-[#0af]/20 text-[#0af] text-xs font-bold
                rounded-lg hover:bg-[#0af]/20 transition-colors disabled:opacity-40">
              📌 Pin Current as Baseline
            </button>
            <p className="text-[10px] text-gray-500 my-3">— OR —</p>
            <label className="px-4 py-1.5 bg-[#141416] border border-[#252525] text-gray-300 text-xs font-bold
                rounded-lg hover:bg-[#1e1e20] transition-colors cursor-pointer inline-flex items-center gap-1.5">
              <Upload size={13} /> Import CSV Telemetry
              <input type="file" accept=".csv" className="hidden" onChange={(e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                const reader = new FileReader();
                reader.onload = (event) => {
                  const text = event.target?.result as string;
                  const lines = text.split('\n');
                  const time: number[] = [], ddz_s: number[] = [], freq_hz: number[] = [], tx: number[] = [];
                  lines.forEach((line, i) => {
                    if (i === 0) return;
                    const parts = line.split(',');
                    if (parts.length >= 2) {
                      time.push(parseFloat(parts[0]));
                      ddz_s.push(parseFloat(parts[1] || "0"));
                      if (parts[2] && parts[3]) {
                        freq_hz.push(parseFloat(parts[2]));
                        tx.push(parseFloat(parts[3]));
                      }
                    }
                  });
                  setBaseline({
                    time, ddz_s, freq_hz, transmissibility_body: tx,
                    z_s: [], z_u: [], susp_travel: [], rms_body_accel: 0, peak_transmissibility: 0, peak_susp_travel: 0, f_n_s: 0, zeta_s: 0,
                    is_telemetry: true
                  });
                };
                reader.readAsText(file);
              }} />
            </label>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <div>
              <span className="text-[9px] font-bold text-gray-700 uppercase tracking-wider">
                {baseline.is_telemetry ? "Real-World Telemetry" : "Baseline pinned"}
              </span>
              <p className="text-xs text-gray-400">
                {baseline.is_telemetry ? `${baseline.time.length} data points` : `ƒₙ = ${baseline.f_n_s.toFixed(3)} Hz · ζ = ${baseline.zeta_s.toFixed(3)}`}
              </p>
            </div>
            <button onClick={() => setBaseline(null)}
              className="text-[10px] text-gray-600 hover:text-red-400 transition-colors">
              Clear
            </button>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar px-5 py-4 space-y-5">
        {/* Delta metrics (hide if telemetry since we lack full metrics) */}
        {baseline && current && !baseline.is_telemetry && (
          <div>
            <h3 className="text-[9px] font-bold text-gray-700 uppercase tracking-widest mb-2">
              Δ Performance Delta
            </h3>
            {delta("rms_body_accel",       "Body Accel RMS",  " m/s²")}
            {delta("peak_transmissibility","Peak TX",         "×")}
            {delta("peak_susp_travel",     "Peak Travel",     " m")}
            {delta("f_n_s",                "Sprung Freq",     " Hz")}
            {delta("zeta_s",               "Damping Ratio",   "")}
          </div>
        )}

        {/* Overlay plot — transmissibility */}
        {baseline && current && (
          <div>
            <h3 className="text-[9px] font-bold text-gray-700 uppercase tracking-widest mb-2">
              Transmissibility Overlay
            </h3>
            <div className="h-[200px] bg-black/40 rounded-xl border border-[#1a1a1a]">
              <Plot
                data={[
                  { x: baseline.freq_hz, y: baseline.transmissibility_body,
                    type: "scatter", mode: "lines", name: "Baseline",
                    line: { color: "#555", width: 1.5, dash: "dash" } },
                  { x: current.freq_hz,  y: current.transmissibility_body,
                    type: "scatter", mode: "lines", name: "Current",
                    line: { color: "#f2a900", width: 2 } },
                ]}
                layout={{
                  ...DARK,
                  title: { text: "", },
                  xaxis: { ...DARK.xaxis, title: { text: "Hz" }, type: "log" },
                  yaxis: { ...DARK.yaxis, title: { text: "TX" } },
                }}
                useResizeHandler style={{ width: "100%", height: "100%" }}
                config={{ displayModeBar: false, responsive: true }}
              />
            </div>
          </div>
        )}

        {/* Overlay plot — acceleration */}
        {baseline && current && (
          <div>
            <h3 className="text-[9px] font-bold text-gray-700 uppercase tracking-widest mb-2">
              Body Acceleration Overlay
            </h3>
            <div className="h-[200px] bg-black/40 rounded-xl border border-[#1a1a1a]">
              <Plot
                data={[
                  { x: baseline.time, y: baseline.ddz_s,
                    type: "scatter", mode: "lines", name: "Baseline",
                    line: { color: "#555", width: 1.5, dash: "dash" } },
                  { x: current.time,  y: current.ddz_s,
                    type: "scatter", mode: "lines", name: "Current",
                    line: { color: "#ff2d55", width: 1.5 } },
                ]}
                layout={{
                  ...DARK,
                  xaxis: { ...DARK.xaxis, title: { text: "Time (s)" } },
                  yaxis: { ...DARK.yaxis, title: { text: "m/s²" } },
                }}
                useResizeHandler style={{ width: "100%", height: "100%" }}
                config={{ displayModeBar: false, responsive: true }}
              />
            </div>
          </div>
        )}

        {!baseline && (
          <div className="flex flex-col items-center justify-center py-12 gap-3 opacity-40">
            <TrendingUp size={40} strokeWidth={1} className="text-gray-600" />
            <p className="text-xs text-gray-600 text-center">Pin a baseline run to see side-by-side comparison</p>
          </div>
        )}
      </div>
    </div>
  );
}
