/* eslint-disable @typescript-eslint/no-explicit-any */
// Full Car Page

"use client";
import { useState, useRef, Suspense, useMemo, useEffect } from "react";
import dynamic from "next/dynamic";
import { useJobPolling } from "../../hooks/useJobPolling";
import { promptModal } from "../../components/sim/ModalHost";
import { ParamSection, ParameterInput } from "../../components/sim/ParameterControls";

import {
  Play, Settings2, AlertTriangle,
  Activity, Save, X, TrendingUp, BarChart3,
  GitBranch, Crosshair, Undo2, Redo2, RotateCcw
} from "lucide-react";
import { useUndoRedo } from "../../hooks/useUndoRedo";
import PDFExport from "../../components/PDFExport";
import DataExport from "../../components/DataExport";
import ComparePanel from "../../components/ComparePanel";
import VehiclePresets from "../../components/VehiclePresets";
import SimHistory, { saveSimulationToHistory } from "../../components/SimHistory";
import { useAuth } from "../../contexts/AuthContext";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });
import KPICard from "../../components/sim/KPICard";
import PlotBox from "../../components/sim/PlotBox";
import { darkLayout, DARK_BASE } from "../../components/sim/theme";
import { maxOf, minOf } from "../../lib/array";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TABS = [
  { label: "Time Domain",       icon: TrendingUp  },
  { label: "Pitch & Roll",      icon: GitBranch   },
  { label: "Load Transfer",     icon: BarChart3   },
  { label: "PSD Analysis",      icon: Crosshair   },
];

// ─── Plotly dark-theme base ──────────────────────────────────────────────────
type Status = "good" | "warn" | "bad" | "neutral";
type Toast  = { msg: string; type: "success" | "error" };

interface FullCarResults {
  error?: boolean;
  message?: string;
  psd_freqs?: number[];
  psd_values?: number[];
  f_n_heave: number;
  f_n_roll: number;
  f_n_pitch: number;
  roll_stiffness_dist: number;
  rms_heave_accel: number;
  rms_pitch_accel: number;
  rms_roll_accel: number;
  lateral_load_transfer_f: number[];
  lateral_load_transfer_r: number[];
  time: number[];
  z_s: number[];
  z_ufl: number[];
  z_url: number[];
  theta: number[];
  phi: number[];
  ddz_s: number[];
  ddtheta: number[];
  ddphi: number[];
  dtheta: number[];
  dphi: number[];
  [key: string]: any;
}

type FullCarState = FullCarResults | { error: boolean; message: string; [key: string]: any };

