// TypeScript type safety fully enabled — @ts-nocheck removed (was CRIT-05)

"use client";
import { useState, useEffect, Suspense, useMemo } from "react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import {
  Play, Settings2, AlertTriangle,
  Activity, Save, Sparkles, X, TrendingUp, BarChart3,
  Zap, GitBranch, Crosshair, RefreshCw,
} from "lucide-react";
import PDFExport from "../../components/PDFExport";
import DataExport from "../../components/DataExport";
import VehiclePresets from "../../components/VehiclePresets";
import TraceManager, { Trace } from "../../components/TraceManager";
import {
  bDisp, bVel, bAccel, bTravel, bTrans, bBodeMag, bBodePhase, bDynLoad,
  bForces, bFV, bFx, bPower, bPhaseS, bPhaseU, bComfortTravel, bPSD
} from "../../components/plotHelpers";
import SimHistory, { saveSimulationToHistory } from "../../components/SimHistory";
import PlanGate from "../../components/PlanGate";
import DamperLUTInput from "../../components/DamperLUTInput";
import RoadProfileUpload from "../../components/RoadProfileUpload";
import { useAuth } from "../../contexts/AuthContext";
import SuspensionRig3D from "../../components/SuspensionRig3D";
import Rig3DPlayer from "../../components/Rig3DPlayer";
import KPIRibbon from "../../components/quarter-car/KPIRibbon";
import SetupScoreBadge from "../../components/SetupScoreBadge";
import { ParamSection, ParameterInput } from "../../components/sim/ParameterControls";
import { useQuarterCarSimulation } from "../../hooks/useQuarterCarSimulation";
import SmartInsights from "../../components/SmartInsights";
import SensitivityTornado from "../../components/SensitivityTornado";
import ModelValidity, { ValidityReport } from "../../components/ModelValidity";
import EngineeringDecisionCard from "../../components/sim/EngineeringDecisionCard";
import EngineeringErrorDisplay from "../../components/sim/EngineeringErrorDisplay";
import { SyncChartProvider, useSyncChart } from "../../components/sim/SyncChartContext";
import { Brain, FlaskConical, Loader2 } from "lucide-react";

import Plot from "../../components/sim/Plot";
import KPICard from "../../components/sim/KPICard";
import PlotBox from "../../components/sim/PlotBox";
import { darkLayout, DARK_BASE } from "../../components/sim/theme";
import { promptModal, alertModal } from "../../components/sim/ModalHost";
import PlotTabs, { type PlotTabDef } from "../../components/sim/PlotTabs";
import { maxOf, minOf } from "../../lib/array";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ROAD_PROFILES = [
  { label: "Step Input",              value: "step"    },
  { label: "Pothole",                 value: "pothole" },
  { label: "Sine Wave",               value: "sine"    },
  { label: "Multi-Harmonic Random",   value: "random"  },
  { label: "Impulse",                 value: "impulse" },
  { label: "ISO 8608 Stochastic",     value: "iso8608" },
];

const ISO_CLASSES = ["A", "B", "C", "D", "E", "F", "G", "H"] as const;
type IsoClass = typeof ISO_CLASSES[number];

const TABS: PlotTabDef[] = [
  { label: "Time Domain",       icon: TrendingUp  },
  { label: "Bode / FRF",        icon: BarChart3   },
  { label: "Forces & Energy",   icon: Zap         },
  { label: "Phase Space",       icon: GitBranch   },
  { label: "PSD Analysis",      icon: Crosshair   },
  { label: "Smart Insights",    icon: Brain       },
  { label: "Sensitivity",       icon: FlaskConical },
];

// ──────── Plotly dark-theme base ───────────
type SimResult = 
  | { error: true; message: string; detail?: string }
  | { error?: false; time: number[]; z_s: number[]; z_u: number[]; dz_s: number[]; dz_u: number[]; f_n_s: number; zeta_s: number; [key: string]: any };

// ————————————————— Types ————————————————————————————————————————————————————————
type Status = "good" | "warn" | "bad" | "neutral";
type Toast  = { msg: string; type: "success" | "error" | "info" };

// ————————————————— KPI helpers —————————————————————————————————————————————————
function getDampingStatus(z: number): Status {
  if (z >= 0.25 && z <= 0.6) return "good";
  if (z >= 0.1  && z <= 0.8) return "warn";
  return "bad";
}
// MED-01 FIX: getComfortStatus must use Wk-weighted RMS (ISO 2631-1 boundary values are for Wk)
function getComfortStatus(rmsWk: number): Status {
  if (rmsWk < 0.315) return "good";
  if (rmsWk < 1.0)   return "warn";
  return "bad";
}
function getTXStatus(tx: number): Status {
  if (tx < 2.0) return "good";
  if (tx < 3.5) return "warn";
  return "bad";
}

// ————————————————— Sub-components —————————————————————————————————————————————

