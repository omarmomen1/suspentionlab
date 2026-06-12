"use client";
import { useState, Suspense } from "react";
import dynamic from "next/dynamic";
import { Play, Settings2, AlertTriangle, Activity, Save, X, Activity as Pulse, Zap } from "lucide-react";
const PDFExport = dynamic(() => import("../../components/PDFExport"), { ssr: false });
import DataExport from "../../components/DataExport";
import { useAuth } from "../../contexts/AuthContext";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
        {typeof value === "number" ? value.toFixed(3) : value}
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

function ActiveSuspensionDashboard() {
  const { authHeader } = useAuth();
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState<Record<string, any> | null>(null);

  const [params, setParams] = useState({
    c_sky: 4000.0,
    c_min: 500.0,
    m_s: 300.0,
    m_u: 35.0,
    k_s: 25000.0,
    k_t: 200000.0,
    MR: 0.85,
    bump_height: 0.05
  });

  const runSimulation = async () => {
    setIsRunning(true); setResults(null);
    try {
      const payload = {
        params: { m_s: params.m_s, m_u: params.m_u, k_s: params.k_s, k_t: params.k_t, MR: params.MR, c_sky: params.c_sky, c_min: params.c_min },
        bump_height: params.bump_height
      };
      const res = await fetch(`${API_BASE}/simulate/active`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeader() }, body: JSON.stringify(payload) });
      const data = await res.json();
      if (!res.ok) setResults({ error: true, message: data.message ?? data.detail ?? "Simulation failed" });
      else setResults(data);
    } catch (err) { setResults({ error: true, message: String(err) }); }
    finally { setIsRunning(false); }
  };

  let comfort_improvement = 0;
  if (results && !results.error) {
    comfort_improvement = ((results.passive_rms_accel - results.active_rms_accel) / Math.max(results.passive_rms_accel, 1e-6)) * 100;
  }

  const hasResults = results && !results.error;
  const r = results;

  return (
    <div className="h-full flex flex-col p-5 pt-3 gap-3 min-h-0">
      <div className="flex items-center justify-between shrink-0 pb-3 border-b border-[#1e1e1e]">
        <div className="flex flex-col">
          <span className="text-[9px] font-bold tracking-[0.25em] text-ansys-yellow uppercase">Semi-Active Skyhook Control Strategy</span>
          <h1 className="text-2xl font-semibold tracking-tight text-white leading-tight">Active Suspension</h1>
        </div>

        <div className="flex items-center gap-2">
          <button onClick={runSimulation} disabled={isRunning}
            className={`px-5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${isRunning ? "bg-[#222] text-gray-500 cursor-not-allowed" : "bg-ansys-yellow text-black hover:brightness-110 shadow-[0_0_20px_rgba(242,169,0,0.2)]"}`}>
            {isRunning ? <><div className="w-3 h-3 border border-gray-600 border-t-gray-300 rounded-full animate-spin" />Solving…</> : <><Zap size={13} fill="currentColor" /> Run Skyhook</>}
          </button>
        </div>
      </div>

      <div className="flex flex-1 gap-4 overflow-hidden min-h-0">
        <div className="w-60 shrink-0 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-y-auto custom-scrollbar">
          <div className="px-4 py-3 border-b border-[#1e1e1e] sticky top-0 bg-[#0d0d0f] z-10"><h2 className="text-xs font-semibold text-gray-300 flex items-center gap-2"><Settings2 size={13} className="text-ansys-yellow" /> Parameters</h2></div>
          <div className="p-4 space-y-5">
            <ParamSection title="Skyhook Controller">
              <ParameterInput label="Skyhook Gain" val={params.c_sky} unit="Ns/m" step={100} onChange={(v) => setParams({ ...params, c_sky: v })} />
              <ParameterInput label="MR Base Damping" val={params.c_min} unit="Ns/m" step={50} onChange={(v) => setParams({ ...params, c_min: v })} />
            </ParamSection>
            <ParamSection title="Physical Plant">
              <ParameterInput label="Sprung Mass" val={params.m_s} unit="kg" onChange={(v) => setParams({ ...params, m_s: v })} />
              <ParameterInput label="Unsprung Mass" val={params.m_u} unit="kg" onChange={(v) => setParams({ ...params, m_u: v })} />
              <ParameterInput label="Spring Rate" val={params.k_s} unit="N/m" step={500} onChange={(v) => setParams({ ...params, k_s: v })} />
              <ParameterInput label="Tire Stiffness" val={params.k_t} unit="N/m" step={5000} onChange={(v) => setParams({ ...params, k_t: v })} />
              <ParameterInput label="Motion Ratio" val={params.MR} unit="" step={0.05} onChange={(v) => setParams({ ...params, MR: v })} />
            </ParamSection>
            <ParamSection title="Input">
              <ParameterInput label="Bump Height" val={params.bump_height} unit="m" step={0.01} onChange={(v) => setParams({ ...params, bump_height: v })} />
            </ParamSection>
          </div>
        </div>

        <div className="flex-1 flex flex-col gap-3 min-w-0 overflow-hidden">
          {!results && !isRunning && (
            <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl flex flex-col items-center justify-center gap-4">
              <div className="w-16 h-16 rounded-2xl bg-ansys-yellow/5 border border-ansys-yellow/10 flex items-center justify-center"><Activity size={32} strokeWidth={1} className="text-ansys-yellow/40" /></div>
              <div className="text-center"><p className="text-sm font-semibold text-gray-400 mb-1">Configure parameters and click <span className="text-ansys-yellow">Run Skyhook</span></p><p className="text-xs text-gray-700">Semi-Active MR Damper Control</p></div>
            </div>
          )}

          {isRunning && (
            <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl flex flex-col items-center justify-center gap-4">
              <div className="w-10 h-10 border-2 border-ansys-yellow/20 border-t-ansys-yellow rounded-full animate-spin" />
              <div className="text-center"><p className="text-sm font-medium text-gray-400 mb-1">Simulating Controller…</p></div>
            </div>
          )}

          {results?.error && (
            <div className="flex-1 bg-[#111113] border border-red-900/30 rounded-xl flex flex-col items-center justify-center gap-3">
              <AlertTriangle size={44} className="text-red-500 opacity-60" /><p className="text-sm font-semibold text-red-400">Simulation Error</p>
              <pre className="text-xs text-red-600/70 max-w-sm text-center font-mono bg-red-950/30 px-4 py-2 rounded-lg border border-red-900/20 whitespace-pre-wrap">{results.message as string}</pre>
            </div>
          )}

          {hasResults && r && (
            <div id="sim-report" className="flex flex-col gap-3 flex-1 overflow-hidden">
              <div className="grid grid-cols-4 gap-2 shrink-0">
                <KPICard label="Passive RMS Accel" value={r.passive_rms_accel} unit="m/s²" status="neutral" />
                <KPICard label="Active RMS Accel" value={r.active_rms_accel} unit="m/s²" status="good" />
                <KPICard label="Comfort Improvement" value={comfort_improvement} unit="%" status={comfort_improvement > 0 ? "good" : "bad"} />
              </div>

              <div className="flex gap-1.5 shrink-0">
                <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-ansys-yellow text-black shadow-[0_0_12px_rgba(242,169,0,0.2)]">
                  <Pulse size={12} /> Time Domain Control Response
                </button>
              </div>

              <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-hidden min-h-0">
                <div className="grid grid-cols-1 grid-rows-2 h-full gap-px bg-[#181818]">
                  <PlotBox>
                    <Plot
                      data={[
                        { x: r.time, y: r.active_ddz_s, type: "scatter", mode: "lines", name: "Skyhook Active", line: { color: "#00ff87", width: 2 } },
                        { x: r.time, y: r.passive_ddz_s, type: "scatter", mode: "lines", name: "Passive Baseline", line: { color: "#ff2d55", width: 1.5, dash: "dot" } }
                      ]}
                      layout={darkLayout({ title: { text: "Body Acceleration (z̈_s)", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Acceleration (m/s²)", font: { color: "#444", size: 10 } } } })}
                      useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: false }}
                    />
                  </PlotBox>
                  <PlotBox>
                    <Plot
                      data={[
                        { x: r.time, y: r.active_susp_travel?.map((v: number) => v * 1000) || [], type: "scatter", mode: "lines", name: "Skyhook Active", line: { color: "#00ff87", width: 2 } },
                        { x: r.time, y: r.passive_susp_travel?.map((v: number) => v * 1000) || [], type: "scatter", mode: "lines", name: "Passive Baseline", line: { color: "#ff2d55", width: 1.5, dash: "dot" } }
                      ]}
                      layout={darkLayout({ title: { text: "Suspension Travel", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Travel (mm)", font: { color: "#444", size: 10 } } } })}
                      useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: false }}
                    />
                  </PlotBox>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div className="h-full flex items-center justify-center text-gray-600 text-sm">Loading environment…</div>}>
      <ActiveSuspensionDashboard />
    </Suspense>
  );
}
