"use client";
import { useState, Suspense } from "react";
import dynamic from "next/dynamic";
import { Play, Settings2, AlertTriangle, Activity, X, Layers } from "lucide-react";
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

function PlotBox({ children }: { children: React.ReactNode }) {
  return <div className="flex-1 min-w-0 min-h-0 relative">{children}</div>;
}

function SensitivitySweepDashboard() {
  const { authHeader } = useAuth();
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState<Record<string, any> | null>(null);

  const [params, setParams] = useState({
    var_x: "Spring Rate (ks)",
    var_y: "Damping (c)",
    objective: "Balanced (Comfort + Grip)",
    grid_res: 20
  });

  const runSimulation = async () => {
    if (params.var_x === params.var_y) { alert("Please select different variables for X and Y axes."); return; }
    setIsRunning(true); setResults(null);
    try {
      const res = await fetch(`${API_BASE}/simulate/sweep`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeader() }, body: JSON.stringify(params) });
      const data = await res.json();
      if (!res.ok) setResults({ error: true, message: data.message ?? data.detail ?? "Sweep failed" });
      else setResults(data);
    } catch (err) { setResults({ error: true, message: String(err) }); }
    finally { setIsRunning(false); }
  };

  const hasResults = results && !results.error;
  const r = results;

  return (
    <div className="h-full flex flex-col p-5 pt-3 gap-3 min-h-0">
      <div className="flex items-center justify-between shrink-0 pb-3 border-b border-[#1e1e1e]">
        <div className="flex flex-col">
          <span className="text-[9px] font-bold tracking-[0.25em] text-ansys-yellow uppercase">Parameter Grid Optimization</span>
          <h1 className="text-2xl font-semibold tracking-tight text-white leading-tight">Sensitivity Sweep</h1>
        </div>

        <div className="flex items-center gap-2">
          <button onClick={runSimulation} disabled={isRunning}
            className={`px-5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${isRunning ? "bg-[#222] text-gray-500 cursor-not-allowed" : "bg-ansys-yellow text-black hover:brightness-110 shadow-[0_0_20px_rgba(242,169,0,0.2)]"}`}>
            {isRunning ? <><div className="w-3 h-3 border border-gray-600 border-t-gray-300 rounded-full animate-spin" />Computing {params.grid_res * params.grid_res} points…</> : <><Play size={13} fill="currentColor" /> Generate Surface</>}
          </button>
        </div>
      </div>

      <div className="flex flex-1 gap-4 overflow-hidden min-h-0">
        <div className="w-60 shrink-0 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-y-auto custom-scrollbar">
          <div className="px-4 py-3 border-b border-[#1e1e1e] sticky top-0 bg-[#0d0d0f] z-10"><h2 className="text-xs font-semibold text-gray-300 flex items-center gap-2"><Settings2 size={13} className="text-ansys-yellow" /> Grid Setup</h2></div>
          <div className="p-4 space-y-5">
            <ParamSection title="Axis Mapping">
              <div className="flex flex-col gap-1.5 mb-2">
                <label className="text-[11px] text-gray-500">X-Axis Variable</label>
                <select value={params.var_x} onChange={(e) => setParams({ ...params, var_x: e.target.value })} className="bg-[#0d0d0d] border border-[#252525] text-[11px] rounded-lg px-2 py-1.5 text-white focus:outline-none focus:border-ansys-yellow/60 w-full">
                  <option>Spring Rate (ks)</option>
                  <option>Damping (c)</option>
                  <option>Tire Stiffness (kt)</option>
                </select>
              </div>
              <div className="flex flex-col gap-1.5 mb-2">
                <label className="text-[11px] text-gray-500">Y-Axis Variable</label>
                <select value={params.var_y} onChange={(e) => setParams({ ...params, var_y: e.target.value })} className="bg-[#0d0d0d] border border-[#252525] text-[11px] rounded-lg px-2 py-1.5 text-white focus:outline-none focus:border-ansys-yellow/60 w-full">
                  <option>Spring Rate (ks)</option>
                  <option>Damping (c)</option>
                  <option>Tire Stiffness (kt)</option>
                </select>
              </div>
              <div className="flex flex-col gap-1.5 mb-2">
                <label className="text-[11px] font-bold text-[#00aeff]">Z-Axis Objective</label>
                <select value={params.objective} onChange={(e) => setParams({ ...params, objective: e.target.value })} className="bg-[#0d0d0d] border border-[#00aeff]/40 text-[11px] rounded-lg px-2 py-1.5 text-white focus:outline-none focus:border-[#00aeff]/80 w-full">
                  <option>Balanced (Comfort + Grip)</option>
                  <option>Ride Comfort (ISO RMS)</option>
                  <option>Grip (Tire RMS)</option>
                </select>
              </div>
            </ParamSection>

            <ParamSection title="Resolution">
              <div className="pt-2">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-[11px] text-gray-500">Grid Density</span>
                  <span className="text-[11px] font-mono text-ansys-yellow">{params.grid_res}×{params.grid_res}</span>
                </div>
                <input type="range" min="10" max="40" step="1" value={params.grid_res} onChange={(e) => setParams({ ...params, grid_res: Number(e.target.value) })} className="w-full accent-ansys-yellow" />
                <p className="text-[9px] text-gray-600 mt-2 leading-tight">Higher resolution increases solve time exponentially as {params.grid_res * params.grid_res} ODE simulations are executed concurrently.</p>
              </div>
            </ParamSection>
          </div>
        </div>

        <div className="flex-1 flex flex-col gap-3 min-w-0 overflow-hidden">
          {!results && !isRunning && (
            <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl flex flex-col items-center justify-center gap-4">
              <div className="w-16 h-16 rounded-2xl bg-ansys-yellow/5 border border-ansys-yellow/10 flex items-center justify-center"><Activity size={32} strokeWidth={1} className="text-ansys-yellow/40" /></div>
              <div className="text-center"><p className="text-sm font-semibold text-gray-400 mb-1">Select parameters and click <span className="text-ansys-yellow">Generate Surface</span></p><p className="text-xs text-gray-700">Explores design space topography for optimal performance</p></div>
            </div>
          )}

          {isRunning && (
            <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl flex flex-col items-center justify-center gap-4">
              <div className="w-10 h-10 border-2 border-ansys-yellow/20 border-t-ansys-yellow rounded-full animate-spin" />
              <div className="text-center"><p className="text-sm font-medium text-gray-400 mb-1">Running parameter sweep…</p></div>
            </div>
          )}

          {results?.error && (
            <div className="flex-1 bg-[#111113] border border-red-900/30 rounded-xl flex flex-col items-center justify-center gap-3">
              <AlertTriangle size={44} className="text-red-500 opacity-60" /><p className="text-sm font-semibold text-red-400">Sweep Error</p>
              <pre className="text-xs text-red-600/70 max-w-sm text-center font-mono bg-red-950/30 px-4 py-2 rounded-lg border border-red-900/20 whitespace-pre-wrap">{results.message as string}</pre>
            </div>
          )}

          {hasResults && r && (
            <div id="sim-report" className="flex flex-col gap-3 flex-1 overflow-hidden">
              <div className="bg-[#141416] border border-[#00ff87]/30 bg-[#00ff87]/5 rounded-xl p-3 shrink-0 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-[#00ff87]/20 flex items-center justify-center"><Layers size={14} className="text-[#00ff87]" /></div>
                  <div className="flex flex-col">
                    <span className="text-[10px] font-bold text-[#00ff87] uppercase tracking-wider">Optimal Setup Located</span>
                    <span className="text-xs text-gray-300">Minimum valley coordinate found on objective surface.</span>
                  </div>
                </div>
                <div className="flex gap-4 font-mono text-sm">
                  <div className="flex flex-col items-end"><span className="text-[9px] text-gray-500 uppercase">{params.var_x}</span><span className="text-white">{r.min_x?.toFixed(0) ?? 0}</span></div>
                  <div className="flex flex-col items-end"><span className="text-[9px] text-gray-500 uppercase">{params.var_y}</span><span className="text-white">{r.min_y?.toFixed(0) ?? 0}</span></div>
                  <div className="flex flex-col items-end"><span className="text-[9px] text-[#00aeff] uppercase">Objective Score</span><span className="text-[#00aeff] font-bold">{r.min_z?.toFixed(4) ?? 0}</span></div>
                </div>
              </div>

              <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-hidden min-h-0">
                <div className="grid grid-cols-1 grid-rows-1 h-full gap-px bg-[#181818]">
                  <PlotBox>
                    <Plot
                      data={[
                        { z: r.Z, x: r.X, y: r.Y, type: "surface", colorscale: "Viridis", showscale: false },
                        { x: [r.min_x], y: [r.min_y], z: [r.min_z], mode: "markers+text" as any, type: "scatter3d", marker: { size: 6, color: "#ff2d55", symbol: "diamond" }, text: ["Minimum"], textposition: "top center", textfont: { color: "#ff2d55", size: 10 } }
                      ]}
                      layout={{
                        ...DARK_BASE,
                        title: { text: "Design Space Topography (3D)", font: { color: "#888", size: 11 } },
                        scene: {
                          xaxis: { title: { text: params.var_x, font: { color: "#444", size: 10 } }, color: "#555", gridcolor: "#222", backgroundcolor: "transparent", showbackground: false },
                          yaxis: { title: { text: params.var_y, font: { color: "#444", size: 10 } }, color: "#555", gridcolor: "#222", backgroundcolor: "transparent", showbackground: false },
                          zaxis: { title: { text: params.objective, font: { color: "#444", size: 10 } }, color: "#555", gridcolor: "#222", backgroundcolor: "transparent", showbackground: false },
                          camera: { eye: { x: 1.5, y: 1.5, z: 1.2 } }
                        }
                      }}
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
      <SensitivitySweepDashboard />
    </Suspense>
  );
}