function FullCarDashboard() {
  const { authHeader } = useAuth();
  const { pollJob } = useJobPolling();

  const [isRunning, setIsRunning] = useState(false);
  const [isSaving,  setIsSaving]  = useState(false);
  const [results,   setResults]   = useState<FullCarState | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [toast,     setToast]     = useState<Toast | null>(null);
  


  const [params, setParams, { undo, redo, reset, canUndo, canRedo }] = useUndoRedo({
    m_s: 1200.0, I_x: 400.0, I_y: 1800.0, m_uf: 40.0, m_ur: 40.0, k_sf: 30000.0, k_sr: 35000.0,
    c_f: 2500.0, c_r: 3000.0, k_arb_f: 20000.0, k_arb_r: 10000.0, L: 2.6, weight_dist: 50.0,
    tw_f: 1.6, tw_r: 1.6, speed_kph: 72.0, p_amp: 0.05
  });

  const showToast = (msg: string, type: Toast["type"]) => { setToast({ msg, type }); setTimeout(() => setToast(null), 3500); };

  const buildPayload = () => {
    const b = params.L * (params.weight_dist / 100.0);
    const a = params.L - b;
    return {
      params: { m_s: params.m_s, I_x: params.I_x, I_y: params.I_y, m_uf: params.m_uf, m_ur: params.m_ur, k_sf: params.k_sf, k_sr: params.k_sr, c_f: params.c_f, c_r: params.c_r, k_arb_f: params.k_arb_f, k_arb_r: params.k_arb_r, k_tf: 250000.0, k_tr: 250000.0, L: params.L, a: a, b: b, tw_f: params.tw_f, tw_r: params.tw_r, speed_mps: params.speed_kph / 3.6, c_tf: 0.0, c_tr: 0.0 },
      profile: { profile_type: "step", amplitude: params.p_amp, frequency: 2.0, duration: 5.0 },
    };
  };

  const runSimulation = async () => {
    setIsRunning(true);
    setResults(null);
    try {
      const res = await fetch(`${API_BASE}/simulate/full-car`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify(buildPayload()),
      });
      const data = await res.json();
      if (!res.ok) {
        setResults({ error: true, message: data.message ?? data.detail ?? "Simulation failed" });
        setIsRunning(false);
        return;
      }
      
      const jobId = data.job_id;
      pollJob({
        jobId,
        authHeader,
        onCompleted: (result) => {
          setResults(result);
          saveSimulationToHistory("sl_sim_history_fcar", params, result);
          setIsRunning(false);
        },
        onFailed: (msg) => {
          setResults({ error: true, message: msg });
          setIsRunning(false);
        },
      });
    } catch (err) {
      setResults({ error: true, message: String(err) });
      setIsRunning(false);
    }
  };

  const saveProfile = async () => {
    const name = await promptModal("Name this Full Car setup:", "Custom 7-DOF Setup");
    if (!name) return;
    setIsSaving(true);
    try {
      const r = await fetch(`${API_BASE}/profiles`, { method: "POST", headers: { "Content-Type": "application/json", ...authHeader() }, body: JSON.stringify({ name, vehicle_type: "FULL_CAR", params }) });
      if (r.ok) showToast("Setup saved to Garage!", "success");
      else showToast("Failed to save", "error");
    } catch { showToast("Failed to save profile", "error"); }
    finally { setIsSaving(false); }
  };

  const psdRoll = useMemo(() => {
    if (!results || results.error) return null;
    if (!results.psd_freqs || !results.psd_values) return null;
    return {
      freqs: results.psd_freqs as number[],
      psd: results.psd_values as number[]
    };
  }, [results]);

  const hasResults = results && !results.error;
  const r = results;

  return (
    <div className="h-full flex flex-col p-5 pt-3 gap-3 min-h-0">
      {toast && (
        <div role="alert" aria-live="polite" className={`fixed top-14 right-4 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-2xl border text-sm font-medium transition-all ${toast.type === "success" ? "bg-[#0a1f12] border-emerald-800/50 text-emerald-300" : "bg-[#1f0a0a] border-red-800/50 text-red-300"}`}>
          {toast.msg} <button onClick={() => setToast(null)} className="opacity-50 hover:opacity-100 ml-1"><X size={13} /></button>
        </div>
      )}

      <div className="flex items-center justify-between shrink-0 pb-3 border-b border-[#1e1e1e]">
        <div className="flex flex-col">
          <span className="text-[9px] font-bold tracking-[0.25em] text-ansys-yellow uppercase">7-DOF Pitch, Roll, Heave</span>
          <h1 className="text-2xl font-semibold tracking-tight text-white leading-tight">Full Car</h1>
        </div>

        <div className="flex items-center gap-2">
          <SimHistory storageKey="sl_sim_history_fcar" renderParams={(p) => [["Mass", p.m_s], ["Ix", p.I_x], ["Iy", p.I_y], ["k_sf", p.k_sf], ["k_sr", p.k_sr], ["Speed", p.speed_kph]]} onRestore={(p) => { setParams(prev => ({ ...prev, ...p })); showToast("Restored from history", "success"); }} />
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
          <PDFExport captureId="sim-report" fileName={`FCar_${params.m_s}`} />
          <DataExport results={results} fileName={`FCar_${params.m_s}`} />

          <button id="btn-run" onClick={runSimulation} disabled={isRunning}
            className={`px-5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${isRunning ? "bg-[#222] text-gray-500 cursor-not-allowed" : "bg-ansys-yellow text-black hover:brightness-110 shadow-[0_0_20px_rgba(242,169,0,0.2)]"}`}>
            {isRunning ? <><div className="w-3 h-3 border border-gray-600 border-t-gray-300 rounded-full animate-spin" />Solving…</> : <><Play size={13} fill="currentColor" /> Run Solver</>}
          </button>
        </div>
      </div>

      <div className="flex flex-1 gap-4 overflow-hidden min-h-0">
        <div className="w-60 shrink-0 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-y-auto custom-scrollbar">
          <div className="px-4 py-3 border-b border-[#1e1e1e] sticky top-0 bg-[#0d0d0f] z-10"><h2 className="text-xs font-semibold text-gray-300 flex items-center gap-2"><Settings2 size={13} className="text-ansys-yellow" /> Parameters</h2></div>
          <div className="p-4 space-y-5">
            <VehiclePresets onSelect={(p) => setParams(prev => ({ ...prev, ...p.params, p_amp: p.road_profile.amplitude }))} />
            <ParamSection title="Inertia">
              <ParameterInput label="Total Mass" val={params.m_s} unit="kg" min={1} onChange={(v) => setParams({ ...params, m_s: v })} />
              <ParameterInput label="Roll Inertia Ix" val={params.I_x} unit="kg·m²" min={1} onChange={(v) => setParams({ ...params, I_x: v })} />
              <ParameterInput label="Pitch Inertia Iy" val={params.I_y} unit="kg·m²" min={1} onChange={(v) => setParams({ ...params, I_y: v })} />
              <ParameterInput label="Wheelbase L" val={params.L} unit="m" step={0.1} min={0.1} onChange={(v) => setParams({ ...params, L: v })} />
              <ParameterInput label="Weight Dist (F)" val={params.weight_dist} unit="%" step={1} min={10} onChange={(v) => setParams({ ...params, weight_dist: v })} />
            </ParamSection>
            <ParamSection title="Front Axle">
              <ParameterInput label="Unsprung Mass" val={params.m_uf} unit="kg" onChange={(v) => setParams({ ...params, m_uf: v })} />
              <ParameterInput label="Spring Rate" val={params.k_sf} unit="N/m" step={500} onChange={(v) => setParams({ ...params, k_sf: v })} />
              <ParameterInput label="Damping" val={params.c_f} unit="N·s/m" step={50} onChange={(v) => setParams({ ...params, c_f: v })} />
              <ParameterInput label="Anti-Roll Bar" val={params.k_arb_f} unit="Nm/rad" step={100} onChange={(v) => setParams({ ...params, k_arb_f: v })} />
              <ParameterInput label="Track Width" val={params.tw_f} unit="m" step={0.05} onChange={(v) => setParams({ ...params, tw_f: v })} />
            </ParamSection>
            <ParamSection title="Rear Axle">
              <ParameterInput label="Unsprung Mass" val={params.m_ur} unit="kg" onChange={(v) => setParams({ ...params, m_ur: v })} />
              <ParameterInput label="Spring Rate" val={params.k_sr} unit="N/m" step={500} onChange={(v) => setParams({ ...params, k_sr: v })} />
              <ParameterInput label="Damping" val={params.c_r} unit="N·s/m" step={50} onChange={(v) => setParams({ ...params, c_r: v })} />
              <ParameterInput label="Anti-Roll Bar" val={params.k_arb_r} unit="Nm/rad" step={100} onChange={(v) => setParams({ ...params, k_arb_r: v })} />
              <ParameterInput label="Track Width" val={params.tw_r} unit="m" step={0.05} onChange={(v) => setParams({ ...params, tw_r: v })} />
            </ParamSection>
            <ParamSection title="Environment">
              <ParameterInput label="Speed" val={params.speed_kph} unit="km/h" step={1} min={0} onChange={(v) => setParams({ ...params, speed_kph: v })} />
              <ParameterInput label="Step Height" val={params.p_amp} unit="m" step={0.01} onChange={(v) => setParams({ ...params, p_amp: v })} />
            </ParamSection>
          </div>
        </div>

        <div className="flex-1 flex flex-col gap-3 min-w-0 overflow-hidden">
          {!results && !isRunning && (
            <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl flex flex-col items-center justify-center gap-4">
              <div className="w-16 h-16 rounded-2xl bg-ansys-yellow/5 border border-ansys-yellow/10 flex items-center justify-center"><Activity size={32} strokeWidth={1} className="text-ansys-yellow/40" /></div>
              <div className="text-center"><p className="text-sm font-semibold text-gray-400 mb-1">Configure parameters and click <span className="text-ansys-yellow">Run Solver</span></p><p className="text-xs text-gray-700">7-DOF full car · LTI State-Space · Pitch & Roll</p></div>
            </div>
          )}

          {isRunning && (
            <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl flex flex-col items-center justify-center gap-4">
              <div className="w-10 h-10 border-2 border-ansys-yellow/20 border-t-ansys-yellow rounded-full animate-spin" />
              <div className="text-center"><p className="text-sm font-medium text-gray-400 mb-1">Running LTI Solver…</p></div>
            </div>
          )}

          {results && results.error ? (
            <div className="flex-1 bg-[#111113] border border-red-900/30 rounded-xl flex flex-col items-center justify-center gap-3">
              <AlertTriangle size={44} className="text-red-500 opacity-60" /><p className="text-sm font-semibold text-red-400">Simulation Error</p>
              <pre className="text-xs text-red-600/70 max-w-sm text-center font-mono bg-red-950/30 px-4 py-2 rounded-lg border border-red-900/20 whitespace-pre-wrap">{results.message as string}</pre>
            </div>
          ) : null}

          {hasResults && r && (
            <div id="sim-report" className="flex flex-col gap-3 flex-1 overflow-hidden">
              <ComparePanel current={r as unknown as React.ComponentProps<typeof ComparePanel>["current"]} />

              <div className="grid grid-cols-8 gap-2 shrink-0">
                <KPICard label="Heave ƒₙ" value={r.f_n_heave} unit="Hz" status={r.f_n_heave >= 1.0 && r.f_n_heave <= 1.5 ? "good" : "warn"} />
                <KPICard label="Roll ƒₙ" value={r.f_n_roll} unit="Hz" status={r.f_n_roll >= 1.5 && r.f_n_roll <= 2.5 ? "good" : "warn"} />
                <KPICard label="Pitch ƒₙ" value={r.f_n_pitch} unit="Hz" status={r.f_n_pitch >= 1.2 && r.f_n_pitch <= 1.8 ? "good" : "warn"} />
                <KPICard label="Roll Dist." value={r.roll_stiffness_dist} unit="% Front" status={r.roll_stiffness_dist >= 55 ? "good" : "warn"} />
                <KPICard label="RMS Heave" value={r.rms_heave_accel} unit="m/s²" status={r.rms_heave_accel < 0.315 ? "good" : r.rms_heave_accel < 1.0 ? "warn" : "bad"} />
                <KPICard label="RMS Pitch" value={r.rms_pitch_accel} unit="rad/s²" status="neutral" />
                <KPICard label="RMS Roll" value={r.rms_roll_accel} unit="rad/s²" status="neutral" />
                <KPICard label="LLT Front" value={maxOf(r.lateral_load_transfer_f as number[])} unit="N" status="neutral" />
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
                {/* ── TAB 0: TIME DOMAIN ── */}
                {activeTab === 0 && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[350px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.z_s?.map((v: number) => v * 1000), type: "scatter", mode: "lines", name: "CG Heave z_s", line: { color: "#f2a900", width: 2 } },
                          { x: r.time, y: r.z_ufl?.map((v: number) => v * 1000), type: "scatter", mode: "lines", name: "FL Wheel", line: { color: "#00aeff", width: 1 } },
                          { x: r.time, y: r.z_url?.map((v: number) => v * 1000), type: "scatter", mode: "lines", name: "RL Wheel", line: { color: "#ff2d55", width: 1 } },
                        ]}
                        layout={darkLayout({ title: { text: "Vertical Displacements", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Displacement (mm)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ 
                          { x: r.time, y: r.theta?.map((v: number) => v * 180 / Math.PI), type: "scatter", mode: "lines", name: "Pitch Angle θ", line: { color: "#00ff87", width: 2 } },
                          { x: r.time, y: r.phi?.map((v: number) => v * 180 / Math.PI), type: "scatter", mode: "lines", name: "Roll Angle φ", line: { color: "#bf5af2", width: 2 } } 
                        ]}
                        layout={darkLayout({ title: { text: "Attitude Angles", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Angle (°)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ { x: r.time, y: r.ddz_s, type: "scatter", mode: "lines", name: "Heave Accel z̈_s", line: { color: "#f2a900", width: 2 }, fill: "tozeroy", fillcolor: "rgba(242,169,0,0.05)" } ]}
                        layout={darkLayout({ title: { text: "Heave Acceleration", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Acceleration (m/s²)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.ddtheta, type: "scatter", mode: "lines", name: "Pitch Accel", line: { color: "#00ff87", width: 1.5 } },
                          { x: r.time, y: r.ddphi, type: "scatter", mode: "lines", name: "Roll Accel", line: { color: "#bf5af2", width: 1.5 } }
                        ]}
                        layout={darkLayout({ title: { text: "Angular Accelerations", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Accel (rad/s²)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                )}

                {/* ── TAB 1: PITCH & ROLL ── */}
                {activeTab === 1 && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[350px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    <PlotBox>
                      <Plot
                        data={[ { x: r.phi?.map((v: number) => v * 180 / Math.PI), y: r.theta?.map((v: number) => v * 180 / Math.PI), type: "scatter", mode: "lines", name: "Coupling", line: { color: "#f2a900", width: 1.5 } } ]}
                        layout={darkLayout({ title: { text: "Roll vs Pitch Space", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Roll φ (°)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Pitch θ (°)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ { x: r.theta?.map((v: number) => v * 180 / Math.PI), y: r.dtheta?.map((v: number) => v * 180 / Math.PI), type: "scatter", mode: "lines", name: "Pitch Phase", line: { color: "#00ff87", width: 1.5 } } ]}
                        layout={darkLayout({ title: { text: "Pitch Phase Portrait", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "θ (°)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "θ̇ (°/s)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ { x: r.phi?.map((v: number) => v * 180 / Math.PI), y: r.dphi?.map((v: number) => v * 180 / Math.PI), type: "scatter", mode: "lines", name: "Roll Phase", line: { color: "#bf5af2", width: 1.5 } } ]}
                        layout={darkLayout({ title: { text: "Roll Phase Portrait", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "φ (°)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "φ̇ (°/s)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <div className="h-full p-5 flex flex-col justify-center gap-4">
                        <p className="text-[10px] font-bold tracking-widest text-gray-700 uppercase">Roll Characteristics</p>
                        <div className="space-y-3 font-mono text-xs">
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Roll Stiffness Dist</span><span className="text-[#00ff87]">{r.roll_stiffness_dist.toFixed(1)}% Front</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Front Track</span><span className="text-white">{params.tw_f} m</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Rear Track</span><span className="text-white">{params.tw_r} m</span></div>
                        </div>
                      </div>
                    </PlotBox>
                  </div>
                )}

                {/* ── TAB 2: LOAD TRANSFER ── */}
                {activeTab === 2 && (
                  <div className="grid grid-cols-1 auto-rows-[400px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.lateral_load_transfer_f, type: "scatter", mode: "lines", name: "Front LLT", line: { color: "#00aeff", width: 2 } },
                          { x: r.time, y: r.lateral_load_transfer_r, type: "scatter", mode: "lines", name: "Rear LLT", line: { color: "#ff2d55", width: 2 } }
                        ]}
                        layout={darkLayout({ title: { text: "Lateral Load Transfer (ΔFz)", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Load Transfer (N)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: false }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <div className="h-full p-5 flex flex-col justify-center gap-4">
                        <p className="text-[10px] font-bold tracking-widest text-gray-700 uppercase">Load Transfer Summary</p>
                        <div className="space-y-3 font-mono text-xs">
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Max Front LLT</span><span className="text-[#00aeff]">{maxOf(r.lateral_load_transfer_f as number[]).toFixed(0)} N</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Max Rear LLT</span><span className="text-[#ff2d55]">{maxOf(r.lateral_load_transfer_r as number[]).toFixed(0)} N</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Total Max LLT</span><span className="text-white">{(maxOf(r.lateral_load_transfer_f as number[]) + maxOf(r.lateral_load_transfer_r as number[])).toFixed(0)} N</span></div>
                        </div>
                      </div>
                    </PlotBox>
                  </div>
                )}

                {/* ── TAB 3: PSD ANALYSIS ── */}
                {activeTab === 3 && psdRoll && (
                  <div className="grid grid-cols-1 grid-rows-1 h-full gap-px bg-[#181818]">
                    <PlotBox>
                      <Plot
                        data={[ { x: psdRoll.freqs, y: psdRoll.psd, type: "scatter", mode: "lines", name: "PSD Roll", fill: "tozeroy", fillcolor: "rgba(191,90,242,0.06)", line: { color: "#bf5af2", width: 2 } } ]}
                        layout={darkLayout({ title: { text: "PSD — Roll Acceleration", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#444", size: 10 } }, type: "log", range: [Math.log10(0.1), Math.log10(50)] }, yaxis: { ...DARK_BASE.yaxis, title: { text: "PSD ((rad/s²)²/Hz)", font: { color: "#444", size: 10 } }, type: "log" } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: false }}
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
      <FullCarDashboard />
    </Suspense>
  );
}

