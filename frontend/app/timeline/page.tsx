"use client";

import React, { useState, useEffect } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Award,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Compass,
  FileCheck,
  FileText,
  Filter,
  GitBranch,
  GitCommit,
  Layers,
  Lock,
  RefreshCw,
  Scale,
  ShieldCheck,
  Sliders,
  Sparkles,
  TrendingDown,
  TrendingUp,
  User,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useWorkspace } from "../../contexts/WorkspaceContext";
import {
  TimelineDecisionApi,
  TimelineEventData,
  EventComparisonReport,
  EngineeringDecisionData,
} from "../../lib/api_client";

const EVENT_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  vehicle_change: { label: "Vehicle Config", color: "bg-blue-500/20 text-blue-300 border-blue-500/40" },
  setup_change: { label: "Setup Delta", color: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40" },
  telemetry_session: { label: "Telemetry DAQ", color: "bg-purple-500/20 text-purple-300 border-purple-500/40" },
  calibration: { label: "Calibration", color: "bg-amber-500/20 text-amber-300 border-amber-500/40" },
  simulation: { label: "Forward Sim", color: "bg-indigo-500/20 text-indigo-300 border-indigo-500/40" },
  optimization: { label: "Pareto Opt", color: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" },
  validation: { label: "Holdout V&V", color: "bg-teal-500/20 text-teal-300 border-teal-500/40" },
  report: { label: "CAE Report", color: "bg-neutral-500/20 text-neutral-300 border-neutral-500/40" },
  approval: { label: "HMAC Sign-off", color: "bg-green-500/20 text-green-300 border-green-500/40" },
  track_session: { label: "Track Session", color: "bg-orange-500/20 text-orange-300 border-orange-500/40" },
  engineering_decision: { label: "Decision Record", color: "bg-yellow-500/20 text-yellow-300 border-yellow-500/40" },
};

export default function TimelinePage() {
  const { vehicle } = useWorkspace();

  const [activeTab, setActiveTab] = useState<"timeline" | "decisions" | "compare">("timeline");
  const [loading, setLoading] = useState(true);

  // Timeline events state
  const [events, setEvents] = useState<TimelineEventData[]>([]);
  const [selectedEventType, setSelectedEventType] = useState<string>("all");
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);

  // Compare mode state
  const [compareEventA, setCompareEventA] = useState<string>("");
  const [compareEventB, setCompareEventB] = useState<string>("");
  const [comparisonReport, setComparisonReport] = useState<EventComparisonReport | null>(null);
  const [loadingCompare, setLoadingCompare] = useState(false);

  // Decisions state
  const [decisions, setDecisions] = useState<EngineeringDecisionData[]>([]);
  const [selectedDecision, setSelectedDecision] = useState<EngineeringDecisionData | null>(null);
  const [signingDecisionId, setSigningDecisionId] = useState<string | null>(null);
  const [approverName, setApproverName] = useState("James Wilson");
  const [approverRole, setApproverRole] = useState("Chief Race Engineer");
  const [approvalNotes, setApprovalNotes] = useState("Approved based on telemetry correlation and 20% holdout validation.");
  const [isSubmittingApproval, setIsSubmittingApproval] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const carRef = vehicle?.name || vehicle?.id || "AMR24-EVO";
      const [eventsRes, decisionsRes] = await Promise.all([
        TimelineDecisionApi.listEvents({
          vehicle_ref: carRef,
          event_type: selectedEventType === "all" ? undefined : selectedEventType,
        }),
        TimelineDecisionApi.listDecisions({
          vehicle_ref: carRef,
        }),
      ]);
      setEvents(eventsRes.events || []);
      setDecisions(decisionsRes.decisions || []);
      if (eventsRes.events && eventsRes.events.length >= 2) {
        setCompareEventA(eventsRes.events[eventsRes.events.length - 2].id);
        setCompareEventB(eventsRes.events[eventsRes.events.length - 1].id);
      }
      if (decisionsRes.decisions && decisionsRes.decisions.length > 0) {
        setSelectedDecision(decisionsRes.decisions[0]);
      }
    } catch (err) {
      console.error("Failed to load timeline and decisions:", err);
    } finally {
      setLoading(false);
    }
  };

  const executeComparison = async () => {
    if (!compareEventA || !compareEventB) return;
    setLoadingCompare(true);
    try {
      const rep = await TimelineDecisionApi.compareEvents(compareEventA, compareEventB);
      setComparisonReport(rep);
    } catch (err) {
      console.error("Failed to compare events:", err);
    } finally {
      setLoadingCompare(false);
    }
  };

  const handleApproveDecision = async (decisionId: string) => {
    setIsSubmittingApproval(true);
    try {
      const updated = await TimelineDecisionApi.approveDecision(decisionId, {
        approver_name: approverName,
        approver_role: approverRole,
        notes: approvalNotes,
      });
      setSigningDecisionId(null);
      setSelectedDecision(updated);
      await loadData();
    } catch (err) {
      console.error("Failed to approve decision:", err);
    } finally {
      setIsSubmittingApproval(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [vehicle?.id, selectedEventType]);

  return (
    <div className="min-h-screen bg-[#0a0a0c] text-white flex flex-col font-sans">
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 space-y-6">
        {/* Header Banner */}
        <div className="bg-gradient-to-r from-neutral-900 via-neutral-900 to-blue-950/40 border border-neutral-800 rounded-xl p-6 shadow-2xl">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-xs font-mono text-cyan-400 uppercase tracking-wider mb-2">
                <Clock className="w-4 h-4 text-cyan-400" />
                <span>Vehicle Development Timeline &bull; Cryptographic Governance</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight flex items-center gap-3">
                <span>Engineering History &amp; Decision Records</span>
                <span className="text-xs px-2.5 py-1 rounded bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 font-mono font-normal">
                  HMAC-SHA256 SIGNED
                </span>
              </h1>
              <p className="mt-2 text-base text-neutral-300 font-medium">
                Immutable audit trail connecting setup evolutions, telemetry validation, and engineering decisions.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={loadData}
                disabled={loading}
                className="flex items-center gap-2 px-3 py-2 text-xs font-mono bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 text-neutral-200 rounded-lg transition-colors"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
                <span>Refresh History</span>
              </button>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="mt-6 flex flex-wrap gap-2 pt-4 border-t border-neutral-800/80">
            <button
              onClick={() => setActiveTab("timeline")}
              className={`px-4 py-2 rounded-lg text-xs font-mono uppercase tracking-wider transition-all flex items-center gap-2 ${
                activeTab === "timeline"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/50 shadow-sm"
                  : "bg-neutral-900 text-neutral-400 hover:text-white border border-neutral-800"
              }`}
            >
              <GitCommit className="w-4 h-4" />
              <span>Timeline Feed ({events.length})</span>
            </button>
            <button
              onClick={() => {
                setActiveTab("compare");
                if (!comparisonReport && events.length >= 2) {
                  executeComparison();
                }
              }}
              className={`px-4 py-2 rounded-lg text-xs font-mono uppercase tracking-wider transition-all flex items-center gap-2 ${
                activeTab === "compare"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/50 shadow-sm"
                  : "bg-neutral-900 text-neutral-400 hover:text-white border border-neutral-800"
              }`}
            >
              <Scale className="w-4 h-4" />
              <span>What Changed? (Diff Engine)</span>
            </button>
            <button
              onClick={() => setActiveTab("decisions")}
              className={`px-4 py-2 rounded-lg text-xs font-mono uppercase tracking-wider transition-all flex items-center gap-2 ${
                activeTab === "decisions"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/50 shadow-sm"
                  : "bg-neutral-900 text-neutral-400 hover:text-white border border-neutral-800"
              }`}
            >
              <FileCheck className="w-4 h-4" />
              <span>Engineering Decisions ({decisions.length})</span>
            </button>
          </div>
        </div>

        {/* TAB 1: Timeline Feed */}
        {activeTab === "timeline" && (
          <div className="space-y-4">
            {/* Filter Bar */}
            <div className="flex flex-wrap items-center justify-between gap-3 bg-neutral-900/60 border border-neutral-800 p-3 rounded-lg text-xs font-mono">
              <div className="flex items-center gap-2">
                <Filter className="w-3.5 h-3.5 text-neutral-400" />
                <span className="text-neutral-400">Filter Event Type:</span>
                <select
                  value={selectedEventType}
                  onChange={(e) => setSelectedEventType(e.target.value)}
                  className="bg-neutral-800 border border-neutral-700 text-white rounded px-2.5 py-1 text-xs focus:outline-none focus:border-cyan-500"
                >
                  <option value="all">All 11 Event Categories</option>
                  <option value="vehicle_change">Vehicle Config Changes</option>
                  <option value="setup_change">Setup Deltas</option>
                  <option value="telemetry_session">Telemetry Sessions</option>
                  <option value="calibration">Calibrations</option>
                  <option value="simulation">Simulations</option>
                  <option value="optimization">Optimizations</option>
                  <option value="validation">Holdout Validations</option>
                  <option value="track_session">Track Sessions</option>
                  <option value="engineering_decision">Engineering Decisions</option>
                  <option value="approval">HMAC Approvals</option>
                </select>
              </div>

              <div className="text-neutral-400">
                Displaying <strong>{events.length}</strong> authenticated events
              </div>
            </div>

            {/* Timeline Stream */}
            <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-3 before:bottom-3 before:w-0.5 before:bg-neutral-800">
              {events.map((ev, idx) => {
                const isExpanded = expandedEventId === ev.id;
                const typeStyle = EVENT_TYPE_LABELS[ev.event_type] || {
                  label: ev.event_type,
                  color: "bg-neutral-800 text-neutral-300 border-neutral-700",
                };

                return (
                  <div key={ev.id} className="relative group">
                    {/* Circle Node */}
                    <div className="absolute -left-6 top-4 w-3.5 h-3.5 rounded-full bg-neutral-900 border-2 border-cyan-400 group-hover:bg-cyan-400 transition-colors" />

                    <div className="bg-neutral-900/80 border border-neutral-800 hover:border-neutral-700 rounded-xl p-5 shadow-lg transition-all space-y-3">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`px-2.5 py-0.5 rounded text-[10px] font-mono font-semibold uppercase border ${typeStyle.color}`}
                          >
                            {typeStyle.label}
                          </span>
                          <span className="text-xs font-mono text-neutral-400">
                            {ev.timestamp ? new Date(ev.timestamp).toLocaleString() : "Recent"}
                          </span>
                          <span className="text-neutral-600">&bull;</span>
                          <span className="text-xs font-mono text-cyan-300 flex items-center gap-1">
                            <User className="w-3 h-3 text-cyan-400" />
                            {ev.author}
                          </span>
                        </div>

                        {/* Explicit Uncertainty State Badge */}
                        <div className="flex items-center gap-2">
                          <span
                            className={`text-[10px] font-mono px-2 py-0.5 rounded uppercase font-bold ${
                              ev.approval_status === "APPROVED"
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                                : ev.approval_status === "VALIDATED"
                                ? "bg-teal-500/20 text-teal-300 border border-teal-500/40"
                                : ev.approval_status === "RECOMMENDED"
                                ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                                : "bg-neutral-800 text-neutral-400 border border-neutral-700"
                            }`}
                          >
                            {ev.approval_status}
                          </span>
                          <button
                            onClick={() => setExpandedEventId(isExpanded ? null : ev.id)}
                            className="p-1 rounded hover:bg-neutral-800 text-neutral-400 hover:text-white"
                          >
                            {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>

                      <div>
                        <h3 className="text-base font-bold text-white">{ev.title}</h3>
                        <p className="text-xs text-neutral-300 mt-1">{ev.description}</p>
                      </div>

                      {/* Parameter changes preview */}
                      {ev.parameter_changes && ev.parameter_changes.length > 0 && (
                        <div className="flex flex-wrap gap-2 pt-1">
                          {ev.parameter_changes.map((pc, i) => (
                            <span
                              key={i}
                              className="text-[11px] font-mono bg-neutral-950 px-2 py-0.5 rounded border border-neutral-800 text-neutral-300"
                            >
                              <strong>{pc.parameter}:</strong> {pc.before} &rarr; {pc.after} ({pc.delta > 0 ? "+" : ""}
                              {pc.delta} {pc.unit})
                            </span>
                          ))}
                        </div>
                      )}

                      {/* Expanded Details */}
                      {isExpanded && (
                        <div className="mt-4 pt-4 border-t border-neutral-800/80 space-y-4 font-mono text-xs">
                          {/* Engineering Effects */}
                          {ev.engineering_effects && ev.engineering_effects.length > 0 && (
                            <div className="space-y-1">
                              <span className="text-[10px] text-neutral-400 uppercase">Engineering Effects:</span>
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                {ev.engineering_effects.map((ef, i) => (
                                  <div key={i} className="bg-neutral-950 p-2 rounded border border-neutral-800 flex justify-between items-center">
                                    <span className="text-neutral-300">{ef.metric}</span>
                                    <span className={ef.beneficial ? "text-emerald-400 font-bold" : "text-amber-400"}>
                                      {ef.before} &rarr; {ef.after} {ef.unit}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Validation Effects */}
                          {ev.validation_effects && (
                            <div className="bg-neutral-950 p-3 rounded border border-neutral-800 flex items-center justify-between">
                              <div className="space-y-0.5">
                                <span className="text-[10px] text-neutral-400 uppercase">Empirical Validation</span>
                                <div className="text-neutral-200">
                                  Holdout R&sup2;: <strong className="text-emerald-400">{ev.validation_effects.holdout_r2}</strong> &bull; Overall R&sup2;: <strong>{ev.validation_effects.overall_r2}</strong>
                                </div>
                              </div>
                              <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-bold">
                                {ev.validation_effects.status}
                              </span>
                            </div>
                          )}

                          {/* Decision consequences */}
                          {ev.decision_consequences && ev.decision_consequences.length > 0 && (
                            <div className="space-y-1">
                              <span className="text-[10px] text-neutral-400 uppercase">Consequences &amp; Downstream Impact:</span>
                              <ul className="list-disc pl-4 space-y-0.5 text-neutral-300 text-[11px]">
                                {ev.decision_consequences.map((c, i) => (
                                  <li key={i}>{c}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Provenance Hash */}
                          <div className="pt-2 text-[10px] text-neutral-500 flex items-center justify-between">
                            <span className="truncate">
                              SHA-256 Fingerprint: <span className="text-cyan-400">{ev.provenance_hash}</span>
                            </span>
                            <span>Model: {ev.model_version}</span>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* TAB 2: What Changed? (Comparison Engine) */}
        {activeTab === "compare" && (
          <div className="space-y-6">
            <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-6 shadow-xl space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <Scale className="w-5 h-5 text-cyan-400" />
                    <span>Comparative Diff Engine: &ldquo;What Changed?&rdquo;</span>
                  </h2>
                  <p className="text-xs text-neutral-400 font-mono mt-0.5">
                    Select any two timeline events to perform side-by-side delta verification.
                  </p>
                </div>

                <button
                  onClick={executeComparison}
                  disabled={loadingCompare || !compareEventA || !compareEventB}
                  className="px-4 py-2 text-xs font-semibold uppercase tracking-wider bg-cyan-600 hover:bg-cyan-500 disabled:bg-neutral-800 text-white rounded-lg shadow-lg transition-colors flex items-center gap-2 shrink-0"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${loadingCompare ? "animate-spin" : ""}`} />
                  <span>Execute Diff Analysis</span>
                </button>
              </div>

              {/* Event Selectors */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                <div className="space-y-1">
                  <label className="text-xs font-mono text-neutral-400 uppercase">Baseline Event (A):</label>
                  <select
                    value={compareEventA}
                    onChange={(e) => setCompareEventA(e.target.value)}
                    className="w-full bg-neutral-950 border border-neutral-800 text-white rounded-lg p-2.5 text-xs font-mono focus:outline-none focus:border-cyan-500"
                  >
                    {events.map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.title} ({e.event_type})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-mono text-neutral-400 uppercase">Comparison Event (B):</label>
                  <select
                    value={compareEventB}
                    onChange={(e) => setCompareEventB(e.target.value)}
                    className="w-full bg-neutral-950 border border-neutral-800 text-white rounded-lg p-2.5 text-xs font-mono focus:outline-none focus:border-cyan-500"
                  >
                    {events.map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.title} ({e.event_type})
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            {/* Comparison Results */}
            {comparisonReport && (
              <div className="space-y-6 animate-in fade-in duration-300">
                {/* Event Summary Banners */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 font-mono text-xs">
                  <div className="bg-neutral-900/60 border border-neutral-800 rounded-xl p-4 space-y-1">
                    <span className="text-[10px] text-cyan-400 uppercase font-bold">EVENT A (BASELINE)</span>
                    <div className="text-sm font-bold text-white font-sans">{comparisonReport.event_a.title}</div>
                    <div className="text-neutral-400 text-[11px]">{comparisonReport.event_a.description}</div>
                  </div>
                  <div className="bg-neutral-900/60 border border-neutral-800 rounded-xl p-4 space-y-1">
                    <span className="text-[10px] text-purple-400 uppercase font-bold">EVENT B (CANDIDATE)</span>
                    <div className="text-sm font-bold text-white font-sans">{comparisonReport.event_b.title}</div>
                    <div className="text-neutral-400 text-[11px]">{comparisonReport.event_b.description}</div>
                  </div>
                </div>

                {/* Parameter Changes Matrix */}
                <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-6 shadow-xl space-y-4">
                  <h3 className="text-sm font-bold text-white uppercase font-mono tracking-wider flex items-center gap-2">
                    <Sliders className="w-4 h-4 text-cyan-400" />
                    <span>Physical Parameter Deltas</span>
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left font-mono text-xs">
                      <thead>
                        <tr className="border-b border-neutral-800 text-[10px] uppercase text-neutral-400">
                          <th className="py-2.5 px-3">Parameter</th>
                          <th className="py-2.5 px-3">State in Event A</th>
                          <th className="py-2.5 px-3">State in Event B</th>
                          <th className="py-2.5 px-3">Absolute Delta (&Delta;)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-neutral-800/60">
                        {comparisonReport.parameter_deltas.map((pd, i) => (
                          <tr key={i} className="hover:bg-neutral-800/30">
                            <td className="py-3 px-3 font-sans font-medium text-white">{pd.parameter}</td>
                            <td className="py-3 px-3 text-neutral-300">
                              {pd.a} {pd.unit}
                            </td>
                            <td className="py-3 px-3 text-neutral-300">
                              {pd.b} {pd.unit}
                            </td>
                            <td className="py-3 px-3">
                              <span className={`font-bold ${pd.delta > 0 ? "text-cyan-400" : "text-amber-400"}`}>
                                {pd.delta > 0 ? `+${pd.delta}` : pd.delta} {pd.unit}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Engineering Effects Deltas */}
                <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-6 shadow-xl space-y-4">
                  <h3 className="text-sm font-bold text-white uppercase font-mono tracking-wider flex items-center gap-2">
                    <Activity className="w-4 h-4 text-emerald-400" />
                    <span>Engineering Performance Consequences</span>
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {comparisonReport.engineering_effect_deltas.map((ef, i) => (
                      <div key={i} className="bg-neutral-950 border border-neutral-800 rounded-lg p-3.5 space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-semibold text-white">{ef.metric}</span>
                          <span
                            className={`font-mono text-xs px-2 py-0.5 rounded font-bold ${
                              ef.beneficial ? "bg-emerald-500/20 text-emerald-300" : "bg-amber-500/20 text-amber-300"
                            }`}
                          >
                            {ef.delta > 0 ? `+${ef.delta}` : ef.delta} {ef.unit}
                          </span>
                        </div>
                        <div className="text-[11px] font-mono text-neutral-400 flex justify-between">
                          <span>A: {ef.a} {ef.unit}</span>
                          <span>B: {ef.b} {ef.unit}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: Engineering Decision Records */}
        {activeTab === "decisions" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Decision List Column */}
            <div className="lg:col-span-1 space-y-3">
              <span className="text-xs font-mono uppercase text-neutral-400 tracking-wider">
                Decision Records ({decisions.length})
              </span>
              <div className="space-y-2">
                {decisions.map((d) => {
                  const isSelected = selectedDecision?.id === d.id;
                  return (
                    <div
                      key={d.id}
                      onClick={() => setSelectedDecision(d)}
                      className={`cursor-pointer p-4 rounded-xl border transition-all space-y-2 ${
                        isSelected
                          ? "bg-neutral-900 border-cyan-400 shadow-lg"
                          : "bg-neutral-900/60 border-neutral-800 hover:border-neutral-700"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono font-bold text-cyan-400">{d.decision_id_display}</span>
                        <span
                          className={`text-[10px] font-mono px-2 py-0.5 rounded uppercase font-bold ${
                            d.status === "APPROVED"
                              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                              : d.status === "VALIDATED"
                              ? "bg-teal-500/20 text-teal-300 border border-teal-500/40"
                              : "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                          }`}
                        >
                          {d.status}
                        </span>
                      </div>
                      <h4 className="text-sm font-bold text-white line-clamp-1">{d.title}</h4>
                      <p className="text-xs text-neutral-400 line-clamp-2">{d.question}</p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Decision Record Details Column */}
            <div className="lg:col-span-2">
              {selectedDecision ? (
                <div className="bg-neutral-900/90 border border-neutral-800 rounded-xl p-6 shadow-xl space-y-6">
                  {/* Top Bar with Approval Status */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-neutral-800">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold text-cyan-400">{selectedDecision.decision_id_display}</span>
                        <span className="text-xs text-neutral-500">&bull;</span>
                        <span className="text-xs font-mono text-neutral-400">{selectedDecision.vehicle_ref}</span>
                      </div>
                      <h2 className="text-xl font-extrabold text-white mt-1">{selectedDecision.title}</h2>
                    </div>

                    <div className="flex items-center gap-3">
                      <span
                        className={`text-xs font-mono px-3 py-1 rounded-lg uppercase font-bold ${
                          selectedDecision.status === "APPROVED"
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                            : "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                        }`}
                      >
                        {selectedDecision.status}
                      </span>
                      {selectedDecision.status !== "APPROVED" && (
                        <button
                          onClick={() => setSigningDecisionId(selectedDecision.id)}
                          className="px-3 py-1.5 text-xs font-semibold uppercase tracking-wider bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition-colors flex items-center gap-1.5"
                        >
                          <Lock className="w-3.5 h-3.5" />
                          <span>Sign Decision (HMAC)</span>
                        </button>
                      )}
                    </div>
                  </div>

                  {/* The Core Question */}
                  <div className="bg-neutral-950/80 border border-neutral-800 rounded-lg p-4 space-y-1">
                    <span className="text-[10px] font-mono text-cyan-400 uppercase font-bold">The Engineering Question</span>
                    <p className="text-sm font-semibold text-white italic">&ldquo;{selectedDecision.question}&rdquo;</p>
                  </div>

                  {/* Context Dimensions */}
                  <div className="space-y-2">
                    <span className="text-xs font-mono uppercase text-neutral-400 tracking-wider">Context &bull; Operating Conditions</span>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono text-xs">
                      <div className="bg-neutral-950 p-2.5 rounded border border-neutral-800">
                        <span className="text-[10px] text-neutral-500">Track:</span>
                        <div className="text-neutral-200 font-bold">{selectedDecision.context_data?.track || "Silverstone"}</div>
                      </div>
                      <div className="bg-neutral-950 p-2.5 rounded border border-neutral-800">
                        <span className="text-[10px] text-neutral-500">Speed Band:</span>
                        <div className="text-neutral-200 font-bold">{selectedDecision.context_data?.speed_band || "High Speed (240+)"}</div>
                      </div>
                      <div className="bg-neutral-950 p-2.5 rounded border border-neutral-800">
                        <span className="text-[10px] text-neutral-500">Weather / Ambient:</span>
                        <div className="text-neutral-200 font-bold">{selectedDecision.context_data?.weather || "Dry, 26°C"}</div>
                      </div>
                      <div className="bg-neutral-950 p-2.5 rounded border border-neutral-800">
                        <span className="text-[10px] text-neutral-500">Tire Compound:</span>
                        <div className="text-neutral-200 font-bold">{selectedDecision.context_data?.tire_compound || "C3 Medium"}</div>
                      </div>
                    </div>
                  </div>

                  {/* Selected Option & Engineering Reason */}
                  <div className="space-y-3">
                    <div className="bg-emerald-950/20 border border-emerald-500/40 rounded-xl p-4 space-y-1.5">
                      <span className="text-xs font-mono uppercase text-emerald-400 font-bold">Selected Decision Option</span>
                      <div className="text-base font-bold text-white">{selectedDecision.selected_option}</div>
                      <p className="text-xs text-neutral-300 mt-1">{selectedDecision.engineering_reason}</p>
                    </div>
                  </div>

                  {/* Three Pillars of Evidence */}
                  <div className="space-y-3">
                    <span className="text-xs font-mono uppercase text-neutral-400 tracking-wider">
                      Three Pillars of Physical Evidence
                    </span>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 font-mono text-xs">
                      {/* Simulation Pillar */}
                      <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3.5 space-y-2">
                        <span className="text-[10px] font-bold text-indigo-400 uppercase">1. Simulation Evidence</span>
                        <div className="text-neutral-300 text-[11px] leading-relaxed">
                          {selectedDecision.simulation_evidence?.summary || <span className="text-neutral-500 italic">No simulation evidence summary available.</span>}
                        </div>
                      </div>

                      {/* Telemetry Pillar */}
                      <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3.5 space-y-2">
                        <span className="text-[10px] font-bold text-purple-400 uppercase">2. Telemetry Evidence</span>
                        <div className="text-neutral-300 text-[11px] leading-relaxed">
                          {selectedDecision.telemetry_evidence?.summary || <span className="text-neutral-500 italic">No telemetry evidence summary available.</span>}
                        </div>
                      </div>

                      {/* Validation Pillar */}
                      <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3.5 space-y-2">
                        <span className="text-[10px] font-bold text-teal-400 uppercase">3. Holdout Validation</span>
                        <div className="text-neutral-300 text-[11px] leading-relaxed">
                          {selectedDecision.validation_evidence?.holdout_r2 != null
                            ? <>Holdout R&sup2;: <strong className="text-emerald-400">{selectedDecision.validation_evidence.holdout_r2}</strong> without leakage.</>
                            : <span className="text-neutral-500 italic">No holdout validation data available.</span>}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* HMAC Signature Card */}
                  {selectedDecision.status === "APPROVED" && selectedDecision.approval_signature_hmac && (
                    <div className="bg-neutral-950 border border-emerald-500/40 rounded-xl p-4 space-y-2 font-mono text-xs">
                      <div className="flex items-center justify-between">
                        <span className="text-emerald-400 font-bold flex items-center gap-1.5 uppercase text-[11px]">
                          <ShieldCheck className="w-4 h-4 text-emerald-400" />
                          Cryptographic Sign-off Active
                        </span>
                        <span className="text-neutral-400 text-[11px]">{selectedDecision.approved_at}</span>
                      </div>
                      <div className="text-neutral-300">
                        Signed by: <strong>{selectedDecision.approved_by}</strong> ({selectedDecision.approver_role})
                      </div>
                      <div className="p-2 bg-black/60 rounded border border-neutral-800 text-[10px] text-neutral-400 truncate">
                        HMAC-SHA256: <span className="text-emerald-400">{selectedDecision.approval_signature_hmac}</span>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="bg-neutral-900/40 border border-neutral-800 rounded-xl p-12 text-center text-neutral-400">
                  Select a decision record to view complete evidence and cryptographic sign-off.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Modal: HMAC Sign-off */}
        {signingDecisionId && (
          <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-neutral-900 border border-neutral-700 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-neutral-800">
                <div className="flex items-center gap-2">
                  <Lock className="w-5 h-5 text-emerald-400" />
                  <h3 className="text-lg font-bold text-white">Cryptographic Decision Sign-off</h3>
                </div>
                <button onClick={() => setSigningDecisionId(null)} className="text-neutral-400 hover:text-white text-xs font-mono">
                  Cancel
                </button>
              </div>

              <div className="space-y-3 font-mono text-xs">
                <div>
                  <label className="block text-neutral-400 mb-1">Approver Full Name:</label>
                  <input
                    type="text"
                    value={approverName}
                    onChange={(e) => setApproverName(e.target.value)}
                    className="w-full bg-neutral-950 border border-neutral-800 text-white rounded p-2 focus:outline-none focus:border-cyan-500"
                  />
                </div>
                <div>
                  <label className="block text-neutral-400 mb-1">Engineering Role / Title:</label>
                  <input
                    type="text"
                    value={approverRole}
                    onChange={(e) => setApproverRole(e.target.value)}
                    className="w-full bg-neutral-950 border border-neutral-800 text-white rounded p-2 focus:outline-none focus:border-cyan-500"
                  />
                </div>
                <div>
                  <label className="block text-neutral-400 mb-1">Engineering Rationale &amp; Notes:</label>
                  <textarea
                    rows={3}
                    value={approvalNotes}
                    onChange={(e) => setApprovalNotes(e.target.value)}
                    className="w-full bg-neutral-950 border border-neutral-800 text-white rounded p-2 focus:outline-none focus:border-cyan-500"
                  />
                </div>
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  onClick={() => setSigningDecisionId(null)}
                  className="px-3 py-1.5 text-xs font-mono bg-neutral-800 text-neutral-300 rounded"
                >
                  Cancel
                </button>
                <button
                  onClick={() => handleApproveDecision(signingDecisionId)}
                  disabled={isSubmittingApproval}
                  className="px-4 py-2 text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg shadow-lg transition-colors flex items-center gap-1.5"
                >
                  <ShieldCheck className="w-4 h-4" />
                  <span>{isSubmittingApproval ? "Generating HMAC..." : "Apply HMAC-SHA256 Signature"}</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
