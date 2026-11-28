"use client";

import React, { useState, useEffect } from "react";
import {
  ShieldCheck,
  Scale,
  TrendingUp,
  AlertCircle,
  HelpCircle,
  Clock,
  Layers,
  FileCheck2,
  CheckCircle2,
  XCircle,
  Filter,
  BarChart3,
  Hash,
} from "lucide-react";
import {
  BlindCalibrationApi,
  CalibrationSummaryResponseDTO,
  CalibrationCurveResponseDTO,
  CalibrationHistoryResponseDTO,
  EvaluationHistoryItemDTO,
} from "../../lib/api_client";

interface BlindCalibrationViewProps {
  onSelectSession?: (sessionId: string) => void;
}

export function BlindCalibrationView({ onSelectSession }: BlindCalibrationViewProps) {
  const [summary, setSummary] = useState<CalibrationSummaryResponseDTO | null>(null);
  const [curve, setCurve] = useState<CalibrationCurveResponseDTO | null>(null);
  const [history, setHistory] = useState<CalibrationHistoryResponseDTO | null>(null);
  const [selectedType, setSelectedType] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadCalibrationData();
  }, [selectedType]);

  const loadCalibrationData = async () => {
    setLoading(true);
    setError(null);
    try {
      const filter = selectedType ? { prediction_type: selectedType } : undefined;
      const [sumRes, curveRes, histRes] = await Promise.all([
        BlindCalibrationApi.getMySummary(filter),
        BlindCalibrationApi.getMyCurve(filter),
        BlindCalibrationApi.getMyHistory({ ...filter, limit: 20 }),
      ]);
      setSummary(sumRes);
      setCurve(curveRes);
      setHistory(histRes);
    } catch (e: any) {
      setError(e.message || "Failed to load blind calibration record.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="blind-calibration-view">
      {/* Header & Governance Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-emerald-400" />
              <h2 className="text-lg font-semibold text-white">
                Longitudinal Blind Engineering Calibration
              </h2>
              <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                Policy: {summary?.calibration_policy_version || "V1"}
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Deterministic, statistically valid evaluation of blind forecasts against authoritative outcomes.
              Separates accuracy from calibration. Zero AI judging or engineer rankings.
            </p>
          </div>

          {/* Prediction Type Filter */}
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-slate-400" />
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              aria-label="Filter by prediction type"
            >
              <option value="">All Prediction Classes</option>
              <option value="QUANTITATIVE">Quantitative</option>
              <option value="DIRECTIONAL">Directional</option>
              <option value="CATEGORICAL">Categorical</option>
              <option value="ENGINEERING_DECISION">Engineering Decision</option>
            </select>
          </div>
        </div>

        {summary?.aggregate_hash && (
          <div className="mt-3 pt-3 border-t border-slate-800/80 flex items-center gap-2 text-xs text-zinc-400 font-mono">
            <Hash className="h-3 w-3" />
            <span>Aggregate Hash: {summary.aggregate_hash.slice(0, 16)}...</span>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-950/40 border border-red-800/50 rounded-lg p-4 flex items-center gap-3 text-red-300 text-sm">
          <AlertCircle className="h-5 w-5 shrink-0 text-red-400" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="p-12 text-center text-slate-400 text-sm">
          Loading longitudinal calibration records...
        </div>
      ) : (
        <>
          {/* Key Metrics: Outcome Accuracy vs Coverage vs Calibration */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* 1. Outcome Accuracy */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                  Observed Accuracy
                </span>
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                {summary?.outcome_statistics.observed_accuracy !== null &&
                summary?.outcome_statistics.observed_accuracy !== undefined ? (
                  <span className="text-2xl font-bold text-white">
                    {(summary.outcome_statistics.observed_accuracy * 100).toFixed(1)}%
                  </span>
                ) : (
                  <span className="text-lg font-semibold text-zinc-400">N/A</span>
                )}
                <span className="text-xs text-slate-400">
                  ({summary?.outcome_statistics.correct_outcomes ?? 0} /{" "}
                  {summary?.outcome_statistics.binary_evaluated_count ?? 0} comparable)
                </span>
              </div>
              {summary?.outcome_statistics.observed_accuracy_ci && (
                <div className="text-xs text-slate-400 mt-1">
                  95% CI: [
                  {(summary.outcome_statistics.observed_accuracy_ci[0] * 100).toFixed(1)}%,{" "}
                  {(summary.outcome_statistics.observed_accuracy_ci[1] * 100).toFixed(1)}%]
                </div>
              )}
              <div className="text-xs text-zinc-400 mt-2">
                Denominator: Binary correct + incorrect outcomes only.
              </div>
            </div>

            {/* 2. Coverage */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                  Evaluation Coverage
                </span>
                <Scale className="h-4 w-4 text-blue-400" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                {summary?.outcome_statistics.comparison_coverage !== null &&
                summary?.outcome_statistics.comparison_coverage !== undefined ? (
                  <span className="text-2xl font-bold text-white">
                    {(summary.outcome_statistics.comparison_coverage * 100).toFixed(1)}%
                  </span>
                ) : (
                  <span className="text-lg font-semibold text-zinc-400">N/A</span>
                )}
                <span className="text-xs text-slate-400">
                  ({summary?.outcome_statistics.comparable_evaluations ?? 0} /{" "}
                  {summary?.outcome_statistics.total_completed_evaluations ?? 0} completed)
                </span>
              </div>
              <div className="text-xs text-slate-400 mt-1">
                Uncomparable: {summary?.outcome_statistics.uncomparable_evaluations ?? 0} (excluded from error)
              </div>
              <div className="text-xs text-zinc-400 mt-2">
                Uncomparable outcomes are never counted as incorrect.
              </div>
            </div>

            {/* 3. Brier Score */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                  Binary Brier Score
                </span>
                <TrendingUp className="h-4 w-4 text-amber-400" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                {summary?.brier_score.status === "AVAILABLE" &&
                summary?.brier_score.brier_score !== null &&
                summary?.brier_score.brier_score !== undefined ? (
                  <span className="text-2xl font-bold text-white font-mono">
                    {summary.brier_score.brier_score.toFixed(4)}
                  </span>
                ) : (
                  <span className="text-sm font-semibold text-amber-400/90">
                    {summary?.brier_score.status || "INSUFFICIENT_SAMPLE"}
                  </span>
                )}
                <span className="text-xs text-slate-400">
                  (N = {summary?.brier_score.eligible_sample_size ?? 0})
                </span>
              </div>
              <div className="text-xs text-slate-400 mt-1">
                Lower = better probabilistic calibration.
              </div>
              <div className="text-xs text-zinc-400 mt-2">
                Requires explicit PROBABILITY_PREDICTION_CORRECT semantics.
              </div>
            </div>
          </div>

          {/* 5-Bin Reliability / Calibration Curve */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-emerald-400" />
                  Reliability / Calibration Curve (5 Bins)
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Mean forecast probability vs. observed event frequency with Wilson score 95% uncertainty intervals.
                </p>
              </div>
              <span
                className={`text-xs px-2.5 py-0.5 rounded font-medium ${
                  curve?.status === "AVAILABLE"
                    ? "bg-emerald-950/60 text-emerald-400 border border-emerald-800/60"
                    : "bg-amber-950/60 text-amber-400 border border-amber-800/60"
                }`}
              >
                Status: {curve?.status || "NO_DATA"}
              </span>
            </div>

            <div className="mt-4 text-xs text-slate-400">
              {curve?.status_message}
            </div>

            {/* Bins Table */}
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="bg-slate-800/60 text-slate-400 border-b border-slate-700">
                  <tr>
                    <th className="py-2 px-3">Probability Bin</th>
                    <th className="py-2 px-3">Sample Count</th>
                    <th className="py-2 px-3">Positive Count</th>
                    <th className="py-2 px-3">Mean Forecast</th>
                    <th className="py-2 px-3">Observed Frequency</th>
                    <th className="py-2 px-3">95% Uncertainty (Wilson)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {curve?.bins && curve.bins.length > 0 ? (
                    curve.bins.map((b) => (
                      <tr key={b.bin_index} className="hover:bg-slate-800/30">
                        <td className="py-2 px-3 font-mono text-slate-200">{b.label}</td>
                        <td className="py-2 px-3 font-mono">{b.sample_count}</td>
                        <td className="py-2 px-3 font-mono">{b.positive_count}</td>
                        <td className="py-2 px-3 font-mono">
                          {b.mean_forecast_probability !== null && b.mean_forecast_probability !== undefined
                            ? (b.mean_forecast_probability * 100).toFixed(1) + "%"
                            : "—"}
                        </td>
                        <td className="py-2 px-3 font-mono">
                          {b.observed_frequency !== null && b.observed_frequency !== undefined
                            ? (b.observed_frequency * 100).toFixed(1) + "%"
                            : "—"}
                        </td>
                        <td className="py-2 px-3 font-mono text-slate-400">
                          {b.uncertainty_interval
                            ? `[${(b.uncertainty_interval[0] * 100).toFixed(1)}%, ${(b.uncertainty_interval[1] * 100).toFixed(1)}%]`
                            : "— (empty)"}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6} className="py-4 text-center text-zinc-400">
                        No calibration curve observations recorded.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Excluded Observations & Ineligibility Explanations */}
          {summary?.outcome_statistics.excluded_counts && (
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4">
              <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <HelpCircle className="h-3.5 w-3.5 text-slate-400" />
                Metric Ineligibility Accounting
              </h4>
              <p className="text-xs text-slate-400 mt-1">
                Authoritative record of excluded evaluations preserving evaluation integrity:
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
                <div className="bg-slate-800/50 border border-slate-700/60 rounded p-2.5">
                  <div className="text-xs text-slate-400">Unspecified Confidence Semantics</div>
                  <div className="text-base font-bold text-slate-200 mt-0.5">
                    {summary.outcome_statistics.excluded_counts["NOT_ELIGIBLE_SEMANTICS_UNSPECIFIED"] ?? 0}
                  </div>
                  <div className="text-xs text-zinc-400 mt-0.5">
                    Historical submissions without declared probability semantics.
                  </div>
                </div>
                <div className="bg-slate-800/50 border border-slate-700/60 rounded p-2.5">
                  <div className="text-xs text-slate-400">Uncomparable Evaluations</div>
                  <div className="text-base font-bold text-slate-200 mt-0.5">
                    {summary.outcome_statistics.excluded_counts["NOT_ELIGIBLE_UNCOMPARABLE"] ?? 0}
                  </div>
                  <div className="text-xs text-zinc-400 mt-0.5">
                    Missing targets or mismatched unit dimensions.
                  </div>
                </div>
                <div className="bg-slate-800/50 border border-slate-700/60 rounded p-2.5">
                  <div className="text-xs text-slate-400">Metrics-Only Evaluations</div>
                  <div className="text-base font-bold text-slate-200 mt-0.5">
                    {summary.outcome_statistics.excluded_counts["NOT_ELIGIBLE_METRICS_ONLY"] ?? 0}
                  </div>
                  <div className="text-xs text-zinc-400 mt-0.5">
                    Continuous quantitative evaluations without declared tolerance bands.
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Longitudinal History & Provenance Backlinks */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                  <Clock className="h-4 w-4 text-blue-400" />
                  Longitudinal Evaluation Record
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Authoritative history with provenance backlinks to sessions and comparisons.
                </p>
              </div>
              <span className="text-xs text-slate-400">
                Showing {history?.evaluations.length ?? 0} of {history?.total_count ?? 0}
              </span>
            </div>

            <div className="mt-4 divide-y divide-slate-800">
              {history?.evaluations && history.evaluations.length > 0 ? (
                history.evaluations.map((item) => (
                  <div key={item.comparison_id} className="py-3 flex flex-col md:flex-row md:items-center justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-white">
                          {item.session_name}
                        </span>
                        <span className="text-xs px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                          {item.comparison_type}
                        </span>
                        <span
                          className={`text-xs px-1.5 py-0.5 rounded font-semibold ${
                            item.verdict === "CORRECT" ||
                            item.verdict === "SUPPORTED" ||
                            item.verdict === "WITHIN_TOLERANCE" ||
                            item.verdict === "CORRECT_DIRECTION"
                              ? "bg-emerald-950/60 text-emerald-400 border border-emerald-800/60"
                              : item.verdict === "UNCOMPARABLE" || item.verdict === "METRICS_ONLY"
                              ? "bg-slate-800 text-slate-300 border border-slate-700"
                              : "bg-red-950/60 text-red-400 border border-red-800/60"
                          }`}
                        >
                          {item.verdict}
                        </span>
                      </div>
                      <div className="text-xs text-slate-400 mt-1">
                        {item.interpretation}
                      </div>
                      <div className="text-xs text-zinc-400 font-mono mt-0.5 flex gap-3">
                        <span>Comparison: {item.comparison_id.slice(0, 8)}...</span>
                        <span>Hash: {item.comparison_hash.slice(0, 8)}...</span>
                        <span>Date: {item.computed_at ? item.computed_at.split("T")[0] : "—"}</span>
                      </div>
                    </div>

                    {onSelectSession && (
                      <button
                        onClick={() => onSelectSession(item.session_id)}
                        className="self-start md:self-center px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded border border-slate-700 transition"
                      >
                        View Session
                      </button>
                    )}
                  </div>
                ))
              ) : (
                <div className="py-6 text-center text-zinc-400 text-xs">
                  No completed blind evaluations recorded.
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
