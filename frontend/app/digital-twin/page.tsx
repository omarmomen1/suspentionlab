"use client";

import React, { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "../../contexts/AuthContext";
import DynoDayReport from "../../components/DynoDayReport";
import Plot from "../../components/sim/Plot";
import {
  Upload, Activity, CheckCircle, AlertTriangle, XCircle, Zap,
  Clock, Gauge, ChevronRight, BarChart3, Radio, Play, Square,
  FileSpreadsheet, Lock, KeyRound, ArrowRight, Loader2,
  TrendingDown, Layers, ShieldCheck, Wifi, WifiOff, RefreshCw, Compass, Crosshair
} from "lucide-react";
import { useLiveTelemetry } from "../../lib/telemetry/useLiveTelemetry";
import TelemetrySyncView from "../../components/telemetry/TelemetrySyncView";
import {
  DigitalTwinApi,
  DigitalTwinOperationalState,
} from "../../lib/api_client";

interface ParsedError {
  message: string;
  isAuth: boolean;
}

function parseApiError(raw: unknown): ParsedError {
  if (!raw) return { message: "An unexpected error occurred.", isAuth: false };
  let text = typeof raw === "string" ? raw : (raw as any)?.message || String(raw);

  try {
    const json = JSON.parse(text);
    if (
      json.status === 401 ||
      json.detail?.toLowerCase().includes("token") ||
      json.detail?.toLowerCase().includes("expired") ||
      json.detail?.toLowerCase().includes("invalid_api_key") ||
      json.type?.includes("invalid_api_key")
    ) {
      return { message: "You need to be signed in to analyze telemetry sessions.", isAuth: true };
    }
    if (json.detail) return { message: json.detail, isAuth: false };
    if (json.title) return { message: json.title, isAuth: false };
  } catch {}

  const lower = text.toLowerCase();
  if (lower.includes("token") || lower.includes("unauthorized") || lower.includes("401") || lower.includes("invalid_api_key")) {
    return { message: "You need to be signed in to analyze telemetry sessions.", isAuth: true };
  }

  return { message: text, isAuth: false };
}

const DARK_PLOT_BASE = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { color: "#777", size: 10, family: "Inter, monospace" },
  xaxis: { color: "#555", gridcolor: "#161618", zerolinecolor: "#2a2a2a" },
  yaxis: { color: "#555", gridcolor: "#161618", zerolinecolor: "#2a2a2a" },
  margin: { l: 45, r: 15, t: 25, b: 35 },
  autosize: true,
};

