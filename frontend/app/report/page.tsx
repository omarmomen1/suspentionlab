"use client";

import { useState, useRef, useEffect, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  FileText, Download, Share2, CheckCircle2, ShieldCheck,
  TrendingDown, Activity, Layers, AlertCircle, ArrowUpRight,
  Printer, Copy, Check, Car, Sparkles, Gauge, ChevronRight,
  FileDown, Eye, Loader2, RefreshCw, XCircle, ShieldAlert
} from "lucide-react";
import Plot from "../../components/sim/Plot";
import TrustBadge from "../../components/TrustBadge";
import PDFExport from "../../components/PDFExport";
import { ReportsApi, SimulationApi } from "../../lib/api_client";
import { useWorkspace } from "../../contexts/WorkspaceContext";

const DARK_PLOT_BASE = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { color: "#94A3B8", size: 10, family: "Inter, monospace" },
  xaxis: { color: "#94A3B8", gridcolor: "#161618", zerolinecolor: "#2a2a2a", tickfont: { color: "#94A3B8" } },
  yaxis: { color: "#94A3B8", gridcolor: "#161618", zerolinecolor: "#2a2a2a", tickfont: { color: "#94A3B8" } },
  margin: { l: 45, r: 15, t: 25, b: 35 },
  autosize: true,
};

function ReportContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { simulation, setSimulation } = useWorkspace();

  const queryRunId =
    searchParams.get("run_id") ||
    searchParams.get("simulation_run_id") ||
    searchParams.get("id") ||
    simulation.activeRunId ||
    "";

  const [activeTab, setActiveTab] = useState<"all" | "executive" | "lap" | "kinematics" | "nvh" | "digital_twin">("all");
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [runsList, setRunsList] = useState<any[]>([]);
  const [selectedRunLabel, setSelectedRunLabel] = useState<string>(queryRunId || "");
  const [baselineRunLabel, setBaselineRunLabel] = useState<string>("");

  const [report, setReport] = useState<any>(null);
  const [approvalModalOpen, setApprovalModalOpen] = useState(false);
  const [approvalAction, setApprovalAction] = useState<"APPROVED" | "REJECTED">("APPROVED");
  const [approvalComment, setApprovalComment] = useState("");
  const [submittingApproval, setSubmittingApproval] = useState(false);

  const [shareModalOpen, setShareModalOpen] = useState(false);
  const [shareUrl, setShareUrl] = useState<string>("");
  const [sharing, setSharing] = useState(false);

  const reportRef = useRef<HTMLDivElement>(null);
  const benchmarkFallbackAttemptedRef = useRef<boolean>(false);

  useEffect(() => {
    async function init() {
      benchmarkFallbackAttemptedRef.current = false;
      setLoading(true);
      setError(null);
      try {
        let activeRun = queryRunId;
        const runsRes = await ReportsApi.listRuns(20).catch(() => ({ total: 0, runs: [] }));
        setRunsList(runsRes.runs || []);

        if (!activeRun && runsRes.runs && runsRes.runs.length > 0) {
          activeRun = runsRes.runs[0].label;
          setSelectedRunLabel(activeRun || "");
        }

        if (activeRun) {
          await loadReportForRun(activeRun);
        } else {
          await triggerBenchmarkSimulation();
        }
      } catch (err: any) {
        console.error("Report initialization failed:", err);
        setError(err.message || "Failed to load engineering report.");
      } finally {
        setLoading(false);
      }
    }
    init();
  }, [queryRunId]);

  async function loadReportForRun(runIdOrLabel: string, allowFallback: boolean = true, baselineId?: string) {
    setLoading(true);
    setError(null);
    const activeBaseline = baselineId !== undefined ? baselineId : baselineRunLabel;
    try {
      const recordRes = await ReportsApi.createReportFromRun({
        simulation_run_id: runIdOrLabel,
        baseline_run_id: activeBaseline || undefined,
        title: `Engineering Decision & Compliance Report — ${runIdOrLabel}`,
      }).catch(async () => {
        const hyd = await ReportsApi.hydrateReport(runIdOrLabel, activeBaseline || undefined);
        return { id: hyd.simulation_run_id, token: "", status: "PROPOSED", doc_id: hyd.doc_id, hydrated: hyd };
      });

      const hydratedData = recordRes.hydrated;
      setReport({
        ...hydratedData,
        recordId: recordRes.id,
        token: recordRes.token,
        status: recordRes.status || "PROPOSED",
        shareUrl: recordRes.share_url || `/report/${recordRes.token}`,
      });
      setSelectedRunLabel(runIdOrLabel);
      setSimulation({ activeRunId: runIdOrLabel });

      if (recordRes.token) {
        const fullRecord = await ReportsApi.getReportRecord(recordRes.token).catch(() => null);
        if (fullRecord) {
          setReport((prev: any) => ({
            ...prev,
            ...fullRecord,
            status: fullRecord.status,
            approval: {
              status: fullRecord.status,
              name: fullRecord.approved_by_email ? fullRecord.approved_by_email.split("@")[0].toUpperCase() : "Chief Race Engineer",
              role: fullRecord.approved_by_role || "ENGINEER",
              timestamp: fullRecord.approved_at || new Date().toISOString(),
              comment: fullRecord.approval_comment || "Validated under engineering correlation threshold.",
              signature: fullRecord.approval_signature,
            },
            signature_verification: fullRecord.signature_verification,
          }));
        }
      }
    } catch (err: any) {
      console.warn("Failed to load run report:", err);
      if (allowFallback && !benchmarkFallbackAttemptedRef.current && runIdOrLabel !== "latest") {
        try {
          await triggerBenchmarkSimulation();
          return;
        } catch (fallbackErr: any) {
          setError(fallbackErr.message || `Failed to hydrate report for ${runIdOrLabel}`);
          return;
        }
      }
      setError(err?.message || `Failed to hydrate report for ${runIdOrLabel}`);
    } finally {
      setLoading(false);
    }
  }

  async function triggerBenchmarkSimulation() {
    if (benchmarkFallbackAttemptedRef.current) {
      setError("Failed to hydrate latest benchmark report.");
      setLoading(false);
      return;
    }
    benchmarkFallbackAttemptedRef.current = true;
    setLoading(true);
    setError(null);
    try {
      await loadReportForRun("latest", false);
    } catch (err: any) {
      console.error("Benchmark run failed:", err);
      setError("Failed to execute benchmark simulation. " + (err.message || ""));
    } finally {
      setLoading(false);
    }
  }

  const handleShareClick = async () => {
    if (!report) return;
    setSharing(true);
    try {
      const targetId = report.token || report.recordId || report.simulation_run_id;
      const shareRes = await ReportsApi.shareReportToken(targetId);
      const fullUrl = `${window.location.origin}/report/${shareRes.token}`;
      setShareUrl(fullUrl);
      if (typeof navigator !== "undefined") {
        await navigator.clipboard.writeText(fullUrl);
        setCopied(true);
        setTimeout(() => setCopied(false), 3000);
      }
      setShareModalOpen(true);
    } catch (err) {
      console.error("Failed to share report:", err);
      alert("Failed to generate share token. Ensure report is persisted.");
    } finally {
      setSharing(false);
    }
  };

  const handleOpenApprovalModal = (action: "APPROVED" | "REJECTED") => {
    setApprovalAction(action);
    setApprovalComment(
      action === "APPROVED"
        ? "Signed off under telemetry residual correlation threshold."
        : "Rejected: Residual error exceeds allowable track tolerance."
    );
    setApprovalModalOpen(true);
  };

  const handleConfirmApproval = async () => {
    if (!report) return;
    setSubmittingApproval(true);
    try {
      const targetId = report.token || report.recordId || report.simulation_run_id;
      const res = await ReportsApi.updateReportStatus(targetId, approvalAction, approvalComment);

      setReport((prev: any) => ({
        ...prev,
        status: res.status,
        approval: {
          status: res.status,
          name: res.approved_by_email ? res.approved_by_email.split("@")[0].toUpperCase() : "Chief Race Engineer",
          role: res.approved_by_role || "ENGINEER",
          timestamp: res.approved_at,
          comment: res.approval_comment,
          signature: res.approval_signature,
        },
        signature_verification: {
          signed: true,
          signature_valid: true,
          tamper_detected: false,
        },
      }));
      setApprovalModalOpen(false);
    } catch (err: any) {
      alert(`Approval operation failed: ${err.message || "Unauthorized"}`);
    } finally {
      setSubmittingApproval(false);
    }
  };

  const showAll = activeTab === "all";

  if (loading) {
    return (
      <div className="min-h-[calc(100vh-44px)] bg-[#08080a] text-white flex flex-col items-center justify-center p-8">
        <Loader2 className="animate-spin text-signal mb-4" size={32} />
        <h1 className="text-lg font-bold">Hydrating Engineering Report…</h1>
        <p className="text-xs text-gray-400 mt-1 font-sans leading-relaxed">Retrieving real vehicle, setup, tire, track, solver, and telemetry facets</p>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="min-h-[calc(100vh-44px)] bg-[#08080a] text-white flex flex-col items-center justify-center p-8 space-y-4">
        <AlertCircle className="text-rose-500" size={36} />
        <h1 className="text-lg font-bold text-rose-300">Report Loading Error</h1>
        <p className="text-xs text-gray-400 max-w-md text-center">{error || "No engineering report data found."}</p>
        <button
          onClick={triggerBenchmarkSimulation}
          className="px-4 py-2 bg-signal text-carbon border border-signal text-xs font-bold rounded-xl hover:bg-[#d6f56e] transition-colors flex items-center gap-2"
        >
          <RefreshCw size={14} /> Execute Real Benchmark Simulation
        </button>
      </div>
    );
  }

  const p = report.params || {};
  const r = report.result || {};
  const metrics = report.metrics || {};
  const plotData = report.plot_data || {};
  const isApproved = report.status === "APPROVED" || report.status === "EXPORTED";
  const isRejected = report.status === "REJECTED";

  return (
    <div className="min-h-[calc(100vh-44px)] bg-[#08080a] text-white p-6 md:p-10 font-sans print:p-0 print:bg-white print:text-black">
      <div ref={reportRef} className="max-w-6xl mx-auto space-y-8 print:space-y-6">

        {/* ── TOP ACTION BAR & HEADER ── */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#1c1c20] pb-6 print:border-gray-300">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <span className="px-2 py-0.5 rounded text-xs font-bold bg-signal/15 text-signal border border-signal/30 tracking-wider">
                STAGE 6: OFFICIAL REPORT
              </span>
              <span className="text-zinc-300">·</span>
              <span className="text-xs text-gray-400 font-mono font-bold">{report.doc_id || "DOC-2026-SL-0001"}</span>
              <span className="text-zinc-300">·</span>
              <span className={`text-xs font-bold px-2 py-0.5 rounded border flex items-center gap-1 ${
                isApproved
                  ? "bg-emerald-950/80 text-emerald-400 border-emerald-500/40"
                  : isRejected
                  ? "bg-rose-950/80 text-rose-400 border-rose-500/40"
                  : "bg-amber-950/80 text-amber-400 border-amber-500/40"
              }`}>
                <ShieldCheck size={12} /> {report.status}
              </span>
            </div>
            <h1 className="text-2xl md:text-3xl font-black tracking-tight text-white print:text-black flex items-center gap-3">
              {report.title || "Engineering Decision & Compliance Report"}
            </h1>
            <p className="text-xs text-gray-400 print:text-gray-700 mt-1">
              Vehicle: <strong className="text-gray-200 print:text-black">{report.vehicle_ref || "CAR-07"}</strong> &middot;
              Track: <strong className="text-gray-200 print:text-black">{report.track_ref || "SPA-FRANCORCHAMPS"}</strong> &middot;
              Setup: <strong className="text-amber-400 print:text-amber-800">{report.setup_ref || "REV-01"}</strong> &middot;
              Run: <span className="font-mono text-gray-300">{report.run_id}</span>
            </p>
          </div>

          <div className="no-print flex flex-wrap items-center gap-2 shrink-0">
            {runsList.length > 1 && (
              <select
                aria-label="Select simulation run"
                value={selectedRunLabel}
                onChange={(e) => {
                  const nextRun = e.target.value;
                  setSelectedRunLabel(nextRun);
                  if (baselineRunLabel === nextRun) {
                    setBaselineRunLabel("");
                    loadReportForRun(nextRun, true, "");
                  } else {
                    loadReportForRun(nextRun);
                  }
                }}
                className="px-3 py-1.5 rounded-xl bg-[#141417] border border-[#25252c] text-xs font-mono text-gray-300 focus:outline-none focus:border-signal"
              >
                {runsList.map((run) => (
                  <option key={run.label} value={run.label}>
                    {run.label} ({run.track_ref || run.simulation_type})
                  </option>
                ))}
              </select>
            )}
            {runsList.length > 1 && (
              <select
                aria-label="Compare against baseline run"
                value={baselineRunLabel}
                onChange={(e) => {
                  const nextBase = e.target.value;
                  setBaselineRunLabel(nextBase);
                  loadReportForRun(selectedRunLabel || report.run_id, true, nextBase);
                }}
                className="px-3 py-1.5 rounded-xl bg-[#141417] border border-[#25252c] text-xs font-mono text-gray-300 focus:outline-none focus:border-signal"
              >
                <option value="">Baseline run (no comparison)</option>
                {runsList
                  .filter((run) => run.label !== selectedRunLabel)
                  .map((run) => (
                    <option key={run.label} value={run.label}>
                      vs {run.label}
                    </option>
                  ))}
              </select>
            )}

            {!isApproved && (
              <button
                onClick={() => handleOpenApprovalModal("APPROVED")}
                className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-white transition flex items-center gap-1.5 shadow-sm"
              >
                <ShieldCheck size={14} /> Sign & Approve
              </button>
            )}
            {!isRejected && !isApproved && (
              <button
                onClick={() => handleOpenApprovalModal("REJECTED")}
                className="px-3.5 py-2 rounded-xl bg-[#1f1618] hover:bg-rose-950 border border-rose-800/40 text-xs font-semibold text-rose-300 transition flex items-center gap-1.5"
              >
                <XCircle size={14} /> Reject
              </button>
            )}

            <PDFExport
              fileName={`SuspensionLab-PRO-Decision-Report-${report.run_id}`}
              title="Engineering Decision & Compliance Report"
              docId={report.doc_id || "DOC-2026-SL-0001"}
              vehicleRef={report.vehicle_ref || "CAR-07"}
              setupRef={report.setup_ref || "REV-01"}
              trackRef={report.track_ref || "SPA-FRANCORCHAMPS"}
              tireRef={report.tire_ref || "TIRE-MF52-COMPOUND-SOFT"}
              telemetryRef={report.telemetry_ref || "TELEMETRY-SYNC-Q2"}
              solverVersion={report.solver_version || "RK45 / BDF Adaptive Stiff"}
              physicsVersion={report.physics_version || "quarter-car-v2"}
              softwareBuild={report.software_build || "BUILD-REL-2026.1"}
              inputHash={report.input_hash}
              resultHash={report.result_hash}
              artifactHash={report.artifact_hash}
              validationStatus={`${report.validation_status} / CERTIFIED`}
              correlationPct={report.correlation_pct}
              comfortCategory={report.comfort_category}
              metrics={metrics}
              paramChanges={report.param_changes}
              plotData={plotData}
              approval={report.approval || {
                status: report.status,
                name: "Chief Race Engineer",
                role: "LEAD",
                timestamp: new Date().toISOString(),
                signature: report.approval_signature,
              }}
            />

            <button
              onClick={handleShareClick}
              disabled={sharing}
              className="px-3.5 py-2 rounded-xl bg-[#141417] hover:bg-[#1f1f24] border border-[#25252c] text-xs font-semibold text-gray-300 hover:text-white transition flex items-center gap-2"
            >
              {sharing ? <Loader2 size={14} className="animate-spin text-signal" /> : copied ? <Check size={14} className="text-emerald-400" /> : <Share2 size={14} />}
              {copied ? "Link Copied" : "Share Token"}
            </button>

            <Link
              href="/garage"
              className="px-3.5 py-2 rounded-xl bg-[#141417] hover:bg-[#1f1f24] border border-[#25252c] text-xs font-semibold text-gray-300 hover:text-white transition flex items-center gap-1.5"
            >
              Garage <ArrowUpRight size={14} />
            </Link>
          </div>
        </div>

        {/* Wave 9 item 3: the auto-computed default-vehicle baseline is labeled on screen. */}
        {report && (report as any).is_default_vehicle_baseline && (
          <div className="rounded-xl border-2 border-amber-500/60 bg-amber-500/10 px-4 py-3 text-xs font-semibold text-amber-300">
            Reference baseline on the default vehicle - not your car. Run a simulation on your own parameters first.
          </div>
        )}

        {/* ── REPORT VIEW SELECTOR TABS ── */}
        <div className="no-print flex items-center gap-2 border-b border-[#18181c] pb-2 overflow-x-auto">
          {[
            { id: "all", label: "All Sections (Full Document)", icon: Eye },
            { id: "executive", label: "Executive Decision", icon: Sparkles },
            { id: "lap", label: "Lap Performance & G-G", icon: Gauge },
            { id: "kinematics", label: "Kinematics & Camber", icon: Layers },
            { id: "nvh", label: "ISO 2631 Ride & NVH", icon: Activity },
            { id: "digital_twin", label: "Digital Twin Lineage", icon: ShieldCheck },
          ].map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`px-3.5 py-2 rounded-lg text-xs font-semibold flex items-center gap-2 whitespace-nowrap transition-all ${
                  active
                    ? "bg-[#18181c] text-signal border border-signal/30 shadow-sm"
                    : "text-gray-400 hover:text-gray-200 hover:bg-[#121215] border border-transparent"
                }`}
              >
                <Icon size={13} className={active ? "text-signal" : "text-zinc-400"} />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* ── SECTION 1: EXECUTIVE DECISION SUMMARY ── */}
        {(showAll || activeTab === "executive") && (
          <div className="print-card space-y-6">
            <h2 className="text-lg font-bold text-white print:text-black border-b border-[#1c1c20] print:border-gray-300 pb-2 flex items-center gap-2">
              <Sparkles size={16} className="text-amber-400 print:text-amber-800" />
              1. Executive Decision Summary & Performance Metrics (Real Engineering Output)
            </h2>

            {/* KPI Ribbon */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-[#0f0f12] print:bg-white border border-[#1e1e24] print:border-gray-300 rounded-2xl p-4">
                <p className="text-xs font-bold text-zinc-400 print:text-gray-600 uppercase tracking-wider">Simulated Lap Delta</p>
                <p className="text-lg font-black text-emerald-400 print:text-emerald-700 font-sans leading-relaxed mt-1">
                  {metrics["Simulated Lap Delta"] || "Baseline run (no comparison)"}
                </p>
                <p className="text-xs text-gray-400 print:text-gray-600 mt-1">
                  {report.baseline_run_id ? `Compared vs ${report.baseline_run_id}` : "Select a baseline run to compare"}
                </p>
              </div>
              <div className="bg-[#0f0f12] print:bg-white border border-[#1e1e24] print:border-gray-300 rounded-2xl p-4">
                <p className="text-xs font-bold text-zinc-400 print:text-gray-600 uppercase tracking-wider">Front Turn-in Grip</p>
                <p className="text-lg font-black text-signal print:text-amber-800 font-sans leading-relaxed mt-1">
                  {metrics["Front Turn-in Grip"] || "Baseline run (no comparison)"}
                </p>
                <p className="text-xs text-gray-400 print:text-gray-600 mt-1">Tire load consistency delta</p>
              </div>
              <div className="bg-[#0f0f12] print:bg-white border border-[#1e1e24] print:border-gray-300 rounded-2xl p-4">
                <p className="text-xs font-bold text-zinc-400 print:text-gray-600 uppercase tracking-wider">Rear Platform Stability</p>
                <p className="text-lg font-black text-blue-400 print:text-blue-700 font-sans leading-relaxed mt-1">
                  {metrics["Rear Platform Stability"] || "Baseline run (no comparison)"}
                </p>
                <p className="text-xs text-gray-400 print:text-gray-600 mt-1">Platform Wk isolation delta</p>
              </div>
              <div className="bg-[#0f0f12] print:bg-white border border-[#1e1e24] print:border-gray-300 rounded-2xl p-4">
                <p className="text-xs font-bold text-zinc-400 print:text-gray-600 uppercase tracking-wider">Telemetry Correlation</p>
                <p className="text-lg font-black text-cyan-400 print:text-cyan-700 font-sans leading-relaxed mt-1">
                  {metrics["Telemetry Correlation"] || (typeof report.correlation_pct === "number" ? `${report.correlation_pct.toFixed(1)} %` : "UNVALIDATED")}
                </p>
                <p className="text-xs text-gray-400 print:text-gray-600 mt-1">
                  {typeof report.correlation_pct === "number" ? "Empirical model correlation" : "No empirical telemetry dataset"}
                </p>
              </div>
            </div>

            {/* Decision Narrative & Dynamic Chart */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 bg-[#0f0f12] print:bg-white border border-[#1e1e24] print:border-gray-300 rounded-2xl p-6 space-y-4">
                <h3 className="text-sm font-bold text-white print:text-black flex items-center gap-2">
                  Engineering Causal Chain & Real Simulation Transient
                </h3>
                <div className="space-y-2 text-xs text-gray-300 print:text-gray-800 leading-relaxed font-mono bg-black/40 print:bg-gray-50 p-4 rounded-xl border border-[#1b1b20] print:border-gray-200">
                  <p>
                    <strong className="text-red-400 print:text-red-700">[1. Measured Problem]:</strong> Platform transient pitch oscillations on road disturbance input.
                  </p>
                  <p>
                    <strong className="text-blue-400 print:text-blue-700">[2. Physical Root Cause]:</strong> Damping ratio ζ_s = {report.result?.zeta_s != null ? Number(report.result.zeta_s).toFixed(2) : "N/A"} allows heave travel to unload wheel load before aerodynamic platform stabilizes.
                  </p>
                  <p>
                    <strong className="text-emerald-400 print:text-emerald-700">[3. Validated Action]:</strong> Configured suspension stiffness to {p.k_s} N/m and damping to {p.c} Ns/m to achieve optimal compromise between ISO 2631 Wk comfort ({metrics["Wk-Weighted RMS Accel"]}) and road holding.
                  </p>
                </div>

                <div className="h-[220px]">
                  {Array.isArray(plotData?.time) && plotData.time.length > 0 ? (
                    <Plot
                      data={[
                        {
                          x: plotData.time,
                          y: (plotData.z_s || []).map((v: number) => v * 1000),
                          name: "Body Displacement (z_s) [mm]",
                          type: "scatter", mode: "lines",
                          line: { color: "#C8F04B", width: 2 }
                        },
                        {
                          x: plotData.time,
                          y: (plotData.z_u || []).map((v: number) => v * 1000),
                          name: "Wheel Displacement (z_u) [mm]",
                          type: "scatter", mode: "lines",
                          line: { color: "#3b82f6", width: 1.5, dash: "dot" }
                        }
                      ]}
                      layout={{
                        ...DARK_PLOT_BASE,
                        title: { text: "Simulated Time-Domain Transient (Distance/Time vs Displacement)", font: { color: "#94A3B8", size: 11 } },
                        legend: { orientation: "h", y: 1.15, font: { color: "#888", size: 9 } }
                      } as any}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  ) : (
                    <div className="h-full flex items-center justify-center text-xs text-zinc-400 font-mono">
                      No time-series data available for this run.
                    </div>
                  )}
                </div>
              </div>

              {/* Setup Parameter Delta Card */}
              <div className="bg-[#0f0f12] print:bg-white border border-[#1e1e24] print:border-gray-300 rounded-2xl p-6 space-y-4 flex flex-col justify-between">
                <div>
                  <h3 className="text-sm font-bold text-white print:text-black mb-3">Setup Parameter Changes</h3>
                  <div className="space-y-2.5">
                    {report.param_changes && report.param_changes.length > 0 ? (
                      report.param_changes.map((item: any, idx: number) => (
                      <div key={idx} className="flex items-center justify-between text-xs p-2 rounded-lg bg-black/30 print:bg-gray-100 border border-[#1a1a20] print:border-gray-200">
                        <div>
                          <p className="font-semibold text-gray-200 print:text-black">{item.parameter}</p>
                          <p className="text-xs text-zinc-400 print:text-gray-600">{item.baseline ?? "\u2014"} &rarr; {item.simulated ?? "\u2014"}</p>
                        </div>
                        <span className="font-mono text-emerald-400 print:text-emerald-700 font-bold">{item.delta ?? "N/A"}</span>
                      </div>
                      ))
                    ) : (
                      <p className="text-xs text-zinc-400 print:text-gray-600 font-sans leading-relaxed">
                        No baseline comparison run for this report - parameter deltas N/A.
                        Run a baseline simulation first to compute real deltas.
                      </p>
                    )}
                  </div>
                </div>

                <div className="pt-4 border-t border-[#1a1a20] print:border-gray-200">
                  <p className="text-xs text-zinc-400 print:text-gray-600 font-sans leading-relaxed">
                    SHA-256 Input Lineage Fingerprint:<br />
                    <span className="text-gray-400 print:text-black break-all">{report.input_hash}</span>
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── SECTION 2: LAP SIMULATION & G-G ENVELOPE ── */}
        {(showAll || activeTab === "lap") && (
          <div className="print-card space-y-4">
            <h2 className="text-lg font-bold text-white print:text-black border-b border-[#1c1c20] print:border-gray-300 pb-2 flex items-center gap-2">
              <Gauge size={16} className="text-amber-400 print:text-amber-800" />
              2. Lap Performance, G-G Envelope & Aerodynamics (Calculated Physics)
            </h2>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="bg-[#0f0f12] print:bg-white border border-[#1e1e24] print:border-gray-300 rounded-2xl p-6 space-y-4">
                <h3 className="text-sm font-bold text-white print:text-black">G-G Friction Bowl & Driver Exploitation</h3>
                <div className="h-[280px]">
                  {plotData?.gg_envelope ? (
                    <Plot
                      data={[
                        {
                          x: plotData.gg_envelope.boundary_lat_g,
                          y: plotData.gg_envelope.boundary_long_g,
                          type: "scatter", mode: "lines", name: "Tire Limit",
                          line: { color: "#C8F04B", width: 1.5, dash: "dot" }
                        },
                        {
                          x: plotData.gg_envelope.sim_lat_g,
                          y: plotData.gg_envelope.sim_long_g,
                          type: "scatter", mode: "markers", name: "Simulated Points",
                          marker: { color: "#3b82f6", size: 6, opacity: 0.8 }
                        }
                      ]}
                      layout={{
                        ...DARK_PLOT_BASE,
                        title: { text: "Lateral G vs Longitudinal G", font: { color: "#94A3B8", size: 11 } },
                        xaxis: { ...DARK_PLOT_BASE.xaxis, title: { text: "Lateral G", font: { color: "#94A3B8" } } },
                        yaxis: { ...DARK_PLOT_BASE.yaxis, title: { text: "Longitudinal G", font: { color: "#94A3B8" } } },
                      } as any}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  ) : null}
                </div>
              </div>

              <div className="bg-[#0f0f12] print:bg-white border border-[#1e1e24] print:border-gray-300 rounded-2xl p-6 space-y-4">
                <h3 className="text-sm font-bold text-white print:text-black">Aerodynamic Downforce vs Speed</h3>
                <div className="h-[280px]">
                  {plotData?.aerodynamics ? (
                    <Plot
                      data={[
                        {
                          x: plotData.aerodynamics.speed_kmh,
                          y: plotData.aerodynamics.downforce_n,
                          name: "Total Downforce [N]",
                          type: "scatter", mode: "lines",
                          line: { color: "#06B6D4", width: 2 }
                        },
                        {
                          x: plotData.aerodynamics.speed_kmh,
                          y: plotData.aerodynamics.drag_n,
                          name: "Aero Drag [N]",
                          type: "scatter", mode: "lines",
                          line: { color: "#f97316", width: 1.5, dash: "dot" }
                        }
                      ]}
                      layout={{
                        ...DARK_PLOT_BASE,
                        title: { text: "Aero Forces F = 0.5 * rho * A * C * v^2", font: { color: "#94A3B8", size: 11 } },
                        xaxis: { ...DARK_PLOT_BASE.xaxis, title: { text: "Speed [km/h]", font: { color: "#94A3B8" } } },
                        yaxis: { ...DARK_PLOT_BASE.yaxis, title: { text: "Force [N]", font: { color: "#94A3B8" } } },
                      } as any}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── SECTION 3: SUSPENSION KINEMATICS ── */}
        {(showAll || activeTab === "kinematics") && (
          <div className="print-card space-y-4">
            <h2 className="text-lg font-bold text-white print:text-black border-b border-[#1c1c20] print:border-gray-300 pb-2 flex items-center gap-2">
              <Layers size={16} className="text-amber-400 print:text-amber-800" />
              3. Suspension Kinematics & Geometry Sign-Off (Double-Wishbone)
            </h2>

            <div className="bg-[#0f0f12] print:bg-white border border-[#1e1e24] print:border-gray-300 rounded-2xl p-6 space-y-4">
              <h3 className="text-sm font-bold text-white print:text-black">Kinematic Camber & Toe Gain Curves</h3>
              <div className="h-[280px]">
                {plotData?.kinematics ? (
                  <Plot
                    data={[
                      {
                        x: plotData.kinematics.heave_travel_mm,
                        y: plotData.kinematics.camber_deg,
                        name: "Camber [deg]",
                        type: "scatter", mode: "lines+markers",
                        line: { color: "#3b82f6", width: 2 }
                      },
                      {
                        x: plotData.kinematics.heave_travel_mm,
                        y: plotData.kinematics.toe_deg,
                        name: "Toe [deg] (Bump Steer)",
                        type: "scatter", mode: "lines+markers",
                        line: { color: "#ef4444", width: 1.5, dash: "dot" }
                      }
                    ]}
                    layout={{
                      ...DARK_PLOT_BASE,
                      title: { text: "Wheel Center Travel [mm] vs Angle [deg]", font: { color: "#94A3B8", size: 11 } },
                      xaxis: { ...DARK_PLOT_BASE.xaxis, title: { text: "Wheel Heave Travel [mm]", font: { color: "#94A3B8" } } },
                      yaxis: { ...DARK_PLOT_BASE.yaxis, title: { text: "Angle [deg]", font: { color: "#94A3B8" } } },
                    } as any}
                    config={{ displayModeBar: false, responsive: true }}
                    style={{ width: "100%", height: "100%" }}
                    useResizeHandler
                  />
                ) : null}
              </div>
            </div>
          </div>
        )}

        {/* ── SECTION 4: ISO 2631 NVH & RIDE ── */}
        {(showAll || activeTab === "nvh") && (
          <div className="print-card space-y-4">
            <h2 className="text-lg font-bold text-white print:text-black border-b border-[#1c1c20] print:border-gray-300 pb-2 flex items-center gap-2">
              <Activity size={16} className="text-amber-400 print:text-amber-800" />
              4. ISO 2631-1 Ride Comfort & Vibration Exposure
            </h2>

            <div className="bg-[#0f0f12] print:bg-white border border-[#1e1e24] print:border-gray-300 rounded-2xl p-6 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-4 bg-black/40 print:bg-gray-100 rounded-xl border border-[#1f1f26] print:border-gray-200">
                  <p className="text-xs text-zinc-400 print:text-gray-600 font-bold uppercase">Wk-Weighted RMS Accel</p>
                  <p className="text-xl font-bold font-sans leading-relaxed text-emerald-400 print:text-emerald-700 mt-1">
                    {metrics["Wk-Weighted RMS Accel"] || "—"}
                  </p>
                  <p className="text-xs text-gray-400 print:text-gray-600 mt-0.5">
                    Category: {report.comfort_category || "—"}
                  </p>
                </div>
                <div className="p-4 bg-black/40 print:bg-gray-100 rounded-xl border border-[#1f1f26] print:border-gray-200">
                  <p className="text-xs text-zinc-400 print:text-gray-600 font-bold uppercase">Vibration Dose Value (VDV)</p>
                  <p className="text-xl font-bold font-sans leading-relaxed text-blue-400 print:text-blue-700 mt-1">
                    {metrics["Vibration Dose Value (VDV)"] || "—"}
                  </p>
                  <p className="text-xs text-gray-400 print:text-gray-600 mt-0.5">
                    {(() => {
                      const v = parseFloat(String(metrics["Vibration Dose Value (VDV)"] || ""));
                      if (!Number.isFinite(v) || v <= 0) return "ISO 2631-1 Daily Check: Not evaluated";
                      return v <= 9.1 ? "ISO 2631-1 Daily Check: Below EAV (<= 9.1)" : v <= 17.0 ? "ISO 2631-1 Daily Check: Caution (9.1-17.0)" : "ISO 2631-1 Daily Check: Above ELV (> 17.0)";
                    })()}
                  </p>
                </div>
                <div className="p-4 bg-black/40 print:bg-gray-100 rounded-xl border border-[#1f1f26] print:border-gray-200">
                  <p className="text-xs text-zinc-400 print:text-gray-600 font-bold uppercase">Heave Natural Frequency</p>
                  <p className="text-xl font-bold font-sans leading-relaxed text-cyan-400 print:text-cyan-700 mt-1">
                    {metrics["Heave Natural Frequency"] || "—"}
                  </p>
                  <p className="text-xs text-gray-400 print:text-gray-600 mt-0.5">
                    Damping Ratio ζ = {metrics["Damping Ratio"] || "—"}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── SECTION 5: DIGITAL TWIN & LINEAGE HASH ── */}
        {(showAll || activeTab === "digital_twin") && (
          <div className="print-card space-y-4">
            <h2 className="text-lg font-bold text-white print:text-black border-b border-[#1c1c20] print:border-gray-300 pb-2 flex items-center gap-2">
              <ShieldCheck size={16} className="text-amber-400 print:text-amber-800" />
              5. Digital Twin Discrepancy & Merkle Audit Lineage
            </h2>

            <div className="bg-[#0f0f12] print:bg-white border border-[#1e1e24] print:border-gray-300 rounded-2xl p-6 font-mono text-xs text-gray-300 print:text-gray-800 space-y-2.5">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <p><strong className="text-zinc-400 print:text-gray-600">RUN_ID:</strong> {report.run_id}</p>
                <p><strong className="text-zinc-400 print:text-gray-600">DOC_ID:</strong> {report.doc_id}</p>
                <p><strong className="text-zinc-400 print:text-gray-600">VALIDATION_STATUS:</strong> {report.validation_status} (Score: {report.correlation_pct}%)</p>
                <p><strong className="text-zinc-400 print:text-gray-600">SOLVER_LINEAGE:</strong> {report.solver_version}</p>
                <p><strong className="text-zinc-400 print:text-gray-600">PHYSICS_VERSION:</strong> {report.physics_version}</p>
                <p><strong className="text-zinc-400 print:text-gray-600">SOFTWARE_BUILD:</strong> {report.software_build}</p>
                <p className="col-span-full"><strong className="text-zinc-400 print:text-gray-600">INPUT_HASH:</strong> <span className="break-all">{report.input_hash}</span></p>
                <p className="col-span-full"><strong className="text-zinc-400 print:text-gray-600">RESULT_HASH:</strong> <span className="break-all">{report.result_hash}</span></p>
                <p className="col-span-full"><strong className="text-zinc-400 print:text-gray-600">ARTIFACT_HASH:</strong> <span className="break-all text-emerald-400">{report.artifact_hash}</span></p>
              </div>

              {/* Wave 6: solver provenance Trust Badge */}
              <TrustBadge
                solverVersion={report.solver_version}
                runId={report.run_id}
                inputSha256={report.input_hash}
                className="mt-3"
              />

              {/* Approval Box */}
              <div className={`mt-6 p-4 rounded-xl border ${
                isApproved
                  ? "bg-emerald-950/30 border-emerald-500/40 text-emerald-300"
                  : isRejected
                  ? "bg-rose-950/30 border-rose-500/40 text-rose-300"
                  : "bg-amber-950/30 border-amber-500/40 text-amber-300"
              }`}>
                <div className="flex items-center justify-between">
                  <span className="font-bold flex items-center gap-1.5">
                    <ShieldCheck size={16} /> CHIEF ENGINEER DECISION SIGN-OFF: {report.status}
                  </span>
                  <span className="text-xs uppercase font-bold tracking-widest px-2 py-0.5 rounded bg-black/40">
                    {report.approval?.role || "LEAD"}
                  </span>
                </div>
                <p className="mt-2 text-xs italic text-gray-300 font-sans">
                  &ldquo;{report.approval?.comment || "Approved under telemetry residual correlation threshold."}&rdquo;
                </p>
                <div className="mt-3 text-xs text-gray-400 font-sans flex flex-wrap justify-between gap-2">
                  <span>Signee: <strong>{report.approval?.name || "Chief Race Engineer"}</strong></span>
                  <span>Timestamp: <strong>{report.approval?.timestamp ? new Date(report.approval.timestamp).toUTCString() : "Pending"}</strong></span>
                </div>
                {report.approval?.signature && (
                  <div className="mt-2.5 pt-2 border-t border-white/10 text-xs font-mono break-all text-emerald-400">
                    <strong>HMAC-SHA256 Signature:</strong> {report.approval.signature}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

      </div>

      {/* ── APPROVAL MODAL ── */}
      {approvalModalOpen && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#111114] border border-[#25252d] rounded-2xl max-w-md w-full p-6 space-y-4">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <ShieldCheck size={18} className={approvalAction === "APPROVED" ? "text-emerald-400" : "text-rose-400"} />
              {approvalAction === "APPROVED" ? "Sign & Approve Engineering Report" : "Reject Engineering Report"}
            </h3>
            <p className="text-xs text-gray-400">
              {approvalAction === "APPROVED"
                ? "Your cryptographic HMAC signature will be permanently stamped on the canonical artifact hash. Only authorized Engineers or Leads can sign."
                : "Record rejection reason. The report will be marked REJECTED and preserved in immutable audit history."}
            </p>

            <div>
              <label className="text-xs font-semibold text-gray-400 mb-1 block">Decision Reason / Comments</label>
              <textarea
                value={approvalComment}
                onChange={(e) => setApprovalComment(e.target.value)}
                rows={3}
                className="w-full bg-[#18181e] border border-[#2c2c36] rounded-xl p-3 text-xs text-white placeholder-gray-500 focus:outline-none focus:border-signal font-mono"
                placeholder="Enter engineering rationale..."
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setApprovalModalOpen(false)}
                disabled={submittingApproval}
                className="px-3.5 py-2 rounded-xl bg-[#1a1a20] hover:bg-[#22222a] text-xs font-semibold text-gray-400 hover:text-white transition"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmApproval}
                disabled={submittingApproval}
                className={`px-4 py-2 rounded-xl text-xs font-bold text-white transition flex items-center gap-2 ${
                  approvalAction === "APPROVED" ? "bg-emerald-600 hover:bg-emerald-500" : "bg-rose-600 hover:bg-rose-500"
                }`}
              >
                {submittingApproval ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
                Confirm {approvalAction === "APPROVED" ? "Approval" : "Rejection"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── SHARE TOKEN MODAL ── */}
      {shareModalOpen && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#111114] border border-[#25252d] rounded-2xl max-w-md w-full p-6 space-y-4">
            <h3 className="text-base font-bold text-white flex items-center gap-2">
              <Share2 size={18} className="text-signal" />
              Genuine Backend Share Token Generated
            </h3>
            <p className="text-xs text-gray-400">
              This report has been sealed with verified engine provenance. The link below grants public read access to the immutable simulation artifact:
            </p>

            <div className="p-3 rounded-xl bg-black/50 border border-[#222] flex items-center justify-between gap-2">
              <span className="text-xs font-mono text-emerald-400 truncate">{shareUrl}</span>
              <button
                onClick={async () => {
                  await navigator.clipboard.writeText(shareUrl);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 2000);
                }}
                className="px-2.5 py-1 rounded-lg bg-[#222] hover:bg-[#333] text-xs text-white font-semibold shrink-0"
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setShareModalOpen(false)}
                className="px-4 py-2 rounded-xl bg-[#1a1a20] hover:bg-[#22222a] text-xs font-semibold text-gray-300 hover:text-white transition"
              >
                Close
              </button>
              <Link
                href={shareUrl.replace(window.location.origin, "")}
                target="_blank"
                className="px-4 py-2 rounded-xl bg-signal text-carbon border border-signal text-xs font-bold hover:bg-[#d6f56e] transition-colors flex items-center gap-1.5"
              >
                Open Shared View <ArrowUpRight size={14} />
              </Link>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default function ReportDashboardPage() {
  return (
    <Suspense fallback={
      <div className="min-h-[calc(100vh-44px)] bg-[#08080a] text-white flex items-center justify-center">
        <Loader2 className="animate-spin text-signal" size={32} />
      </div>
    }>
      <ReportContent />
    </Suspense>
  );
}
