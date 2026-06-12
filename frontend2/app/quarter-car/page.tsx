// @ts-nocheck

"use client";
import { useState, useEffect, Suspense, useMemo } from "react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import {
  Play, Settings2, AlertTriangle,
  Activity, Save, Sparkles, X, TrendingUp, BarChart3,
  Zap, GitBranch, Crosshair, RefreshCw,
} from "lucide-react";
// import PDFExport from "../../components/PDFExport";
import DataExport from "../../components/DataExport";
import ComparePanel from "../../components/ComparePanel";
import VehiclePresets from "../../components/VehiclePresets";
import SimHistory, { saveSimulationToHistory } from "../../components/SimHistory";
import ShareSession from "../../components/ShareSession";
import { useCollaboration } from "../../hooks/useCollaboration";
import PlanGate from "../../components/PlanGate";
import DamperLUTInput from "../../components/DamperLUTInput";
import { useAuth } from "../../contexts/AuthContext";
import ISOReportExport from "../../components/ISOReportExport";
const SuspensionRig3D = dynamic(() => import("../../components/SuspensionRig3D"), { ssr: false });

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

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
  { label: "Bode / FRF",        icon: BarChart3   },
  { label: "Forces & Energy",   icon: Zap         },
  { label: "Phase Space",       icon: GitBranch   },
  { label: "PSD Analysis",      icon: Crosshair   },
  { label: "3D Viewer",         icon: Zap         },
];

// â”€â”€â”€ Plotly dark-theme base â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

// â”€â”€â”€ Types â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
type Status = "good" | "warn" | "bad" | "neutral";
type Toast  = { msg: string; type: "success" | "error" };

// â”€â”€â”€ KPI helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function getDampingStatus(z: number): Status {
  if (z >= 0.25 && z <= 0.6) return "good";
  if (z >= 0.1  && z <= 0.8) return "warn";
  return "bad";
}
function getComfortStatus(rms: number): Status {
  if (rms < 0.315) return "good";
  if (rms < 1.0)   return "warn";
  return "bad";
}
function getTXStatus(tx: number): Status {
  if (tx < 2.0) return "good";
  if (tx < 3.5) return "warn";
  return "bad";
}

// â”€â”€â”€ Sub-components â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function KPICard({
  label, value, unit, sub, status = "neutral",
}: {
  label: string; value: number | string; unit?: string;
  sub?: string; status?: Status;
}) {
  const colours: Record<Status, string> = {
    good:    "text-emerald-400",
    warn:    "text-amber-400",
    bad:     "text-red-400",
    neutral: "text-white",
  };
  const borders: Record<Status, string> = {
    good:    "border-emerald-900/40 bg-emerald-950/10",
    warn:    "border-amber-900/40 bg-amber-950/10",
    bad:     "border-red-900/40 bg-red-950/10",
    neutral: "border-[#252525]",
  };
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

function ParameterInput({
  label, val, unit, step = 1, min, onChange,
}: {
  label: string; val: number; unit: string;
  step?: number; min?: number; onChange: (v: number) => void;
}) {
  return (
    <div className="flex justify-between items-center gap-2">
      <label className="text-[11px] text-gray-500 flex-1 min-w-0 leading-tight">{label}</label>
      <div className="relative shrink-0">
        <input
          type="number" step={step} value={val} min={min}
          onChange={(e) => onChange(Number(e.target.value))}
          className="bg-[#0d0d0d] border border-[#252525] text-[11px] rounded-lg px-2 py-1.5 text-white
            w-28 text-right pr-9 focus:outline-none focus:border-ansys-yellow/60
            focus:ring-1 focus:ring-ansys-yellow/15 transition-all"
        />
        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[9px] text-gray-700 pointer-events-none">
          {unit}
        </span>
      </div>
    </div>
  );
}

// â”€â”€â”€ Plot wrappers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function PlotBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex-1 min-w-0 min-h-0 relative">
      {children}
    </div>
  );
}

