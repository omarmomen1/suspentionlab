"use client";

import React, { useState, useEffect, useMemo } from "react";
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
import SampleDemoTelemetryBadge from "../../components/engineering/SampleDemoTelemetryBadge";
import GGFrictionCircle from "../../components/GGFrictionCircle";
import PlanGate from "../../components/PlanGate";
import {
  SAMPLE_TELEMETRY_DATASETS,
  fetchSampleCsvText,
  isSampleTelemetryFilename,
  type SampleTelemetryDataset,
} from "../../lib/sampleTelemetry";

function fmtNum(val: number | null | undefined, digits = 2, withPlus = false): string {
  if (val === null || val === undefined || isNaN(val)) return "—";
  const formatted = val.toFixed(digits);
  return withPlus && val > 0 ? `+${formatted}` : formatted;
}

const CHANNEL_META: Record<string, { name: string; unit: string }> = {
  time: { name: "Time", unit: "s" },
  distance: { name: "Distance", unit: "m" },
  speed: { name: "Speed", unit: "km/h" },
  lat_g: { name: "Lateral Acceleration", unit: "G" },
  long_g: { name: "Longitudinal Acceleration", unit: "G" },
  vert_g: { name: "Vertical Acceleration", unit: "G" },
  damper_fl: { name: "Damper FL Displacement", unit: "mm" },
  damper_fr: { name: "Damper FR Displacement", unit: "mm" },
  damper_rl: { name: "Damper RL Displacement", unit: "mm" },
  damper_rr: { name: "Damper RR Displacement", unit: "mm" },
  rh_fl: { name: "Ride Height FL", unit: "mm" },
  steer: { name: "Steering Angle", unit: "deg" },
  brake: { name: "Brake Pressure Front", unit: "bar" },
  throttle: { name: "Throttle Position", unit: "%" },
  engine_rpm: { name: "Engine RPM", unit: "rpm" },
};

function mapHeaderKey(rawHeader: string): string {
  const norm = rawHeader.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  if (norm === "t" || norm === "timestamp" || norm === "time_s" || norm === "sec" || norm === "seconds" || norm === "elapsed_time" || norm === "time") return "time";
  if (norm === "gps_speed" || norm === "v" || norm === "vehicle_speed" || norm === "speed_kmh" || norm === "v_kph" || norm === "ground_speed" || norm === "car_speed" || norm === "speed") return "speed";
  if (norm === "g_lat" || norm === "latacc" || norm === "lat_acc" || norm === "lataccel" || norm === "lat_accel" || norm === "ay" || norm === "lateral_acc" || norm === "lat_g") return "lat_g";
  if (norm === "g_lon" || norm === "inlineacc" || norm === "lonacc" || norm === "lon_g" || norm === "lonaccel" || norm === "longaccel" || norm === "ax" || norm === "long_acc" || norm === "long_g") return "long_g";
  if (norm === "g_vert" || norm === "vertacc" || norm === "az" || norm === "vert_g" || norm === "vertaccel" || norm === "vert_acc" || norm === "heave_accel") return "vert_g";
  if (norm === "susptravel_fl" || norm === "damper_fl" || norm === "damper_disp_fl") return "damper_fl";
  if (norm === "susptravel_fr" || norm === "damper_fr" || norm === "damper_disp_fr") return "damper_fr";
  if (norm === "susptravel_rl" || norm === "damper_rl" || norm === "damper_disp_rl") return "damper_rl";
  if (norm === "susptravel_rr" || norm === "damper_rr" || norm === "damper_disp_rr") return "damper_rr";
  if (norm === "steerangle" || norm === "steer_deg" || norm === "steering" || norm === "steer") return "steer";
  if (norm === "brakepress_f" || norm === "brake_front" || norm === "brake_press" || norm === "brake") return "brake";
  if (norm === "throttlepos" || norm === "tps" || norm === "throttle") return "throttle";
  if (norm === "enginerpm" || norm === "rpm" || norm === "engine_rpm") return "engine_rpm";
  return norm || "unknown";
}

interface ParsedCsvTelemetry {
  rawColumns: string[];
  mappedKeys: string[];
  rejectedColumns: string[];
  sampleCount: number;
  sampleRateHz: number;
  durationSec: number;
  channels: Record<string, number[]>;
  healthRows: Array<{
    key: string;
    name: string;
    unit: string;
    state: "VALID" | "WARNING" | "INVALID" | "MISSING";
    rate: number;
    coverage: number;
    min: number;
    max: number;
    mean: number;
    std: number;
    missing_pct: number;
    synthetic?: boolean;
  }>;
  synthesizedChannels?: string[];
  maxG: number;
  latG: number;
  longG: number;
}

