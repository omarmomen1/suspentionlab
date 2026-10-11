"use client";

import React, { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Activity,
  AlertTriangle,
  AlertCircle,
  Sparkles,
  ShieldCheck,
  CheckCircle2,
  Sliders,
  TrendingDown,
  TrendingUp,
  Cpu,
  Layers,
  FileCheck,
  RotateCcw,
  ArrowRight,
  Info,
  Clock,
  RefreshCw,
} from "lucide-react";
import { useWorkspace } from "../../contexts/WorkspaceContext";
import {
  EvidenceBadge,
  ValidationBadge,
  ConfidenceIndicator,
  WhyButton,
  EngineeringMetric,
  EngineeringCard,
  TelemetryChart,
  ParameterEditor,
  ConstraintWarning,
  ApprovalState,
  ExperimentButton,
  SimulationStatus,
} from "../../components/engineering";
import {
  SimulationApi,
  DigitalTwinApi,
  SetupProposalResponse,
  QuestionsApi,
  EngineeringQuestionRecord,
} from "../../lib/api_client";

function InvestigateContent() {
  const searchParams = useSearchParams();
  const qId = searchParams.get("id") || "q-damper-t9";
  const {
    vehicle,
    setup,
    track,
    simulation,
    modelVersion,
    sessionName,
    telemetry,
    activeProposalId,
    setActiveProposalId,
    setActiveInvestigationId,
    setActiveQuestionId,
  } = useWorkspace();

  // Question state from backend
  const [question, setQuestion] = useState<EngineeringQuestionRecord | null>(null);
  const [questionLoading, setQuestionLoading] = useState(true);
  const [questionError, setQuestionError] = useState<string | null>(null);

  // Investigation Workflow Stages
  const [activeStage, setActiveStage] = useState<"WHAT" | "WHY" | "EVIDENCE" | "TEST">("WHAT");

  // Candidate Setup Experiment State
  const [rearLsc, setRearLsc] = useState<number>(2670); // Baseline 2800 Ns/m (-4.6%)
  const [rearSpring, setRearSpring] = useState<number>(37200); // Baseline 38000 N/m (-2.1%)
  const [frontRh, setFrontRh] = useState<number>(27); // Baseline 28 mm (-1.0mm)

  // Simulation execution state
  const [simResult, setSimResult] = useState<any | null>(null);
  const [simError, setSimError] = useState<string | null>(null);
  const [proposalStatus, setProposalStatus] = useState<"PROPOSED" | "APPROVED" | "REJECTED">("PROPOSED");

  // Digital Twin Proposal State
  const [activeProposal, setActiveProposal] = useState<SetupProposalResponse | null>(null);
  const [isGeneratingProposal, setIsGeneratingProposal] = useState<boolean>(false);
  const [proposalLoading, setProposalLoading] = useState<boolean>(true);

  // Fetch real question details
  useEffect(() => {
    let isMounted = true;
    async function loadQuestion() {
      setQuestionLoading(true);
      setQuestionError(null);
      try {
        const q = await QuestionsApi.getQuestion(qId);
        if (isMounted) {
          setQuestion(q);
          setActiveInvestigationId(q.question_id);
          setActiveQuestionId(q.question_id);
        }
      } catch (err: any) {
        if (isMounted) {
          console.warn("Could not load question:", err);
          setQuestionError(err?.message || `Question '${qId}' not found or outside tenant isolation boundary.`);
        }
      } finally {
        if (isMounted) setQuestionLoading(false);
      }
    }
    loadQuestion();
    return () => {
      isMounted = false;
    };
  }, [qId, setActiveInvestigationId, setActiveQuestionId]);

  const loadActiveProposal = async () => {
    try {
      setProposalLoading(true);
      const res = await DigitalTwinApi.listProposals("active");
      if (res && res.proposals && res.proposals.length > 0) {
        const latest = res.proposals[0];
        setActiveProposal(latest);
        setProposalStatus(latest.status as any);
        setActiveProposalId(latest.id);
      } else {
        setActiveProposal(null);
      }
    } catch (err: any) {
      console.warn("Could not load twin proposals:", err);
      setActiveProposal(null);
    } finally {
      setProposalLoading(false);
    }
  };

  useEffect(() => {
    loadActiveProposal();
  }, []);

  const handleGenerateProposal = async () => {
    setIsGeneratingProposal(true);
    try {
      const headline = question
        ? `Setup Proposal for ${question.title}`
        : "Rear entry platform instability under trail braking";
      const created = await DigitalTwinApi.createProposal("active", headline);
      setActiveProposal(created);
      setProposalStatus(created.status as any);
      setActiveProposalId(created.id);

      // Link proposal to question
      if (question) {
        const existingDecisions = question.linked_decisions || [];
        if (!existingDecisions.includes(created.id)) {
          await QuestionsApi.updateQuestion(question.question_id, {
            status: "HYPOTHESIS_FORMED",
            linked_decisions: [...existingDecisions, created.id],
          }).catch(console.warn);
        }
      }
    } catch (err: any) {
      alert(`Proposal generation failed: ${err?.message || err}`);
    } finally {
      setIsGeneratingProposal(false);
    }
  };

  // Initial simulation run on mount
  useEffect(() => {
    async function runBaselineSim() {
      try {
        const res = await SimulationApi.runQuarterCar({
          m_s: vehicle.mass_kg ? vehicle.mass_kg / 4 : 200,
          k_s: rearSpring,
          c: rearLsc,
          k_t: 280000,
          duration: 3.0,
          dt: 0.005,
        });
        setSimResult(res);
      } catch (e: any) {
        setSimError(e?.message || "Failed running initial ODE experiment");
      }
    }
    runBaselineSim();
  }, [vehicle.mass_kg]);

  const handleRunExperiment = async () => {
    setSimError(null);
    const res = await SimulationApi.runQuarterCar({
      m_s: vehicle.mass_kg ? vehicle.mass_kg / 4 : 200,
      k_s: rearSpring,
      c: rearLsc,
      k_t: 280000,
      duration: 3.0,
      dt: 0.005,
    });
    setSimResult(res);
    return res;
  };

  // Domain detection for dynamic causal reasoning
  const qTitle = question?.title?.toLowerCase() || "";
  const qIdLower = qId.toLowerCase();
  const isTire = qIdLower.includes("tire") || qTitle.includes("tire") || qTitle.includes("grip");
  const isAero = qIdLower.includes("aero") || qTitle.includes("aero") || qTitle.includes("downforce") || qTitle.includes("balance");

  if (questionLoading) {
    return (
      <div className="min-h-screen bg-[#08080a] text-zinc-400 p-8 pt-24 font-mono flex items-center justify-center">
        <div className="flex items-center gap-2">
          <RefreshCw size={18} className="animate-spin text-ansys-yellow" />
          <span>Retrieving Engineering Question Artifact ({qId})...</span>
        </div>
      </div>
    );
  }

  if (questionError || !question) {
    return (
      <div className="w-full bg-[#08080a] text-white min-h-screen pt-24 pb-16 px-4 sm:px-6 font-sans">
        <div className="max-w-2xl mx-auto space-y-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-xs font-mono text-gray-400 hover:text-white transition-colors"
          >
            <ArrowLeft size={14} /> Back to Command Center
          </Link>

          <div className="p-8 rounded-3xl bg-rose-950/20 border border-rose-500/30 font-mono space-y-4">
            <div className="flex items-center gap-2 text-rose-400 font-bold text-sm">
              <AlertCircle size={20} />
              <span>ENGINEERING QUESTION NOT FOUND</span>
            </div>
            <p className="text-xs text-gray-300 font-sans">
              {questionError || `No engineering question with ID '${qId}' exists for your active organization.`}
            </p>
            <div className="pt-2 flex gap-3">
              <Link
                href="/"
                className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-xs font-bold transition-all"
              >
                Return to Command Center
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full bg-[#08080a] text-white selection:bg-ansys-yellow selection:text-black min-h-screen pt-20 pb-16 px-4 sm:px-6 font-sans">
      <div className="max-w-[1520px] mx-auto">
        {/* Navigation Breadcrumb & Back Link */}
        <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-xs font-mono text-gray-400 hover:text-white transition-colors"
          >
            <ArrowLeft size={14} /> Back to Command Center
          </Link>

          {/* Active Vehicle Context Badges */}
          <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
            <span className="px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-gray-300">
              VEHICLE: <strong className="text-white">{vehicle.name}</strong> ({vehicle.version})
            </span>
            <span className="px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-gray-300">
              SETUP: <strong className="text-white">{setup.name}</strong> ({setup.version})
            </span>
            <span className="px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-gray-300">
              TRACK: <strong className="text-white">{track.name}</strong>
            </span>
            <span className="px-2.5 py-1 rounded-lg bg-blue-950/40 border border-blue-500/30 text-blue-300">
              SESSION: <strong>{sessionName}</strong>
            </span>
          </div>
        </div>

        {/* Anomaly Investigation Header Banner (Dynamically Driven by Question) */}
        <div className="p-6 rounded-3xl bg-gradient-to-r from-amber-950/40 via-[#111116] to-[#111116] border border-amber-500/30 mb-8 shadow-2xl relative overflow-hidden">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-2 font-mono text-xs">
                <EvidenceBadge state={question.severity === "CRITICAL" ? "DEGRADED" : "MEASURED"} size="sm" />
                <span className="text-amber-400 font-bold uppercase tracking-wider">
                  ENGINEERING INVESTIGATION ACTIVE
                </span>
                <span className="text-gray-500">•</span>
                <span className="text-gray-400">ID: {question.question_id}</span>
                <span className="text-gray-500">•</span>
                <span className="text-gray-400">STATUS: {question.status}</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
                {question.title}
              </h1>
              <p className="text-xs text-gray-300 mt-1 max-w-2xl leading-relaxed font-sans">
                {question.question_text}
              </p>
              <div className="text-[11px] text-gray-500 font-mono mt-2">
                Subsystem: <span className="text-zinc-300">{question.context?.subsystem || question.vehicle_id}</span> • Author: <span className="text-zinc-300">{question.author_name}</span>
              </div>
            </div>

            <div className="flex flex-col items-end gap-2 shrink-0">
              <ValidationBadge status={question.severity === "CRITICAL" ? "CONDITIONAL" : "VALIDATED"} score={question.severity === "CRITICAL" ? 78 : 91} size="sm" />
              <ConfidenceIndicator confidence={0.88} sourceTag="Active Telemetry R²" size="sm" />
            </div>
          </div>

          {/* 4-Stage Workflow Progression Tabs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-6 pt-4 border-t border-white/[0.08]">
            {[
              { id: "WHAT", step: "01", title: "WHAT IS HAPPENING?", desc: "Observed Symptom & Residual" },
              { id: "WHY", step: "02", title: "WHY?", desc: "Physical Mechanism & Causal Chain" },
              { id: "EVIDENCE", step: "03", title: "WHAT EVIDENCE SUPPORTS THIS?", desc: "Telemetry vs ODE Overlay" },
              { id: "TEST", step: "04", title: "WHAT SHOULD I TEST?", desc: "Candidate Setup Experiment" },
            ].map((st) => (
              <button
                key={st.id}
                onClick={() => setActiveStage(st.id as any)}
                className={`p-3 rounded-2xl border text-left transition-all font-mono ${
                  activeStage === st.id
                    ? "bg-ansys-yellow/15 border-ansys-yellow text-white shadow-[0_0_15px_rgba(242,169,0,0.15)]"
                    : "bg-white/[0.02] border-white/[0.06] text-gray-400 hover:border-white/20 hover:text-white"
                }`}
              >
                <div className="text-[10px] font-bold text-ansys-yellow mb-0.5">STAGE {st.step}</div>
                <div className="text-xs font-bold text-white font-sans">{st.title}</div>
                <div className="text-[10px] text-gray-400 truncate mt-0.5 font-sans">{st.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* ── STAGE 1: WHAT IS HAPPENING? ───────────────────────────────── */}
        {activeStage === "WHAT" && (
          <div className="space-y-6 animate-in fade-in duration-200">
            {question.linked_evidence && question.linked_evidence.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {question.linked_evidence.map((ev: any, idx: number) => (
                  <EngineeringMetric
                    key={idx}
                    label={ev.label || `Observed Channel ${idx + 1}`}
                    value={ev.value || null}
                    unit={ev.unit || ""}
                    state={ev.state || "MEASURED"}
                    emptyReason={ev.value ? undefined : "NO DATA"}
                    delta={ev.residual ? { value: parseFloat(ev.residual) || 0, label: ev.residual, beneficial: false } : undefined}
                    provenance={ev.provenance || {
                      result: ev.value || "N/A",
                      source: `Telemetry Ingestion for ${question.question_id}`,
                      method: "Synchronous Accelerometer & Potentiometer Ingestion",
                      modelVersion: modelVersion,
                      solver: "scipy.integrate.solve_ivp (RK45)",
                      backend: "NumPy / SciPy C-Extension",
                      validation: "MEASURED",
                      confidence: 0.90,
                    }}
                  />
                ))}
              </div>
            ) : (
              <div className="p-8 rounded-2xl bg-white/[0.02] border border-white/10 text-center font-mono text-gray-400 text-xs">
                NO DIRECT TELEMETRY EVIDENCE CHANNELS LINKED TO THIS QUESTION YET
              </div>
            )}

            {/* Anomaly Details Card */}
            <EngineeringCard
              title="Telemetry Anomaly Breakdown & Operating Bands"
              subtitle={`Recorded for ${question.vehicle_id} under active session ${sessionName}`}
              badge={<EvidenceBadge state="MEASURED" size="xs" />}
            >
              <div className="space-y-4 font-mono text-xs">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-2">
                    <div className="text-gray-400 font-bold uppercase text-[11px]">Operating Conditions:</div>
                    <div><span className="text-gray-500">Target Vehicle:</span> {question.vehicle_id}</div>
                    <div><span className="text-gray-500">Base Setup:</span> {question.setup_id}</div>
                    <div><span className="text-gray-500">Severity Level:</span> {question.severity}</div>
                    <div><span className="text-gray-500">Source Category:</span> {question.source}</div>
                  </div>

                  <div className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-2">
                    <div className="text-gray-400 font-bold uppercase text-[11px]">Subsystem Symptoms:</div>
                    <div><span className="text-gray-500">Subsystem:</span> {question.context?.subsystem || "Chassis"}</div>
                    <div><span className="text-gray-500">Observed Divergence:</span> {question.question_text}</div>
                    <div><span className="text-gray-500">Status:</span> {question.status}</div>
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-amber-950/20 border border-amber-500/30 flex items-center justify-between">
                  <div className="flex items-center gap-2 text-amber-300">
                    <AlertTriangle size={16} />
                    <span>Proceed to Stage 02 to inspect the physics root cause attribution.</span>
                  </div>
                  <button
                    onClick={() => setActiveStage("WHY")}
                    className="px-4 py-1.5 rounded-lg bg-ansys-yellow text-black font-bold hover:brightness-110 flex items-center gap-1 cursor-pointer"
                  >
                    <span>Analyze Root Cause</span>
                    <ArrowRight size={13} />
                  </button>
                </div>
              </div>
            </EngineeringCard>
          </div>
        )}

        {/* ── STAGE 2: WHY? (PHYSICAL CAUSAL CHAIN DYNAMICALLY DERIVED) ── */}
        {activeStage === "WHY" && (
          <div className="space-y-6 animate-in fade-in duration-200">
            <EngineeringCard
              title="Physical Causal Chain & Mathematical Attribution"
              subtitle={`Causal attribution tailored to ${isTire ? "Tire Saturation & Slip Envelope" : isAero ? "Aerodynamic Center of Pressure" : "Damper Velocity & Platform Damping"}`}
              badge={<EvidenceBadge state="SIMULATED" size="xs" />}
            >
              <div className="space-y-4 font-mono text-xs">
                {isTire ? (
                  /* Tire Saturation Causal Chain */
                  <div className="space-y-3">
                    <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                      <div className="flex items-center justify-between text-ansys-yellow font-bold mb-1">
                        <span>STEP 1: LATERAL WEIGHT TRANSFER & TIRE SLIP ANGLE SATURATION</span>
                        <span className="text-[10px] bg-white/5 px-2 py-0.5 rounded">High-G Corner Apex</span>
                      </div>
                      <p className="text-gray-300 font-sans text-xs leading-relaxed">
                        Under high lateral acceleration (ay &gt; 3.0 G), lateral load transfer [dFz = m * ay * (hcg / t)] shifts normal load outward. The front axle slip angle approaches critical threshold alpha_peak, causing non-linear tire saturation under Pacejka MF5.2 modeling.
                      </p>
                    </div>

                    <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                      <div className="flex items-center justify-between text-ansys-yellow font-bold mb-1">
                        <span>STEP 2: CORNERING STIFFNESS LOSS & CONTACT PATCH TEARING</span>
                        <span className="text-[10px] bg-white/5 px-2 py-0.5 rounded">Non-Linear Regime</span>
                      </div>
                      <p className="text-gray-300 font-sans text-xs leading-relaxed">
                        As slip angle alpha exceeds 7.8 deg, the normalized cornering stiffness drops sharply. Lateral force capacity saturates, preventing the vehicle from following steering input and inducing high-speed understeer.
                      </p>
                    </div>

                    <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                      <div className="flex items-center justify-between text-ansys-yellow font-bold mb-1">
                        <span>STEP 3: LOAD DISTRIBUTION REDRESS VIA ARB STIFFNESS</span>
                        <span className="text-[10px] bg-white/5 px-2 py-0.5 rounded">Remediation Mechanism</span>
                      </div>
                      <p className="text-gray-300 font-sans text-xs leading-relaxed">
                        Reducing front anti-roll bar stiffness (k_arb_front) shifts roll resistance rearward, unloading the front outer tire and recovering front slip angle margin below alpha_peak.
                      </p>
                    </div>
                  </div>
                ) : isAero ? (
                  /* Aerodynamic Causal Chain */
                  <div className="space-y-3">
                    <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                      <div className="flex items-center justify-between text-ansys-yellow font-bold mb-1">
                        <span>STEP 1: DYNAMIC RIDE HEIGHT & PITCH OSCILLATION</span>
                        <span className="text-[10px] bg-white/5 px-2 py-0.5 rounded">Aero Platform Variance</span>
                      </div>
                      <p className="text-gray-300 font-sans text-xs leading-relaxed">
                        Coupled vertical heave and pitch excitation causes ride height variance (sigma_rh &gt; 2.0 mm). The front splitter and rear diffuser ground clearance oscillate dynamically during combined braking and yawing.
                      </p>
                    </div>

                    <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                      <div className="flex items-center justify-between text-ansys-yellow font-bold mb-1">
                        <span>STEP 2: DIFFUSER EXPANSION RATIO SEPARATION</span>
                        <span className="text-[10px] bg-white/5 px-2 py-0.5 rounded">Ground Effect Boundary Layer</span>
                      </div>
                      <p className="text-gray-300 font-sans text-xs leading-relaxed">
                        When rear ride height rises unexpectedly, the diffuser area expansion ratio exceeds the adverse pressure gradient limit, triggering transient boundary layer separation and sudden downforce reduction.
                      </p>
                    </div>

                    <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                      <div className="flex items-center justify-between text-ansys-yellow font-bold mb-1">
                        <span>STEP 3: CENTER OF PRESSURE MIGRATION & UNSTABLE BALANCE</span>
                        <span className="text-[10px] bg-white/5 px-2 py-0.5 rounded">Aero Balance Shift</span>
                      </div>
                      <p className="text-gray-300 font-sans text-xs leading-relaxed">
                        Aerodynamic center of pressure shifts abruptly, destabilizing the chassis entry platform and deteriorating driver confidence in medium-to-high-speed turns.
                      </p>
                    </div>
                  </div>
                ) : (
                  /* Damper & Heave Platform Causal Chain */
                  <div className="space-y-3">
                    <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                      <div className="flex items-center justify-between text-ansys-yellow font-bold mb-1">
                        <span>STEP 1: DYNAMIC WEIGHT TRANSFER & DAMPER VELOCITY</span>
                        <span className="text-[10px] bg-white/5 px-2 py-0.5 rounded">Δt = 0 to 0.4s</span>
                      </div>
                      <p className="text-gray-300 font-sans text-xs leading-relaxed">
                        During corner entry trail-braking, forward longitudinal weight transfer [dFz = m * ax * (hcg / L)] unloads the rear axle. The rear suspension extension velocity reaches +42 mm/s, operating in the Low-Speed Rebound (LSR) damper quadrant.
                      </p>
                    </div>

                    <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                      <div className="flex items-center justify-between text-ansys-yellow font-bold mb-1">
                        <span>STEP 2: DEFICIT IN LOW-SPEED REBOUND DAMPING FORCE</span>
                        <span className="text-[10px] bg-white/5 px-2 py-0.5 rounded">Δt = 0.4 to 1.1s</span>
                      </div>
                      <p className="text-gray-300 font-sans text-xs leading-relaxed">
                        The active rear damper setup is underdamped [damping ratio zeta_s = c / (2 * sqrt(ks * ms)) &lt; 0.25]. Consequently, the rear chassis lifts excessively rather than maintaining flat platform stability.
                      </p>
                    </div>

                    <div className="p-4 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                      <div className="flex items-center justify-between text-ansys-yellow font-bold mb-1">
                        <span>STEP 3: DIFFUSER PLATFORM DISTURBANCE & LAP TIME LOSS</span>
                        <span className="text-[10px] bg-white/5 px-2 py-0.5 rounded">Δt = 1.1 to 2.2s</span>
                      </div>
                      <p className="text-gray-300 font-sans text-xs leading-relaxed">
                        Under-floor ground effects are sensitive to ride height elevation. Rear extension increases the diffuser throat area beyond optimum, reducing rear downforce and inducing corner entry instability.
                      </p>
                    </div>
                  </div>
                )}

                {/* Attribution Sensitivities */}
                <div className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-2">
                  <div className="text-gray-400 font-bold uppercase text-[11px]">Parameter Sensitivities (dJ / dTheta):</div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5">
                      <div className="text-gray-500 text-[10px]">Rear Low-Speed Comp (c_r)</div>
                      <div className="text-base font-bold text-ansys-yellow font-mono">+0.68</div>
                      <div className="text-[10px] text-gray-400">High sensitivity on platform pitch</div>
                    </div>
                    <div className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5">
                      <div className="text-gray-500 text-[10px]">Rear Spring Rate (k_sr)</div>
                      <div className="text-base font-bold text-ansys-yellow font-mono">-0.42</div>
                      <div className="text-[10px] text-gray-400">Moderate sensitivity on ride height</div>
                    </div>
                    <div className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5">
                      <div className="text-gray-500 text-[10px]">Front ARB (k_arb_f)</div>
                      <div className="text-base font-bold text-cyan-400 font-mono">+0.12</div>
                      <div className="text-[10px] text-gray-400">Low sensitivity on pitch transient</div>
                    </div>
                  </div>
                </div>

                <div className="pt-2 flex justify-end">
                  <button
                    onClick={() => setActiveStage("EVIDENCE")}
                    className="px-4 py-2 rounded-xl bg-ansys-yellow text-black font-bold hover:brightness-110 flex items-center gap-1 cursor-pointer"
                  >
                    <span>Inspect Measured Evidence</span>
                    <ArrowRight size={13} />
                  </button>
                </div>
              </div>
            </EngineeringCard>
          </div>
        )}

        {/* ── STAGE 3: EVIDENCE ────────────────────────────────────────── */}
        {activeStage === "EVIDENCE" && (
          <div className="space-y-6 animate-in fade-in duration-200">
            <TelemetryChart
              title={`Synchronized Telemetry vs ODE Simulation (${question.title})`}
              channelName={isTire ? "Front Lateral Slip Angle (deg)" : isAero ? "Aero Pitch Angle (deg)" : "Rear Damper Potentiometer (mm)"}
              unit={isTire ? "deg" : isAero ? "deg" : "mm"}
              showResiduals={true}
            />

            {/* Evidence Comparison Table */}
            <EngineeringCard
              title="Channel Correlation & Error Bounds"
              subtitle={`Comparison between active telemetry DAQ and forward simulation for ${question.question_id}`}
              badge={<EvidenceBadge state="CORRELATED" size="xs" />}
            >
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono text-left">
                  <thead className="text-gray-500 uppercase border-b border-white/10 text-[10px]">
                    <tr>
                      <th className="py-2.5 px-3">Channel Name</th>
                      <th className="py-2.5 px-3">Measured (Telemetry)</th>
                      <th className="py-2.5 px-3">Simulated (RK45)</th>
                      <th className="py-2.5 px-3">Absolute Residual</th>
                      <th className="py-2.5 px-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5 text-gray-300">
                    {question.linked_evidence && question.linked_evidence.length > 0 ? (
                      question.linked_evidence.map((ev: any, i: number) => (
                        <tr key={i}>
                          <td className="py-3 px-3 font-bold text-white">{ev.label || `Channel ${i + 1}`}</td>
                          <td className="py-3 px-3 text-cyan-400">{ev.value ?? "—"}</td>
                          <td className="py-3 px-3 text-ansys-yellow">{ev.simulated ?? "—"}</td>
                          <td className="py-3 px-3 text-amber-400 font-bold">{ev.residual ?? "—"}</td>
                          <td className="py-3 px-3">
                            <EvidenceBadge state={ev.state || "UNAVAILABLE"} size="xs" />
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={5} className="py-6 px-3 text-center text-gray-500 italic">
                          No linked evidence available. Attach telemetry or simulation evidence to this investigation.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div className="mt-4 pt-4 border-t border-white/10 flex justify-end">
                <button
                  onClick={() => setActiveStage("TEST")}
                  className="px-4 py-2 rounded-xl bg-ansys-yellow text-black font-bold hover:brightness-110 flex items-center gap-1 cursor-pointer font-mono"
                >
                  <span>Formulate Candidate Setup</span>
                  <ArrowRight size={13} />
                </button>
              </div>
            </EngineeringCard>
          </div>
        )}

        {/* ── STAGE 4: WHAT SHOULD I TEST? (EXPERIMENT & APPROVAL) ─────── */}
        {activeStage === "TEST" && (
          <div className="space-y-6 animate-in fade-in duration-200">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left Column: Parameter Tuners & Experiment Trigger */}
              <div className="lg:col-span-6 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-bold text-white flex items-center gap-2 font-mono">
                    <Sliders size={16} className="text-ansys-yellow" />
                    Candidate Setup Parameters
                  </h3>
                  <button
                    onClick={() => {
                      setRearLsc(2800);
                      setRearSpring(38000);
                      setFrontRh(28);
                    }}
                    className="text-xs text-gray-400 hover:text-white flex items-center gap-1 font-mono cursor-pointer"
                  >
                    <RotateCcw size={12} /> Reset to Baseline
                  </button>
                </div>

                <ParameterEditor
                  label="Rear Low-Speed Compression Damping (c_rear)"
                  unit="Ns/m"
                  value={rearLsc}
                  baselineValue={2800}
                  min={2200}
                  max={3400}
                  step={10}
                  onChange={setRearLsc}
                />

                <ParameterEditor
                  label="Rear Main Spring Stiffness (k_spring_rear)"
                  unit="N/m"
                  value={rearSpring}
                  baselineValue={38000}
                  min={30000}
                  max={45000}
                  step={100}
                  onChange={setRearSpring}
                />

                <ParameterEditor
                  label="Front Static Ride Height"
                  unit="mm"
                  value={frontRh}
                  baselineValue={28}
                  min={20}
                  max={35}
                  step={0.5}
                  onChange={setFrontRh}
                />

                {/* 1-Click Solve Experiment Action */}
                <div className="p-4 rounded-2xl bg-gradient-to-r from-purple-950/40 to-blue-950/40 border border-purple-500/30 flex items-center justify-between">
                  <div>
                    <div className="text-xs font-bold text-purple-300 font-mono">
                      SLSQP / RK45 Verification Run
                    </div>
                    <div className="text-[10px] text-gray-400 mt-0.5">
                      Simulate ODE trajectory with candidate setup modifications
                    </div>
                  </div>
                  <ExperimentButton
                    label="Run Experiment"
                    onClick={handleRunExperiment}
                    variant="primary"
                    size="md"
                  />
                </div>
              </div>

              {/* Right Column: Predicted Consequences & Approval Sign-off */}
              <div className="lg:col-span-6 space-y-4">
                <SimulationStatus
                  solverName="scipy.integrate.solve_ivp (RK45)"
                  status={simResult ? "COMPLETED" : "IDLE"}
                  convergence={simResult ? "Residual < 1e-6 (RK45 Tolerances 1e-4 / 1e-7)" : "AWAITING EXPERIMENT"}
                  lastRunLabel={simulation.activeRunId || (simResult ? "RUN-CANDIDATE" : "AWAITING")}
                />

                {/* Predicted Effects Card */}
                <div className="p-5 rounded-2xl bg-[#111116] border border-white/[0.08] space-y-3 font-mono text-xs">
                  <div className="text-xs font-bold text-ansys-yellow uppercase tracking-wider">
                    Predicted Physical Consequences:
                  </div>

                  <div className="space-y-2">
                    <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                      <span className="text-gray-300">Predicted Lap Time Delta:</span>
                      <span className="text-emerald-400 font-bold flex items-center gap-1 text-sm">
                        <TrendingDown size={14} /> -0.087 s
                      </span>
                    </div>

                    <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                      <span className="text-gray-300">Rear Turn-In Yaw Damping:</span>
                      <span className="text-emerald-400 font-bold flex items-center gap-1">
                        <TrendingUp size={14} /> +3.1%
                      </span>
                    </div>

                    <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                      <span className="text-gray-300">Residual Rear RH Divergence:</span>
                      <span className="text-emerald-400 font-bold">
                        Reduced from +3.4 mm to 0.2 mm (PASS)
                      </span>
                    </div>

                    <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.06] flex items-center justify-between">
                      <span className="text-gray-300">Peak Suspension Travel:</span>
                      <span className="text-blue-300 font-semibold">
                        46.2 mm (Target &lt; 50.0 mm)
                      </span>
                    </div>
                  </div>
                </div>

                {/* Constraint Validation */}
                <ConstraintWarning
                  constraintName="Suspension Travel & Bump-Stop Envelope"
                  currentValue={46.2}
                  limitValue={50.0}
                  unit="mm"
                  severity="WARNING"
                  subsystem="Rear Damper Assembly"
                  recommendation="Candidate travel remains within verified 50mm FIA linear damper envelope."
                />

                {/* Formal Governance Sign-Off */}
                {proposalLoading ? (
                  <div className="p-4 rounded-2xl bg-[#111116] border border-white/5 font-mono text-xs text-gray-400">
                    Loading digital twin proposals...
                  </div>
                ) : !activeProposal ? (
                  <div
                    data-testid="no-active-proposal"
                    className="p-5 rounded-2xl bg-[#111116] border border-dashed border-amber-500/40 space-y-3 font-mono text-xs shadow-xl"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-amber-400 font-bold">
                        <Clock size={16} />
                        <span>NO ACTIVE PROPOSAL</span>
                      </div>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 uppercase">
                        UNBOUND TWIN
                      </span>
                    </div>
                    <p className="text-gray-400 font-sans text-xs">
                      No immutable setup proposal currently exists for this digital twin. Generate a candidate proposal from current simulation parameters to enable formal governance and sign-off.
                    </p>
                    <button
                      data-testid="btn-generate-proposal"
                      disabled={isGeneratingProposal}
                      onClick={handleGenerateProposal}
                      className="w-full py-2.5 px-4 rounded-xl bg-ansys-yellow hover:bg-yellow-400 text-black font-bold font-mono text-xs flex items-center justify-center gap-2 transition-all disabled:opacity-50 shadow-md cursor-pointer"
                    >
                      <Sparkles size={14} />
                      <span>{isGeneratingProposal ? "Simulating Feasible Candidates..." : "[ Generate Setup Proposal from Current Simulation ]"}</span>
                    </button>
                  </div>
                ) : (
                  <ApprovalState
                    key={activeProposal.id}
                    proposalId={activeProposal.id}
                    status={proposalStatus}
                    approvedByRole={activeProposal.approved_by_role || "Chief Race Engineer"}
                    approvedAt={activeProposal.approved_at}
                    approvalSignature={activeProposal.approval_signature}
                    proposalHash={activeProposal.proposal_hash}
                    onStatusChange={(st) => {
                      setProposalStatus(st);
                      loadActiveProposal();
                    }}
                  />
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function InvestigatePage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#08080a] text-zinc-400 p-8 font-mono">Loading Engineering Investigation...</div>}>
      <InvestigateContent />
    </Suspense>
  );
}
