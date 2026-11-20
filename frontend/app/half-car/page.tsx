
// Half Car Page

"use client";
import { useState, useRef, Suspense, useMemo, useEffect } from "react";
import { useSearchParams } from "next/navigation";
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
import DamperLUTInput from "../../components/DamperLUTInput";
import { useAuth } from "../../contexts/AuthContext";

import Plot from "../../components/sim/Plot";
import KPICard from "../../components/sim/KPICard";
import PlotBox from "../../components/sim/PlotBox";
import { darkLayout, DARK_BASE } from "../../components/sim/theme";
import { computePsd } from "../../lib/fft";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ROAD_PROFILES = [
  { label: "Step Input",        value: "step"    },
  { label: "Pothole",           value: "pothole" },
  { label: "Sine Wave",         value: "sine"    },
  { label: "Random (ISO 8608)", value: "random"  },
  { label: "Impulse",           value: "impulse" },
];

const TABS = [
  { label: "Time Domain",       icon: TrendingUp  },
  { label: "Pitch-Heave",       icon: GitBranch   },
  { label: "Phase Space",       icon: BarChart3   },
  { label: "PSD Analysis",      icon: Crosshair   },
];

// ─── Plotly dark-theme base ──────────────────────────────────────────────────
type Status = "good" | "warn" | "bad" | "neutral";
type Toast  = { msg: string; type: "success" | "error" };

interface HalfCarResults {
  f_n_heave: number;
  f_n_pitch: number;
  [key: string]: any;
}

type HalfCarState = HalfCarResults | { error: boolean; message: string; [key: string]: any };

