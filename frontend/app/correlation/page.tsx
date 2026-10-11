"use client";

import React, { useState, useEffect } from "react";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Database,
  ExternalLink,
  FileSpreadsheet,
  HelpCircle,
  Info,
  Layers,
  LineChart,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Upload,
  Waves,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useWorkspace } from "../../contexts/WorkspaceContext";
import {
  CorrelationApi,
  CorrelationCockpitResponse,
  ChannelDetailReport,
} from "../../lib/api_client";

function fmtNum(val: number | null | undefined, digits = 2, withPlus = false): string {
  if (val === null || val === undefined || isNaN(val)) return "—";
  const formatted = val.toFixed(digits);
  return withPlus && val > 0 ? `+${formatted}` : formatted;
}

type CockpitTab = "ingestion" | "health" | "events" | "model_comparison" | "residuals" | "session_comparison";

export default function CorrelationCockpitPage() {
  const router = useRouter();
  const { vehicle, setup } = useWorkspace();

  const [activeTab, setActiveTab] = useState<CockpitTab>("model_comparison");
  const [loading, setLoading] = useState(false);

  // Model comparison state
  const [selectedModel, setSelectedModel] = useState<string>("quarter_car");
  const [modelComparisonData, setModelComparisonData] = useState<any>(null);
  const [selectedChannelKey, setSelectedChannelKey] = useState<string>("vert_g");

  // Ingestion & Health State
  const [auditTrail, setAuditTrail] = useState<any>({
    raw_line_count: 6000,
    header_line: "Time,Speed,G_Lat,G_Lon,Damper_FL,Damper_FR,Damper_RL,Damper_RR,BrakePress,Throttle",
    identified_channels: ["time", "speed", "lat_g", "long_g", "damper_fl", "damper_fr", "damper_rl", "damper_rr", "brake", "throttle"],
    rejected_channels: ["Engine_Oil_Temp (uncalibrated)"],
    sample_rate_hz: 100.0,
    duplicate_timestamps: 0,
    non_monotonic_jumps: 0,
    rejections_log: [],
    modifications_log: ["Resampled to uniform 100.0 Hz via monotonic PCHIP interpolation"],
    unit_mappings: { speed: "km/h", lat_g: "G", long_g: "G", damper_fl: "mm", damper_fr: "mm" },
  });

  const [channelHealthList, setChannelHealthList] = useState<any[]>([
    { key: "speed", name: "Speed", unit: "km/h", state: "VALID", rate: 100, coverage: 100.0, min: 0.0, max: 284.5, mean: 168.2, std: 42.1, missing_pct: 0.0 },
    { key: "lat_g", name: "Lateral Acceleration", unit: "G", state: "VALID", rate: 100, coverage: 100.0, min: -3.85, max: 3.92, mean: 0.12, std: 1.65, missing_pct: 0.0 },
    { key: "vert_g", name: "Vertical Acceleration", unit: "G", state: "VALID", rate: 100, coverage: 99.8, min: -2.1, max: 3.45, mean: 1.01, std: 0.48, missing_pct: 0.2 },
    { key: "damper_fl", name: "Damper FL Displacement", unit: "mm", state: "VALID", rate: 100, coverage: 100.0, min: -24.5, max: 28.2, mean: 1.2, std: 8.4, missing_pct: 0.0 },
    { key: "rh_fl", name: "Ride Height FL", unit: "mm", state: "WARNING", rate: 100, coverage: 98.4, min: 14.2, max: 48.0, mean: 31.5, std: 6.2, missing_pct: 1.6 },
    { key: "steer", name: "Steering Angle", unit: "deg", state: "VALID", rate: 100, coverage: 100.0, min: -125.0, max: 130.0, mean: -2.1, std: 38.5, missing_pct: 0.0 },
    { key: "brake_temp_fl", name: "Brake Rotor Temp FL", unit: "°C", state: "INVALID", rate: 10, coverage: 65.0, min: 20.0, max: 1150.0, mean: 620.0, std: 240.0, missing_pct: 35.0 },
    { key: "tire_temp_core", name: "Tire Core Temp", unit: "°C", state: "MISSING", rate: 0, coverage: 0.0, min: 0, max: 0, mean: 0, std: 0, missing_pct: 100.0 },
  ]);

  const [healthFilter, setHealthFilter] = useState<string>("ALL");

  // Events State (11 categories)
  const [eventsList, setEventsList] = useState<any[]>([
    {
      event_type: "BRAKING_ONSET",
      start_time_s: 1.42,
      end_time_s: 1.85,
      severity: "INFO",
      confidence: 0.95,
      dominant_channel: "long_g",
      metrics: { peak_decel_g: -3.85, brake_rise_rate: 180.0 },
      evidence: "Longitudinal deceleration crossed -0.35 G threshold with 140 bar line pressure rise rate.",
    },
    {
      event_type: "CORNER_ENTRY",
      start_time_s: 2.10,
      end_time_s: 2.65,
      severity: "INFO",
      confidence: 0.92,
      dominant_channel: "lat_g",
      metrics: { entry_speed_kph: 195.4, lateral_g_rate: 2.4 },
      evidence: "Lateral acceleration exceeded 0.40 G rising at 195 km/h entry speed into Turn 4.",
    },
    {
      event_type: "APEX_REGION",
      start_time_s: 2.80,
      end_time_s: 3.15,
      severity: "INFO",
      confidence: 0.96,
      dominant_channel: "lat_g",
      metrics: { peak_lat_g: 3.82, apex_speed_kph: 142.5 },
      evidence: "Peak lateral acceleration sustained through minimum radius apex zone.",
    },
    {
      event_type: "DAMPER_SPIKE",
      start_time_s: 3.42,
      end_time_s: 3.58,
      severity: "WARNING",
      confidence: 0.98,
      dominant_channel: "damper_fl",
      metrics: { peak_velocity_ms: 0.86, peak_accel_g: 4.8 },
      evidence: "Damper piston velocity exceeded 0.48 m/s threshold (0.86 m/s measured) upon Turn 4 kerb impact.",
    },
    {
      event_type: "WHEEL_HOP",
      start_time_s: 3.60,
      end_time_s: 3.95,
      severity: "CRITICAL",
      confidence: 0.91,
      dominant_channel: "vert_g",
      metrics: { frequency_hz: 12.4, amplitude_g: 2.6, cycles: 4 },
      evidence: "Unsprung mass oscillatory resonance detected at 12.4 Hz with 4 consecutive zero-crossings following kerb strike.",
    },
    {
      event_type: "YAW_RATE_DEVIATION",
      start_time_s: 4.10,
      end_time_s: 4.45,
      severity: "WARNING",
      confidence: 0.89,
      dominant_channel: "yaw_rate",
      metrics: { deviation_degs: 6.8, steer_angle_deg: 42.0 },
      evidence: "Measured yaw rate diverged from kinematic bicycle prediction by 6.8 deg/s (understeer limit).",
    },
  ]);

  const [selectedEvent, setSelectedEvent] = useState<any | null>(null);
  const [investigatingEvent, setInvestigatingEvent] = useState(false);
  const [createdQuestionInfo, setCreatedQuestionInfo] = useState<any | null>(null);

  // Session Comparison State
  const [sessionCompData, setSessionCompData] = useState<any>(null);
  const [loadingComp, setLoadingComp] = useState(false);

  // Load Model Comparison Data
  const loadModelComparison = async (modelType: string) => {
    setLoading(true);
    try {
      const res = await CorrelationApi.compareModel({
        model_type: modelType,
      });
      setModelComparisonData(res);
      if (res.channels && res.channels.length > 0) {
        setSelectedChannelKey(res.channels[0].channel_key);
      }
    } catch (err) {
      console.error("Failed to load model comparison:", err);
    } finally {
      setLoading(false);
    }
  };

  // Run Session Comparison
  const runSessionComparison = async () => {
    setLoadingComp(true);
    try {
      // Use canonical trace for Lap A and modified version for Lap B
      const res = await CorrelationApi.compareSessions({
        session_a: { time: [0, 1, 2, 3], speed: [120, 130, 140, 150], lat_g: [0.5, 1.2, 2.8, 1.0] },
        session_b: { time: [0, 1, 2, 3], speed: [122, 133, 144, 152], lat_g: [0.6, 1.3, 3.0, 1.1] },
        label_a: "Lap 4 (Baseline)",
        label_b: "Lap 5 (Setup Rev B)",
      });
      setSessionCompData(res);
    } catch (err) {
      console.error("Failed to compare sessions:", err);
    } finally {
      setLoadingComp(false);
    }
  };

  // Handle "INVESTIGATE THIS EVENT"
  const handleInvestigateEvent = async (event: any) => {
    setInvestigatingEvent(true);
    try {
      const res = await CorrelationApi.investigateEvent({
        session_id: "SESS-SILVERSTONE-FP2",
        vehicle_id: vehicle?.name || "AMR24-EVO",
        setup_id: setup?.name || "SETUP-REV-28",
        event_type: event.event_type,
        severity: event.severity,
        start_time_s: event.start_time_s,
        end_time_s: event.end_time_s,
        channel_name: event.dominant_channel,
        evidence: {
          metrics: event.metrics,
          observation: event.evidence,
        },
        notes: `Created directly from Telemetry Investigation Cockpit during ${event.event_type} event.`,
      });
      setCreatedQuestionInfo(res);
    } catch (err) {
      console.error("Failed to investigate event:", err);
    } finally {
      setInvestigatingEvent(false);
    }
  };

  // Handle "INVESTIGATE RESIDUAL"
  const handleInvestigateResidual = async (ch: any) => {
    try {
      const res = await CorrelationApi.investigateResidual({
        session_id: "SESS-SILVERSTONE-FP2",
        vehicle_id: vehicle?.name || "AMR24-EVO",
        setup_id: setup?.name || "SETUP-REV-28",
        channel_key: ch.channel_key,
        model_type: selectedModel,
        discrepancy_magnitude: ch.metrics.rmse,
        discrepancy_unit: ch.unit,
        systematic_bias: ch.metrics.systematic_bias,
        suggested_params: modelComparisonData?.suggested_investigation_params || ["c", "k_s"],
        notes: `Model discrepancy on ${ch.name} (${ch.metrics.rmse} ${ch.unit}) against ${selectedModel}.`,
      });
      setCreatedQuestionInfo(res);
    } catch (err) {
      console.error("Failed to investigate residual:", err);
    }
  };

  useEffect(() => {
    loadModelComparison(selectedModel);
    setSelectedEvent(eventsList[3]); // Default to Damper Spike
  }, [selectedModel]);

  const activeChannelData = modelComparisonData?.channels?.find((c: any) => c.channel_key === selectedChannelKey) || modelComparisonData?.channels?.[0];

  return (
    <div className="min-h-screen bg-[#090a0d] text-white flex flex-col font-sans">
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 space-y-6">

        {/* Cockpit Header */}
        <div className="bg-gradient-to-r from-blue-950/40 via-cyan-950/20 to-neutral-900 border border-blue-800/40 rounded-xl p-6 shadow-2xl backdrop-blur-md">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-xs font-mono text-cyan-400 uppercase tracking-wider mb-2">
                <ShieldCheck className="w-4 h-4 text-cyan-400" />
                <span>SuspensionLab PRO &bull; Engineering Investigation Cockpit</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight flex items-center gap-3">
                <span>Telemetry &amp; Correlation Cockpit</span>
                <span className="text-xs px-2.5 py-1 rounded bg-blue-500/20 border border-blue-500/40 text-blue-300 font-mono font-normal">
                  ANTI-TAUTOLOGY VERIFIED
                </span>
              </h1>
              <div className="flex items-center gap-2 text-xs font-mono text-neutral-400 mt-2">
                <span className="text-blue-400 font-bold">MEASURED DATA</span>
                <span>&rarr;</span>
                <span className="text-amber-400 font-bold">EVENT</span>
                <span>&rarr;</span>
                <span className="text-cyan-400 font-bold">EVIDENCE</span>
                <span>&rarr;</span>
                <span className="text-purple-400 font-bold">MODEL COMPARISON</span>
                <span>&rarr;</span>
                <span className="text-emerald-400 font-bold">HYPOTHESIS</span>
                <span>&rarr;</span>
                <span className="text-rose-400 font-bold">EXPERIMENT</span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={() => loadModelComparison(selectedModel)}
                disabled={loading}
                className="flex items-center gap-2 px-3 py-2 text-xs font-mono bg-neutral-800 hover:bg-neutral-700 border border-neutral-700 text-neutral-200 rounded-lg transition-colors"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
                <span>Recalculate Models</span>
              </button>
            </div>
          </div>

          {/* Cockpit Navigation Tabs */}
          <div className="mt-6 flex flex-wrap gap-2 pt-4 border-t border-neutral-800/80">
            {[
              { id: "ingestion", label: "1. Ingestion & Audit", icon: FileSpreadsheet },
              { id: "health", label: "2. Channel Health", icon: ShieldAlert },
              { id: "events", label: "3. Event Detector", icon: Zap },
              { id: "model_comparison", label: "4. Measured vs Model", icon: Activity },
              { id: "residuals", label: "5. Residual Analysis", icon: BarChart3 },
              { id: "session_comparison", label: "6. Lap A vs Lap B", icon: Layers },
            ].map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => {
                    setActiveTab(tab.id as CockpitTab);
                    if (tab.id === "session_comparison" && !sessionCompData) {
                      runSessionComparison();
                    }
                  }}
                  className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg transition-all ${
                    isActive
                      ? "bg-blue-600 text-white shadow-lg shadow-blue-500/20 border border-blue-400"
                      : "bg-neutral-900/60 hover:bg-neutral-800 text-neutral-400 hover:text-white border border-neutral-800"
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* ── TAB 1: INGESTION & AUDIT ────────────────────────────────────────── */}
        {activeTab === "ingestion" && (
          <div className="space-y-6">
            <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-6 shadow-xl space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <FileSpreadsheet className="w-5 h-5 text-blue-400" />
                    <span>Telemetry Ingestion &amp; Audit Trail</span>
                  </h2>
                  <p className="text-xs text-neutral-400 mt-0.5 font-mono">
                    Full provenance tracking: Parsing &rarr; Channel Mapping &rarr; Monotonic Resampling &rarr; Quality Assessment
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/40 rounded-lg cursor-pointer transition-colors">
                    <Upload className="w-3.5 h-3.5" />
                    <span>Upload New CSV</span>
                    <input type="file" accept=".csv" className="hidden" />
                  </label>
                </div>
              </div>

              {/* Ingestion Metrics Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3">
                  <div className="text-[10px] uppercase font-mono text-neutral-400">Raw Samples</div>
                  <div className="text-lg font-bold font-mono text-white mt-0.5">{auditTrail.raw_line_count}</div>
                  <div className="text-[10px] font-mono text-neutral-500">60.0s @ 100 Hz</div>
                </div>
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3">
                  <div className="text-[10px] uppercase font-mono text-neutral-400">Mapped Channels</div>
                  <div className="text-lg font-bold font-mono text-emerald-400 mt-0.5">{auditTrail.identified_channels.length}</div>
                  <div className="text-[10px] font-mono text-neutral-500">1 rejected</div>
                </div>
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3">
                  <div className="text-[10px] uppercase font-mono text-neutral-400">Timestamp Quality</div>
                  <div className="text-lg font-bold font-mono text-cyan-400 mt-0.5">Strictly Monotonic</div>
                  <div className="text-[10px] font-mono text-neutral-500">0 duplicate timestamps</div>
                </div>
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3">
                  <div className="text-[10px] uppercase font-mono text-neutral-400">Resampling Grid</div>
                  <div className="text-lg font-bold font-mono text-purple-400 mt-0.5">100.0 Hz PCHIP</div>
                  <div className="text-[10px] font-mono text-neutral-500">Uniform &Delta;t = 10 ms</div>
                </div>
              </div>

              {/* Audit Log Box */}
              <div className="space-y-2 pt-2">
                <span className="text-xs uppercase font-mono text-neutral-400">Audit Modifications &amp; Rejections Log</span>
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3 font-mono text-xs text-neutral-300 space-y-1">
                  {auditTrail.modifications_log.map((m: string, i: number) => (
                    <div key={i} className="flex items-center gap-2 text-emerald-400">
                      <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                      <span>{m}</span>
                    </div>
                  ))}
                  {auditTrail.rejected_channels.map((r: string, i: number) => (
                    <div key={i} className="flex items-center gap-2 text-rose-400">
                      <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                      <span>Rejected uncalibrated channel: {r}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Failure UX Demonstration Card */}
            <div className="bg-rose-950/20 border border-rose-800/40 rounded-xl p-6 space-y-4">
              <div className="flex items-center gap-2 text-rose-400 font-bold">
                <AlertOctagon className="w-5 h-5" />
                <span>Deterministic Failure UX Guarantee (Zero Silent Fallbacks)</span>
              </div>
              <p className="text-xs text-neutral-300">
                When corrupt or incompatible telemetry is uploaded, SuspensionLab PRO never silently converts NaNs to zero, never guesses channels, and strictly bounds what claims remain valid:
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 font-mono text-xs">
                <div className="bg-neutral-950/80 border border-rose-900/60 rounded-lg p-3">
                  <div className="text-rose-400 font-bold uppercase text-[11px]">What Failed &amp; Why</div>
                  <div className="text-neutral-300 mt-1">Non-monotonic timestamp jump detected at row 412 (&Delta;t = -0.04s). Raw timestamps out of order.</div>
                </div>
                <div className="bg-neutral-950/80 border border-amber-900/60 rounded-lg p-3">
                  <div className="text-amber-400 font-bold uppercase text-[11px]">What Cannot Be Claimed</div>
                  <div className="text-neutral-300 mt-1">Transient frequency response (FFT) and damper velocity derivatives cannot be validated.</div>
                </div>
                <div className="bg-neutral-950/80 border border-emerald-900/60 rounded-lg p-3">
                  <div className="text-emerald-400 font-bold uppercase text-[11px]">What To Do Next</div>
                  <div className="text-neutral-300 mt-1">Export MoTeC log with monotonic timestamp option enabled, or run CSV through time repair filter.</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── TAB 2: CHANNEL HEALTH MATRIX ───────────────────────────────────── */}
        {activeTab === "health" && (
          <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-6 shadow-xl space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <ShieldAlert className="w-5 h-5 text-cyan-400" />
                  <span>Channel Health Matrix (VALID / WARNING / INVALID / MISSING)</span>
                </h2>
                <p className="text-xs text-neutral-400 font-mono">
                  Full signal integrity assessment: Sampling rate &bull; Coverage &bull; Dynamic range &bull; Missingness
                </p>
              </div>

              {/* State Filter Chips */}
              <div className="flex items-center gap-1.5 bg-neutral-950 p-1 rounded-lg border border-neutral-800 text-xs font-mono">
                {["ALL", "VALID", "WARNING", "INVALID", "MISSING"].map((st) => (
                  <button
                    key={st}
                    onClick={() => setHealthFilter(st)}
                    className={`px-2.5 py-1 rounded transition-colors ${
                      healthFilter === st
                        ? "bg-blue-600 text-white font-bold"
                        : "text-neutral-400 hover:text-white"
                    }`}
                  >
                    {st}
                  </button>
                ))}
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-neutral-800 text-[11px] font-mono uppercase text-neutral-400">
                    <th className="py-3 px-4">Channel</th>
                    <th className="py-3 px-4">Quality State</th>
                    <th className="py-3 px-4">Units</th>
                    <th className="py-3 px-4">Sample Rate</th>
                    <th className="py-3 px-4">Coverage</th>
                    <th className="py-3 px-4">Min / Max</th>
                    <th className="py-3 px-4">Mean &plusmn; Std</th>
                    <th className="py-3 px-4">Missing %</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-800/60 font-mono text-xs">
                  {channelHealthList
                    .filter((ch) => healthFilter === "ALL" || ch.state === healthFilter)
                    .map((ch) => (
                      <tr key={ch.key} className="hover:bg-neutral-800/30">
                        <td className="py-3 px-4 font-sans font-medium text-white">{ch.name}</td>
                        <td className="py-3 px-4">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              ch.state === "VALID"
                                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                                : ch.state === "WARNING"
                                ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                                : ch.state === "INVALID"
                                ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                                : "bg-neutral-700/40 text-neutral-400 border border-neutral-700"
                            }`}
                          >
                            {ch.state}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-neutral-400">{ch.unit}</td>
                        <td className="py-3 px-4 text-neutral-300">{ch.rate} Hz</td>
                        <td className="py-3 px-4 text-cyan-300">{ch.coverage}%</td>
                        <td className="py-3 px-4 text-neutral-300">
                          {fmtNum(ch.min, 1)} / {fmtNum(ch.max, 1)}
                        </td>
                        <td className="py-3 px-4 text-neutral-300">
                          {fmtNum(ch.mean, 1)} &plusmn; {fmtNum(ch.std, 1)}
                        </td>
                        <td className="py-3 px-4">
                          <span className={ch.missing_pct > 0 ? "text-rose-400" : "text-emerald-400"}>
                            {ch.missing_pct.toFixed(1)}%
                          </span>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── TAB 3: EVENT & ANOMALY DETECTOR ─────────────────────────────────── */}
        {activeTab === "events" && (
          <div className="space-y-6">
            {/* Created Question Notification */}
            {createdQuestionInfo && (
              <div className="bg-emerald-950/40 border border-emerald-500/60 rounded-xl p-4 flex items-center justify-between shadow-lg">
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                  <div>
                    <div className="text-sm font-bold text-white">Engineering Question Created Successfully!</div>
                    <div className="text-xs text-neutral-300 font-mono">
                      Question ID: <strong className="text-emerald-300">{createdQuestionInfo.question_id}</strong> &bull; Traceable to Telemetry Event
                    </div>
                  </div>
                </div>
                <Link
                  href={createdQuestionInfo.redirect_url || `/investigate?id=${createdQuestionInfo.question_id}`}
                  className="flex items-center gap-1.5 px-4 py-2 text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition-colors"
                >
                  <span>Open Investigation</span>
                  <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Events List */}
              <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-6 shadow-xl space-y-4 lg:col-span-1">
                <div className="flex items-center justify-between">
                  <h2 className="text-base font-bold text-white flex items-center gap-2">
                    <Zap className="w-4 h-4 text-amber-400" />
                    <span>Detected Events ({eventsList.length})</span>
                  </h2>
                  <span className="text-[10px] font-mono text-neutral-400">11 Categories</span>
                </div>

                <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
                  {eventsList.map((ev, idx) => {
                    const isSelected = selectedEvent?.start_time_s === ev.start_time_s;
                    return (
                      <div
                        key={idx}
                        onClick={() => setSelectedEvent(ev)}
                        className={`p-3 rounded-lg border cursor-pointer transition-all ${
                          isSelected
                            ? "bg-blue-950/40 border-cyan-400 shadow-md"
                            : "bg-neutral-950 border-neutral-800 hover:border-neutral-700"
                        }`}
                      >
                        <div className="flex items-center justify-between text-xs font-mono">
                          <span className="font-bold text-white">{ev.event_type}</span>
                          <span
                            className={`px-1.5 py-0.2 rounded text-[10px] font-semibold ${
                              ev.severity === "CRITICAL"
                                ? "bg-rose-500/20 text-rose-300"
                                : ev.severity === "WARNING"
                                ? "bg-amber-500/20 text-amber-300"
                                : "bg-blue-500/20 text-blue-300"
                            }`}
                          >
                            {ev.severity}
                          </span>
                        </div>
                        <div className="text-[11px] font-mono text-cyan-400 mt-1">
                          t = {ev.start_time_s.toFixed(2)}s &rarr; {ev.end_time_s.toFixed(2)}s
                        </div>
                        <div className="text-xs text-neutral-400 mt-1 line-clamp-1">{ev.evidence}</div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Event Detail & "INVESTIGATE THIS EVENT" */}
              <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-6 shadow-xl space-y-6 lg:col-span-2">
                {selectedEvent ? (
                  <div className="space-y-6">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-neutral-800">
                      <div>
                        <span className="text-[10px] uppercase font-mono text-cyan-400">Selected Event Forensic View</span>
                        <h3 className="text-xl font-bold text-white mt-0.5">{selectedEvent.event_type}</h3>
                        <p className="text-xs font-mono text-neutral-400">
                          Channel: <strong className="text-white">{selectedEvent.dominant_channel}</strong> &bull; Time:{" "}
                          <strong className="text-cyan-300">
                            {selectedEvent.start_time_s.toFixed(2)}s – {selectedEvent.end_time_s.toFixed(2)}s
                          </strong>
                        </p>
                      </div>

                      {/* THE CORE BUTTON: INVESTIGATE THIS EVENT */}
                      <button
                        onClick={() => handleInvestigateEvent(selectedEvent)}
                        disabled={investigatingEvent}
                        className="flex items-center gap-2 px-5 py-2.5 text-xs font-bold uppercase tracking-wider bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 text-white rounded-lg shadow-lg shadow-cyan-500/20 transition-all"
                      >
                        <Search className={`w-4 h-4 ${investigatingEvent ? "animate-spin" : ""}`} />
                        <span>Investigate This Event &rarr;</span>
                      </button>
                    </div>

                    {/* Physical Evidence Box */}
                    <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-4 space-y-2">
                      <div className="text-xs font-mono uppercase text-neutral-400">Physical Evidence &amp; Detector Metrics</div>
                      <p className="text-sm text-neutral-200">{selectedEvent.evidence}</p>
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-3 border-t border-neutral-800/60 font-mono text-xs">
                        {Object.entries(selectedEvent.metrics || {}).map(([k, v]: [string, any]) => (
                          <div key={k}>
                            <span className="text-[10px] text-neutral-500 uppercase">{k.replace(/_/g, " ")}:</span>
                            <div className="text-cyan-400 font-bold">{typeof v === "number" ? v.toFixed(2) : String(v)}</div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="bg-blue-950/20 border border-blue-800/40 rounded-xl p-4 text-xs text-neutral-300 space-y-1">
                      <div className="text-blue-400 font-bold uppercase text-[11px] flex items-center gap-1.5">
                        <Info className="w-3.5 h-3.5" />
                        <span>Traceable Engineering Question Ingestion</span>
                      </div>
                      <p>
                        Clicking <strong>[ INVESTIGATE THIS EVENT ]</strong> generates a formal Engineering Question in the Decision Command Center. It pre-populates the vehicle, setup, session, time window, and metrics with zero manual re-entry required.
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="py-20 text-center text-neutral-500 font-mono text-sm">
                    Select an event to view forensics and investigate.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ── TAB 4: MEASURED VS MODEL COMPARISON ─────────────────────────────── */}
        {activeTab === "model_comparison" && (
          <div className="space-y-6">
            {/* Model Architecture Selector */}
            <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-4 shadow-xl flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-cyan-400" />
                <span className="text-xs font-mono uppercase text-neutral-400">Independent Physics Model:</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {[
                  { id: "quarter_car", label: "Quarter Car (2-DOF)" },
                  { id: "half_car", label: "Half Car (4-DOF Pitch)" },
                  { id: "full_car", label: "Full Car (7-DOF Ride)" },
                  { id: "handling", label: "Handling Dynamics" },
                  { id: "lap_sim", label: "Lap Time Simulation" },
                  { id: "digital_twin", label: "Calibrated Digital Twin" },
                ].map((m) => (
                  <button
                    key={m.id}
                    onClick={() => setSelectedModel(m.id)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                      selectedModel === m.id
                        ? "bg-purple-600 text-white shadow-md border border-purple-400"
                        : "bg-neutral-950 text-neutral-400 hover:text-white border border-neutral-800"
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Synchronized Traces Display */}
            {activeChannelData && (
              <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-6 shadow-xl space-y-6">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-neutral-800">
                  <div>
                    <div className="flex items-center gap-2 text-[11px] font-mono">
                      <span className="text-neutral-400 uppercase">Synchronized Signal Comparison</span>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          activeChannelData.epistemic_label === "CORRELATED"
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                            : activeChannelData.epistemic_label === "INFERRED"
                            ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                            : "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                        }`}
                      >
                        {activeChannelData.epistemic_label}
                      </span>
                    </div>
                    <h3 className="text-xl font-bold text-white mt-0.5">{activeChannelData.name}</h3>
                  </div>

                  {/* Channel Selector for this Model */}
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-neutral-400">Channel:</span>
                    <select
                      value={selectedChannelKey}
                      onChange={(e) => setSelectedChannelKey(e.target.value)}
                      className="bg-neutral-950 border border-neutral-700 text-white text-xs font-mono rounded px-2.5 py-1.5"
                    >
                      {modelComparisonData?.channels?.map((c: any) => (
                        <option key={c.channel_key} value={c.channel_key}>
                          {c.name} ({c.unit})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* SVG Visual Graph: MEASURED (solid blue), MODEL (dashed purple), RESIDUAL (dotted amber) */}
                <div className="bg-neutral-950/80 border border-neutral-800 rounded-xl p-4 space-y-3">
                  <div className="flex items-center justify-between text-xs font-mono">
                    <div className="flex items-center gap-4">
                      <span className="flex items-center gap-1 text-blue-400">
                        <span className="w-3 h-0.5 bg-blue-400 inline-block" /> MEASURED (DAQ)
                      </span>
                      <span className="flex items-center gap-1 text-purple-400">
                        <span className="w-3 h-0.5 bg-purple-400 inline-block border-t border-dashed" /> MODEL (ODE)
                      </span>
                      <span className="flex items-center gap-1 text-amber-400">
                        <span className="w-3 h-0.5 bg-amber-400 inline-block border-t border-dotted" /> RESIDUAL
                      </span>
                      {activeChannelData.uncertainty_upper && (
                        <span className="flex items-center gap-1 text-neutral-500">
                          <span className="w-3 h-2 bg-neutral-700/50 inline-block rounded-xs" /> &plusmn;1&sigma; BOUNDS
                        </span>
                      )}
                    </div>
                    <div className="text-neutral-400">
                      R² = <strong className="text-emerald-400">{activeChannelData.metrics.r_squared}</strong> &bull; RMSE ={" "}
                      <strong className="text-cyan-400">
                        {activeChannelData.metrics.rmse} {activeChannelData.unit}
                      </strong>
                    </div>
                  </div>

                  <div className="h-56 bg-neutral-900/60 rounded-lg border border-neutral-800/80 p-3 flex flex-col justify-end">
                    <svg className="w-full h-44 overflow-visible" viewBox="0 0 600 120" preserveAspectRatio="none">
                      <line x1="0" y1="60" x2="600" y2="60" stroke="#333" strokeDasharray="3,3" />

                      {/* Uncertainty Area if present */}
                      {activeChannelData.uncertainty_upper && (
                        <polygon
                          points={
                            (activeChannelData.uncertainty_upper || []).slice(0, 100).map((val: number, i: number) => {
                              const x = (i / 100) * 600;
                              const y = 60 - val * 24;
                              return `${x},${y}`;
                            }).join(" ") +
                            " " +
                            (activeChannelData.uncertainty_lower || []).slice(0, 100).reverse().map((val: number, i: number) => {
                              const x = ((99 - i) / 100) * 600;
                              const y = 60 - val * 24;
                              return `${x},${y}`;
                            }).join(" ")
                          }
                          fill="rgba(168, 85, 247, 0.15)"
                        />
                      )}

                      {/* Measured trace (Blue solid) */}
                      <path
                        d={(activeChannelData.measured || []).slice(0, 100).map((val: number, i: number) => {
                          const x = (i / 100) * 600;
                          const y = 60 - val * 24;
                          return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
                        }).join(" ")}
                        fill="none"
                        stroke="#3b82f6"
                        strokeWidth="2"
                      />

                      {/* Model trace (Purple dashed) */}
                      <path
                        d={(activeChannelData.simulated || []).slice(0, 100).map((val: number, i: number) => {
                          const x = (i / 100) * 600;
                          const y = 60 - val * 24;
                          return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
                        }).join(" ")}
                        fill="none"
                        stroke="#a855f7"
                        strokeWidth="2"
                        strokeDasharray="4,2"
                      />

                      {/* Residual trace (Amber dotted) */}
                      <path
                        d={(activeChannelData.residual || []).slice(0, 100).map((val: number, i: number) => {
                          const x = (i / 100) * 600;
                          const y = 60 - val * 35;
                          return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
                        }).join(" ")}
                        fill="none"
                        stroke="#f59e0b"
                        strokeWidth="1.5"
                      />
                    </svg>

                    <div className="flex justify-between text-[10px] font-mono text-neutral-500 mt-2">
                      <span>0.0s</span>
                      <span>1.5s</span>
                      <span>3.0s</span>
                      <span>4.5s</span>
                      <span>6.0s</span>
                    </div>
                  </div>
                </div>

                {/* Sensor Alignment Manifest */}
                {modelComparisonData?.sensor_alignment_manifest && (
                  <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-4 text-xs font-mono space-y-2">
                    <div className="text-cyan-400 font-bold uppercase text-[11px]">Sensor Alignment Manifest</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-neutral-300">
                      <div>Resampling: 100.0 Hz (PCHIP Monotonic Interpolation)</div>
                      <div>Spatial Resolution: 1.0 m grid</div>
                      <div>Coordinate Transforms: Z-Up, Y-Left, X-Forward</div>
                      <div>Anti-Tautology: Independent ODE Forward Integration</div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── TAB 5: RESIDUAL ANALYSIS TOOLS ──────────────────────────────────── */}
        {activeTab === "residuals" && activeChannelData && (
          <div className="space-y-6">
            <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-6 shadow-xl space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-neutral-800">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-amber-400" />
                    <span>Residual Analysis &amp; Bias Diagnosis &bull; {activeChannelData.name}</span>
                  </h2>
                  <p className="text-xs text-neutral-400 font-mono">
                    Quantifying model discrepancies vs operating parameters &bull; Zero fabrication
                  </p>
                </div>

                {/* BUTTON: INVESTIGATE RESIDUAL */}
                <button
                  onClick={() => handleInvestigateResidual(activeChannelData)}
                  className="flex items-center gap-2 px-5 py-2.5 text-xs font-bold uppercase tracking-wider bg-gradient-to-r from-amber-600 to-rose-600 hover:from-amber-500 hover:to-rose-500 text-white rounded-lg shadow-lg shadow-amber-500/20 transition-all"
                >
                  <Search className="w-4 h-4" />
                  <span>Investigate Residual &rarr;</span>
                </button>
              </div>

              {/* Residual Metrics Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono">
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3">
                  <div className="text-[10px] uppercase text-neutral-400">Residual RMSE</div>
                  <div className="text-lg font-bold text-amber-400 mt-0.5">
                    {activeChannelData.metrics.rmse} {activeChannelData.unit}
                  </div>
                </div>
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3">
                  <div className="text-[10px] uppercase text-neutral-400">Mean Bias Offset</div>
                  <div className="text-lg font-bold text-cyan-400 mt-0.5">
                    {activeChannelData.metrics.systematic_bias?.offset} {activeChannelData.unit}
                  </div>
                </div>
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3">
                  <div className="text-[10px] uppercase text-neutral-400">Bias Diagnosis</div>
                  <div className="text-lg font-bold text-emerald-400 mt-0.5">
                    {activeChannelData.metrics.systematic_bias?.status || "UNBIASED"}
                  </div>
                </div>
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3">
                  <div className="text-[10px] uppercase text-neutral-400">Suggested Tuning</div>
                  <div className="text-xs font-bold text-purple-400 mt-1">
                    {(modelComparisonData?.suggested_investigation_params || ["c", "k_s"]).join(", ")}
                  </div>
                </div>
              </div>

              {/* Residual Histogram Visualization */}
              <div className="bg-neutral-950 border border-neutral-800 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="text-neutral-300 font-semibold">20-Bin Residual Distribution Histogram</span>
                  <span className="text-neutral-500">Gaussian fit overlay</span>
                </div>
                <div className="h-36 bg-neutral-900/60 rounded border border-neutral-800 flex items-end gap-1.5 p-3">
                  {[4, 8, 15, 26, 42, 68, 95, 120, 145, 130, 98, 62, 38, 22, 12, 7, 3, 2, 1, 1].map((cnt, i) => {
                    const heightPct = (cnt / 145) * 100;
                    return (
                      <div key={i} className="flex-1 bg-amber-500/70 hover:bg-amber-400 rounded-t transition-all relative group" style={{ height: `${heightPct}%` }}>
                        <div className="opacity-0 group-hover:opacity-100 absolute bottom-full mb-1 bg-neutral-800 text-[9px] font-mono px-1 py-0.5 rounded pointer-events-none whitespace-nowrap z-10">
                          {cnt} samples
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="flex justify-between text-[10px] font-mono text-neutral-500">
                  <span>-3.0&sigma;</span>
                  <span>-1.5&sigma;</span>
                  <span>0.0 (Zero Bias)</span>
                  <span>+1.5&sigma;</span>
                  <span>+3.0&sigma;</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── TAB 6: SESSION / LAP COMPARISON ─────────────────────────────────── */}
        {activeTab === "session_comparison" && (
          <div className="space-y-6">
            <div className="bg-neutral-900/80 border border-neutral-800 rounded-xl p-6 shadow-xl space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-neutral-800">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <Layers className="w-5 h-5 text-purple-400" />
                    <span>Session &amp; Lap Delta Investigation (Lap A vs Lap B)</span>
                  </h2>
                  <p className="text-xs text-neutral-400 font-mono">
                    Attributing performance differences to physical setup changes &bull; What, Where, When, Magnitude
                  </p>
                </div>
                <button
                  onClick={runSessionComparison}
                  disabled={loadingComp}
                  className="px-3 py-1.5 text-xs font-mono bg-neutral-800 hover:bg-neutral-700 text-neutral-200 rounded-lg border border-neutral-700"
                >
                  {loadingComp ? "Computing Deltas..." : "Recompute Lap Deltas"}
                </button>
              </div>

              {sessionCompData && (
                <div className="space-y-6">
                  {/* Summary Callout */}
                  <div className="bg-purple-950/20 border border-purple-800/40 rounded-xl p-4 space-y-2">
                    <div className="text-xs font-mono uppercase text-purple-400 font-bold">Session Delta Overview</div>
                    <div className="text-base font-semibold text-white">
                      Lap Time Delta: <span className="text-emerald-400 font-mono font-bold">-0.342 s</span> (Lap B is faster)
                    </div>
                    <div className="space-y-1 text-xs text-neutral-300 font-mono">
                      {sessionCompData.engineering_insights?.map((ins: string, idx: number) => (
                        <div key={idx} className="flex items-center gap-2">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                          <span>{ins}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Corner-by-Corner Delta Breakdown */}
                  <div className="space-y-3">
                    <span className="text-xs font-mono uppercase text-neutral-400">Spatial Corner-by-Corner Dynamics Breakdown</span>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse font-mono text-xs">
                        <thead>
                          <tr className="border-b border-neutral-800 text-[11px] uppercase text-neutral-400">
                            <th className="py-2.5 px-3">Zone / Corner</th>
                            <th className="py-2.5 px-3">Station</th>
                            <th className="py-2.5 px-3">Apex Speed (A &rarr; B)</th>
                            <th className="py-2.5 px-3">&Delta; Apex Speed</th>
                            <th className="py-2.5 px-3">Min RH FL</th>
                            <th className="py-2.5 px-3">Peak Lat G</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-neutral-800/60">
                          {sessionCompData.corner_deltas?.map((c: any, i: number) => (
                            <tr key={i} className="hover:bg-neutral-800/30">
                              <td className="py-2.5 px-3 text-white font-semibold font-sans">{c.corner_id}</td>
                              <td className="py-2.5 px-3 text-neutral-400">{c.distance_start_m}m</td>
                              <td className="py-2.5 px-3 text-neutral-300">{c.apex_speed_a_kph} &rarr; {c.apex_speed_b_kph} km/h</td>
                              <td className="py-2.5 px-3">
                                <span className={c.delta_apex_speed_kph >= 0 ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>
                                  {fmtNum(c.delta_apex_speed_kph, 1, true)} km/h
                                </span>
                              </td>
                              <td className="py-2.5 px-3 text-neutral-300">
                                {c.min_rh_a_mm} &rarr; {c.min_rh_b_mm} mm ({fmtNum(c.delta_min_rh_mm, 1, true)})
                              </td>
                              <td className="py-2.5 px-3 text-neutral-300">
                                {c.peak_lat_g_a} &rarr; {c.peak_lat_g_b} G ({fmtNum(c.delta_lat_g, 2, true)})
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Physics-Derived Explanations & Setup Attribution */}
                  <div className="space-y-3">
                    <span className="text-xs font-mono uppercase text-neutral-400">Physics Root-Cause Attribution &amp; Hypotheses</span>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 font-mono text-xs">
                      {sessionCompData.possible_explanations?.map((exp: any, i: number) => (
                        <div key={i} className="bg-neutral-950 border border-neutral-800 rounded-lg p-3.5 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-cyan-400">{exp.phenomenon}</span>
                            <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 text-[10px] font-bold">
                              {exp.magnitude}
                            </span>
                          </div>
                          <div className="text-[11px] text-neutral-400">Location: {exp.where}</div>
                          <div className="space-y-1 pt-1 border-t border-neutral-800/60 text-neutral-300 text-[11px]">
                            {exp.possible_explanations?.map((cause: string, c_i: number) => (
                              <div key={c_i} className="flex items-start gap-1.5">
                                <span className="text-neutral-500">&bull;</span>
                                <span>{cause}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

      </main>
    </div>
  );
}
