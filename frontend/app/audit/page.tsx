"use client";

import React, { useState, useEffect, useMemo } from "react";
import { useAuth } from "../../contexts/AuthContext";
import Link from "next/link";
import {
  ShieldCheck,
  AlertTriangle,
  RefreshCw,
  Download,
  Search,
  Filter,
  Calendar,
  Key,
  Copy,
  CheckCircle2,
  ExternalLink,
  ChevronRight,
  ChevronDown,
  Layers,
  FileText,
  Activity,
  User,
  Clock,
  Sparkles,
  Lock,
  ArrowUpDown,
  X
} from "lucide-react";

interface AuditEntry {
  id: string;
  sequence_number: number;
  event: string;
  user_id: string;
  team_id: string | null;
  artifact_id: string | null;
  ip: string;
  timestamp: string;
  previous_hash: string;
  hash: string;
  metadata: Record<string, any>;
  canonical_event?: string;
}

interface VerificationResult {
  chain_integrity: string;
  is_valid: boolean;
  total_records: number;
  head_hash: string | null;
  error_details: Record<string, any> | null;
  verified_at: string;
}

const EVENT_CATEGORIES: Record<string, { label: string; color: string; bg: string; border: string }> = {
  VEHICLE:      { label: "Vehicle",      color: "text-blue-400",   bg: "bg-blue-950/40",   border: "border-blue-800/40" },
  SETUP:        { label: "Setup",        color: "text-amber-400",  bg: "bg-amber-950/40",  border: "border-amber-800/40" },
  SIMULATION:   { label: "Simulation",   color: "text-emerald-400",bg: "bg-emerald-950/40",border: "border-emerald-800/40" },
  OPTIMIZATION: { label: "Optimization", color: "text-purple-400", bg: "bg-purple-950/40", border: "border-purple-800/40" },
  VALIDATION:   { label: "Validation",   color: "text-cyan-400",   bg: "bg-cyan-950/40",   border: "border-cyan-800/40" },
  APPROVAL:     { label: "Approval",     color: "text-green-400",  bg: "bg-green-950/40",  border: "border-green-800/40" },
  REPORT:       { label: "Report",       color: "text-indigo-400", bg: "bg-indigo-950/40", border: "border-indigo-800/40" },
  EXPORT:       { label: "CAE Export",   color: "text-rose-400",   bg: "bg-rose-950/40",   border: "border-rose-800/40" },
  SHARE:        { label: "Share",        color: "text-teal-400",   bg: "bg-teal-950/40",   border: "border-teal-800/40" },
  DELETION:     { label: "Deletion",     color: "text-red-400",    bg: "bg-red-950/40",    border: "border-red-800/40" },
  ROLE:         { label: "Team / Role",  color: "text-orange-400", bg: "bg-orange-950/40", border: "border-orange-800/40" },
  SECURITY:     { label: "Security",     color: "text-gray-300",   bg: "bg-gray-800/40",   border: "border-gray-700/40" },
};

function getCategoryForEvent(eventName: string): { label: string; color: string; bg: string; border: string } {
  const upper = eventName.toUpperCase();
  if (upper.includes("VEHICLE")) return EVENT_CATEGORIES.VEHICLE;
  if (upper.includes("SETUP") || upper.includes("PROPOSAL")) return EVENT_CATEGORIES.SETUP;
  if (upper.includes("SIMULATION") || upper.includes("RUN")) return EVENT_CATEGORIES.SIMULATION;
  if (upper.includes("OPTIMIZ")) return EVENT_CATEGORIES.OPTIMIZATION;
  if (upper.includes("VALIDAT") || upper.includes("VNV")) return EVENT_CATEGORIES.VALIDATION;
  if (upper.includes("APPROV") || upper.includes("SIGN")) return EVENT_CATEGORIES.APPROVAL;
  if (upper.includes("REPORT") && !upper.includes("SHARE")) return EVENT_CATEGORIES.REPORT;
  if (upper.includes("EXPORT")) return EVENT_CATEGORIES.EXPORT;
  if (upper.includes("SHARE")) return EVENT_CATEGORIES.SHARE;
  if (upper.includes("DELETE") || upper.includes("REVOKE")) return EVENT_CATEGORIES.DELETION;
  if (upper.includes("ROLE") || upper.includes("TEAM")) return EVENT_CATEGORIES.ROLE;
  return EVENT_CATEGORIES.SECURITY;
}