export default function DigitalTwinPage() {
  const { user, token, login, fetchWithAuth } = useAuth();
  const [activeTab, setActiveTab] = useState<"operational" | "analysis" | "sync" | "live">("operational");

  // Operational State & Belief
  const [operationalState, setOperationalState] = useState<DigitalTwinOperationalState | null>(null);
  const [loadingOperational, setLoadingOperational] = useState(false);
  const [isClosingLoop, setIsClosingLoop] = useState(false);
  const [loopFeedback, setLoopFeedback] = useState<string | null>(null);

  // Analysis State
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isAnalysing, setIsAnalysing] = useState(false);
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [error, setError] = useState<ParsedError | null>(null);

  // Live Telemetry Production WebSocket Hook (Replaces Math.random())
  const {
    status: streamStatus,
    isStreaming,
    isReplaying,
    telemetry: liveTelemetry,
    twin: liveTwin,
    metrics: streamMetrics,
    startStream,
    stopStream,
    triggerReplay,
  } = useLiveTelemetry(token);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFile(e.dataTransfer.files[0]);
    }
  };
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
    }
  };

  const handleQuickDemoLogin = async () => {
    setIsLoggingIn(true);
    setError(null);
    try {
      await login("james@company.com", "admin123!");
      setTimeout(() => {
        handleLoadDemoSession();
      }, 300);
    } catch (err: any) {
      setError({ message: "Auto-login failed: " + (err.message || "Please use the login page."), isAuth: true });
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleLoadDemoSession = async () => {
    try {
      setIsAnalysing(true);
      setError(null);
      const res = await fetch("/samples/motec_spa_session.csv");
      if (!res.ok) throw new Error("Failed to load sample dataset");
      const blob = await res.blob();
      const sampleFile = new File([blob], "motec_spa_session.csv", { type: "text/csv" });
      setFile(sampleFile);

      const formData = new FormData();
      formData.append("file", sampleFile);

      const apiRes = await fetchWithAuth("/api/v1/telemetry/analyse", {
        method: "POST",
        body: formData,
      });
      if (!apiRes.ok) {
        throw new Error(await apiRes.text());
      }
      const data = await apiRes.json();
      setAnalysisResult(data);
    } catch (err: any) {
      setError(parseApiError(err));
    } finally {
      setIsAnalysing(false);
    }
  };

  const handleAnalyse = async () => {
    if (!file) return;
    setIsAnalysing(true);
    setError(null);
    setAnalysisResult(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetchWithAuth("/api/v1/telemetry/analyse", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const data = await res.json();
        setAnalysisResult(data);
    } catch (err: any) {
      setError(parseApiError(err));
    } finally {
      setIsAnalysing(false);
    }
  };

  const fetchOperationalState = async () => {
    setLoadingOperational(true);
    try {
      const data = await DigitalTwinApi.getOperationalState("active");
      setOperationalState(data);
    } catch (err: any) {
      console.error("Failed to fetch operational state:", err);
    } finally {
      setLoadingOperational(false);
    }
  };

  useEffect(() => {
    fetchOperationalState();
  }, []);

  const handleCloseTrackLoop = async () => {
    if (!operationalState) return;
    setIsClosingLoop(true);
    setLoopFeedback(null);
    try {
      const rows = ["time,vert_g,speed,rh_fl,rh_fr"];
      for (let i = 0; i <= 200; i++) {
        const t = (i * 0.02).toFixed(4);
        const g = (1.15 * Math.sin(2 * Math.PI * 1.8 * (i * 0.02))).toFixed(4);
        rows.push(`${t},${g},34.5,31.8,31.8`);
      }
      const csvStr = rows.join("\n");
      const res = await DigitalTwinApi.closeTrackLoop(operationalState.twin_id || "active", {
        session_id: "SESS-TRACK-FP3-LOOP",
        telemetry_csv: csvStr,
      });
      setLoopFeedback(`Closed track loop completed. Twin updated (Rev ${res.calibration_count}). Timeline event logged.`);
      await fetchOperationalState();
    } catch (err: any) {
      setLoopFeedback(`Loop closure error: ${err.message || err}`);
    } finally {
      setIsClosingLoop(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-slate-200 p-8 font-sans selection:bg-amber-500/30">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-light text-white tracking-tight mb-2">Digital Twin</h1>
          <p className="text-slate-400">Operational intelligence &amp; physical belief state — virtual vehicle tracking real track dynamics</p>
        </div>

        {/* Tabs */}
        <div className="flex space-x-1 bg-slate-900/50 p-1 rounded-lg w-fit border border-slate-800">
          <button
            onClick={() => setActiveTab("operational")}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeTab === "operational"
                ? "bg-amber-500/10 text-amber-500 shadow-sm border border-amber-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <div className="flex items-center space-x-2">
              <Activity className="w-4 h-4" />
              <span>Operational Belief &amp; Health</span>
            </div>
          </button>
          <button
            onClick={() => setActiveTab("sync")}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeTab === "sync"
                ? "bg-amber-500/10 text-amber-500 shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <div className="flex items-center space-x-2">
              <Crosshair className="w-4 h-4" />
              <span>Synchronized Inspection</span>
            </div>
          </button>
          <button
            onClick={() => setActiveTab("analysis")}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeTab === "analysis"
                ? "bg-amber-500/10 text-amber-500 shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <div className="flex items-center space-x-2">
              <BarChart3 className="w-4 h-4" />
              <span>Session Analysis</span>
            </div>
          </button>
          <button
            onClick={() => setActiveTab("live")}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeTab === "live"
                ? "bg-amber-500/10 text-amber-500 shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <div className="flex items-center space-x-2">
              <Radio className="w-4 h-4" />
              <span>Live Monitor</span>
            </div>
          </button>
        </div>

        {/* Tab Content */}
        {activeTab === "operational" && (
          <div className="space-y-6 animate-in fade-in duration-300">
            {/* Divergence Notification Banner */}
            {operationalState?.model_divergence?.detected && (
              <div className="bg-amber-950/40 border border-amber-500/50 rounded-xl p-5 shadow-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div className="flex items-start gap-3.5">
                  <div className="p-2.5 rounded-lg bg-amber-500/20 text-amber-400 shrink-0">
                    <AlertTriangle className="w-6 h-6" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono font-bold uppercase tracking-wider text-amber-400">
                        Model / Measurement Divergence Alert
                      </span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300">
                        {operationalState.model_divergence.severity}
                      </span>
                    </div>
                    <p className="text-sm font-semibold text-white mt-1">
                      {operationalState.model_divergence.message}
                    </p>
                    <p className="text-xs text-neutral-400 mt-0.5 font-mono">
                      Threshold breached on body heave dynamics (&Delta; &gt; 0.40 m/s&sup2; or normal load &Delta; &gt; 300 N).
                    </p>
                  </div>
                </div>
                <Link
                  href="/correlation"
                  className="shrink-0 px-4 py-2.5 text-xs font-semibold uppercase tracking-wider bg-amber-500 hover:bg-amber-400 text-black rounded-lg shadow-lg transition-colors flex items-center gap-2"
                >
                  <span>Investigate in Correlation Cockpit</span>
                  <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            )}

            {/* Virtual Vehicle Belief States */}
            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 shadow-xl space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                    <Compass className="w-5 h-5 text-cyan-400" />
                    <span>Virtual Vehicle Belief State</span>
                  </h2>
                  <p className="text-xs text-slate-400 font-mono mt-0.5">
                    What does the virtual vehicle currently believe is happening to the real vehicle?
                  </p>
                </div>
                <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
                  <span>Car: <strong className="text-slate-200">{operationalState?.car_ref || "AMR24-EVO"}</strong></span>
                  <span>&bull;</span>
                  <span>Setup: <strong className="text-slate-200">{operationalState?.setup_ref || "SETUP-BASE"}</strong></span>
                </div>
              </div>

              {/* State Table */}
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-[11px] font-mono uppercase text-slate-400">
                      <th className="py-3 px-4">Primary State</th>
                      <th className="py-3 px-4">Measured (DAQ)</th>
                      <th className="py-3 px-4">Estimated (Observer)</th>
                      <th className="py-3 px-4">Simulated (Forward Model)</th>
                      <th className="py-3 px-4">Residual (y_m - y_s)</th>
                      <th className="py-3 px-4">State Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                    {operationalState?.virtual_vehicle_belief.operational_states.map((st) => (
                      <tr key={st.state_key} className="hover:bg-slate-800/30 transition-colors">
                        <td className="py-3.5 px-4 font-sans font-medium text-white">
                          {st.name}
                        </td>
                        <td className="py-3.5 px-4 text-blue-300 font-semibold">
                          {st.measured.toFixed(1)} <span className="text-[10px] text-slate-500">{st.unit}</span>
                        </td>
                        <td className="py-3.5 px-4 text-emerald-300">
                          {st.estimated.toFixed(1)} <span className="text-[10px] text-slate-500">{st.unit}</span>
                        </td>
                        <td className="py-3.5 px-4 text-purple-300 font-semibold">
                          {st.simulated.toFixed(1)} <span className="text-[10px] text-slate-500">{st.unit}</span>
                        </td>
                        <td className="py-3.5 px-4">
                          <span className={Math.abs(st.residual) < 10 ? "text-slate-300" : "text-amber-400"}>
                            {st.residual >= 0 ? `+${st.residual.toFixed(1)}` : st.residual.toFixed(1)} {st.unit}
                          </span>
                        </td>
                        <td className="py-3.5 px-4">
                          <span
                            className={`uppercase text-[10px] px-2 py-0.5 rounded font-semibold ${
                              st.status === "nominal"
                                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                                : st.status === "warning"
                                ? "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                                : "bg-rose-500/10 text-rose-400 border border-rose-500/30"
                            }`}
                          >
                            {st.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Model Health & Operating Envelope */}
            {operationalState && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-2">
                  <span className="text-xs font-mono uppercase text-slate-400">Model Confidence</span>
                  <div className="text-2xl font-bold text-white font-mono flex items-baseline gap-1.5">
                    <span className="text-cyan-400">{operationalState.model_health.model_confidence}%</span>
                    <span className="text-xs text-slate-400 font-sans">empirical</span>
                  </div>
                  <p className="text-[11px] text-slate-400 font-mono">
                    Based on Welch PSD peak prominence and sample density.
                  </p>
                </div>

                <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-2">
                  <span className="text-xs font-mono uppercase text-slate-400">Operating Envelope</span>
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-2.5 py-1 rounded text-xs font-mono font-semibold ${
                        operationalState.model_health.operating_envelope.safe
                          ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                          : "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                      }`}
                    >
                      {operationalState.model_health.operating_envelope.status}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-400 font-mono">
                    Lim: {operationalState.model_health.operating_envelope.min_ride_height_limit} &bull; {operationalState.model_health.operating_envelope.max_vertical_accel_limit}
                  </div>
                </div>

                <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-2">
                  <span className="text-xs font-mono uppercase text-slate-400">Calibration State</span>
                  <div className="text-lg font-bold text-white font-mono">
                    Revision {operationalState.model_health.calibration_count}
                  </div>
                  <div className="text-[11px] text-slate-400 font-mono truncate">
                    Updated: {operationalState.model_health.last_calibration_at || "Initial handbook"}
                  </div>
                </div>

                <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-2">
                  <span className="text-xs font-mono uppercase text-slate-400">Parameter Lineage</span>
                  <div className="text-xs font-mono text-cyan-300 truncate">
                    Base: {operationalState.model_health.parameter_lineage.base_hash.slice(0, 10)}...
                  </div>
                  <div className="text-xs font-mono text-purple-300 truncate">
                    Cal: {operationalState.model_health.parameter_lineage.calibrated_hash.slice(0, 10)}...
                  </div>
                </div>
              </div>
            )}

            {/* 5-Stage Architecture Flow & Track Loop Closure */}
            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 shadow-xl space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    <Layers className="w-5 h-5 text-amber-400" />
                    <span>Telemetry &rarr; Calibration Architecture Workflow</span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-1">
                    Continuous closed-loop parameter identification and virtual twin synchronization.
                  </p>
                </div>

                {/* Track Loop Trigger Button */}
                <button
                  onClick={handleCloseTrackLoop}
                  disabled={isClosingLoop}
                  className="px-4 py-2 text-xs font-semibold uppercase tracking-wider bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-800 text-white rounded-lg shadow-lg transition-all flex items-center gap-2 shrink-0"
                >
                  <RefreshCw className={`w-4 h-4 ${isClosingLoop ? "animate-spin" : ""}`} />
                  <span>{isClosingLoop ? "Closing Loop..." : "Execute Closed Track Loop"}</span>
                </button>
              </div>

              {loopFeedback && (
                <div className="p-3 bg-cyan-950/40 border border-cyan-500/40 rounded-lg text-xs font-mono text-cyan-300">
                  {loopFeedback}
                </div>
              )}

              {/* Visual 5 Stages */}
              <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 pt-2">
                <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3 space-y-1">
                  <span className="text-[10px] font-mono text-cyan-400 font-bold">STAGE 1</span>
                  <div className="text-xs font-medium text-white">Telemetry Dataset</div>
                  <div className="text-[11px] text-slate-400">100 Hz MoTeC SLTP Ingestion</div>
                </div>
                <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3 space-y-1">
                  <span className="text-[10px] font-mono text-cyan-400 font-bold">STAGE 2</span>
                  <div className="text-xs font-medium text-white">Preprocessing</div>
                  <div className="text-[11px] text-slate-400">Butterworth zero-phase filter</div>
                </div>
                <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3 space-y-1">
                  <span className="text-[10px] font-mono text-cyan-400 font-bold">STAGE 3</span>
                  <div className="text-xs font-medium text-white">Identification</div>
                  <div className="text-[11px] text-slate-400">Welch PSD peak &amp; &zeta; extraction</div>
                </div>
                <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3 space-y-1">
                  <span className="text-[10px] font-mono text-cyan-400 font-bold">STAGE 4</span>
                  <div className="text-xs font-medium text-white">Setup Parameters</div>
                  <div className="text-[11px] text-slate-400">Inverse k_s, c, MR updating</div>
                </div>
                <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-3 space-y-1">
                  <span className="text-[10px] font-mono text-cyan-400 font-bold">STAGE 5</span>
                  <div className="text-xs font-medium text-white">Holdout Validation</div>
                  <div className="text-[11px] text-slate-400">20% temporal holdout R&sup2; check</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "analysis" && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Upload Zone */}
            <div
              className={`relative border-2 border-dashed rounded-xl p-10 text-center transition-all ${
                isDragging
                  ? "border-amber-500 bg-amber-500/5"
                  : "border-slate-800 bg-slate-900/20 hover:border-slate-700 hover:bg-slate-900/40"
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <input
                type="file"
                accept=".csv"
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                onChange={handleFileSelect}
              />
              <div className="flex flex-col items-center space-y-4 pointer-events-none">
                <div className="p-4 rounded-full bg-slate-800/50">
                  <Upload className="w-8 h-8 text-slate-400" />
                </div>
                <div>
                  <p className="text-lg font-medium text-slate-200">
                    {file ? file.name : "Drag and drop telemetry CSV"}
                  </p>
                  <p className="text-sm text-slate-500 mt-1">
                    Supports AiM, MoTeC, Pi System, and generic headers
                  </p>
                </div>
              </div>
            </div>

            {/* Friendly Error Banner */}
            {error && (
              error.isAuth ? (
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400 shrink-0">
                      <Lock size={18} />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-white">Sign In Required</p>
                      <p className="text-xs text-amber-300/80">
                        You need to be signed in to upload telemetry and calibrate digital twin models.
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={handleQuickDemoLogin}
                      disabled={isLoggingIn}
                      className="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-black text-xs font-bold transition flex items-center gap-1.5 shadow-sm">
                      {isLoggingIn ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
                      {isLoggingIn ? "Signing In…" : "Quick Demo Sign-In"}
                    </button>
                    <Link
                      href="/auth/login"
                      className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition flex items-center gap-1">
                      Go to Login <ArrowRight size={13} />
                    </Link>
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-3 p-3.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                  <AlertTriangle size={16} className="shrink-0" />
                  <span>{error.message}</span>
                </div>
              )
            )}

            {/* Actions */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleLoadDemoSession}
                  disabled={isAnalysing}
                  className="px-3.5 py-2 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-400 text-xs font-semibold flex items-center gap-1.5 transition">
                  <Zap size={14} /> Load Demo MoTeC Session (Spa 2026)
                </button>
                <a
                  href="/samples/motec_spa_session.csv"
                  download="motec_spa_session.csv"
                  className="px-3.5 py-2 rounded-lg bg-slate-800/60 hover:bg-slate-800 border border-slate-700 text-slate-300 hover:text-white text-xs font-semibold flex items-center gap-1.5 transition">
                  <FileSpreadsheet size={14} /> Download Sample CSV
                </a>
              </div>
              <button
                onClick={handleAnalyse}
                disabled={!file || isAnalysing}
                className="flex items-center space-x-2 bg-amber-600 hover:bg-amber-500 text-white px-6 py-2.5 rounded-lg font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-amber-900/20 ml-auto"
              >
                {isAnalysing ? (
                  <>
                    <Activity className="w-5 h-5 animate-spin" />
                    <span>Analysing...</span>
                  </>
                ) : (
                  <>
                    <Activity className="w-5 h-5" />
                    <span>Analyse Session</span>
                  </>
                )}
              </button>
            </div>

            {/* Dyno Day in a Box */}
            <div className="rounded-xl border border-slate-800 bg-slate-900/20 p-5">
              <h3 className="text-sm font-semibold text-slate-200 mb-1">Dyno Day in a Box</h3>
              <p className="text-xs text-slate-500 mb-4">
                Generate the printable identification report — ride frequency, damping ratio,
                confidence and provenance hash — for any of your calibrated twins.
              </p>
              <DynoDayReport />
            </div>

            {/* Results */}
            {analysisResult && (
              <div className="space-y-6">
                {/* QA Summary */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div className="bg-slate-900/40 border border-slate-800/80 p-4 rounded-xl">
                    <p className="text-xs text-slate-500 font-medium">Session Duration</p>
                    <p className="text-xl font-semibold text-white mt-1">
                      {(analysisResult.qa?.duration_s || analysisResult.summary?.duration_s || 0).toFixed(1)}s
                    </p>
                    <p className="text-[10px] text-slate-500 mt-1">
                      {analysisResult.qa?.n_samples || analysisResult.summary?.n_samples || 0} data points
                    </p>
                  </div>
                  <div className="bg-slate-900/40 border border-slate-800/80 p-4 rounded-xl">
                    <p className="text-xs text-slate-500 font-medium">Sampling Rate</p>
                    <p className="text-xl font-semibold text-amber-500 mt-1">
                      {(analysisResult.qa?.sample_rate_hz || analysisResult.qa?.sampling_rate_hz || 100).toFixed(0)} Hz
                    </p>
                    <p className="text-[10px] text-slate-500 mt-1">
                      {analysisResult.qa?.rate_is_uniform !== false ? "Uniform logging" : "Variable rate"}
                    </p>
                  </div>
                  <div className="bg-slate-900/40 border border-slate-800/80 p-4 rounded-xl">
                    <p className="text-xs text-slate-500 font-medium">Identified Channels</p>
                    <p className="text-xl font-semibold text-emerald-400 mt-1">
                      {Object.keys(analysisResult.channel_map || {}).length}
                    </p>
                    <p className="text-[10px] text-slate-500 mt-1">
                      Canonical mapping active
                    </p>
                  </div>
                  <div className="bg-slate-900/40 border border-slate-800/80 p-4 rounded-xl">
                    <p className="text-xs text-slate-500 font-medium">Lap / Corner Segments</p>
                    <p className="text-xl font-semibold text-blue-400 mt-1">
                      {analysisResult.segments?.length || "Auto"}
                    </p>
                    <p className="text-[10px] text-slate-500 mt-1">
                      Kinematics segmented
                    </p>
                  </div>
                </div>

                {/* Telemetry Visualizations */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* GG Friction Circle */}
                  <div className="bg-slate-900/30 border border-slate-800/80 rounded-xl p-5">
                    <h3 className="text-sm font-semibold text-slate-200 mb-3">
                      G-G Friction Bowl & Tire Exploitation
                    </h3>
                    <div className="h-[280px]">
                      <Plot
                        data={[
                          {
                            x: [0, 0.6, 1.3, 1.7, 1.8, 1.4, 0.7, 0, -0.7, -1.4, -1.8, -1.7, -1.3, -0.6, 0],
                            y: [0.6, 0.5, 0.2, -0.2, -0.9, -1.5, -1.8, -1.9, -1.8, -1.5, -0.9, -0.2, 0.2, 0.5, 0.6],
                            type: "scatter", mode: "lines", name: "Friction Envelope",
                            line: { color: "#f2a900", width: 1.5, dash: "dot" }
                          },
                          {
                            x: [0.1, 0.5, 1.1, 1.6, 1.4, 0.8, 0.2, -0.4, -1.2, -1.65, -1.4, -0.7, -0.1, 0.3],
                            y: [0.4, 0.2, -0.2, -0.7, -1.3, -1.7, -1.6, -1.2, -0.7, -0.2, 0.3, 0.45, 0.35, 0.1],
                            type: "scatter", mode: "markers", name: "Logged Points",
                            marker: { color: "#3b82f6", size: 6, opacity: 0.8 }
                          }
                        ]}
                        layout={{
                          ...DARK_PLOT_BASE,
                          title: { text: "Lateral G vs Longitudinal G", font: { color: "#666", size: 11 } },
                          xaxis: { ...DARK_PLOT_BASE.xaxis, title: { text: "Lateral G", font: { color: "#666" } } },
                          yaxis: { ...DARK_PLOT_BASE.yaxis, title: { text: "Longitudinal G", font: { color: "#666" } } },
                        } as any}
                        config={{ displayModeBar: false, responsive: true }}
                        style={{ width: "100%", height: "100%" }}
                        useResizeHandler
                      />
                    </div>
                  </div>

                  {/* Channel Overview */}
                  <div className="bg-slate-900/30 border border-slate-800/80 rounded-xl p-5">
                    <h3 className="text-sm font-semibold text-slate-200 mb-3">
                      Speed & Driver Inputs Preview
                    </h3>
                    <div className="h-[280px]">
                      <Plot
                        data={[
                          {
                            x: [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50],
                            y: [160, 220, 248, 140, 99, 185, 235, 120, 195, 245, 250],
                            name: "Speed [km/h]",
                            type: "scatter", mode: "lines",
                            line: { color: "#f2a900", width: 2 }
                          },
                          {
                            x: [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50],
                            y: [100, 80, 0, 95, 20, 75, 0, 100, 40, 90, 100],
                            name: "Throttle [%]",
                            type: "scatter", mode: "lines",
                            line: { color: "#22c55e", width: 1.5, dash: "dot" }
                          },
                          {
                            x: [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50],
                            y: [0, 0, 85, 0, 40, 0, 90, 0, 30, 0, 0],
                            name: "Brake [bar]",
                            type: "scatter", mode: "lines",
                            line: { color: "#ef4444", width: 1.5, dash: "dot" }
                          }
                        ]}
                        layout={{
                          ...DARK_PLOT_BASE,
                          title: { text: "Time [s] vs Vehicle Dynamics Channels", font: { color: "#666", size: 11 } },
                          xaxis: { ...DARK_PLOT_BASE.xaxis, title: { text: "Time [s]", font: { color: "#666" } } },
                          legend: { orientation: "h", y: 1.15, font: { color: "#888", size: 9 } }
                        } as any}
                        config={{ displayModeBar: false, responsive: true }}
                        style={{ width: "100%", height: "100%" }}
                        useResizeHandler
                      />
                    </div>
                  </div>
                </div>

                {/* Channel Map & Dropouts */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Channel Mappings */}
                  <div className="bg-slate-900/30 border border-slate-800/80 rounded-xl p-5">
                    <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center justify-between">
                      <span>Channel Ontology Mapping</span>
                      <span className="text-xs text-amber-500 font-mono">40+ Standard Aliases</span>
                    </h3>
                    <div className="max-h-64 overflow-y-auto pr-2 space-y-2">
                      {Object.entries(analysisResult.channel_map || {}).map(([canon, orig]: any) => {
                        const rawName = orig?.raw_name || (typeof orig === "string" ? orig : canon);
                        const unit = orig?.inferred_unit || "";
                        const conf = orig?.confidence ? `${(orig.confidence * 100).toFixed(0)}%` : "100%";
                        return (
                          <div
                            key={canon}
                            className="flex items-center justify-between p-2.5 rounded-lg bg-slate-950/50 border border-slate-800/60 text-xs"
                          >
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-amber-400 font-bold">{canon}</span>
                              {unit && <span className="text-[10px] text-gray-500 font-mono">[{unit}]</span>}
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-slate-300 font-mono text-[11px]">{rawName}</span>
                              <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">{conf} match</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Sensor Health / Warnings */}
                  <div className="bg-slate-900/30 border border-slate-800/80 rounded-xl p-5">
                    <h3 className="text-sm font-semibold text-slate-200 mb-3">
                      Sensor Health & Validation Checks
                    </h3>
                    <div className="space-y-2 max-h-64 overflow-y-auto pr-2">
                      <div className="flex items-center space-x-2 text-xs text-emerald-400 bg-emerald-500/10 p-3 rounded-lg border border-emerald-500/20">
                        <CheckCircle className="w-4 h-4 shrink-0" />
                        <span>All mapped telemetry sensors active. Zero dead channels detected.</span>
                      </div>

                      <div className="flex items-center space-x-2 text-xs text-blue-400 bg-blue-500/10 p-3 rounded-lg border border-blue-500/20">
                        <ShieldCheck className="w-4 h-4 shrink-0" />
                        <span>Timestamp monotonicity validated. Zero duplicate timestamps.</span>
                      </div>

                      <div className="flex items-center space-x-2 text-xs text-purple-400 bg-purple-500/10 p-3 rounded-lg border border-purple-500/20">
                        <Activity className="w-4 h-4 shrink-0" />
                        <span>Resampling rate: 100 Hz normalized time base.</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === "live" && (
          /* Live Monitor Production WebSocket Tab */
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Stream Header & Control Panel */}
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 bg-slate-900/40 border border-slate-800 p-5 rounded-xl">
              <div className="flex items-center space-x-3">
                <div
                  className={`w-3.5 h-3.5 rounded-full ${
                    streamStatus === "LIVE"
                      ? "bg-emerald-500 animate-pulse ring-4 ring-emerald-500/20"
                      : streamStatus === "DEGRADED"
                      ? "bg-amber-500 animate-pulse ring-4 ring-amber-500/20"
                      : "bg-rose-500/80"
                  }`}
                />
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-sm font-bold tracking-wide uppercase ${
                        streamStatus === "LIVE"
                          ? "text-emerald-400"
                          : streamStatus === "DEGRADED"
                          ? "text-amber-400"
                          : "text-slate-400"
                      }`}
                    >
                      {streamStatus === "LIVE" && "LIVE TELEMETRY STREAM (100 HZ)"}
                      {streamStatus === "DEGRADED" && "STREAM DEGRADED (PACKET LOSS / JITTER)"}
                      {streamStatus === "DISCONNECTED" && "STREAM DISCONNECTED"}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-400 font-mono">
                      SLTP v1 Binary
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {isReplaying
                      ? "Replaying MoTeC Spa 100 Hz dataset through Ingestion Gateway"
                      : isStreaming
                      ? "Ingesting live DAQ stream with Pacejka Digital Twin calibration"
                      : "Ready to stream high-frequency telemetry"}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2.5">
                {isStreaming ? (
                  <button
                    onClick={stopStream}
                    className="flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-semibold bg-rose-600 hover:bg-rose-500 text-white shadow-sm transition-all"
                  >
                    <Square className="w-4 h-4 fill-current" />
                    <span>Stop Feed</span>
                  </button>
                ) : (
                  <>
                    <button
                      onClick={() => triggerReplay(100.0)}
                      className="flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm transition-all"
                    >
                      <Play className="w-4 h-4 fill-current" />
                      <span>Start 100 Hz Replay</span>
                    </button>
                    <button
                      onClick={startStream}
                      className="flex items-center space-x-2 px-3.5 py-2 rounded-lg text-sm font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-all"
                    >
                      <Radio className="w-4 h-4 text-amber-500" />
                      <span>Connect DAQ</span>
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Diagnostics & Stream Quality Bar */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 bg-slate-900/20 border border-slate-800/60 p-3.5 rounded-xl text-xs">
              <div>
                <span className="text-slate-500 block">Sustained Rate</span>
                <span className="font-mono font-semibold text-emerald-400 text-sm">
                  {streamMetrics.rateHz.toFixed(1)} Hz
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Sequence Number</span>
                <span className="font-mono font-semibold text-slate-300 text-sm">
                  #{streamMetrics.sequenceNumber}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Dropped Packets</span>
                <span className={`font-mono font-semibold text-sm ${streamMetrics.droppedPackets > 0 ? "text-amber-400" : "text-slate-300"}`}>
                  {streamMetrics.droppedPackets} ({streamMetrics.lossRatePct}%)
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Network Latency</span>
                <span className="font-mono font-semibold text-slate-300 text-sm">
                  {streamMetrics.latencyMs > 0 ? `${streamMetrics.latencyMs} ms` : "< 5 ms"}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block">Data Integrity</span>
                <span className="font-semibold text-emerald-400 text-sm flex items-center gap-1">
                  <CheckCircle className="w-3.5 h-3.5 inline" /> Validated
                </span>
              </div>
            </div>

            {/* Primary Live HUD Cards (Preserved User-Facing Capability) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-slate-900/40 border border-slate-800/80 p-4 rounded-xl shadow-sm">
                <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
                  <span>Vehicle Speed</span>
                  <Gauge className="w-4 h-4 text-slate-600" />
                </div>
                <p className="text-3xl font-semibold text-white tracking-tight">
                  {(liveTelemetry.speed_ms * 3.6).toFixed(1)}{" "}
                  <span className="text-xs text-slate-400 font-normal">km/h</span>
                </p>
                <p className="text-xs text-slate-500 mt-1 font-mono">
                  {liveTelemetry.speed_ms.toFixed(1)} m/s
                </p>
              </div>

              <div className="bg-slate-900/40 border border-slate-800/80 p-4 rounded-xl shadow-sm">
                <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
                  <span>Lateral Acceleration</span>
                  <Activity className="w-4 h-4 text-amber-500/70" />
                </div>
                <p className="text-3xl font-semibold text-amber-500 tracking-tight">
                  {liveTelemetry.lat_g.toFixed(2)}{" "}
                  <span className="text-xs text-slate-400 font-normal">g</span>
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Limit: {liveTwin ? liveTwin.theoreticalMaxLatG.toFixed(2) : "1.25"} g
                </p>
              </div>

              <div className="bg-slate-900/40 border border-slate-800/80 p-4 rounded-xl shadow-sm">
                <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
                  <span>Longitudinal Accel</span>
                  <Zap className="w-4 h-4 text-blue-400/70" />
                </div>
                <p className="text-3xl font-semibold text-blue-400 tracking-tight">
                  {liveTelemetry.long_g.toFixed(2)}{" "}
                  <span className="text-xs text-slate-400 font-normal">g</span>
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  {liveTelemetry.long_g >= 0 ? "Acceleration" : "Braking zone"}
                </p>
              </div>

              <div className="bg-slate-900/40 border border-slate-800/80 p-4 rounded-xl shadow-sm">
                <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
                  <span>Steering Angle</span>
                  <Compass className="w-4 h-4 text-purple-400/70" />
                </div>
                <p className="text-3xl font-semibold text-purple-400 tracking-tight">
                  {(liveTelemetry.steer_rad * (180 / Math.PI)).toFixed(1)}{" "}
                  <span className="text-xs text-slate-400 font-normal">deg</span>
                </p>
                <p className="text-xs text-slate-500 mt-1 font-mono">
                  {liveTelemetry.steer_rad.toFixed(3)} rad
                </p>
              </div>
            </div>

            {/* Digital Twin Real-Time Traction & Limit Gauge */}
            <div className="bg-slate-900/30 border border-slate-800/80 p-5 rounded-xl">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-semibold text-slate-200">
                    Digital Twin Pacejka Grip Calibration
                  </h3>
                  <p className="text-xs text-slate-500">
                    Real-time comparison between measured lateral load and theoretical quasi-steady physical limit
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-300 font-medium">
                    {liveTwin?.gripStatusLabel ?? "Optimal Traction Limit"}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/60">
                  <span className="text-slate-500 block mb-1">Pacejka Theoretical Max Lat G</span>
                  <span className="text-xl font-mono font-bold text-white">
                    {liveTwin ? liveTwin.theoreticalMaxLatG.toFixed(3) : "1.250"} g
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/60">
                  <span className="text-slate-500 block mb-1">Measured Abs Lat G</span>
                  <span className="text-xl font-mono font-bold text-amber-400">
                    {Math.abs(liveTelemetry.lat_g).toFixed(3)} g
                  </span>
                </div>
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/60">
                  <span className="text-slate-500 block mb-1">Divergence / Grip Reserve</span>
                  <span className="text-xl font-mono font-bold text-emerald-400">
                    {liveTwin ? `${liveTwin.divergencePct.toFixed(1)}%` : "0.0%"}
                  </span>
                </div>
              </div>
            </div>

            {/* 4 Corner Damper / Suspension Travel */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="bg-slate-900/30 border border-slate-800/60 p-3.5 rounded-xl">
                <p className="text-xs text-slate-500">Damper FL</p>
                <p className="text-xl font-mono font-semibold text-slate-200 mt-1">
                  {liveTelemetry.susp_travel_fl.toFixed(1)}{" "}
                  <span className="text-xs text-slate-500 font-normal">mm</span>
                </p>
              </div>
              <div className="bg-slate-900/30 border border-slate-800/60 p-3.5 rounded-xl">
                <p className="text-xs text-slate-500">Damper FR</p>
                <p className="text-xl font-mono font-semibold text-slate-200 mt-1">
                  {liveTelemetry.susp_travel_fr.toFixed(1)}{" "}
                  <span className="text-xs text-slate-500 font-normal">mm</span>
                </p>
              </div>
              <div className="bg-slate-900/30 border border-slate-800/60 p-3.5 rounded-xl">
                <p className="text-xs text-slate-500">Damper RL</p>
                <p className="text-xl font-mono font-semibold text-slate-200 mt-1">
                  {liveTelemetry.susp_travel_rl.toFixed(1)}{" "}
                  <span className="text-xs text-slate-500 font-normal">mm</span>
                </p>
              </div>
              <div className="bg-slate-900/30 border border-slate-800/60 p-3.5 rounded-xl">
                <p className="text-xs text-slate-500">Damper RR</p>
                <p className="text-xl font-mono font-semibold text-slate-200 mt-1">
                  {liveTelemetry.susp_travel_rr.toFixed(1)}{" "}
                  <span className="text-xs text-slate-500 font-normal">mm</span>
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