// â”€â”€â”€ Main dashboard â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function QuarterCarDashboard() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session");
  
  const { authHeader } = useAuth();

  const [isRunning, setIsRunning] = useState(false);
  const [isSaving,  setIsSaving]  = useState(false);
  const [isTuning,  setIsTuning]  = useState(false);
  const [results,   setResults]   = useState<Record<string, unknown> | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [toast,     setToast]     = useState<Toast | null>(null);

  const [params, setParams] = useState({
    m_s:          300.0,
    m_u:          35.0,
    k_s:          25000.0,
    c:            2050.0,
    k_t:          200000.0,
    MR:           0.85,
    c_t:          0.0,
    road_profile: "step",
    amplitude:    0.05,
    frequency:    2.0,
    duration:     5.0,
    damper_curve_v: null as number[] | null,
    damper_curve_f: null as number[] | null,
  });
  const { isConnected, activeUsers } = useCollaboration(sessionId, params, setParams);


  const showToast = (msg: string, type: Toast["type"]) => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  useEffect(() => {
    const profileId = searchParams.get("load");
    if (!profileId) return;
    fetch(`${API_BASE}/profiles/${profileId}`, { headers: authHeader() })
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((data) => {
        if (data.params) {
          setParams((prev) => ({ ...prev, ...data.params }));
          showToast(`Loaded "${data.name}" from Garage`, "success");
        }
      })
      .catch(() => showToast("Could not load profile", "error"));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const buildPayload = () => ({
    params: { m_s: params.m_s, m_u: params.m_u, k_s: params.k_s, c: params.c, k_t: params.k_t, MR: params.MR, c_t: params.c_t, damper_curve_v: params.damper_curve_v, damper_curve_f: params.damper_curve_f },
    profile: { profile_type: params.road_profile, amplitude: params.amplitude, frequency: params.frequency, duration: params.duration },
  });

  const runSimulation = async () => {
    setIsRunning(true);
    setResults(null);
    try {
      const res  = await fetch(`${API_BASE}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body:    JSON.stringify(buildPayload()),
      });
      const data = await res.json();
      if (!res.ok) setResults({ error: true, message: data.message ?? data.detail ?? "Simulation failed" });
      else { setResults(data); saveSimulationToHistory(params, data); }
    } catch (err) {
      setResults({ error: true, message: String(err) });
    } finally {
      setIsRunning(false);
    }
  };

  const saveProfile = async () => {
    const name = prompt("Name this Quarter Car setup:", "Custom 2-DOF Setup");
    if (!name) return;
    setIsSaving(true);
    try {
      const r = await fetch(`${API_BASE}/profiles`, {
        method:  "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body:    JSON.stringify({ name, vehicle_type: "QUARTER_CAR", params }),
      });
      if (r.ok) showToast("Setup saved to Garage!", "success");
      else      showToast("Failed to save", "error");
    } catch { showToast("Failed to save profile", "error"); }
    finally { setIsSaving(false); }
  };

  const autoTune = async () => {
    setIsTuning(true);
    try {
      const res  = await fetch(`${API_BASE}/auto-tune`, {
        method:  "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body:    JSON.stringify(buildPayload()),
      });
      const data = await res.json();
      if (data.status === "success") {
        const ks = Math.round(data.optimal_ks);
        const c  = Math.round(data.optimal_c);
        setParams((prev) => ({ ...prev, k_s: ks, c }));
        showToast(`AI tuned → k_s = ${ks.toLocaleString()} N/m  |  c = ${c.toLocaleString()} N·s/m`, "success");
        setTimeout(() => document.getElementById("btn-run")?.click(), 400);
      } else {
        showToast("Auto-tune did not converge", "error");
      }
    } catch { showToast("Failed to reach auto-tune endpoint", "error"); }
    finally { setIsTuning(false); }
  };

  // PSD computation moved to backend.

  // â”€â”€â”€ Derived: spring + damper forces â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const forces = useMemo(() => {
    if (!results || results.error) return null;
    const zs = results.z_s as number[];
    const zu = results.z_u as number[];
    const vs = results.dz_s as number[];
    const vu = results.dz_u as number[];
    const kw = params.k_s * params.MR * params.MR;
    const cw = params.c   * params.MR * params.MR;
    const F_spring = zs.map((z, i) => kw * (z - zu[i]));
    const F_damper = vs.map((v, i) => cw * (v - vu[i]));
    const F_total  = F_spring.map((fs, i) => fs + F_damper[i]);
    // Damper F-V: relative velocity vs damper force
    const relVel   = vs.map((v, i) => v - vu[i]);
    return { F_spring, F_damper, F_total, relVel };
  }, [results, params]);

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
    psd_freqs: number[]; psd_values: number[];
  } | null;

  return (
    <div className="h-full flex flex-col p-5 pt-3 gap-3 min-h-0">

      {/* Toast */}
      
        {isConnected && (
          <div className="fixed bottom-4 left-4 z-50 flex items-center gap-2 px-3 py-1.5 bg-[#0a1f12] border border-emerald-800/50 rounded-full text-emerald-300 text-xs font-medium shadow-lg">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
            Live Session ({activeUsers} connected)
          </div>
        )}
{toast && (
        <div className={`fixed top-14 right-4 z-50 flex items-center gap-3 px-4 py-3 rounded-xl
          shadow-2xl border text-sm font-medium transition-all
          ${toast.type === "success"
            ? "bg-[#0a1f12] border-emerald-800/50 text-emerald-300"
            : "bg-[#1f0a0a] border-red-800/50 text-red-300"}`}>
          {toast.msg}
          <button onClick={() => setToast(null)} className="opacity-50 hover:opacity-100 ml-1">
            <X size={13} />
          </button>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex items-center justify-between shrink-0 pb-3 border-b border-[#1e1e1e]">
        <div className="flex flex-col">
          <span className="text-[9px] font-bold tracking-[0.25em] text-ansys-yellow uppercase">
            2-DOF Vertical Dynamics · RK45 ODE
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-white leading-tight">Quarter Car</h1>
        </div>

        <div className="flex items-center gap-2">
          <SimHistory onRestore={(p) => { setParams(prev => ({ ...prev, ...p })); showToast("Restored from history", "success"); }} />
          <button onClick={saveProfile} disabled={isSaving}
            className="px-3 py-1.5 bg-[#141416] border border-[#252525] hover:bg-[#1e1e20] rounded-lg
              text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-40">
            <Save size={13} className="text-ansys-yellow" />
            {isSaving ? "Savingâ€¦" : "Save Setup"}
          </button>
          <ISOReportExport params={{ m_s: params.m_s, m_u: params.m_u, k_s: params.k_s, c: params.c, k_t: params.k_t, MR: params.MR, c_t: params.c_t, damper_curve_v: params.damper_curve_v, damper_curve_f: params.damper_curve_f }} profile={{ profile_type: params.road_profile, amplitude: params.amplitude, frequency: params.frequency, duration: params.duration }} />
          <ShareSession currentParams={params} vehicleType="QUARTER_CAR" />
          {/* PDF Export removed temporarily to fix compilation */}
          <DataExport results={results} fileName={`QCar_${Math.round(params.k_s)}_${Math.round(params.c)}`} />

          <button id="btn-run" onClick={runSimulation} disabled={isRunning}
            className={`px-5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
              isRunning
                ? "bg-[#222] text-gray-500 cursor-not-allowed"
                : "bg-ansys-yellow text-black hover:brightness-110 shadow-[0_0_20px_rgba(242,169,0,0.2)]"
            }`}>
            {isRunning ? (
              <><div className="w-3 h-3 border border-gray-600 border-t-gray-300 rounded-full animate-spin" />Solvingâ€¦</>
            ) : (
              <><Play size={13} fill="currentColor" /> Run Solver</>
            )}
          </button>

          <PlanGate required="PRO">
            <button onClick={autoTune} disabled={isTuning}
              className="px-4 py-1.5 bg-[#5e17eb] hover:bg-[#7c3aed] text-white rounded-lg text-xs font-bold
                flex items-center gap-1.5 transition-colors shadow-[0_0_16px_rgba(94,23,235,0.3)]
                disabled:opacity-50 disabled:cursor-not-allowed">
              <Sparkles size={13} /> {isTuning ? "AI Tuningâ€¦" : "AI Auto-Tune"}
            </button>
          </PlanGate>
        </div>
      </div>

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
              <ParameterInput label="Sprung Mass"   val={params.m_s} unit="kg"    min={1}    onChange={(v) => setParams({ ...params, m_s: v })} />
              <ParameterInput label="Unsprung Mass" val={params.m_u} unit="kg"    min={1}    onChange={(v) => setParams({ ...params, m_u: v })} />
            </ParamSection>
            <ParamSection title="Suspension">
              <ParameterInput label="Spring Rate"    val={params.k_s} unit="N/m"   step={500}  onChange={(v) => setParams({ ...params, k_s: v })} />
              <ParameterInput label="Damping"        val={params.c}   unit="N·s/m" step={50}   onChange={(v) => setParams({ ...params, c:   v })} />
              <ParameterInput label="Tire Stiffness" val={params.k_t} unit="N/m"   step={5000} onChange={(v) => setParams({ ...params, k_t: v })} />
              <ParameterInput label="Motion Ratio"   val={params.MR}  unit="â€”"     step={0.01} min={0.1} onChange={(v) => setParams({ ...params, MR:  v })} />
              <DamperLUTInput 
                label="Non-Linear Damper Curve"
                isActive={params.damper_curve_v !== null}
                onApply={(v, f) => setParams({ ...params, damper_curve_v: v, damper_curve_f: f })}
                onClear={() => setParams({ ...params, damper_curve_v: null, damper_curve_f: null })}
              />
            </ParamSection>
            <ParamSection title="Road Profile">
              <div className="flex justify-between items-center gap-2">
                <label className="text-[11px] text-gray-500 flex-1">Profile</label>
                <select value={params.road_profile} onChange={(e) => setParams({ ...params, road_profile: e.target.value })}
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
            </ParamSection>

            {/* Derived params display */}
            <ParamSection title="Derived">
              <div className="space-y-1.5 font-mono text-[10px]">
                <div className="flex justify-between text-gray-600">
                  <span>Wheel Rate k_w</span>
                  <span className="text-gray-400">{(params.k_s * params.MR * params.MR).toFixed(0)} N/m</span>
                </div>
                <div className="flex justify-between text-gray-600">
                  <span>Mass Ratio Î¼</span>
                  <span className="text-gray-400">{(params.m_u / params.m_s).toFixed(3)}</span>
                </div>
                <div className="flex justify-between text-gray-600">
                  <span>Static Defl.</span>
                  <span className="text-gray-400">{((params.m_s * 9.81) / (params.k_s * params.MR * params.MR) * 1000).toFixed(1)} mm</span>
                </div>
              </div>
            </ParamSection>
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 flex flex-col gap-3 min-w-0 overflow-hidden">

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
                  2-DOF quarter car · RK45 ODE · Impedance matrix FRF · ISO 2631-1 Wk weighting
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
          {isRunning && (
            <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl flex flex-col items-center justify-center gap-4">
              <div className="w-10 h-10 border-2 border-ansys-yellow/20 border-t-ansys-yellow rounded-full animate-spin" />
              <div className="text-center">
                <p className="text-sm font-medium text-gray-400 mb-1">Running RK45 ODE solverâ€¦</p>
                <p className="text-xs text-gray-700">Computing eigenvalues · FRF · time response · metrics</p>
              </div>
            </div>
          )}

          {/* Error */}
          {results?.error && (
            <div className="flex-1 bg-[#111113] border border-red-900/30 rounded-xl flex flex-col items-center justify-center gap-3">
              <AlertTriangle size={44} className="text-red-500 opacity-60" />
              <p className="text-sm font-semibold text-red-400">Simulation Error</p>
              <pre className="text-xs text-red-600/70 max-w-sm text-center font-mono
                bg-red-950/30 px-4 py-2 rounded-lg border border-red-900/20 whitespace-pre-wrap">
                {results.message as string}
              </pre>
            </div>
          )}

          {/* Results */}
          {hasResults && r && (
            <div id="sim-report" className="flex flex-col gap-3 flex-1 overflow-hidden">

              {/* Compare panel */}
              <ComparePanel current={r as any} />

              {/* KPI Ribbon â€” 8 cards */}
              <div className="grid grid-cols-8 gap-2 shrink-0">
                <KPICard
                  label="Ride Freq f_n"
                  value={r.f_n_s}
                  unit="Hz"
                  sub={`omega_n = ${r.omega_n_s.toFixed(2)} rad/s`}
                  status={r.f_n_s >= 1.0 && r.f_n_s <= 1.5 ? "good" : "warn"}
                />
                <KPICard
                  label="Wheel-Hop f_n"
                  value={r.f_n_u}
                  unit="Hz"
                  sub="Unsprung mode"
                  status={r.f_n_u >= 8 && r.f_n_u <= 15 ? "good" : "warn"}
                />
                <KPICard
                  label="Damping Ratio zeta"
                  value={r.zeta_s}
                  sub={`c_crit = ${r.c_crit_s.toFixed(0)} N·s/m`}
                  status={getDampingStatus(r.zeta_s)}
                />
                <KPICard
                  label="Peak TX"
                  value={r.peak_transmissibility}
                  sub={`@ ${r.freq_at_peak_tx.toFixed(2)} Hz`}
                  status={getTXStatus(r.peak_transmissibility)}
                />
                <KPICard
                  label="Wk RMS Accel"
                  value={r.rms_body_accel_wk ?? r.rms_body_accel}
                  unit="m/s²"
                  sub={r.comfort_rating || "ISO 2631-1"}
                  status={getComfortStatus(r.rms_body_accel)}
                />
                <KPICard
                  label="RMS Susp Travel"
                  value={r.rms_susp_travel * 1000}
                  unit="mm"
                  sub={`Peak: ${(r.peak_susp_travel * 1000).toFixed(1)} mm`}
                  status={r.peak_susp_travel < 0.08 ? "good" : r.peak_susp_travel < 0.15 ? "warn" : "bad"}
                />
                <KPICard
                  label="RMS Tire Load"
                  value={r.rms_tire_load}
                  unit="N"
                  sub={`k_t·Δz tire`}
                  status={r.rms_tire_load < 500 ? "good" : r.rms_tire_load < 1500 ? "warn" : "bad"}
                />
                <KPICard
                  label="Wheel Rate k_w"
                  value={r.k_w}
                  unit="N/m"
                  sub={`MR = ${params.MR.toFixed(2)}`}
                  status="neutral"
                />
              </div>

              {/* Tab nav */}
              <div className="flex gap-1.5 shrink-0">
                {TABS.map((tab, i) => {
                  const Icon = tab.icon;
                  return (
                    <button key={tab.label} onClick={() => setActiveTab(i)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                        activeTab === i
                          ? "bg-ansys-yellow text-black shadow-[0_0_12px_rgba(242,169,0,0.2)]"
                          : "bg-[#111113] border border-[#1e1e1e] text-gray-500 hover:text-gray-300 hover:border-[#2a2a2a]"
                      }`}>
                      <Icon size={12} /> {tab.label}
                    </button>
                  );
                })}
              </div>

              {/* Plot area */}
              <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-hidden min-h-0">

                {/* â”€â”€ TAB 0: TIME DOMAIN â€” 2Ã—2 grid â”€â”€ */}
                {activeTab === 0 && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[350px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    {/* Displacement */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.z_s.map(v => v * 1000), type: "scatter", mode: "lines", name: "Body z_s",
                            line: { color: "#f2a900", width: 2 } },
                          { x: r.time, y: r.z_u.map(v => v * 1000), type: "scatter", mode: "lines", name: "Wheel z_u",
                            line: { color: "#00aeff", width: 1.5 } },
                          { x: r.time, y: r.z_r.map(v => v * 1000), type: "scatter", mode: "lines", name: "Road z_r",
                            line: { color: "#333", width: 1, dash: "dash" } },
                        ]}
                        layout={darkLayout({
                          title: { text: "Displacement", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Displacement (mm)", font: { color: "#444", size: 10 } } },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Velocity */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.dz_s.map(v => v * 1000), type: "scatter", mode: "lines", name: "Body vel Å¼_s",
                            line: { color: "#f2a900", width: 2 } },
                          { x: r.time, y: r.dz_u.map(v => v * 1000), type: "scatter", mode: "lines", name: "Wheel vel Å¼_u",
                            line: { color: "#00aeff", width: 1.5 } },
                        ]}
                        layout={darkLayout({
                          title: { text: "Velocity", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Velocity (mm/s)", font: { color: "#444", size: 10 } } },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Acceleration */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.ddz_s, type: "scatter", mode: "lines", name: "Body accel zÌˆ_s",
                            line: { color: "#ff2d55", width: 2 }, fill: "tozeroy", fillcolor: "rgba(255,45,85,0.04)" },
                        ]}
                        layout={darkLayout({
                          title: { text: "Sprung Acceleration", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Acceleration (m/s²)", font: { color: "#444", size: 10 } } },
                          shapes: [
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0:  0.315, y1:  0.315, line: { color: "rgba(52,211,153,0.3)", dash: "dot", width: 1 } },
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0: -0.315, y1: -0.315, line: { color: "rgba(52,211,153,0.3)", dash: "dot", width: 1 } },
                          ],
                          annotations: [{ x: 0.02, xref: "paper", y: 0.315, yref: "y",
                            text: "ISO 0.315 m/s²", showarrow: false, font: { color: "#22c55e80", size: 9 }, xanchor: "left" }],
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Suspension Travel + Tire Deflection */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.susp_travel.map(v => v * 1000), type: "scatter", mode: "lines", name: "Susp travel (mm)",
                            line: { color: "#bf5af2", width: 2 } },
                          { x: r.time, y: r.tire_defl.map(v => v * 1000), type: "scatter", mode: "lines", name: "Tire deflection (mm)",
                            line: { color: "#64d2ff", width: 1.5 } },
                        ]}
                        layout={darkLayout({
                          title: { text: "Suspension & Tire Deflection", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Deflection (mm)", font: { color: "#444", size: 10 } } },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                )}

                {/* â”€â”€ TAB 1: BODE / FRF â€” 2Ã—2 â”€â”€ */}
                {activeTab === 1 && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[350px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    {/* Transmissibility linear */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.freq_hz, y: r.transmissibility_body, type: "scatter", mode: "lines", name: "Body |H_s|",
                            line: { color: "#f2a900", width: 2 }, fill: "tozeroy", fillcolor: "rgba(242,169,0,0.04)" },
                          { x: r.freq_hz, y: r.transmissibility_wheel, type: "scatter", mode: "lines", name: "Wheel |H_u|",
                            line: { color: "#00aeff", width: 1.5 } },
                        ]}
                        layout={darkLayout({
                          title: { text: "Transmissibility |H(jÏ‰)|", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#444", size: 10 } }, type: "log" },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Transmissibility (â€“)", font: { color: "#444", size: 10 } } },
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
                        data={[
                          { x: r.freq_hz, y: r.bode_magnitude_db, type: "scatter", mode: "lines", name: "Magnitude (dB)",
                            line: { color: "#00ff87", width: 2 } },
                        ]}
                        layout={darkLayout({
                          title: { text: "Bode â€” Magnitude", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#444", size: 10 } }, type: "log" },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Magnitude (dB)", font: { color: "#444", size: 10 } } },
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
                        data={[
                          { x: r.freq_hz, y: r.bode_phase_deg, type: "scatter", mode: "lines", name: "Phase (°)",
                            line: { color: "#ff9f0a", width: 2 } },
                        ]}
                        layout={darkLayout({
                          title: { text: "Bode â€” Phase", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#444", size: 10 } }, type: "log" },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Phase (°)", font: { color: "#444", size: 10 } }, range: [-200, 10] },
                          shapes: [
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0: -90, y1: -90, line: { color: "#333", dash: "dot", width: 1 } },
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0: -180, y1: -180, line: { color: "#333", dash: "dot", width: 1 } },
                          ],
                          annotations: [
                            { x: 0.02, xref: "paper", y: -90, yref: "y", text: "−90°", showarrow: false, font: { color: "#555", size: 9 }, xanchor: "left" },
                            { x: 0.02, xref: "paper", y: -180, yref: "y", text: "−180°", showarrow: false, font: { color: "#555", size: 9 }, xanchor: "left" },
                          ],
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Dynamic Index â€” tire load variation */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.tire_load_var, type: "scatter", mode: "lines", name: "Dynamic tire load dF_z",
                            line: { color: "#ff6b35", width: 2 }, fill: "tozeroy", fillcolor: "rgba(255,107,53,0.05)" },
                        ]}
                        layout={darkLayout({
                          title: { text: "Dynamic Tire Load Variation", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "dF_z (N)", font: { color: "#444", size: 10 } } },
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

                {/* â”€â”€ TAB 2: FORCES & ENERGY â€” 2Ã—2 â”€â”€ */}
                {activeTab === 2 && forces && (
                  <div className="grid grid-cols-2 grid-rows-2 h-full gap-px bg-[#181818]">
                    {/* Spring + Damper force */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: forces.F_spring, type: "scatter", mode: "lines", name: "Spring F_k",
                            line: { color: "#f2a900", width: 1.5 } },
                          { x: r.time, y: forces.F_damper, type: "scatter", mode: "lines", name: "Damper F_c",
                            line: { color: "#00aeff", width: 1.5 } },
                          { x: r.time, y: forces.F_total,  type: "scatter", mode: "lines", name: "Total F_susp",
                            line: { color: "#fff", width: 2, dash: "dot" } },
                        ]}
                        layout={darkLayout({
                          title: { text: "Suspension Forces", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Force (N)", font: { color: "#444", size: 10 } } },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Damper Fâ€“V diagram (the signature plot every NVH engineer wants) */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: forces.relVel.map(v => v * 1000), y: forces.F_damper, type: "scatter", mode: "markers",
                            name: "Damper Fâ€“V", marker: { color: forces.F_damper.map((_, i) => i / forces.F_damper.length),
                              colorscale: [["0", "#0a1628"], ["0.5", "#00aeff"], ["1", "#f2a900"]],
                              size: 2, opacity: 0.8 } },
                        ]}
                        layout={darkLayout({
                          title: { text: "Damper Forceâ€“Velocity Diagram", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Relative Velocity (mm/s)", font: { color: "#444", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Damper Force (N)", font: { color: "#444", size: 10 } } },
                          shapes: [
                            { type: "line", x0: 0, x1: 0, y0: 0, y1: 1, yref: "paper", line: { color: "#2a2a2a", width: 1 } },
                            { type: "line", x0: 0, x1: 1, xref: "paper", y0: 0, y1: 0, line: { color: "#2a2a2a", width: 1 } },
                          ],
                          margin: { ...DARK_BASE.margin, b: 60 },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Spring Fâ€“Displacement */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.susp_travel.map(v => v * 1000), y: forces.F_spring, type: "scatter", mode: "markers",
                            name: "Spring Fâ€“x", marker: { color: "#f2a900", size: 2, opacity: 0.7 } },
                        ]}
                        layout={darkLayout({
                          title: { text: "Spring Forceâ€“Displacement (Hysteresis)", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Suspension Travel (mm)", font: { color: "#444", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Spring Force (N)", font: { color: "#444", size: 10 } } },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Instantaneous Power */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: forces.F_damper.map((f, i) => f * (forces.relVel[i] ?? 0)),
                            type: "scatter", mode: "lines", name: "Damper Power P_c",
                            line: { color: "#ff2d55", width: 2 }, fill: "tozeroy", fillcolor: "rgba(255,45,85,0.05)" },
                        ]}
                        layout={darkLayout({
                          title: { text: "Damper Power Dissipation", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Power (W)", font: { color: "#444", size: 10 } } },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                )}

                {/* â”€â”€ TAB 3: PHASE SPACE â”€â”€ */}
                {activeTab === 3 && (
                  <div className="grid grid-cols-1 auto-rows-[400px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    {/* Phase portrait: body velocity vs displacement */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.z_s.map(v => v * 1000), y: r.dz_s.map(v => v * 1000),
                            type: "scatter", mode: "lines",
                            name: "Body phase portrait",
                            line: { color: "#f2a900", width: 1.5 },
                            marker: { size: 0 } },
                          // Start point
                          { x: [r.z_s[0] * 1000], y: [r.dz_s[0] * 1000], type: "scatter", mode: "markers",
                            name: "Start", marker: { color: "#00ff87", size: 8, symbol: "circle" } },
                        ]}
                        layout={darkLayout({
                          title: { text: "Phase Portrait â€” Sprung Mass", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "z_s (mm)", font: { color: "#444", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Å¼_s (mm/s)", font: { color: "#444", size: 10 } } },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    {/* Phase portrait: wheel */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.z_u.map(v => v * 1000), y: r.dz_u.map(v => v * 1000),
                            type: "scatter", mode: "lines",
                            name: "Wheel phase portrait",
                            line: { color: "#00aeff", width: 1.5 } },
                          { x: [r.z_u[0] * 1000], y: [r.dz_u[0] * 1000], type: "scatter", mode: "markers",
                            name: "Start", marker: { color: "#00ff87", size: 8, symbol: "circle" } },
                        ]}
                        layout={darkLayout({
                          title: { text: "Phase Portrait â€” Unsprung Mass", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "z_u (mm)", font: { color: "#444", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Å¼_u (mm/s)", font: { color: "#444", size: 10 } } },
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
                            { label: "Sprung Ï‰â‚™",   val: `${r.omega_n_s.toFixed(4)} rad/s`, color: "#f2a900" },
                            { label: "Sprung Î¶",    val: r.zeta_s.toFixed(4),              color: getDampingStatus(r.zeta_s) === "good" ? "#34d399" : "#f59e0b" },
                            { label: "Sprung Ï‰d",   val: `${(r.omega_n_s * Math.sqrt(Math.max(0, 1 - r.zeta_s**2))).toFixed(4)} rad/s`, color: "#aaa" },
                            { label: "Unsprung Ï‰â‚™", val: `${(r.f_n_u * 2 * Math.PI).toFixed(4)} rad/s`, color: "#00aeff" },
                            { label: "Unsprung Î¶",  val: (r.zeta_u as number).toFixed(4),  color: "#aaa" },
                            { label: "k_w",          val: `${r.k_w.toFixed(0)} N/m`,        color: "#aaa" },
                          ].map(({ label, val, color }) => (
                            <div key={label} className="flex justify-between items-center border-b border-[#1a1a1a] pb-2">
                              <span className="text-gray-600">{label}</span>
                              <span style={{ color }}>{val}</span>
                            </div>
                          ))}
                        </div>
                        <p className="text-[9px] text-gray-700 mt-2">
                          Eigenvalues extracted from 4Ã—4 state-space matrix A via scipy.linalg.eigvals
                        </p>
                      </div>
                    </PlotBox>

                    {/* Body accel vs susp travel cross-plot */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.susp_travel.map(v => v * 1000), y: r.ddz_s,
                            type: "scatter", mode: "markers",
                            name: "Accel vs Travel",
                            marker: { color: "#bf5af2", size: 2, opacity: 0.6 } },
                        ]}
                        layout={darkLayout({
                          title: { text: "Comfortâ€“Travel Trade-off Space", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Susp. Travel (mm)", font: { color: "#444", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Body Accel (m/s²)", font: { color: "#444", size: 10 } } },
                        })}
                        useResizeHandler style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                )}

                {/* â”€â”€ TAB 4: PSD ANALYSIS â”€â”€ */}
                {activeTab === 4 && r?.psd_freqs && (
                  <div className="grid grid-cols-2 grid-rows-2 h-full gap-px bg-[#181818]">
                    {/* PSD of body acceleration */}
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.psd_freqs, y: r.psd_values, type: "scatter", mode: "lines",
                            name: "PSD a_s", fill: "tozeroy", fillcolor: "rgba(255,45,85,0.06)",
                            line: { color: "#ff2d55", width: 2 } },
                        ]}
                        layout={darkLayout({
                          title: { text: "PSD â€” Body Acceleration", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#444", size: 10 } }, type: "log", range: [Math.log10(0.1), Math.log10(50)] },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "PSD ((m/s²)Â²/Hz)", font: { color: "#444", size: 10 } }, type: "log" },
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
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#444", size: 10 } }, type: "log" },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "|H(jÏ‰)| (â€“)", font: { color: "#444", size: 10 } } },
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
                            { range: "0.315â€“0.63",  label: "Slightly uncomfortable",  aw: r.rms_body_accel_wk },
                            { range: "0.63â€“1.0",    label: "Fairly uncomfortable",    aw: r.rms_body_accel_wk },
                            { range: "1.0â€“2.0",     label: "Uncomfortable",           aw: r.rms_body_accel_wk },
                            { range: "> 2.0",       label: "Very uncomfortable",      aw: r.rms_body_accel_wk },
                          ].map(({ range, label }) => {
                            const limits = range === "< 0.315"
                              ? [0, 0.315] : range === "0.315â€“0.63"
                              ? [0.315, 0.63] : range === "0.63â€“1.0"
                              ? [0.63, 1.0] : range === "1.0â€“2.0"
                              ? [1.0, 2.0] : [2.0, 99];
                            const active = r.rms_body_accel >= limits[0] && r.rms_body_accel < limits[1];
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
                          y: r.ddz_s.map((_: number, i: number) => {
                            const slice = (r.ddz_s as number[]).slice(0, i + 1);
                            return Math.sqrt(slice.reduce((s: number, v: number) => s + v * v, 0) / (i + 1));
                          }),
                          type: "scatter", mode: "lines", name: "Cumulative RMS",
                          line: { color: "#bf5af2", width: 2 },
                        }]}
                        layout={darkLayout({
                          title: { text: "Cumulative RMS Acceleration", font: { color: "#888", size: 11 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#444", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Cum. RMS (m/s²)", font: { color: "#444", size: 10 } } },
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

                {/* â”€â”€ TAB 5: 3D VIEWER â”€â”€ */}
                {activeTab === 5 && r?.time && (
                  <div className="h-full bg-[#181818] relative flex items-center justify-center p-2">
                    <div className="w-full h-full border border-[#2a2a2a] rounded-lg overflow-hidden relative">
                      <div className="absolute top-4 left-4 z-10 bg-black/50 px-3 py-1.5 rounded text-xs font-mono text-white border border-white/10 backdrop-blur-md">
                        Real-time kinematics playback
                      </div>
                      <SuspensionRig3D
                        times={r.time}
                        zs={r.z_s}
                        zu={r.z_u}
                      />
                    </div>
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
    <Suspense
      fallback={
        <div className="h-full flex items-center justify-center text-gray-600 text-sm">
          Loading simulation environmentâ€¦
        </div>
      }
    >
      <QuarterCarDashboard />
    </Suspense>
  );
}