function HalfCarDashboard() {
  const searchParams = useSearchParams();
  const { authHeader, fetchWithAuth } = useAuth();
  const { pollJob } = useJobPolling();

  const [isRunning, setIsRunning] = useState(false);
  const [isSaving,  setIsSaving]  = useState(false);
  const [results,   setResults]   = useState<HalfCarState | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [toast,     setToast]     = useState<Toast | null>(null);

  const [params, setParams, { undo, redo, reset, canUndo, canRedo }] = useUndoRedo({
    m_s: 1200.0, I_y: 1800.0, m_uf: 40.0, m_ur: 40.0, k_sf: 30000.0, k_sr: 35000.0, c_f: 2500.0, c_r: 3000.0,
    k_tf: 250000.0, k_tr: 250000.0, L: 2.6, weight_dist: 50.0, speed_kph: 72.0, road_profile: "step", amplitude: 0.05, frequency: 2.0, duration: 5.0,
    damper_curve_v_f: null as number[] | null, damper_curve_f_f: null as number[] | null,
    damper_curve_v_r: null as number[] | null, damper_curve_f_r: null as number[] | null,
  });

  const showToast = (msg: string, type: Toast["type"]) => { setToast({ msg, type }); setTimeout(() => setToast(null), 3500); };

  useEffect(() => {
    const profileId = searchParams.get("load");
    if (!profileId) return;
    fetchWithAuth(`/api/v1/profiles/${profileId}`)
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((data) => {
        if (data.params) {
          setParams((prev: any) => ({ ...prev, ...data.params }));
          showToast(`Loaded "${data.name}" from Garage`, "success");
        }
      })
      .catch(() => showToast("Could not load profile", "error"));
  }, [searchParams]);

  const buildPayload = () => {
    const b = params.L * (params.weight_dist / 100.0);
    const a = params.L - b;
    return {
      params: { m_s: params.m_s, I_y: params.I_y, m_uf: params.m_uf, m_ur: params.m_ur, k_sf: params.k_sf, k_sr: params.k_sr, c_f: params.c_f, c_r: params.c_r, k_tf: params.k_tf, k_tr: params.k_tr, L: params.L, a: a, b: b, speed_mps: params.speed_kph / 3.6, c_tf: 0.0, c_tr: 0.0, damper_curve_v_f: params.damper_curve_v_f, damper_curve_f_f: params.damper_curve_f_f, damper_curve_v_r: params.damper_curve_v_r, damper_curve_f_r: params.damper_curve_f_r },
      profile: { profile_type: params.road_profile, amplitude: params.amplitude, frequency: params.frequency, duration: params.duration },
    };
  };

  const runSimulation = async () => {
    setIsRunning(true);
    setResults(null);
    try {
      const res = await fetchWithAuth("/api/v1/simulate/half-car", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      const data = await res.json();
      if (!res.ok) {
        setResults({ error: true, message: data.message ?? data.detail ?? "Simulation failed" });
        setIsRunning(false);
        return;
      }
      
      if (data.job_id) {
        pollJob({
          jobId: data.job_id,
          authHeader,
          onCompleted: (result) => {
            setResults(result);
            saveSimulationToHistory("sl_sim_history_hcar", params, result);
            setIsRunning(false);
          },
          onFailed: (msg) => {
            setResults({ error: true, message: msg });
            setIsRunning(false);
          },
        });
      } else {
        setResults(data);
        saveSimulationToHistory("sl_sim_history_hcar", params, data);
        setIsRunning(false);
      }
    } catch (err) {
      setResults({ error: true, message: String(err) });
      setIsRunning(false);
    }
  };

  const saveProfile = async () => {
    if (isSaving) return;
    const name = await promptModal("Name this Half Car setup:", "Custom 4-DOF Setup");
    if (!name) return;
    setIsSaving(true);
    try {
      const r = await fetchWithAuth("/api/v1/profiles/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, vehicle_type: "HALF_CAR", params })
      });
      if (r.ok) showToast("Setup saved to Garage!", "success");
      else showToast("Failed to save", "error");
    } catch { showToast("Failed to save profile", "error"); }
    finally { setIsSaving(false); }
  };

  // P0-PERF-01: O(N log N) FFT (lib/fft) replaces the O(N^2) DFT that froze
  // the UI thread on long simulations.
  const psdData = useMemo(() => {
    if (!results || results.error) return null;
    const ddz = results.ddz_s as number[];
    const t = results.time as number[];
    if (!ddz || ddz.length < 64) return null;
    const dt = t[1] - t[0], fs = 1 / dt;
    const { freqs, psd } = computePsd(ddz, fs);
    const psdOneSided = psd.map((v, k) => (k > 0 && k < psd.length - 1 ? 2 * v : v));
    return { freqs, psd: psdOneSided };
  }, [results]);

  const psdPitch = useMemo(() => {
    if (!results || results.error) return null;
    const ddtheta = results.ddtheta as number[];
    const t = results.time as number[];
    if (!ddtheta || ddtheta.length < 64) return null;
    const dt = t[1] - t[0], fs = 1 / dt;
    const { freqs, psd } = computePsd(ddtheta, fs);
    const psdOneSided = psd.map((v, k) => (k > 0 && k < psd.length - 1 ? 2 * v : v));
    return { freqs, psd: psdOneSided };
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
          <span className="text-[9px] font-bold tracking-[0.25em] text-ansys-yellow uppercase">4-DOF Pitch Plane · RK45 ODE</span>
          <h1 className="text-2xl font-semibold tracking-tight text-white leading-tight">Half Car</h1>
        </div>

        <div className="flex items-center gap-2">
          <SimHistory storageKey="sl_sim_history_hcar" renderParams={(p, m) => [["m_s", p.m_s], ["k_sf", p.k_sf], ["k_sr", p.k_sr], ["RMS", m?.rms_body_accel], ["TX", m?.peak_transmissibility], ["fₙ", m?.f_n_s]]} onRestore={(p) => { setParams(prev => ({ ...prev, ...p })); showToast("Restored from history", "success"); }} />
          {/* Undo/Redo/Reset Controls */}
          <div className="flex items-center bg-[#141416] border border-[#252525] rounded-lg overflow-hidden mr-2">
            <button
              type="button"
              onClick={undo}
              disabled={!canUndo}
              title="Undo (Ctrl+Z)"
              aria-label="Undo parameter change"
              className="px-2.5 py-1.5 hover:bg-[#1e1e20] text-gray-400 hover:text-white disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
            >
              <Undo2 size={14} />
            </button>
            <button
              type="button"
              onClick={redo}
              disabled={!canRedo}
              title="Redo (Ctrl+Y)"
              aria-label="Redo parameter change"
              className="px-2.5 py-1.5 hover:bg-[#1e1e20] text-gray-400 hover:text-white border-l border-[#252525] disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
            >
              <Redo2 size={14} />
            </button>
            <button
              type="button"
              onClick={reset}
              title="Reset to Defaults"
              aria-label="Reset parameters to defaults"
              className="px-2.5 py-1.5 hover:bg-[#1e1e20] text-red-400/80 hover:text-red-400 border-l border-[#252525] transition-colors"
            >
              <RotateCcw size={14} />
            </button>
          </div>
          <button onClick={saveProfile} disabled={isSaving} className="px-3 py-1.5 bg-[#141416] border border-[#252525] hover:bg-[#1e1e20] rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-40">
            <Save size={13} className="text-ansys-yellow" /> Save Setup
          </button>
          <PDFExport captureId="sim-report" fileName={`HCar_${params.m_s}`} />
          <DataExport results={results} fileName={`HCar_${params.m_s}`} />

          <button id="btn-run" onClick={runSimulation} disabled={isRunning}
            className={`px-5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${isRunning ? "bg-[#222] text-gray-500 cursor-not-allowed" : "bg-ansys-yellow text-black hover:brightness-110 shadow-[0_0_20px_rgba(242,169,0,0.2)]"}`}>
            {isRunning ? <><div className="w-3 h-3 border border-gray-600 border-t-gray-300 rounded-full animate-spin" />Solving…</> : <><Play size={13} fill="currentColor" /> Run Solver</>}
          </button>
        </div>
      </div>

      {/* Screen Reader Live Solver Announcer */}
      <div className="sr-only" role="status" aria-live="polite">
        {isRunning
          ? "Solving 4-DOF half car ODE system..."
          : results
          ? `Simulation completed. Heave frequency: ${(results as any).f_n_heave?.toFixed(2) ?? "N/A"} Hertz, Pitch frequency: ${(results as any).f_n_pitch?.toFixed(2) ?? "N/A"} Hertz`
          : ""}
      </div>

      <div className="flex flex-1 gap-4 overflow-hidden min-h-0">
        <div className="w-60 shrink-0 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-y-auto custom-scrollbar">
          <div className="px-4 py-3 border-b border-[#1e1e1e] sticky top-0 bg-[#0d0d0f] z-10"><h2 className="text-xs font-semibold text-gray-300 flex items-center gap-2"><Settings2 size={13} className="text-ansys-yellow" /> Parameters</h2></div>
          <div className="p-4 space-y-5">
            <VehiclePresets onSelect={(p) => setParams(prev => ({ ...prev, ...p.params, road_profile: p.road_profile.profile_type, amplitude: p.road_profile.amplitude, frequency: p.road_profile.frequency, duration: p.road_profile.duration }))} />
            <ParamSection title="Sprung Mass">
              <ParameterInput label="Total Mass" val={params.m_s} unit="kg" min={1} onChange={(v) => setParams({ ...params, m_s: v })} />
              <ParameterInput label="Pitch Inertia Iy" val={params.I_y} unit="kg·m²" min={1} onChange={(v) => setParams({ ...params, I_y: v })} />
              <ParameterInput label="Wheelbase L" val={params.L} unit="m" step={0.1} min={0.1} onChange={(v) => setParams({ ...params, L: v })} />
              <ParameterInput label="Weight Dist (F)" val={params.weight_dist} unit="%" step={1} min={10} onChange={(v) => setParams({ ...params, weight_dist: v })} />
            </ParamSection>
            <ParamSection title="Front Axle">
              <ParameterInput label="Unsprung Mass (F)" val={params.m_uf} unit="kg" onChange={(v) => setParams({ ...params, m_uf: v })} />
              <ParameterInput label="Spring Rate (F)" val={params.k_sf} unit="N/m" step={500} onChange={(v) => setParams({ ...params, k_sf: v })} />
              <ParameterInput label="Damping (F)" val={params.c_f} unit="N·s/m" step={50} onChange={(v) => setParams({ ...params, c_f: v })} />
              <ParameterInput label="Tire Stiffness (F)" val={params.k_tf} unit="N/m" step={5000} onChange={(v) => setParams({ ...params, k_tf: v })} />
              <DamperLUTInput label="Non-Linear Front Damper" isActive={params.damper_curve_v_f !== null} onApply={(v, f) => setParams({ ...params, damper_curve_v_f: v, damper_curve_f_f: f })} onClear={() => setParams({ ...params, damper_curve_v_f: null, damper_curve_f_f: null })} />
            </ParamSection>
            <ParamSection title="Rear Axle">
              <ParameterInput label="Unsprung Mass (R)" val={params.m_ur} unit="kg" onChange={(v) => setParams({ ...params, m_ur: v })} />
              <ParameterInput label="Spring Rate (R)" val={params.k_sr} unit="N/m" step={500} onChange={(v) => setParams({ ...params, k_sr: v })} />
              <ParameterInput label="Damping (R)" val={params.c_r} unit="N·s/m" step={50} onChange={(v) => setParams({ ...params, c_r: v })} />
              <ParameterInput label="Tire Stiffness (R)" val={params.k_tr} unit="N/m" step={5000} onChange={(v) => setParams({ ...params, k_tr: v })} />
              <DamperLUTInput label="Non-Linear Rear Damper" isActive={params.damper_curve_v_r !== null} onApply={(v, f) => setParams({ ...params, damper_curve_v_r: v, damper_curve_f_r: f })} onClear={() => setParams({ ...params, damper_curve_v_r: null, damper_curve_f_r: null })} />
            </ParamSection>
            <ParamSection title="Road Profile">
              <div className="flex justify-between items-center gap-2">
                <label htmlFor="half-car-road-profile" className="text-[11px] text-gray-400 flex-1">Profile Type</label>
                <select id="half-car-road-profile" aria-label="Road profile type" value={params.road_profile} onChange={(e) => setParams({ ...params, road_profile: e.target.value })}
                  className="bg-[#0d0d0d] border border-[#252525] text-[11px] rounded-lg px-2 py-1.5 text-white w-28 focus:outline-none focus:border-ansys-yellow/60">
                  <option value="step">Step</option>
                  <option value="sine">Sine Wave</option>
                  <option value="bump">Single Bump</option>
                  <option value="pothole">Pothole</option>
                  <option value="random">Random Rough</option>
                </select>
              </div>
              <ParameterInput label="Amplitude" val={params.amplitude} unit="m" step={0.005} min={0.001} onChange={(v) => setParams({ ...params, amplitude: v })} />
              <ParameterInput label="Duration" val={params.duration} unit="s" step={0.5} min={0.5} onChange={(v) => setParams({ ...params, duration: v })} />
              {params.road_profile === "sine" && <ParameterInput label="Frequency" val={params.frequency} unit="Hz" step={0.5} min={0.1} onChange={(v) => setParams({ ...params, frequency: v })} />}
            </ParamSection>
          </div>
        </div>

        <div className="flex-1 flex flex-col gap-3 min-w-0 overflow-hidden">
          {!results && !isRunning && (
            <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl flex flex-col items-center justify-center gap-4">
              <div className="w-16 h-16 rounded-2xl bg-ansys-yellow/5 border border-ansys-yellow/10 flex items-center justify-center"><Activity size={32} strokeWidth={1} className="text-ansys-yellow/40" /></div>
              <div className="text-center"><p className="text-sm font-semibold text-gray-400 mb-1">Configure parameters and click <span className="text-ansys-yellow">Run Solver</span></p><p className="text-xs text-gray-400">4-DOF half car · RK45 ODE · Pitch & Heave coupling</p></div>
            </div>
          )}

          {isRunning && (
            <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl flex flex-col items-center justify-center gap-4">
              <div className="w-10 h-10 border-2 border-ansys-yellow/20 border-t-ansys-yellow rounded-full animate-spin" />
              <div className="text-center"><p className="text-sm font-medium text-gray-400 mb-1">Running RK45 ODE solver…</p></div>
            </div>
          )}

          {results && results.error ? (
            <div role="alert" aria-live="assertive" className="flex-1 bg-[#111113] border border-red-900/30 rounded-xl flex flex-col items-center justify-center gap-3">
              <AlertTriangle size={44} className="text-red-500 opacity-60" /><p className="text-sm font-semibold text-red-400">Simulation Error</p>
              <pre className="text-xs text-red-400 max-w-sm text-center font-mono bg-red-950/30 px-4 py-2 rounded-lg border border-red-900/20 whitespace-pre-wrap">{results.message as string}</pre>
            </div>
          ) : null}

          {hasResults && r && (
            <div id="sim-report" className="flex flex-col gap-3 flex-1 overflow-hidden">
              <ComparePanel current={r as unknown as React.ComponentProps<typeof ComparePanel>["current"]} />

              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 shrink-0">
                <KPICard label="Heave Freq ƒₙ" value={r.f_n_heave} unit="Hz" status={r.f_n_heave >= 1.0 && r.f_n_heave <= 1.5 ? "good" : "warn"} />
                <KPICard label="Pitch Freq ƒₙ" value={r.f_n_pitch} unit="Hz" status={r.f_n_pitch >= 1.2 && r.f_n_pitch <= 1.8 ? "good" : "warn"} />
                <KPICard label="F. Wheel-Hop" value={r.f_n_uf} unit="Hz" status="neutral" />
                <KPICard label="R. Wheel-Hop" value={r.f_n_ur} unit="Hz" status="neutral" />
                <KPICard label="RMS Heave" value={r.rms_heave_accel} unit="m/s²" status={r.rms_heave_accel < 0.315 ? "good" : r.rms_heave_accel < 1.0 ? "warn" : "bad"} />
                <KPICard label="RMS Pitch" value={r.rms_pitch_accel} unit="rad/s²" status="neutral" />
                <KPICard label="RMS Susp F" value={r.rms_susp_travel_f * 1000} unit="mm" status="neutral" />
                <KPICard label="RMS Susp R" value={r.rms_susp_travel_r * 1000} unit="mm" status="neutral" />
              </div>

              <div className="flex gap-1.5 shrink-0" role="tablist" aria-label="Half-car simulation views">
                {TABS.map((tab, i) => {
                  const Icon = tab.icon;
                  return (
                    <button
                      key={tab.label}
                      role="tab"
                      aria-selected={activeTab === i}
                      onClick={() => setActiveTab(i)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                        activeTab === i
                          ? "bg-ansys-yellow text-black shadow-[0_0_12px_rgba(242,169,0,0.2)]"
                          : "bg-[#111113] border border-[#1e1e1e] text-gray-400 hover:text-white hover:border-[#2a2a2a]"
                      }`}
                    >
                      <Icon size={12} aria-hidden="true" /> {tab.label}
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
                          { x: r.time, y: r.z_s?.map((v: number) => v * 1000), type: "scatter" as any, mode: "lines" as any, name: "CG Heave z_s", line: { color: "#f2a900", width: 2 } },
                          { x: r.time, y: r.z_uf?.map((v: number) => v * 1000), type: "scatter" as any, mode: "lines" as any, name: "Front z_uf", line: { color: "#00aeff", width: 1.5 } },
                          { x: r.time, y: r.z_ur?.map((v: number) => v * 1000), type: "scatter" as any, mode: "lines" as any, name: "Rear z_ur", line: { color: "#ff2d55", width: 1.5 } },
                          { x: r.time, y: r.z_rf?.map((v: number) => v * 1000), type: "scatter" as any, mode: "lines" as any, name: "Road Front", line: { color: "#555", width: 1, dash: "dash" as any } },
                          { x: r.time, y: r.z_rr?.map((v: number) => v * 1000), type: "scatter" as any, mode: "lines" as any, name: "Road Rear", line: { color: "#333", width: 1, dash: "dash" as any } },
                        ]}
                        layout={darkLayout({ title: { text: "Vertical Displacements", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Displacement (mm)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ { x: r.time, y: r.theta?.map((v: number) => v * 180 / Math.PI), type: "scatter" as any, mode: "lines" as any, name: "Pitch Angle θ", line: { color: "#00ff87", width: 2 } } ]}
                        layout={darkLayout({ title: { text: "Pitch Angle", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Pitch (°)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ { x: r.time, y: r.ddz_s, type: "scatter" as any, mode: "lines" as any, name: "Heave Accel z̈_s", line: { color: "#bf5af2", width: 2 }, fill: "tozeroy", fillcolor: "rgba(191,90,242,0.05)" } ]}
                        layout={darkLayout({ title: { text: "Heave Acceleration", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Acceleration (m/s²)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ { x: r.time, y: r.ddtheta, type: "scatter" as any, mode: "lines" as any, name: "Pitch Accel θ̈", line: { color: "#ff9f0a", width: 2 }, fill: "tozeroy", fillcolor: "rgba(255,159,10,0.05)" } ]}
                        layout={darkLayout({ title: { text: "Pitch Acceleration", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Acceleration (rad/s²)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                )}

                {/* ── TAB 1: PITCH-HEAVE COUPLING ── */}
                {activeTab === 1 && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[350px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    <PlotBox>
                      <Plot
                        data={[ { x: r.z_s?.map((v: number) => v * 1000), y: r.theta?.map((v: number) => v * 180 / Math.PI), type: "scatter" as any, mode: "lines" as any, name: "Coupling", line: { color: "#f2a900", width: 1.5 } } ]}
                        layout={darkLayout({ title: { text: "Heave vs Pitch Coupling", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Heave z_s (mm)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Pitch θ (°)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.susp_travel_f?.map((v: number) => v * 1000), type: "scatter" as any, mode: "lines" as any, name: "Front Travel", line: { color: "#00aeff", width: 1.5 } },
                          { x: r.time, y: r.susp_travel_r?.map((v: number) => v * 1000), type: "scatter" as any, mode: "lines" as any, name: "Rear Travel", line: { color: "#ff2d55", width: 1.5 } }
                        ]}
                        layout={darkLayout({ title: { text: "Suspension Travels", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Travel (mm)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.tire_load_f, type: "scatter" as any, mode: "lines" as any, name: "Front Tire ΔFz", line: { color: "#00aeff", width: 1.5 } },
                          { x: r.time, y: r.tire_load_r, type: "scatter" as any, mode: "lines" as any, name: "Rear Tire ΔFz", line: { color: "#ff2d55", width: 1.5 } }
                        ]}
                        layout={darkLayout({ title: { text: "Dynamic Tire Load Variation", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "ΔFz (N)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <div className="h-full p-5 flex flex-col justify-center gap-4">
                        <p className="text-[10px] font-bold tracking-widest text-gray-700 uppercase">Pitch Center Geometry</p>
                        <div className="space-y-3 font-mono text-xs">
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Static Pitch Center</span><span className="text-[#00ff87]">Analytic</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Wheelbase (L)</span><span className="text-white">{params.L} m</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Front weight bias</span><span className="text-[#f2a900]">{params.weight_dist}%</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Olcott Bounce Ratio</span><span className="text-gray-400">{((params.k_sf * (params.L - params.L * params.weight_dist / 100.0) ** 2) / (params.k_sr * (params.L * params.weight_dist / 100.0) ** 2)).toFixed(2)}</span></div>
                        </div>
                      </div>
                    </PlotBox>
                  </div>
                )}

                {/* ── TAB 2: PHASE SPACE ── */}
                {activeTab === 2 && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[350px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    <PlotBox>
                      <Plot
                        data={[ { x: r.z_s?.map((v: number) => v * 1000), y: r.dz_s?.map((v: number) => v * 1000), type: "scatter" as any, mode: "lines" as any, name: "Heave Phase", line: { color: "#f2a900", width: 1.5 } } ]}
                        layout={darkLayout({ title: { text: "Heave Phase Portrait", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "z_s (mm)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "ż_s (mm/s)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ { x: r.theta?.map((v: number) => v * 180 / Math.PI), y: r.dtheta?.map((v: number) => v * 180 / Math.PI), type: "scatter" as any, mode: "lines" as any, name: "Pitch Phase", line: { color: "#00ff87", width: 1.5 } } ]}
                        layout={darkLayout({ title: { text: "Pitch Phase Portrait", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "θ (°)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "θ̇ (°/s)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ { x: r.z_uf?.map((v: number) => v * 1000), y: r.z_ur?.map((v: number) => v * 1000), type: "scatter" as any, mode: "lines" as any, name: "Wheel Tracking", line: { color: "#00aeff", width: 1.5 } } ]}
                        layout={darkLayout({ title: { text: "Front vs Rear Wheel Tracking", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Front z_uf (mm)", font: { color: "#444", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Rear z_ur (mm)", font: { color: "#444", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <div className="h-full p-5 flex flex-col justify-center gap-4">
                        <p className="text-[10px] font-bold tracking-widest text-gray-700 uppercase">State-Space Eigenvalues</p>
                        <div className="space-y-3 font-mono text-xs">
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Heave Mode</span><span className="text-[#f2a900]">{r.f_n_heave.toFixed(2)} Hz</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Pitch Mode</span><span className="text-[#00ff87]">{r.f_n_pitch.toFixed(2)} Hz</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Front Hop</span><span className="text-[#00aeff]">{r.f_n_uf.toFixed(2)} Hz</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Rear Hop</span><span className="text-[#ff2d55]">{r.f_n_ur.toFixed(2)} Hz</span></div>
                        </div>
                      </div>
                    </PlotBox>
                  </div>
                )}

                {/* ── TAB 3: PSD ANALYSIS ── */}
                {activeTab === 3 && psdData && psdPitch && (
                  <div className="grid grid-cols-2 grid-rows-1 h-full gap-px bg-[#181818]">
                    <PlotBox>
                      <Plot
                        data={[ { x: psdData.freqs, y: psdData.psd, type: "scatter" as any, mode: "lines" as any, name: "PSD Heave", fill: "tozeroy", fillcolor: "rgba(242,169,0,0.06)", line: { color: "#f2a900", width: 2 } } ]}
                        layout={darkLayout({ title: { text: "PSD — Heave Acceleration", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#444", size: 10 } }, type: "log", range: [Math.log10(0.1), Math.log10(50)] }, yaxis: { ...DARK_BASE.yaxis, title: { text: "PSD ((m/s²)²/Hz)", font: { color: "#444", size: 10 } }, type: "log" } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ { x: psdPitch.freqs, y: psdPitch.psd, type: "scatter" as any, mode: "lines" as any, name: "PSD Pitch", fill: "tozeroy", fillcolor: "rgba(0,255,135,0.06)", line: { color: "#00ff87", width: 2 } } ]}
                        layout={darkLayout({ title: { text: "PSD — Pitch Acceleration", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#444", size: 10 } }, type: "log", range: [Math.log10(0.1), Math.log10(50)] }, yaxis: { ...DARK_BASE.yaxis, title: { text: "PSD ((rad/s²)²/Hz)", font: { color: "#444", size: 10 } }, type: "log" } })}
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
      <HalfCarDashboard />
    </Suspense>
  );
}