// ————————————————— Plot wrappers —————————————————————————————————————————————
// ————————————————— Main dashboard —————————————————————————————————————————————
function QuarterCarDashboard() {
  const searchParams = useSearchParams();
  const { authHeader, fetchWithAuth } = useAuth();

  const [isSaving,  setIsSaving]  = useState<boolean>(false);
  const [isTuning,  setIsTuning]  = useState<boolean>(false);
  const [traces,    setTraces]    = useState<Trace[]>([]);
  const [deltaMode, setDeltaMode] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<number>(0);
  const [toast,     setToast]     = useState<Toast | null>(null);
  const [autoRun, setAutoRun] = useState(false);
  const [customRoad, setCustomRoad] = useState<{
    time: number[];
    displacement: number[];
    duration: number;
    sampleRate: number;
    pointCount: number;
    fileName: string;
  } | null>(null);

  const showToast = (msg: string, type: Toast["type"]) => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  // P1-ARCH-01: simulation domain logic lives in the hook
  const {
    isRunning, setIsRunning,
    loadingStage,
    cancelSimulation,
    retrySimulation,
    retryCount,
    results, setResults,
    simError, setSimError,
    validity,
    simParams,
    params, setParams,
    buildPayload,
    runSimulation,
  } = useQuarterCarSimulation({ authHeader, showToast, autoRun });

  const { cursorTime, setTelemetryCursor } = useSyncChart();
  const cursorShape = useMemo(() => {
    if (cursorTime === null) return [];
    return [
      {
        type: "line" as const,
        x0: cursorTime,
        x1: cursorTime,
        y0: 0,
        y1: 1,
        yref: "paper" as const,
        line: { color: "#f2a900", width: 1.5, dash: "dot" as const },
      },
    ];
  }, [cursorTime]);

  const onTimePlotHover = (ev: any) => {
    const pt = ev.points?.[0];
    if (pt && typeof pt.x === "number") {
      let phase = "Steady Equilibrium";
      if (pt.x < 0.1) phase = "Pre-Excitation";
      else if (pt.x < 0.5) phase = "Curb Strike / Bump Transient";
      else if (pt.x < 1.2) phase = "Rebound Oscillation";
      else if (pt.x < 2.5) phase = "Damper Dissipation Phase";
      setTelemetryCursor(pt.x, phase, pt.x * (params.speed_mps || 20));
    }
  };

  // MIN-07: Dismiss toast on Escape key
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => { if (e.key === "Escape") setToast(null); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    const profileId = searchParams.get("load");
    if (!profileId) return;
    fetchWithAuth(`/api/v1/profiles/${profileId}`)
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((data) => {
        if (data.params) {
          setParams((prev) => ({ ...prev, ...data.params }));
          showToast(`Loaded "${data.name}" from Garage`, "success");
        }
      })
      .catch(() => showToast("Could not load profile", "error"));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const saveProfile = async () => {
    if (isSaving) return;
    const name = await promptModal("Enter a name for this configuration:", "My Setup");
    if (!name) return;
    setIsSaving(true);
    try {
      const r = await fetchWithAuth("/api/v1/profiles/", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ name, vehicle_type: "QUARTER_CAR", params }),
      });
      if (r.ok) showToast("Setup saved to Garage!", "success");
      else      showToast("Failed to save", "error");
    } catch { showToast("Failed to save profile", "error"); }
    finally { setIsSaving(false); }
  };

  const [isMagicModalOpen, setIsMagicModalOpen] = useState(false);
  const [magicGoal, setMagicGoal] = useState("");

  const autoTune = async () => {
    if (!magicGoal.trim() || isTuning) return;
    setIsTuning(true);
    try {
      const res = await fetchWithAuth("/api/v1/ai/chat", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ problem: magicGoal.trim(), params }),
      });
      const data = await res.json();
      if (res.ok) {
        const recMap: Record<string, number> = {};
        if (Array.isArray(data.best_feasible)) {
          data.best_feasible.forEach((item: any) => {
            if (item?.parameter && typeof item.recommended_value === "number") {
              recMap[item.parameter] = item.recommended_value;
            }
          });
        }
        if (Array.isArray(data.recommendations)) {
          data.recommendations.forEach((item: any) => {
            if (item?.parameter && typeof item.recommended_value === "number") {
              recMap[item.parameter] = item.recommended_value;
            }
          });
        }
        if (data.params && typeof data.params === "object") {
          Object.entries(data.params).forEach(([k, v]) => {
            if (typeof v === "number") recMap[k] = v;
          });
        }

        setParams((prev) => ({ 
          ...prev, 
          m_s: recMap["m_s"] ?? (typeof data.m_s === "number" ? data.m_s : prev.m_s),
          m_u: recMap["m_u"] ?? (typeof data.m_u === "number" ? data.m_u : prev.m_u),
          k_s: recMap["k_s"] ?? (typeof data.k_s === "number" ? data.k_s : prev.k_s),
          c:   recMap["c"]   ?? (typeof data.c === "number" ? data.c : prev.c),
          k_t: recMap["k_t"] ?? (typeof data.k_t === "number" ? data.k_t : prev.k_t),
          MR:  recMap["MR"]  ?? (typeof data.MR === "number" ? data.MR : prev.MR),
        }));

        const explanationText = data.explanation || data.answer || data.setup_summary || "Setup optimized based on vehicle physics.";
        showToast(`AI Tuned: ${String(explanationText).slice(0, 90)}`, "success");
        setIsMagicModalOpen(false);
        setMagicGoal("");
        setTimeout(() => document.getElementById("btn-run")?.click(), 800);
      } else {
        showToast(data.detail || data.message || "Auto-tune failed", "error");
      }
    } catch { showToast("Failed to reach generative optimizer", "error"); }
    finally { setIsTuning(false); }
  };

  // ————————————————— Derived: PSD from acceleration time series (Welch-style via FFT) —————
  const psdData = useMemo(() => {
    if (!results || results.error) return null;
    if (!results.psd_freqs || !results.psd_values) return null;
    if (!Array.isArray(results.psd_freqs) || !Array.isArray(results.psd_values)) return null;
    return {
      freqs: results.psd_freqs as number[],
      psd: results.psd_values as number[]
    };
  }, [results]);

  // MED-07: Forces computed from SNAPSHOTTED params (simParams), not current live params
  const forces = useMemo(() => {
    if (!results || results.error) return null;
    const p = simParams ?? params; // fall back to current if snapshot not yet available
    const zs = results.z_s as number[];
    const zu = results.z_u as number[];
    const vs = results.dz_s as number[];
    const vu = results.dz_u as number[];
    if (!Array.isArray(zs) || !Array.isArray(zu) || !Array.isArray(vs) || !Array.isArray(vu)) return null;
    const ksVal = typeof p?.k_s === "number" ? p.k_s : 35000;
    const mrVal = typeof p?.MR === "number" ? p.MR : 1.0;
    const cVal  = typeof p?.c === "number" ? p.c : 1500;
    const kw = ksVal * mrVal * mrVal;
    const cw = cVal   * mrVal * mrVal;
    const F_spring = zs.map((z, i) => kw * (z - (zu[i] ?? 0)));
    const F_damper = vs.map((v, i) => cw * (v - (vu[i] ?? 0)));
    const F_total  = F_spring.map((fs, i) => fs + (F_damper[i] ?? 0));
    const relVel   = vs.map((v, i) => v - (vu[i] ?? 0));
    return { F_spring, F_damper, F_total, relVel };
  }, [results, simParams, params]); // NOT dependent on live `params`

  const hasResults = results && !results.error;

  const r = results as Record<string, unknown> & {
    time: number[]; z_s: number[]; z_u: number[]; z_r: number[];
    dz_s: number[]; dz_u: number[];
    ddz_s: number[]; susp_travel: number[]; tire_defl: number[];
    tire_load_var: number[];
    freq_hz: number[]; transmissibility_body: number[];
    transmissibility_wheel: number[]; bode_magnitude_db: number[];
    bode_phase_deg: number[];
    f_n_s: number; f_n_u: number; zeta_s: number; zeta_u: number;
    omega_n_s: number; c_crit_s: number;
    peak_transmissibility: number; freq_at_peak_tx: number;
    rms_body_accel: number; rms_body_accel_wk: number;
    rms_susp_travel: number; rms_tire_load: number;
    peak_susp_travel: number; comfort_rating: string; k_w: number;
  } | null;

  return (
    <div className="h-full flex flex-col p-5 pt-3 gap-3 min-h-0">

      {/* Toast */}
      {toast && (
        <div role="alert" aria-live="polite" className={`fixed top-14 right-4 z-50 flex items-center gap-3 px-4 py-3 rounded-xl
          shadow-2xl border text-sm font-medium transition-all
          ${toast.type === "success"
            ? "bg-[#0a1f12] border-emerald-800/50 text-emerald-300"
            : "bg-[#1f0a0a] border-red-800/50 text-red-300"}`}
        >
          {toast.msg}
          <button
            onClick={() => setToast(null)}
            aria-label="Dismiss notification"
            className="opacity-50 hover:opacity-100 ml-1 p-0.5"
          >
            <X size={13} />
          </button>
        </div>
      )}

      {/* Screen Reader Live Solver Announcer */}
      <div className="sr-only" role="status" aria-live="polite">
        {isRunning
          ? "Solving 2-DOF quarter car ODE system..."
          : results && !("error" in results && results.error)
          ? `Simulation completed. Natural frequency: ${(results as any).metrics?.fn_hz?.toFixed(2) ?? "N/A"} Hertz, damping ratio: ${(results as any).metrics?.zeta_s?.toFixed(2) ?? "N/A"}`
          : ""}
      </div>


      {/* Toolbar */}
      <div className="flex items-center justify-between shrink-0 pb-3 border-b border-[#1e1e1e]">
        <div className="flex flex-col">
          <span className="text-[9px] font-bold tracking-[0.25em] text-ansys-yellow uppercase">
            2-DOF Vertical Dynamics · BDF Stiff ODE
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-white leading-tight">Quarter Car</h1>
        </div>

        <div className="flex items-center gap-2">
          <SimHistory storageKey="sl_sim_history_qcar" onRestore={(p) => { setParams(prev => ({ ...prev, ...p })); showToast("Restored from history", "success"); }} />
          <button onClick={saveProfile} disabled={isSaving}
            className="px-3 py-1.5 bg-[#141416] border border-[#252525] hover:bg-[#1e1e20] rounded-lg
              text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-40">
            <Save size={13} className="text-ansys-yellow" />
            {isSaving ? "Saving…" : "Save Setup"}
          </button>
          <PDFExport captureId="sim-report" fileName={`QCar_${Math.round(params.k_s)}_${Math.round(params.c)}`} />
          <DataExport results={results} fileName={`QCar_${Math.round(params.k_s)}_${Math.round(params.c)}`} />

          <button id="btn-run" onClick={() => runSimulation()} disabled={isRunning}
            className={`px-5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
              isRunning
                ? "bg-[#222] text-gray-500 cursor-not-allowed"
                : "bg-ansys-yellow text-black hover:brightness-110 shadow-[0_0_20px_rgba(242,169,0,0.2)]"
            }`}>
            {isRunning ? (
              <><div className="w-3 h-3 border border-gray-600 border-t-gray-300 rounded-full animate-spin" />Solving…</>
            ) : (
              <><Play size={13} fill="currentColor" /> Run Solver</>
            )}
          </button>

          <button onClick={() => setAutoRun(!autoRun)}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
              autoRun 
                ? "bg-emerald-950/60 text-emerald-400 border border-emerald-900/50" 
                : "bg-[#141416] border border-[#252525] hover:bg-[#1e1e20] text-gray-400"
            }`}>
            <RefreshCw size={13} className={autoRun ? "animate-spin-slow" : ""} />
            {autoRun ? "Live Update: ON" : "Live Update"}
          </button>

          <PlanGate required="PRO" compact feature="AI Auto-Tune">
            <button onClick={() => setIsMagicModalOpen(true)} disabled={isTuning}
              className="px-4 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-xs font-bold
                flex items-center gap-1.5 transition-colors border border-cyan-400/30
                disabled:opacity-50 disabled:cursor-not-allowed">
              <Sparkles size={13} /> AI Auto-Tune
            </button>
          </PlanGate>
        </div>
      </div>

      {/* Magic Wand Modal */}
      {isMagicModalOpen ? (
        <div
          className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="autotune-modal-title"
          onKeyDown={(e) => {
            if (e.key === "Escape") setIsMagicModalOpen(false);
          }}
        >
          <div className="w-full max-w-lg bg-[#111113] border border-[#222] rounded-2xl p-6 shadow-2xl">
            <h3 id="autotune-modal-title" className="text-lg font-semibold text-white flex items-center gap-2 mb-2">
              <Sparkles className="text-[#5e17eb]" size={20} /> Generative AI Auto-Tuner
            </h3>
            <p className="text-sm text-gray-400 mb-4">
              Describe the vehicle dynamics problem you want to solve in plain English. The AI will mathematically optimize your parameters and re-run the simulation.
            </p>
            <label htmlFor="magic-goal-input" className="sr-only">Optimization goal description</label>
            <textarea 
              id="magic-goal-input"
              autoFocus
              className="w-full h-24 bg-[#0d0d0f] border border-[#2a2a2a] rounded-xl p-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-[#5e17eb] focus:ring-1 focus:ring-[#5e17eb]/30 mb-4"
              placeholder="e.g., 'Make the ride much softer over this bumpy road without letting the suspension bottom out.'"
              value={magicGoal}
              onChange={(e) => setMagicGoal(e.target.value)}
            />
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setIsMagicModalOpen(false)}
                className="px-4 py-2 text-sm text-gray-300 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={autoTune}
                disabled={isTuning || !magicGoal.trim()}
                className="px-5 py-2 bg-[#5e17eb] hover:bg-[#7c3aed] text-white rounded-xl text-sm font-bold flex items-center gap-2 transition-colors disabled:opacity-50 shadow-[0_0_15px_rgba(94,23,235,0.4)]"
              >
                {isTuning ? "Optimizing..." : "Optimize Setup"} <Sparkles size={14} />
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Body */}
      <div className="flex flex-1 gap-4 overflow-hidden min-h-0">

        {/* Left Panel */}
        <div className="w-60 shrink-0 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-y-auto custom-scrollbar">
          <div className="px-4 py-3 border-b border-[#1e1e1e] sticky top-0 bg-[#0d0d0f] z-10">
            <h2 className="text-xs font-semibold text-gray-300 flex items-center gap-2">
              <Settings2 size={13} className="text-ansys-yellow" /> Parameters
            </h2>
          </div>
          <div className="p-4 space-y-5">
            <VehiclePresets onSelect={(p) => setParams(prev => ({ ...prev, ...p.params, road_profile: p.road_profile.profile_type, amplitude: p.road_profile.amplitude, frequency: p.road_profile.frequency, duration: p.road_profile.duration }))} />
            <ParamSection title="Mass">
              <ParameterInput label="Sprung Mass"   val={params.m_s} unit="kg"    min={1}    hasError={params.m_s <= 0} onChange={(v) => setParams({ ...params, m_s: v })} />
              <ParameterInput label="Unsprung Mass" val={params.m_u} unit="kg"    min={1}    hasError={params.m_u <= 0} onChange={(v) => setParams({ ...params, m_u: v })} />
            </ParamSection>
            <ParamSection title="Suspension">
              <ParameterInput label="Spring Rate"    val={params.k_s} unit="N/m"   step={500} hasError={params.k_s <= 0} onChange={(v) => setParams({ ...params, k_s: v })} />
              <ParameterInput label="Damping"        val={params.c}   unit="N·s/m" step={50}  hasError={params.c < 0} onChange={(v) => setParams({ ...params, c:   v })} />
              <ParameterInput label="Tire Stiffness" val={params.k_t} unit="N/m"   step={5000} hasError={params.k_t <= 0} onChange={(v) => setParams({ ...params, k_t: v })} />
              <ParameterInput label="Motion Ratio (spring/wheel)"   val={params.MR}  unit="—"     step={0.01} min={0.1} hasError={params.MR <= 0} onChange={(v) => setParams({ ...params, MR:  v })} />
              <DamperLUTInput 
                label="Non-Linear Damper Curve"
                isActive={params.damper_curve_v !== null}
                onApply={(v, f) => setParams({ ...params, damper_curve_v: v, damper_curve_f: f })}
                onClear={() => setParams({ ...params, damper_curve_v: null, damper_curve_f: null })}
              />
            </ParamSection>
            <ParamSection title="Road Profile">
              <div className="flex justify-between items-center gap-2">
                <label htmlFor="qcar-road-profile" className="text-[11px] text-gray-400 flex-1">Profile</label>
                <select id="qcar-road-profile" aria-label="Road Profile Type" value={params.road_profile} onChange={(e) => setParams({ ...params, road_profile: e.target.value })}
                  className="bg-[#0d0d0d] border border-[#252525] text-[11px] rounded-lg px-2 py-1.5 text-white w-[7.5rem]
                    focus:outline-none focus:border-ansys-yellow/60 focus:ring-1 focus:ring-ansys-yellow/15">
                  {ROAD_PROFILES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
              <ParameterInput label="Amplitude" val={params.amplitude} unit="m"  step={0.005} min={0.001} onChange={(v) => setParams({ ...params, amplitude: v })} />
              <ParameterInput label="Duration"  val={params.duration}  unit="s"  step={0.5}   min={0.5}   onChange={(v) => setParams({ ...params, duration:  v })} />
              {params.road_profile === "sine" && (
                <ParameterInput label="Frequency" val={params.frequency} unit="Hz" step={0.5} min={0.1} onChange={(v) => setParams({ ...params, frequency: v })} />
              )}
              {/* ARCH-05: ISO 8608 road class and speed controls */}
              {params.road_profile === "iso8608" && (
                <>
                  <div className="flex justify-between items-center gap-2">
                    <label htmlFor="qcar-iso-class" className="text-[11px] text-gray-400 flex-1">Road Class</label>
                    <select
                      id="qcar-iso-class"
                      aria-label="ISO 8608 Road Class"
                      value={params.iso_class}
                      onChange={(e) => setParams({ ...params, iso_class: e.target.value as IsoClass })}
                      className="bg-[#0d0d0d] border border-[#252525] text-[11px] rounded-lg px-2 py-1.5 text-white w-[7.5rem] focus:outline-none focus:border-ansys-yellow/60">
                      {ISO_CLASSES.map((cls) => (
                        <option key={cls} value={cls}>Class {cls}</option>
                      ))}
                    </select>
                  </div>
                  <ParameterInput label="Speed" val={params.speed_mps} unit="m/s" step={5} min={1} onChange={(v) => setParams({ ...params, speed_mps: v })} />
                </>
              )}
              <div className="pt-2 border-t border-[#1e1e1e]">
                <span className="text-[10px] text-gray-400 block mb-1.5">Custom Road CSV</span>
                <RoadProfileUpload
                  loaded={customRoad}
                  onLoad={(prof) => {
                    setCustomRoad(prof);
                    const maxAmp = prof.displacement.reduce((acc, v) => Math.max(acc, Math.abs(v)), 0);
                    setParams((prev) => ({
                      ...prev,
                      road_profile: "random",
                      amplitude: Math.max(0.001, Number((maxAmp > 0 ? maxAmp : prev.amplitude).toFixed(4))),
                      duration: Math.min(60, Math.max(0.5, Number(prof.duration.toFixed(2)))),
                    }));
                    showToast(`Loaded road CSV: ${prof.fileName} (${prof.pointCount} pts)`, "success");
                  }}
                  onClear={() => setCustomRoad(null)}
                />
              </div>
            </ParamSection>

            {/* Derived params display */}
            <ParamSection title="Derived">
              {(() => {
                const kw = params.k_s * params.MR * params.MR;
                const cw = params.c * params.MR * params.MR;
                const fs = (1 / (2 * Math.PI)) * Math.sqrt(kw / Math.max(params.m_s, 1e-6));
                const fu = (1 / (2 * Math.PI)) * Math.sqrt((kw + params.k_t) / Math.max(params.m_u, 1e-6));
                const zeta = cw / Math.max(1e-9, 2 * Math.sqrt(kw * Math.max(params.m_s, 1e-6)));
                return (
                  <div className="space-y-1.5 font-mono text-[10px]">
                    <div className="flex justify-between text-gray-500">
                      <span>Sprung Freq f_s</span>
                      <span className="text-ansys-yellow font-bold">{fs.toFixed(2)} Hz</span>
                    </div>
                    <div className="flex justify-between text-gray-500">
                      <span>Unsprung Freq f_u</span>
                      <span className="text-cyan-400 font-bold">{fu.toFixed(2)} Hz</span>
                    </div>
                    <div className="flex justify-between text-gray-500">
                      <span>Damping Ratio ζ</span>
                      <span className="text-emerald-400 font-bold">{zeta.toFixed(3)}</span>
                    </div>
                    <div className="flex justify-between text-gray-600">
                      <span>Wheel Rate k_w</span>
                      <span className="text-gray-400">{kw.toFixed(0)} N/m</span>
                    </div>
                    <div className="flex justify-between text-gray-600">
                      <span>Mass Ratio μ</span>
                      <span className="text-gray-400">{(params.m_u / params.m_s).toFixed(3)}</span>
                    </div>
                    <div className="flex justify-between text-gray-600">
                      <span>Static Defl.</span>
                      <span className="text-gray-400">{((params.m_s * 9.81) / kw * 1000).toFixed(1)} mm</span>
                    </div>
                    <div className="pt-1 border-t border-[#1e1e1e] text-[9px] text-gray-700 leading-tight">
                      k_w = k_s × MR²&nbsp;&nbsp;|&nbsp;&nbsp;MR = spring travel / wheel travel
                    </div>
                  </div>
                );
              })()}
            </ParamSection>
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 flex flex-col gap-3 min-w-0 overflow-hidden">

          {/* Instant Analytical Modal Strip */}
          {(() => {
            const kw = params.k_s * params.MR * params.MR;
            const cw = params.c * params.MR * params.MR;
            const fs = (1 / (2 * Math.PI)) * Math.sqrt(kw / Math.max(params.m_s, 1e-6));
            const fu = (1 / (2 * Math.PI)) * Math.sqrt((kw + params.k_t) / Math.max(params.m_u, 1e-6));
            const zeta = cw / Math.max(1e-9, 2 * Math.sqrt(kw * Math.max(params.m_s, 1e-6)));
            return (
              <div className="bg-[#111113] border border-[#1e1e1e] rounded-xl px-4 py-2 flex flex-wrap items-center justify-between gap-3 shrink-0 font-mono text-xs">
                <span className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">
                  Analytical Modal Preview
                </span>
                <div className="flex flex-wrap items-center gap-5">
                  <div>
                    <span className="text-gray-500 mr-1.5">Sprung f_s:</span>
                    <span className="text-ansys-yellow font-bold">{fs.toFixed(2)} Hz</span>
                  </div>
                  <div>
                    <span className="text-gray-500 mr-1.5">Unsprung f_u:</span>
                    <span className="text-cyan-400 font-bold">{fu.toFixed(2)} Hz</span>
                  </div>
                  <div>
                    <span className="text-gray-500 mr-1.5">Damping ζ:</span>
                    <span className="text-emerald-400 font-bold">{zeta.toFixed(3)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 mr-1.5">Wheel Rate k_w:</span>
                    <span className="text-gray-200">{kw.toFixed(0)} N/m</span>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Empty state */}
          {!results && !isRunning && (
            <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl flex flex-col items-center justify-center gap-4">
              <div className="w-16 h-16 rounded-2xl bg-ansys-yellow/5 border border-ansys-yellow/10 flex items-center justify-center">
                <Activity size={32} strokeWidth={1} className="text-ansys-yellow/40" />
              </div>
              <div className="text-center">
                <p className="text-sm font-semibold text-gray-400 mb-1">
                  Configure parameters and click <span className="text-ansys-yellow">Run Solver</span>
                </p>
                <p className="text-xs text-gray-700">
                  2-DOF quarter car · BDF implicit stiff solver · Impedance matrix FRF · ISO 2631-1 Wk weighting
                </p>
                <div className="flex items-center justify-center gap-4 mt-4">
                  {["Transmissibility", "Bode Magnitude + Phase", "PSD", "Phase Portrait", "F-V Diagram"].map((t) => (
                    <span key={t} className="text-[10px] text-gray-700 bg-[#141416] border border-[#252525] px-2 py-1 rounded-lg">{t}</span>
                  ))}
                </div>
              </div>
            </div>
          )}



          {/* Loading */}
          {isRunning && !hasResults && (
            <div className="flex flex-col gap-3 flex-1 overflow-hidden">
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 shrink-0">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="h-16 bg-[#141416] border border-[#1e1e1e] rounded-xl animate-pulse" />
                ))}
              </div>
              <div className="flex-1 min-h-0 bg-[#111113] border border-[#1e1e1e] rounded-xl flex items-center justify-center relative overflow-hidden">
                <div className="absolute inset-0 bg-gradient-to-b from-[#111113] to-[#0a0a0c] animate-pulse" />
                <div className="flex flex-col items-center gap-3 z-10">
                  <Loader2 size={36} className="text-ansys-yellow animate-spin" />
                  <p className="text-xs text-ansys-yellow font-mono tracking-widest font-bold">
                    {loadingStage === "VALIDATING" && "VALIDATING PARAMETERS & BOUNDS"}
                    {loadingStage === "DISPATCHING" && "DISPATCHING TO PHYSICS CORE"}
                    {loadingStage === "SOLVING_ODE" && "SOLVING ADAPTIVE RK45 ODE SYSTEM"}
                    {loadingStage === "COMPUTING_PSD" && "COMPUTING ISO 8608 PSD & FREQUENCY RESPONSE"}
                    {loadingStage === "EVALUATING_KPIS" && "EVALUATING ISO 2631-1 KPIS"}
                    {!loadingStage && "SOLVING IMPLICIT ODE"}
                  </p>
                  <p className="text-[11px] text-gray-400 font-mono">Real-time state integration in progress</p>
                  <button
                    type="button"
                    onClick={cancelSimulation}
                    className="mt-2 px-3 py-1 bg-red-950/60 border border-red-500/40 hover:bg-red-900/80 text-red-200 rounded-lg text-xs font-mono transition-all flex items-center gap-1.5"
                  >
                    <X size={13} /> Cancel Simulation
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Error: only show centered full error if no previous valid results exist */}
          {!hasResults && Boolean(results?.error || simError) && (
            <div className="flex-1 bg-[#111113] border border-red-900/30 rounded-xl p-6 flex flex-col items-center justify-center">
              <EngineeringErrorDisplay
                error={(results as any)?.message || simError}
                onRetry={retrySimulation}
                onDismiss={() => setSimError(null)}
                retryCount={retryCount}
              />
            </div>
          )}

          {/* Results */}
          {hasResults && r && (
            <div id="sim-report" className="flex flex-col gap-3 flex-1 overflow-y-auto min-h-0 custom-scrollbar pr-1">

              {/* Floating Non-Destructive Error HUD */}
              {simError && (
                <EngineeringErrorDisplay
                  error={simError}
                  onRetry={retrySimulation}
                  onDismiss={() => setSimError(null)}
                  retryCount={retryCount}
                />
              )}

              {/* Issue 16: MODEL VALIDITY — how much to trust this result */}
              <ModelValidity report={validity} />

              {/* 5 Primary User Questions: Engineering Decision Engine */}
              <EngineeringDecisionCard
                currentParams={params}
                baselineParams={simParams}
                results={r}
                validity={validity}
              />

              {/* Trace manager */}
              <TraceManager currentResult={r as any} currentParams={params} traces={traces} setTraces={setTraces} deltaMode={deltaMode} setDeltaMode={setDeltaMode} />

              {/* KPI Ribbon — 8 cards */}
              <KPIRibbon r={r} MR={params.MR} />
              <SetupScoreBadge
                rmsBodyAccel={r.rms_body_accel}
                rmsTireLoadN={r.rms_tire_load}
                peakSuspTravelM={r.peak_susp_travel}
                runKey={`${r.time.length}-${r.rms_body_accel}-${r.rms_tire_load}`}
              />

              {/* Tab nav */}
              <PlotTabs tabs={TABS} activeTab={activeTab} onChange={setActiveTab} />

              {/* Plot area */}
              <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-hidden min-h-[480px]">

                {/* ── TAB 0: TIME DOMAIN — 2×2 grid ── */}
                {activeTab === 0 && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[350px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    {/* Displacement */}
                    <PlotBox
                      title="Displacement"
                      description="Chassis sprung mass and wheel unsprung mass displacement time histories"
                      summaryData={[
                        { label: "Max Body Disp.", value: `${(maxOf(r.z_s) * 1000).toFixed(1)} mm` },
                        { label: "Min Body Disp.", value: `${(minOf(r.z_s) * 1000).toFixed(1)} mm` },
                        { label: "Max Wheel Disp.", value: `${(maxOf(r.z_u) * 1000).toFixed(1)} mm` },
                      ]}
                    >
                      <Plot
                        data={bDisp(r, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Displacement", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#94A3B8", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Displacement (mm)", font: { color: "#94A3B8", size: 10 } } },
                          shapes: [...cursorShape],
                        })}
                        onHover={onTimePlotHover}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Velocity */}
                    <PlotBox
                      title="Velocity"
                      description="Chassis sprung mass and wheel unsprung mass velocity time histories"
                      summaryData={[
                        { label: "Peak Body Vel.", value: `${(maxOf(r.dz_s) * 1000).toFixed(1)} mm/s` },
                        { label: "Min Body Vel.", value: `${(minOf(r.dz_s) * 1000).toFixed(1)} mm/s` },
                        { label: "Peak Wheel Vel.", value: `${(maxOf(r.dz_u) * 1000).toFixed(1)} mm/s` },
                      ]}
                    >
                      <Plot
                        data={bVel(r, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Velocity", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#94A3B8", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Velocity (mm/s)", font: { color: "#94A3B8", size: 10 } } },
                          shapes: [...cursorShape],
                        })}
                        onHover={onTimePlotHover}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Acceleration */}
                    <PlotBox
                      title="Sprung Acceleration"
                      description="Chassis sprung mass vertical acceleration compared to ISO 2631-1 comfortable threshold"
                      summaryData={[
                        { label: "Peak Acceleration", value: `${maxOf(r.ddz_s).toFixed(2)} m/s²` },
                        { label: "Min Acceleration", value: `${minOf(r.ddz_s).toFixed(2)} m/s²` },
                        { label: "ISO RMS", value: `${r.rms_body_accel.toFixed(3)} m/s²` },
                      ]}
                    >
                      <Plot
                        data={bAccel(r, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Sprung Acceleration", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#94A3B8", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Acceleration (m/s²)", font: { color: "#94A3B8", size: 10 } } },
                          shapes: [
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0:  0.315, y1:  0.315, line: { color: "rgba(52,211,153,0.3)", dash: "dot", width: 1 } },
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0: -0.315, y1: -0.315, line: { color: "rgba(52,211,153,0.3)", dash: "dot", width: 1 } },
                            ...cursorShape,
                          ],
                          annotations: [{ x: 0.02, xref: "paper", y: 0.315, yref: "y",
                            text: "ISO 0.315 m/s²", showarrow: false, font: { color: "#22c55e80", size: 9 }, xanchor: "left" }],
                        })}
                        onHover={onTimePlotHover}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Suspension Travel + Tire Deflection */}
                    <PlotBox
                      title="Suspension & Tire Deflection"
                      description="Relative suspension travel and tire deflection with bump and droop stops"
                      summaryData={[
                        { label: "Max Susp Travel", value: `${(maxOf(r.susp_travel) * 1000).toFixed(1)} mm` },
                        { label: "Max Tire Deflection", value: `${(maxOf(r.tire_defl) * 1000).toFixed(1)} mm` },
                        { label: "Jounce Stop Limit", value: "+60 mm" },
                      ]}
                    >
                      <Plot
                        data={bTravel(r, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Suspension & Tire Deflection", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#94A3B8", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Deflection (mm)", font: { color: "#94A3B8", size: 10 } } },
                          shapes: [
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0:  60, y1:  60, line: { color: "rgba(245,158,11,0.4)", dash: "dash", width: 1 } },
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0: -40, y1: -40, line: { color: "rgba(245,158,11,0.4)", dash: "dash", width: 1 } },
                            ...cursorShape,
                          ],
                          annotations: [
                            { x: 0.02, xref: "paper", y: 60, yref: "y", text: "Jounce Stop (+60mm)", showarrow: false, font: { color: "#f59e0b90", size: 8.5 }, xanchor: "left" },
                            { x: 0.02, xref: "paper", y: -40, yref: "y", text: "Rebound Stop (-40mm)", showarrow: false, font: { color: "#f59e0b90", size: 8.5 }, xanchor: "left" },
                          ],
                        })}
                        onHover={onTimePlotHover}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                )}

                {/* ── TAB 1: BODE / FRF — 2×2 ── */}
                {activeTab === 1 && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[350px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    {/* Transmissibility linear */}
                    <PlotBox>
                      <Plot
                        data={bTrans(r, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Transmissibility |H(jω)|", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#94A3B8", size: 10 } }, type: "log" },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Transmissibility (–)", font: { color: "#94A3B8", size: 10 } } },
                          shapes: [{ type: "line", x0: r.freq_at_peak_tx, x1: r.freq_at_peak_tx, y0: 0, y1: 1, yref: "paper",
                            line: { color: "rgba(242,169,0,0.2)", dash: "dot", width: 1 } }],
                          annotations: [{ x: Math.log10(r.freq_at_peak_tx), xref: "x", y: 0.98, yref: "paper",
                            text: `${r.freq_at_peak_tx.toFixed(2)} Hz`, showarrow: false, font: { color: "#888", size: 9 }, xanchor: "left", xshift: 4 }],
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Bode Magnitude dB */}
                    <PlotBox>
                      <Plot
                        data={bBodeMag(r, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Bode — Magnitude", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#94A3B8", size: 10 } }, type: "log" },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Magnitude (dB)", font: { color: "#94A3B8", size: 10 } } },
                          shapes: [
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0: 0, y1: 0, line: { color: "#333", dash: "dot", width: 1 } },
                          ],
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Bode Phase */}
                    <PlotBox>
                      <Plot
                        data={bBodePhase(r, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Bode — Phase", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#94A3B8", size: 10 } }, type: "log" },
                          // MIN-03: Auto-range phase axis based on actual data — clamp to [-200, 10] only as sensible default
                          ...(r.bode_phase_deg && r.bode_phase_deg.length > 0
                            ? { yaxis: { ...DARK_BASE.yaxis,
                                title: { text: "Phase (°)", font: { color: "#94A3B8", size: 10 } },
                                range: [
                                  Math.min(-10, Math.floor(minOf(r.bode_phase_deg) / 10) * 10 - 10),
                                  Math.max(10, Math.ceil(maxOf(r.bode_phase_deg) / 10) * 10 + 10),
                                ] } }
                            : {}),
                          shapes: [
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0: -90, y1: -90, line: { color: "#333", dash: "dot", width: 1 } },
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0: -180, y1: -180, line: { color: "#333", dash: "dot", width: 1 } },
                          ],
                          annotations: [
                            { x: 0.02, xref: "paper", y: -90, yref: "y", text: "−90°", showarrow: false, font: { color: "#94A3B8", size: 9 }, xanchor: "left" },
                            { x: 0.02, xref: "paper", y: -180, yref: "y", text: "−180°", showarrow: false, font: { color: "#94A3B8", size: 9 }, xanchor: "left" },
                          ],
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Dynamic Index — tire load variation */}
                    <PlotBox>
                      <Plot
                        data={bDynLoad(r, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Dynamic Tire Load Variation", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#94A3B8", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "ΔF_z (N)", font: { color: "#94A3B8", size: 10 } } },
                          shapes: [
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0: 0, y1: 0, line: { color: "#2a2a2a", width: 1 } },
                          ],
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                )}

                {/* — TAB 2: FORCES & ENERGY — 2×2 — */}
                {activeTab === 2 && forces && (
                  <div className="grid grid-cols-2 grid-rows-2 h-full gap-px bg-[#181818]">
                    {/* Spring + Damper force */}
                    <PlotBox>
                      <Plot
                        data={bForces(r, params, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Suspension Forces", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#94A3B8", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Force (N)", font: { color: "#94A3B8", size: 10 } } },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Damper F–V diagram */}
                    <PlotBox>
                      <Plot
                        data={bFV(r, params, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Damper Force–Velocity Diagram", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Relative Velocity (mm/s)", font: { color: "#94A3B8", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Damper Force (N)", font: { color: "#94A3B8", size: 10 } } },
                          shapes: [
                            { type: "line", x0: 0, x1: 0, y0: 0, y1: 1, yref: "paper", line: { color: "#2a2a2a", width: 1 } },
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0: 0, y1: 0, line: { color: "#2a2a2a", width: 1 } },
                          ],
                          annotations: [
                            { x: 0.95, y: 0.95, xref: "paper", yref: "paper", text: "COMPRESSION (BUMP +)", showarrow: false, font: { color: "#ffffff18", size: 11, weight: "bold" } },
                            { x: 0.05, y: 0.05, xref: "paper", yref: "paper", text: "EXTENSION (REBOUND -)", showarrow: false, font: { color: "#ffffff18", size: 11, weight: "bold" } },
                          ],
                          margin: { ...DARK_BASE.margin, b: 60 },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Spring F–Displacement */}
                    <PlotBox>
                      <Plot
                        data={bFx(r, params, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Spring Force–Displacement (Hysteresis)", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Suspension Travel (mm)", font: { color: "#94A3B8", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Spring Force (N)", font: { color: "#94A3B8", size: 10 } } },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Instantaneous Power */}
                    <PlotBox>
                      <Plot
                        data={bPower(r, params, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Damper Power Dissipation", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#94A3B8", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Power (W)", font: { color: "#94A3B8", size: 10 } } },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                )}

                {/* — TAB 3: PHASE SPACE — */}
                {activeTab === 3 && (
                  <div className="grid grid-cols-1 auto-rows-[400px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    {/* Phase portrait: body velocity vs displacement */}
                    <PlotBox>
                      <Plot
                        data={bPhaseS(r, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Phase Portrait — Sprung Mass", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "z_s (mm)", font: { color: "#94A3B8", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "ż_s (mm/s)", font: { color: "#94A3B8", size: 10 } } },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Phase portrait: wheel */}
                    <PlotBox>
                      <Plot
                        data={bPhaseU(r, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Phase Portrait — Unsprung Mass", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "z_u (mm)", font: { color: "#94A3B8", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "ż_u (mm/s)", font: { color: "#94A3B8", size: 10 } } },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* State-space eigenvalue info card */}
                    <PlotBox>
                      <div className="h-full p-5 flex flex-col justify-center gap-4">
                        <p className="text-[10px] font-bold tracking-widest text-gray-700 uppercase">State-Space Summary</p>
                        <div className="space-y-3 font-mono text-xs">
                          {[
                            { label: "Sprung ωₙ",   val: `${r.omega_n_s.toFixed(4)} rad/s`, color: "#f2a900" },
                            { label: "Sprung ζ",    val: r.zeta_s.toFixed(4),              color: getDampingStatus(r.zeta_s) === "good" ? "#34d399" : "#f59e0b" },
                            { label: "Sprung ωd",   val: `${(r.omega_n_s * Math.sqrt(Math.max(0, 1 - r.zeta_s**2))).toFixed(4)} rad/s`, color: "#aaa" },
                            { label: "Unsprung ωₙ", val: `${(r.f_n_u * 2 * Math.PI).toFixed(4)} rad/s`, color: "#00aeff" },
                            { label: "Unsprung ζ",  val: (r.zeta_u as number).toFixed(4),  color: "#aaa" },
                            { label: "k_w",          val: `${r.k_w.toFixed(0)} N/m`,        color: "#aaa" },
                          ].map(({ label, val, color }) => (
                            <div key={label} className="flex justify-between items-center border-b border-[#1a1a1a] pb-2">
                              <span className="text-gray-600">{label}</span>
                              <span style={{ color }}>{val}</span>
                            </div>
                          ))}
                        </div>
                        <p className="text-[9px] text-gray-700 mt-2">
                          Eigenvalues extracted from 4×4 state-space matrix A via scipy.linalg.eigvals
                        </p>
                      </div>
                    </PlotBox>

                    {/* Body accel vs susp travel cross-plot */}
                    <PlotBox>
                      <Plot
                        data={bComfortTravel(r, traces, deltaMode)}
                        layout={darkLayout({
                          title: { text: "Comfort–Travel Trade-off Space", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Susp. Travel (mm)", font: { color: "#94A3B8", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Body Accel (m/s²)", font: { color: "#94A3B8", size: 10 } } },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                )}

                {/* — TAB 4: PSD ANALYSIS — */}
                {activeTab === 4 && psdData && (
                  <div className="grid grid-cols-2 grid-rows-2 h-full gap-px bg-[#181818]">
                    {/* PSD of body acceleration */}
                    <PlotBox>
                      <Plot
                        data={bPSD(psdData, traces, deltaMode, r)}
                        layout={darkLayout({
                          title: { text: "PSD — Body Acceleration", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#94A3B8", size: 10 } }, type: "log", range: [Math.log10(0.1), Math.log10(50)] },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "PSD ((m/s²)²/Hz)", font: { color: "#94A3B8", size: 10 } }, type: "log" },
                          shapes: [
                            { type: "rect", x0: 1, x1: 1.5, y0: 0, y1: 1, yref: "paper", xref: "x",
                              fillcolor: "rgba(242,169,0,0.04)", line: { width: 0 } },
                          ],
                          annotations: [{ x: Math.log10(1.25), xref: "x", y: 0.95, yref: "paper",
                            text: "Ride band", showarrow: false, font: { color: "#f2a90060", size: 9 } }],
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Transmissibility overlaid with frequency bands */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.freq_hz, y: r.transmissibility_body, type: "scatter", mode: "lines",
                            name: "Body TX", line: { color: "#f2a900", width: 2 } },
                          { x: r.freq_hz, y: r.transmissibility_wheel, type: "scatter", mode: "lines",
                            name: "Wheel TX", line: { color: "#00aeff", width: 1.5 } },
                        ]}
                        layout={darkLayout({
                          title: { text: "Transmissibility with ISO Bands", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#94A3B8", size: 10 } }, type: "log" },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "|H(jω)| (–)", font: { color: "#94A3B8", size: 10 } } },
                          shapes: [
                            { type: "rect", x0: 1, x1: 2, y0: 0, y1: 1, yref: "paper", xref: "x", fillcolor: "rgba(52,211,153,0.04)", line: { width: 0 } },
                            { type: "rect", x0: 8, x1: 15, y0: 0, y1: 1, yref: "paper", xref: "x", fillcolor: "rgba(0,174,255,0.04)", line: { width: 0 } },
                          ],
                          annotations: [
                            { x: Math.log10(1.4), xref: "x", y: 0.92, yref: "paper", text: "Ride", showarrow: false, font: { color: "#34d39960", size: 9 } },
                            { x: Math.log10(11), xref: "x", y: 0.92, yref: "paper", text: "Wheel-hop", showarrow: false, font: { color: "#00aeff60", size: 9 } },
                          ],
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* ISO 2631 comfort info table */}
                    <PlotBox>
                      <div className="h-full p-5 flex flex-col justify-center gap-3">
                        <p className="text-[10px] font-bold tracking-widest text-gray-700 uppercase">ISO 2631-1 Assessment</p>
                        <div className="space-y-2">
                          {[
                            { range: "< 0.315",     label: "Not uncomfortable",       aw: r.rms_body_accel_wk },
                            { range: "0.315–0.63",  label: "Slightly uncomfortable",  aw: r.rms_body_accel_wk },
                            { range: "0.63–1.0",    label: "Fairly uncomfortable",    aw: r.rms_body_accel_wk },
                            { range: "1.0–2.0",     label: "Uncomfortable",           aw: r.rms_body_accel_wk },
                            { range: "> 2.0",       label: "Very uncomfortable",      aw: r.rms_body_accel_wk },
                          ].map(({ range, label }) => {
                            const limits = range === "< 0.315"
                              ? [0, 0.315] : range === "0.315–0.63"
                              ? [0.315, 0.63] : range === "0.63–1.0"
                              ? [0.63, 1.0] : range === "1.0–2.0"
                              ? [1.0, 2.0] : [2.0, 99];
                            const active = r.rms_body_accel_wk >= limits[0] && r.rms_body_accel_wk < limits[1];
                            return (
                              <div key={range}
                                className={`flex items-center justify-between px-3 py-2 rounded-lg border text-xs font-mono
                                  ${active ? "border-ansys-yellow/40 bg-ansys-yellow/5 text-ansys-yellow" : "border-[#1e1e1e] text-gray-700"}`}>
                                <span>{range} m/s²</span>
                                <span className={active ? "font-bold" : ""}>{label}</span>
                                {active && <RefreshCw size={11} className="text-ansys-yellow" />}
                              </div>
                            );
                          })}
                        </div>
                        <div className="mt-2 pt-3 border-t border-[#1a1a1a] font-mono text-xs">
                          <div className="flex justify-between text-gray-600">
                            <span>Raw RMS a_z</span>
                            <span className="text-white">{r.rms_body_accel.toFixed(4)} m/s²</span>
                          </div>
                          <div className="flex justify-between text-gray-600 mt-1">
                            <span>Wk-weighted RMS</span>
                            <span className="text-ansys-yellow">{(r.rms_body_accel_wk ?? 0).toFixed(4)} m/s²</span>
                          </div>
                        </div>
                      </div>
                    </PlotBox>

                    {/* Cumulative RMS vs time */}
                    <PlotBox>
                      <Plot
                        data={[{
                          x: r.time,
                          y: (() => {
                            // MIN-01: O(n) running sum instead of O(n²) nested reduce
                            const acc: number[] = [];
                            let sumSq = 0;
                            (r.ddz_s as number[]).forEach((v: number, i: number) => {
                              sumSq += v * v;
                              acc.push(Math.sqrt(sumSq / (i + 1)));
                            });
                            return acc;
                          })(),
                          type: "scatter", mode: "lines", name: "Cumulative RMS",
                          line: { color: "#bf5af2", width: 2 },
                        }]}
                        layout={darkLayout({
                          title: { text: "Cumulative RMS Acceleration", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#94A3B8", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Cum. RMS (m/s²)", font: { color: "#94A3B8", size: 10 } } },
                          shapes: [
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0: 0.315, y1: 0.315, line: { color: "rgba(52,211,153,0.3)", dash: "dot", width: 1 } },
                          ],
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                )}

                {/* ── TAB 5: SMART ENGINEERING INSIGHTS ── */}
                {activeTab === 5 && (
                  <div className="p-4 h-full overflow-y-auto custom-scrollbar">
                    <SmartInsights 
                      result={r} 
                      onApplyRecommendation={(patch) => {
                        setParams(prev => ({ ...prev, ...patch }));
                        showToast("Applied recommended setup parameters!", "success");
                        setTimeout(() => {
                          document.getElementById("btn-run")?.click();
                        }, 300);
                      }}
                    />
                  </div>
                )}

                {/* ── TAB 6: PARAMETRIC SENSITIVITY ANALYSIS ── */}
                {activeTab === 6 && (
                  <div className="p-4 h-full overflow-y-auto custom-scrollbar">
                    <SensitivityTornado
                      payload={buildPayload()}
                      authHeader={authHeader}
                    />
                  </div>
                )}

              </div>
            </div>
          )}

          {/* 3D Viewport Split */}
          {hasResults && r && (
            <div className="h-64 shrink-0 bg-[#0d0d0f] border border-[#1e1e1e] rounded-xl overflow-hidden relative">
               <div className="absolute top-2 left-3 z-10 text-[10px] font-mono text-gray-500 uppercase tracking-widest flex items-center gap-2">
                 <span>Live Telemetry</span>
                 <span className="text-gray-700">·</span>
                 <span className="text-ansys-yellow/80">2-DOF Corner (Symmetric Visualization)</span>
               </div>
               {/* Live Telemetry: Quarter-car has ONE unsprung mass (z_u).
                   All 4 corners receive the same z_u since the model is 2-DOF.
                   This is a symmetric approximation for visualization only. */}
               <Rig3DPlayer z_s={r.z_s as number[]} z_u={r.z_u as number[]} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense
      fallback={
        <div className="h-full flex items-center justify-center text-gray-600 text-sm">
          Loading simulation environment…
        </div>
      }
    >
      <SyncChartProvider>
        <QuarterCarDashboard />
      </SyncChartProvider>
    </Suspense>
  );
}
