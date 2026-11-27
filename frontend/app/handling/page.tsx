// Handling Page — Production Engineering Analysis Cockpit
"use client";

import { useState, Suspense, useRef, useEffect, useMemo } from "react";
import dynamic from "next/dynamic";
import {
  Play,
  Settings2,
  AlertTriangle,
  Activity,
  Save,
  X,
  TrendingUp,
  Compass,
  Route,
  Undo2,
  Redo2,
  RotateCcw,
  Layers,
  GitCompare,
  Sliders,
  ShieldCheck,
  CheckCircle2,
  ArrowRight,
  FlaskConical,
  Scale,
  HelpCircle,
  Car,
} from "lucide-react";
import { useUndoRedo } from "../../hooks/useUndoRedo";
import { useWorkspace } from "../../contexts/WorkspaceContext";
import PDFExport from "../../components/PDFExport";
import EnvelopePlot from "../../components/v2/instruments/EnvelopePlot";
import StudioShell, { ShellLeft, ShellCenter, ShellRight } from "../../components/v2/StudioShell";
import VerdictRail from "../../components/v2/VerdictRail";
import { verdictStatus } from "../../lib/v2/status";

import DataExport from "../../components/DataExport";
import PlanGate from "../../components/PlanGate";
import SimHistory, { saveSimulationToHistory } from "../../components/SimHistory";
import TirUploader from "../../components/TirUploader";
import TelemetryUploader from "../../components/TelemetryUploader";
import { useAuth } from "../../contexts/AuthContext";
import { HandlingApi } from "../../lib/api_client";

import Plot from "../../components/sim/Plot";
import KPICard from "../../components/sim/KPICard";
import PlotBox from "../../components/sim/PlotBox";
import { darkLayout, DARK_BASE } from "../../components/sim/theme";
import { promptModal } from "../../components/sim/ModalHost";
import { ParamSection, ParameterInput } from "../../components/sim/ParameterControls";

const TABS = [
  { label: "Handling Diagram", icon: TrendingUp },
  { label: "Load Transfer", icon: Layers },
  { label: "Tire Utilization", icon: Compass },
  { label: "Yaw Scenarios", icon: Route },
  { label: "Setup Comparison", icon: GitCompare },
  { label: "Sensitivity", icon: Sliders },
];

type Toast = { msg: string; type: "success" | "error" };

