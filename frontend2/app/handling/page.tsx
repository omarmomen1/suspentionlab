// @ts-nocheck

"use client";
import { useState, Suspense } from "react";
import dynamic from "next/dynamic";
import { Play, Settings2, AlertTriangle, Activity, Save, X, TrendingUp, Compass, Route } from "lucide-react";
const PDFExport = dynamic(() => import("../../components/PDFExport"), { ssr: false });
import DataExport from "../../components/DataExport";
import SimHistory, { saveSimulationToHistory } from "../../components/SimHistory";
import TirUploader from "../../components/TirUploader";
import TelemetryUploader from "../../components/TelemetryUploader";
import { useAuth } from "../../contexts/AuthContext";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TABS = [
  { label: "Telemetry",   icon: TrendingUp },
  { label: "Trajectory",  icon: Route },
  { label: "Stability",   icon: Compass },
];

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
type Toast  = { msg: string; type: "success" | "error" };

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

function HandlingDashboard() {
  const { authHeader } = useAuth();
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState<Record<string, any> | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [toast, setToast] = useState<Toast | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [telemetryData, setTelemetryData] = useState<any | null>(null);

  const [params, setParams] = useState({
    maneuver_type: "Step Steer (J-Turn)",
    v_init_kph: 100.0,
    m: 1200.0,
    h_cg: 0.4,
    roll_dist: 0.55,
    tire_coeffs: null as any
  });

  const showToast = (msg: string, type: Toast["type"]) => { setToast({ msg, type }); setTimeout(() => setToast(null), 3500); };

  const runSimulation = async () => {
    setIsRunning(true); setResults(null);
    try {
      const payload = {
        params: { m: params.m, h_cg: params.h_cg, roll_dist: params.roll_dist, tire_coeffs: params.tire_coeffs },
        maneuver_type: params.maneuver_type, v_init_kph: params.v_init_kph
      };
      const res = await fetch(`${API_BASE}/simulate/handling`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeader() }, body: JSON.stringify(payload) });
      const data = await res.json();
      if (!res.ok) setResults({ error: true, message: data.message ?? data.detail ?? "Simulation failed" });
      else { setResults(data); saveSimulationToHistory(params, data); }
    } catch (err) { setResults({ error: true, message: String(err) }); }
    finally { setIsRunning(false); }
  };

  const saveProfile = async () => {
    const name = prompt("Name this Handling setup:", "Custom Setup");
    if (!name) return;
    setIsSaving(true);
    try {
      const r = await fetch(`${API_BASE}/profiles`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeader() }, body: JSON.stringify({ name, vehicle_type: "HANDLING", params }) });
      if (r.ok) showToast("Setup saved to Garage!", "success");
      else showToast("Failed to save", "error");
    } catch { showToast("Failed to save profile", "error"); }
    finally { setIsSaving(false); }
  };

  let max_lat_g = 0, max_long_g = 0, max_yaw = 0, final_speed = 0;
  let trackTraces: any[] = [], ggTraces: any[] = [];
  
  if (results && !results.error) {
    max_lat_g = Math.max(...results.a_y.map(Math.abs)) / 9.81;
    max_long_g = Math.max(...results.a_x.map(Math.abs)) / 9.81;
    max_yaw = Math.max(...results.yaw_rate.map(Math.abs)) * 180 / Math.PI;
    const vx_last = results.v_x[results.v_x.length - 1];
    const vy_last = results.v_y[results.v_y.length - 1];
    final_speed = Math.sqrt(vx_last*vx_last + vy_last*vy_last) * 3.6;

    trackTraces.push({ x: results.Y, y: results.X, mode: 'lines', line: { color: '#00ff87', width: 3 }, name: 'CG Path' });
    const dt = results.time[1] - results.time[0];
    const step = Math.floor(0.5 / dt) || 1;
    for (let i = 0; i < results.time.length; i += step) {
      const x_cg = results.Y[i], y_cg = results.X[i], psi = results.Psi[i];
      const L_draw = 4.0;
      const dx = (L_draw/2) * Math.sin(psi);
      const dy = (L_draw/2) * Math.cos(psi);
      trackTraces.push({ x: [x_cg - dx, x_cg + dx], y: [y_cg - dy, y_cg + dy], mode: 'lines', line: { color: 'rgba(255,255,255,0.2)', width: 1.5 }, showlegend: false });
    }

    const theta = Array.from({ length: 100 }, (_, i) => (i * 2 * Math.PI) / 99);
    const mu_peak = 1.05;
    ggTraces.push({ x: theta.map(t => Math.sin(t) * mu_peak), y: theta.map(t => Math.cos(t) * mu_peak), mode: 'lines', line: { color: '#444', width: 1.5, dash: 'dash' }, name: 'Friction Circle' });
    ggTraces.push({ x: results.a_y.map((a: number) => a / 9.81), y: results.a_x.map((a: number) => a / 9.81), mode: 'markers+lines', marker: { size: 4, color: results.time, colorscale: 'Viridis' }, line: { width: 1, color: 'rgba(255,255,255,0.2)' }, name: 'Simulated' });
  }

  if (telemetryData) {
    if (telemetryData.lat_g && telemetryData.long_g && telemetryData.lat_g.length > 0) {
       ggTraces.push({ x: telemetryData.lat_g, y: telemetryData.long_g, mode: 'markers', marker: { size: 4, color: 'rgba(0, 168, 255, 0.4)' }, name: 'MoTeC Telemetry' });
    }
  }

  const hasResults = results && !results.error;
  const r = results;

  return (
    <div className="h-full flex flex-col p-5 pt-3 gap-3 min-h-0">
      {toast && (
        <div className={`fixed top-14 right-4 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-2xl border text-sm font-medium transition-all ${toast.type === "success" ? "bg-[#0a1f12] border-emerald-800/50 text-emerald-300" : "bg-[#1f0a0a] border-red-800/50 text-red-300"}`}>
          {toast.msg} <button onClick={() => setToast(null)} className="opacity-50 hover:opacity-100 ml-1"><X size={13} /></button>
        </div>
      )}

      <div className="flex items-center justify-between shrink-0 pb-3 border-b border-[#1e1e1e]">
        <div className="flex flex-col">
          <span className="text-[9px] font-bold tracking-[0.25em] text-ansys-yellow uppercase">7-DOF Pacejka Architecture</span>
          <h1 className="text-2xl font-semibold tracking-tight text-white leading-tight">Handling Dynamics</h1>
        </div>

        <div className="flex items-center gap-2">
          <SimHistory onRestore={(p) => { setParams(prev => ({ ...prev, ...p })); showToast("Restored from history", "success"); }} />
          <button onClick={saveProfile} disabled={isSaving} className="px-3 py-1.5 bg-[#141416] border border-[#252525] hover:bg-[#1e1e20] rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-40">
            <Save size={13} className="text-ansys-yellow" /> Save Setup
          </button>
          <PDFExport captureId="sim-report" fileName={`Handling_${params.maneuver_type}`} />
          <DataExport results={results} fileName={`Handling_${params.maneuver_type}`} />

          <button onClick={runSimulation} disabled={isRunning}
            className={`px-5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${isRunning ? "bg-[#222] text-gray-500 cursor-not-allowed" : "bg-ansys-yellow text-black hover:brightness-110 shadow-[0_0_20px_rgba(242,169,0,0.2)]"}`}>
            {isRunning ? <><div className="w-3 h-3 border border-gray-600 border-t-gray-300 rounded-full animate-spin" />Solvingâ€¦</> : <><Play size={13} fill="currentColor" /> Run Solver</>}
          </button>
        </div>
      </div>

      <div className="flex flex-1 gap-4 overflow-hidden min-h-0">
        <div className="w-60 shrink-0 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-y-auto custom-scrollbar">
          <div className="px-4 py-3 border-b border-[#1e1e1e] sticky top-0 bg-[#0d0d0f] z-10"><h2 className="text-xs font-semibold text-gray-300 flex items-center gap-2"><Settings2 size={13} className="text-ansys-yellow" /> Parameters</h2></div>
          <div className="p-4 space-y-5">
            <ParamSection title="Maneuver">
              <div className="flex flex-col gap-1.5 mb-2">
                <label className="text-[11px] text-gray-500">Test Track Maneuver</label>
                <select value={params.maneuver_type} onChange={(e) => setParams({ ...params, maneuver_type: e.target.value })} className="bg-[#0d0d0d] border border-[#252525] text-[11px] rounded-lg px-2 py-1.5 text-white focus:outline-none focus:border-ansys-yellow/60 focus:ring-1 focus:ring-ansys-yellow/15 w-full">
                  <option>Step Steer (J-Turn)</option>
                  <option>Sine Sweep (Slalom)</option>
                  <option>Constant Radius Cornering</option>
                  <option>Brake in Turn</option>
                </select>
              </div>
              <ParameterInput label="Initial Speed" val={params.v_init_kph} unit="km/h" onChange={(v) => setParams({ ...params, v_init_kph: v })} />
            </ParamSection>
            <ParamSection title="Vehicle Setup">
              <ParameterInput label="Total Mass" val={params.m} unit="kg" onChange={(v) => setParams({ ...params, m: v })} />
              <ParameterInput label="CG Height" val={params.h_cg} unit="m" step={0.05} onChange={(v) => setParams({ ...params, h_cg: v })} />
              <ParameterInput label="Roll Stiffness Dist" val={params.roll_dist} unit="fr%" step={0.05} onChange={(v) => setParams({ ...params, roll_dist: v })} />
              <TirUploader 
                hasCoeffs={params.tire_coeffs !== null} 
                onParsed={(coeffs) => setParams({ ...params, tire_coeffs: coeffs })} 
                onClear={() => setParams({ ...params, tire_coeffs: null })} 
              />
              <TelemetryUploader
                hasData={telemetryData !== null}
                onParsed={(data) => setTelemetryData(data)}
                onClear={() => setTelemetryData(null)}
              />
            </ParamSection>
          </div>
        </div>

        <div className="flex-1 flex flex-col gap-3 min-w-0 overflow-hidden">
          {!results && !isRunning && (
            <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl flex flex-col items-center justify-center gap-4">
              <div className="w-16 h-16 rounded-2xl bg-ansys-yellow/5 border border-ansys-yellow/10 flex items-center justify-center"><Activity size={32} strokeWidth={1} className="text-ansys-yellow/40" /></div>
              <div className="text-center"><p className="text-sm font-semibold text-gray-400 mb-1">Configure parameters and click <span className="text-ansys-yellow">Run Solver</span></p><p className="text-xs text-gray-700">7-DOF Pacejka Tire Model · Kinematic Stability</p></div>
            </div>
          )}

          {isRunning && (
            <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl flex flex-col items-center justify-center gap-4">
              <div className="w-10 h-10 border-2 border-ansys-yellow/20 border-t-ansys-yellow rounded-full animate-spin" />
              <div className="text-center"><p className="text-sm font-medium text-gray-400 mb-1">Integrating 7-DOF statesâ€¦</p></div>
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
                <KPICard label="Peak Lat Accel" value={max_lat_g} unit="G" status={max_lat_g > 0.8 ? "good" : "warn"} />
                <KPICard label="Peak Long Accel" value={max_long_g} unit="G" status="neutral" />
                <KPICard label="Peak Yaw Rate" value={max_yaw} unit="°/s" status={max_yaw < 40 ? "good" : "warn"} />
                <KPICard label="Exit Speed" value={final_speed} unit="km/h" status="neutral" />
              </div>

              <div className="flex gap-1.5 shrink-0">
                {TABS.map((tab, i) => {
                  const Icon = tab.icon;
                  return (
                    <button key={tab.label} onClick={() => setActiveTab(i)} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${activeTab === i ? "bg-ansys-yellow text-black shadow-[0_0_12px_rgba(242,169,0,0.2)]" : "bg-[#111113] border border-[#1e1e1e] text-gray-500 hover:text-gray-300 hover:border-[#2a2a2a]"}`}>
                      <Icon size={12} /> {tab.label}
                    </button>
                  );
                })}
              </div>

              <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-hidden min-h-0">
                {activeTab === 0 && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[350px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.a_y.map((a: number) => a / 9.81), type: "scatter" as any, mode: "lines", name: "Lat G (Sim)", line: { color: "#00ff87", width: 2 } },
                          { x: r.time, y: r.a_x.map((a: number) => a / 9.81), type: "scatter" as any, mode: "lines", name: "Long G (Sim)", line: { color: "#f2a900", width: 2 } },
                          ...(telemetryData?.lat_g?.length ? [{ x: telemetryData.time, y: telemetryData.lat_g, type: "scatter" as any, mode: "lines", name: "Lat G (MoTeC)", line: { color: "rgba(0,255,135,0.4)", width: 1, dash: "dot" } }] : []),
                          ...(telemetryData?.long_g?.length ? [{ x: telemetryData.time, y: telemetryData.long_g, type: "scatter" as any, mode: "lines", name: "Long G (MoTeC)", line: { color: "rgba(242,169,0,0.4)", width: 1, dash: "dot" } }] : [])
                        ]}
                        layout={darkLayout({ title: { text: "G-Forces over Time", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Acceleration (G)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.v_x.map((v: number) => v * 3.6), type: "scatter" as any, mode: "lines", name: "Vx (km/h)", line: { color: "#00aeff", width: 2 } },
                          { x: r.time, y: r.v_y.map((v: number) => v * 3.6), type: "scatter" as any, mode: "lines", name: "Vy (km/h)", line: { color: "#ff2d55", width: 2 } },
                          ...(telemetryData?.speed?.length ? [{ x: telemetryData.time, y: telemetryData.speed, type: "scatter" as any, mode: "lines", name: "Speed (MoTeC)", line: { color: "rgba(0,174,255,0.4)", width: 1, dash: "dot" } }] : [])
                        ]}
                        layout={darkLayout({ title: { text: "Velocities", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Velocity (km/h)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.yaw_rate.map((y: number) => y * 180 / Math.PI), type: "scatter" as any, mode: "lines", name: "Yaw Rate", line: { color: "#bf5af2", width: 2 }, fill: "tozeroy", fillcolor: "rgba(191,90,242,0.05)" },
                          ...(telemetryData?.yaw_rate?.length ? [{ x: telemetryData.time, y: telemetryData.yaw_rate, type: "scatter" as any, mode: "lines", name: "Yaw (MoTeC)", line: { color: "rgba(191,90,242,0.4)", width: 1, dash: "dot" } }] : [])
                        ]}
                        layout={darkLayout({ title: { text: "Yaw Rate", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Yaw Rate (°/s)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ { x: r.time, y: r.slip_angle.map((s: number) => s * 180 / Math.PI), type: "scatter" as any, mode: "lines", name: "Slip Angle", line: { color: "#ff9f0a", width: 2 }, fill: "tozeroy", fillcolor: "rgba(255,159,10,0.05)" } ]}
                        layout={darkLayout({ title: { text: "Side Slip Angle", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Slip Angle (°)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                )}

                {activeTab === 1 && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[350px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    <PlotBox>
                      <Plot
                        data={trackTraces as any}
                        layout={darkLayout({ title: { text: "Vehicle Trajectory (Top Down)", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Y (Lateral) [m]", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "X (Longitudinal) [m]", font: { color: "#444", size: 10 } }, scaleanchor: "x", scaleratio: 1 } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={ggTraces as any}
                        layout={darkLayout({ title: { text: "G-G Diagram", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Lat (G)", font: { color: "#444", size: 10 } }, range: [-1.5, 1.5] }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Long (G)", font: { color: "#444", size: 10 } }, scaleanchor: "x", scaleratio: 1, range: [-1.5, 1.5] } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                )}

                {activeTab === 2 && (
                  <div className="grid grid-cols-1 auto-rows-[400px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    <PlotBox>
                      <Plot
                        data={[ { x: r.slip_angle.map((s: number) => s * 180 / Math.PI), y: r.yaw_rate.map((y: number) => y * 180 / Math.PI), mode: "lines+markers", marker: { size: 3, color: r.time, colorscale: "Plasma" }, line: { width: 1, color: "rgba(255,255,255,0.2)" }, name: "Phase Plane" } as any ]}
                        layout={darkLayout({ title: { text: "Stability Phase Plane (Slip Angle vs Yaw Rate)", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Slip Angle (°)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Yaw Rate (°/s)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                )}
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
    <Suspense fallback={<div className="h-full flex items-center justify-center text-gray-600 text-sm">Loading simulation environmentâ€¦</div>}>
      <HandlingDashboard />
    </Suspense>
  );
}