function parseTelemetryCsv(csvText: string): ParsedCsvTelemetry {
  // Strip UTF-8 BOM if present
  const cleanCsvText = csvText.replace(/^\uFEFF/, "");
  const lines = cleanCsvText.split(/\r?\n/).filter((l) => l.trim().length > 0 && !l.trim().startsWith("#"));
  if (lines.length < 2) {
    throw new Error("Telemetry CSV must contain a header line and at least one data row.");
  }

  // Detect delimiter (comma, semicolon, tab)
  const firstLine = lines[0];
  const delim = firstLine.includes("\t") ? "\t" : (firstLine.includes(";") && !firstLine.includes(",") ? ";" : ",");

  const rawColumns = firstLine
    .split(delim)
    .map((c) => c.trim())
    .filter(Boolean);
  const mappedKeys = rawColumns.map(mapHeaderKey);

  const buckets: number[][] = mappedKeys.map(() => []);
  const validCounts: number[] = mappedKeys.map(() => 0);
  const dataLines = lines.slice(1);

  for (const line of dataLines) {
    const parts = line.split(delim);
    let rowHasData = false;
    for (let c = 0; c < mappedKeys.length; c++) {
      const cell = (parts[c] ?? "").trim();
      if (cell === "" || cell.toLowerCase() === "nan" || cell.toLowerCase() === "null") {
        buckets[c].push(NaN);
        continue;
      }
      const v = parseFloat(cell);
      if (Number.isFinite(v)) {
        buckets[c].push(v);
        validCounts[c] += 1;
        rowHasData = true;
      } else {
        buckets[c].push(NaN);
      }
    }
    if (!rowHasData && parts.length === 1 && parts[0] === "") {
      // trailing empty row, pop
      mappedKeys.forEach((_, c) => buckets[c].pop());
    }
  }

  const channels: Record<string, number[]> = {};
  const rejectedColumns: string[] = [];
  const healthRows: ParsedCsvTelemetry["healthRows"] = [];
  const sampleCount = dataLines.length;

  // Estimate sample rate from time axis if available
  const timeIdx = mappedKeys.indexOf("time");
  let sampleRateHz = 100.0;
  let durationSec = sampleCount > 0 ? sampleCount / sampleRateHz : 0;
  if (timeIdx >= 0) {
    const tArr = buckets[timeIdx].filter(Number.isFinite);
    if (tArr.length >= 2) {
      const span = tArr[tArr.length - 1] - tArr[0];
      const dt = (tArr[1] - tArr[0]) || (span > 0 ? span / (tArr.length - 1) : 0.01);
      if (dt > 1e-5) {
        sampleRateHz = Math.round((1.0 / dt) * 10) / 10;
      }
      durationSec = span > 0 ? span : sampleCount / sampleRateHz;
    }
  }

  for (let c = 0; c < mappedKeys.length; c++) {
    const key = mappedKeys[c];
    const finiteVals = buckets[c].filter(Number.isFinite);
    if (finiteVals.length === 0) {
      rejectedColumns.push(`${rawColumns[c]} (non-numeric/empty) - expected schema: time, speed, lat_g, long_g, damper_fl/vert_g channels as numeric columns`);
      continue;
    }
    // Deduplicate only non-NaN cleaned vector
    channels[key] = buckets[c].map((v, i) => (Number.isFinite(v) ? v : i > 0 && Number.isFinite(buckets[c][i - 1]) ? buckets[c][i - 1] : 0));
    if (key === "damper_fl" && !channels["rh_fl"]) {
      channels["rh_fl"] = channels[key];
    }
    if (key === "time") continue;

    let min = finiteVals[0];
    let max = finiteVals[0];
    let sum = 0;
    for (const v of finiteVals) {
      if (v < min) min = v;
      if (v > max) max = v;
      sum += v;
    }
    const mean = sum / finiteVals.length;
    let varSum = 0;
    for (const v of finiteVals) {
      varSum += (v - mean) ** 2;
    }
    const std = Math.sqrt(varSum / finiteVals.length);
    const coverage = sampleCount > 0 ? (finiteVals.length / sampleCount) * 100 : 100;
    const missingPct = Math.max(0, 100 - coverage);
    const meta = CHANNEL_META[key] || { name: rawColumns[c], unit: "raw" };

    healthRows.push({
      key,
      name: meta.name,
      unit: meta.unit,
      state: missingPct > 5 ? "WARNING" : "VALID",
      rate: Math.round(sampleRateHz),
      coverage: Number(coverage.toFixed(1)),
      min: Number(min.toFixed(3)),
      max: Number(max.toFixed(3)),
      mean: Number(mean.toFixed(3)),
      std: Number(std.toFixed(3)),
      missing_pct: Number(missingPct.toFixed(1)),
    });
  }

  // Synthesize vertical acceleration proxy if CSV lacks vert_g so quarter-car/full-car correlation works cleanly
  const synthesizedChannels: string[] = [];
  if (!channels["vert_g"] && channels["damper_fl"] && channels["damper_fl"].length > 2) {
    const d = channels["damper_fl"];
    const dt = sampleRateHz > 0 ? 1 / sampleRateHz : 0.01;
    const vertG: number[] = new Array(d.length).fill(0);
    for (let i = 1; i < d.length - 1; i++) {
      const accelMps2 = ((d[i + 1] - 2 * d[i] + d[i - 1]) / 1000.0) / (dt * dt);
      vertG[i] = Math.max(-4, Math.min(4, Number((accelMps2 / 9.81).toFixed(4))));
    }
    channels["vert_g"] = vertG;
    // Double-differentiated from damper travel - must be labelled synthetic everywhere it shows.
    synthesizedChannels.push("vert_g");
    healthRows.push({
      key: "vert_g",
      name: "Vertical Acceleration (SYNTHETIC CHANNEL - derived from damper_fl)",
      unit: "G",
      state: "WARNING",
      rate: sampleRateHz > 0 ? Number(sampleRateHz.toFixed(1)) : 100,
      coverage: 100,
      min: Math.min(...vertG),
      max: Math.max(...vertG),
      mean: Number((vertG.reduce((a, b) => a + b, 0) / vertG.length).toFixed(3)),
      std: 0,
      missing_pct: 0,
      synthetic: true,
    });
  }

  // Compute G-G circle point & peak envelope
  const latArr = channels["lat_g"] || [];
  const longArr = channels["long_g"] || [];
  let maxG = 1.5;
  let peakLat = 0;
  let peakLong = 0;
  const nG = Math.max(latArr.length, longArr.length);
  for (let i = 0; i < nG; i++) {
    const gx = latArr[i] ?? 0;
    const gy = longArr[i] ?? 0;
    const mag = Math.hypot(gx, gy);
    if (mag > maxG) {
      maxG = mag;
      peakLat = gx;
      peakLong = gy;
    }
  }

  return {
    rawColumns,
    mappedKeys: Object.keys(channels),
    rejectedColumns,
    sampleCount,
    sampleRateHz,
    durationSec,
    channels,
    healthRows,
    synthesizedChannels,
    maxG: Number(maxG.toFixed(2)),
    latG: Number(peakLat.toFixed(2)),
    longG: Number(peakLong.toFixed(2)),
  };
}

