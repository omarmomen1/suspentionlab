"use client";

import React, { useState, useEffect } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  Lock,
  Eye,
  Send,
  AlertCircle,
  Clock,
  KeyRound,
  FileCheck2,
  Unlock,
  CheckCircle2,
  Scale,
} from "lucide-react";
import {
  BlindEngineeringApi,
  BlindSessionDTO,
  VisibleContextDTO,
  BlindSubmissionDTO,
  BlindComparisonDTO,
  RevealedOutcomeDTO,
  PredictionContractPayload,
  PredictionType,
  ExpectedDirection,
} from "../../lib/api_client";

interface BlindSessionViewProps {
  sessionId?: string;
  onSessionLoaded?: (session: BlindSessionDTO) => void;
}

export function BlindSessionView({ sessionId, onSessionLoaded }: BlindSessionViewProps) {
  const [session, setSession] = useState<BlindSessionDTO | null>(null);
  const [context, setContext] = useState<VisibleContextDTO | null>(null);
  const [submission, setSubmission] = useState<BlindSubmissionDTO | null>(null);
  const [comparison, setComparison] = useState<BlindComparisonDTO | null>(null);
  const [revealedOutcome, setRevealedOutcome] = useState<RevealedOutcomeDTO | null>(null);
  const [revealing, setRevealing] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Versioned Prediction Contract State (Phase 5.2)
  const [predictionType, setPredictionType] = useState<PredictionType>("ENGINEERING_DECISION");
  const [targetEntityType, setTargetEntityType] = useState<string>("");
  const [targetEntityId, setTargetEntityId] = useState<string>("");
  const [targetMetric, setTargetMetric] = useState<string>("bar_rate");
  const [targetAggregation, setTargetAggregation] = useState<string>("");

  const [selectedCandidateId, setSelectedCandidateId] = useState<string>("SETUP-B");
  const [predictedValue, setPredictedValue] = useState<string>("140.0");
  const [unit, setUnit] = useState<string>("N/m");
  const [predictedCategory, setPredictedCategory] = useState<string>("SETUP-B");
  const [expectedDirection, setExpectedDirection] = useState<ExpectedDirection>("INCREASE");
  const [expectedDelta, setExpectedDelta] = useState<string>("0.2");
  const [confidence, setConfidence] = useState<string>("0.95");
  const [rationaleInput, setRationaleInput] = useState<string>("");
  const [assumptionsInput, setAssumptionsInput] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);

  useEffect(() => {
    if (!sessionId) return;
    loadSessionData(sessionId);
  }, [sessionId]);

  const loadSessionData = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const sess = await BlindEngineeringApi.getSession(id);
      setSession(sess);
      if (onSessionLoaded) onSessionLoaded(sess);

      // Default target fields from session root
      if (!targetEntityType) setTargetEntityType(sess.root_entity_type);
      if (!targetEntityId) setTargetEntityId(sess.root_entity_id);

      // Load visible context if permitted
      try {
        const ctx = await BlindEngineeringApi.getVisibleContext(id);
        setContext(ctx);
      } catch (e: any) {
        // Context might not be accessible in draft/armed or if aborted
      }

      // Load revealed outcome & comparison if session has been legitimately revealed
      if (sess.status === "REVEALED" || sess.status === "COMPLETED") {
        try {
          const comp = await BlindEngineeringApi.getComparison(id);
          setComparison(comp);
        } catch (e: any) {}
        try {
          const rev = await BlindEngineeringApi.getReveal(id);
          setRevealedOutcome(rev);
        } catch (e: any) {}
      } else {
        setComparison(null);
        setRevealedOutcome(null);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load blind engineering session.");
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteReveal = async () => {
    if (!sessionId) return;
    setRevealing(true);
    setError(null);
    try {
      const comp = await BlindEngineeringApi.revealSession(sessionId);
      setComparison(comp);
      await loadSessionData(sessionId);
    } catch (err: any) {
      setError(err?.message || "Failed to execute controlled reveal.");
    } finally {
      setRevealing(false);
    }
  };

  const handleSubmitPrediction = async () => {
    if (!session || !sessionId) return;

    setSubmitting(true);
    setError(null);
    try {
      const confNum = parseFloat(confidence);
      if (isNaN(confNum) || confNum < 0.0 || confNum > 1.0) {
        throw new Error("Confidence must be a finite number between 0.0 and 1.0.");
      }

      const effectiveEntityType = targetEntityType || session.root_entity_type;
      const effectiveEntityId = targetEntityId || session.root_entity_id;
      if (!effectiveEntityType || !effectiveEntityId || !targetMetric.trim()) {
        throw new Error("Target requires valid entity_type, entity_id, and metric.");
      }

      const payload: PredictionContractPayload = {
        schema_version: "1",
        prediction_type: predictionType,
        target: {
          entity_type: effectiveEntityType,
          entity_id: effectiveEntityId,
          metric: targetMetric.trim(),
          aggregation: targetAggregation.trim() || undefined,
        },
        confidence: confNum,
        rationale: rationaleInput.trim() || undefined,
        assumptions: assumptionsInput.trim()
          ? assumptionsInput.split("\n").map((s) => s.trim()).filter(Boolean)
          : undefined,
        visible_context_hash: context?.visible_context_hash || undefined,
      };

      if (predictionType === "QUANTITATIVE") {
        const val = parseFloat(predictedValue);
        if (isNaN(val) || !isFinite(val)) {
          throw new Error("Quantitative prediction requires a finite numeric predicted_value.");
        }
        if (!unit.trim()) {
          throw new Error("Quantitative prediction requires a physical unit.");
        }
        payload.predicted_value = val;
        payload.unit = unit.trim();
      } else if (predictionType === "ENGINEERING_DECISION") {
        if (!selectedCandidateId.trim()) {
          throw new Error("Engineering decision requires a selected_candidate_id.");
        }
        payload.selected_candidate_id = selectedCandidateId.trim();
      } else if (predictionType === "DIRECTIONAL") {
        payload.expected_direction = expectedDirection;
        if (expectedDelta.trim()) {
          const delta = parseFloat(expectedDelta);
          if (!isNaN(delta) && isFinite(delta)) {
            payload.expected_delta = delta;
            if (unit.trim()) payload.unit = unit.trim();
          }
        }
      } else if (predictionType === "CATEGORICAL") {
        if (!predictedCategory.trim()) {
          throw new Error("Categorical prediction requires predicted_category.");
        }
        payload.predicted_category = predictedCategory.trim();
      }

      const res = await BlindEngineeringApi.lockSubmission(sessionId, payload);
      setSubmission(res);
      // Reload session to reflect SUBMISSION_LOCKED state
      await loadSessionData(sessionId);
    } catch (err: any) {
      setError(err?.message || "Failed to submit prediction.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="p-6 rounded-lg bg-gray-900 border border-gray-800 text-gray-300 animate-pulse flex items-center space-x-3">
        <Clock className="w-5 h-5 text-indigo-400 animate-spin" />
        <span>Loading blind session boundary...</span>
      </div>
    );
  }

  if (error && !session) {
    return (
      <div className="p-6 rounded-lg bg-red-950/40 border border-red-800/60 text-red-200 flex items-center space-x-3">
        <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
        <div>
          <h4 className="font-semibold">Access Notice</h4>
          <p className="text-sm text-red-300">{error}</p>
        </div>
      </div>
    );
  }

  if (!session) {
    return null;
  }

  const isLocked = session.status === "SUBMISSION_LOCKED" || session.status === "READY_FOR_REVEAL" || session.has_submission;
  const isBlindActive = session.status === "BLIND_ACTIVE";

  return (
    <div className="space-y-6 bg-gray-950 p-6 rounded-xl border border-gray-800">
      {/* ── HEADER & FIREWALL STATE INDICATOR ── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-gray-800 gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <ShieldAlert className="w-6 h-6 text-amber-400" />
            <h2 className="text-xl font-bold text-white tracking-wide">{session.name}</h2>
          </div>
          <p className="text-xs text-gray-400 mt-1 font-sans leading-relaxed">
            SESSION HASH: {session.session_hash.substring(0, 16)}...
          </p>
        </div>

        {/* State Badge */}
        <div className="flex items-center space-x-3">
          <span
            data-testid="blind-state-badge"
            className={`px-3 py-1 text-xs font-semibold rounded-full border ${
              isLocked
                ? "bg-emerald-950/60 text-emerald-300 border-emerald-800/60"
                : isBlindActive
                ? "bg-amber-950/60 text-amber-300 border-amber-800/60 animate-pulse"
                : "bg-gray-800 text-gray-300 border-gray-700"
            }`}
          >
            {session.status}
          </span>
          <span className="px-2.5 py-1 text-xs font-mono rounded bg-gray-900 border border-gray-800 text-gray-400">
            ROOT: {session.root_entity_type} ({session.root_entity_id})
          </span>
        </div>
      </div>

      {/* ── INFORMATION FIREWALL BANNER ── */}
      <div className="p-4 rounded-lg bg-gray-900/80 border border-amber-900/50 flex items-start space-x-3">
        <ShieldCheck className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div className="text-xs text-gray-300 space-y-1">
          <span className="font-semibold text-amber-300">INFORMATION FIREWALL ACTIVE:</span> Withheld outcome remains
          strictly hidden until submission lock boundary is finalized and immutable. No outcome data is transmitted to
          evaluator runtime or client state.
        </div>
      </div>

      {/* ── VISIBLE CONTEXT VIEWER ── */}
      {context && (
        <div className="p-5 rounded-lg bg-gray-900 border border-gray-800 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2 text-sm font-semibold text-gray-200">
              <Eye className="w-4 h-4 text-indigo-400" />
              <span>Evaluator Visible Context</span>
            </div>
            <span className="text-xs font-mono text-zinc-400">
              CTX HASH: {context.visible_context_hash.substring(0, 16)}...
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
            {/* Root Entity Fields */}
            <div className="p-3 bg-gray-950 rounded border border-gray-800">
              <span className="text-gray-400 uppercase tracking-wider block mb-2 font-bold">
                Root Entity Allowed Inputs
              </span>
              <pre className="text-gray-300 overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(context.root_entity, null, 2)}
              </pre>
            </div>

            {/* Allowed Upstream/Downstream Evidence */}
            <div className="p-3 bg-gray-950 rounded border border-gray-800">
              <span className="text-gray-400 uppercase tracking-wider block mb-2 font-bold">
                Permitted Evidence Nodes ({context.visible_entities.length})
              </span>
              {context.visible_entities.length === 0 ? (
                <span className="text-zinc-400 italic">No additional evidence attached.</span>
              ) : (
                <ul className="space-y-1.5 text-gray-300">
                  {context.visible_entities.map((ent, idx) => (
                    <li key={idx} className="truncate">
                      • <span className="text-indigo-300">{ent.entity_type}</span>: {ent.entity_id}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── SUBMISSION BOUNDARY ── */}
      {isLocked ? (
        <>
          {/* LOCKED STATE DISPLAY */}
          <div className="p-5 rounded-lg bg-emerald-950/30 border border-emerald-800/60 space-y-3">
            <div className="flex items-center space-x-2 text-emerald-300 font-semibold">
              <Lock className="w-5 h-5 text-emerald-400" />
              <span>SUBMISSION LOCKED & IMMUTABLE</span>
            </div>
            <p className="text-xs text-gray-300">
              The prediction boundary is cryptographically sealed. Edits, deletions, or duplicate submissions are strictly
              prohibited.
            </p>
            <div className="text-xs font-mono text-gray-400 space-y-1 bg-gray-950 p-3 rounded border border-gray-800">
              <div>SUBMISSION HASH: {session.submission_hash || submission?.submission_hash || "VERIFIED"}</div>
              {session.locked_at && <div>LOCKED AT: {session.locked_at}</div>}
              {session.visible_context_hash && <div>CONTEXT SNAPSHOT HASH: {session.visible_context_hash}</div>}
            </div>
          </div>

          {/* ── REVEAL BOUNDARY (READY_FOR_REVEAL) ── */}
          {session.status === "READY_FOR_REVEAL" && (
            <div className="p-5 rounded-lg bg-amber-950/30 border border-amber-800/60 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2 text-amber-300 font-semibold">
                  <Unlock className="w-5 h-5 text-amber-400" />
                  <span>AWAITING CONTROLLED REVEAL</span>
                </div>
                <button
                  onClick={handleExecuteReveal}
                  disabled={revealing}
                  className="px-4 py-2 text-xs font-semibold rounded bg-signal hover:bg-[#d6f56e] text-carbon flex items-center space-x-2 disabled:opacity-50"
                >
                  <Unlock className="w-3.5 h-3.5" />
                  <span>{revealing ? "Executing Reveal..." : "Execute Controlled Reveal"}</span>
                </button>
              </div>
              <p className="text-xs text-gray-300">
                Prediction is sealed. Revealing the withheld engineering outcome will snapshot its identity and compute deterministic comparison under Comparison Policy v1.
              </p>
            </div>
          )}

          {/* ── REVEALED OUTCOME & PREDICTION COMPARISON (PHASE 5.3) ── */}
          {(session.status === "REVEALED" || session.status === "COMPLETED") && comparison && (
            <div data-testid="blind-comparison-section" className="p-5 rounded-lg bg-gray-900 border border-indigo-900/60 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-gray-800 gap-2">
                <div className="flex items-center space-x-2">
                  <Scale className="w-5 h-5 text-indigo-400" />
                  <h3 className="text-base font-bold text-white">Prediction vs Authoritative Outcome Comparison</h3>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-xs font-mono text-gray-400">POLICY: v{comparison.comparison_policy_version}</span>
                  <span
                    data-testid="comparison-verdict-badge"
                    className={`px-3 py-1 text-xs font-bold rounded border ${
                      comparison.verdict === "WITHIN_TOLERANCE" || comparison.verdict === "CORRECT" || comparison.verdict === "CORRECT_DIRECTION" || comparison.verdict === "SUPPORTED"
                        ? "bg-emerald-950/80 text-emerald-300 border-emerald-800"
                        : comparison.verdict === "METRICS_ONLY"
                        ? "bg-blue-950/80 text-blue-300 border-blue-800"
                        : comparison.verdict === "UNCOMPARABLE"
                        ? "bg-gray-800 text-gray-300 border-gray-700"
                        : "bg-red-950/80 text-red-300 border-red-800"
                    }`}
                  >
                    {comparison.verdict}
                  </span>
                </div>
              </div>

              {/* Comparison Explanation */}
              <div className="p-3.5 bg-gray-950 rounded border border-gray-800 text-xs text-gray-200">
                <span className="font-semibold text-indigo-300 block mb-1">Explainable Evaluation:</span>
                {comparison.interpretation}
              </div>

              {/* Side-by-Side: Prediction vs Revealed Outcome */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                {/* Engineer's Prediction */}
                <div className="p-4 bg-gray-950 rounded border border-gray-800 space-y-2">
                  <div className="font-bold text-gray-300 uppercase tracking-wider pb-1 border-b border-gray-800 flex items-center justify-between">
                    <span>Engineer Prediction</span>
                    <span className="text-indigo-400 text-xs">{comparison.comparison_type}</span>
                  </div>
                  {comparison.prediction_payload && (
                    <div className="space-y-1 text-gray-300">
                      <div>Target Metric: <span className="text-indigo-300">{comparison.prediction_payload.target?.metric}</span></div>
                      {comparison.prediction_payload.predicted_value !== undefined && (
                        <div>Predicted Value: <span className="text-white font-bold">{comparison.prediction_payload.predicted_value} {comparison.prediction_payload.unit}</span></div>
                      )}
                      {comparison.prediction_payload.predicted_category && (
                        <div>Predicted Category: <span className="text-white font-bold">{comparison.prediction_payload.predicted_category}</span></div>
                      )}
                      {comparison.prediction_payload.expected_direction && (
                        <div>Expected Direction: <span className="text-white font-bold">{comparison.prediction_payload.expected_direction}</span></div>
                      )}
                      {comparison.prediction_payload.selected_candidate_id && (
                        <div>Selected Candidate: <span className="text-white font-bold">{comparison.prediction_payload.selected_candidate_id}</span></div>
                      )}
                      <div>Confidence: <span className="text-gray-400">{((comparison.prediction_payload.confidence || 0) * 100).toFixed(0)}%</span></div>
                    </div>
                  )}
                </div>

                {/* Authoritative Revealed Outcome */}
                <div className="p-4 bg-gray-950 rounded border border-gray-800 space-y-2">
                  <div className="font-bold text-gray-300 uppercase tracking-wider pb-1 border-b border-gray-800 flex items-center justify-between">
                    <span>Authoritative Outcome</span>
                    <span className="text-emerald-400 text-xs">REVEALED</span>
                  </div>
                  <div className="space-y-1 text-gray-300">
                    <div>Source Entity: <span className="text-emerald-300">{comparison.outcome_identity.entity_type} ({comparison.outcome_identity.entity_id})</span></div>
                    {comparison.comparison_metrics.actual_value !== undefined && (
                      <div>Observed Value: <span className="text-white font-bold">{comparison.comparison_metrics.actual_value} {comparison.comparison_metrics.actual_unit || ""}</span></div>
                    )}
                    {comparison.comparison_metrics.actual_category && (
                      <div>Observed Category: <span className="text-white font-bold">{comparison.comparison_metrics.actual_category}</span></div>
                    )}
                    {comparison.comparison_metrics.actual_direction && (
                      <div>Observed Direction: <span className="text-white font-bold">{comparison.comparison_metrics.actual_direction} (delta: {comparison.comparison_metrics.actual_delta})</span></div>
                    )}
                    {comparison.comparison_metrics.authoritative_choice && (
                      <div>Winning Option: <span className="text-white font-bold">{comparison.comparison_metrics.authoritative_choice}</span></div>
                    )}
                    <div className="truncate text-zinc-400 text-xs">Outcome Hash: {comparison.outcome_identity.artifact_hash}</div>
                  </div>
                </div>
              </div>

              {/* Quantitative Error Metrics if Quantitative */}
              {comparison.comparison_type === "QUANTITATIVE" && (
                <div className="p-3.5 bg-gray-950 rounded border border-gray-800 space-y-2">
                  <span className="font-semibold text-gray-300 text-xs block">Comparative Quantitative Metrics</span>
                  <div className="grid grid-cols-3 gap-3 text-xs font-mono">
                    <div className="p-2 rounded bg-gray-900 border border-gray-800">
                      <div className="text-zinc-400 text-xs">Signed Error</div>
                      <div className="text-white font-bold">{comparison.comparison_metrics.signed_error !== undefined ? Number(comparison.comparison_metrics.signed_error).toFixed(4) : "N/A"} {comparison.comparison_metrics.base_unit || ""}</div>
                    </div>
                    <div className="p-2 rounded bg-gray-900 border border-gray-800">
                      <div className="text-zinc-400 text-xs">Absolute Error</div>
                      <div className="text-white font-bold">{comparison.comparison_metrics.absolute_error !== undefined ? Number(comparison.comparison_metrics.absolute_error).toFixed(4) : "N/A"} {comparison.comparison_metrics.base_unit || ""}</div>
                    </div>
                    <div className="p-2 rounded bg-gray-900 border border-gray-800">
                      <div className="text-zinc-400 text-xs">Relative Error</div>
                      <div className="text-white font-bold">{comparison.comparison_metrics.relative_error !== null && comparison.comparison_metrics.relative_error !== undefined ? `${(Number(comparison.comparison_metrics.relative_error) * 100).toFixed(2)}%` : "N/A"}</div>
                    </div>
                  </div>
                </div>
              )}

              {/* Tolerance & Provenance */}
              <div className="text-xs font-mono text-gray-400 space-y-1 p-3 bg-gray-950 rounded border border-gray-800">
                <div>TOLERANCE EVALUATED: {comparison.tolerance_applied ? JSON.stringify(comparison.tolerance_applied) : "None declared (raw error metrics only)"}</div>
                <div className="truncate">COMPARISON HASH: {comparison.comparison_hash}</div>
                {session.revealed_at && <div>REVEALED AT: {session.revealed_at}</div>}
              </div>
            </div>
          )}
        </>
      ) : isBlindActive ? (
        /* SUBMISSION FORM SHELL */
        <div className="p-5 rounded-lg bg-gray-900 border border-gray-800 space-y-4">
          <div className="flex items-center space-x-2 text-sm font-semibold text-gray-200">
            <KeyRound className="w-4 h-4 text-amber-400" />
            <span>Lock Blind Prediction</span>
          </div>

          <div className="space-y-3">
            {/* Prediction Type Selection */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">
                Prediction Contract Type (Schema v1)
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {(["ENGINEERING_DECISION", "QUANTITATIVE", "DIRECTIONAL", "CATEGORICAL"] as PredictionType[]).map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setPredictionType(t)}
                    className={`px-3 py-1.5 text-xs font-semibold rounded border transition-colors ${
                      predictionType === t
                        ? "bg-indigo-600 text-white border-indigo-500 shadow-sm"
                        : "bg-gray-950 text-gray-400 border-gray-800 hover:border-gray-700 hover:text-gray-200"
                    }`}
                  >
                    {t.replace("_", " ")}
                  </button>
                ))}
              </div>
            </div>

            {/* Target Specification */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-3 bg-gray-950 rounded border border-gray-800">
              <div>
                <label className="block text-xs font-mono text-gray-400 mb-1">
                  Target Entity
                </label>
                <div className="text-xs font-mono text-indigo-300 py-1.5 px-2.5 bg-gray-900 rounded border border-gray-800 truncate">
                  {targetEntityType || session.root_entity_type}: {targetEntityId || session.root_entity_id}
                </div>
              </div>
              <div>
                <label className="block text-xs font-mono text-gray-400 mb-1">
                  Target Metric
                </label>
                <input
                  type="text"
                  value={targetMetric}
                  onChange={(e) => setTargetMetric(e.target.value)}
                  placeholder="e.g. bar_rate, lap_time, roll_stiffness"
                  className="w-full bg-gray-900 border border-gray-800 rounded px-2.5 py-1.5 text-xs font-mono text-gray-200 focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            {/* Type-Specific Value Fields */}
            {predictionType === "ENGINEERING_DECISION" && (
              <div className="space-y-1">
                <label className="block text-xs font-medium text-gray-400 mb-1">
                  Selected Candidate Option
                </label>
                <input
                  type="text"
                  value={selectedCandidateId}
                  onChange={(e) => setSelectedCandidateId(e.target.value)}
                  placeholder="e.g. SETUP-B"
                  className="w-full bg-gray-950 border border-gray-800 rounded p-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500 font-mono"
                />
              </div>
            )}

            {predictionType === "QUANTITATIVE" && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">
                    Predicted Finite Value
                  </label>
                  <input
                    type="number"
                    step="any"
                    value={predictedValue}
                    onChange={(e) => setPredictedValue(e.target.value)}
                    placeholder="e.g. 140.0"
                    className="w-full bg-gray-950 border border-gray-800 rounded p-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">
                    Physical Unit
                  </label>
                  <input
                    type="text"
                    value={unit}
                    onChange={(e) => setUnit(e.target.value)}
                    placeholder="e.g. N/m, N, Nm, m/s, s, %, deg"
                    className="w-full bg-gray-950 border border-gray-800 rounded p-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500 font-mono"
                  />
                </div>
              </div>
            )}

            {predictionType === "DIRECTIONAL" && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">
                    Expected Direction
                  </label>
                  <select
                    value={expectedDirection}
                    onChange={(e) => setExpectedDirection(e.target.value as ExpectedDirection)}
                    className="w-full bg-gray-950 border border-gray-800 rounded p-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="INCREASE">INCREASE</option>
                    <option value="DECREASE">DECREASE</option>
                    <option value="NEUTRAL">NEUTRAL</option>
                    <option value="CONSTANT">CONSTANT</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">
                    Expected Delta (Optional)
                  </label>
                  <input
                    type="number"
                    step="any"
                    value={expectedDelta}
                    onChange={(e) => setExpectedDelta(e.target.value)}
                    placeholder="e.g. 0.2"
                    className="w-full bg-gray-950 border border-gray-800 rounded p-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">
                    Unit (Optional)
                  </label>
                  <input
                    type="text"
                    value={unit}
                    onChange={(e) => setUnit(e.target.value)}
                    placeholder="e.g. g, N/m, s"
                    className="w-full bg-gray-950 border border-gray-800 rounded p-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500 font-mono"
                  />
                </div>
              </div>
            )}

            {predictionType === "CATEGORICAL" && (
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">
                  Predicted Category
                </label>
                <input
                  type="text"
                  value={predictedCategory}
                  onChange={(e) => setPredictedCategory(e.target.value)}
                  placeholder="e.g. SETUP-B"
                  className="w-full bg-gray-950 border border-gray-800 rounded p-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500 font-mono"
                />
              </div>
            )}

            {/* Confidence & Rationale */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">
                  Confidence (0.0 to 1.0)
                </label>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={confidence}
                  onChange={(e) => setConfidence(e.target.value)}
                  className="w-full bg-gray-950 border border-gray-800 rounded p-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500 font-mono"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="block text-xs font-medium text-gray-400 mb-1">
                  Engineering Rationale
                </label>
                <input
                  type="text"
                  value={rationaleInput}
                  onChange={(e) => setRationaleInput(e.target.value)}
                  placeholder="Justification based on visible telemetry / simulation..."
                  className="w-full bg-gray-950 border border-gray-800 rounded p-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            {/* Assumptions */}
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">
                Assumptions (One per line)
              </label>
              <textarea
                value={assumptionsInput}
                onChange={(e) => setAssumptionsInput(e.target.value)}
                placeholder="e.g. Dry track conditions&#10;Nominal tire pressures"
                rows={2}
                className="w-full bg-gray-950 border border-gray-800 rounded p-2 text-xs text-gray-200 focus:outline-none focus:border-indigo-500"
              />
            </div>

            {error && <p className="text-xs text-red-400">{error}</p>}

            <button
              onClick={handleSubmitPrediction}
              disabled={submitting}
              className="px-4 py-2 text-xs font-semibold rounded bg-signal hover:bg-[#d6f56e] text-carbon flex items-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Send className="w-3.5 h-3.5" />
              <span>{submitting ? "Locking Submission..." : "Lock Prediction & Seal Session"}</span>
            </button>
          </div>
        </div>
      ) : (
        /* PENDING ACTIVATION */
        <div className="p-4 rounded bg-gray-900 text-gray-400 text-xs italic border border-gray-800">
          Session is currently in {session.status} state. Awaiting activation before evaluator submissions open.
        </div>
      )}
    </div>
  );
}
