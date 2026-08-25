/* eslint-disable @typescript-eslint/no-explicit-any */
// Handling Page

"use client";
import { useState, Suspense } from "react";
import dynamic from "next/dynamic";
import {
  Play, Settings2, AlertTriangle, Activity, Save, X, TrendingUp, Compass, Route, Undo2, Redo2, RotateCcw
} from "lucide-react";
import { useUndoRedo } from "../../hooks/useUndoRedo";
import PDFExport from "../../components/PDFExport";
import DataExport from "../../components/DataExport";
import SimHistory, { saveSimulationToHistory } from "../../components/SimHistory";
import TirUploader from "../../components/TirUploader";
import TelemetryUploader from "../../components/TelemetryUploader";
import { useAuth } from "../../contexts/AuthContext";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });
import KPICard from "../../components/sim/KPICard";
import PlotBox from "../../components/sim/PlotBox";
import { darkLayout, DARK_BASE } from "../../components/sim/theme";
import { maxAbs } from "../../lib/array";
import { promptModal } from "../../components/sim/ModalHost";
import { ParamSection, ParameterInput } from "../../components/sim/ParameterControls";
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TABS = [
  { label: "Telemetry",   icon: TrendingUp },
  { label: "Trajectory",  icon: Route },
  { label: "Stability",   icon: Compass },
];

type Status = "good" | "warn" | "bad" | "neutral";
type Toast  = { msg: string; type: "success" | "error" };

interface HandlingResults {
  a_y?: number[];
  a_x?: number[];
  yaw_rate?: number[];
  v_x: number[];
  v_y: number[];
  Y: number[];
  X: number[];
  time: number[];
  Psi: number[];
  [key: string]: any;
}

type HandlingState = HandlingResults | { error: boolean; message: string; [key: string]: any };

interface TelemetryData {
  lat_g?: number[];
  long_g?: number[];
  [key: string]: any;
}

