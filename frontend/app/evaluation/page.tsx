"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "../../contexts/AuthContext";
import { useWorkspace } from "../../contexts/WorkspaceContext";
import { useRouter } from "next/navigation";
import {
  Clock,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  Gauge,
  Activity,
  Sliders,
  Play,
  RotateCcw,
  Sparkles,
  ArrowRight,
  TrendingDown,
  TrendingUp,
  FileText,
  Mail,
  HelpCircle,
  Database,
  ExternalLink,
  LogOut,
  Car,
  ChevronRight,
  Check,
  Target,
  Award,
  Info,
  PlusCircle,
  X,
  Layers,
  Compass,
  MessageSquare,
} from "lucide-react";

interface SetupItem {
  id: string;
  name: string;
  params: Record<string, number>;
  kpis: Record<string, number>;
  description?: string;
  specs?: Record<string, any>;
  deltas_vs_baseline?: Record<string, number>;
}

interface TelemetryPoint {
  time: number;
  vehicle_speed_kmh: number;
  lateral_accel_g: number;
  longitudinal_accel_g: number;
  steering_angle_deg: number;
  susp_travel_fl_mm: number;
  susp_travel_fr_mm: number;
  damper_velocity_fl_mms: number;
  damper_velocity_fr_mms: number;
  wheel_speed_fl_rpm: number;
  wheel_speed_fr_rpm: number;
  tire_load_fl_n: number;
  tire_load_fr_n: number;
  yaw_rate_degs: number;
}

interface TelemetryDataset {
  dataset_name: string;
  dataset_type: string;
  is_synthetic: boolean;
  evaluation_label: string;
  vehicle_ref: string;
  corner: string;
  duration_s: number;
  sample_rate_hz: number;
  total_samples: number;
  peak_metrics: Record<string, number>;
  channels: TelemetryPoint[];
}

interface InvestigationData {
  what_is_happening: {
    summary: string;
    description: string;
    severity: string;
  };
  evidence: {
    telemetry_source: string;
    peak_tire_load_variation_n: number;
    max_damper_velocity_mms: number;
    lateral_accel_rate_gs: number;
    transient_settle_delay_s: number;
    target_settle_s: number;
    channels_inspected: string[];
  };
  why: {
    root_cause: string;
    explanation: string;
  };
  what_should_we_test: string[];
}

interface WorkspaceData {
  trial: {
    trial_id: string;
    organization_id: string;
    status: string;
    is_expired: boolean;
    expires_at: string;
    days_remaining: number;
    simulation_run_limit: number;
    simulation_run_count: number;
    simulations_remaining: number;
    telemetry_storage_limit_bytes: number;
    telemetry_storage_used_bytes: number;
    vehicle_project_limit: number;
    vehicle_project_count: number;
    evaluation_title: string;
    contact_email?: string;
    day_number?: number;
    day_label?: string;
  };
  evaluation_labels?: {
    dataset: string;
    telemetry: string;
    demonstration: string;
  };
  vehicle: {
    id: string;
    car_ref: string;
    setup_ref: string;
    track_ref: string;
    base_params: Record<string, number>;
    specs?: Record<string, any>;
  };
  setups?: SetupItem[];
  telemetry_session: {
    id: string;
    name: string;
    summary: Record<string, any>;
  };
  telemetry_dataset?: TelemetryDataset;
  engineering_question: {
    id: string;
    title: string;
    question_text: string;
    severity: string;
    status: string;
    context: Record<string, any>;
  };
  investigation?: InvestigationData;
  baseline_simulation: {
    id: string;
    label: string;
    title: string;
    kpis: Record<string, number>;
  };
  experiment_history: Array<{
    id: string;
    simulation_run_id: string;
    created_at: string;
    hypothesis: string;
    improvements: Array<{ label: string; delta_pct: number; unit: string; reason: string }>;
    regressions: Array<{ label: string; delta_pct: number; unit: string; reason: string }>;
    reproducibility_hash: string;
    candidate_metrics: Record<string, number>;
  }>;
  checklist?: {
    items: {
      investigate_question: boolean;
      run_experiment: boolean;
      compare_setups: boolean;
      run_optimization: boolean;
      create_decision: boolean;
      try_own_question: boolean;
    };
    completed_count: number;
    total_count: number;
    is_all_completed: boolean;
    feedback_submitted: boolean;
  };
  feedback_submitted?: boolean;
}