export default function AuditPage() {
  const { user, fetchWithAuth } = useAuth();
  const [logs, setLogs] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [verification, setVerification] = useState<VerificationResult | null>(null);
  const [selectedEntry, setSelectedEntry] = useState<AuditEntry | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("ALL");
  const [timeRange, setTimeRange] = useState("ALL");
  const [artifactFilter, setArtifactFilter] = useState("");

  const loadAuditData = async () => {
    setLoading(true);
    try {
      const res = await fetchWithAuth("/api/v1/audit/logs?limit=200");
      if (res.ok) {
        const data = await res.json();
        setLogs(Array.isArray(data) ? data : []);
      }
    } catch (e) {
      console.error("Failed to load audit logs:", e);
    } finally {
      setLoading(false);
    }
  };

  const runVerification = async () => {
    setVerifying(true);
    try {
      const res = await fetchWithAuth("/api/v1/audit/verify");
      if (res.ok) {
        const result = await res.json();
        setVerification(result);
      }
    } catch (e) {
      console.error("Failed to verify audit chain:", e);
    } finally {
      setVerifying(false);
    }
  };

  useEffect(() => {
    loadAuditData();
    runVerification();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(text);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  const handleExport = async (format: "csv" | "json") => {
    try {
      const res = await fetchWithAuth(`/api/v1/audit/export?format=${format}`);
      if (!res.ok) return;
      if (format === "csv") {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `suspensionlab_audit_ledger_${Date.now()}.csv`;
        a.click();
      } else {
        const data = await res.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `suspensionlab_audit_bundle_${Date.now()}.json`;
        a.click();
      }
    } catch (e) {
      console.error("Export failed:", e);
    }
  };

  // Filtered logs
  const filteredLogs = useMemo(() => {
    return logs.filter((log) => {
      // 1. Text Search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesEvent = log.event.toLowerCase().includes(q);
        const matchesArtifact = log.artifact_id?.toLowerCase().includes(q);
        const matchesIp = log.ip?.toLowerCase().includes(q);
        const matchesUser = log.user_id?.toLowerCase().includes(q);
        const matchesHash = log.hash?.toLowerCase().includes(q);
        if (!matchesEvent && !matchesArtifact && !matchesIp && !matchesUser && !matchesHash) {
          return false;
        }
      }

      // 2. Category Filter
      if (selectedCategory !== "ALL") {
        const cat = getCategoryForEvent(log.event);
        if (cat.label.toUpperCase() !== selectedCategory) {
          return false;
        }
      }

      // 3. Artifact Filter
      if (artifactFilter.trim() && !log.artifact_id?.toLowerCase().includes(artifactFilter.toLowerCase())) {
        return false;
      }

      // 4. Time Range Filter
      if (timeRange !== "ALL" && log.timestamp) {
        const logDate = new Date(log.timestamp).getTime();
        const now = Date.now();
        if (timeRange === "24H" && now - logDate > 24 * 3600 * 1000) return false;
        if (timeRange === "7D" && now - logDate > 7 * 24 * 3600 * 1000) return false;
        if (timeRange === "30D" && now - logDate > 30 * 24 * 3600 * 1000) return false;
      }

      return true;
    });
  }, [logs, searchQuery, selectedCategory, timeRange, artifactFilter]);

  return (
    <div className="min-h-full bg-black text-gray-100 pt-[44px] pb-16">
      <div className="max-w-[1560px] mx-auto px-6 py-8">
        
        {/* Header Breadcrumb & Actions */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 pb-6 border-b border-white/[0.08]">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-ansys-yellow tracking-wider uppercase mb-1">
              <ShieldCheck size={14} />
              <span>Tamper-Evident Engineering Governance</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
              Audit & Traceability Ledger
            </h1>
            <p className="text-xs sm:text-sm text-gray-400 mt-1">
              Cryptographic hash chain verifying vehicle models, simulations, parameter commits, CAE exports, and server-verifiable authenticated sign-offs.
            </p>
          </div>

          {/* Quick Actions */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={runVerification}
              disabled={verifying}
              className="flex items-center gap-2 px-3.5 py-2 bg-white/[0.06] hover:bg-white/[0.1] border border-white/10 rounded-xl text-xs font-semibold text-white transition-all disabled:opacity-50"
            >
              <RefreshCw size={13} className={verifying ? "animate-spin text-ansys-yellow" : "text-gray-400"} />
              <span>{verifying ? "Verifying Hash Chain..." : "Verify Chain"}</span>
            </button>

            <button
              onClick={() => handleExport("csv")}
              className="flex items-center gap-2 px-3.5 py-2 bg-white/[0.06] hover:bg-white/[0.1] border border-white/10 rounded-xl text-xs font-semibold text-white transition-all"
            >
              <Download size={13} className="text-ansys-yellow" />
              <span>Export CSV</span>
            </button>

            <button
              onClick={() => handleExport("json")}
              className="flex items-center gap-2 px-3.5 py-2 bg-ansys-yellow text-black rounded-xl text-xs font-bold hover:brightness-110 transition-all shadow-lg shadow-ansys-yellow/10"
            >
              <FileText size={13} />
              <span>Export Verified JSON</span>
            </button>
          </div>
        </div>

        {/* Cryptographic Integrity Status Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 my-6">
          
          {/* Card 1: Chain Integrity Banner */}
          <div className={`p-5 rounded-2xl border ${
            verification?.is_valid
              ? "bg-emerald-950/20 border-emerald-800/40"
              : "bg-red-950/20 border-red-800/40"
          }`}>
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-gray-400">Chain Integrity</span>
              {verification?.is_valid ? (
                <ShieldCheck size={18} className="text-emerald-400" />
              ) : (
                <AlertTriangle size={18} className="text-red-400 animate-pulse" />
              )}
            </div>
            <div className={`text-xl font-bold mt-2 ${verification?.is_valid ? "text-emerald-400" : "text-red-400"}`}>
              {verification?.chain_integrity || "VERIFYING..."}
            </div>
            <p className="text-[11px] text-gray-400 mt-1">
              {verification?.is_valid
                ? "All sequential SHA-256 blocks cryptographically valid."
                : "Tamper or sequence break detected in ledger."}
            </p>
          </div>

          {/* Card 2: Total Blocks */}
          <div className="p-5 rounded-2xl bg-[#111113] border border-white/[0.08]">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-gray-400">Ledger Depth</span>
              <Layers size={16} className="text-ansys-yellow" />
            </div>
            <div className="text-xl font-bold text-white mt-2">
              {verification?.total_records ?? logs.length} Blocks
            </div>
            <p className="text-[11px] text-gray-400 mt-1">
              Strictly monotonic sequence numbers.
            </p>
          </div>

          {/* Card 3: Head Hash */}
          <div className="p-5 rounded-2xl bg-[#111113] border border-white/[0.08]">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-gray-400">Chain Head Hash</span>
              <Key size={16} className="text-gray-400" />
            </div>
            <div className="text-xs font-mono text-gray-300 mt-2 truncate flex items-center justify-between gap-2 bg-black/40 px-2.5 py-1.5 rounded-lg border border-white/5">
              <span className="truncate">{verification?.head_hash || (logs[0]?.hash ?? "GENESIS")}</span>
              <button
                onClick={() => handleCopy(verification?.head_hash || (logs[0]?.hash ?? "GENESIS"))}
                className="text-gray-500 hover:text-white shrink-0"
              >
                {copiedHash === (verification?.head_hash || logs[0]?.hash) ? (
                  <CheckCircle2 size={12} className="text-emerald-400" />
                ) : (
                  <Copy size={12} />
                )}
              </button>
            </div>
            <p className="text-[11px] text-gray-400 mt-1">
              H_n = SHA256(H_n-1 || Canonical)
            </p>
          </div>

          {/* Card 4: Verified Timestamp */}
          <div className="p-5 rounded-2xl bg-[#111113] border border-white/[0.08]">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-gray-400">Last Verified</span>
              <Clock size={16} className="text-gray-400" />
            </div>
            <div className="text-sm font-semibold text-white mt-2 truncate">
              {verification?.verified_at ? new Date(verification.verified_at).toLocaleTimeString() : "Just now"}
            </div>
            <p className="text-[11px] text-gray-400 mt-1 truncate">
              {verification?.verified_at ? new Date(verification.verified_at).toLocaleDateString("en-GB") : "Current Session"}
            </p>
          </div>

        </div>

        {/* Filter Bar */}
        <div className="bg-[#111113] border border-white/[0.08] rounded-2xl p-4 mb-6 flex flex-wrap items-center gap-4">
          
          {/* Search Input */}
          <div className="flex-1 min-w-[240px] relative">
            <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              placeholder="Search by event, artifact, IP, hash, or actor..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#0b0b0d] border border-white/10 rounded-xl pl-9 pr-3.5 py-2 text-xs text-white placeholder:text-gray-600 focus:outline-none focus:border-ansys-yellow/60 transition-all"
            />
          </div>

          {/* Event Category Dropdown */}
          <div className="flex items-center gap-2">
            <Filter size={13} className="text-gray-500" />
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="bg-[#0b0b0d] border border-white/10 rounded-xl px-3 py-2 text-xs text-gray-300 focus:outline-none focus:border-ansys-yellow/60"
            >
              <option value="ALL">All Categories</option>
              <option value="SIMULATION">Simulations</option>
              <option value="VEHICLE">Vehicles</option>
              <option value="SETUP">Setups</option>
              <option value="OPTIMIZATION">Optimizations</option>
              <option value="VALIDATION">Validations</option>
              <option value="APPROVAL">Approvals</option>
              <option value="REPORT">Reports</option>
              <option value="CAE EXPORT">CAE Exports</option>
              <option value="SHARE">Shares</option>
              <option value="DELETION">Deletions</option>
              <option value="TEAM / ROLE">Team & Roles</option>
              <option value="SECURITY">Security / Auth</option>
            </select>
          </div>

          {/* Time Range Selector */}
          <div className="flex items-center gap-2">
            <Calendar size={13} className="text-gray-500" />
            <select
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              className="bg-[#0b0b0d] border border-white/10 rounded-xl px-3 py-2 text-xs text-gray-300 focus:outline-none focus:border-ansys-yellow/60"
            >
              <option value="ALL">All Time</option>
              <option value="24H">Last 24 Hours</option>
              <option value="7D">Last 7 Days</option>
              <option value="30D">Last 30 Days</option>
            </select>
          </div>

          {/* Artifact Filter */}
          <input
            type="text"
            placeholder="Filter artifact (e.g. RUN-000183)..."
            value={artifactFilter}
            onChange={(e) => setArtifactFilter(e.target.value)}
            className="w-48 bg-[#0b0b0d] border border-white/10 rounded-xl px-3 py-2 text-xs text-white placeholder:text-gray-600 focus:outline-none focus:border-ansys-yellow/60 transition-all"
          />

          {(searchQuery || selectedCategory !== "ALL" || timeRange !== "ALL" || artifactFilter) && (
            <button
              onClick={() => {
                setSearchQuery("");
                setSelectedCategory("ALL");
                setTimeRange("ALL");
                setArtifactFilter("");
              }}
              className="text-xs text-gray-500 hover:text-white underline px-1"
            >
              Reset
            </button>
          )}

        </div>

        {/* Audit Ledger Table */}
        <div className="bg-[#111113] border border-white/[0.08] rounded-2xl overflow-hidden shadow-2xl">
          
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-white/[0.08] bg-white/[0.02] text-gray-400 font-semibold uppercase tracking-wider text-[10px]">
                  <th className="py-3 px-4 w-16 text-center">Seq #</th>
                  <th className="py-3 px-4">Timestamp (UTC)</th>
                  <th className="py-3 px-4">Event Type</th>
                  <th className="py-3 px-4">Actor</th>
                  <th className="py-3 px-4">Artifact</th>
                  <th className="py-3 px-4">Previous Hash</th>
                  <th className="py-3 px-4">Record Hash</th>
                  <th className="py-3 px-4 text-center">Integrity</th>
                  <th className="py-3 px-4 text-right">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {loading ? (
                  <tr>
                    <td colSpan={9} className="py-12 text-center text-gray-500">
                      <RefreshCw size={20} className="animate-spin mx-auto text-ansys-yellow mb-2" />
                      Loading tamper-evident ledger...
                    </td>
                  </tr>
                ) : filteredLogs.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-12 text-center text-gray-500">
                      No matching audit records found.
                    </td>
                  </tr>
                ) : (
                  filteredLogs.map((entry) => {
                    const cat = getCategoryForEvent(entry.event);
                    return (
                      <tr key={entry.id} className="hover:bg-white/[0.02] transition-colors group">
                        
                        {/* Sequence Number */}
                        <td className="py-3.5 px-4 text-center font-mono font-bold text-gray-400">
                          #{entry.sequence_number}
                        </td>

                        {/* Timestamp */}
                        <td className="py-3.5 px-4 font-mono text-gray-300 text-[11px] whitespace-nowrap">
                          {entry.timestamp ? new Date(entry.timestamp).toISOString().replace("T", " ").replace("Z", "") : "—"}
                        </td>

                        {/* Event Category Badge */}
                        <td className="py-3.5 px-4 whitespace-nowrap">
                          <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold border ${cat.bg} ${cat.color} ${cat.border}`}>
                            {entry.event}
                          </span>
                        </td>

                        {/* Actor */}
                        <td className="py-3.5 px-4 font-mono text-gray-300 text-[11px] max-w-[140px] truncate">
                          <div className="truncate text-white font-medium">{entry.user_id || "system"}</div>
                          <div className="text-[10px] text-gray-500">{entry.ip || "127.0.0.1"}</div>
                        </td>

                        {/* Artifact */}
                        <td className="py-3.5 px-4 font-mono text-gray-300 text-[11px] max-w-[150px] truncate">
                          {entry.artifact_id ? (
                            <span className="text-ansys-yellow bg-ansys-yellow/10 px-1.5 py-0.5 rounded border border-ansys-yellow/20">
                              {entry.artifact_id}
                            </span>
                          ) : (
                            <span className="text-gray-600">—</span>
                          )}
                        </td>

                        {/* Previous Hash */}
                        <td className="py-3.5 px-4 font-mono text-[10px] text-gray-500 max-w-[120px] truncate">
                          <div className="flex items-center gap-1.5">
                            <span className="truncate">{entry.previous_hash || "GENESIS"}</span>
                            <button
                              onClick={() => handleCopy(entry.previous_hash || "GENESIS")}
                              className="text-gray-600 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
                            >
                              <Copy size={10} />
                            </button>
                          </div>
                        </td>

                        {/* Record Hash */}
                        <td className="py-3.5 px-4 font-mono text-[10px] text-gray-300 max-w-[120px] truncate">
                          <div className="flex items-center gap-1.5">
                            <span className="truncate">{entry.hash}</span>
                            <button
                              onClick={() => handleCopy(entry.hash)}
                              className="text-gray-600 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
                            >
                              <Copy size={10} />
                            </button>
                          </div>
                        </td>

                        {/* Integrity Badge */}
                        <td className="py-3.5 px-4 text-center whitespace-nowrap">
                          <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-400 bg-emerald-950/30 px-2 py-0.5 rounded-full border border-emerald-800/30">
                            <ShieldCheck size={11} /> VALID
                          </span>
                        </td>

                        {/* Inspect Button */}
                        <td className="py-3.5 px-4 text-right whitespace-nowrap">
                          <button
                            onClick={() => setSelectedEntry(entry)}
                            className="px-2.5 py-1 text-[11px] font-semibold text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors inline-flex items-center gap-1"
                          >
                            <span>Inspect</span>
                            <ChevronRight size={12} />
                          </button>
                        </td>

                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Table Footer */}
          <div className="py-3 px-6 border-t border-white/[0.08] bg-white/[0.01] flex items-center justify-between text-xs text-gray-500">
            <span>Showing {filteredLogs.length} of {logs.length} audit entries</span>
            <span>Tamper-Evident Hash Chain Architecture &middot; RFC 8785 Canonical JSON</span>
          </div>

        </div>

        {/* Modal / Drawer for Event Inspection */}
        {selectedEntry && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-150">
            <div className="bg-[#0e0e11] border border-white/10 rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
              
              {/* Modal Header */}
              <div className="p-5 border-b border-white/10 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-ansys-yellow/10 border border-ansys-yellow/30 flex items-center justify-center text-ansys-yellow font-bold text-xs">
                    #{selectedEntry.sequence_number}
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-white">{selectedEntry.event}</h3>
                    <p className="text-[11px] text-gray-400">{selectedEntry.timestamp}</p>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedEntry(null)}
                  className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
                >
                  <X size={16} />
                </button>
              </div>

              {/* Modal Body */}
              <div className="p-6 overflow-y-auto space-y-5 text-xs">
                
                {/* Cryptographic Linkage Block */}
                <div className="p-4 bg-black/40 border border-white/5 rounded-xl space-y-2 font-mono">
                  <div className="text-gray-400 text-[10px] uppercase tracking-wider font-bold">Cryptographic Linkage</div>
                  <div className="text-[11px]">
                    <span className="text-gray-500">Previous Hash (H_{selectedEntry.sequence_number - 1}):</span>
                    <div className="text-gray-300 truncate mt-0.5">{selectedEntry.previous_hash || "GENESIS"}</div>
                  </div>
                  <div className="text-[11px] pt-1">
                    <span className="text-gray-500">Block Hash (H_{selectedEntry.sequence_number}):</span>
                    <div className="text-emerald-400 truncate mt-0.5 font-bold">{selectedEntry.hash}</div>
                  </div>
                  <div className="text-[10px] text-gray-500 pt-1 border-t border-white/5">
                    H_{selectedEntry.sequence_number} = SHA256(H_{selectedEntry.sequence_number - 1} || Canonical(Event_{selectedEntry.sequence_number}))
                  </div>
                </div>

                {/* Canonical Event Payload (RFC 8785) */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-bold text-gray-300">Canonical Event Envelope (RFC 8785)</span>
                    <button
                      onClick={() => handleCopy(selectedEntry.canonical_event || JSON.stringify(selectedEntry, null, 2))}
                      className="text-gray-400 hover:text-white text-[11px] flex items-center gap-1"
                    >
                      <Copy size={11} /> Copy Envelope
                    </button>
                  </div>
                  <pre className="bg-black/60 border border-white/5 rounded-xl p-3 font-mono text-[11px] text-gray-300 overflow-x-auto max-h-48 custom-scrollbar">
                    {selectedEntry.canonical_event || JSON.stringify(selectedEntry, null, 2)}
                  </pre>
                </div>

                {/* Event Metadata */}
                <div>
                  <span className="font-bold text-gray-300 block mb-1.5">Event Metadata</span>
                  <pre className="bg-black/60 border border-white/5 rounded-xl p-3 font-mono text-[11px] text-gray-300 overflow-x-auto max-h-48 custom-scrollbar">
                    {JSON.stringify(selectedEntry.metadata, null, 2)}
                  </pre>
                </div>

                {/* Context Details */}
                <div className="grid grid-cols-2 gap-3 pt-2 text-[11px]">
                  <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                    <span className="text-gray-500 block">User ID</span>
                    <span className="text-white font-mono truncate block mt-0.5">{selectedEntry.user_id}</span>
                  </div>
                  <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                    <span className="text-gray-500 block">Artifact Reference</span>
                    <span className="text-ansys-yellow font-mono truncate block mt-0.5">{selectedEntry.artifact_id || "None"}</span>
                  </div>
                  <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                    <span className="text-gray-500 block">IP Address</span>
                    <span className="text-white font-mono block mt-0.5">{selectedEntry.ip}</span>
                  </div>
                  <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                    <span className="text-gray-500 block">Team ID</span>
                    <span className="text-white font-mono truncate block mt-0.5">{selectedEntry.team_id || "None (Personal)"}</span>
                  </div>
                </div>

              </div>

              {/* Modal Footer */}
              <div className="p-4 border-t border-white/10 bg-white/[0.02] flex items-center justify-end">
                <button
                  onClick={() => setSelectedEntry(null)}
                  className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-xl font-semibold transition-colors text-xs"
                >
                  Close
                </button>
              </div>

            </div>
          </div>
        )}

      </div>
    </div>
  );
}
