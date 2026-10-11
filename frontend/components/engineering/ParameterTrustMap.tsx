"use client";

import React, { useState, useEffect } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  Clock,
  History,
  FileCheck2,
  HelpCircle,
  Hash,
  Database,
  Layers,
  Search,
  RefreshCw,
  Sliders,
  CheckCircle2,
} from "lucide-react";
import {
  ParameterTrustApi,
  ParameterTrustResponseDTO,
  ParameterTrustHistoryItemDTO,
  ParameterTrustState,
  ValidationCoverage,
  BatchIngestSummaryDTO,
  ParameterSweepAnalysisResponseDTO,
  FleetSynchronizationResponseDTO,
  AssemblyImpactAssessmentResponseDTO,
  SensitivityEvidenceResponseDTO,
} from "../../lib/api_client";

interface ParameterTrustMapProps {
  initialEntityType?: string;
  initialEntityId?: string;
  initialParameter?: string;
  onLoaded?: (data: ParameterTrustResponseDTO) => void;
}

export function ParameterTrustMap({
  initialEntityType = "SetupCandidate",
  initialEntityId = "SETUP-P3L-CAND-01",
  initialParameter = "front_spring_rate",
  onLoaded,
}: ParameterTrustMapProps) {
  const [entityType, setEntityType] = useState(initialEntityType);
  const [entityId, setEntityId] = useState(initialEntityId);
  const [parameter, setParameter] = useState(initialParameter);

  const [trustData, setTrustData] = useState<ParameterTrustResponseDTO | null>(null);
  const [historyItems, setHistoryItems] = useState<ParameterTrustHistoryItemDTO[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<
    "overview" | "evidence" | "history" | "sweep" | "ingestion" | "fleet" | "propagation"
  >("overview");

  // Phase 6.2 Ingestion & Sweep State
  const [ingestSummary, setIngestSummary] = useState<BatchIngestSummaryDTO | null>(null);
  const [ingestLoading, setIngestLoading] = useState(false);
  const [ingestError, setIngestError] = useState<string | null>(null);

  const [sweepData, setSweepData] = useState<ParameterSweepAnalysisResponseDTO | null>(null);
  const [sweepLoading, setSweepLoading] = useState(false);
  const [sweepError, setSweepError] = useState<string | null>(null);

  // Phase 6.3 Fleet & Propagation State
  const [fleetData, setFleetData] = useState<FleetSynchronizationResponseDTO | null>(null);
  const [fleetLoading, setFleetLoading] = useState(false);
  const [fleetError, setFleetError] = useState<string | null>(null);
  const [fleetId, setFleetId] = useState("FLEET-GT3-2026");

  const [impactData, setImpactData] = useState<AssemblyImpactAssessmentResponseDTO | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [impactError, setImpactError] = useState<string | null>(null);

  const fetchTrustData = async (type: string, id: string, param: string) => {
    if (!type || !id || !param) return;
    setLoading(true);
    setError(null);
    try {
      const data = await ParameterTrustApi.getParameterTrust(type, id, param);
      setTrustData(data);
      if (onLoaded) onLoaded(data);

      try {
        const histRes = await ParameterTrustApi.getParameterTrustHistory(type, id, param);
        setHistoryItems(histRes.history || []);
      } catch {
        setHistoryItems([]);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load parameter trust assessment.");
      setTrustData(null);
      setHistoryItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrustData(entityType, entityId, parameter);
  }, []);

  const handleQuery = (e: React.FormEvent) => {
    e.preventDefault();
    fetchTrustData(entityType, entityId, parameter);
  };

  const handleRunIngest = async () => {
    setIngestLoading(true);
    setIngestError(null);
    try {
      const res = await ParameterTrustApi.ingestEntity(entityType, entityId);
      setIngestSummary(res);
      await fetchTrustData(entityType, entityId, parameter);
    } catch (err: any) {
      setIngestError(err?.message || "Automated ingestion failed.");
    } finally {
      setIngestLoading(false);
    }
  };

  const handleRunSweep = async () => {
    setSweepLoading(true);
    setSweepError(null);
    try {
      const res = await ParameterTrustApi.analyzeSweep({
        parameter_name: parameter,
        candidates: [
          { entity_type: entityType, entity_id: entityId },
          { entity_type: "SetupCandidate", entity_id: "SETUP-P3L-CAND-02" },
          { entity_type: "SimulationRun", entity_id: "RUN-000183" },
        ],
      });
      setSweepData(res);
    } catch (err: any) {
      setSweepError(err?.message || "Parameter sweep analysis failed.");
    } finally {
      setSweepLoading(false);
    }
  };

  const handleRunFleetSync = async () => {
    setFleetLoading(true);
    setFleetError(null);
    try {
      const res = await ParameterTrustApi.compareFleet({
        fleet_id: fleetId,
        parameter_name: parameter,
        members: [
          { entity_type: entityType, entity_id: entityId },
          { entity_type: "VehicleProfile", entity_id: "VEH-GT3-02" },
          { entity_type: "VehicleProfile", entity_id: "VEH-GT3-03" },
          { entity_type: "VehicleProfile", entity_id: "VEH-GT3-04" },
        ],
        persist_report: false,
      });
      setFleetData(res);
    } catch (err: any) {
      setFleetError(err?.message || "Fleet synchronization failed.");
    } finally {
      setFleetLoading(false);
    }
  };

  const handleRunAssemblyImpact = async () => {
    setImpactLoading(true);
    setImpactError(null);
    try {
      const res = await ParameterTrustApi.getAssemblyImpact(entityId, parameter);
      setImpactData(res);
    } catch (err: any) {
      setImpactError(err?.message || "Assembly impact assessment failed.");
    } finally {
      setImpactLoading(false);
    }
  };

  // State styling helper
  const getTrustStateBadge = (state: ParameterTrustState) => {
    switch (state) {
      case "HIGH_CONFIDENCE":
        return {
          bg: "bg-emerald-950/80 border-emerald-500/50 text-emerald-300",
          icon: ShieldCheck,
          label: "HIGH CONFIDENCE",
        };
      case "VALIDATED":
        return {
          bg: "bg-blue-950/80 border-blue-500/50 text-blue-300",
          icon: ShieldCheck,
          label: "VALIDATED",
        };
      case "SUPPORTED":
        return {
          bg: "bg-cyan-950/80 border-cyan-500/50 text-cyan-300",
          icon: FileCheck2,
          label: "SUPPORTED",
        };
      case "PROVISIONAL":
        return {
          bg: "bg-amber-950/80 border-amber-500/50 text-amber-300",
          icon: Clock,
          label: "PROVISIONAL",
        };
      case "CONFLICTED":
        return {
          bg: "bg-rose-950/80 border-rose-500/50 text-rose-300",
          icon: AlertTriangle,
          label: "CONFLICTED",
        };
      case "STALE":
        return {
          bg: "bg-zinc-900 border-zinc-700 text-zinc-400",
          icon: Clock,
          label: "STALE",
        };
      case "REJECTED":
        return {
          bg: "bg-red-950/90 border-red-500/60 text-red-300",
          icon: ShieldAlert,
          label: "REJECTED",
        };
      case "INSUFFICIENT_EVIDENCE":
        return {
          bg: "bg-orange-950/80 border-orange-500/50 text-orange-300",
          icon: HelpCircle,
          label: "INSUFFICIENT EVIDENCE",
        };
      case "UNASSESSED":
      default:
        return {
          bg: "bg-gray-900 border-gray-700 text-gray-400",
          icon: HelpCircle,
          label: "UNASSESSED",
        };
    }
  };

  const getValidationCoverageBadge = (coverage: ValidationCoverage) => {
    switch (coverage) {
      case "VALIDATED":
        return "bg-emerald-950/70 border-emerald-500/40 text-emerald-300";
      case "PARTIAL_VALIDATION":
        return "bg-amber-950/70 border-amber-500/40 text-amber-300";
      case "CONFLICTING_VALIDATION":
        return "bg-rose-950/70 border-rose-500/40 text-rose-300";
      case "NO_VALIDATION":
      default:
        return "bg-zinc-900 border-zinc-700 text-zinc-400";
    }
  };

  return (
    <div className="w-full max-w-6xl mx-auto rounded-xl border border-zinc-800 bg-[#0c0d0e] text-zinc-100 shadow-2xl p-6 font-sans">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-6 border-b border-zinc-800 gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono tracking-widest uppercase px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
              Phase 6.1
            </span>
            <span className="text-[10px] font-mono text-zinc-400">
              POLICY: {trustData?.policy_version || "TRUST_POLICY_V1"}
            </span>
          </div>
          <h1 className="text-2xl font-bold mt-1 text-white flex items-center gap-2">
            <Layers className="w-6 h-6 text-amber-400" />
            Parameter Trust Map
          </h1>
          <p className="text-xs text-zinc-400 mt-0.5">
            Provenance-aware engineering confidence grounded in authoritative evidence and validation history.
          </p>
        </div>

        {/* Query Controls */}
        <form onSubmit={handleQuery} className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
            placeholder="Entity Type"
            className="px-3 py-1.5 text-xs bg-zinc-900 border border-zinc-700 rounded text-zinc-200 focus:outline-none focus:border-amber-400 w-36 font-mono"
            data-testid="input-entity-type"
          />
          <input
            type="text"
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
            placeholder="Entity ID"
            className="px-3 py-1.5 text-xs bg-zinc-900 border border-zinc-700 rounded text-zinc-200 focus:outline-none focus:border-amber-400 w-44 font-mono"
            data-testid="input-entity-id"
          />
          <input
            type="text"
            value={parameter}
            onChange={(e) => setParameter(e.target.value)}
            placeholder="Parameter Name"
            className="px-3 py-1.5 text-xs bg-zinc-900 border border-zinc-700 rounded text-zinc-200 focus:outline-none focus:border-amber-400 w-40 font-mono"
            data-testid="input-parameter"
          />
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-1.5 text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-black rounded transition flex items-center gap-1.5 disabled:opacity-50"
            data-testid="btn-query-trust"
          >
            <Search className="w-3.5 h-3.5" />
            {loading ? "Evaluating..." : "Inspect"}
          </button>
        </form>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mt-4 p-4 rounded-lg bg-red-950/50 border border-red-500/40 text-red-300 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 text-red-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Main Content */}
      {trustData && (
        <div className="mt-6 space-y-6">
          {/* Parameter Identity & Primary Trust State */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 p-5 rounded-lg bg-zinc-900/60 border border-zinc-800">
            {/* 1. Parameter */}
            <div>
              <div className="text-[10px] uppercase font-mono tracking-wider text-zinc-400">Parameter</div>
              <div className="text-base font-semibold text-white mt-1 font-mono break-all" data-testid="param-name">
                {trustData.parameter_identity.parameter_name}
              </div>
              <div className="text-[11px] text-zinc-500 font-mono truncate mt-0.5" title={trustData.parameter_identity.parameter_path}>
                {trustData.parameter_identity.parameter_path}
              </div>
            </div>

            {/* 2. Value & Unit */}
            <div>
              <div className="text-[10px] uppercase font-mono tracking-wider text-zinc-400">Value & Unit</div>
              <div className="text-lg font-bold text-white mt-1 flex items-baseline gap-1.5 font-mono">
                <span data-testid="param-value">
                  {typeof trustData.value_reference.value === "number"
                    ? trustData.value_reference.value.toLocaleString()
                    : String(trustData.value_reference.value)}
                </span>
                <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-amber-400 border border-zinc-700" data-testid="param-unit">
                  {trustData.unit || "—"}
                </span>
              </div>
              <div className="text-[10px] text-zinc-500 font-mono mt-0.5">
                Hash: {trustData.value_reference.value_identity}
              </div>
            </div>

            {/* 3. Trust State */}
            <div>
              <div className="text-[10px] uppercase font-mono tracking-wider text-zinc-400">Trust State</div>
              <div className="mt-1">
                {(() => {
                  const badge = getTrustStateBadge(trustData.current_trust_state);
                  const Icon = badge.icon;
                  return (
                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold border ${badge.bg}`}
                      data-testid="param-trust-state"
                    >
                      <Icon className="w-3.5 h-3.5" />
                      {badge.label}
                    </span>
                  );
                })()}
              </div>
              <div className="text-[10px] text-zinc-500 mt-1">
                Deterministic: {trustData.assessment_hash.slice(0, 12)}...
              </div>
            </div>

            {/* 4. Validation Coverage */}
            <div>
              <div className="text-[10px] uppercase font-mono tracking-wider text-zinc-400">Validation Coverage</div>
              <div className="mt-1">
                <span
                  className={`inline-block px-2.5 py-1 rounded-md text-xs font-semibold border ${getValidationCoverageBadge(
                    trustData.validation_coverage
                  )}`}
                  data-testid="param-validation-coverage"
                >
                  {trustData.validation_coverage.replace("_", " ")}
                </span>
              </div>
              <div className="text-[10px] text-zinc-500 mt-1">
                {trustData.recency.latest_supporting_validation
                  ? `Latest: ${trustData.recency.latest_supporting_validation}`
                  : "No out-of-sample gate"}
              </div>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex items-center gap-2 border-b border-zinc-800 pb-2">
            <button
              onClick={() => setActiveTab("overview")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "overview"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Overview & Scope
            </button>
            <button
              onClick={() => setActiveTab("evidence")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "evidence"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Supporting Evidence ({trustData.supporting_evidence.length})
            </button>
            <button
              onClick={() => setActiveTab("history")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "history"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Audit History ({historyItems.length})
            </button>
            <button
              onClick={() => setActiveTab("sweep")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "sweep"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
              data-testid="tab-sweep"
            >
              Sweep Analysis
            </button>
            <button
              onClick={() => setActiveTab("ingestion")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "ingestion"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
              data-testid="tab-ingestion"
            >
              Automated Ingestion
            </button>
            <button
              onClick={() => setActiveTab("fleet")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "fleet"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
              data-testid="tab-fleet"
            >
              Fleet Sync
            </button>
            <button
              onClick={() => setActiveTab("propagation")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "propagation"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
              data-testid="tab-propagation"
            >
              Assembly Propagation
            </button>
          </div>

          {/* Tab 1: Overview & Scope */}
          {activeTab === "overview" && (
            <div className="space-y-6">
              {/* Conflict Alert (if any) */}
              {trustData.conflicts && trustData.conflicts.length > 0 && (
                <div className="p-4 rounded-lg bg-rose-950/40 border border-rose-500/50 text-rose-200" data-testid="conflicts-container">
                  <div className="flex items-center gap-2 font-semibold text-xs text-rose-300">
                    <AlertTriangle className="w-4 h-4" />
                    Conflict Detected ({trustData.conflicts.length})
                  </div>
                  <div className="mt-2 space-y-2">
                    {trustData.conflicts.map((c, i) => (
                      <div key={i} className="text-xs p-2.5 rounded bg-rose-950/60 border border-rose-500/30">
                        <div className="font-mono font-medium">{c.conflict_type}</div>
                        <div className="text-zinc-300 mt-1">{c.detail}</div>
                        {c.delta_pct !== null && c.delta_pct !== undefined && (
                          <div className="text-[11px] text-rose-400 mt-0.5">
                            Divergence: {c.delta_pct}% (Delta: {c.delta})
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Scope / Applicability */}
              <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800" data-testid="scope-container">
                <div className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-2">
                  <Database className="w-3.5 h-3.5 text-amber-400" />
                  Scope & Applicability Envelope
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3 text-xs">
                  {Object.entries(trustData.scope).map(([k, v]) => (
                    <div key={k} className="p-2 rounded bg-zinc-900 border border-zinc-800 font-mono">
                      <div className="text-[10px] text-zinc-500 uppercase">{k}</div>
                      <div className="text-zinc-200 truncate mt-0.5" title={String(v)}>
                        {String(v ?? "—")}
                      </div>
                    </div>
                  ))}
                  {Object.keys(trustData.scope).length === 0 && (
                    <div className="text-xs text-zinc-500 italic">No scope boundaries recorded.</div>
                  )}
                </div>
              </div>

              {/* Trust Explanation */}
              <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800" data-testid="explanation-container">
                <div className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-2">
                  <FileCheck2 className="w-3.5 h-3.5 text-amber-400" />
                  Auditable Trust Explanation
                </div>
                <div className="mt-3 space-y-2">
                  {trustData.explanation.reasons.map((r, i) => (
                    <div key={i} className="text-xs text-zinc-300 flex items-start gap-2">
                      <span className="text-amber-400 font-mono">▸</span>
                      <span>{r}</span>
                    </div>
                  ))}
                </div>

                {trustData.explanation.limitations && trustData.explanation.limitations.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-zinc-800">
                    <div className="text-[10px] uppercase font-mono text-zinc-500 tracking-wider">
                      Known Limitations
                    </div>
                    <ul className="mt-1 list-disc list-inside text-xs text-zinc-400 space-y-1">
                      {trustData.explanation.limitations.map((lim, i) => (
                        <li key={i}>{lim}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Recency Metadata (TRUST_RECENCY_POLICY_V1) */}
              <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800" data-testid="recency-container">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-amber-400" />
                    Validation Recency Metadata
                  </div>
                  {trustData.recency.recency_condition && (
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-zinc-800 text-amber-300 border border-zinc-700">
                      {trustData.recency.recency_condition}
                    </span>
                  )}
                </div>

                {/* Recency Warning / Advisory if recommended */}
                {trustData.recency.reassessment_recommended && (
                  <div className="mt-3 p-2.5 rounded bg-amber-950/40 border border-amber-500/30 text-xs text-amber-200 flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold text-amber-300">Reassessment Recommended</div>
                      <div className="text-zinc-300 mt-0.5">{trustData.recency.reassessment_reason}</div>
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3 text-xs font-mono">
                  <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                    <div className="text-[10px] text-zinc-500 uppercase">Evidence Timestamp</div>
                    <div className="text-zinc-200 mt-0.5">{trustData.recency.evidence_timestamp || "—"}</div>
                  </div>
                  <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                    <div className="text-[10px] text-zinc-500 uppercase">Validation Timestamp</div>
                    <div className="text-zinc-200 mt-0.5">{trustData.recency.validation_timestamp || "—"}</div>
                  </div>
                  <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                    <div className="text-[10px] text-zinc-500 uppercase">Source Version</div>
                    <div className="text-zinc-200 mt-0.5">{trustData.recency.source_version || "—"}</div>
                  </div>
                  <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                    <div className="text-[10px] text-zinc-500 uppercase">Age (Days)</div>
                    <div className="text-zinc-200 mt-0.5">{trustData.recency.age_days ?? "—"}</div>
                  </div>
                </div>

                {/* Epistemic Aging Invariant Note */}
                <div className="mt-3 p-2 rounded bg-zinc-900/60 border border-zinc-800/80 text-[11px] text-zinc-400 flex items-start gap-2">
                  <span className="text-amber-400 font-bold shrink-0">ℹ</span>
                  <span>
                    <strong>Epistemic Invariant:</strong> {trustData.recency.epistemic_aging_note || "Evidence aging reflects temporal epistemic recency, NOT physical component degradation or mechanical fatigue."}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Tab 2: Supporting Evidence */}
          {activeTab === "evidence" && (
            <div className="space-y-4" data-testid="evidence-container">
              {trustData.supporting_evidence.length === 0 ? (
                <div className="p-6 text-center text-xs text-zinc-500 italic rounded-lg bg-zinc-900/40 border border-zinc-800">
                  No supporting evidence artifacts connected in the Evidence Graph.
                </div>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-zinc-800">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-zinc-900/80 text-zinc-400 uppercase font-mono text-[10px] border-b border-zinc-800">
                      <tr>
                        <th className="p-3">Relationship</th>
                        <th className="p-3">Artifact Type</th>
                        <th className="p-3">Artifact ID</th>
                        <th className="p-3">Artifact Hash</th>
                        <th className="p-3">Timestamp</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-800/60 font-mono">
                      {trustData.supporting_evidence.map((ev, i) => (
                        <tr key={i} className="hover:bg-zinc-900/40">
                          <td className="p-3 text-amber-400 font-semibold">{ev.relationship}</td>
                          <td className="p-3 text-zinc-300">{ev.evidence_type}</td>
                          <td className="p-3 text-white">{ev.evidence_id}</td>
                          <td className="p-3 text-zinc-500 text-[11px] truncate max-w-xs" title={ev.artifact_hash}>
                            {ev.artifact_hash.slice(0, 16)}...
                          </td>
                          <td className="p-3 text-zinc-400 text-[11px]">{ev.timestamp || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Tab 3: History */}
          {activeTab === "history" && (
            <div className="space-y-4" data-testid="history-container">
              {historyItems.length === 0 ? (
                <div className="p-6 text-center text-xs text-zinc-500 italic rounded-lg bg-zinc-900/40 border border-zinc-800">
                  No historical assessments recorded yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {historyItems.map((h, i) => (
                    <div
                      key={h.id || i}
                      className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-zinc-400 text-[11px]">{h.created_at}</span>
                          <span className="font-mono text-[10px] text-zinc-600">ID: {h.id.slice(0, 8)}</span>
                        </div>
                        <div className="mt-1 flex items-center gap-2">
                          <span className="font-semibold text-white">{h.trust_state}</span>
                          <span className="text-zinc-500">•</span>
                          <span className="text-zinc-400">{h.validation_coverage}</span>
                          <span className="text-zinc-500">•</span>
                          <span className="text-zinc-500 font-mono text-[11px]">
                            Policy: {h.policy_version}
                          </span>
                        </div>
                      </div>
                      <div className="text-right font-mono text-[11px] text-zinc-500">
                        <div title={h.assessment_hash}>Hash: {h.assessment_hash.slice(0, 16)}...</div>
                        <div title={h.value_identity}>Val: {h.value_identity}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Tab 4: Sweep Analysis */}
          {activeTab === "sweep" && (
            <div className="space-y-6" data-testid="sweep-container">
              <div className="flex items-center justify-between p-4 rounded-lg bg-zinc-900/40 border border-zinc-800">
                <div>
                  <div className="text-xs font-semibold text-white flex items-center gap-2">
                    <Sliders className="w-4 h-4 text-amber-400" />
                    Cross-Variant Parameter Sweep Analysis
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-1">
                    Evaluates comparability across candidate setups, sweeps, and simulation runs.
                  </div>
                </div>
                <button
                  onClick={handleRunSweep}
                  disabled={sweepLoading}
                  className="px-3 py-1.5 text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-black rounded transition flex items-center gap-1.5 disabled:opacity-50"
                  data-testid="btn-run-sweep"
                >
                  <Sliders className="w-3.5 h-3.5" />
                  {sweepLoading ? "Analyzing Sweep..." : "Run Sweep Analysis"}
                </button>
              </div>

              {sweepError && (
                <div className="p-3 rounded bg-red-950/40 border border-red-500/30 text-red-300 text-xs">
                  {sweepError}
                </div>
              )}

              {sweepData && (
                <div className="space-y-4">
                  {/* Sweep Metrics Cards */}
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-3 font-mono">
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Min Value</div>
                      <div className="text-base font-bold text-white mt-1">
                        {sweepData.summary_metrics.min ?? "—"} <span className="text-xs font-normal text-amber-400">{sweepData.canonical_unit}</span>
                      </div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Max Value</div>
                      <div className="text-base font-bold text-white mt-1">
                        {sweepData.summary_metrics.max ?? "—"} <span className="text-xs font-normal text-amber-400">{sweepData.canonical_unit}</span>
                      </div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Delta (Range)</div>
                      <div className="text-base font-bold text-white mt-1">
                        {sweepData.summary_metrics.delta ?? "—"} <span className="text-xs font-normal text-amber-400">{sweepData.canonical_unit}</span>
                      </div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Mean Value</div>
                      <div className="text-base font-bold text-white mt-1">
                        {sweepData.summary_metrics.mean ?? "—"} <span className="text-xs font-normal text-amber-400">{sweepData.canonical_unit}</span>
                      </div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Comparable</div>
                      <div className="text-base font-bold text-emerald-400 mt-1">
                        {sweepData.comparable_count} / {sweepData.total_observations}
                      </div>
                    </div>
                  </div>

                  {/* Evidence Gaps */}
                  <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800">
                    <div className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center justify-between">
                      <span>Validation Coverage Across Sweep</span>
                      <span className="font-mono text-amber-400">{sweepData.evidence_gaps.coverage_pct}% Validated</span>
                    </div>
                    <div className="mt-2 text-xs text-zinc-400 flex items-center gap-4">
                      <span>Validated: {sweepData.evidence_gaps.validated_candidates.length}</span>
                      <span>Unvalidated: {sweepData.evidence_gaps.unvalidated_candidates.length}</span>
                      <span>Excluded: {sweepData.excluded_count}</span>
                    </div>
                  </div>

                  {/* Observations Table */}
                  <div className="rounded-lg border border-zinc-800 overflow-hidden">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-zinc-900 text-zinc-400 font-mono text-[11px] uppercase">
                        <tr>
                          <th className="p-3">Candidate / Entity</th>
                          <th className="p-3">Observed Value</th>
                          <th className="p-3">Trust State</th>
                          <th className="p-3">Validation</th>
                          <th className="p-3">Comparability</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800 bg-zinc-900/20 font-mono">
                        {sweepData.observations.map((obs, i) => (
                          <tr key={i} className="hover:bg-zinc-900/40">
                            <td className="p-3 text-white font-medium">{obs.entity_type}:{obs.entity_id}</td>
                            <td className="p-3 text-zinc-300">{obs.value} {obs.unit}</td>
                            <td className="p-3">{obs.trust_state}</td>
                            <td className="p-3 text-zinc-400">{obs.validation_coverage}</td>
                            <td className="p-3">
                              {obs.is_comparable ? (
                                <span className="text-emerald-400">Comparable</span>
                              ) : (
                                <span className="text-rose-400" title={obs.exclusion_reason || ""}>Not Comparable</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Tab 5: Automated Ingestion */}
          {activeTab === "ingestion" && (
            <div className="space-y-6" data-testid="ingestion-container">
              <div className="flex items-center justify-between p-4 rounded-lg bg-zinc-900/40 border border-zinc-800">
                <div>
                  <div className="text-xs font-semibold text-white flex items-center gap-2">
                    <RefreshCw className="w-4 h-4 text-amber-400" />
                    Automated Trust Ingestion & Reconciliation
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-1">
                    Discovers all eligible parameters from {entityType}:{entityId} and reconciles trust assessments idempotently.
                  </div>
                </div>
                <button
                  onClick={handleRunIngest}
                  disabled={ingestLoading}
                  className="px-3 py-1.5 text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-black rounded transition flex items-center gap-1.5 disabled:opacity-50"
                  data-testid="btn-run-ingest"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${ingestLoading ? "animate-spin" : ""}`} />
                  {ingestLoading ? "Ingesting..." : "Ingest Entity Parameters"}
                </button>
              </div>

              {ingestError && (
                <div className="p-3 rounded bg-red-950/40 border border-red-500/30 text-red-300 text-xs">
                  {ingestError}
                </div>
              )}

              {ingestSummary && (
                <div className="space-y-4">
                  {/* Summary KPI grid */}
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-3 font-mono text-xs">
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Discovered</div>
                      <div className="text-base font-bold text-white mt-1">{ingestSummary.discovered_parameters}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">New Profiles</div>
                      <div className="text-base font-bold text-emerald-400 mt-1">{ingestSummary.new_profiles}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Refreshed</div>
                      <div className="text-base font-bold text-cyan-400 mt-1">{ingestSummary.refreshed_assessments}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Unchanged</div>
                      <div className="text-base font-bold text-zinc-400 mt-1">{ingestSummary.unchanged_assessments}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Evidence Linked</div>
                      <div className="text-base font-bold text-amber-400 mt-1">{ingestSummary.linked_evidence_count}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Conflicts</div>
                      <div className="text-base font-bold text-rose-400 mt-1">{ingestSummary.conflicts_found}</div>
                    </div>
                  </div>

                  {/* Profiles Table */}
                  <div className="rounded-lg border border-zinc-800 overflow-hidden">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-zinc-900 text-zinc-400 font-mono text-[11px] uppercase">
                        <tr>
                          <th className="p-3">Parameter Name</th>
                          <th className="p-3">Unit</th>
                          <th className="p-3">Trust State</th>
                          <th className="p-3">Validation</th>
                          <th className="p-3">Recency</th>
                          <th className="p-3">Assessment Hash</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800 bg-zinc-900/20 font-mono">
                        {ingestSummary.profiles.map((p, i) => (
                          <tr key={i} className="hover:bg-zinc-900/40">
                            <td className="p-3 text-white font-medium">{p.parameter_name}</td>
                            <td className="p-3 text-zinc-400">{p.unit || "—"}</td>
                            <td className="p-3">{p.trust_state}</td>
                            <td className="p-3 text-zinc-400">{p.validation_coverage}</td>
                            <td className="p-3 text-zinc-400">{p.recency_condition}</td>
                            <td className="p-3 text-zinc-500">{p.assessment_hash.slice(0, 12)}...</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Tab 6: Fleet Trust Synchronization */}
          {activeTab === "fleet" && (
            <div className="space-y-6" data-testid="fleet-container">
              <div className="flex flex-col md:flex-row md:items-center justify-between p-4 rounded-lg bg-zinc-900/40 border border-zinc-800 gap-3">
                <div>
                  <div className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
                    Fleet-Wide Trust Synchronization
                  </div>
                  <div className="text-xs text-zinc-400 mt-0.5">
                    Multi-vehicle parameter comparability without merging incompatible evidence or overwriting local records.
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={fleetId}
                    onChange={(e) => setFleetId(e.target.value)}
                    placeholder="Fleet Cohort ID"
                    className="px-3 py-1.5 text-xs bg-zinc-900 border border-zinc-700 rounded text-zinc-200 focus:outline-none focus:border-amber-400 font-mono w-44"
                    data-testid="input-fleet-id"
                  />
                  <button
                    onClick={handleRunFleetSync}
                    disabled={fleetLoading}
                    className="px-4 py-1.5 text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-black rounded transition flex items-center gap-1.5 disabled:opacity-50"
                    data-testid="btn-run-fleet-sync"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${fleetLoading ? "animate-spin" : ""}`} />
                    {fleetLoading ? "Synchronizing..." : "Synchronize Cohort"}
                  </button>
                </div>
              </div>

              {fleetError && (
                <div className="p-3 rounded bg-red-950/40 border border-red-500/30 text-red-300 text-xs">
                  {fleetError}
                </div>
              )}

              {fleetData && (
                <div className="space-y-6">
                  {/* Summary Stats Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-3 font-mono text-xs">
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Cohort Size</div>
                      <div className="text-base font-bold text-white mt-1">{fleetData.cohort_size}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Comparable</div>
                      <div className="text-base font-bold text-emerald-400 mt-1">{fleetData.comparable_count}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Missing</div>
                      <div className="text-base font-bold text-zinc-400 mt-1">{fleetData.missing_count}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Excluded</div>
                      <div className="text-base font-bold text-rose-400 mt-1">{fleetData.excluded_count}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Range (Min - Max)</div>
                      <div className="text-xs font-bold text-amber-400 mt-1 truncate">
                        {fleetData.summary_metrics.min ?? "—"} – {fleetData.summary_metrics.max ?? "—"}
                      </div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Median / Mean</div>
                      <div className="text-xs font-bold text-cyan-400 mt-1 truncate">
                        {fleetData.summary_metrics.median ?? "—"} / {fleetData.summary_metrics.mean ?? "—"}
                      </div>
                    </div>
                  </div>

                  {/* Outliers Alert Box */}
                  {fleetData.outliers && fleetData.outliers.length > 0 && (
                    <div className="p-4 rounded-lg bg-amber-950/40 border border-amber-500/40 text-amber-200 space-y-2">
                      <div className="flex items-center gap-2 font-semibold text-xs text-amber-300">
                        <AlertTriangle className="w-4 h-4" />
                        Statistical Outliers Detected ({fleetData.outliers.length})
                      </div>
                      <div className="text-[11px] text-amber-300/80 italic">
                        Notice: Statistical outlier does not constitute an engineering defect or automatic rejection.
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
                        {fleetData.outliers.map((outlier, idx) => (
                          <div key={idx} className="p-2.5 rounded bg-zinc-900/80 border border-zinc-800 text-xs font-mono">
                            <div className="text-white font-semibold">{outlier.vehicle_ref}</div>
                            <div className="text-amber-400 mt-1">Value: {outlier.value}</div>
                            <div className="text-[10px] text-zinc-400 mt-0.5">{outlier.note}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Comparable Instances Table */}
                  <div className="rounded-lg border border-zinc-800 overflow-hidden">
                    <div className="bg-zinc-900 p-3 text-xs font-semibold uppercase font-mono text-zinc-300">
                      Comparable Fleet Instances ({fleetData.comparable_instances.length})
                    </div>
                    <table className="w-full text-xs text-left">
                      <thead className="bg-zinc-900/80 text-zinc-400 font-mono text-[11px] uppercase">
                        <tr>
                          <th className="p-3">Vehicle Ref</th>
                          <th className="p-3">Normalized Value</th>
                          <th className="p-3">Unit</th>
                          <th className="p-3">Trust State</th>
                          <th className="p-3">Validation</th>
                          <th className="p-3">Provenance</th>
                          <th className="p-3">Assessment Hash</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800 bg-zinc-900/20 font-mono">
                        {fleetData.comparable_instances.map((inst, idx) => (
                          <tr key={idx} className="hover:bg-zinc-900/40">
                            <td className="p-3 text-white font-medium">{inst.vehicle_ref}</td>
                            <td className="p-3 text-amber-400 font-bold">{inst.normalized_value}</td>
                            <td className="p-3 text-zinc-400">{inst.canonical_unit}</td>
                            <td className="p-3">{inst.trust_state}</td>
                            <td className="p-3 text-zinc-400">{inst.validation_coverage}</td>
                            <td className="p-3 text-zinc-400">{inst.provenance_class}</td>
                            <td className="p-3 text-zinc-500">{inst.assessment_hash?.slice(0, 10)}...</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Tab 7: Assembly Propagation & Sensitivity */}
          {activeTab === "propagation" && (
            <div className="space-y-6" data-testid="propagation-container">
              {/* Invariant Alert */}
              <div className="p-4 rounded-lg bg-blue-950/40 border border-blue-500/40 text-blue-200 text-xs">
                <div className="flex items-center gap-2 font-semibold text-blue-300">
                  <Layers className="w-4 h-4 shrink-0" />
                  Strict Invariant: Direct Trust is Decoupled from Propagated Impact
                </div>
                <p className="mt-1 text-zinc-300">
                  A component parameter has direct trust (e.g. PROVISIONAL or VALIDATED); an affected assembly has an impact assessment.
                  Downstream uncertainty does not rewrite local parameter trust.
                </p>
                <div className="mt-3">
                  <button
                    onClick={handleRunAssemblyImpact}
                    disabled={impactLoading}
                    className="px-4 py-1.5 text-xs font-semibold bg-blue-500 hover:bg-blue-400 text-white rounded transition flex items-center gap-1.5 disabled:opacity-50"
                    data-testid="btn-run-assembly-impact"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${impactLoading ? "animate-spin" : ""}`} />
                    {impactLoading ? "Evaluating..." : "Evaluate Assembly Impact"}
                  </button>
                </div>
              </div>

              {impactError && (
                <div className="p-3 rounded bg-red-950/40 border border-red-500/30 text-red-300 text-xs">
                  {impactError}
                </div>
              )}

              {impactData && (
                <div className="space-y-6">
                  {/* Dependency Path Breadcrumbs */}
                  {impactData.dependency_path && (
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800 text-xs font-mono text-zinc-300 flex items-center gap-2">
                      <span className="text-zinc-500 uppercase text-[10px]">Structural Lineage:</span>
                      <span className="text-amber-400 font-semibold">{impactData.dependency_path.join(" ➔ ")}</span>
                    </div>
                  )}

                  {/* Impact & Direct Trust Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Direct Parameter Assessment */}
                    <div className="p-4 rounded-lg bg-zinc-900 border border-zinc-800">
                      <div className="text-xs font-semibold uppercase font-mono text-zinc-400">
                        Direct Component Trust
                      </div>
                      <div className="mt-2 space-y-1 font-mono text-xs">
                        <div className="text-white">
                          Trust State: <span className="font-semibold text-amber-400">{impactData.direct_trust_assessment?.trust_state}</span>
                        </div>
                        <div className="text-zinc-400">
                          Coverage: {impactData.direct_trust_assessment?.validation_coverage}
                        </div>
                        <div className="text-zinc-400">
                          Conflicts: {impactData.direct_trust_assessment?.conflicts_count ?? 0}
                        </div>
                      </div>
                    </div>

                    {/* Propagated Assembly Impact */}
                    <div className="p-4 rounded-lg bg-zinc-900 border border-zinc-800">
                      <div className="text-xs font-semibold uppercase font-mono text-zinc-400">
                        Propagated Assembly Impact
                      </div>
                      <div className="mt-2 space-y-1 font-mono text-xs">
                        <div className="text-white font-semibold">
                          Classification: <span className="text-cyan-400">{impactData.impact_assessment?.impact_classification}</span>
                        </div>
                        <div className="text-zinc-300 text-[11px] mt-1 font-sans">
                          {impactData.impact_assessment?.impact_summary}
                        </div>
                        <div className="text-zinc-400 text-[10px] mt-2 pt-2 border-t border-zinc-800/80 font-mono">
                          Threshold Provenance: <span className="text-amber-300">{impactData.impact_assessment?.threshold_provenance || "PROVISIONAL"}</span> (Analytical Screening Bins)
                        </div>
                        <div className="text-zinc-500 text-[10px] mt-1 font-sans italic">
                          Deployment Safety: Independent Governance Gate (Not Inferred)
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Sensitivity Evidence Details */}
                  {impactData.sensitivity_evidence && (
                    <div className="p-4 rounded-lg bg-zinc-900/60 border border-zinc-800 space-y-3">
                      <div className="text-xs font-semibold uppercase font-mono text-zinc-300 flex items-center justify-between">
                        <span>Authoritative Sensitivity Evidence</span>
                        <span className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 text-amber-400 border border-zinc-700">
                          STATUS: {impactData.sensitivity_evidence.status}
                        </span>
                      </div>

                      {impactData.sensitivity_evidence.status === "SENSITIVITY_UNAVAILABLE" ? (
                        <div className="p-3 rounded bg-amber-950/30 border border-amber-500/30 text-amber-300 text-xs">
                          {impactData.sensitivity_evidence.warning || "Sensitivity evidence unavailable. Missing sensitivity is never treated as zero."}
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 font-mono text-xs">
                            <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                              <div className="text-[10px] text-zinc-500 uppercase">Source</div>
                              <div className="text-white truncate">{impactData.sensitivity_evidence.source_type}:{impactData.sensitivity_evidence.source_id}</div>
                            </div>
                            <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                              <div className="text-[10px] text-zinc-500 uppercase">Method</div>
                              <div className="text-white truncate">{impactData.sensitivity_evidence.method}</div>
                            </div>
                            <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                              <div className="text-[10px] text-zinc-500 uppercase">Regime</div>
                              <div className="text-white truncate">{impactData.sensitivity_evidence.operating_regime}</div>
                            </div>
                            <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                              <div className="text-[10px] text-zinc-500 uppercase">Artifact Hash</div>
                              <div className="text-zinc-400 truncate">{impactData.sensitivity_evidence.artifact_hash?.slice(0, 10)}...</div>
                            </div>
                          </div>

                          {/* Downstream KPIs */}
                          {impactData.impact_assessment?.downstream_metrics && impactData.impact_assessment.downstream_metrics.length > 0 && (
                            <div className="rounded border border-zinc-800 overflow-hidden">
                              <table className="w-full text-xs text-left">
                                <thead className="bg-zinc-900 text-zinc-400 font-mono text-[11px] uppercase">
                                  <tr>
                                    <th className="p-2.5">Downstream KPI</th>
                                    <th className="p-2.5">Sensitivity Unit</th>
                                    <th className="p-2.5">Elasticity / Magnitude</th>
                                    <th className="p-2.5">Direction</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-zinc-800 bg-zinc-900/20 font-mono">
                                  {impactData.impact_assessment.downstream_metrics.map((m: any, idx: number) => (
                                    <tr key={idx}>
                                      <td className="p-2.5 text-white font-medium">{m.metric || m.kpi}</td>
                                      <td className="p-2.5 text-zinc-400">{m.unit || "unit(y)/unit(x)"}</td>
                                      <td className="p-2.5 text-amber-400 font-semibold">{m.elasticity ?? m.sensitivity ?? "—"}</td>
                                      <td className="p-2.5 text-zinc-300">{m.direction || "—"}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