function HandlingDashboard() {
  const { authHeader } = useAuth();
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState<HandlingState | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [toast, setToast] = useState<Toast | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [telemetryData, setTelemetryData] = useState<TelemetryData | null>(null);

  const [params, setParams, { undo, redo, reset, canUndo, canRedo }] = useUndoRedo({
    maneuver_type: "Step Steer (J-Turn)",
    v_init_kph: 100.0,
    m: 1200.0,
    h_cg: 0.4,
    roll_dist: 0.55,
    tire_coeffs: null as Record<string, number> | null
  });

  const showToast = (msg: string, type: Toast["type"]) => { setToast({ msg, type }); setTimeout(() => setToast(null), 3500); };

  const runSimulation = async () => {
    setIsRunning(true);
    setResults(null);
    try {
      const payload = {
        params: { m: params.m, h_cg: params.h_cg, roll_dist: params.roll_dist, tire_coeffs: params.tire_coeffs },
        maneuver_type: params.maneuver_type, v_init_kph: params.v_init_kph
      };
      const res = await fetch(`${API_BASE}/simulate/handling`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) {
        setResults({ error: true, message: data.message ?? data.detail ?? "Simulation failed" });
        setIsRunning(false);
        return;
      }
      
      const jobId = data.job_id;
      const interval = setInterval(async () => {
        try {
          const pollRes = await fetch(`${API_BASE}/jobs/${jobId}`, { headers: authHeader() });
          const pollData = await pollRes.json();
          if (pollData.status === "COMPLETED") {
             clearInterval(interval);
             setResults(pollData.result);
             saveSimulationToHistory("sl_sim_history_handling", params, pollData.result);
             setIsRunning(false);
          } else if (pollData.status === "FAILED" || pollData.status === "CANCELED") {
             clearInterval(interval);
             setResults({ error: true, message: pollData.error || "Simulation failed." });
             setIsRunning(false);
          }
        } catch (e) {
             clearInterval(interval);
             setResults({ error: true, message: String(e) });
             setIsRunning(false);
        }
      }, 1000);
    } catch (err) {
      setResults({ error: true, message: String(err) });
      setIsRunning(false);
    }
  };

  const saveProfile = async () => {
    const name = await promptModal("Name this Handling setup:", "Custom Setup");
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
  const trackTraces: Record<string, unknown>[] = [], ggTraces: Record<string, unknown>[] = [];
  
  if (results && !results.error) {
    max_lat_g = maxAbs(results.a_y || []) / 9.81;
    max_long_g = maxAbs(results.a_x || []) / 9.81;
    max_yaw = maxAbs(results.yaw_rate || []) * 180 / Math.PI;
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
    ggTraces.push({ x: (results.a_y || []).map((a: number) => a / 9.81), y: (results.a_x || []).map((a: number) => a / 9.81), mode: 'markers+lines', marker: { size: 4, color: results.time, colorscale: 'Viridis' }, line: { width: 1, color: 'rgba(255,255,255,0.2)' }, name: 'Simulated' });
  }

  if (telemetryData) {
    if (telemetryData.lat_g && telemetryData.long_g && telemetryData.lat_g.length > 0) {
       ggTraces.push({ x: telemetryData.lat_g, y: telemetryData.long_g, mode: 'markers', marker: { size: 4, color: 'rgba(0, 168, 255, 0.4)' }, name: 'MoTeC Telemetry' });
    }
  }

  const hasResults = results && !results.error;
  const r = results as any;

  return (
    <div className="h-full flex flex-col p-5 pt-3 gap-3 min-h-0">
      {toast && (
        <div role="alert" aria-live="polite" className={`fixed top-14 right-4 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-2xl border text-sm font-medium transition-all ${toast.type === "success" ? "bg-[#0a1f12] border-emerald-800/50 text-emerald-300" : "bg-[#1f0a0a] border-red-800/50 text-red-300"}`}>
          {toast.msg} <button onClick={() => setToast(null)} className="opacity-50 hover:opacity-100 ml-1"><X size={13} /></button>
        </div>
      )}

      <div className="flex items-center justify-between shrink-0 pb-3 border-b border-[#1e1e1e]">
        <div className="flex flex-col">
          <span className="text-[9px] font-bold tracking-[0.25em] text-ansys-yellow uppercase">7-DOF Pacejka Architecture</span>
          <h1 className="text-2xl font-semibold tracking-tight text-white leading-tight">Handling Dynamics</h1>
        </div>

        <div className="flex items-center gap-2">
          <SimHistory storageKey="sl_sim_history_handling" renderParams={(p) => [["Speed", p.v_init_kph], ["RollDist", p.roll_dist], ["Maneuver", p.maneuver_type]]} onRestore={(p) => { setParams(prev => ({ ...prev, ...p })); showToast("Restored from history", "success"); }} />
                    {/* Undo/Redo/Reset Controls */}
          <div className="flex items-center bg-[#141416] border border-[#252525] rounded-lg overflow-hidden mr-2">
            <button onClick={undo} disabled={!canUndo} title="Undo (Ctrl+Z)"
              className="px-2.5 py-1.5 hover:bg-[#1e1e20] text-gray-400 disabled:opacity-30 disabled:hover:bg-transparent transition-colors">
              <Undo2 size={14} />
            </button>
            <button onClick={redo} disabled={!canRedo} title="Redo (Ctrl+Y)"
              className="px-2.5 py-1.5 hover:bg-[#1e1e20] text-gray-400 border-l border-[#252525] disabled:opacity-30 disabled:hover:bg-transparent transition-colors">
              <Redo2 size={14} />
            </button>
            <button onClick={reset} title="Reset to Defaults"
              className="px-2.5 py-1.5 hover:bg-[#1e1e20] text-red-400/80 hover:text-red-400 border-l border-[#252525] transition-colors">
              <RotateCcw size={14} />
            </button>
          </div>
<button onClick={saveProfile} disabled={isSaving} className="px-3 py-1.5 bg-[#141416] border border-[#252525] hover:bg-[#1e1e20] rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-40">
            <Save size={13} className="text-ansys-yellow" /> Save Setup
          </button>
          <PDFExport captureId="sim-report" fileName={`Handling_${params.maneuver_type}`} />
          <DataExport results={results} fileName={`Handling_${params.maneuver_type}`} />

          <button onClick={runSimulation} disabled={isRunning}
            className={`px-5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${isRunning ? "bg-[#222] text-gray-500 cursor-not-allowed" : "bg-ansys-yellow text-black hover:brightness-110 shadow-[0_0_20px_rgba(242,169,0,0.2)]"}`}>
            {isRunning ? <><div className="w-3 h-3 border border-gray-600 border-t-gray-300 rounded-full animate-spin" />Solving...</> : <><Play size={13} fill="currentColor" /> Run Solver</>}
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
                onParsed={(coeffs) => setParams({ ...params, tire_coeffs: coeffs as any })} 
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
              <div className="text-center"><p className="text-sm font-medium text-gray-400 mb-1">Integrating 7-DOF states…</p></div>
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
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 shrink-0">
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
                          { x: r.time, y: r.a_y?.map((a: number) => a / 9.81), type: "scatter" as any as any, mode: "lines" as any as any, name: "Lat G (Sim)", line: { color: "#00ff87", width: 2 } },
                          { x: r.time, y: r.a_x?.map((a: number) => a / 9.81), type: "scatter" as any as any, mode: "lines" as any as any, name: "Long G (Sim)", line: { color: "#f2a900", width: 2 } },
                          ...(telemetryData?.lat_g?.length ? [{ x: telemetryData.time, y: telemetryData.lat_g, type: "scatter" as any as any, mode: "lines" as any as any, name: "Lat G (MoTeC)", line: { color: "rgba(0,255,135,0.4)", width: 1, dash: "dot" as any } }] : []),
                          ...(telemetryData?.long_g?.length ? [{ x: telemetryData.time, y: telemetryData.long_g, type: "scatter" as any as any, mode: "lines" as any as any, name: "Long G (MoTeC)", line: { color: "rgba(242,169,0,0.4)", width: 1, dash: "dot" as any } }] : [])
                        ]}
                        layout={darkLayout({ title: { text: "G-Forces over Time", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Acceleration (G)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.v_x?.map((v: number) => v * 3.6), type: "scatter" as any as any, mode: "lines" as any as any, name: "Vx (km/h)", line: { color: "#00aeff", width: 2 } },
                          { x: r.time, y: r.v_y?.map((v: number) => v * 3.6), type: "scatter" as any as any, mode: "lines" as any as any, name: "Vy (km/h)", line: { color: "#ff2d55", width: 2 } },
                          ...(telemetryData?.speed?.length ? [{ x: telemetryData.time, y: telemetryData.speed, type: "scatter" as any as any, mode: "lines" as any as any, name: "Speed (MoTeC)", line: { color: "rgba(0,174,255,0.4)", width: 1, dash: "dot" as any } }] : [])
                        ]}
                        layout={darkLayout({ title: { text: "Velocities", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Velocity (km/h)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.yaw_rate?.map((y: number) => y * 180 / Math.PI), type: "scatter" as any as any, mode: "lines" as any as any, name: "Yaw Rate", line: { color: "#bf5af2", width: 2 }, fill: "tozeroy", fillcolor: "rgba(191,90,242,0.05)" },
                          ...(telemetryData?.yaw_rate?.length ? [{ x: telemetryData.time, y: telemetryData.yaw_rate, type: "scatter" as any as any, mode: "lines" as any as any, name: "Yaw (MoTeC)", line: { color: "rgba(191,90,242,0.4)", width: 1, dash: "dot" as any } }] : [])
                        ]}
                        layout={darkLayout({ title: { text: "Yaw Rate", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Yaw Rate (°/s)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ { x: r.time, y: r.slip_angle?.map((s: number) => s * 180 / Math.PI), type: "scatter" as any as any, mode: "lines" as any as any, name: "Slip Angle", line: { color: "#ff9f0a", width: 2 }, fill: "tozeroy", fillcolor: "rgba(255,159,10,0.05)" } ]}
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
                        data={[ { x: r.slip_angle?.map((s: number) => s * 180 / Math.PI), y: r.yaw_rate?.map((y: number) => y * 180 / Math.PI), mode: "lines+markers", marker: { size: 3, color: r.time, colorscale: "Plasma" }, line: { width: 1, color: "rgba(255,255,255,0.2)" }, name: "Phase Plane" } as const ]}
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
    <Suspense fallback={<div className="h-full flex items-center justify-center text-gray-600 text-sm">Loading simulation environment…</div>}>
      <HandlingDashboard />
    </Suspense>
  );
}


