"use client";

import React, { useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  CheckCircle2,
  Cpu,
  FileQuestion,
  FlaskConical,
  GitCommit,
  Layers,
  Lock,
  Network,
  Play,
  RotateCcw,
  Sliders,
  Sparkles,
  Zap,
} from "lucide-react";
import StructuredErrorCard from "./StructuredErrorCard";
import EvidenceGraph from "./EvidenceGraph";

export interface DecisionLoopStep {
  step: number;
  stage: string;
  entity: string;
  id: string;
  number: number;
  summary: string;
  status: "COMPLETED" | "ACTIVE" | "PENDING" | "FAILED";
  hash?: string;
}

export interface DecisionLoopCockpitProps {
  className?: string;
}

export default function DecisionLoopCockpit({ className = "" }: DecisionLoopCockpitProps) {
  const [activeTab, setActiveTab] = useState<"workflow" | "evidence_graph" | "failure_ux">("workflow");
  const [selectedFailureMode, setSelectedFailureMode] = useState<string>("solver_failure");
  const [selectedGraphRoot, setSelectedGraphRoot] = useState<{ type: string; id: string }>({
    type: "EngineeringDecision",
    id: "DEC-12",
  });

  // Canonical Phase 3K Sequence: Session 381 -> Next Session 382
  const steps: DecisionLoopStep[] = [
    { step: 1, stage: "TRACK SESSION", entity: "TelemetrySessionRecord", id: "TS-381", number: 381, summary: "Silverstone GP FP1: 100 Hz MoTeC DAQ trace (Turn 8 apex).", status: "COMPLETED", hash: "a1b2c3d4e5f6...7890" },
    { step: 2, stage: "DETECTION", entity: "InvestigationRecord", id: "INV-91", number: 91, summary: "Front axle lateral grip deficit: 1.85 G vs 2.05 G expected (0.20 G residual).", status: "COMPLETED", hash: "b2c3d4e5f6a7...8901" },
    { step: 3, stage: "ENGINEERING QUESTION", entity: "EngineeringQuestion", id: "Q-17", number: 17, summary: "Why did front axle lateral performance decrease in Session 381?", status: "COMPLETED", hash: "c3d4e5f6a7b8...9012" },
    { step: 4, stage: "EXPERIMENT", entity: "ExperimentRecord", id: "EXP-52", number: 52, summary: "Hypothesis: Increase front roll stiffness (+32.1%) and damping (+12%).", status: "COMPLETED", hash: "d4e5f6a7b8c9...0123" },
    { step: 5, stage: "SIMULATION", entity: "SimulationRun", id: "RUN-001844", number: 1844, summary: "scipy.integrate.solve_ivp (RK45) forward ODE executed with rtol=1e-6.", status: "COMPLETED", hash: "e5f6a7b8c9d0...1234" },
    { step: 6, stage: "SETUP", entity: "VehicleSetup", id: "SETUP-92", number: 92, summary: "k_arb_f = 18,500 N/m, c = 2,464 Ns/m (baseline: 14,000 N/m, 2,200 Ns/m).", status: "COMPLETED", hash: "f6a7b8c9d0e1...2345" },
    { step: 7, stage: "COMPARISON", entity: "SetupComparisonRecord", id: "COMP-31", number: 31, summary: "Compare Setup #91 vs #92: +0.16 G lateral grip, front slip 8.2° -> 5.85°.", status: "COMPLETED", hash: "a7b8c9d0e1f2...3456" },
    { step: 8, stage: "OPTIMIZATION", entity: "OptimizationRecord", id: "OPT-18", number: 18, summary: "Evaluated 25 Pareto candidates calling genuine physics simulation engine.", status: "COMPLETED", hash: "b8c9d0e1f2a3...4567" },
    { step: 9, stage: "BLIND VALIDATION", entity: "BlindValidationRecord", id: "VAL-31", number: 31, summary: "Zero-leakage holdout cross-validation: R² = 0.938 >= 0.85 (Gate PASSED).", status: "COMPLETED", hash: "c9d0e1f2a3b4...5678" },
    { step: 10, stage: "ENGINEERING DECISION", entity: "EngineeringDecision", id: "DEC-12", number: 12, summary: "Adopt Setup #92 for Turn 8 apex lateral performance recovery.", status: "COMPLETED", hash: "d0e1f2a3b4c5...6789" },
    { step: 11, stage: "APPROVAL", entity: "ApprovalRecord", id: "APPR-8", number: 8, summary: "HMAC-SHA256 signature verified by James Wilson (Chief Race Engineer).", status: "COMPLETED", hash: "e1f2a3b4c5d6...789a" },
    { step: 12, stage: "NEXT TRACK SESSION", entity: "TelemetrySessionRecord", id: "TS-382", number: 382, summary: "FP2 telemetry confirms 2.03 G apex lateral grip (+0.18 G). Loop closed.", status: "COMPLETED", hash: "f2a3b4c5d6e7...89ab" },
  ];

  const failureModes: Record<string, {
    title: string;
    whatFailed: string;
    why: string;
    whatRemainsValid: string;
    whatCannotBeClaimed: string;
    nextAction: string;
  }> = {
    solver_failure: {
      title: "NUMERICAL INTEGRATION FAILURE (ODE RK45)",
      whatFailed: "Numerical Integration Failure in Quarter-Car / Handling ODE Solver",
      why: "Adaptive step size underflowed (dt < 1e-12 s) or state derivative evaluated to non-finite NaN/Inf due to extreme parameter inputs.",
      whatRemainsValid: "Baseline vehicle configuration handbook, static wheel rate geometry, and pre-existing telemetry recordings remain valid.",
      whatCannotBeClaimed: "Cannot claim dynamic stability, settling time, transient body heave response, or load transfer characteristics for the candidate setup.",
      nextAction: "Check for negative stiffness or non-physical damper rates; clamp input bounds and re-execute using implicit Radau/BDF stiff ODE integrator.",
    },
    invalid_telemetry: {
      title: "INVALID TELEMETRY INGESTION GATE",
      whatFailed: "Telemetry Ingestion & Quality Audit Gate Failed",
      why: "Telemetry trace contains non-monotonic timestamps, sensor dropout rate exceeding 15%, or missing mandatory lateral acceleration channel.",
      whatRemainsValid: "Forward physics simulation models, analytical steady-state handling diagrams, and previously certified telemetry sessions remain valid.",
      whatCannotBeClaimed: "Cannot claim empirical on-track correlation or observed model divergence for this corrupted session.",
      nextAction: "Re-export raw MoTeC/CSV logging file with monotonic timestamps, verify DAQ channel mappings, and re-run ingestion.",
    },
    extrapolated_physics: {
      title: "PHYSICS VALIDITY CONTRACT VIOLATION",
      whatFailed: "Physics Validity Contract Violation (Domain Extrapolation)",
      why: "Operating conditions fell outside validated tire model envelope (front slip angle |alpha| = 28.4° > 25.0° maximum limit or tire normal load Fz < 0 N).",
      whatRemainsValid: "Linear and small-slip regime dynamics (|alpha| ≤ 8.0°) and steady-state roll gradient predictions remain valid.",
      whatCannotBeClaimed: "Cannot claim accurate peak tire lateral force, limit balance, or spin recovery dynamics in full slide regimes.",
      nextAction: "Clip steering maneuver severity within physical envelope or calibrate large-angle thermal tire wear sub-model.",
    },
    optimizer_failure: {
      title: "OPTIMIZATION SEARCH DIVERGENCE",
      whatFailed: "Setup Optimization Search Divergence / Infeasible Constraints",
      why: "Optimization engine evaluated 50 iterations with 0 feasible candidates: suspension travel limit (≤ 30 mm) and roll stiffness constraints are mutually exclusive for current road excitation.",
      whatRemainsValid: "Individual forward simulation runs, baseline metrics, and sensitivity gradients remain valid.",
      whatCannotBeClaimed: "Cannot claim an optimal candidate setup was discovered.",
      nextAction: "Relax secondary constraints (allow +3 mm travel), adjust multi-objective penalty weights, or expand parameter search bounds.",
    },
    validation_failure: {
      title: "BLIND HOLDOUT VALIDATION GATE FAILED",
      whatFailed: "Out-of-Sample Blind Holdout Validation Gate Failed",
      why: "Model correlation against unseen holdout telemetry segment yielded R² = 0.64 (< 0.85 authoritative gate threshold), or data leakage was detected.",
      whatRemainsValid: "In-sample training fit metrics and qualitative direction of parameter influence remain valid.",
      whatCannotBeClaimed: "Cannot claim candidate setup is validated for track deployment or that simulated performance gains will transfer to track.",
      nextAction: "Investigate unmodeled degrees of freedom (chassis torsional compliance, tire temperature drift) and re-calibrate with split cross-validation.",
    },
    missing_provenance: {
      title: "PROVENANCE & HASH MISMATCH",
      whatFailed: "Cryptographic Provenance & Lineage Verification Failure",
      why: "Upstream artifact reference is broken: Experiment #52 references simulation run whose input parameter hash does not match stored setup definition.",
      whatRemainsValid: "Raw simulation output data files and telemetry CSV files remain physically intact on disk.",
      whatCannotBeClaimed: "Cannot claim audit-defensible traceability or regulatory/championship compliance for this decision.",
      nextAction: "Re-execute simulation run from within registered experiment container to regenerate tamper-evident cryptographic hash chain.",
    },
    stale_model: {
      title: "MODEL CONFIGURATION STALENESS",
      whatFailed: "Model Freshness & Configuration Staleness Detected",
      why: "Chassis suspension hardpoints and aero polar map version (Aero-Rev-26) were superseded by Aero-Rev-28 prior to this session; simulation reflects obsolete kinematics.",
      whatRemainsValid: "Qualitative comparative trends between damper rates remain mechanically informative.",
      whatCannotBeClaimed: "Cannot claim absolute quantitative aerodynamic downforce, drag figures, or exact ride height millimeter clearances.",
      nextAction: "Synchronize vehicle digital twin to active Aero-Rev-28 specification and re-execute simulation workflow.",
    },
    external_solver_unavailable: {
      title: "EXTERNAL CAE SERVICE TIMEOUT",
      whatFailed: "External High-Performance CAE Solver Unavailable",
      why: "External solver service (MSC Adams / MATLAB Simulink / HPC cluster) RPC connection timed out after 30 seconds or binary is not present in runtime environment.",
      whatRemainsValid: "Native high-performance quarter-car and 3-DOF non-linear handling ODE solvers remain fully operational.",
      whatCannotBeClaimed: "Cannot claim multi-body flexible chassis co-simulation agreement from external Adams cluster.",
      nextAction: "Fall back to native high-fidelity forward ODE solver or verify network RPC connection and license server status for CAE cluster.",
    },
  };

  const currentFailure = failureModes[selectedFailureMode];

  return (
    <div className={`p-6 rounded-2xl bg-neutral-900 border border-neutral-800 text-white ${className}`}>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-neutral-800 mb-6">
        <div>
          <div className="flex items-center gap-2 text-rose-500 font-mono text-xs uppercase tracking-widest font-semibold mb-1">
            <Cpu size={15} />
            <span>SUSPENSIONLAB PRO — PHASE 3K</span>
          </div>
          <h2 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            Engineering Decision Loop Cockpit
          </h2>
          <p className="text-xs text-neutral-400 mt-1">
            Executable end-to-end engineering workflow linking real telemetry, simulation, optimization, and non-repudiable approvals.
          </p>
        </div>

        {/* Tab switch */}
        <div className="flex bg-neutral-950 p-1 rounded-xl border border-neutral-800 text-xs font-mono">
          <button
            onClick={() => setActiveTab("workflow")}
            className={`px-3 py-1.5 rounded-lg transition-all ${
              activeTab === "workflow" ? "bg-rose-500 text-white font-bold" : "text-neutral-400 hover:text-white"
            }`}
          >
            12-Stage Provenance Loop
          </button>
          <button
            onClick={() => setActiveTab("evidence_graph")}
            className={`px-3 py-1.5 rounded-lg transition-all ${
              activeTab === "evidence_graph" ? "bg-rose-500 text-white font-bold" : "text-neutral-400 hover:text-white"
            }`}
          >
            Evidence Graph
          </button>
          <button
            onClick={() => setActiveTab("failure_ux")}
            className={`px-3 py-1.5 rounded-lg transition-all ${
              activeTab === "failure_ux" ? "bg-rose-500 text-white font-bold" : "text-neutral-400 hover:text-white"
            }`}
          >
            Failure UX (8 Modes)
          </button>
        </div>
      </div>

      {activeTab === "workflow" ? (
        <div className="space-y-4">
          <div className="p-3 rounded-xl bg-neutral-950/80 border border-neutral-800 text-xs text-neutral-300 font-mono flex items-center justify-between">
            <span>Target Lineage: TelemetrySession #381 → Decision #12 → Next Track Session #382</span>
            <span className="text-emerald-400 font-bold flex items-center gap-1">
              <CheckCircle2 size={13} /> 100% PROVENANCE VERIFIED
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {steps.map((st) => (
              <div
                key={st.step}
                className="p-4 rounded-xl bg-neutral-950/50 border border-neutral-800/80 hover:border-neutral-700 transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between text-[11px] font-mono text-neutral-400 mb-1.5">
                    <span className="text-rose-400 font-bold">STAGE {st.step}</span>
                    <span className="px-1.5 py-0.5 rounded bg-neutral-800 text-[10px] text-neutral-300">
                      {st.id}
                    </span>
                  </div>
                  <h3 className="text-sm font-semibold text-white tracking-wide mb-1 font-sans">
                    {st.stage}
                  </h3>
                  <p className="text-xs text-neutral-300 leading-relaxed font-sans">
                    {st.summary}
                  </p>
                </div>
                <div className="pt-3 mt-3 border-t border-neutral-800/60 flex items-center justify-between text-[10px] font-mono text-neutral-400">
                  <span>Entity: {st.entity}</span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => {
                        setSelectedGraphRoot({ type: st.entity, id: st.id });
                        setActiveTab("evidence_graph");
                      }}
                      className="text-rose-400 hover:text-rose-300 flex items-center gap-1 font-semibold"
                      title="Inspect entity in Evidence Graph"
                    >
                      <Network size={11} />
                      <span>Graph</span>
                    </button>
                    <span className="text-emerald-400 flex items-center gap-1 font-bold">
                      <CheckCircle2 size={11} /> {st.status}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : activeTab === "evidence_graph" ? (
        <div className="space-y-4">
          <div className="p-3 rounded-xl bg-neutral-950/80 border border-neutral-800 text-xs text-neutral-300 font-mono flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-neutral-400">Active Root:</span>
              <span className="font-bold text-white px-2 py-0.5 rounded bg-neutral-800">
                {selectedGraphRoot.type} : {selectedGraphRoot.id}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-neutral-400">Jump to:</span>
              <button
                onClick={() => setSelectedGraphRoot({ type: "EngineeringDecision", id: "DEC-12" })}
                className={`px-2 py-1 rounded text-[11px] transition-colors ${
                  selectedGraphRoot.id === "DEC-12"
                    ? "bg-rose-500 text-white font-bold"
                    : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
                }`}
              >
                Decision DEC-12
              </button>
              <button
                onClick={() => setSelectedGraphRoot({ type: "ExperimentRecord", id: "EXP-52" })}
                className={`px-2 py-1 rounded text-[11px] transition-colors ${
                  selectedGraphRoot.id === "EXP-52"
                    ? "bg-rose-500 text-white font-bold"
                    : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
                }`}
              >
                EXP-52
              </button>
              <button
                onClick={() => setSelectedGraphRoot({ type: "BlindValidationRecord", id: "VAL-31" })}
                className={`px-2 py-1 rounded text-[11px] transition-colors ${
                  selectedGraphRoot.id === "VAL-31"
                    ? "bg-rose-500 text-white font-bold"
                    : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
                }`}
              >
                VAL-31
              </button>
              <button
                onClick={() => setSelectedGraphRoot({ type: "TelemetrySessionRecord", id: "TS-381" })}
                className={`px-2 py-1 rounded text-[11px] transition-colors ${
                  selectedGraphRoot.id === "TS-381"
                    ? "bg-rose-500 text-white font-bold"
                    : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
                }`}
              >
                TS-381
              </button>
            </div>
          </div>

          <EvidenceGraph
            rootType={selectedGraphRoot.type}
            rootId={selectedGraphRoot.id}
            initialDirection="BACKWARD"
            initialDepth={6}
          />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Failure mode selector */}
          <div className="space-y-2">
            <label className="text-xs font-mono text-neutral-400 font-semibold uppercase tracking-wider">
              Select Failure Mode to Inspect Mandatory 5-Section Diagnostics:
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {Object.keys(failureModes).map((key) => (
                <button
                  key={key}
                  onClick={() => setSelectedFailureMode(key)}
                  className={`p-2 rounded-lg border text-left font-mono text-xs transition-all ${
                    selectedFailureMode === key
                      ? "bg-rose-950/60 border-rose-500 text-rose-200 font-bold"
                      : "bg-neutral-950 border-neutral-800 text-neutral-400 hover:border-neutral-700 hover:text-white"
                  }`}
                >
                  {key.replace("_", " ").toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Render Structured Error Card */}
          {currentFailure && (
            <StructuredErrorCard
              title={currentFailure.title}
              whatFailed={currentFailure.whatFailed}
              why={currentFailure.why}
              whatRemainsValid={currentFailure.whatRemainsValid}
              whatCannotBeClaimed={currentFailure.whatCannotBeClaimed}
              nextAction={currentFailure.nextAction}
            />
          )}
        </div>
      )}
    </div>
  );
}
