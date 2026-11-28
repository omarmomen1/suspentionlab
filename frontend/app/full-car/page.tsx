
// Full Car Page

"use client";
import { useState, useRef, Suspense, useMemo, useEffect, useCallback } from "react";
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
import NextStepLink from "../../components/NextStepLink";
import { formatApiError } from "../../lib/api_client";
import { useUndoRedo } from "../../hooks/useUndoRedo";
import PDFExport, { type PinnedLedgerRow } from "../../components/PDFExport";
import type { LedgerRow } from "../../components/v2/instruments/LedgerTable";
import { fullCarLedgerRows } from "../../lib/v2/ledgers";
import StudioShell, { ShellLeft, ShellCenter, ShellRight } from "../../components/v2/StudioShell";
import VerdictRail from "../../components/v2/VerdictRail";
import LedgerDock from "../../components/v2/instruments/LedgerDock";
import { verdictStatus } from "../../lib/v2/status";
import { toPinnedPdfRows } from "../../lib/v2/ledgers";

import DataExport from "../../components/DataExport";
import PlanGate from "../../components/PlanGate";
import ComparePanel from "../../components/ComparePanel";
import SimHistory, { saveSimulationToHistory } from "../../components/SimHistory";
import { useAuth } from "../../contexts/AuthContext";

import ModelValidity, { ValidityReport, resolveValidityTier } from "../../components/ModelValidity";
import Plot from "../../components/sim/Plot";
import KPICard from "../../components/sim/KPICard";
import PlotBox from "../../components/sim/PlotBox";
import { darkLayout, DARK_BASE } from "../../components/sim/theme";
import { maxOf, minOf } from "../../lib/array";
import EmptyState from "../../components/v2/EmptyState";
import FourFootprintsSVG from "../../components/v2/instruments/FourFootprintsSVG";
import type { FullCarLoadParams } from "../../lib/v2/phase4";

// One WebGL canvas on this route, loaded only in the browser.
const AttitudeModel3D = dynamic(() => import("../../components/v2/instruments/AttitudeModel3D"), {
  ssr: false,
  loading: () => <p className="text-[11px] text-[#8a909a] m-0">Loading 3D view</p>,
});

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TABS = [
  { label: "Footprints & Attitude", icon: GitBranch },
  { label: "Time Domain",           icon: TrendingUp },
  { label: "Pitch & Roll",          icon: GitBranch },
  { label: "Load Transfer",         icon: BarChart3 },
  { label: "PSD Analysis",          icon: Crosshair },
];

// ─── Plotly dark-theme base ──────────────────────────────────────────────────
type Status = "good" | "warn" | "bad" | "neutral";
type Toast  = { msg: string; type: "success" | "error" };

interface FullCarPreset {
  id: string;
  name: string;
  category: string;
  description: string;
  params: {
    m_s: number;
    I_x: number;
    I_y: number;
    m_uf: number;
    m_ur: number;
    k_sf: number;
    k_sr: number;
    c_f: number;
    c_r: number;
    k_arb_f: number;
    k_arb_r: number;
    L: number;
    weight_dist: number;
    tw_f: number;
    tw_r: number;
    speed_kph: number;
    p_amp: number;
  };
}

