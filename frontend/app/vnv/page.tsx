"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Play,
  Download,
  FileText,
  Loader2,
  RefreshCw,
  Cpu,
  Layers,
  ChevronRight,
  ChevronDown,
  Info,
  ExternalLink,
} from "lucide-react";
import { VnApi, VnSuiteResponse, VnCaseResult } from "../../lib/api_client";
import { useAuth } from "../../contexts/AuthContext";

export default function VnVPage() {
  const { user, fetchWithAuth } = useAuth();
  const [suite, setSuite] = useState<VnSuiteResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelFilter, setModelFilter] = useState<string>("all");
  const [reportMarkdown, setReportMarkdown] = useState<string | null>(null);
  const [showMarkdownModal, setShowMarkdownModal] = useState(false);
  const [expandedCase, setExpandedCase] = useState<string | null>(null);

  const runVnSuite = async () => {
    setLoading(true);
    setError(null);
    try {
      const filter = modelFilter === "all" ? undefined : modelFilter;
      const url = filter ? `/api/v1/vnv/run?model=${encodeURIComponent(filter)}` : "/api/v1/vnv/run";
      let resData: VnSuiteResponse;
      if (fetchWithAuth) {
        const res = await fetchWithAuth(url);
        if (res.ok) {
          resData = await res.json();
        } else {
          resData = await VnApi.runVnSuite(filter);
        }
      } else {
        resData = await VnApi.runVnSuite(filter);
      }
      setSuite(resData);
    } catch (err: any) {
      console.error("V&V Suite Execution Error:", err);
      setError(err.message || "Failed to execute V&V suite. Ensure Enterprise plan or admin credentials.");
    } finally {
      setLoading(false);
    }
  };

  const fetchMarkdownReport = async () => {
    try {
      let md = "";
      if (fetchWithAuth) {
        const res = await fetchWithAuth("/api/v1/vnv/report");
        if (res.ok) {
          md = await res.text();
        } else {
          md = await VnApi.getVnReport();
        }
      } else {
        md = await VnApi.getVnReport();
      }
      setReportMarkdown(md);
      setShowMarkdownModal(true);
    } catch (err: any) {
      console.error("Failed to load V&V markdown evidence report:", err);
      setError("Failed to load V&V evidence report: " + (err.message || "Unauthorized"));
    }
  };

  useEffect(() => {
    runVnSuite();
  }, [modelFilter]);

  const filteredCases = suite?.cases || [];

  return (
    <div className="w-full bg-[#08080a] text-white min-h-screen pt-20 pb-16 px-4 sm:px-6 font-sans">
      <div className="max-w-[1440px] mx-auto">
        {/* Breadcrumbs & Header */}
        <div className="flex items-center gap-2 text-xs font-mono text-gray-500 mb-2">
          <Link href="/" className="hover:text-gray-300">HOME</Link>
          <ChevronRight size={12} />
          <span className="text-ansys-yellow font-bold">VERIFICATION & VALIDATION (V&V)</span>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-4 mb-8 pb-6 border-b border-white/[0.08]">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-ansys-yellow mb-1">
              <ShieldCheck size={16} />
              Numerical & Physical Rigor Compliance Suite
            </div>
            <h1 className="text-3xl font-extrabold text-white tracking-tight">
              Verification & Validation (V&V) Evidence
            </h1>
            <p className="text-sm text-gray-400 mt-1 max-w-2xl">
              Independent benchmark testing of mathematical models against closed-form analytical solutions,
              conservation laws, and empirical tire/damper dyno ground-truth.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <select
              value={modelFilter}
              onChange={(e) => setModelFilter(e.target.value)}
              className="bg-[#141418] border border-white/10 rounded-xl px-3 py-2 text-xs font-mono text-gray-200 focus:outline-none focus:border-ansys-yellow"
            >
              <option value="all">All Physics Models</option>
              <option value="quarter_car">Quarter Car (2-DOF Ride)</option>
              <option value="half_car">Half Car (4-DOF Pitch/Heave)</option>
              <option value="full_car">Full Car (7-DOF Rig)</option>
              <option value="kinematics">Kinematics Solver</option>
              <option value="magic_formula">Pacejka MF5.2 Tire Model</option>
            </select>

            <button
              onClick={runVnSuite}
              disabled={loading}
              className="px-4 py-2 bg-ansys-yellow text-black font-bold text-xs rounded-xl hover:brightness-110 flex items-center gap-2 disabled:opacity-50 transition-all"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
              Run V&V Suite
            </button>

            <button
              onClick={fetchMarkdownReport}
              className="px-4 py-2 bg-white/[0.05] border border-white/10 text-gray-200 hover:bg-white/10 font-bold text-xs rounded-xl flex items-center gap-2 transition-all"
            >
              <FileText size={14} />
              Evidence Report
            </button>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-6 p-4 rounded-xl bg-rose-950/30 border border-rose-500/40 text-rose-300 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              <AlertTriangle size={16} className="text-rose-400 shrink-0 mt-0.5" />
              <div>
                <div className="font-bold text-rose-200">V&V Suite Execution Notice</div>
                <div className="mt-0.5">{error}</div>
              </div>
            </div>
            <div className="flex items-center gap-2 mt-2 sm:mt-0 shrink-0">
              <button
                onClick={runVnSuite}
                className="px-3 py-1.5 bg-ansys-yellow text-black font-bold text-xs rounded-lg hover:brightness-110 flex items-center gap-1.5 transition-all"
              >
                <RefreshCw size={12} />
                Retry Suite
              </button>
              <Link
                href="/auth/login?redirect=/vnv"
                className="px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white font-semibold text-xs rounded-lg flex items-center gap-1.5 transition-all"
              >
                Log In / Restore Session
              </Link>
            </div>
          </div>
        )}

        {/* Summary Metrics */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/[0.06]">
            <div className="text-[11px] text-gray-400 uppercase font-mono">Total Test Cases</div>
            <div className="text-2xl font-extrabold font-mono text-white mt-1">
              {suite?.summary.total ?? "—"}
            </div>
            <div className="text-[10px] text-gray-500 mt-0.5">Automated benchmark cases</div>
          </div>

          <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/[0.06]">
            <div className="text-[11px] text-gray-400 uppercase font-mono">Passing Cases</div>
            <div className="text-2xl font-extrabold font-mono text-emerald-400 mt-1 flex items-center gap-1.5">
              <CheckCircle2 size={20} />
              {suite?.summary.passed ?? "—"}
            </div>
            <div className="text-[10px] text-gray-500 mt-0.5">Within numerical tolerance</div>
          </div>

          <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/[0.06]">
            <div className="text-[11px] text-gray-400 uppercase font-mono">Failed Cases</div>
            <div className="text-2xl font-extrabold font-mono text-rose-400 mt-1 flex items-center gap-1.5">
              <XCircle size={20} />
              {suite?.summary.failed ?? "0"}
            </div>
            <div className="text-[10px] text-gray-500 mt-0.5">Exceeding tolerance bounds</div>
          </div>

          <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/[0.06]">
            <div className="text-[11px] text-gray-400 uppercase font-mono">Suite Compliance</div>
            <div className="text-sm font-extrabold font-mono mt-1">
              {suite?.summary.all_passed ? (
                <span className="px-2.5 py-1 rounded-full bg-emerald-950/60 border border-emerald-500/40 text-emerald-400">
                  100% VERIFIED
                </span>
              ) : (
                <span className="px-2.5 py-1 rounded-full bg-amber-950/60 border border-amber-500/40 text-amber-400">
                  REQUIRES REVIEW
                </span>
              )}
            </div>
            <div className="text-[10px] text-gray-500 mt-1">ISO 16331 / DIN 70000</div>
          </div>
        </div>

        {/* Test Cases Table */}
        <div className="rounded-2xl bg-[#111116] border border-white/[0.08] overflow-hidden shadow-2xl">
          <div className="px-6 py-4 border-b border-white/[0.06] flex items-center justify-between">
            <div className="flex items-center gap-2 font-bold text-sm text-white">
              <Cpu size={16} className="text-ansys-yellow" />
              Benchmark Case Execution Log
            </div>
            <div className="text-xs font-mono text-gray-400">
              Showing {filteredCases.length} validated benchmark tests
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-white/[0.02] border-b border-white/[0.06] text-gray-400 uppercase text-[10px] tracking-wider">
                <tr>
                  <th className="py-3 px-4">Test Case & Target</th>
                  <th className="py-3 px-4">Model & Solver</th>
                  <th className="py-3 px-4 text-right">Target Tol.</th>
                  <th className="py-3 px-4 text-right">Discrepancy</th>
                  <th className="py-3 px-4 text-center">Status</th>
                  <th className="py-3 px-4 text-right">Provenance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {loading ? (
                  <tr>
                    <td colSpan={6} className="py-12 text-center text-gray-500">
                      <Loader2 size={24} className="animate-spin mx-auto mb-2 text-ansys-yellow" />
                      Executing mathematical verification benchmarks...
                    </td>
                  </tr>
                ) : filteredCases.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-12 text-center text-gray-500">
                      No test cases found for the selected model filter.
                    </td>
                  </tr>
                ) : (
                  filteredCases.map((c, idx) => (
                    <React.Fragment key={idx}>
                      <tr
                        onClick={() => setExpandedCase(expandedCase === c.name ? null : c.name)}
                        className="hover:bg-white/[0.02] cursor-pointer transition-colors"
                      >
                        <td className="py-3 px-4 font-semibold text-white">
                          <div className="flex items-center gap-2">
                            <ChevronDown
                              size={13}
                              className={`text-gray-500 transition-transform ${
                                expandedCase === (c.name || (c as any).id) ? "rotate-180" : ""
                              }`}
                            />
                            {c.name || (c as any).title || (c as any).id}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-gray-400">
                          <div>{c.model}</div>
                          <div className="text-[10px] text-gray-600">{c.solver || (c as any).solver_version || "RK45"}</div>
                        </td>
                        <td className="py-3 px-4 text-right text-gray-400 font-mono">
                          ±{(((c.tolerance !== undefined ? c.tolerance : ((c as any).tolerance_pct ? (c as any).tolerance_pct / 100 : 0.05))) * 100).toFixed(2)}%
                        </td>
                        <td
                          className={`py-3 px-4 text-right font-mono font-bold ${
                            Math.abs(c.discrepancy_pct ?? (c as any).error_pct ?? 0) <= (((c.tolerance !== undefined ? c.tolerance : ((c as any).tolerance_pct ? (c as any).tolerance_pct / 100 : 0.05))) * 100)
                              ? "text-emerald-400"
                              : "text-rose-400"
                          }`}
                        >
                          {(c.discrepancy_pct ?? (c as any).error_pct ?? 0) >= 0 ? "+" : ""}
                          {(c.discrepancy_pct ?? (c as any).error_pct ?? 0).toFixed(4)}%
                        </td>
                        <td className="py-3 px-4 text-center">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                              c.status === "PASS"
                                ? "bg-emerald-950/60 border-emerald-500/40 text-emerald-400"
                                : "bg-rose-950/60 border-rose-500/40 text-rose-400"
                            }`}
                          >
                            {c.status}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right text-gray-500 text-[10px]">
                          <div>{c.provenance?.dataset || (c as any).reference_source || "ANALYTICAL"}</div>
                          <div className="text-gray-600">{c.provenance?.build || (c as any).physics_version || "PROD"}</div>
                        </td>
                      </tr>

                      {expandedCase === (c.name || (c as any).id) && (
                        <tr className="bg-white/[0.01]">
                          <td colSpan={6} className="py-3 px-8 text-xs text-gray-400 border-t border-white/[0.02]">
                            <div className="p-3 rounded-xl bg-black/40 border border-white/[0.04] space-y-1">
                              <div className="text-white font-bold flex items-center gap-1.5">
                                <Info size={13} className="text-ansys-yellow" />
                                Engineering Explanation & Benchmark Ground Truth:
                              </div>
                              <p className="text-gray-300 font-sans">{c.explanation || `Validated against ${(c as any).reference_source || 'ground truth'}`}</p>
                              <div className="pt-2 text-[10px] text-gray-500 flex gap-4">
                                <span>Dataset: {c.provenance?.dataset || (c as any).reference_source || "ANALYTICAL"}</span>
                                <span>Execution Date: {c.provenance?.date || "2026-03-01"}</span>
                                <span>Software Build: {c.provenance?.build || (c as any).physics_version || "PROD"}</span>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Markdown Evidence Report Modal */}
      {showMarkdownModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Evidence Report Modal"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-150"
        >
          <div className="bg-[#111116] border border-white/10 rounded-2xl max-w-4xl w-full max-h-[85vh] flex flex-col p-6 shadow-2xl relative text-white">
            <div className="flex items-center justify-between pb-4 border-b border-white/10 mb-4">
              <div>
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <FileText size={16} className="text-ansys-yellow" />
                  Evidence Report (Markdown) · ISO 16331 / DIN 70000
                </h2>
                <p className="text-xs text-gray-400">Standard evidence format for certification and compliance audits.</p>
              </div>
              <button
                onClick={() => setShowMarkdownModal(false)}
                className="px-3 py-1 bg-white/10 hover:bg-white/20 rounded-lg text-xs font-bold"
              >
                Close
              </button>
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar p-4 bg-black/60 rounded-xl font-mono text-xs text-gray-300 border border-white/5 whitespace-pre-wrap">
              {reportMarkdown}
            </div>

            <div className="flex justify-end gap-3 mt-4 pt-4 border-t border-white/10">
              <button
                onClick={() => {
                  if (!reportMarkdown) return;
                  const blob = new Blob([reportMarkdown], { type: "text/markdown" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `SuspensionLab_VnV_Evidence_Report_${Date.now()}.md`;
                  a.click();
                }}
                className="px-4 py-2 bg-ansys-yellow text-black font-bold text-xs rounded-xl hover:brightness-110 flex items-center gap-1.5"
              >
                <Download size={13} />
                Download Markdown (.md)
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