export default function EvaluationPage() {
  const { user, loading: authLoading, logout, fetchWithAuth } = useAuth();
  const { vehicle: sharedVehicle } = useWorkspace();
  const router = useRouter();

  const [workspace, setWorkspace] = useState<WorkspaceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<
    "question" | "vehicle" | "experiment" | "optimize" | "decision" | "telemetry" | "simulate"
  >("question");

  // Setup Comparator state
  const [selectedSetupA, setSelectedSetupA] = useState<string>("Setup A — Baseline");
  const [selectedSetupB, setSelectedSetupB] = useState<string>("Setup B — High Roll Stiffness");

  // Editable setup parameters for solver
  const [params, setParams] = useState<Record<string, number>>({});
  const [simulating, setSimulating] = useState(false);
  const [simResult, setSimResult] = useState<Record<string, number> | null>(null);

  // Hero experiment state
  const [hypothesisText, setHypothesisText] = useState(
    "Increase front roll stiffness by 10% to evaluate roll angle control vs tire load variation tradeoff."
  );
  const [experimenting, setExperimenting] = useState(false);
  const [expError, setExpError] = useState<any>(null);

  // Pareto Optimizer state
  const [optimizing, setOptimizing] = useState(false);
  const [paretoData, setParetoData] = useState<any>(null);

  // Decision Workflow Demo state
  const [creatingDecision, setCreatingDecision] = useState(false);
  const [decisionRecord, setDecisionRecord] = useState<any>(null);

  // Custom Question Modal
  const [showCustomModal, setShowCustomModal] = useState(false);
  const [customQuestionTitle, setCustomQuestionTitle] = useState("");
  const [customQuestionText, setCustomQuestionText] = useState("");
  const [submittingCustomQ, setSubmittingCustomQ] = useState(false);

  // Telemetry time scrubber index
  const [telemetryIndex, setTelemetryIndex] = useState(37); // Peak transition point (~1.85s)

  // Limit Exceeded / Error state
  const [limitError, setLimitError] = useState<{
    what_limit_was_reached: string;
    current_usage: Record<string, any>;
    what_remains_available: string[];
    how_to_request_continuation: string;
  } | null>(null);

  // Customer discovery feedback state
  const [feedbackValuable, setFeedbackValuable] = useState("");
  const [feedbackPrevented, setFeedbackPrevented] = useState("");
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [feedbackSuccess, setFeedbackSuccess] = useState(false);

  // Non-sensitive product analytics event tracker
  const trackEvent = useCallback(
    async (eventName: string, properties?: Record<string, any>) => {
      try {
        await fetchWithAuth("/api/v1/trials/events", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ event_name: eventName, properties }),
        });
      } catch (err) {
        // Non-blocking analytics
      }
    },
    [fetchWithAuth]
  );

  const getStageLabel = (tab: string) => {
    switch (tab) {
      case "question":
        return "1 / 6 — Engineering Question";
      case "telemetry":
        return "2 / 6 — Telemetry Evidence";
      case "experiment":
        return "3 / 6 — Hypothesis Experiment";
      case "vehicle":
        return "4 / 6 — Multi-Setup Comparison";
      case "optimize":
        return "5 / 6 — Pareto Optimization";
      case "decision":
        return "6 / 6 — Decision Workflow";
      case "simulate":
        return "Deep Dive — Quarter-Car ODE Solver";
      default:
        return "1 / 6 — Engineering Question";
    }
  };

  const fetchWorkspace = useCallback(async () => {
    try {
      const res = await fetchWithAuth("/api/v1/trials/workspace");
      if (res.ok) {
        const data: WorkspaceData = await res.json();
        setWorkspace(data);
        if (data.vehicle?.base_params) {
          setParams(data.vehicle.base_params);
        }
        if (data.baseline_simulation?.kpis) {
          setSimResult((prev) => prev ?? data.baseline_simulation.kpis);
        }
        if (data.feedback_submitted || data.checklist?.feedback_submitted) {
          setFeedbackSuccess(true);
        }
        if (data.trial?.is_expired) {
          setLimitError({
            what_limit_was_reached: "7-Day Evaluation Period Expired",
            current_usage: {
              simulations_used: data.trial.simulation_run_count,
              simulations_limit: data.trial.simulation_run_limit,
              days_remaining: 0,
              expires_at: data.trial.expires_at,
            },
            what_remains_available: [
              "Read-only workspace access",
              "Review previous simulation results and KPIs",
              "Inspect telemetry sessions and correlation reports",
              "Export existing engineering summaries and datasets",
            ],
            how_to_request_continuation:
              "Contact enterprise@suspensionlab.pro or visit https://suspensionlab.pro/pricing to extend your evaluation or activate PRO Enterprise.",
          });
        }
      } else if (res.status === 403) {
        const errJson = await res.json().catch(() => ({}));
        if (errJson.detail && errJson.detail.error === "TRIAL_LIMIT_EXCEEDED") {
          setLimitError(errJson.detail);
        }
      }
    } catch (err) {
      console.error("Failed loading evaluation workspace:", err);
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth]);

  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/auth/login");
      return;
    }
    fetchWorkspace();
    trackEvent("evaluation_started");
  }, [user, authLoading, router, fetchWorkspace, trackEvent]);

  // Submit Customer Discovery Feedback
  const handleSubmitFeedback = async () => {
    if (!feedbackValuable.trim() && !feedbackPrevented.trim()) return;
    setSubmittingFeedback(true);
    try {
      const res = await fetchWithAuth("/api/v1/trials/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          most_valuable_part: feedbackValuable,
          prevented_more_use: feedbackPrevented,
        }),
      });
      if (res.ok) {
        setFeedbackSuccess(true);
        await fetchWorkspace();
        trackEvent("feedback_submitted");
      }
    } catch (err) {
      console.error("Feedback submit error:", err);
    } finally {
      setSubmittingFeedback(false);
    }
  };

  // Run Real Quarter-Car Simulation
  const handleRunSimulation = async () => {
    setSimulating(true);
    setLimitError(null);
    try {
      const res = await fetchWithAuth("/api/v1/trials/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ params }),
      });
      if (res.ok) {
        const data = await res.json();
        await fetchWorkspace();
        setSimResult(data.kpis);
      } else if (res.status === 403) {
        const err = await res.json();
        if (err.detail && err.detail.error === "TRIAL_LIMIT_EXCEEDED") {
          setLimitError(err.detail);
        }
      }
    } catch (err) {
      console.error("Simulation failed:", err);
    } finally {
      setSimulating(false);
    }
  };

  // Run Real Hero Experiment
  const handleRunExperiment = async () => {
    setExperimenting(true);
    setExpError(null);
    setLimitError(null);
    try {
      const res = await fetchWithAuth("/api/v1/trials/experiment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: workspace?.engineering_question?.title || "Front roll stiffness corner entry evaluation",
          hypothesis: hypothesisText,
          parent_setup: workspace?.vehicle?.base_params,
          parameter_changes: { k_arb_f: (workspace?.vehicle?.base_params?.k_arb_f || 4500) * 1.1 },
        }),
      });
      if (res.ok) {
        await fetchWorkspace();
      } else if (res.status === 403) {
        const err = await res.json();
        if (err.detail && err.detail.error === "TRIAL_LIMIT_EXCEEDED") {
          setLimitError(err.detail);
        } else {
          setExpError(err.detail || "Experiment failed");
        }
      } else {
        const err = await res.json();
        setExpError(err.detail || "Experiment execution failed");
      }
    } catch (err: any) {
      setExpError(err.message);
    } finally {
      setExperimenting(false);
    }
  };

  // Run Real Multi-Objective Pareto Optimization
  const handleRunParetoOptimization = async () => {
    setOptimizing(true);
    setLimitError(null);
    try {
      const res = await fetchWithAuth("/api/v1/trials/optimize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          param_ranges: {
            k_s: [25000.0, 45000.0],
            c: [1200.0, 2600.0],
          },
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setParetoData(data);
        await fetchWorkspace();
      } else if (res.status === 403) {
        const err = await res.json();
        if (err.detail && err.detail.error === "TRIAL_LIMIT_EXCEEDED") {
          setLimitError(err.detail);
        }
      }
    } catch (err) {
      console.error("Pareto optimization failed:", err);
    } finally {
      setOptimizing(false);
    }
  };

  // Create Formal Engineering Decision (Decision Workflow Demo)
  const handleCreateDecision = async () => {
    setCreatingDecision(true);
    setLimitError(null);
    try {
      const res = await fetchWithAuth("/api/v1/trials/decision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: workspace?.engineering_question?.title,
          selected_option: {
            setup_name: "Setup A+ (Tuned Damping)",
            params: { k_s: 35000.0, c: 1650.0, k_arb_f: 4500.0, k_arb_r: 3800.0 },
          },
          reason:
            "Rebound damping reduction from 1,800 to 1,650 Ns/m attenuates initial contact patch normal force spike by 14.2% while retaining 94% of steady-state roll resistance.",
          tradeoffs: [
            { parameter: "tire_load_variation", delta_pct: -14.2, status: "IMPROVEMENT" },
            { parameter: "body_roll_compliance", delta_pct: +1.8, status: "ACCEPTABLE_REGRESSION" },
          ],
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setDecisionRecord(data);
      } else if (res.status === 403) {
        const err = await res.json();
        if (err.detail && err.detail.error === "TRIAL_LIMIT_EXCEEDED") {
          setLimitError(err.detail);
        }
      }
    } catch (err) {
      console.error("Decision creation failed:", err);
    } finally {
      setCreatingDecision(false);
    }
  };

  // Submit Custom Question
  const handleCreateCustomQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customQuestionTitle.trim()) return;
    setSubmittingCustomQ(true);
    try {
      const res = await fetchWithAuth("/api/v1/trials/questions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: customQuestionTitle,
          question_text: customQuestionText || "Investigating custom dynamics sensitivity.",
          severity: "HIGH",
        }),
      });
      if (res.ok) {
        setShowCustomModal(false);
        setCustomQuestionTitle("");
        setCustomQuestionText("");
        await fetchWorkspace();
        setActiveTab("question");
      }
    } catch (err) {
      console.error("Custom question failed:", err);
    } finally {
      setSubmittingCustomQ(false);
    }
  };

  if (loading || authLoading) {
    return (
      <div className="min-h-screen bg-[#0a0a0c] text-white flex items-center justify-center pt-16">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-ansys-yellow border-t-transparent rounded-full animate-spin"></div>
          <p className="text-xs text-gray-400 font-mono">Loading Formula Student Evaluation Garage…</p>
        </div>
      </div>
    );
  }

  const trial = workspace?.trial;
  const isExpired = trial?.is_expired || false;
  const simsUsed = trial?.simulation_run_count ?? 0;
  const simsLimit = trial?.simulation_run_limit ?? 50;
  const daysLeft = trial?.days_remaining ?? 0;

  const setups = workspace?.setups || [];
  const setupA = setups.find((s) => s.name === selectedSetupA) || setups[0];
  const setupB = setups.find((s) => s.name === selectedSetupB) || setups[1] || setups[0];
  const telemData = workspace?.telemetry_dataset?.channels || [];
  const currentTelemPoint = telemData[telemetryIndex] || telemData[0];
  const investigation = workspace?.investigation;

  if (isExpired) {
    return (
      <div className="min-h-screen bg-[#0a0a0c] text-white p-6 md:p-12 flex flex-col justify-center items-center">
        <div className="w-full max-w-2xl space-y-6">
          <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-2xl w-fit mx-auto text-red-400">
            <Clock size={44} />
          </div>

          <div className="text-center space-y-2">
            <h1 className="text-3xl font-extrabold text-white">Evaluation Expired</h1>
            <p className="text-sm text-gray-300">
              Your evaluation data is preserved according to the trial policy.
            </p>
            <div className="pt-3">
              <a
                href="mailto:enterprise@suspensionlab.pro?subject=Trial%20Extension%20Request"
                className="inline-flex items-center gap-2 px-6 py-3 bg-ansys-yellow text-black font-extrabold text-xs sm:text-sm rounded-xl hover:brightness-110 shadow-lg shadow-ansys-yellow/20 cursor-pointer"
              >
                REQUEST EXTENDED EVALUATION
              </a>
            </div>
          </div>

          {/* 4 Required Sections Breakdown */}
          <div
            role="alert"
            className="p-6 bg-[#111114] border-2 border-red-500/40 rounded-2xl space-y-4 text-xs"
          >
            <div>
              <div className="text-[11px] font-mono uppercase tracking-wider text-red-400 font-bold">
                Evaluation Policy Limit Reached
              </div>
              <h2 className="text-lg font-bold text-white mt-0.5">
                {limitError?.what_limit_was_reached || "7-Day Evaluation Period Expired"}
              </h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-3 border-t border-red-500/20 font-sans">
              <div className="bg-[#17171b] p-3 rounded-xl border border-[#222]">
                <div className="text-gray-400 font-bold uppercase tracking-wider text-[10px] mb-2 flex items-center gap-1.5">
                  <Gauge size={12} className="text-ansys-yellow" /> CURRENT USAGE
                </div>
                <div className="space-y-1 font-mono text-gray-300">
                  <div>Simulations: <span className="font-bold text-white">{simsUsed} / {simsLimit}</span></div>
                  <div>Days Left: <span className="font-bold text-white">{daysLeft}</span></div>
                  <div>Status: <span className="font-bold text-red-400 uppercase">EXPIRED</span></div>
                </div>
              </div>

              <div className="bg-[#17171b] p-3 rounded-xl border border-[#222]">
                <div className="text-gray-400 font-bold uppercase tracking-wider text-[10px] mb-2 flex items-center gap-1.5">
                  <CheckCircle2 size={12} className="text-emerald-400" /> WHAT REMAINS AVAILABLE
                </div>
                <ul className="space-y-1 text-gray-300 list-disc list-inside">
                  {(limitError?.what_remains_available || [
                    "Read-only workspace access",
                    "Review previous simulation results and KPIs",
                    "Inspect telemetry sessions and correlation reports",
                    "Export existing engineering summaries and datasets",
                  ]).map((item, idx) => (
                    <li key={idx} className="truncate">{item}</li>
                  ))}
                </ul>
              </div>

              <div className="bg-[#17171b] p-3 rounded-xl border border-[#222]">
                <div className="text-gray-400 font-bold uppercase tracking-wider text-[10px] mb-2 flex items-center gap-1.5">
                  <Mail size={12} className="text-blue-400" /> HOW TO REQUEST CONTINUATION
                </div>
                <p className="text-gray-300 leading-relaxed">
                  {limitError?.how_to_request_continuation ||
                    "Contact enterprise@suspensionlab.pro to extend your evaluation."}
                </p>
                <div className="mt-2 text-ansys-yellow font-mono text-[11px] font-bold">
                  enterprise@suspensionlab.pro
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#0a0a0c] text-white pt-16 pb-20 px-4 sm:px-8 max-w-[1540px] mx-auto">
      {/* ── Expiration Warning (< 2 days remaining) ── */}
      {daysLeft < 2.0 && !isExpired && (
        <div
          role="alert"
          className="mb-6 p-4 bg-amber-950/40 border border-amber-500/50 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-lg"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-500/20 border border-amber-500/40 rounded-xl text-amber-400 shrink-0">
              <AlertTriangle size={20} />
            </div>
            <div>
              <div className="text-xs font-bold text-amber-400 uppercase tracking-wider">
                Evaluation Ending Soon — Fewer than 2 days remaining
              </div>
              <p className="text-xs text-gray-300 mt-0.5">
                {daysLeft} days remaining. Your evaluation data and provenance ledger will be preserved according to the trial policy.
              </p>
            </div>
          </div>
          <a
            href="mailto:enterprise@suspensionlab.pro?subject=Trial%20Extension%20Request"
            className="px-4 py-2 bg-amber-500 text-black text-xs font-bold rounded-xl hover:brightness-110 shrink-0 self-start sm:self-auto cursor-pointer"
          >
            REQUEST EXTENDED EVALUATION
          </a>
        </div>
      )}

      {/* ── 1. EVALUATION LANDING SCREEN HEADER ── */}
      <div className="border-b border-[#222] pb-6 mb-6">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-ansys-yellow/15 text-ansys-yellow border border-ansys-yellow/30">
                Evaluation Workspace
              </span>
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-purple-950/40 text-purple-300 border border-purple-800/40">
                EVALUATION DATASET
              </span>
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-blue-950/40 text-blue-300 border border-blue-800/40">
                SYNTHETIC EVALUATION DATA
              </span>
              <span className="text-xs text-gray-500">|</span>
              <span className="text-xs text-gray-400 font-mono">
                Vehicle: {workspace?.vehicle?.car_ref || sharedVehicle?.name || "No active vehicle"}
              </span>
            </div>
            <h1 className="text-3xl font-extrabold tracking-tight text-white">
              SuspensionLab PRO
            </h1>
            <h2 className="text-lg font-bold text-ansys-yellow mt-0.5">
              7-Day Engineering Evaluation
            </h2>
            <p className="text-xs text-gray-300 font-mono mt-1 flex items-center gap-1.5">
              Investigate → Experiment → Compare → Optimize → Decide
            </p>
          </div>

          {/* Top Trial Status Counters */}
          <div className="flex flex-wrap items-center gap-3 bg-[#111114] border border-[#222] p-3 rounded-2xl shadow-xl">
            {/* Days Remaining / Day label */}
            <div className="px-3 py-2 bg-[#17171b] border border-[#26262a] rounded-xl flex items-center gap-2.5">
              <Clock size={16} className="text-ansys-yellow" />
              <div>
                <div className="text-[10px] uppercase font-bold tracking-wider text-gray-500">Trial Status</div>
                <div className="text-xs font-mono font-bold text-white">
                  {daysLeft <= 0
                    ? "Trial expired"
                    : workspace?.trial?.day_label || `Day ${Math.min(7, Math.max(1, 8 - Math.ceil(daysLeft)))} of 7`}{daysLeft > 0 ? ` (${daysLeft} days left)` : ""}
                </div>
              </div>
            </div>

            {/* Simulations Remaining */}
            <div className="px-3 py-2 bg-[#17171b] border border-[#26262a] rounded-xl flex items-center gap-2.5">
              <Gauge size={16} className={simsUsed >= simsLimit ? "text-red-400" : "text-emerald-400"} />
              <div>
                <div className="text-[10px] uppercase font-bold tracking-wider text-gray-500">Simulations</div>
                <div className="text-xs font-mono font-bold text-white">
                  {Math.max(0, simsLimit - simsUsed)} / {simsLimit} simulations remaining
                </div>
              </div>
            </div>

            {/* Active Vehicle */}
            <div className="px-3 py-2 bg-[#17171b] border border-[#26262a] rounded-xl flex items-center gap-2.5">
              <Car size={16} className="text-blue-400" />
              <div>
                <div className="text-[10px] uppercase font-bold tracking-wider text-gray-500">Active Vehicle</div>
                <div className="text-xs font-mono font-bold text-white">{workspace?.vehicle?.car_ref || sharedVehicle?.name || "No active vehicle"}</div>
              </div>
            </div>

            {/* Current Evaluation Stage */}
            <div className="px-3 py-2 bg-[#17171b] border border-[#26262a] rounded-xl flex items-center gap-2.5">
              <Activity size={16} className="text-purple-400" />
              <div>
                <div className="text-[10px] uppercase font-bold tracking-wider text-gray-500">Current Stage</div>
                <div className="text-xs font-mono font-bold text-ansys-yellow">{getStageLabel(activeTab)}</div>
              </div>
            </div>

            <button
              onClick={() => logout()}
              title="Sign Out"
              className="p-2 text-gray-500 hover:text-white rounded-lg hover:bg-white/5 transition-colors cursor-pointer"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>

        {/* Active Question Banner */}
        <div className="mt-4 bg-[#111114] border border-[#222] rounded-2xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-md">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-red-500/20 text-red-400 border border-red-500/30 rounded-xl shrink-0">
              <Target size={18} />
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-wider text-red-400 font-bold">
                Active Engineering Question
              </div>
              <div className="text-sm font-bold text-white">
                {workspace?.engineering_question?.title || "Why is front tire-load variation increasing during aggressive corner entry?"}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="px-2.5 py-1 bg-red-950/60 border border-red-500/40 text-red-300 font-mono text-[11px] font-bold rounded-lg">
              SEVERITY: {workspace?.engineering_question?.severity || "CRITICAL"}
            </span>
            <span className="px-2.5 py-1 bg-[#1a1a20] border border-[#333] text-gray-300 font-mono text-[11px] rounded-lg">
              {workspace?.vehicle?.track_ref || "FS-Michigan-Autocross"}
            </span>
          </div>
        </div>
      </div>

      {/* ── 2. PRIMARY ACTION BUTTONS (CTAs) ── */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <button
          onClick={() => {
            setActiveTab("question");
            trackEvent("question_opened", { question_id: workspace?.engineering_question?.id });
          }}
          className="px-6 py-3.5 bg-ansys-yellow text-black font-extrabold text-xs sm:text-sm rounded-xl hover:brightness-110 shadow-lg shadow-ansys-yellow/20 flex items-center gap-2.5 transition-all cursor-pointer"
        >
          <Play size={16} fill="black" /> START ENGINEERING INVESTIGATION
        </button>
        <button
          onClick={() => setShowCustomModal(true)}
          className="px-5 py-3.5 bg-[#17171b] border border-[#26262a] text-xs font-bold text-white rounded-xl hover:border-ansys-yellow/50 flex items-center gap-2 transition-all cursor-pointer"
        >
          <PlusCircle size={15} className="text-ansys-yellow" /> TRY YOUR OWN QUESTION
        </button>
        <button
          onClick={() => {
            setActiveTab("vehicle");
            trackEvent("explore_platform");
          }}
          className="px-5 py-3.5 bg-[#17171b] border border-[#26262a] text-xs font-bold text-gray-400 hover:text-white rounded-xl flex items-center gap-2 transition-all cursor-pointer"
        >
          <Compass size={15} className="text-blue-400" /> EXPLORE THE PLATFORM
        </button>
      </div>

      {/* ── FULL APPLICATION STUDIOS (Unrestricted Normal App Access) ── */}
      <div className="mb-6 p-4 bg-[#111114] border border-[#222] rounded-2xl shadow-lg">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-extrabold text-[10px] uppercase tracking-wider rounded">
              FULL APPLICATION ACCESS
            </span>
            <span className="text-xs font-bold text-white">Full Application Studios — Identical to Enterprise License</span>
          </div>
          <span className="text-[10px] text-gray-500 font-mono">Formula Student EV Pre-loaded • 50 Runs Quota</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
          <Link
            href="/kinematics"
            className="p-3.5 bg-[#17171b] border border-[#26262a] rounded-xl hover:border-ansys-yellow/50 hover:bg-[#1c1c22] transition-all group"
          >
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] uppercase font-bold text-gray-400 group-hover:text-ansys-yellow">Kinematics</span>
              <ExternalLink size={12} className="text-gray-500 group-hover:text-ansys-yellow" />
            </div>
            <div className="text-xs font-bold text-white">3D Hardpoints</div>
            <div className="text-[10px] text-gray-400 mt-0.5 font-mono">Double Wishbone CAE</div>
          </Link>
          <Link
            href="/handling"
            className="p-3.5 bg-[#17171b] border border-[#26262a] rounded-xl hover:border-ansys-yellow/50 hover:bg-[#1c1c22] transition-all group"
          >
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] uppercase font-bold text-gray-400 group-hover:text-ansys-yellow">Handling</span>
              <ExternalLink size={12} className="text-gray-500 group-hover:text-ansys-yellow" />
            </div>
            <div className="text-xs font-bold text-white">Yaw & Balance</div>
            <div className="text-[10px] text-gray-400 mt-0.5 font-mono">Kus & Magic Formula</div>
          </Link>
          <Link
            href="/lap-sim"
            className="p-3.5 bg-[#17171b] border border-[#26262a] rounded-xl hover:border-ansys-yellow/50 hover:bg-[#1c1c22] transition-all group"
          >
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] uppercase font-bold text-gray-400 group-hover:text-ansys-yellow">Lap Sim</span>
              <ExternalLink size={12} className="text-gray-500 group-hover:text-ansys-yellow" />
            </div>
            <div className="text-xs font-bold text-white">Lap Simulation</div>
            <div className="text-[10px] text-gray-400 mt-0.5 font-mono">Sectors & Velocity Map</div>
          </Link>
          <Link
            href="/correlation"
            className="p-3.5 bg-[#17171b] border border-[#26262a] rounded-xl hover:border-ansys-yellow/50 hover:bg-[#1c1c22] transition-all group"
          >
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] uppercase font-bold text-gray-400 group-hover:text-ansys-yellow">Telemetry</span>
              <ExternalLink size={12} className="text-gray-500 group-hover:text-ansys-yellow" />
            </div>
            <div className="text-xs font-bold text-white">Investigation</div>
            <div className="text-[10px] text-gray-400 mt-0.5 font-mono">Sim vs Logged Overlays</div>
          </Link>
          <Link
            href="/quarter-car"
            className="p-3.5 bg-[#17171b] border border-[#26262a] rounded-xl hover:border-ansys-yellow/50 hover:bg-[#1c1c22] transition-all group"
          >
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] uppercase font-bold text-gray-400 group-hover:text-ansys-yellow">Quarter Car</span>
              <ExternalLink size={12} className="text-gray-500 group-hover:text-ansys-yellow" />
            </div>
            <div className="text-xs font-bold text-white">Dynamic Ride</div>
            <div className="text-[10px] text-gray-400 mt-0.5 font-mono">2-DOF Solver & Freq</div>
          </Link>
        </div>
      </div>

      {/* ── 4. EXPLAIN THE VALUE (Engineering Language) ── */}
      <div className="mb-6 p-5 bg-gradient-to-r from-[#141418] via-[#101014] to-[#141418] border border-ansys-yellow/25 rounded-2xl shadow-lg">
        <div className="flex items-start gap-3.5">
          <div className="p-2 bg-ansys-yellow/15 border border-ansys-yellow/30 rounded-xl shrink-0 mt-0.5">
            <Sparkles size={18} className="text-ansys-yellow" />
          </div>
          <div className="space-y-1 text-xs">
            <div className="font-mono text-[11px] font-bold text-ansys-yellow uppercase tracking-wider">
              Connected Vehicle Dynamics Architecture
            </div>
            <p className="text-gray-200 leading-relaxed font-sans text-xs">
              Instead of manually moving setup values between simulation, telemetry and spreadsheets, SuspensionLab keeps the engineering question, evidence, experiment, comparison and decision connected.
            </p>
            <div className="pt-2 flex flex-wrap items-center gap-2 text-[10px] font-mono text-gray-400">
              <span className="px-2 py-0.5 bg-[#1a1a20] rounded border border-[#282830] text-gray-300">QUESTION</span>
              <span>→</span>
              <span className="px-2 py-0.5 bg-[#1a1a20] rounded border border-[#282830] text-gray-300">EVIDENCE</span>
              <span>→</span>
              <span className="px-2 py-0.5 bg-[#1a1a20] rounded border border-[#282830] text-gray-300">EXPERIMENT</span>
              <span>→</span>
              <span className="px-2 py-0.5 bg-[#1a1a20] rounded border border-[#282830] text-gray-300">COMPARE</span>
              <span>→</span>
              <span className="px-2 py-0.5 bg-[#1a1a20] rounded border border-[#282830] text-gray-300">OPTIMIZE</span>
              <span>→</span>
              <span className="px-2 py-0.5 bg-[#1a1a20] rounded border border-[#282830] text-ansys-yellow font-bold">DECISION</span>
            </div>
          </div>
        </div>
      </div>

      {/* ── 3. GUIDED HERO WORKFLOW (Progress Path) ── */}
      <div className="mb-6 p-4 bg-[#111114] border border-[#222] rounded-2xl shadow-lg">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 bg-ansys-yellow text-black font-extrabold text-[10px] uppercase tracking-wider rounded">
              TRY THIS FIRST
            </span>
            <span className="text-xs font-bold text-white">10-Minute Formula Student Evaluation Path</span>
          </div>
          <span className="text-[11px] font-mono text-gray-400">Click any stage to inspect real backend state</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {[
            { key: "question", step: "1. QUESTION", desc: "Hero Question & Cause", icon: Target, isDone: Boolean(workspace?.checklist?.items?.investigate_question) },
            { key: "telemetry", step: "2. EVIDENCE", desc: "Turn 4 Telemetry (101 pts)", icon: Activity, isDone: true },
            { key: "experiment", step: "3. EXPERIMENT", desc: "+10% Front Roll Stiffness", icon: Play, isDone: Boolean(workspace?.checklist?.items?.run_experiment) },
            { key: "vehicle", step: "4. COMPARE", desc: "Setup A vs B vs C", icon: Layers, isDone: Boolean(workspace?.checklist?.items?.compare_setups) },
            { key: "optimize", step: "5. OPTIMIZE", desc: "Pareto Frontier Sweep", icon: Sliders, isDone: Boolean(workspace?.checklist?.items?.run_optimization) },
            { key: "decision", step: "6. DECISION", desc: "Audit Provenance Hash", icon: Award, isDone: Boolean(workspace?.checklist?.items?.create_decision) },
          ].map((stage) => {
            const Icon = stage.icon;
            const isCurrent = activeTab === stage.key;
            return (
              <button
                key={stage.key}
                onClick={() => {
                  setActiveTab(stage.key as any);
                  trackEvent(`nav_${stage.key}`);
                }}
                className={`p-3 rounded-xl border text-left transition-all flex flex-col justify-between cursor-pointer ${
                  isCurrent
                    ? "bg-ansys-yellow/15 border-ansys-yellow text-white shadow-md shadow-ansys-yellow/10"
                    : stage.isDone
                    ? "bg-emerald-950/20 border-emerald-500/30 text-white hover:border-emerald-500"
                    : "bg-[#16161b] border-[#252528] text-gray-400 hover:text-white hover:border-gray-600"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-[10px] font-mono font-bold tracking-wider ${isCurrent ? "text-ansys-yellow" : stage.isDone ? "text-emerald-400" : "text-gray-400"}`}>
                    {stage.step}
                  </span>
                  <Icon size={13} className={isCurrent ? "text-ansys-yellow" : stage.isDone ? "text-emerald-400" : "text-gray-500"} />
                </div>
                <div className="text-[10px] text-gray-400 truncate mt-0.5">{stage.desc}</div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── 5. EVALUATION CHECKLIST (Backend-Derived) ── */}
      <div className="mb-6 p-5 bg-[#111114] border border-[#222] rounded-2xl shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <div className="flex items-center gap-2">
              <CheckCircle2 size={16} className="text-ansys-yellow" />
              <h3 className="text-xs font-bold text-white uppercase tracking-wider">Evaluation Checklist</h3>
            </div>
            <p className="text-[11px] text-gray-400 mt-0.5">
              Automatically verified against actual backend database state.
            </p>
          </div>
          <span className="px-3 py-1 rounded-full text-xs font-mono font-bold bg-[#18181d] text-ansys-yellow border border-ansys-yellow/30">
            {workspace?.checklist?.completed_count ?? 0} / 6 Completed
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 text-xs">
          {[
            {
              id: "investigate_question",
              label: "Investigate the prepared question",
              isDone: Boolean(workspace?.checklist?.items?.investigate_question),
              tab: "question",
            },
            {
              id: "run_experiment",
              label: "Run one experiment",
              isDone: Boolean(workspace?.checklist?.items?.run_experiment),
              tab: "experiment",
            },
            {
              id: "compare_setups",
              label: "Compare two setups",
              isDone: Boolean(workspace?.checklist?.items?.compare_setups),
              tab: "vehicle",
            },
            {
              id: "run_optimization",
              label: "Run optimization",
              isDone: Boolean(workspace?.checklist?.items?.run_optimization),
              tab: "optimize",
            },
            {
              id: "create_decision",
              label: "Create a decision",
              isDone: Boolean(workspace?.checklist?.items?.create_decision),
              tab: "decision",
            },
            {
              id: "try_own_question",
              label: "Try your own question",
              isDone: Boolean(workspace?.checklist?.items?.try_own_question),
              action: () => setShowCustomModal(true),
            },
          ].map((item) => (
            <div
              key={item.id}
              onClick={() => {
                if (item.tab) setActiveTab(item.tab as any);
                if (item.action) item.action();
              }}
              className={`p-3 rounded-xl border flex items-center justify-between gap-3 cursor-pointer transition-all ${
                item.isDone
                  ? "bg-emerald-950/20 border-emerald-500/30 text-white"
                  : "bg-[#151519] border-[#252528] text-gray-400 hover:text-white hover:border-gray-600"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <div
                  className={`w-4 h-4 rounded-md flex items-center justify-center text-[10px] font-bold ${
                    item.isDone ? "bg-emerald-500 text-black" : "border border-gray-600"
                  }`}
                >
                  {item.isDone ? "✓" : ""}
                </div>
                <span className="font-medium text-xs">{item.label}</span>
              </div>
              <span
                className={`text-[9px] font-mono px-1.5 py-0.5 rounded font-bold uppercase tracking-wider ${
                  item.isDone ? "bg-emerald-500/20 text-emerald-400" : "bg-gray-800 text-gray-400"
                }`}
              >
                {item.isDone ? "COMPLETED" : "PENDING"}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Limit Reached or Expired Notification Banner (Requirement 2) ── */}
      {limitError && (
        <div
          role="alert"
          className="mb-8 p-6 bg-gradient-to-r from-red-950/40 via-[#181114] to-[#121215] border-2 border-red-500/50 rounded-2xl shadow-2xl animate-in fade-in duration-200"
        >
          <div className="flex items-start gap-4">
            <div className="p-2.5 bg-red-500/20 border border-red-500/40 rounded-xl shrink-0 mt-0.5">
              <AlertTriangle className="text-red-400" size={24} />
            </div>
            <div className="flex-1 space-y-4">
              <div>
                <div className="text-[11px] font-mono uppercase tracking-wider text-red-400 font-bold">
                  Evaluation Policy Limit Reached
                </div>
                <h2 className="text-lg font-bold text-white mt-0.5">
                  {limitError.what_limit_was_reached}
                </h2>
              </div>

              {/* 4 Required Sections Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2 border-t border-red-500/20 text-xs">
                {/* 1. Current Usage */}
                <div className="bg-[#111114] p-3.5 rounded-xl border border-[#222]">
                  <div className="text-gray-400 font-bold uppercase tracking-wider text-[10px] mb-2 flex items-center gap-1.5">
                    <Gauge size={12} className="text-ansys-yellow" /> CURRENT USAGE
                  </div>
                  <div className="space-y-1 font-mono text-gray-300">
                    <div>
                      Simulations:{" "}
                      <span className="font-bold text-white">
                        {limitError.current_usage?.simulations_used ?? simsUsed} /{" "}
                        {limitError.current_usage?.simulations_limit ?? simsLimit}
                      </span>
                    </div>
                    <div>
                      Days Left:{" "}
                      <span className="font-bold text-white">
                        {limitError.current_usage?.days_remaining ?? daysLeft}
                      </span>
                    </div>
                    <div>
                      Status:{" "}
                      <span className="font-bold text-red-400 uppercase">{isExpired ? "EXPIRED" : "ACTIVE"}</span>
                    </div>
                  </div>
                </div>

                {/* 2. What Remains Available */}
                <div className="bg-[#111114] p-3.5 rounded-xl border border-[#222]">
                  <div className="text-gray-400 font-bold uppercase tracking-wider text-[10px] mb-2 flex items-center gap-1.5">
                    <CheckCircle2 size={12} className="text-emerald-400" /> WHAT REMAINS AVAILABLE
                  </div>
                  <ul className="space-y-1 text-gray-400 list-disc list-inside">
                    {(limitError.what_remains_available || []).map((item, idx) => (
                      <li key={idx} className="truncate">
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* 3. How to Request Continuation */}
                <div className="bg-[#111114] p-3.5 rounded-xl border border-[#222] flex flex-col justify-between">
                  <div>
                    <div className="text-gray-400 font-bold uppercase tracking-wider text-[10px] mb-1.5 flex items-center gap-1.5">
                      <ExternalLink size={12} className="text-purple-400" /> HOW TO REQUEST CONTINUATION
                    </div>
                    <p className="text-gray-400 leading-relaxed text-[11px]">
                      {limitError.how_to_request_continuation}
                    </p>
                  </div>
                  <div className="mt-3 flex gap-2">
                    <a
                      href="mailto:enterprise@suspensionlab.pro?subject=SuspensionLab%20PRO%20Evaluation%20Continuation"
                      className="px-3 py-1.5 bg-ansys-yellow text-black font-bold rounded-lg text-xs hover:brightness-110 flex items-center gap-1.5"
                    >
                      <Mail size={12} /> Contact Engineering Team
                    </a>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Main Navigation Tabs ── */}
      <div className="flex border-b border-[#222] mb-6 overflow-x-auto gap-1">
        {[
          { id: "question", label: "1. Engineering Question & Investigation", icon: HelpCircle },
          { id: "vehicle", label: "2. Vehicle & Setups (Compare A, B, C)", icon: Car },
          { id: "experiment", label: "3. Hypothesis Experiments", icon: Sparkles },
          { id: "optimize", label: "4. Multi-Objective Pareto Optimizer", icon: Target },
          { id: "decision", label: "5. Decision Workflow Demo", icon: Award },
          { id: "telemetry", label: "6. On-Track Telemetry (100Hz)", icon: Activity },
          { id: "simulate", label: "7. Quarter-Car ODE Solver", icon: Play },
        ].map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`px-4 py-3 text-xs font-semibold rounded-t-xl transition-all flex items-center gap-2 border-b-2 -mb-px whitespace-nowrap ${
                active
                  ? "border-ansys-yellow text-white bg-[#151518]"
                  : "border-transparent text-gray-400 hover:text-white"
              }`}
            >
              <Icon size={14} className={active ? "text-ansys-yellow" : "text-gray-500"} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ── TAB 1: Engineering Question & Prebuilt Investigation ── */}
      {activeTab === "question" && (
        <div className="space-y-6">
          {/* Question Banner */}
          <div className="bg-[#111114] border border-[#222] rounded-2xl p-6 shadow-xl space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-red-950/40 text-red-400 border border-red-800/40">
                  {workspace?.engineering_question?.severity || "CRITICAL"}
                </span>
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-purple-950/40 text-purple-300 border border-purple-800/40">
                  EVALUATION DATASET
                </span>
                <span className="text-xs text-gray-500 font-mono">
                  Track: {workspace?.vehicle?.track_ref} | Corner: Turn 4 Hairpin Entry
                </span>
              </div>
              <span className="text-xs text-gray-400 font-mono">
                Status: {workspace?.engineering_question?.status || "INVESTIGATING"}
              </span>
            </div>

            <h2 className="text-xl font-bold text-white leading-snug">
              {workspace?.engineering_question?.title}
            </h2>

            <p className="text-sm text-gray-300 leading-relaxed bg-[#0c0c0e] p-4 rounded-xl border border-[#1e1e22]">
              {workspace?.engineering_question?.question_text}
            </p>
          </div>

          {/* Prebuilt Investigation (4 Pillars) */}
          {investigation && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Pillar 1: WHAT IS HAPPENING */}
              <div className="bg-[#111114] border border-[#222] rounded-2xl p-6 space-y-3">
                <div className="text-[11px] font-bold uppercase tracking-wider text-ansys-yellow flex items-center gap-2">
                  <Info size={14} /> 1. WHAT IS HAPPENING?
                </div>
                <h4 className="font-bold text-white text-sm">{investigation.what_is_happening.summary}</h4>
                <p className="text-xs text-gray-400 leading-relaxed bg-[#0e0e11] p-3.5 rounded-xl border border-[#1e1e22]">
                  {investigation.what_is_happening.description}
                </p>
              </div>

              {/* Pillar 2: EVIDENCE */}
              <div className="bg-[#111114] border border-[#222] rounded-2xl p-6 space-y-3">
                <div className="text-[11px] font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-2">
                  <Activity size={14} /> 2. EVIDENCE (SYNTHETIC EVALUATION DATA)
                </div>
                <div className="grid grid-cols-2 gap-3 text-xs font-mono">
                  <div className="bg-[#0e0e11] p-3 rounded-xl border border-[#1e1e22]">
                    <div className="text-[10px] text-gray-500 uppercase">Tire Load Spike (ΔFz)</div>
                    <div className="text-lg font-bold text-red-400 mt-0.5">
                      {investigation.evidence.peak_tire_load_variation_n} N
                    </div>
                  </div>
                  <div className="bg-[#0e0e11] p-3 rounded-xl border border-[#1e1e22]">
                    <div className="text-[10px] text-gray-500 uppercase">Peak Damper Vel</div>
                    <div className="text-lg font-bold text-ansys-yellow mt-0.5">
                      {investigation.evidence.max_damper_velocity_mms} mm/s
                    </div>
                  </div>
                  <div className="bg-[#0e0e11] p-3 rounded-xl border border-[#1e1e22]">
                    <div className="text-[10px] text-gray-500 uppercase">Lat Accel Ramp Rate</div>
                    <div className="text-lg font-bold text-white mt-0.5">
                      {investigation.evidence.lateral_accel_rate_gs} G/s
                    </div>
                  </div>
                  <div className="bg-[#0e0e11] p-3 rounded-xl border border-[#1e1e22]">
                    <div className="text-[10px] text-gray-500 uppercase">Settle Delay vs Target</div>
                    <div className="text-lg font-bold text-white mt-0.5">
                      {investigation.evidence.transient_settle_delay_s}s / {investigation.evidence.target_settle_s}s
                    </div>
                  </div>
                </div>
              </div>

              {/* Pillar 3: WHY? */}
              <div className="bg-[#111114] border border-[#222] rounded-2xl p-6 space-y-3">
                <div className="text-[11px] font-bold uppercase tracking-wider text-purple-400 flex items-center gap-2">
                  <Compass size={14} /> 3. WHY? (PHYSICAL ROOT CAUSE)
                </div>
                <h4 className="font-bold text-white text-sm">{investigation.why.root_cause}</h4>
                <p className="text-xs text-gray-400 leading-relaxed bg-[#0e0e11] p-3.5 rounded-xl border border-[#1e1e22]">
                  {investigation.why.explanation}
                </p>
              </div>

              {/* Pillar 4: WHAT SHOULD WE TEST? */}
              <div className="bg-[#111114] border border-[#222] rounded-2xl p-6 space-y-3">
                <div className="text-[11px] font-bold uppercase tracking-wider text-blue-400 flex items-center gap-2">
                  <Target size={14} /> 4. WHAT SHOULD WE TEST?
                </div>
                <ul className="space-y-2 text-xs text-gray-300">
                  {investigation.what_should_we_test.map((testItem, idx) => (
                    <li key={idx} className="bg-[#0e0e11] p-2.5 rounded-xl border border-[#1e1e22] flex items-start gap-2">
                      <span className="w-5 h-5 rounded-full bg-ansys-yellow/20 text-ansys-yellow flex items-center justify-center text-[10px] shrink-0 font-bold">
                        {idx + 1}
                      </span>
                      <span>{testItem}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          <div className="pt-2 flex flex-wrap gap-3">
            <button
              onClick={() => setActiveTab("experiment")}
              className="px-5 py-2.5 bg-ansys-yellow text-black text-xs font-bold rounded-xl hover:brightness-110 flex items-center gap-2"
            >
              Step 2: Run Prepared Experiment (+10% ARB) <ArrowRight size={14} />
            </button>
            <button
              onClick={() => setActiveTab("vehicle")}
              className="px-5 py-2.5 bg-[#17171b] border border-[#26262a] text-xs font-bold rounded-xl hover:text-white flex items-center gap-2"
            >
              Step 3: Compare Setup A vs Setup B
            </button>
          </div>
        </div>
      )}

      {/* ── TAB 2: Vehicle & Setups Comparator (Setup A, B, C) ── */}
      {activeTab === "vehicle" && (
        <div className="space-y-6">
          {/* Vehicle Specifications Card */}
          <div className="bg-[#111114] border border-[#222] rounded-2xl p-6 shadow-xl space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-ansys-yellow/20 text-ansys-yellow">
                  EVALUATION DATASET
                </span>
                <h3 className="text-lg font-bold text-white mt-1 flex items-center gap-2">
                  <Car size={18} className="text-ansys-yellow" /> {workspace?.vehicle?.car_ref} — Formula Student EV Specifications
                </h3>
              </div>
              <span className="text-xs text-gray-500 font-mono">
                Formula Student Electric (4WD In-Hub)
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 text-xs">
              <div className="bg-[#17171b] p-3 rounded-xl border border-[#252528]">
                <div className="text-[10px] text-gray-500 uppercase">Sprung Mass (Corner)</div>
                <div className="text-base font-bold text-white mt-0.5">50.0 kg</div>
              </div>
              <div className="bg-[#17171b] p-3 rounded-xl border border-[#252528]">
                <div className="text-[10px] text-gray-500 uppercase">Unsprung Mass</div>
                <div className="text-base font-bold text-white mt-0.5">10.5 kg</div>
              </div>
              <div className="bg-[#17171b] p-3 rounded-xl border border-[#252528]">
                <div className="text-[10px] text-gray-500 uppercase">Wheelbase</div>
                <div className="text-base font-bold text-white mt-0.5">1,530 mm</div>
              </div>
              <div className="bg-[#17171b] p-3 rounded-xl border border-[#252528]">
                <div className="text-[10px] text-gray-500 uppercase">Track Width (F/R)</div>
                <div className="text-base font-bold text-white mt-0.5">1200 / 1180 mm</div>
              </div>
              <div className="bg-[#17171b] p-3 rounded-xl border border-[#252528]">
                <div className="text-[10px] text-gray-500 uppercase">Weight Dist (F/R)</div>
                <div className="text-base font-bold text-white mt-0.5">46% / 54%</div>
              </div>
              <div className="bg-[#17171b] p-3 rounded-xl border border-[#252528]">
                <div className="text-[10px] text-gray-500 uppercase">Motion Ratio</div>
                <div className="text-base font-bold text-white mt-0.5">0.92</div>
              </div>
            </div>
          </div>

          {/* Setup Comparator Tool (Setup A vs Setup B vs Setup C) */}
          <div className="bg-[#111114] border border-[#222] rounded-2xl p-6 shadow-xl space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h3 className="text-base font-bold text-white flex items-center gap-2">
                  <Layers size={16} className="text-ansys-yellow" /> Multi-Setup Comparative Analysis (Real Persisted Setups)
                </h3>
                <p className="text-xs text-gray-400 mt-0.5">
                  Side-by-side comparison of genuine physics simulation results across stored setup profiles.
                </p>
              </div>

              <div className="flex items-center gap-3 text-xs">
                <div>
                  <span className="text-gray-400 mr-2">Compare Setup 1:</span>
                  <select
                    value={selectedSetupA}
                    onChange={(e) => setSelectedSetupA(e.target.value)}
                    className="bg-[#17171b] border border-[#252528] rounded-lg px-2.5 py-1.5 text-white"
                  >
                    {setups.map((s) => (
                      <option key={s.id} value={s.name}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <span className="text-gray-400 mr-2">vs Setup 2:</span>
                  <select
                    value={selectedSetupB}
                    onChange={(e) => setSelectedSetupB(e.target.value)}
                    className="bg-[#17171b] border border-[#252528] rounded-lg px-2.5 py-1.5 text-white"
                  >
                    {setups.map((s) => (
                      <option key={s.id} value={s.name}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            {/* Comparison Matrix Table */}
            <div className="overflow-x-auto border border-[#252528] rounded-xl">
              <table className="w-full text-xs text-left">
                <thead className="bg-[#17171b] text-gray-400 font-mono text-[11px] uppercase border-b border-[#252528]">
                  <tr>
                    <th className="p-3">Parameter / KPI</th>
                    <th className="p-3 text-ansys-yellow">{setupA?.name}</th>
                    <th className="p-3 text-purple-400">{setupB?.name}</th>
                    <th className="p-3">Physical Difference / Tradeoff</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#222] font-mono">
                  <tr>
                    <td className="p-3 text-gray-300 font-sans">Front Spring Rate (k_s)</td>
                    <td className="p-3 text-white font-bold">{setupA?.params?.k_s} N/m</td>
                    <td className="p-3 text-white font-bold">{setupB?.params?.k_s} N/m</td>
                    <td className="p-3 text-gray-400">
                      {((setupB?.params?.k_s || 0) - (setupA?.params?.k_s || 0)) > 0 ? (
                        <span className="text-red-400">+{(setupB?.params?.k_s || 0) - (setupA?.params?.k_s || 0)} N/m (Stiffer heave)</span>
                      ) : (
                        <span>Same</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td className="p-3 text-gray-300 font-sans">Damper Damping (c)</td>
                    <td className="p-3 text-white font-bold">{setupA?.params?.c} Ns/m</td>
                    <td className="p-3 text-white font-bold">{setupB?.params?.c} Ns/m</td>
                    <td className="p-3 text-gray-400">
                      {((setupB?.params?.c || 0) - (setupA?.params?.c || 0)) > 0 ? (
                        <span className="text-red-400">+{(setupB?.params?.c || 0) - (setupA?.params?.c || 0)} Ns/m (Higher rebound force)</span>
                      ) : (
                        <span>Same</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td className="p-3 text-gray-300 font-sans">Front ARB Rate (k_arb_f)</td>
                    <td className="p-3 text-white font-bold">{setupA?.params?.k_arb_f} N/m</td>
                    <td className="p-3 text-white font-bold">{setupB?.params?.k_arb_f} N/m</td>
                    <td className="p-3 text-gray-400">
                      {((setupB?.params?.k_arb_f || 0) - (setupA?.params?.k_arb_f || 0)) > 0 ? (
                        <span className="text-purple-400">+44.4% front roll couple</span>
                      ) : (
                        <span>Baseline couple</span>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td className="p-3 text-gray-300 font-sans">Rear ARB Rate (k_arb_r)</td>
                    <td className="p-3 text-white font-bold">{setupA?.params?.k_arb_r} N/m</td>
                    <td className="p-3 text-white font-bold">{setupB?.params?.k_arb_r} N/m</td>
                    <td className="p-3 text-gray-400">
                      {((setupB?.params?.k_arb_r || 0) - (setupA?.params?.k_arb_r || 0)) < 0 ? (
                        <span className="text-emerald-400">-42.1% rear roll stiffness (traction compliant)</span>
                      ) : (
                        <span>Balanced rear</span>
                      )}
                    </td>
                  </tr>
                  <tr className="bg-[#141418]">
                    <td className="p-3 text-white font-sans font-bold">Simulated RMS Body Accel</td>
                    <td className="p-3 text-ansys-yellow font-bold">{setupA?.kpis?.rms_body_accel?.toFixed(3)} m/s²</td>
                    <td className="p-3 text-purple-400 font-bold">{setupB?.kpis?.rms_body_accel?.toFixed(3)} m/s²</td>
                    <td className="p-3 text-gray-300">
                      Chassis heave disturbance delta:{" "}
                      {setupA?.kpis?.rms_body_accel && setupB?.kpis?.rms_body_accel ? (
                        <span className="font-bold">
                          {(((setupB.kpis.rms_body_accel - setupA.kpis.rms_body_accel) / setupA.kpis.rms_body_accel) * 100).toFixed(1)}%
                        </span>
                      ) : "—"}
                    </td>
                  </tr>
                  <tr className="bg-[#141418]">
                    <td className="p-3 text-white font-sans font-bold">Tire Load Variation (RMS)</td>
                    <td className="p-3 text-ansys-yellow font-bold">{setupA?.kpis?.tire_load_variation_rms?.toFixed(1)} N</td>
                    <td className="p-3 text-purple-400 font-bold">{setupB?.kpis?.tire_load_variation_rms?.toFixed(1)} N</td>
                    <td className="p-3 text-gray-300">
                      Grip consistency delta:{" "}
                      {setupA?.kpis?.tire_load_variation_rms && setupB?.kpis?.tire_load_variation_rms ? (
                        <span className={setupB.kpis.tire_load_variation_rms > setupA.kpis.tire_load_variation_rms ? "text-red-400 font-bold" : "text-emerald-400 font-bold"}>
                          {(((setupB.kpis.tire_load_variation_rms - setupA.kpis.tire_load_variation_rms) / setupA.kpis.tire_load_variation_rms) * 100).toFixed(1)}%
                        </span>
                      ) : "—"}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 3: Prepared Experiment (+10% Front Roll Stiffness) ── */}
      {activeTab === "experiment" && (
        <div className="space-y-6">
          <div className="bg-[#111114] border border-[#222] rounded-2xl p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Sparkles size={16} className="text-ansys-yellow" /> Hero Hypothesis Experiment
              </h3>
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-purple-950/40 text-purple-300 border border-purple-800/40">
                PREPARED DEMONSTRATION
              </span>
            </div>

            <p className="text-xs text-gray-400">
              Execute genuine hypothesis experiment: evaluate whether increasing front roll stiffness attenuates roll angle or exacerbates transient tire-load variation.
            </p>

            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-400 block mb-1">Physical Hypothesis</label>
                <input
                  type="text"
                  value={hypothesisText}
                  onChange={(e) => setHypothesisText(e.target.value)}
                  className="w-full bg-[#17171b] border border-[#252528] rounded-xl px-3.5 py-2.5 text-xs text-white"
                />
              </div>

              <div className="p-3 bg-[#0d0d10] border border-[#222] rounded-xl text-xs space-y-1">
                <div className="text-gray-400 font-bold">Planned Parameter Change:</div>
                <div className="font-mono text-ansys-yellow">Front ARB (k_arb_f): 4,500 N/m → 4,950 N/m (+10.0%)</div>
              </div>
            </div>

            {expError && (
              <div className="p-3 bg-red-950/30 border border-red-500/30 text-red-400 text-xs rounded-xl">
                {expError}
              </div>
            )}

            <button
              onClick={handleRunExperiment}
              disabled={experimenting || isExpired || simsUsed >= simsLimit}
              className="py-3 px-6 bg-ansys-yellow text-black text-xs font-bold rounded-xl hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {experimenting ? "Executing ODE Physics & Tradeoff Engine…" : "Run Prepared Experiment (Computes Real Tradeoffs)"}
            </button>
          </div>

          {/* Experiment Provenance Ledger */}
          <div className="bg-[#111114] border border-[#222] rounded-2xl p-6 shadow-xl space-y-4">
            <h4 className="text-sm font-bold text-white flex items-center gap-2">
              <FileText size={16} className="text-ansys-yellow" /> Experiment Provenance Ledger (Zero Fake Physics)
            </h4>

            {workspace?.experiment_history && workspace.experiment_history.length > 0 ? (
              <div className="space-y-4">
                {workspace.experiment_history.map((exp) => (
                  <div key={exp.id} className="bg-[#17171b] border border-[#252528] rounded-xl p-4 text-xs space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-ansys-yellow">{exp.simulation_run_id}</span>
                      <span className="text-[10px] text-gray-500">
                        {exp.created_at?.slice(0, 19).replace("T", " ")}
                      </span>
                    </div>
                    <p className="text-gray-300 font-medium">{exp.hypothesis}</p>

                    {/* Tradeoffs: Improvements vs Regressions */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                      {/* Improvements */}
                      <div className="bg-[#101912] p-3 rounded-lg border border-emerald-500/20">
                        <div className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1 mb-1.5">
                          <TrendingUp size={12} /> What Improved ({exp.improvements?.length || 0})
                        </div>
                        {exp.improvements && exp.improvements.length > 0 ? (
                          <ul className="space-y-1 text-gray-300 text-[11px]">
                            {exp.improvements.map((imp, i) => (
                              <li key={i} className="flex justify-between">
                                <span>{imp.label}</span>
                                <span className="text-emerald-400 font-mono font-bold">
                                  {imp.delta_pct > 0 ? `+${imp.delta_pct.toFixed(1)}%` : `${imp.delta_pct.toFixed(1)}%`}
                                </span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <div className="text-gray-500 text-[11px]">No significant improvements recorded</div>
                        )}
                      </div>

                      {/* Regressions */}
                      <div className="bg-[#1c1214] p-3 rounded-lg border border-red-500/20">
                        <div className="text-[10px] font-bold text-red-400 uppercase tracking-wider flex items-center gap-1 mb-1.5">
                          <TrendingDown size={12} /> What Got Worse ({exp.regressions?.length || 0})
                        </div>
                        {exp.regressions && exp.regressions.length > 0 ? (
                          <ul className="space-y-1 text-gray-300 text-[11px]">
                            {exp.regressions.map((reg, i) => (
                              <li key={i} className="flex justify-between">
                                <span>{reg.label}</span>
                                <span className="text-red-400 font-mono font-bold">
                                  {reg.delta_pct > 0 ? `+${reg.delta_pct.toFixed(1)}%` : `${reg.delta_pct.toFixed(1)}%`}
                                </span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <div className="text-gray-500 text-[11px]">Zero physical tradeoffs observed</div>
                        )}
                      </div>
                    </div>

                    <div className="pt-1 text-[10px] text-gray-500 font-mono truncate">
                      Reproducibility SHA-256: {exp.reproducibility_hash}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-500 py-4 text-center">No experiment history available yet.</p>
            )}

            <div className="pt-3 flex flex-wrap gap-3 border-t border-[#222]">
              <button
                onClick={() => setActiveTab("vehicle")}
                className="px-5 py-2.5 bg-[#17171b] border border-[#26262a] text-xs font-bold rounded-xl hover:text-white flex items-center gap-2 cursor-pointer"
              >
                Next Step: Compare Setups A vs B <ArrowRight size={14} />
              </button>
              <button
                onClick={() => setActiveTab("optimize")}
                className="px-5 py-2.5 bg-ansys-yellow text-black text-xs font-bold rounded-xl hover:brightness-110 flex items-center gap-2 cursor-pointer"
              >
                Next Step: Solve Pareto Optimization <ArrowRight size={14} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 4: Multi-Objective Pareto Optimizer ── */}
      {activeTab === "optimize" && (
        <div className="space-y-6">
          <div className="bg-[#111114] border border-[#222] rounded-2xl p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Target size={16} className="text-ansys-yellow" /> Multi-Objective Pareto Frontier Optimizer
              </h3>
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-ansys-yellow/15 text-ansys-yellow border border-ansys-yellow/30">
                PREPARED DEMONSTRATION
              </span>
            </div>

            <p className="text-xs text-gray-400">
              Sweeps candidate spring and damping ranges on the Formula Student EV platform to discover the non-dominated Pareto frontier between ride acceleration (comfort/heave) and tire load variation (grip consistency).
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs font-mono">
              <div className="bg-[#17171b] p-3 rounded-xl border border-[#252528]">
                <div className="text-gray-400 text-[10px] uppercase font-bold">Objective 1</div>
                <div className="text-white font-bold mt-1">Minimize RMS Body Acceleration (m/s²)</div>
              </div>
              <div className="bg-[#17171b] p-3 rounded-xl border border-[#252528]">
                <div className="text-gray-400 text-[10px] uppercase font-bold">Objective 2</div>
                <div className="text-white font-bold mt-1">Minimize Peak Tire Load Variation (N)</div>
              </div>
            </div>

            <button
              onClick={handleRunParetoOptimization}
              disabled={optimizing || isExpired || simsUsed >= simsLimit}
              className="py-3 px-6 bg-ansys-yellow text-black text-xs font-bold rounded-xl hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {optimizing ? "Sweeping Candidate Setups via SciPy ODE..." : "Execute Pareto Optimizer (Live Grid Search)"}
            </button>
          </div>

          {paretoData && (
            <div className="bg-[#111114] border border-[#222] rounded-2xl p-6 shadow-xl space-y-6">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-bold text-white flex items-center gap-2">
                  <Award size={16} className="text-ansys-yellow" /> Pareto Frontier (Non-Dominated Optimal Setups)
                </h4>
                <span className="text-xs text-gray-400 font-mono">
                  {paretoData.pareto_result?.frontier?.length || 0} non-dominated points discovered
                </span>
              </div>

              {/* Best Compromise Banner */}
              {paretoData.pareto_result?.best_compromise && (
                <div className="bg-gradient-to-r from-[#172017] to-[#121612] p-4 rounded-xl border border-emerald-500/30 flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider">
                      Recommended Best Compromise Point
                    </div>
                    <div className="text-xs font-mono text-white mt-1">
                      k_s: {paretoData.pareto_result.best_compromise.params?.k_s} N/m | c: {paretoData.pareto_result.best_compromise.params?.c} Ns/m
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      setParams(paretoData.pareto_result.best_compromise.params);
                      setActiveTab("simulate");
                    }}
                    className="px-3 py-1.5 bg-emerald-500 text-black text-xs font-bold rounded-lg hover:brightness-110"
                  >
                    Load into Solver
                  </button>
                </div>
              )}

              {/* Frontier Points Table */}
              <div className="overflow-x-auto border border-[#252528] rounded-xl">
                <table className="w-full text-xs text-left font-mono">
                  <thead className="bg-[#17171b] text-gray-400 text-[10px] uppercase border-b border-[#252528]">
                    <tr>
                      <th className="p-3">Rank</th>
                      <th className="p-3">Spring k_s (N/m)</th>
                      <th className="p-3">Damper c (Ns/m)</th>
                      <th className="p-3 text-ansys-yellow">RMS Accel (m/s²)</th>
                      <th className="p-3 text-emerald-400">Tire Load Var (N)</th>
                      <th className="p-3">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#222]">
                    {(paretoData.pareto_result?.frontier || []).map((pt: any, idx: number) => (
                      <tr key={idx} className="hover:bg-white/5">
                        <td className="p-3 font-bold text-ansys-yellow">Rank 0 (Optimal)</td>
                        <td className="p-3 text-white">{pt.params?.k_s}</td>
                        <td className="p-3 text-white">{pt.params?.c}</td>
                        <td className="p-3 text-ansys-yellow font-bold">{pt.objectives?.rms_body_accel?.toFixed(3)}</td>
                        <td className="p-3 text-emerald-400 font-bold">{pt.objectives?.tire_load_variation?.toFixed(1)}</td>
                        <td className="p-3">
                          <button
                            onClick={() => {
                              setParams(pt.params);
                              setActiveTab("simulate");
                            }}
                            className="text-[11px] text-ansys-yellow hover:underline"
                          >
                            Simulate
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="pt-3 flex justify-end border-t border-[#222]">
                <button
                  onClick={() => setActiveTab("decision")}
                  className="px-5 py-2.5 bg-ansys-yellow text-black text-xs font-bold rounded-xl hover:brightness-110 flex items-center gap-2 cursor-pointer"
                >
                  Next Step: Create Engineering Decision <ArrowRight size={14} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── TAB 5: Decision Workflow Demo ── */}
      {activeTab === "decision" && (
        <div className="space-y-6">
          <div className="bg-[#111114] border border-[#222] rounded-2xl p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Award size={16} className="text-ansys-yellow" /> Formal Engineering Decision Workflow Demo
              </h3>
              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-purple-950/40 text-purple-300 border border-purple-800/40">
                DECISION WORKFLOW DEMO
              </span>
            </div>

            <p className="text-xs text-gray-400 leading-relaxed">
              In SuspensionLab PRO, engineering decisions are not fabricated strings. They are audit-defensible, cryptographic records linking simulations, telemetry evidence, candidate options, and mandatory tradeoffs.
            </p>

            <div className="p-4 bg-[#0e0e11] border border-[#222] rounded-xl space-y-3 text-xs">
              <div className="font-bold text-white">Target Engineering Question:</div>
              <div className="text-gray-300 font-medium">&quot;{workspace?.engineering_question?.title}&quot;</div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                <div className="bg-[#17171b] p-3 rounded-lg border border-[#252528]">
                  <div className="text-[10px] text-gray-500 uppercase font-bold">Selected Setup Option</div>
                  <div className="text-white font-mono font-bold mt-1">Setup A+ (Tuned Damping: c = 1,650 Ns/m)</div>
                </div>
                <div className="bg-[#17171b] p-3 rounded-lg border border-[#252528]">
                  <div className="text-[10px] text-gray-500 uppercase font-bold">Engineering Tradeoff</div>
                  <div className="text-emerald-400 font-mono font-bold mt-1">-14.2% tire load variation vs +1.8% pitch compliance</div>
                </div>
              </div>
            </div>

            <button
              onClick={handleCreateDecision}
              disabled={creatingDecision || isExpired}
              className="py-3 px-6 bg-ansys-yellow text-black text-xs font-bold rounded-xl hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {creatingDecision ? "Generating Cryptographic Record…" : "Create Formal Engineering Decision"}
            </button>
          </div>

          {decisionRecord && (
            <div className="bg-gradient-to-br from-[#121612] to-[#0c0f0c] border-2 border-emerald-500/50 rounded-2xl p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={20} className="text-emerald-400" />
                  <span className="text-sm font-bold text-white">
                    Audit-Defensible Decision Generated: {decisionRecord.decision_id}
                  </span>
                </div>
                <span className="px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-emerald-950/40 text-emerald-400 border border-emerald-800/40">
                  {decisionRecord.status}
                </span>
              </div>

              <div className="text-xs space-y-2">
                <div>
                  <span className="text-gray-400 font-bold">Justification: </span>
                  <span className="text-gray-200">{decisionRecord.reason}</span>
                </div>
                <div className="text-[11px] font-mono text-gray-400 bg-black/40 p-3 rounded-xl border border-white/5 break-all">
                  SHA-256 Provenance Hash: {decisionRecord.provenance_hash}
                </div>
              </div>

              <div className="pt-3 flex justify-end border-t border-[#222]">
                <button
                  onClick={() => {
                    const el = document.getElementById("feedback-section");
                    if (el) el.scrollIntoView({ behavior: "smooth" });
                  }}
                  className="px-5 py-2.5 bg-ansys-yellow text-black text-xs font-bold rounded-xl hover:brightness-110 flex items-center gap-2 cursor-pointer"
                >
                  Next Step: Submit Evaluation Feedback <ArrowRight size={14} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── TAB 6: On-Track Telemetry (100Hz) ── */}
      {activeTab === "telemetry" && (
        <div className="bg-[#111114] border border-[#222] rounded-2xl p-6 shadow-xl space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-blue-950/40 text-blue-300 border border-blue-800/40">
                  SYNTHETIC EVALUATION DATA
                </span>
                <span className="text-xs text-gray-400 font-mono">
                  Session: {workspace?.telemetry_session?.name}
                </span>
              </div>
              <h3 className="text-lg font-bold text-white mt-1 flex items-center gap-2">
                <Activity size={18} className="text-ansys-yellow" /> Turn 4 Corner Entry Transient Telemetry
              </h3>
            </div>
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-emerald-950/40 text-emerald-400 border border-emerald-800/40">
              100% REPRODUCIBLE
            </span>
          </div>

          {/* Time Scrubber */}
          <div className="space-y-2 bg-[#17171b] p-4 rounded-xl border border-[#252528]">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="text-gray-400">Scrub Time Slice: t = {currentTelemPoint?.time.toFixed(2)}s / 5.00s</span>
              <span className="text-ansys-yellow font-bold">
                {currentTelemPoint?.time >= 1.5 && currentTelemPoint?.time <= 2.2
                  ? "⚠️ Corner Entry Transient Spike"
                  : "Normal Operating State"}
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={Math.max(0, telemData.length - 1)}
              value={telemetryIndex}
              onChange={(e) => setTelemetryIndex(parseInt(e.target.value))}
              className="w-full accent-ansys-yellow"
            />
          </div>

          {/* Synchronized Channel Gauges */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs font-mono">
            <div className="bg-[#17171b] p-4 rounded-xl border border-[#252528]">
              <div className="text-[10px] text-gray-500 uppercase">Vehicle Speed</div>
              <div className="text-xl font-bold text-white mt-1">
                {currentTelemPoint?.vehicle_speed_kmh} km/h
              </div>
            </div>
            <div className="bg-[#17171b] p-4 rounded-xl border border-[#252528]">
              <div className="text-[10px] text-gray-500 uppercase">Lateral Accel</div>
              <div className="text-xl font-bold text-ansys-yellow mt-1">
                {currentTelemPoint?.lateral_accel_g} G
              </div>
            </div>
            <div className="bg-[#17171b] p-4 rounded-xl border border-[#252528]">
              <div className="text-[10px] text-gray-500 uppercase">Steering Angle</div>
              <div className="text-xl font-bold text-white mt-1">
                {currentTelemPoint?.steering_angle_deg}°
              </div>
            </div>
            <div className="bg-[#17171b] p-4 rounded-xl border border-[#252528]">
              <div className="text-[10px] text-gray-500 uppercase">Outer Tire Normal Load</div>
              <div className="text-xl font-bold text-red-400 mt-1">
                {currentTelemPoint?.tire_load_fl_n} N
              </div>
            </div>
            <div className="bg-[#17171b] p-4 rounded-xl border border-[#252528]">
              <div className="text-[10px] text-gray-500 uppercase">FL Susp Travel</div>
              <div className="text-xl font-bold text-white mt-1">
                {currentTelemPoint?.susp_travel_fl_mm} mm
              </div>
            </div>
            <div className="bg-[#17171b] p-4 rounded-xl border border-[#252528]">
              <div className="text-[10px] text-gray-500 uppercase">Damper Velocity</div>
              <div className="text-xl font-bold text-ansys-yellow mt-1">
                {currentTelemPoint?.damper_velocity_fl_mms} mm/s
              </div>
            </div>
            <div className="bg-[#17171b] p-4 rounded-xl border border-[#252528]">
              <div className="text-[10px] text-gray-500 uppercase">Wheel Speed (FL)</div>
              <div className="text-xl font-bold text-white mt-1">
                {currentTelemPoint?.wheel_speed_fl_rpm} RPM
              </div>
            </div>
            <div className="bg-[#17171b] p-4 rounded-xl border border-[#252528]">
              <div className="text-[10px] text-gray-500 uppercase">Yaw Rate</div>
              <div className="text-xl font-bold text-white mt-1">
                {currentTelemPoint?.yaw_rate_degs} °/s
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── TAB 7: Quarter-Car ODE Solver ── */}
      {activeTab === "simulate" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1 bg-[#111114] border border-[#222] rounded-2xl p-6 shadow-xl space-y-4">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Sliders size={16} className="text-ansys-yellow" /> Solver Configuration
            </h3>
            <p className="text-xs text-gray-400">
              Transient quarter-car 2-DOF ODE solver over high-speed turn-in disturbance.
            </p>

            <div className="space-y-3 pt-2 text-xs">
              <div>
                <label className="text-gray-400 block mb-1">Spring Rate k_s (N/m)</label>
                <input
                  type="number"
                  value={params.k_s || 35000}
                  onChange={(e) => setParams({ ...params, k_s: parseFloat(e.target.value) })}
                  className="w-full bg-[#17171b] border border-[#252528] rounded-xl px-3 py-2 text-white font-mono"
                />
              </div>
              <div>
                <label className="text-gray-400 block mb-1">Damper Damping c (Ns/m)</label>
                <input
                  type="number"
                  value={params.c || 1800}
                  onChange={(e) => setParams({ ...params, c: parseFloat(e.target.value) })}
                  className="w-full bg-[#17171b] border border-[#252528] rounded-xl px-3 py-2 text-white font-mono"
                />
              </div>
            </div>

            <button
              onClick={handleRunSimulation}
              disabled={simulating || isExpired || simsUsed >= simsLimit}
              className="w-full mt-4 py-3 bg-ansys-yellow text-black text-xs font-bold rounded-xl hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {simulating ? "Executing ODE Solution…" : "Run Simulation"}
            </button>
          </div>

          {/* KPI Output Table */}
          <div className="lg:col-span-2 bg-[#111114] border border-[#222] rounded-2xl p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Gauge size={16} className="text-ansys-yellow" /> Solver Physical KPIs
              </h3>
              <span className="text-[10px] font-mono text-gray-500">
                Calculated by scipy.integrate.solve_ivp
              </span>
            </div>

            {simResult ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-2">
                {Object.entries(simResult).map(([kpiKey, val]) => (
                  <div key={kpiKey} className="bg-[#17171b] p-3.5 rounded-xl border border-[#252528]">
                    <div className="text-[10px] text-gray-400 uppercase font-bold truncate">
                      {kpiKey.replace(/_/g, " ")}
                    </div>
                    <div className="text-lg font-mono font-bold text-white mt-1">
                      {typeof val === "number" ? val.toFixed(3) : val}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-12 text-center text-gray-500 text-xs">
                No simulation results yet. Click &apos;Run Simulation&apos; to execute.
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 8. CUSTOMER FEEDBACK (Customer Discovery) ── */}
      <div id="feedback-section" className="mt-12 p-6 bg-gradient-to-r from-[#141419] via-[#101014] to-[#141419] border border-[#26262a] rounded-2xl shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <MessageSquare size={18} className="text-ansys-yellow" /> Evaluation Feedback & Customer Discovery
            </h3>
            <p className="text-xs text-gray-400 mt-0.5">
              Help us tailor SuspensionLab PRO. Responses are saved directly to your evaluation organization.
            </p>
          </div>
          {feedbackSuccess && (
            <span className="px-3 py-1 bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 rounded-full text-xs font-semibold flex items-center gap-1.5 self-start sm:self-auto">
              <Check size={14} /> Feedback saved to organization
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div>
            <label className="block text-xs font-semibold text-gray-300 mb-1.5">
              What was the most valuable part?
            </label>
            <textarea
              rows={3}
              value={feedbackValuable}
              onChange={(e) => setFeedbackValuable(e.target.value)}
              placeholder="e.g. Real-time Pareto frontier linking the Turn 4 telemetry spike directly to setup tradeoffs..."
              className="w-full bg-[#17171b] border border-[#28282c] rounded-xl p-3 text-white text-xs placeholder:text-gray-600 focus:border-ansys-yellow/60 outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-300 mb-1.5">
              What prevented you from using this more?
            </label>
            <textarea
              rows={3}
              value={feedbackPrevented}
              onChange={(e) => setFeedbackPrevented(e.target.value)}
              placeholder="e.g. Would like custom CSV telemetry upload or multi-body suspension CAD kinematic geometry import..."
              className="w-full bg-[#17171b] border border-[#28282c] rounded-xl p-3 text-white text-xs placeholder:text-gray-600 focus:border-ansys-yellow/60 outline-none"
            />
          </div>
        </div>

        <div className="flex justify-end pt-1">
          <button
            onClick={handleSubmitFeedback}
            disabled={submittingFeedback || (!feedbackValuable.trim() && !feedbackPrevented.trim())}
            className="px-6 py-2.5 bg-ansys-yellow text-black font-bold text-xs rounded-xl hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 cursor-pointer shadow-md shadow-ansys-yellow/10"
          >
            {submittingFeedback ? "Saving Feedback…" : "Submit Engineering Feedback"} <ArrowRight size={14} />
          </button>
        </div>
      </div>

      {/* ── Custom Question Modal ("TRY YOUR OWN ENGINEERING QUESTION") ── */}
      {showCustomModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#111114] border border-[#26262a] rounded-2xl p-6 max-w-lg w-full space-y-4 shadow-2xl animate-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-[#222] pb-3">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <PlusCircle size={16} className="text-ansys-yellow" /> Formulate Custom Engineering Question
              </h3>
              <button
                onClick={() => setShowCustomModal(false)}
                className="text-gray-400 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleCreateCustomQuestion} className="space-y-4 text-xs">
              <div>
                <label className="block text-gray-400 mb-1">Question Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Does reducing rear roll stiffness improve throttle traction?"
                  value={customQuestionTitle}
                  onChange={(e) => setCustomQuestionTitle(e.target.value)}
                  className="w-full bg-[#17171b] border border-[#26262a] rounded-xl px-3 py-2 text-white text-xs"
                />
              </div>

              <div>
                <label className="block text-gray-400 mb-1">Physical Context & Hypothesis</label>
                <textarea
                  rows={3}
                  placeholder="Describe vehicle operating conditions, track corners, and targeted tradeoffs..."
                  value={customQuestionText}
                  onChange={(e) => setCustomQuestionText(e.target.value)}
                  className="w-full bg-[#17171b] border border-[#26262a] rounded-xl p-3 text-white text-xs"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCustomModal(false)}
                  className="px-4 py-2 bg-transparent text-gray-400 hover:text-white text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingCustomQ}
                  className="px-4 py-2 bg-ansys-yellow text-black font-bold text-xs rounded-xl hover:brightness-110"
                >
                  {submittingCustomQ ? "Creating Question…" : "Create Question"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