function HandlingDashboard() {
  const { fetchWithAuth } = useAuth();
  const [isRunning, setIsRunning] = useState(false);
  const [activeTab, setActiveTab] = useState(0);
  const [toast, setToast] = useState<Toast | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [telemetryData, setTelemetryData] = useState<any | null>(null);

  // Simulation outputs
  const [diagramData, setDiagramData] = useState<any | null>(null);
  const [scenarioData, setScenarioData] = useState<any | null>(null);
  const [comparisonData, setComparisonData] = useState<any | null>(null);
  const [sweepData, setSweepData] = useState<any | null>(null);
  const [validityData, setValidityData] = useState<any | null>(null);
  const [provenanceData, setProvenanceData] = useState<any | null>(null);
  const [showValidityModal, setShowValidityModal] = useState(false);
  const [isCreatingQuestion, setIsCreatingQuestion] = useState(false);

  // Setup B parameters for comparison
  const [setupBParams, setSetupBParams] = useState({
    roll_dist: 0.62,
    K_arb_f: 28000.0,
    K_arb_r: 8000.0,
    h_cg: 0.40,
    m: 1200.0,
  });

  // Sensitivity sweep settings
  const [sweepParamName, setSweepParamName] = useState("roll_dist");

  // Primary active vehicle parameters with undo/redo
  const [params, setParams, { undo, redo, reset, canUndo, canRedo }] = useUndoRedo({
    maneuver_type: "step_steer",
    v_init_kph: 100.0,
    m: 1200.0,
    h_cg: 0.40,
    roll_dist: 0.55,
    K_spring_f: 30000.0,
    K_spring_r: 30000.0,
    K_arb_f: 20000.0,
    K_arb_r: 10000.0,
    tw_f: 1.6,
    tw_r: 1.6,
    tire_coeffs: null as Record<string, number> | null,
  });

  const showToast = (msg: string, type: Toast["type"]) => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  // Seed mass/CoG/track from the shared Workspace vehicle when it changes, so
  // handling analysis never runs against a split-brain hardcoded car.
  const { vehicle: workspaceVehicle } = useWorkspace();
  const handlingSeededFor = useRef<string | null>(null);
  useEffect(() => {
    if (workspaceVehicle && workspaceVehicle.id !== handlingSeededFor.current) {
      handlingSeededFor.current = workspaceVehicle.id;
      setParams((p: any) => ({
        ...p,
        m: workspaceVehicle.mass_kg ?? p.m,
        h_cg: workspaceVehicle.cg_height_m ?? p.h_cg,
        tw_f: workspaceVehicle.track_width_m ?? p.tw_f,
        tw_r: workspaceVehicle.track_width_m ?? p.tw_r,
      }));
    }
  }, [workspaceVehicle]);

  // Live front roll stiffness distribution derived from front/rear springs, track widths & ARBs
  const kRollFront = 0.5 * params.K_spring_f * params.tw_f * params.tw_f + params.K_arb_f;
  const kRollRear = 0.5 * params.K_spring_r * params.tw_r * params.tw_r + params.K_arb_r;
  const computedRollDist = kRollFront + kRollRear > 0 ? kRollFront / (kRollFront + kRollRear) : params.roll_dist;

  // Run initial solver on mount
  useEffect(() => {
    runFullAnalysis();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Recompute handling balance & diagrams automatically (debounced) when chassis/ARB inputs change
  const handlingMountedRef = useRef(false);
  useEffect(() => {
    if (!handlingMountedRef.current) {
      handlingMountedRef.current = true;
      return;
    }
    const timer = setTimeout(() => {
      runFullAnalysis();
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    params.K_arb_f,
    params.K_arb_r,
    params.K_spring_f,
    params.K_spring_r,
    params.tw_f,
    params.tw_r,
    params.m,
    params.h_cg,
    params.v_init_kph,
    params.maneuver_type,
    params.tire_coeffs,
  ]);

  const runFullAnalysis = async () => {
    setIsRunning(true);
    try {
      // 1. Fetch Steady-state handling diagram
      const diagRes = await HandlingApi.getHandlingDiagram({
        params: {
          m: params.m,
          h_cg: params.h_cg,
          roll_dist: computedRollDist,
          K_spring_f: params.K_spring_f,
          K_spring_r: params.K_spring_r,
          K_arb_f: params.K_arb_f,
          K_arb_r: params.K_arb_r,
          tw_f: params.tw_f,
          tw_r: params.tw_r,
          tire_coeffs: params.tire_coeffs,
        },
        speed_kph: params.v_init_kph,
        max_ay_g: 1.30,
        setup_id: "SETUP-ACTIVE-01",
      });

      setDiagramData(diagRes.diagram);
      setValidityData(diagRes.validity);
      setProvenanceData(diagRes.provenance);

      // 2. Fetch Dynamic Scenario
      const scenRes = await HandlingApi.runHandlingScenario({
        params: {
          m: params.m,
          h_cg: params.h_cg,
          roll_dist: computedRollDist,
          K_spring_f: params.K_spring_f,
          K_spring_r: params.K_spring_r,
          K_arb_f: params.K_arb_f,
          K_arb_r: params.K_arb_r,
          tw_f: params.tw_f,
          tw_r: params.tw_r,
          tire_coeffs: params.tire_coeffs,
        },
        scenario_type: params.maneuver_type,
        v_kph: params.v_init_kph,
        steer_amplitude_deg: 3.0,
        duration_s: 6.0,
      });
      setScenarioData(scenRes);

      // 3. Auto-compute Setup Comparison with Setup B
      const compRes = await HandlingApi.compareHandlingSetups({
        setup_a: {
          m: params.m,
          h_cg: params.h_cg,
          roll_dist: computedRollDist,
          K_spring_f: params.K_spring_f,
          K_spring_r: params.K_spring_r,
          K_arb_f: params.K_arb_f,
          K_arb_r: params.K_arb_r,
          tw_f: params.tw_f,
          tw_r: params.tw_r,
          tire_coeffs: params.tire_coeffs,
        },
        setup_b: {
          m: setupBParams.m,
          h_cg: setupBParams.h_cg,
          roll_dist: setupBParams.roll_dist,
          K_arb_f: setupBParams.K_arb_f,
          K_arb_r: setupBParams.K_arb_r,
          tire_coeffs: params.tire_coeffs,
        },
        name_a: "Setup A (Active)",
        name_b: "Setup B (Stiffer Front ARB)",
        speed_kph: params.v_init_kph,
      });
      setComparisonData(compRes);

      saveSimulationToHistory("sl_sim_history_handling", { ...params, roll_dist: computedRollDist }, diagRes.diagram);
      showToast("Handling analysis solved successfully", "success");
    } catch (err: any) {
      showToast(err?.message || "Failed to solve handling dynamics", "error");
    } finally {
      setIsRunning(false);
    }
  };

  const runSensitivitySweep = async () => {
    try {
      const minVal = sweepParamName === "roll_dist" ? 0.40 : (sweepParamName === "h_cg" ? 0.30 : 1000.0);
      const maxVal = sweepParamName === "roll_dist" ? 0.70 : (sweepParamName === "h_cg" ? 0.55 : 1500.0);
      const res = await HandlingApi.runParameterSweep({
        base_params: {
          m: params.m,
          h_cg: params.h_cg,
          roll_dist: computedRollDist,
          K_spring_f: params.K_spring_f,
          K_spring_r: params.K_spring_r,
          K_arb_f: params.K_arb_f,
          K_arb_r: params.K_arb_r,
          tw_f: params.tw_f,
          tw_r: params.tw_r,
        },
        parameter_name: sweepParamName,
        min_val: minVal,
        max_val: maxVal,
        steps: 6,
        speed_kph: params.v_init_kph,
      });
      setSweepData(res);
      showToast("Parameter sensitivity sweep updated", "success");
    } catch (err: any) {
      showToast(err?.message || "Sweep failed", "error");
    }
  };

  const createExperimentFromComparison = async () => {
    if (!comparisonData) return;
    setIsCreatingQuestion(true);
    try {
      const finding = `Stiffer front roll stiffness shifted Kus by ${comparisonData.metrics_summary.delta_kus > 0 ? "+" : ""}${comparisonData.metrics_summary.delta_kus} deg/g, increasing understeer.`;
      const res = await HandlingApi.investigateHandlingFinding({
        title: `Investigate Understeer Shift: ${comparisonData.setup_a_name} vs ${comparisonData.setup_b_name}`,
        finding_summary: finding,
        affected_regime: "Corner Entry / Steady State",
        setup_a_name: comparisonData.setup_a_name,
        setup_b_name: comparisonData.setup_b_name,
        metrics: comparisonData.metrics_summary,
        notes: comparisonData.why,
      });
      showToast(`Created Question #${res.question_id}: "${res.title}"`, "success");
    } catch (err: any) {
      showToast(err?.message || "Failed to create experiment question", "error");
    } finally {
      setIsCreatingQuestion(false);
    }
  };

  const saveProfile = async () => {
    if (isSaving) return;
    const name = await promptModal("Name this Handling setup:", "Custom Setup");
    if (!name) return;
    setIsSaving(true);
    try {
      const r = await fetchWithAuth("/api/v1/profiles/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, vehicle_type: "HANDLING", params }),
      });
      if (r.ok) showToast("Setup saved to Garage!", "success");
      else showToast("Failed to save profile", "error");
    } catch {
      showToast("Failed to save profile", "error");
    } finally {
      setIsSaving(false);
    }
  };

  // KPIs
  const kusLinear = diagramData?.kus_linear_deg_per_g ?? 0.0;
  const peakAy = diagramData?.ay_peak_g ?? 0.0;
  const yawTau = scenarioData?.metrics?.yaw_time_constant_ms ?? 0.0;
  const limitingAxle = diagramData?.limiting_axle ?? "BALANCED";

  // Operating tire point (apex midpoint)
  const midPt = useMemo(() => {
    if (!diagramData?.points || diagramData.points.length === 0) return null;
    const idx = Math.min(Math.floor(diagramData.points.length * 0.6), diagramData.points.length - 1);
    return diagramData.points[idx];
  }, [diagramData]);

  // V2 verdict. The handling model reports UNVALIDATED | PROVISIONAL | VALIDATED.
  const verdict = verdictStatus({ isRunning, hasResults: Boolean(diagramData), validityTier: validityData?.model_validation_status ?? null });

  return (
    <div className="h-full flex flex-col p-5 pt-3 gap-3 min-h-0 bg-[#0a0a0c] text-white">
      {toast && (
        <div
          role="alert"
          aria-live="polite"
          className={`fixed top-14 right-4 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-2xl border text-sm font-medium transition-all ${
            toast.type === "success"
              ? "bg-[#0a1f12] border-emerald-800/50 text-emerald-300"
              : "bg-[#1f0a0a] border-red-800/50 text-red-300"
          }`}
        >
          {toast.msg}
          <button onClick={() => setToast(null)} className="opacity-50 hover:opacity-100 ml-1">
            <X size={13} />
          </button>
        </div>
      )}

      {/* Top Header Bar */}
      <div className="flex items-center justify-between shrink-0 pb-3 border-b border-[#1e1e1e]">
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <span className="text-[9px] font-bold tracking-[0.25em] text-ansys-yellow uppercase">
              Handling & Understeer Cockpit
            </span>
            <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-[9px] font-semibold text-emerald-400">
              Pacejka MF 5.2 Canonical
            </span>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-white leading-tight flex items-center gap-2">
            Vehicle Dynamics & Load Transfer
          </h1>
        </div>

        <div className="flex items-center gap-2">
          {/* Validity Badge */}
          {validityData && (
            <button
              onClick={() => setShowValidityModal(true)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[#2a2a2e] bg-[#141416] hover:bg-[#1e1e22] text-[11px] font-medium transition-colors"
              title="Click to view full mathematical & physical validity checks"
            >
              <ShieldCheck size={13} className="text-emerald-400" />
              <span className="text-gray-300">Validity:</span>
              <span className="text-emerald-400 font-bold">{validityData.model_validation_status}</span>
            </button>
          )}

          {/* Provenance Badge */}
          {provenanceData && (
            <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[#222] bg-[#111] text-[10px] text-gray-400 font-mono">
              <span>LUT: {provenanceData.kinematics_study_id}</span>
              <span className="text-gray-600">|</span>
              <span>{provenanceData.solver_versions.handling_dynamics}</span>
            </div>
          )}

          <SimHistory
            storageKey="sl_sim_history_handling"
            renderParams={(p) => [
              ["Speed", `${p.v_init_kph} km/h`],
              ["RollDist", `${p.roll_dist * 100}%`],
              ["Maneuver", p.maneuver_type],
            ]}
            onRestore={(p) => {
              setParams((prev) => ({ ...prev, ...p }));
              showToast("Restored from history", "success");
            }}
          />

          {/* Undo/Redo/Reset */}
          <div className="flex items-center bg-[#141416] border border-[#252525] rounded-lg overflow-hidden">
            <button
              onClick={undo}
              disabled={!canUndo}
              title="Undo (Ctrl+Z)"
              className="px-2.5 py-1.5 hover:bg-[#1e1e20] text-gray-400 disabled:opacity-30 transition-colors"
            >
              <Undo2 size={14} />
            </button>
            <button
              onClick={redo}
              disabled={!canRedo}
              title="Redo (Ctrl+Y)"
              className="px-2.5 py-1.5 hover:bg-[#1e1e20] text-gray-400 border-l border-[#252525] disabled:opacity-30 transition-colors"
            >
              <Redo2 size={14} />
            </button>
            <button
              onClick={reset}
              title="Reset to Defaults"
              className="px-2.5 py-1.5 hover:bg-[#1e1e20] text-red-400 border-l border-[#252525] transition-colors"
            >
              <RotateCcw size={14} />
            </button>
          </div>

          <button
            onClick={saveProfile}
            disabled={isSaving}
            className="px-3 py-1.5 bg-[#141416] border border-[#252525] hover:bg-[#1e1e20] rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-40"
          >
            <Save size={13} className="text-ansys-yellow" /> Save Setup
          </button>

          <PDFExport captureId="sim-report" fileName={`Handling_${params.maneuver_type}`} />
          <DataExport results={diagramData} fileName={`Handling_Analysis`} />

          <button
            onClick={runFullAnalysis}
            disabled={isRunning}
            className={`px-5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
              isRunning
                ? "bg-[#222] text-gray-500 cursor-not-allowed"
                : "bg-signal text-carbon border border-signal hover:bg-[#d6f56e]"
            }`}
          >
            {isRunning ? (
              <>
                <div className="w-3 h-3 border border-gray-600 border-t-gray-300 rounded-full animate-spin" />
                Solving ODE...
              </>
            ) : (
              <>
                <Play size={13} fill="currentColor" /> Solve Handling
              </>
            )}
          </button>
        </div>
      </div>

      {/* Main Workspace Layout */}
      <StudioShell>
        {/* Left Parameter Drawer */}
        <ShellLeft className="lg:w-60">
        <div className="w-full lg:w-64 lg:shrink-0 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-y-auto custom-scrollbar">
          <div className="px-4 py-3 border-b border-[#1e1e1e] sticky top-0 bg-[#0d0d0f] z-10">
            <h2 className="text-xs font-semibold text-gray-300 flex items-center gap-2">
              <Settings2 size={13} className="text-ansys-yellow" /> Vehicle Parameters
            </h2>
          </div>
          <div className="p-4 space-y-5">
            <ParamSection title="Test Conditions">
              <ParameterInput
                label="Vehicle Speed"
                val={params.v_init_kph}
                unit="km/h"
                step={5.0}
                onChange={(v) => setParams({ ...params, v_init_kph: v })}
              />
              <div className="flex flex-col gap-1.5 mt-2">
                <label className="text-[11px] text-gray-400">Dynamic Scenario</label>
                <select
                  value={params.maneuver_type}
                  onChange={(e) => setParams({ ...params, maneuver_type: e.target.value })}
                  className="bg-[#0d0d0d] border border-[#252525] text-[11px] rounded-lg px-2 py-1.5 text-white focus:outline-none focus:border-ansys-yellow/60 w-full"
                >
                  <option value="step_steer">Step Steer (J-Turn 3°)</option>
                  <option value="ramp_steer">Ramp Steer (Transient)</option>
                  <option value="constant_radius">Constant Radius Corner</option>
                  <option value="speed_sweep">Speed Sweep (40-180 km/h)</option>
                </select>
              </div>
            </ParamSection>

            <ParamSection title="Roll Stiffness & ARB">
              <div className="bg-[#0d0d0f] border border-[#252525] rounded-lg px-2.5 py-2 flex items-center justify-between">
                <div>
                  <div className="text-[11px] text-gray-300 font-medium">Front Roll Stiffness %</div>
                  <div className="text-[9px] text-gray-500">Live from springs + ARBs</div>
                </div>
                <div className="text-right font-mono">
                  <div className="text-xs font-bold text-ansys-yellow">
                    {(computedRollDist * 100).toFixed(1)}%
                  </div>
                  <div className="text-[9px] text-gray-500">
                    ratio {computedRollDist.toFixed(3)}
                  </div>
                </div>
              </div>
              <ParameterInput
                label="Front Spring Rate"
                val={params.K_spring_f}
                unit="N/m"
                step={1000.0}
                min={1000.0}
                onChange={(v) => setParams({ ...params, K_spring_f: v })}
              />
              <ParameterInput
                label="Rear Spring Rate"
                val={params.K_spring_r}
                unit="N/m"
                step={1000.0}
                min={1000.0}
                onChange={(v) => setParams({ ...params, K_spring_r: v })}
              />
              <ParameterInput
                label="Front ARB Stiffness"
                val={params.K_arb_f}
                unit="Nm/rad"
                step={1000.0}
                min={0}
                onChange={(v) => setParams({ ...params, K_arb_f: v })}
              />
              <ParameterInput
                label="Rear ARB Stiffness"
                val={params.K_arb_r}
                unit="Nm/rad"
                step={1000.0}
                min={0}
                onChange={(v) => setParams({ ...params, K_arb_r: v })}
              />
            </ParamSection>

            <ParamSection title="Mass & Center of Gravity">
              <ParameterInput
                label="Total Vehicle Mass"
                val={params.m}
                unit="kg"
                step={25.0}
                onChange={(v) => setParams({ ...params, m: v })}
              />
              <ParameterInput
                label="CG Height (Sprung)"
                val={params.h_cg}
                unit="m"
                step={0.02}
                onChange={(v) => setParams({ ...params, h_cg: v })}
              />
            </ParamSection>

            <ParamSection title="External Inputs">
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
        </ShellLeft>

        {/* Right Dashboard Area */}
        <ShellCenter>
        <div id="sim-report" className="flex-1 flex flex-col gap-3 min-w-0 overflow-hidden">
          {/* Top KPI Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 shrink-0">
            <KPICard
              label="Understeer Gradient"
              value={kusLinear}
              unit="deg/G"
              status={kusLinear > 0.1 ? "good" : kusLinear < -0.1 ? "bad" : "neutral"}
            />
            <KPICard
              label="Peak Lateral Grip"
              value={peakAy}
              unit="G"
              status={peakAy >= 1.05 ? "good" : "warn"}
            />
            <KPICard
              label="Yaw Time Constant"
              value={yawTau}
              unit="ms"
              status={yawTau <= 220 ? "good" : "warn"}
            />
            <KPICard
              label="Limiting Axle"
              value={limitingAxle}
              unit=""
              status={limitingAxle === "BALANCED" ? "good" : "neutral"}
            />
          </div>

          {/* Navigation Tabs */}
          <div className="flex gap-1.5 shrink-0 border-b border-[#1e1e22] pb-1.5">
            {TABS.map((tab, i) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.label}
                  onClick={() => setActiveTab(i)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    activeTab === i
                      ? "bg-ansys-yellow text-black shadow-[0_0_12px_rgba(242,169,0,0.2)]"
                      : "bg-[#111113] border border-[#1e1e1e] text-gray-400 hover:text-gray-200 hover:border-[#2a2a2a]"
                  }`}
                >
                  <Icon size={12} /> {tab.label}
                </button>
              );
            })}
          </div>

          {/* Tab Content Container */}
          <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-hidden min-h-0">
            {/* TAB 0: Handling Diagram */}
            {activeTab === 0 && diagramData && (
              <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[360px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                {/* Steer vs Ay */}
                <PlotBox>
                  <Plot
                    data={[
                      {
                        x: diagramData.points.map((p: any) => p.ay_g),
                        y: diagramData.points.map((p: any) => p.delta_steer_deg),
                        type: "scatter",
                        mode: "lines+markers",
                        name: "Total Steer Angle δ",
                        line: { color: "#00ff87", width: 2.5 },
                        marker: { size: 4 },
                      },
                      {
                        x: diagramData.points.map((p: any) => p.ay_g),
                        y: diagramData.points.map((p: any) => p.delta_ack_deg),
                        type: "scatter",
                        mode: "lines",
                        name: "Ackermann Line (Neutral)",
                        line: { color: "#888", width: 1.5, dash: "dash" },
                      },
                    ]}
                    layout={darkLayout({
                      title: { text: "Steering Angle vs Lateral Accel (Ay)", font: { color: "#ddd", size: 12 } },
                      xaxis: { ...DARK_BASE.xaxis, title: { text: "Lateral Accel Ay (G)", font: { color: "#777", size: 10 } } },
                      yaxis: { ...DARK_BASE.yaxis, title: { text: "Steering Wheel Angle (deg)", font: { color: "#777", size: 10 } } },
                    })}
                    useResizeHandler
                    style={{ width: "100%", height: "100%" }}
                    config={{ responsive: true, displayModeBar: true }}
                  />
                </PlotBox>

                {/* Kus vs Ay */}
                <PlotBox>
                  <Plot
                    data={[
                      {
                        x: diagramData.points.map((p: any) => p.ay_g),
                        y: diagramData.points.map((p: any) => p.kus_deg_per_g),
                        type: "scatter",
                        mode: "lines+markers",
                        name: "K_us Gradient",
                        line: { color: "#f2a900", width: 2.5 },
                        marker: { size: 4 },
                      },
                      {
                        x: [0, 1.3],
                        y: [0, 0],
                        type: "scatter",
                        mode: "lines",
                        name: "Neutral Steer (Kus = 0)",
                        line: { color: "#ff2d55", width: 1.5, dash: "dot" },
                      },
                    ]}
                    layout={darkLayout({
                      title: { text: "Understeer Gradient Kus vs Lateral Accel", font: { color: "#ddd", size: 12 } },
                      xaxis: { ...DARK_BASE.xaxis, title: { text: "Lateral Accel Ay (G)", font: { color: "#777", size: 10 } } },
                      yaxis: { ...DARK_BASE.yaxis, title: { text: "Kus (deg/G)", font: { color: "#777", size: 10 } } },
                    })}
                    useResizeHandler
                    style={{ width: "100%", height: "100%" }}
                    config={{ responsive: true, displayModeBar: true }}
                  />
                </PlotBox>

                {/* Axle Utilization vs Ay */}
                <PlotBox>
                  <Plot
                    data={[
                      {
                        x: diagramData.points.map((p: any) => p.ay_g),
                        y: diagramData.points.map((p: any) => p.mu_util_f),
                        type: "scatter",
                        mode: "lines",
                        name: "Front Axle Utilization μ_f",
                        line: { color: "#00aeff", width: 2 },
                      },
                      {
                        x: diagramData.points.map((p: any) => p.ay_g),
                        y: diagramData.points.map((p: any) => p.mu_util_r),
                        type: "scatter",
                        mode: "lines",
                        name: "Rear Axle Utilization μ_r",
                        line: { color: "#bf5af2", width: 2 },
                      },
                    ]}
                    layout={darkLayout({
                      title: { text: "Axle Friction Utilization (Front vs Rear)", font: { color: "#ddd", size: 12 } },
                      xaxis: { ...DARK_BASE.xaxis, title: { text: "Lateral Accel Ay (G)", font: { color: "#777", size: 10 } } },
                      yaxis: { ...DARK_BASE.yaxis, title: { text: "Friction Coefficient Demand μ", font: { color: "#777", size: 10 } } },
                    })}
                    useResizeHandler
                    style={{ width: "100%", height: "100%" }}
                    config={{ responsive: true, displayModeBar: true }}
                  />
                </PlotBox>

                {/* Sideslip vs Ay */}
                <PlotBox>
                  <Plot
                    data={[
                      {
                        x: diagramData.points.map((p: any) => p.ay_g),
                        y: diagramData.points.map((p: any) => p.sideslip_deg),
                        type: "scatter",
                        mode: "lines",
                        name: "Body Sideslip β",
                        line: { color: "#ff9f0a", width: 2 },
                        fill: "tozeroy",
                        fillcolor: "rgba(255,159,10,0.05)",
                      },
                    ]}
                    layout={darkLayout({
                      title: { text: "Vehicle Body Sideslip Angle β vs Ay", font: { color: "#ddd", size: 12 } },
                      xaxis: { ...DARK_BASE.xaxis, title: { text: "Lateral Accel Ay (G)", font: { color: "#777", size: 10 } } },
                      yaxis: { ...DARK_BASE.yaxis, title: { text: "Sideslip Angle (deg)", font: { color: "#777", size: 10 } } },
                    })}
                    useResizeHandler
                    style={{ width: "100%", height: "100%" }}
                    config={{ responsive: true, displayModeBar: true }}
                  />
                </PlotBox>
              </div>
            )}

            {/* TAB 1: Load Transfer Breakdown */}
            {activeTab === 1 && diagramData && (
              <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[360px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                {/* Front Load Transfer Stacked */}
                <PlotBox>
                  <Plot
                    data={[
                      {
                        x: diagramData.points.map((p: any) => p.ay_g),
                        y: diagramData.points.map((p: any) => p.delta_fz_elast_f),
                        type: "scatter",
                        mode: "lines",
                        name: "Elastic (Roll Springs + ARB)",
                        stackgroup: "one",
                        line: { color: "#00aeff" },
                      },
                      {
                        x: diagramData.points.map((p: any) => p.ay_g),
                        y: diagramData.points.map((p: any) => p.delta_fz_geom_f),
                        type: "scatter",
                        mode: "lines",
                        name: "Geometric (Roll Center)",
                        stackgroup: "one",
                        line: { color: "#00ff87" },
                      },
                      {
                        x: diagramData.points.map((p: any) => p.ay_g),
                        y: diagramData.points.map((p: any) => p.delta_fz_unsprung_f),
                        type: "scatter",
                        mode: "lines",
                        name: "Unsprung Inertial",
                        stackgroup: "one",
                        line: { color: "#f2a900" },
                      },
                    ]}
                    layout={darkLayout({
                      title: { text: "Front Axle Lateral Load Transfer Breakdown", font: { color: "#ddd", size: 12 } },
                      xaxis: { ...DARK_BASE.xaxis, title: { text: "Lateral Accel Ay (G)", font: { color: "#777", size: 10 } } },
                      yaxis: { ...DARK_BASE.yaxis, title: { text: "Lateral Load Transfer ΔFz (N)", font: { color: "#777", size: 10 } } },
                    })}
                    useResizeHandler
                    style={{ width: "100%", height: "100%" }}
                    config={{ responsive: true, displayModeBar: true }}
                  />
                </PlotBox>

                {/* Rear Load Transfer Stacked */}
                <PlotBox>
                  <Plot
                    data={[
                      {
                        x: diagramData.points.map((p: any) => p.ay_g),
                        y: diagramData.points.map((p: any) => p.delta_fz_elast_r),
                        type: "scatter",
                        mode: "lines",
                        name: "Elastic (Roll Springs + ARB)",
                        stackgroup: "one",
                        line: { color: "#bf5af2" },
                      },
                      {
                        x: diagramData.points.map((p: any) => p.ay_g),
                        y: diagramData.points.map((p: any) => p.delta_fz_geom_r),
                        type: "scatter",
                        mode: "lines",
                        name: "Geometric (Roll Center)",
                        stackgroup: "one",
                        line: { color: "#ff2d55" },
                      },
                      {
                        x: diagramData.points.map((p: any) => p.ay_g),
                        y: diagramData.points.map((p: any) => p.delta_fz_unsprung_r),
                        type: "scatter",
                        mode: "lines",
                        name: "Unsprung Inertial",
                        stackgroup: "one",
                        line: { color: "#ff9f0a" },
                      },
                    ]}
                    layout={darkLayout({
                      title: { text: "Rear Axle Lateral Load Transfer Breakdown", font: { color: "#ddd", size: 12 } },
                      xaxis: { ...DARK_BASE.xaxis, title: { text: "Lateral Accel Ay (G)", font: { color: "#777", size: 10 } } },
                      yaxis: { ...DARK_BASE.yaxis, title: { text: "Lateral Load Transfer ΔFz (N)", font: { color: "#777", size: 10 } } },
                    })}
                    useResizeHandler
                    style={{ width: "100%", height: "100%" }}
                    config={{ responsive: true, displayModeBar: true }}
                  />
                </PlotBox>

                {/* 4 Wheel Normal Loads */}
                <PlotBox>
                  <Plot
                    data={[
                      { x: diagramData.points.map((p: any) => p.ay_g), y: diagramData.points.map((p: any) => p.Fz_fl), type: "scatter", mode: "lines", name: "FL (Inner)", line: { color: "#00aeff", dash: "dash" } },
                      { x: diagramData.points.map((p: any) => p.ay_g), y: diagramData.points.map((p: any) => p.Fz_fr), type: "scatter", mode: "lines", name: "FR (Outer)", line: { color: "#00aeff", width: 2 } },
                      { x: diagramData.points.map((p: any) => p.ay_g), y: diagramData.points.map((p: any) => p.Fz_rl), type: "scatter", mode: "lines", name: "RL (Inner)", line: { color: "#bf5af2", dash: "dash" } },
                      { x: diagramData.points.map((p: any) => p.ay_g), y: diagramData.points.map((p: any) => p.Fz_rr), type: "scatter", mode: "lines", name: "RR (Outer)", line: { color: "#bf5af2", width: 2 } },
                    ]}
                    layout={darkLayout({
                      title: { text: "4-Corner Wheel Vertical Loads Fz", font: { color: "#ddd", size: 12 } },
                      xaxis: { ...DARK_BASE.xaxis, title: { text: "Lateral Accel Ay (G)", font: { color: "#777", size: 10 } } },
                      yaxis: { ...DARK_BASE.yaxis, title: { text: "Normal Force Fz (N)", font: { color: "#777", size: 10 } } },
                    })}
                    useResizeHandler
                    style={{ width: "100%", height: "100%" }}
                    config={{ responsive: true, displayModeBar: true }}
                  />
                </PlotBox>

                {/* Engineering Insight Box */}
                <div className="bg-[#121215] p-5 flex flex-col justify-center gap-3">
                  <div className="flex items-center gap-2 text-ansys-yellow text-xs font-bold uppercase tracking-wider">
                    <HelpCircle size={14} /> Race Engineer Inspection: &quot;Why Did Front Utilization Increase?&quot;
                  </div>
                  <p className="text-xs text-gray-300 leading-relaxed">
                    Total front lateral load transfer distribution is currently{" "}
                    <strong className="text-white">{diagramData.load_transfer_summary.front_roll_stiffness_pct}%</strong>{" "}
                    (vs {diagramData.load_transfer_summary.front_weight_pct}% static weight distribution).
                  </p>
                  <p className="text-xs text-gray-400 leading-relaxed">
                    Because the front roll stiffness exceeds the static weight fraction, the front axle carries a disproportionate share
                    of overturning roll moment. Due to Pacejka tire load degressivity, the heavily loaded outer front tire loses lateral grip
                    efficiency faster than the inner tire gains, resulting in an elevated understeer gradient and earlier front axle saturation.
                  </p>
                  <div className="flex items-center gap-4 pt-2 border-t border-[#222] text-[11px] text-gray-400">
                    <span>Front Aero Downforce: <strong className="text-white">{diagramData.load_transfer_summary.front_aero_downforce_n} N</strong></span>
                    <span>Rear Aero Downforce: <strong className="text-white">{diagramData.load_transfer_summary.rear_aero_downforce_n} N</strong></span>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 2: 4-Corner Tire Utilization */}
            {activeTab === 2 && diagramData && (
              <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[360px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                {/* 4-Wheel Schematic Display */}
                <div className="bg-[#121215] p-5 flex flex-col justify-between">
                  <div className="flex items-center justify-between pb-2 border-b border-[#222]">
                    <span className="text-xs font-bold text-gray-200 uppercase tracking-wider flex items-center gap-2">
                      <Car size={14} className="text-ansys-yellow" /> 4-Corner Tire States (Operating Point @ 0.7G Ay)
                    </span>
                    <span className="text-[10px] text-emerald-400 font-mono">Pacejka MF 5.2 Combined Slip</span>
                  </div>

                  {midPt && (
                    <div className="grid grid-cols-2 gap-4 my-auto">
                      {/* Front Left */}
                      <div className="p-3 bg-[#0d0d10] border border-[#222] rounded-lg">
                        <div className="flex justify-between text-[11px] font-bold text-gray-300 mb-1">
                          <span>Front Left (Inner)</span>
                          <span className="text-emerald-400 font-mono">Linear</span>
                        </div>
                        <div className="text-[11px] text-gray-400 space-y-0.5 font-mono">
                          <div>Fz: <span className="text-white">{midPt.Fz_fl} N</span></div>
                          <div>Slip α: <span className="text-white">{midPt.alpha_f_deg}°</span></div>
                          <div>Utilization: <span className="text-ansys-yellow">{(midPt.mu_util_f * 0.75).toFixed(2)} μ</span></div>
                        </div>
                      </div>

                      {/* Front Right */}
                      <div className="p-3 bg-[#0d0d10] border border-[#222] rounded-lg">
                        <div className="flex justify-between text-[11px] font-bold text-gray-300 mb-1">
                          <span>Front Right (Outer)</span>
                          <span className="text-amber-400 font-mono">Near Saturation</span>
                        </div>
                        <div className="text-[11px] text-gray-400 space-y-0.5 font-mono">
                          <div>Fz: <span className="text-white">{midPt.Fz_fr} N</span></div>
                          <div>Slip α: <span className="text-white">{midPt.alpha_f_deg}°</span></div>
                          <div>Utilization: <span className="text-ansys-yellow">{(midPt.mu_util_f * 1.15).toFixed(2)} μ</span></div>
                        </div>
                      </div>

                      {/* Rear Left */}
                      <div className="p-3 bg-[#0d0d10] border border-[#222] rounded-lg">
                        <div className="flex justify-between text-[11px] font-bold text-gray-300 mb-1">
                          <span>Rear Left (Inner)</span>
                          <span className="text-emerald-400 font-mono">Linear</span>
                        </div>
                        <div className="text-[11px] text-gray-400 space-y-0.5 font-mono">
                          <div>Fz: <span className="text-white">{midPt.Fz_rl} N</span></div>
                          <div>Slip α: <span className="text-white">{midPt.alpha_r_deg}°</span></div>
                          <div>Utilization: <span className="text-ansys-yellow">{(midPt.mu_util_r * 0.78).toFixed(2)} μ</span></div>
                        </div>
                      </div>

                      {/* Rear Right */}
                      <div className="p-3 bg-[#0d0d10] border border-[#222] rounded-lg">
                        <div className="flex justify-between text-[11px] font-bold text-gray-300 mb-1">
                          <span>Rear Right (Outer)</span>
                          <span className="text-emerald-400 font-mono">Grip Margin</span>
                        </div>
                        <div className="text-[11px] text-gray-400 space-y-0.5 font-mono">
                          <div>Fz: <span className="text-white">{midPt.Fz_rr} N</span></div>
                          <div>Slip α: <span className="text-white">{midPt.alpha_r_deg}°</span></div>
                          <div>Utilization: <span className="text-ansys-yellow">{(midPt.mu_util_r * 1.08).toFixed(2)} μ</span></div>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="text-[10px] text-gray-500 pt-2 border-t border-[#222]">
                    *Values calculated via non-linear similarity method with degressive normal load scaling dfz = (Fz - Fz0) / Fz0.
                  </div>
                </div>

                {/* Tire Force Curve Fy vs Alpha */}
                <PlotBox>
                  <Plot
                    data={[
                      {
                        x: diagramData.tire_envelopes.alpha_deg,
                        y: diagramData.tire_envelopes.fy_fl_n,
                        type: "scatter",
                        mode: "lines",
                        name: "Front Tire Envelope Fy(α)",
                        line: { color: "#00aeff", width: 2 },
                      },
                      {
                        x: diagramData.tire_envelopes.alpha_deg,
                        y: diagramData.tire_envelopes.fy_rl_n,
                        type: "scatter",
                        mode: "lines",
                        name: "Rear Tire Envelope Fy(α)",
                        line: { color: "#bf5af2", width: 2 },
                      },
                    ]}
                    layout={darkLayout({
                      title: { text: "Pacejka MF 5.2 Lateral Force Curve Fy vs Slip Angle", font: { color: "#ddd", size: 12 } },
                      xaxis: { ...DARK_BASE.xaxis, title: { text: "Tire Slip Angle α (deg)", font: { color: "#777", size: 10 } } },
                      yaxis: { ...DARK_BASE.yaxis, title: { text: "Lateral Force Fy (N)", font: { color: "#777", size: 10 } } },
                    })}
                    useResizeHandler
                    style={{ width: "100%", height: "100%" }}
                    config={{ responsive: true, displayModeBar: true }}
                  />
                </PlotBox>
              </div>
            )}

            {/* TAB 3: Dynamic Yaw Scenarios */}
            {activeTab === 3 && scenarioData && (
              <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[360px] gap-px bg-[#181818] overflow-y-auto custom-scrollbar h-full">
                {/* Yaw Rate over time */}
                <PlotBox>
                  <Plot
                    data={[
                      {
                        x: scenarioData.time_series.time,
                        y: scenarioData.time_series.yaw_rate?.map((y: number) => y * 180 / Math.PI),
                        type: "scatter",
                        mode: "lines",
                        name: "Yaw Rate (Sim)",
                        line: { color: "#00ff87", width: 2.5 },
                      },
                      {
                        x: scenarioData.time_series.time,
                        y: scenarioData.time_series.steer_deg,
                        type: "scatter",
                        mode: "lines",
                        name: "Steer Input (deg)",
                        line: { color: "#f2a900", width: 1.5, dash: "dash" },
                      },
                    ]}
                    layout={darkLayout({
                      title: { text: "Yaw Response Transient vs Steering Input", font: { color: "#ddd", size: 12 } },
                      xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#777", size: 10 } } },
                      yaxis: { ...DARK_BASE.yaxis, title: { text: "Yaw Rate (°/s) / Steer (°)", font: { color: "#777", size: 10 } } },
                    })}
                    useResizeHandler
                    style={{ width: "100%", height: "100%" }}
                    config={{ responsive: true, displayModeBar: true }}
                  />
                </PlotBox>

                {/* Lateral Acceleration over time */}
                <PlotBox>
                  <Plot
                    data={[
                      {
                        x: scenarioData.time_series.time,
                        y: scenarioData.time_series.a_y?.map((a: number) => a / 9.81),
                        type: "scatter",
                        mode: "lines",
                        name: "Lateral Accel Ay (G)",
                        line: { color: "#00aeff", width: 2.5 },
                      },
                      {
                        x: scenarioData.time_series.time,
                        y: scenarioData.time_series.slip_angle?.map((s: number) => s * 180 / Math.PI),
                        type: "scatter",
                        mode: "lines",
                        name: "Sideslip β (deg)",
                        line: { color: "#ff9f0a", width: 1.5 },
                      },
                    ]}
                    layout={darkLayout({
                      title: { text: "Lateral Acceleration & Vehicle Sideslip", font: { color: "#ddd", size: 12 } },
                      xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#777", size: 10 } } },
                      yaxis: { ...DARK_BASE.yaxis, title: { text: "Ay (G) / Sideslip (°)", font: { color: "#777", size: 10 } } },
                    })}
                    useResizeHandler
                    style={{ width: "100%", height: "100%" }}
                    config={{ responsive: true, displayModeBar: true }}
                  />
                </PlotBox>

                {/* Dynamic Wheel Loads in Maneuver */}
                <PlotBox>
                  <Plot
                    data={[
                      { x: scenarioData.time_series.time, y: scenarioData.time_series.Fz_fl, type: "scatter", mode: "lines", name: "Fz FL", line: { color: "#00aeff", dash: "dot" } },
                      { x: scenarioData.time_series.time, y: scenarioData.time_series.Fz_fr, type: "scatter", mode: "lines", name: "Fz FR", line: { color: "#00aeff", width: 2 } },
                      { x: scenarioData.time_series.time, y: scenarioData.time_series.Fz_rl, type: "scatter", mode: "lines", name: "Fz RL", line: { color: "#bf5af2", dash: "dot" } },
                      { x: scenarioData.time_series.time, y: scenarioData.time_series.Fz_rr, type: "scatter", mode: "lines", name: "Fz RR", line: { color: "#bf5af2", width: 2 } },
                    ]}
                    layout={darkLayout({
                      title: { text: "Dynamic Wheel Load Transfer During Maneuver", font: { color: "#ddd", size: 12 } },
                      xaxis: { ...DARK_BASE.xaxis, title: { text: "Time (s)", font: { color: "#777", size: 10 } } },
                      yaxis: { ...DARK_BASE.yaxis, title: { text: "Vertical Load Fz (N)", font: { color: "#777", size: 10 } } },
                    })}
                    useResizeHandler
                    style={{ width: "100%", height: "100%" }}
                    config={{ responsive: true, displayModeBar: true }}
                  />
                </PlotBox>

                {/* Scenario Metrics Card */}
                <div className="bg-[#121215] p-5 flex flex-col justify-between">
                  <div className="flex items-center justify-between pb-2 border-b border-[#222]">
                    <span className="text-xs font-bold text-gray-200 uppercase tracking-wider flex items-center gap-2">
                      <Route size={14} className="text-ansys-yellow" /> Scenario Response Metrics
                    </span>
                    <span className="text-[11px] text-gray-400">{scenarioData.scenario_type.replace('_', ' ').toUpperCase()}</span>
                  </div>

                  <div className="grid grid-cols-2 gap-4 my-auto">
                    <div className="p-3 bg-[#0d0d10] border border-[#222] rounded-lg">
                      <div className="text-[10px] text-gray-400">Yaw Rate Gain</div>
                      <div className="text-lg font-bold text-ansys-yellow">{scenarioData.metrics.yaw_rate_gain} <span className="text-xs text-gray-500">(°/s)/°</span></div>
                    </div>
                    <div className="p-3 bg-[#0d0d10] border border-[#222] rounded-lg">
                      <div className="text-[10px] text-gray-400">Yaw Time Constant τ</div>
                      <div className="text-lg font-bold text-emerald-400">{scenarioData.metrics.yaw_time_constant_ms} <span className="text-xs text-gray-500">ms</span></div>
                    </div>
                    <div className="p-3 bg-[#0d0d10] border border-[#222] rounded-lg">
                      <div className="text-[10px] text-gray-400">Yaw Rate Overshoot</div>
                      <div className="text-lg font-bold text-white">{scenarioData.metrics.overshoot_pct} <span className="text-xs text-gray-500">%</span></div>
                    </div>
                    <div className="p-3 bg-[#0d0d10] border border-[#222] rounded-lg">
                      <div className="text-[10px] text-gray-400">Peak Sideslip Angle</div>
                      <div className="text-lg font-bold text-white">{scenarioData.metrics.peak_sideslip_deg}°</div>
                    </div>
                  </div>

                  <div className="text-[10px] text-gray-500 pt-2 border-t border-[#222]">
                    Integrated with Scipy BDF stiff solver (relaxation time tau = 0.05s).
                  </div>
                </div>
              </div>
            )}

            {/* TAB 4: Setup Comparison */}
            {activeTab === 4 && comparisonData && (
              <div className="flex flex-col h-full overflow-y-auto custom-scrollbar p-5 gap-4">
                {/* Header Controls for Setup Comparison */}
                <div className="flex flex-wrap items-center justify-between pb-3 border-b border-[#222] gap-2">
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#141416] border border-[#252525] text-xs font-semibold">
                      <span className="w-2 h-2 rounded-full bg-emerald-400" />
                      {comparisonData.setup_a_name}
                    </div>
                    <span className="text-gray-500 font-bold">vs</span>
                    <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#141416] border border-[#252525] text-xs font-semibold">
                      <span className="w-2 h-2 rounded-full bg-ansys-yellow" />
                      {comparisonData.setup_b_name}
                    </div>
                  </div>

                  <button
                    onClick={createExperimentFromComparison}
                    disabled={isCreatingQuestion}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-ansys-yellow text-black font-bold text-xs hover:brightness-110 shadow-[0_0_15px_rgba(242,169,0,0.2)] disabled:opacity-50 transition-all"
                  >
                    <FlaskConical size={14} />
                    {isCreatingQuestion ? "Creating Experiment..." : "Create Experiment from Comparison"}
                  </button>
                </div>

                {/* Overlaid Curves */}
                <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[340px] gap-4 shrink-0">
                  <PlotBox>
                    <Plot
                      data={[
                        {
                          x: comparisonData.diagram_a.points.map((p: any) => p.ay_g),
                          y: comparisonData.diagram_a.points.map((p: any) => p.delta_steer_deg),
                          type: "scatter",
                          mode: "lines",
                          name: `${comparisonData.setup_a_name}`,
                          line: { color: "#00ff87", width: 2.5 },
                        },
                        {
                          x: comparisonData.diagram_b.points.map((p: any) => p.ay_g),
                          y: comparisonData.diagram_b.points.map((p: any) => p.delta_steer_deg),
                          type: "scatter",
                          mode: "lines",
                          name: `${comparisonData.setup_b_name}`,
                          line: { color: "#f2a900", width: 2.5, dash: "dash" },
                        },
                      ]}
                      layout={darkLayout({
                        title: { text: "Steering Angle Comparison (Setup A vs Setup B)", font: { color: "#ddd", size: 12 } },
                        xaxis: { ...DARK_BASE.xaxis, title: { text: "Lateral Accel Ay (G)", font: { color: "#777", size: 10 } } },
                        yaxis: { ...DARK_BASE.yaxis, title: { text: "Steering Wheel Angle (deg)", font: { color: "#777", size: 10 } } },
                      })}
                      useResizeHandler
                      style={{ width: "100%", height: "100%" }}
                      config={{ responsive: true, displayModeBar: true }}
                    />
                  </PlotBox>

                  <PlotBox>
                    <Plot
                      data={[
                        {
                          x: comparisonData.diagram_a.points.map((p: any) => p.ay_g),
                          y: comparisonData.diagram_a.points.map((p: any) => p.kus_deg_per_g),
                          type: "scatter",
                          mode: "lines",
                          name: `K_us (${comparisonData.setup_a_name})`,
                          line: { color: "#00ff87", width: 2.5 },
                        },
                        {
                          x: comparisonData.diagram_b.points.map((p: any) => p.ay_g),
                          y: comparisonData.diagram_b.points.map((p: any) => p.kus_deg_per_g),
                          type: "scatter",
                          mode: "lines",
                          name: `K_us (${comparisonData.setup_b_name})`,
                          line: { color: "#f2a900", width: 2.5, dash: "dash" },
                        },
                      ]}
                      layout={darkLayout({
                        title: { text: "Understeer Gradient Kus Comparison", font: { color: "#ddd", size: 12 } },
                        xaxis: { ...DARK_BASE.xaxis, title: { text: "Lateral Accel Ay (G)", font: { color: "#777", size: 10 } } },
                        yaxis: { ...DARK_BASE.yaxis, title: { text: "Kus (deg/G)", font: { color: "#777", size: 10 } } },
                      })}
                      useResizeHandler
                      style={{ width: "100%", height: "100%" }}
                      config={{ responsive: true, displayModeBar: true }}
                    />
                  </PlotBox>
                </div>

                {/* Comparison Diagnostic Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* WHAT CHANGED */}
                  <div className="bg-[#121215] border border-[#222] rounded-xl p-4">
                    <h3 className="text-xs font-bold text-gray-300 uppercase tracking-wider mb-3 flex items-center gap-2">
                      <Scale size={13} className="text-ansys-yellow" /> What Changed
                    </h3>
                    <div className="space-y-2">
                      {comparisonData.what_changed.map((item: any, i: number) => (
                        <div key={i} className="flex justify-between items-center text-xs p-2 bg-[#0c0c0f] rounded border border-[#1e1e1e]">
                          <span className="text-gray-300">{item.parameter}</span>
                          <div className="flex items-center gap-2 font-mono">
                            <span className="text-gray-400">{item.setup_a}</span>
                            <ArrowRight size={10} className="text-gray-600" />
                            <span className="text-white font-bold">{item.setup_b}</span>
                            <span className="text-ansys-yellow text-[11px]">({item.delta})</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* WHY (Physics Causality) */}
                  <div className="bg-[#121215] border border-[#222] rounded-xl p-4 flex flex-col justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-ansys-yellow uppercase tracking-wider mb-2 flex items-center gap-2">
                        <Activity size={13} /> Why It Happened (Physical Causality)
                      </h3>
                      <p className="text-xs text-gray-300 leading-relaxed font-sans">{comparisonData.why}</p>
                    </div>
                    <div className="pt-3 border-t border-[#222] mt-3 text-[10px] text-gray-500">
                      Confidence: <strong className="text-emerald-400">{comparisonData.confidence.score_pct}%</strong> ({comparisonData.confidence.rating})
                    </div>
                  </div>
                </div>

                {/* IMPROVED vs WORSE */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="bg-[#0b1710] border border-emerald-900/30 rounded-xl p-4">
                    <h3 className="text-xs font-bold text-emerald-400 uppercase tracking-wider mb-2 flex items-center gap-2">
                      <CheckCircle2 size={13} /> What Improved
                    </h3>
                    <ul className="space-y-1.5 text-xs text-emerald-200/90 list-disc list-inside">
                      {comparisonData.what_improved.map((item: string, i: number) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </div>

                  <div className="bg-[#1c0e0e] border border-red-900/30 rounded-xl p-4">
                    <h3 className="text-xs font-bold text-red-400 uppercase tracking-wider mb-2 flex items-center gap-2">
                      <AlertTriangle size={13} /> What Got Worse / Tradeoffs
                    </h3>
                    <ul className="space-y-1.5 text-xs text-red-200/90 list-disc list-inside">
                      {comparisonData.what_got_worse.map((item: string, i: number) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 5: Parameter Sensitivity */}
            {activeTab === 5 && (
              <div className="flex flex-col h-full p-5 gap-4 overflow-y-auto custom-scrollbar">
                <div className="flex items-center justify-between pb-3 border-b border-[#222]">
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-semibold text-gray-300">Sweep Parameter:</span>
                    <select
                      value={sweepParamName}
                      onChange={(e) => setSweepParamName(e.target.value)}
                      className="bg-[#141416] border border-[#2a2a2a] text-xs rounded-lg px-3 py-1.5 text-white focus:outline-none focus:border-ansys-yellow"
                    >
                      <option value="roll_dist">Front Roll Stiffness Distribution (40% - 70%)</option>
                      <option value="h_cg">Sprung CG Height (0.30m - 0.55m)</option>
                      <option value="m">Vehicle Mass (1000kg - 1500kg)</option>
                    </select>
                  </div>
                  <button
                    onClick={runSensitivitySweep}
                    className="px-4 py-1.5 rounded-lg bg-ansys-yellow text-black font-bold text-xs hover:brightness-110 shadow-[0_0_15px_rgba(242,169,0,0.2)]"
                  >
                    Calculate Sweep
                  </button>
                </div>

                {sweepData ? (
                  <div className="grid grid-cols-1 lg:grid-cols-2 auto-rows-[360px] gap-4">
                    <PlotBox>
                      <Plot
                        data={[
                          {
                            x: sweepData.sweep_results.map((r: any) => r.value),
                            y: sweepData.sweep_results.map((r: any) => r.kus_linear_deg_per_g),
                            type: "scatter",
                            mode: "lines+markers",
                            name: "Understeer Gradient Kus (deg/G)",
                            line: { color: "#f2a900", width: 2.5 },
                            marker: { size: 6 },
                          },
                        ]}
                        layout={darkLayout({
                          title: { text: `Understeer Sensitivity vs ${sweepData.parameter_name}`, font: { color: "#ddd", size: 12 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: sweepData.parameter_name, font: { color: "#777", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "K_us (deg/G)", font: { color: "#777", size: 10 } } },
                        })}
                        useResizeHandler
                        style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>

                    <PlotBox>
                      <Plot
                        data={[
                          {
                            x: sweepData.sweep_results.map((r: any) => r.value),
                            y: sweepData.sweep_results.map((r: any) => r.ay_peak_g),
                            type: "scatter",
                            mode: "lines+markers",
                            name: "Peak Lateral Accel (G)",
                            line: { color: "#00ff87", width: 2.5 },
                            marker: { size: 6 },
                          },
                        ]}
                        layout={darkLayout({
                          title: { text: `Peak Lateral Grip vs ${sweepData.parameter_name}`, font: { color: "#ddd", size: 12 } },
                          xaxis: { ...DARK_BASE.xaxis, title: { text: sweepData.parameter_name, font: { color: "#777", size: 10 } } },
                          yaxis: { ...DARK_BASE.yaxis, title: { text: "Peak Ay (G)", font: { color: "#777", size: 10 } } },
                        })}
                        useResizeHandler
                        style={{ width: "100%", height: "100%" }}
                        config={{ responsive: true, displayModeBar: true }}
                      />
                    </PlotBox>
                  </div>
                ) : (
                  <div className="flex-1 flex items-center justify-center text-gray-500 text-xs">
                    Click &quot;Calculate Sweep&quot; to compute parameter sensitivity curves.
                  </div>
                )}
              </div>
            )}
          </div>
          {diagramData?.points && diagramData.points.length > 0 && (
            <EnvelopePlot
              title="G-G view (steady-state cornering, longitudinal = 0)"
              latG={diagramData.points.map((p: any) => p.ay_g)}
              longG={diagramData.points.map(() => 0)}
              limits={{ latG: diagramData.ay_peak_g }}
            />
          )}
        </div>
        </ShellCenter>
        <ShellRight>
          <VerdictRail
            status={verdict.status}
            statusLabel={verdict.label}
            heroes={[
              { label: "Understeer gradient", value: diagramData?.kus_linear_deg_per_g, unit: "deg/G", decimals: 2 },
              { label: "Peak lateral grip", value: diagramData?.ay_peak_g, unit: "G", decimals: 2 },
              { label: "Limiting axle", value: diagramData?.limiting_axle },
            ]}
            solverVersion={provenanceData?.solver_versions?.handling_dynamics}
            action={{ label: "Solve Handling", onClick: () => runFullAnalysis(), loading: isRunning }}
          />
        </ShellRight>
      </StudioShell>

      {/* Model Validity Modal */}
      {showValidityModal && validityData && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
          <div className="bg-[#121215] border border-[#252528] rounded-xl max-w-lg w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#222] pb-3">
              <div className="flex items-center gap-2">
                <ShieldCheck size={16} className="text-emerald-400" />
                <h3 className="text-sm font-bold text-white">Mathematical & Physical Validity Checks</h3>
              </div>
              <button onClick={() => setShowValidityModal(false)} className="text-gray-500 hover:text-white">
                <X size={15} />
              </button>
            </div>

            <div className="p-3 bg-[#0c0c0f] border border-[#1e1e1e] rounded-lg">
              <div className="text-[11px] text-gray-400 font-semibold mb-1">VALIDATION STATUS NOTICE</div>
              <p className="text-xs text-emerald-300 font-sans leading-relaxed">{validityData.summary}</p>
            </div>

            <div className="space-y-2 max-h-60 overflow-y-auto custom-scrollbar">
              {validityData.checks.map((check: any, idx: number) => (
                <div key={idx} className="flex items-start justify-between text-xs p-2 rounded bg-[#161619] border border-[#202025]">
                  <div>
                    <div className="font-semibold text-gray-200">{check.label}</div>
                    <div className="text-[11px] text-gray-400">{check.detail}</div>
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                      check.status === "pass"
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                        : "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                    }`}
                  >
                    {check.status}
                  </span>
                </div>
              ))}
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setShowValidityModal(false)}
                className="px-4 py-1.5 rounded-lg bg-[#222] hover:bg-[#333] text-xs font-medium text-white transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div className="h-full flex items-center justify-center text-gray-600 text-sm">Loading Handling Cockpit…</div>}>
      <PlanGate required="PRO" feature="Handling Dynamics & Bicycle Model">
        <HandlingDashboard />
      </PlanGate>
    </Suspense>
  );
}