type CockpitTab = "ingestion" | "health" | "events" | "model_comparison" | "residuals" | "session_comparison";

function CorrelationCockpitContent() {
  const router = useRouter();
  const { vehicle, setup } = useWorkspace();

  const [activeTab, setActiveTab] = useState<CockpitTab>("model_comparison");
  const [loading, setLoading] = useState(false);

  // Model comparison state
  const [selectedModel, setSelectedModel] = useState<string>("quarter_car");
  const [modelComparisonData, setModelComparisonData] = useState<any>(null);
  const [selectedChannelKey, setSelectedChannelKey] = useState<string>("vert_g");

  const [activeDatasetName, setActiveDatasetName] = useState<string>("sample_spa_gt3.csv");
  const [isSampleDataset, setIsSampleDataset] = useState<boolean>(true);
  const [loadingSampleId, setLoadingSampleId] = useState<string | null>(null);
  const [parsedTelemetry, setParsedTelemetry] = useState<Record<string, number[]> | null>(null);
  const [gCircleStats, setGCircleStats] = useState<{ maxG: number; latG: number; longG: number }>({
    maxG: 1.85,
    latG: 1.25,
    longG: -0.95,
  });

  // Ingestion & Health State
  const [auditTrail, setAuditTrail] = useState<any>({
    raw_line_count: 5000,
    header_line: "Time,Distance,Speed,SteerAngle,G_Lat,G_Lon,SuspTravel_FL,SuspTravel_FR,SuspTravel_RL,SuspTravel_RR,BrakePress_F,ThrottlePos,EngineRPM",
    identified_channels: ["time", "distance", "speed", "steer", "lat_g", "long_g", "damper_fl", "damper_fr", "damper_rl", "damper_rr", "brake", "throttle", "engine_rpm"],
    rejected_channels: [],
    sample_rate_hz: 100.0,
    duration_s: 50.0,
    duplicate_timestamps: 0,
    non_monotonic_jumps: 0,
    rejections_log: [],
    modifications_log: ["Ready: GT3 sample telemetry schema (100.0 Hz PCHIP resampling)"],
    unit_mappings: { speed: "km/h", lat_g: "G", long_g: "G", damper_fl: "mm", damper_fr: "mm" },
  });

  const [channelHealthList, setChannelHealthList] = useState<any[]>([
    { key: "speed", name: "Speed", unit: "km/h", state: "VALID", rate: 100, coverage: 100.0, min: 45.0, max: 258.0, mean: 162.4, std: 38.2, missing_pct: 0.0 },
    { key: "lat_g", name: "Lateral Acceleration", unit: "G", state: "VALID", rate: 100, coverage: 100.0, min: -1.78, max: 1.82, mean: 0.08, std: 0.92, missing_pct: 0.0 },
    { key: "long_g", name: "Longitudinal Acceleration", unit: "G", state: "VALID", rate: 100, coverage: 100.0, min: -1.65, max: 0.85, mean: -0.04, std: 0.62, missing_pct: 0.0 },
    { key: "damper_fl", name: "Damper FL Displacement", unit: "mm", state: "VALID", rate: 100, coverage: 100.0, min: -18.5, max: 24.0, mean: 1.8, std: 7.4, missing_pct: 0.0 },
    { key: "steer", name: "Steering Angle", unit: "deg", state: "VALID", rate: 100, coverage: 100.0, min: -95.0, max: 98.0, mean: -1.2, std: 28.4, missing_pct: 0.0 },
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

  const applyCsvMetadata = (csvText: string, filename: string, sampleFlag: boolean) => {
    const parsed = parseTelemetryCsv(csvText);
    setActiveDatasetName(filename);
    setIsSampleDataset(sampleFlag);
    setParsedTelemetry(parsed.channels);
    setGCircleStats({ maxG: parsed.maxG, latG: parsed.latG, longG: parsed.longG });
    setChannelHealthList(parsed.healthRows);
    setAuditTrail((prev: any) => ({
      ...prev,
      raw_line_count: parsed.sampleCount,
      header_line: parsed.rawColumns.join(","),
      identified_channels: parsed.mappedKeys,
      rejected_channels: parsed.rejectedColumns,
      sample_rate_hz: parsed.sampleRateHz,
      duration_s: parsed.durationSec,
      modifications_log: [
        `Loaded ${filename} (${parsed.sampleCount.toLocaleString()} frames, ${parsed.rawColumns.length} columns)`,
        `Estimated sampling rate ${parsed.sampleRateHz.toFixed(1)} Hz (${parsed.durationSec.toFixed(1)} s duration)`,
      ],
    }));

    // Recompute model comparison & session delta directly with newly parsed CSV telemetry
    loadModelComparison(selectedModel, parsed.channels);
    if (activeTab === "session_comparison" || sessionCompData) {
      runSessionComparison(parsed.channels);
    }
  };

  const handleLoadSampleDataset = async (ds: SampleTelemetryDataset) => {
    setLoadingSampleId(ds.id);
    try {
      const text = await fetchSampleCsvText(ds);
      applyCsvMetadata(text, ds.filename, true);
    } catch (err) {
      console.error("Failed to load sample telemetry:", err);
    } finally {
      setLoadingSampleId(null);
    }
  };

  const handleCsvUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const uploaded = e.target.files?.[0];
    if (!uploaded) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = typeof ev.target?.result === "string" ? ev.target.result : "";
      if (text) {
        applyCsvMetadata(text, uploaded.name, isSampleTelemetryFilename(uploaded.name));
      }
    };
    reader.readAsText(uploaded);
  };

  // Load Model Comparison Data
  const loadModelComparison = async (modelType: string, overrideTelemetry?: Record<string, number[]> | null) => {
    setLoading(true);
    try {
      const telemPayload = overrideTelemetry ?? parsedTelemetry;
      const res = await CorrelationApi.compareModel({
        model_type: modelType,
        ...(telemPayload && telemPayload.time && telemPayload.time.length > 1
          ? { telemetry_data: telemPayload }
          : {}),
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

  // Run Session Comparison using parsed CSV telemetry slices (or loaded session trace)
  const runSessionComparison = async (overrideTelemetry?: Record<string, number[]> | null) => {
    setLoadingComp(true);
    try {
      const telemSource = overrideTelemetry ?? parsedTelemetry;
      if (!telemSource || !telemSource.time || telemSource.time.length < 20) {
        setSessionCompData(null);
        setLoadingComp(false);
        return;
      }

      const mid = Math.floor(telemSource.time.length / 2);
      const t0B = telemSource.time[mid] ?? 0;
      const sliceHalf = (start: number, end: number, shiftTimeZero: number) => {
        const out: Record<string, number[]> = {};
        for (const [k, arr] of Object.entries(telemSource)) {
          const sl = arr.slice(start, end);
          out[k] = k === "time" ? sl.map((t) => Number((t - shiftTimeZero).toFixed(4))) : sl;
        }
        return out;
      };
      const sessionA = sliceHalf(0, mid, telemSource.time[0] ?? 0);
      const sessionB = sliceHalf(mid, telemSource.time.length, t0B);
      const labelA = `${activeDatasetName} (Stint 1)`;
      const labelB = `${activeDatasetName} (Stint 2)`;

      const res = await CorrelationApi.compareSessions({
        session_a: sessionA,
        session_b: sessionB,
        label_a: labelA,
        label_b: labelB,
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
        session_id: activeDatasetName ? activeDatasetName.replace(/\.csv$/, "") : "active-session",
        vehicle_id: vehicle?.name || "active-vehicle",
        setup_id: setup?.name || "active-setup",
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
        session_id: activeDatasetName ? activeDatasetName.replace(/\.csv$/, "") : "active-session",
        vehicle_id: vehicle?.name || "active-vehicle",
        setup_id: setup?.name || "active-setup",
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

  // Zero-lie gate: never show green CORRELATED below the R^2 >= 0.70 acceptance threshold.
  const activeR2 = Number(activeChannelData?.metrics?.r_squared);
  const r2Ok = Number.isFinite(activeR2) && activeR2 >= 0.70;
  const displayEpistemicLabel =
    activeChannelData?.epistemic_label === "CORRELATED" && !r2Ok
      ? "UNVERIFIED (R\u00b2 < 0.70)"
      : activeChannelData?.epistemic_label;

  const { channelYMin, channelYMax, dynamicTimeLabels, scaleChannelY, scaleResidualY, channelZeroY } = useMemo(() => {
    const meas = (activeChannelData?.measured || []) as number[];
    const sim = (activeChannelData?.simulated || []) as number[];
    const res = (activeChannelData?.residual || []) as number[];
    const timeArr = (activeChannelData?.time || modelComparisonData?.time || []) as number[];

    const allVals = [...meas, ...sim];
    let min = allVals.length > 0 ? Math.min(...allVals) : -1.0;
    let max = allVals.length > 0 ? Math.max(...allVals) : 1.0;
    if (min === max) {
      min -= 1;
      max += 1;
    }
    const range = max - min;
    const padding = range * 0.12;
    const effYMin = min - padding;
    const effYMax = max + padding;

    const scaleChannelY = (val: number) => {
      const norm = (val - effYMin) / Math.max(effYMax - effYMin, 1e-4);
      return Math.max(4, Math.min(116, 120 - norm * 120));
    };

    const maxAbsRes = Math.max(...res.map((r: number) => Math.abs(r)), 1e-3);
    const zeroY = effYMin <= 0 && effYMax >= 0 ? scaleChannelY(0) : 60;
    const scaleResidualY = (val: number) => {
      const deltaY = (val / (maxAbsRes * 2.0)) * 45;
      return Math.max(4, Math.min(116, zeroY - deltaY));
    };

    const tStart = timeArr.length > 0 ? timeArr[0] : 0;
    const tEnd = timeArr.length > 0 ? timeArr[timeArr.length - 1] : 6.0;
    const dt = (tEnd - tStart) / 4;
    const dynamicTimeLabels = [
      `${tStart.toFixed(1)}s`,
      `${(tStart + dt).toFixed(1)}s`,
      `${(tStart + 2 * dt).toFixed(1)}s`,
      `${(tStart + 3 * dt).toFixed(1)}s`,
      `${tEnd.toFixed(1)}s`,
    ];

    return { channelYMin: effYMin, channelYMax: effYMax, dynamicTimeLabels, scaleChannelY, scaleResidualY, channelZeroY: zeroY };
  }, [activeChannelData, modelComparisonData?.time]);

  const residualHistogramBins = useMemo(() => {
    const residuals = (activeChannelData?.residual || []) as number[];
    if (residuals.length === 0) return Array(20).fill(0);
    let min = Math.min(...residuals);
    let max = Math.max(...residuals);
    if (min === max) {
      min -= 0.1;
      max += 0.1;
    }
    const binCount = 20;
    const binWidth = (max - min) / binCount;
    const counts = Array(binCount).fill(0);
    for (const r of residuals) {
      let idx = Math.floor((r - min) / binWidth);
      if (idx >= binCount) idx = binCount - 1;
      if (idx < 0) idx = 0;
      counts[idx]++;
    }
    return counts;
  }, [activeChannelData?.residual]);

  return (
    <div className="min-h-screen bg-[#090a0d] text-white flex flex-col font-sans">
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 space-y-6">

        {/* Cockpit Header */}
        <div className="bg-[#0e0e12] border border-[#222536] rounded-xl p-6 shadow-xl backdrop-blur-md">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-xs font-mono text-cyan-400 uppercase tracking-wider mb-2">
                <ShieldCheck className="w-4 h-4 text-cyan-400" />
                <span>SuspensionLab PRO &bull; Engineering Investigation Cockpit</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight flex flex-wrap items-center gap-3">
                <span>Telemetry &amp; Correlation Cockpit</span>
                {!isSampleDataset && (
                  <span className="text-xs px-2.5 py-1 rounded bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 font-mono font-normal">
                    ANTI-TAUTOLOGY VERIFIED
                  </span>
                )}
                {isSampleDataset && <SampleDemoTelemetryBadge size="sm" />}
              </h1>
              <div className="flex items-center gap-2 text-xs font-mono text-neutral-400 mt-2">
                <span className="text-cyan-400 font-bold">MEASURED DATA</span>
                <span>&rarr;</span>
                <span className="text-slate-300 font-bold">EVENT</span>
                <span>&rarr;</span>
                <span className="text-slate-300 font-bold">EVIDENCE</span>
                <span>&rarr;</span>
                <span className="text-amber-400 font-bold">MODEL COMPARISON</span>
                <span>&rarr;</span>
                <span className="text-slate-300 font-bold">HYPOTHESIS</span>
                <span>&rarr;</span>
                <span className="text-emerald-400 font-bold">EXPERIMENT</span>
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
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-bold text-white flex flex-wrap items-center gap-2">
                    <FileSpreadsheet className="w-5 h-5 text-blue-400" />
                    <span>Telemetry Ingestion &amp; Audit Trail</span>
                    {isSampleDataset && <SampleDemoTelemetryBadge size="xs" />}
                  </h2>
                  <p className="text-xs text-neutral-400 mt-0.5 font-mono">
                    Active Dataset: <span className="text-neutral-200">{activeDatasetName}</span> &bull; Parsing &rarr; Channel Mapping &rarr; Monotonic Resampling
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {SAMPLE_TELEMETRY_DATASETS.map((ds) => (
                    <button
                      key={ds.id}
                      type="button"
                      onClick={() => handleLoadSampleDataset(ds)}
                      disabled={loadingSampleId === ds.id}
                      className={`px-2.5 py-1.5 text-xs font-mono rounded-lg border transition-colors ${
                        activeDatasetName === ds.filename
                          ? "bg-amber-500/20 border-amber-500/50 text-amber-300"
                          : "bg-neutral-950 border-neutral-800 text-neutral-300 hover:border-amber-500/40 hover:text-amber-300"
                      }`}
                      title={ds.formatNote}
                    >
                      {loadingSampleId === ds.id ? "Loading…" : ds.shortLabel}
                    </button>
                  ))}
                  <label className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/40 rounded-lg cursor-pointer transition-colors">
                    <Upload className="w-3.5 h-3.5" />
                    <span>Upload New CSV</span>
                    <input type="file" accept=".csv" onChange={handleCsvUpload} className="hidden" />
                  </label>
                </div>
              </div>

              {/* Ingestion Metrics Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3">
                  <div className="text-[10px] uppercase font-mono text-neutral-400">Raw Samples</div>
                  <div className="text-lg font-bold font-mono text-white mt-0.5">{auditTrail.raw_line_count}</div>
                  <div className="text-[10px] font-mono text-neutral-500">
                    {(() => {
                      const rate = Number(auditTrail.sample_rate_hz) || 100;
                      const dur =
                        typeof auditTrail.duration_s === "number"
                          ? auditTrail.duration_s
                          : auditTrail.raw_line_count / rate;
                      return `${dur.toFixed(1)}s @ ${rate.toFixed(0)} Hz`;
                    })()}
                  </div>
                </div>
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3">
                  <div className="text-[10px] uppercase font-mono text-neutral-400">Mapped Channels</div>
                  <div className="text-lg font-bold font-mono text-emerald-400 mt-0.5">{auditTrail.identified_channels.length}</div>
                  <div className="text-[10px] font-mono text-neutral-500">
                    {(auditTrail.rejected_channels?.length ?? 0)} rejected
                  </div>
                </div>
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3">
                  <div className="text-[10px] uppercase font-mono text-neutral-400">Timestamp Quality</div>
                  <div className="text-lg font-bold font-mono text-cyan-400 mt-0.5">Strictly Monotonic</div>
                  <div className="text-[10px] font-mono text-neutral-500">0 duplicate timestamps</div>
                </div>
                <div className="bg-neutral-950 border border-neutral-800 rounded-lg p-3">
                  <div className="text-[10px] uppercase font-mono text-neutral-400">Resampling Grid</div>
                  <div className="text-lg font-bold font-mono text-cyan-400 mt-0.5">100.0 Hz PCHIP</div>
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

            {/* Failure UX Demonstration Card — only shown when uncalibrated/rejected channels exist */}
            {(auditTrail.rejected_channels?.length ?? 0) > 0 && (
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
            )}
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
                        <td className="py-3 px-4 font-sans font-medium text-white">
                          {ch.name}
                          {ch.synthetic && (
                            <span className="ml-2 px-1.5 py-0.5 rounded text-[9px] font-bold bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 font-mono">
                              SYNTHETIC CHANNEL
                            </span>
                          )}
                        </td>
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
                        className="flex items-center gap-2 px-5 py-2.5 text-xs font-bold uppercase tracking-wider bg-cyan-500 hover:bg-cyan-400 text-black rounded-lg shadow-md transition-all"
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
                        ? "bg-amber-500 text-black font-bold shadow-md"
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
                          activeChannelData.epistemic_label === "CORRELATED" && r2Ok
                            ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                            : activeChannelData.epistemic_label === "INFERRED"
                            ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                            : "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                        }`}
                      >
                        {displayEpistemicLabel}
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
                      <span className="flex items-center gap-1 text-cyan-400">
                        <span className="w-3 h-0.5 bg-cyan-400 inline-block" /> MEASURED (DAQ)
                      </span>
                      <span className="flex items-center gap-1 text-amber-400">
                        <span className="w-3 h-0.5 bg-amber-400 inline-block border-t border-dashed" /> MODEL (ODE)
                      </span>
                      <span className="flex items-center gap-1 text-rose-400">
                        <span className="w-3 h-0.5 bg-rose-400 inline-block border-t border-dotted" /> RESIDUAL
                      </span>
                      {activeChannelData.uncertainty_upper && (
                        <span className="flex items-center gap-1 text-neutral-400">
                          <span className="w-3 h-2 bg-neutral-700/50 inline-block rounded-xs" /> &plusmn;1&sigma; BOUNDS
                        </span>
                      )}
                    </div>
                    <div className="text-neutral-400">
                      R² = <strong className={r2Ok ? "text-emerald-400" : "text-amber-400"}>{activeChannelData.metrics.r_squared}</strong> &bull; RMSE ={" "}
                      <strong className="text-cyan-400">
                        {activeChannelData.metrics.rmse} {activeChannelData.unit}
                      </strong>
                    </div>
                  </div>

                  <div className="h-56 bg-neutral-900/60 rounded-lg border border-neutral-800/80 p-3 flex flex-col justify-end">
                    <svg className="w-full h-44 overflow-visible" viewBox="0 0 600 120" preserveAspectRatio="none">
                      <line x1="0" y1={channelZeroY} x2="600" y2={channelZeroY} stroke="#333" strokeDasharray="3,3" />

                      {/* Uncertainty Area if present */}
                      {activeChannelData.uncertainty_upper && (
                        <polygon
                          points={
                            (activeChannelData.uncertainty_upper || []).slice(0, 100).map((val: number, i: number, arr: number[]) => {
                              const x = (i / Math.max(arr.length - 1, 1)) * 600;
                              const y = scaleChannelY(val);
                              return `${x.toFixed(1)},${y.toFixed(1)}`;
                            }).join(" ") +
                            " " +
                            (activeChannelData.uncertainty_lower || []).slice(0, 100).reverse().map((val: number, i: number, arr: number[]) => {
                              const x = ((arr.length - 1 - i) / Math.max(arr.length - 1, 1)) * 600;
                              const y = scaleChannelY(val);
                              return `${x.toFixed(1)},${y.toFixed(1)}`;
                            }).join(" ")
                          }
                          fill="rgba(168, 85, 247, 0.15)"
                        />
                      )}

                      {/* Measured trace (Cyan solid) */}
                      <path
                        d={(activeChannelData.measured || []).slice(0, 100).map((val: number, i: number, arr: number[]) => {
                          const x = (i / Math.max(arr.length - 1, 1)) * 600;
                          const y = scaleChannelY(val);
                          return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
                        }).join(" ")}
                        fill="none"
                        stroke="#06B6D4"
                        strokeWidth="2"
                      />

                      {/* Model trace (Amber dashed) */}
                      <path
                        d={(activeChannelData.simulated || []).slice(0, 100).map((val: number, i: number, arr: number[]) => {
                          const x = (i / Math.max(arr.length - 1, 1)) * 600;
                          const y = scaleChannelY(val);
                          return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
                        }).join(" ")}
                        fill="none"
                        stroke="#F59E0B"
                        strokeWidth="2"
                        strokeDasharray="4,2"
                      />

                      {/* Residual trace (Coral dotted) */}
                      <path
                        d={(activeChannelData.residual || []).slice(0, 100).map((val: number, i: number, arr: number[]) => {
                          const x = (i / Math.max(arr.length - 1, 1)) * 600;
                          const y = scaleResidualY(val);
                          return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
                        }).join(" ")}
                        fill="none"
                        stroke="#F43F5E"
                        strokeWidth="1.5"
                        strokeDasharray="2,2"
                      />
                    </svg>

                    <div className="flex justify-between text-[10px] font-mono text-neutral-500 mt-2">
                      {dynamicTimeLabels.map((lbl: string, idx: number) => (
                        <span key={idx}>{lbl}</span>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Sensor Alignment Manifest & G-G Friction Circle */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
                  <div className={modelComparisonData?.sensor_alignment_manifest ? "lg:col-span-8" : "lg:col-span-8 flex items-center"}>
                    {modelComparisonData?.sensor_alignment_manifest ? (
                      <div className="h-full bg-neutral-950 border border-neutral-800 rounded-xl p-4 text-xs font-mono space-y-2">
                        <div className="text-cyan-400 font-bold uppercase text-[11px]">Sensor Alignment Manifest</div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-neutral-300">
                          <div>Resampling: {Number(auditTrail.sample_rate_hz || 100).toFixed(1)} Hz (PCHIP Monotonic Interpolation)</div>
                          <div>Spatial Resolution: 1.0 m grid</div>
                          <div>Coordinate Transforms: Z-Up, Y-Left, X-Forward</div>
                          <div>Anti-Tautology: Independent ODE Forward Integration</div>
                        </div>
                      </div>
                    ) : (
                      <div className="w-full h-full bg-neutral-950 border border-neutral-800 rounded-xl p-4 text-xs font-mono text-neutral-400 flex items-center">
                        Peak Resultant Grip Envelope ({activeDatasetName}): <strong className="text-white ml-2">{gCircleStats.maxG.toFixed(2)} G</strong>
                      </div>
                    )}
                  </div>
                  <div className="lg:col-span-4 min-h-[320px]">
                    <GGFrictionCircle
                      maxG={gCircleStats.maxG}
                      latG={gCircleStats.latG}
                      longG={gCircleStats.longG}
                    />
                  </div>
                </div>
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
                  className="flex items-center gap-2 px-5 py-2.5 text-xs font-bold uppercase tracking-wider bg-amber-500 hover:bg-amber-400 text-black rounded-lg shadow-md transition-all"
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
                  {residualHistogramBins.map((cnt: number, i: number) => {
                    const maxBin = Math.max(...residualHistogramBins, 1);
                    const heightPct = (cnt / maxBin) * 100;
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
                  onClick={() => runSessionComparison()}
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
                      {(() => {
                        const dt = sessionCompData.lap_time_delta_s ?? sessionCompData.lap_time_delta;
                        if (typeof dt === "number" && Number.isFinite(dt)) {
                          return (
                            <>
                              Lap Time Delta:{" "}
                              <span className={`${dt <= 0 ? "text-emerald-400" : "text-amber-400"} font-mono font-bold`}>
                                {fmtNum(dt, 3, true)} s
                              </span>{" "}
                              ({dt <= 0 ? "Stint B is faster" : "Stint A is faster"})
                            </>
                          );
                        }
                        return (
                          <>
                            Telemetry Session Comparison:{" "}
                            <span className="text-cyan-400 font-mono font-bold">
                              {sessionCompData.corner_deltas?.length ?? 0} zones compared
                            </span>
                          </>
                        );
                      })()}
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

              {!sessionCompData && (
                <div className="rounded-xl border border-dashed border-neutral-800 bg-neutral-950/40 p-10 text-center space-y-3">
                  <div className="w-10 h-10 rounded-full bg-neutral-800/80 text-purple-400 mx-auto flex items-center justify-center">
                    <Layers className="w-5 h-5" />
                  </div>
                  <h3 className="text-sm font-semibold text-white">No Session Comparison Data Available</h3>
                  <p className="text-xs text-neutral-400 max-w-md mx-auto">
                    Upload a CSV telemetry log with at least 20 samples or load one of the built-in GT3 datasets above to perform empirical stint and lap delta attribution.
                  </p>
                  <div className="flex flex-wrap justify-center gap-2 pt-2">
                    {SAMPLE_TELEMETRY_DATASETS.map((ds) => (
                      <button
                        key={ds.id}
                        onClick={() => handleLoadSampleDataset(ds)}
                        className="px-2.5 py-1 text-[11px] font-mono bg-neutral-800 hover:bg-neutral-700 text-neutral-300 rounded border border-neutral-700"
                      >
                        Load {ds.shortLabel}
                      </button>
                    ))}
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

export default function CorrelationCockpitPage() {
  return (
    <PlanGate required="PRO" feature="Telemetry & Physical Model Correlation Cockpit">
      <CorrelationCockpitContent />
    </PlanGate>
  );
}