const FULL_CAR_PRESETS: FullCarPreset[] = [
  {
    id: "sports_saloon",
    name: "Sports Saloon (Default)",
    category: "Road Car",
    description: "Balanced 7-DOF sports sedan with moderate roll & pitch stiffness.",
    params: {
      m_s: 1200.0, I_x: 400.0, I_y: 1800.0, m_uf: 40.0, m_ur: 40.0,
      k_sf: 30000.0, k_sr: 35000.0, c_f: 2500.0, c_r: 3000.0,
      k_arb_f: 20000.0, k_arb_r: 10000.0, L: 2.6, weight_dist: 50.0,
      tw_f: 1.6, tw_r: 1.6, speed_kph: 72.0, p_amp: 0.05,
    },
  },
  {
    id: "compact_hatch",
    name: "Compact Hatchback",
    category: "Road Car",
    description: "FWD passenger hatchback with front-biased static mass and compliant ride.",
    params: {
      m_s: 1120.0, I_x: 340.0, I_y: 1650.0, m_uf: 32.0, m_ur: 30.0,
      k_sf: 18000.0, k_sr: 20000.0, c_f: 1500.0, c_r: 1600.0,
      k_arb_f: 12000.0, k_arb_r: 6000.0, L: 2.55, weight_dist: 60.0,
      tw_f: 1.52, tw_r: 1.50, speed_kph: 72.0, p_amp: 0.03,
    },
  },
  {
    id: "gt3_race",
    name: "GT3 Race Car",
    category: "Racing",
    description: "FIA GT3 chassis with stiff wheel rates, high roll resistance, and aero platform.",
    params: {
      m_s: 1180.0, I_x: 380.0, I_y: 1650.0, m_uf: 40.0, m_ur: 42.0,
      k_sf: 75000.0, k_sr: 85000.0, c_f: 4800.0, c_r: 5200.0,
      k_arb_f: 45000.0, k_arb_r: 24000.0, L: 2.70, weight_dist: 48.0,
      tw_f: 1.66, tw_r: 1.64, speed_kph: 140.0, p_amp: 0.02,
    },
  },
  {
    id: "formula_student",
    name: "Formula Student",
    category: "Racing",
    description: "Lightweight FSAE single-seater (240 kg sprung, low roll/pitch inertia).",
    params: {
      m_s: 240.0, I_x: 45.0, I_y: 110.0, m_uf: 14.0, m_ur: 15.0,
      k_sf: 55000.0, k_sr: 60000.0, c_f: 1800.0, c_r: 1800.0,
      k_arb_f: 18000.0, k_arb_r: 12000.0, L: 1.58, weight_dist: 47.0,
      tw_f: 1.22, tw_r: 1.20, speed_kph: 80.0, p_amp: 0.015,
    },
  },
  {
    id: "full_size_suv",
    name: "Full-Size SUV",
    category: "Off-Road",
    description: "Heavy high-inertia SUV tuned for deep stroke and obstacle absorption.",
    params: {
      m_s: 2150.0, I_x: 780.0, I_y: 3400.0, m_uf: 60.0, m_ur: 65.0,
      k_sf: 26000.0, k_sr: 30000.0, c_f: 3600.0, c_r: 4000.0,
      k_arb_f: 16000.0, k_arb_r: 10000.0, L: 2.95, weight_dist: 53.0,
      tw_f: 1.68, tw_r: 1.68, speed_kph: 70.0, p_amp: 0.06,
    },
  },
  {
    id: "lmp_prototype",
    name: "LMP Prototype",
    category: "Racing",
    description: "Endurance prototype with ultra-stiff heave/roll control.",
    params: {
      m_s: 880.0, I_x: 240.0, I_y: 1150.0, m_uf: 24.0, m_ur: 26.0,
      k_sf: 125000.0, k_sr: 140000.0, c_f: 6500.0, c_r: 7200.0,
      k_arb_f: 60000.0, k_arb_r: 35000.0, L: 2.95, weight_dist: 46.0,
      tw_f: 1.65, tw_r: 1.62, speed_kph: 180.0, p_amp: 0.01,
    },
  },
];

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
  const searchParams = useSearchParams();
  const { authHeader, fetchWithAuth } = useAuth();
  const { pollJob } = useJobPolling();

  const [isRunning, setIsRunning] = useState(false);
  const [isSaving,  setIsSaving]  = useState(false);
  const [results,   setResults]   = useState<FullCarState | null>(null);
  const [lastValidResults, setLastValidResults] = useState<FullCarResults | null>(null);
  const [simError, setSimError] = useState<string | null>(null);
  const [validity, setValidity] = useState<ValidityReport | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [scrubIdx, setScrubIdx] = useState(0);
  // Load-relevant parameters of the run that produced the current results (k_t is the value the payload sends).
  const runLoadParamsRef = useRef<FullCarLoadParams | null>(null);
  const [toast,     setToast]     = useState<Toast | null>(null);

  const [params, setParams, { undo, redo, reset, canUndo, canRedo }] = useUndoRedo({
    m_s: 1200.0, I_x: 400.0, I_y: 1800.0, m_uf: 40.0, m_ur: 40.0, k_sf: 30000.0, k_sr: 35000.0,
    c_f: 2500.0, c_r: 3000.0, k_arb_f: 20000.0, k_arb_r: 10000.0, L: 2.6, weight_dist: 50.0,
    tw_f: 1.6, tw_r: 1.6, speed_kph: 72.0, p_amp: 0.05
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
    runLoadParamsRef.current = { m_s: params.m_s, m_uf: params.m_uf, m_ur: params.m_ur, a, b, k_tf: 250000.0, k_tr: 250000.0 };
    return {
      params: { m_s: params.m_s, I_x: params.I_x, I_y: params.I_y, m_uf: params.m_uf, m_ur: params.m_ur, k_sf: params.k_sf, k_sr: params.k_sr, c_f: params.c_f, c_r: params.c_r, k_arb_f: params.k_arb_f, k_arb_r: params.k_arb_r, k_tf: 250000.0, k_tr: 250000.0, L: params.L, a: a, b: b, tw_f: params.tw_f, tw_r: params.tw_r, speed_mps: params.speed_kph / 3.6, c_tf: 0.0, c_tr: 0.0 },
      profile: { profile_type: "step", amplitude: params.p_amp, frequency: 2.0, duration: 5.0 },
    };
  };

  const evaluateFullCarValidity = (res: FullCarResults): ValidityReport => {
    const maxRollDeg = res.phi ? Math.max(...res.phi.map(p => Math.abs(p * 180 / Math.PI))) : 0;
    const maxPitchDeg = res.theta ? Math.max(...res.theta.map(t => Math.abs(t * 180 / Math.PI))) : 0;
    const heaveAccel = res.rms_heave_accel ?? 0;
    
    const checks: ValidityReport["checks"] = [
      {
        label: "Roll Angle Domain (< 8°)",
        status: maxRollDeg < 5 ? "pass" : maxRollDeg < 8 ? "warn" : "fail",
        detail: `Peak roll = ${maxRollDeg.toFixed(2)}° (Linear multi-body suspension assumption)`,
      },
      {
        label: "Pitch Angle Domain (< 6°)",
        status: maxPitchDeg < 4 ? "pass" : maxPitchDeg < 6 ? "warn" : "fail",
        detail: `Peak pitch = ${maxPitchDeg.toFixed(2)}° (Small-angle LTI kinematic validity)`,
      },
      {
        label: "Heave Comfort (ISO 2631)",
        status: heaveAccel < 0.5 ? "pass" : heaveAccel < 1.2 ? "warn" : "fail",
        detail: `RMS Heave = ${heaveAccel.toFixed(3)} m/s²`,
      },
    ];

    const passCount = checks.filter(c => c.status === "pass").length;
    const warnCount = checks.filter(c => c.status === "warn").length;
    const score = Math.round((passCount * 100 + warnCount * 50) / checks.length);
    const band = score >= 80 ? "High" : score >= 50 ? "Medium" : "Low";

    return {
      score,
      band,
      summary: "7-DOF Full Car Multi-Body LTI State-Space Verification",
      checks,
    };
  };

  const runSimulation = async () => {
    setIsRunning(true);
    setSimError(null);
    try {
      const res = await fetchWithAuth("/api/v1/simulate/full-car", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      const data = await res.json();
      if (!res.ok) {
        const msg = data.message ?? data.detail ?? "Simulation failed";
        setSimError(msg);
        showToast(msg, "error");
        setIsRunning(false);
        return;
      }
      
      const onCompleted = (result: FullCarResults) => {
        setResults(result);
        setLastValidResults(result);
        setSimError(null);
        setValidity(evaluateFullCarValidity(result));
        saveSimulationToHistory("sl_sim_history_fcar", params, result);
        setIsRunning(false);
      };

      if (data.job_id) {
        pollJob({
          jobId: data.job_id,
          authHeader,
          onCompleted,
          onFailed: (msg) => {
            setSimError(msg);
            showToast(msg, "error");
            setIsRunning(false);
          },
        });
      } else {
        onCompleted(data);
      }
    } catch (err) {
      const msg = formatApiError(err, "Full-car simulation failed");
      setSimError(msg);
      showToast(msg, "error");
      setIsRunning(false);
    }
  };

  const saveProfile = async () => {
    if (isSaving) return;
    const name = await promptModal("Name this Full Car setup:", "Custom 7-DOF Setup");
    if (!name) return;
    setIsSaving(true);
    try {
      const r = await fetchWithAuth("/api/v1/profiles/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, vehicle_type: "FULL_CAR", params })
      });
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

  const activeResult = ((results && !results.error) ? results : lastValidResults) as FullCarResults | null;
  // Zero-lie gate: verdict requires a payload with a real solved value, not
  // an error shell or an empty object.
  const hasResults = Boolean(
    activeResult && !activeResult.error && typeof activeResult.f_n_heave === "number"
  );
  const r = activeResult;

  // V2 verdict, ledger and pinned PDF rows.
  const verdict = verdictStatus({ isRunning, error: simError, hasResults, validityTier: validity ? resolveValidityTier(validity) : null });
  const ledgerSource = (r as any)?.run_id ? `solver run ${(r as any).run_id}` : "this session's solver run";
  const ledgerRows = useMemo(
    () => (hasResults ? fullCarLedgerRows(r as any, params as any, verdict.status, ledgerSource) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [hasResults, r, params, verdict.status, ledgerSource],
  );
  const [pinnedPdfRows, setPinnedPdfRows] = useState<PinnedLedgerRow[]>([]);
  const handlePinned = useCallback((rows: LedgerRow[]) => setPinnedPdfRows(toPinnedPdfRows(rows)), []);

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
          <NextStepLink />
        </div>

        <div className="flex items-center gap-2">
          <SimHistory storageKey="sl_sim_history_fcar" renderParams={(p) => [["Mass", p.m_s], ["Ix", p.I_x], ["Iy", p.I_y], ["k_sf", p.k_sf], ["k_sr", p.k_sr], ["Speed", p.speed_kph]]} onRestore={(p) => { setParams(prev => ({ ...prev, ...p })); showToast("Restored from history", "success"); }} />
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
          <PDFExport captureId="sim-report" fileName={`FCar_${params.m_s}`} pinnedRows={pinnedPdfRows} />
          <DataExport results={results} fileName={`FCar_${params.m_s}`} />

          <button id="btn-run" onClick={runSimulation} disabled={isRunning}
            className={`px-5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-colors ${isRunning ? "bg-[#222] text-gray-500 cursor-not-allowed" : "bg-signal text-carbon border border-signal hover:bg-[#d6f56e]"}`}>
            {isRunning ? <><div className="w-3 h-3 border border-gray-600 border-t-gray-300 rounded-full animate-spin" />Solving…</> : <><Play size={13} fill="currentColor" /> Run Solver</>}
          </button>
        </div>
      </div>

      {/* Screen Reader Live Solver Announcer */}
      <div className="sr-only" role="status" aria-live="polite">
        {isRunning
          ? "Solving 7-DOF full car LTI system..."
          : results
          ? `Simulation completed. Heave frequency: ${(results as any).f_n_heave?.toFixed(2) ?? "N/A"} Hertz, Roll frequency: ${(results as any).f_n_roll?.toFixed(2) ?? "N/A"} Hertz, Pitch frequency: ${(results as any).f_n_pitch?.toFixed(2) ?? "N/A"} Hertz`
          : ""}
      </div>

      <StudioShell>
        <ShellLeft className="lg:w-60">
        <div className="w-full lg:w-60 lg:shrink-0 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-y-auto custom-scrollbar">
          <div className="px-4 py-3 border-b border-[#1e1e1e] sticky top-0 bg-[#0d0d0f] z-10"><h2 className="text-xs font-semibold text-gray-300 flex items-center gap-2"><Settings2 size={13} className="text-ansys-yellow" /> Parameters</h2></div>
          <div className="p-4 space-y-5">
            <div className="space-y-1.5">
              <label htmlFor="full-car-preset-select" className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                7-DOF Full-Car Presets
              </label>
              <select
                id="full-car-preset-select"
                defaultValue="sports_saloon"
                onChange={(e) => {
                  const found = FULL_CAR_PRESETS.find((p) => p.id === e.target.value);
                  if (found) {
                    setParams({ ...found.params });
                    showToast(`Loaded 7-DOF preset: ${found.name}`, "success");
                  }
                }}
                className="w-full bg-[#0d0d0f] border border-[#252525] rounded-lg px-2.5 py-1.5 text-xs font-medium text-white focus:outline-none focus:border-ansys-yellow/60"
              >
                {FULL_CAR_PRESETS.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.category})
                  </option>
                ))}
              </select>
            </div>
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
        </ShellLeft>

        <ShellCenter>
        <div className="flex-1 flex flex-col gap-3 min-w-0 overflow-hidden">
          {!results && !isRunning && (
            <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl flex flex-col items-center justify-center gap-4">
              <div className="w-16 h-16 rounded-2xl bg-signal/5 border border-signal/15 flex items-center justify-center"><Activity size={32} strokeWidth={1} className="text-signal/60" /></div>
              <div className="text-center"><p className="text-sm font-semibold text-gray-400 mb-1">Configure parameters and click <span className="text-ansys-yellow">Run Solver</span></p><p className="text-xs text-gray-400">7-DOF full car · LTI State-Space · Pitch & Roll</p></div>
            </div>
          )}

          {isRunning && (
            <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl flex flex-col items-center justify-center gap-4">
              <div className="w-10 h-10 border-2 border-ansys-yellow/20 border-t-ansys-yellow rounded-full animate-spin" />
              <div className="text-center"><p className="text-sm font-medium text-gray-400 mb-1">Running LTI Solver…</p></div>
            </div>
          )}

          {/* Error: only show centered if no prior results */}
          {!hasResults && (results?.error || simError) && (
            <div role="alert" aria-live="assertive" className="flex-1 bg-[#111113] border border-red-900/30 rounded-xl flex flex-col items-center justify-center gap-3">
              <AlertTriangle size={44} className="text-red-500 opacity-60" /><p className="text-sm font-semibold text-red-400">Simulation Error</p>
              <pre className="text-xs text-red-400 max-w-sm text-center font-mono bg-red-950/30 px-4 py-2 rounded-lg border border-red-900/20 whitespace-pre-wrap">{(results as any)?.message || simError}</pre>
            </div>
          )}

          {hasResults && r && (
            <div id="sim-report" className="flex flex-col gap-3 flex-1 overflow-hidden">
              {/* Floating Non-Destructive Error HUD */}
              {simError && (
                <div role="alert" className="bg-red-950/50 border border-red-800/70 rounded-xl p-3 flex items-center justify-between gap-3 text-xs text-red-300 shadow-xl shrink-0 animate-in slide-in-from-top-1">
                  <div className="flex items-center gap-2">
                    <AlertTriangle size={15} className="text-red-400 shrink-0" />
                    <div>
                      <span className="font-bold text-red-300">Last solve failed:</span> {simError}.
                      <span className="text-gray-400 ml-1.5 text-[11px]">(Preserving previous valid curves)</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSimError(null)}
                    aria-label="Dismiss error"
                    className="text-gray-400 hover:text-white text-xs px-2.5 py-1 rounded bg-black/50 border border-white/10 hover:bg-black/80 transition-colors"
                  >
                    Dismiss
                  </button>
                </div>
              )}

              {/* Model Domain Validity */}
              <ModelValidity report={validity} />

              <ComparePanel current={r as unknown as React.ComponentProps<typeof ComparePanel>["current"]} />

              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-9 gap-2 shrink-0">
                <KPICard label="Heave ƒₙ" value={r.f_n_heave} unit="Hz" status={r.f_n_heave >= 1.0 && r.f_n_heave <= 1.5 ? "good" : "warn"} />
                <KPICard label="Roll ƒₙ" value={r.f_n_roll} unit="Hz" status={r.f_n_roll >= 1.5 && r.f_n_roll <= 2.5 ? "good" : "warn"} />
                <KPICard label="Pitch ƒₙ" value={r.f_n_pitch} unit="Hz" status={r.f_n_pitch >= 1.2 && r.f_n_pitch <= 1.8 ? "good" : "warn"} />
                <KPICard label="Elastic Roll" value={r.roll_stiffness_dist} unit="% K_φ,f" status={r.roll_stiffness_dist >= 55 ? "good" : "warn"} />
                <KPICard label="Dynamic LLTD" value={(maxOf(r.lateral_load_transfer_f as number[]) + maxOf(r.lateral_load_transfer_r as number[])) > 0 ? (maxOf(r.lateral_load_transfer_f as number[]) / (maxOf(r.lateral_load_transfer_f as number[]) + maxOf(r.lateral_load_transfer_r as number[]))) * 100 : 50} unit="% ΔFz,f" status="neutral" />
                <KPICard label="RMS Heave" value={r.rms_heave_accel} unit="m/s²" status={r.rms_heave_accel < 0.315 ? "good" : r.rms_heave_accel < 1.0 ? "warn" : "bad"} />
                <KPICard label="RMS Pitch" value={r.rms_pitch_accel} unit="rad/s²" status="neutral" />
                <KPICard label="RMS Roll" value={r.rms_roll_accel} unit="rad/s²" status="neutral" />
                <KPICard label="LLT Front" value={maxOf(r.lateral_load_transfer_f as number[])} unit="N" status="neutral" />
              </div>

              {/* Wave 11 item 2: say where roll and load transfer come from. */}
              <p className="text-[10px] leading-relaxed text-gray-500" data-testid="lateral-g-model-note">
                Ride-and-attitude model: roll and load transfer are computed from the lateral g you enter
                here, not solved.
              </p>

              <div className="flex gap-1.5 shrink-0" role="tablist" aria-label="Full-car simulation views">
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
                          ? "bg-signal text-carbon border border-signal"
                          : "bg-[#111113] border border-[#1e1e1e] text-gray-400 hover:text-white hover:border-[#2a2a2a]"
                      }`}
                    >
                      <Icon size={12} aria-hidden="true" /> {tab.label}
                    </button>
                  );
                })}
              </div>

              <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-hidden min-h-0">
                {/* ── TAB 0: FOOTPRINTS & ATTITUDE (Primary View) ── */}
                {activeTab === 0 && (() => {
                  const n = Array.isArray(r.time) ? r.time.length : 0;
                  const idx = Math.min(scrubIdx, Math.max(0, n - 1));
                  const lp = runLoadParamsRef.current;
                  return (
                    <div className="h-full overflow-y-auto p-4 flex flex-col gap-4" data-testid="footprints-attitude-tab">
                      <label className="text-[11px] text-[#8a909a] flex items-center gap-3">
                        Time
                        <input type="range" min={0} max={Math.max(0, n - 1)} value={idx} onChange={(e) => setScrubIdx(Number(e.target.value))} aria-label="Scrub time index" className="flex-1 accent-[#C8F04B]" />
                        <span className="font-mono text-[#cfd3da]">{Array.isArray(r.time) && typeof r.time[idx] === "number" ? `${r.time[idx].toFixed(3)} s` : "n/a"}</span>
                      </label>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div className="hidden lg:block">
                          {lp ? <FourFootprintsSVG result={r as any} params={lp} index={idx} /> : <EmptyState kind="unavailable" reason="Tire loads need a run in this session." />}
                        </div>
                        <AttitudeModel3D result={r as any} index={idx} loadParams={lp} />
                      </div>
                    </div>
                  );
                })()}

                {/* ── TAB 1: TIME DOMAIN ── */}
                {activeTab === 1 && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[350px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.z_s?.map((v: number) => v * 1000), type: "scatter", mode: "lines", name: "CG Heave z_s", line: { color: "#F59E0B", width: 2 } },
                          { x: r.time, y: r.z_ufl?.map((v: number) => v * 1000), type: "scatter", mode: "lines", name: "FL Wheel", line: { color: "#06B6D4", width: 1 } },
                          { x: r.time, y: r.z_url?.map((v: number) => v * 1000), type: "scatter", mode: "lines", name: "RL Wheel", line: { color: "#F43F5E", width: 1 } },
                        ]}
                        layout={darkLayout({ title: { text: "Vertical Displacements", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#94A3B8", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Displacement (mm)", font: { color: "#94A3B8", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ 
                          { x: r.time, y: r.theta?.map((v: number) => v * 180 / Math.PI), type: "scatter", mode: "lines", name: "Pitch Angle θ", line: { color: "#10B981", width: 2 } },
                          { x: r.time, y: r.phi?.map((v: number) => v * 180 / Math.PI), type: "scatter", mode: "lines", name: "Roll Angle φ", line: { color: "#F43F5E", width: 2 } } 
                        ]}
                        layout={darkLayout({ title: { text: "Attitude Angles", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#94A3B8", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Angle (°)", font: { color: "#94A3B8", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ { x: r.time, y: r.ddz_s, type: "scatter", mode: "lines", name: "Heave Accel z̈_s", line: { color: "#F59E0B", width: 2 }, fill: "tozeroy", fillcolor: "rgba(245,158,11,0.06)" } ]}
                        layout={darkLayout({ title: { text: "Heave Acceleration", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#94A3B8", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Acceleration (m/s²)", font: { color: "#94A3B8", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.ddtheta, type: "scatter", mode: "lines", name: "Pitch Accel", line: { color: "#10B981", width: 1.5 } },
                          { x: r.time, y: r.ddphi, type: "scatter", mode: "lines", name: "Roll Accel", line: { color: "#F43F5E", width: 1.5 } }
                        ]}
                        layout={darkLayout({ title: { text: "Angular Accelerations", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#94A3B8", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Accel (rad/s²)", font: { color: "#94A3B8", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                )}

                {/* ── TAB 2: PITCH & ROLL ── */}
                {activeTab === 2 && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[350px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    <PlotBox>
                      <Plot
                        data={[ { x: r.phi?.map((v: number) => v * 180 / Math.PI), y: r.theta?.map((v: number) => v * 180 / Math.PI), type: "scatter", mode: "lines", name: "Coupling", line: { color: "#F59E0B", width: 1.5 } } ]}
                        layout={darkLayout({ title: { text: "Roll vs Pitch Space", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Roll φ (°)", font: { color: "#94A3B8", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Pitch θ (°)", font: { color: "#94A3B8", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ { x: r.theta?.map((v: number) => v * 180 / Math.PI), y: r.dtheta?.map((v: number) => v * 180 / Math.PI), type: "scatter", mode: "lines", name: "Pitch Phase", line: { color: "#10B981", width: 1.5 } } ]}
                        layout={darkLayout({ title: { text: "Pitch Phase Portrait", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "θ (°)", font: { color: "#94A3B8", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "θ̇ (°/s)", font: { color: "#94A3B8", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <Plot
                        data={[ { x: r.phi?.map((v: number) => v * 180 / Math.PI), y: r.dphi?.map((v: number) => v * 180 / Math.PI), type: "scatter", mode: "lines", name: "Roll Phase", line: { color: "#F43F5E", width: 1.5 } } ]}
                        layout={darkLayout({ title: { text: "Roll Phase Portrait", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "φ (°)", font: { color: "#94A3B8", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "φ̇ (°/s)", font: { color: "#94A3B8", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <div className="h-full p-5 flex flex-col justify-center gap-4">
                        <p className="text-[10px] font-bold tracking-widest text-gray-700 uppercase">Roll Characteristics</p>
                        <div className="space-y-3 font-mono text-xs">
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Elastic Roll Dist. (K_φ,f / K_φ,tot)</span><span className="text-[#10B981]">{r.roll_stiffness_dist.toFixed(1)}% Front</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Dynamic LLTD (ΔFz,f / ΔFz,tot)</span><span className="text-cyan-400 font-bold">{((maxOf(r.lateral_load_transfer_f as number[]) + maxOf(r.lateral_load_transfer_r as number[])) > 0 ? (maxOf(r.lateral_load_transfer_f as number[]) / (maxOf(r.lateral_load_transfer_f as number[]) + maxOf(r.lateral_load_transfer_r as number[]))) * 100 : 50).toFixed(1)}% Front</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Front Track</span><span className="text-white">{params.tw_f} m</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Rear Track</span><span className="text-white">{params.tw_r} m</span></div>
                        </div>
                      </div>
                    </PlotBox>
                  </div>
                )}

                {/* ── TAB 3: LOAD TRANSFER ── */}
                {activeTab === 3 && (
                  <div className="grid grid-cols-1 auto-rows-[400px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                    <PlotBox>
                      <Plot
                        data={[
                          { x: r.time, y: r.lateral_load_transfer_f, type: "scatter", mode: "lines", name: "Front LLT", line: { color: "#06B6D4", width: 2 } },
                          { x: r.time, y: r.lateral_load_transfer_r, type: "scatter", mode: "lines", name: "Rear LLT", line: { color: "#F43F5E", width: 2 } }
                        ]}
                        layout={darkLayout({ title: { text: "Lateral Load Transfer (ΔFz)", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#94A3B8", size: 10 } } }, yaxis: { ...DARK_BASE.yaxis, title: { text: "Load Transfer (N)", font: { color: "#94A3B8", size: 10 } } } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: false }}
                      />
                    </PlotBox>
                    <PlotBox>
                      <div className="h-full p-5 flex flex-col justify-center gap-4">
                        <p className="text-[10px] font-bold tracking-widest text-gray-700 uppercase">Load Transfer Summary</p>
                        <div className="space-y-3 font-mono text-xs">
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Max Front LLT (ΔFz,f)</span><span className="text-[#06B6D4]">{maxOf(r.lateral_load_transfer_f as number[]).toFixed(0)} N</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Max Rear LLT (ΔFz,r)</span><span className="text-[#F43F5E]">{maxOf(r.lateral_load_transfer_r as number[]).toFixed(0)} N</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Total Dynamic LLT (ΔFz,tot)</span><span className="text-white">{(maxOf(r.lateral_load_transfer_f as number[]) + maxOf(r.lateral_load_transfer_r as number[])).toFixed(0)} N</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Dynamic LLTD (ΔFz,f / ΔFz,tot)</span><span className="text-cyan-400 font-bold">{((maxOf(r.lateral_load_transfer_f as number[]) + maxOf(r.lateral_load_transfer_r as number[])) > 0 ? (maxOf(r.lateral_load_transfer_f as number[]) / (maxOf(r.lateral_load_transfer_f as number[]) + maxOf(r.lateral_load_transfer_r as number[]))) * 100 : 50).toFixed(1)}% Front</span></div>
                          <div className="flex justify-between items-center border-b border-[#1a1a1a] pb-2"><span className="text-gray-600">Elastic Roll Dist. (K_φ,f / K_φ,tot)</span><span className="text-[#10B981]">{r.roll_stiffness_dist.toFixed(1)}% Front</span></div>
                        </div>
                      </div>
                    </PlotBox>
                  </div>
                )}

                {/* ── TAB 4: PSD ANALYSIS ── */}
                {activeTab === 4 && psdRoll && (
                  <div className="grid grid-cols-1 grid-rows-1 h-full gap-px bg-[#181818]">
                    <PlotBox>
                      <Plot
                        data={[ { x: psdRoll.freqs, y: psdRoll.psd, type: "scatter", mode: "lines", name: "PSD Roll", fill: "tozeroy", fillcolor: "rgba(244,63,94,0.08)", line: { color: "#F43F5E", width: 2 } } ]}
                        layout={darkLayout({ title: { text: "PSD — Roll Acceleration", font: { color: "#888", size: 11 } }, xaxis: { ...DARK_BASE.xaxis, title: { text: "Frequency (Hz)", font: { color: "#94A3B8", size: 10 } }, type: "log", range: [Math.log10(0.1), Math.log10(50)] }, yaxis: { ...DARK_BASE.yaxis, title: { text: "PSD ((rad/s²)²/Hz)", font: { color: "#94A3B8", size: 10 } }, type: "log" } })}
                        useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: false }}
                      />
                    </PlotBox>
                  </div>
                )}
              </div>
            </div>
          )}
          {hasResults && r && <LedgerDock rows={ledgerRows} caption="Full-car ledger" onPinnedChange={handlePinned} />}
        </div>
        </ShellCenter>
        <ShellRight>
          <VerdictRail
            status={verdict.status}
            statusLabel={verdict.label}
            heroes={[
              { label: "Heave ƒₙ", value: hasResults ? (r as any)?.f_n_heave : null, unit: "Hz", decimals: 2 },
              { label: "Roll ƒₙ", value: hasResults ? (r as any)?.f_n_roll : null, unit: "Hz", decimals: 2 },
              { label: "Pitch ƒₙ", value: hasResults ? (r as any)?.f_n_pitch : null, unit: "Hz", decimals: 2 },
            ]}
            solverVersion={(r as any)?.solver_version}
            runId={(r as any)?.run_id}
            inputSha256={(r as any)?.input_sha256}
            action={{ label: "Run Solver", onClick: () => runSimulation(), loading: isRunning }}
          />
        </ShellRight>
      </StudioShell>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div className="h-full flex items-center justify-center text-gray-600 text-sm">Loading simulation environment…</div>}>
      <PlanGate required="PRO" feature="Full-Car (7-DOF) Multi-Body Solver">
        <FullCarDashboard />
      </PlanGate>
    </Suspense>
  );
}

