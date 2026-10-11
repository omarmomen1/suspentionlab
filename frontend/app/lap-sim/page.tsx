"use client";

import { useState, useCallback, useRef } from "react";
import dynamic from "next/dynamic";
import {
  Timer, Upload, Play, ChevronDown, ChevronRight,
  Zap, Gauge, Wind, Activity, BarChart3, TrendingDown,
  AlertCircle, CheckCircle, Loader2, Settings2, Layers,
} from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";

import Plot from "../../components/sim/Plot";
import { maxAbs } from "../../lib/array";
import TrackMap from "../../components/sim/TrackMap";
import CornerAnalysisPanel, { CornerItem, CornerComparisonItem } from "../../components/sim/CornerAnalysisPanel";
import LapDeltaView, { LapDeltaReportData } from "../../components/sim/LapDeltaView";
import TelemetryCorrelationView, { CorrelationReportData } from "../../components/sim/TelemetryCorrelationView";
import LapSimDecisionCard, { RaceEngineerDecisionData } from "../../components/sim/LapSimDecisionCard";

import CrossValidationView, { CrossValidationData } from "../../components/sim/CrossValidationView";
import TransientManeuverView, { ManeuverResultData } from "../../components/sim/TransientManeuverView";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Types ───────────────────────────────────────────────────────────────────

interface VehicleConfig {
  // Mass
  mass: number;
  h_cog: number;
  wheelbase: number;
  cog_dist_front: number;
  track_front: number;
  // Aero
  cl_base: number;
  cd_base: number;
  frontal_area: number;
  cop_fraction: number;
  cl_rh_sens: number;
  // Powertrain
  max_power_kw: number;
  brake_front_bias: number;
  // Differential Subsystem
  diff_type: "OPEN" | "LOCKED" | "LSD_TORQUE_BIASED" | "CLUTCH_PACK";
  bias_ratio: number;
  preload_nm: number;
  ramp_angle_accel_deg: number;
  ramp_angle_decel_deg: number;
  drivetrain_layout: "RWD" | "FWD" | "AWD";
}

interface LapResult {
  total_time_s: number;
  sector_times_s: number[];
  max_speed_kmh: number;
  min_speed_kmh: number;
  avg_speed_kmh: number;
  energy_used_kj: number;
  avg_power_kw: number;
  terminal_velocity_kmh: number;
  model_version: string;
  telemetry: {
    distances: number[];
    speeds_ms?: number[];
    speeds_kmh: number[];
    lateral_g: number[];
    longitudinal_g: number[];
    curvatures: number[];
    gear_number: number[];
    drive_force_n: number[];
    aero_downforce_n: number[];
    aero_drag_n: number[];
    wheel_load_fl_n: number[];
    wheel_load_fr_n: number[];
    wheel_load_rl_n: number[];
    wheel_load_rr_n: number[];
    tire_utilization_combined?: number[];
  };
  ggv: {
    speeds_ms: number[];
    ay_max_ms2: number[];
    ax_accel_ms2: number[];
    ax_brake_ms2: number[];
    ay_frac?: number[];
    ax_accel_surface?: number[][];
    ax_brake_surface?: number[][];
  };
  track_coordinates?: {
    x: number[];
    y: number[];
    heading_rad: number[];
    is_closed: boolean;
    closure_error_m: number;
  };
}

interface GpsData {
  latitudes: number[];
  longitudes: number[];
  elevations: number[];
  n_points: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatLapTime(s: number): string {
  if (!s || s <= 0) return "--:--.---";
  const m = Math.floor(s / 60);
  const sec = s - m * 60;
  return `${m}:${sec.toFixed(3).padStart(6, "0")}`;
}

function syntheticGrandPrixCircuit(totalLengthM: number, avgRadiusM: number, nPoints = 600) {
  // Generates a realistic 10-corner Grand Prix circuit with varied slow, medium, and fast corners
  // plus smooth clothoid curvature ramps for realistic trail braking and exit traction.
  const distances: number[] = [];
  const curvatures: number[] = [];
  const ds = totalLengthM / nPoints;

  // Corner definitions: [center_fraction, length_fraction, radius_m, sign (1=right, -1=left)]
  const corners = [
    { frac: 0.12, len: 0.05, r: Math.max(avgRadiusM * 0.55, 28), sign: 1 },    // T1 Hairpin (slow)
    { frac: 0.22, len: 0.04, r: Math.max(avgRadiusM * 0.90, 48), sign: -1 },   // T2 Chicane Left
    { frac: 0.28, len: 0.04, r: Math.max(avgRadiusM * 0.95, 52), sign: 1 },    // T3 Chicane Right
    { frac: 0.42, len: 0.06, r: Math.max(avgRadiusM * 2.10, 130), sign: -1 },  // T4 High Speed Sweeper
    { frac: 0.54, len: 0.06, r: Math.max(avgRadiusM * 1.20, 70), sign: 1 },    // T5 Carousel Right
    { frac: 0.65, len: 0.05, r: Math.max(avgRadiusM * 0.80, 42), sign: -1 },   // T6 Medium Left
    { frac: 0.76, len: 0.04, r: Math.max(avgRadiusM * 1.05, 58), sign: 1 },    // T7 Double Apex 1
    { frac: 0.82, len: 0.04, r: Math.max(avgRadiusM * 0.70, 36), sign: 1 },    // T8 Double Apex 2
    { frac: 0.92, len: 0.05, r: Math.max(avgRadiusM * 1.10, 62), sign: -1 },   // T9 Final Corner
  ];

  let d = 0;
  for (let i = 0; i < nPoints; i++) {
    const frac = i / nPoints;
    let kappa = 0;

    for (const c of corners) {
      const halfLen = c.len / 2;
      const distFromCenter = Math.abs(frac - c.frac);
      if (distFromCenter < halfLen) {
        // Smooth Hann window curvature ramp (clothoid approximation)
        const ramp = 0.5 * (1 + Math.cos((Math.PI * distFromCenter) / halfLen));
        kappa += (1.0 / c.r) * c.sign * ramp;
      }
    }

    distances.push(d);
    curvatures.push(kappa);
    d += ds;
  }

  return { distances, curvatures };
}


const PLOTLY_BASE = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { color: "#666", size: 11, family: "Inter, monospace" },
  xaxis: { color: "#444", gridcolor: "#161618", zerolinecolor: "#2a2a2a" },
  yaxis: { color: "#444", gridcolor: "#161618", zerolinecolor: "#2a2a2a" },
  margin: { l: 58, r: 22, t: 32, b: 55 },
  autosize: true,
  legend: { font: { color: "#888", size: 10 } },
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function Section({ title, children, defaultOpen = true }: {
  title: string; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="mb-3 pb-2 border-b border-[#1f1f23]">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between py-1 mb-1.5 group text-left cursor-pointer"
      >
        <span className="text-[10px] font-bold text-zinc-300 uppercase tracking-[0.14em] group-hover:text-amber-400 transition-colors">
          {title}
        </span>
        {open ? <ChevronDown size={12} className="text-zinc-500 group-hover:text-amber-400 transition-colors" /> : <ChevronRight size={12} className="text-zinc-500 group-hover:text-amber-400 transition-colors" />}
      </button>
      {open && <div className="space-y-1">{children}</div>}
    </div>
  );
}

function ParamRow({ label, unit, value, onChange, min, max, step = 0.01 }: {
  label: string; unit: string; value: number;
  onChange: (v: number) => void; min?: number; max?: number; step?: number;
}) {
  const inputId = `param-${label.toLowerCase().replace(/[^a-z0-9]/g, "-")}`;
  return (
    <div className="flex items-center justify-between gap-2.5 py-1">
      <label htmlFor={inputId} className="text-[11px] text-zinc-400 flex-1 leading-snug whitespace-nowrap">{label}</label>
      <div className="flex items-center gap-1.5 shrink-0">
        <input
          id={inputId}
          aria-label={`${label} (${unit})`}
          type="number"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={e => onChange(parseFloat(e.target.value) || 0)}
          className="w-[74px] bg-[#0d0d0d] border border-[#252525] text-[11px] rounded px-2 py-1 text-white font-mono
            focus:outline-none focus:border-[#f2a900]/50 focus:ring-1 focus:ring-[#f2a900]/30 text-right"
        />
        <span className="text-[10px] text-zinc-500 w-12 text-left leading-none font-sans">{unit}</span>
      </div>
    </div>
  );
}

function KpiCard({ label, value, unit, icon: Icon, accent = false }: {
  label: string; value: string; unit: string; icon: React.ElementType; accent?: boolean;
}) {
  return (
    <div className={`bg-[#141416] border rounded-xl p-3 flex flex-col gap-1.5
      ${accent ? "border-[#f2a900]/30" : "border-[#252525]"}
      hover:border-[#353535] transition-colors`}>
      <div className="flex items-center gap-1.5">
        <Icon size={11} className={accent ? "text-[#f2a900]" : "text-gray-600"} />
        <span className="text-[9px] font-bold uppercase tracking-[0.14em] text-gray-600">{label}</span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className={`text-xl font-bold tabular-nums leading-none ${accent ? "text-[#f2a900]" : "text-white"}`}>
          {value}
        </span>
        <span className="text-[9px] text-gray-600">{unit}</span>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function LapSimPage() {
  const { authHeader, fetchWithAuth } = useAuth();
  const [activeTab, setActiveTab] = useState(0);
  const [result, setResult] = useState<LapResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [gpsData, setGpsData] = useState<GpsData | null>(null);
  const [gpxName, setGpxName] = useState<string>("");
  const [uploading, setUploading] = useState(false);
  const [trackMode, setTrackMode] = useState<"gpx" | "oval">("oval");
  const [ovalLength, setOvalLength] = useState(3500);
  const [ovalRadius, setOvalRadius] = useState(60);
  const [hoverDist, setHoverDist] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Phase 3 Intelligence State
  const [corners, setCorners] = useState<CornerItem[]>([]);
  const [cornerComparisons, setCornerComparisons] = useState<CornerComparisonItem[]>([]);
  const [selectedCornerId, setSelectedCornerId] = useState<number | null>(null);
  const [deltaReport, setDeltaReport] = useState<LapDeltaReportData | null>(null);
  const [decision, setDecision] = useState<RaceEngineerDecisionData | null>(null);
  const [correlationReport, setCorrelationReport] = useState<CorrelationReportData | null>(null);
  const [comparing, setComparing] = useState(false);
  const [correlating, setCorrelating] = useState(false);

  // 3-Tier Multi-Fidelity Architecture State
  const [solverMode, setSolverMode] = useState<"FAST_QSS" | "HIGH_FIDELITY_LAP" | "TRANSIENT_ENGINEERING">("FAST_QSS");
  const [maneuverType, setManeuverType] = useState<"STEP_STEER" | "THRESHOLD_BRAKING" | "RAMP_STEER" | "SINE_SWEEP" | "CONSTANT_RADIUS" | "DOUBLE_LANE_CHANGE">("STEP_STEER");
  const [maneuverSpeedMps, setManeuverSpeedMps] = useState<number>(35.0);
  const [maneuverSteerDeg, setManeuverSteerDeg] = useState<number>(3.0);
  const [maneuverBrakeDemand, setManeuverBrakeDemand] = useState<number>(0.85);
  const [maneuverDurationS, setManeuverDurationS] = useState<number>(3.0);
  const [maneuverResult, setManeuverResult] = useState<ManeuverResultData | null>(null);
  const [crossValidationData, setCrossValidationData] = useState<CrossValidationData | null>(null);
  const [crossValidating, setCrossValidating] = useState<boolean>(false);

  const [cfg, setCfg] = useState<VehicleConfig>({
    mass: 800, h_cog: 0.30, wheelbase: 2.70, cog_dist_front: 1.35, track_front: 1.55,
    cl_base: 1.80, cd_base: 0.95, frontal_area: 1.70, cop_fraction: 0.45, cl_rh_sens: 0.0,
    max_power_kw: 350, brake_front_bias: 65,
    diff_type: "LSD_TORQUE_BIASED",
    bias_ratio: 3.0,
    preload_nm: 60,
    ramp_angle_accel_deg: 45,
    ramp_angle_decel_deg: 60,
    drivetrain_layout: "RWD",
  });

  const set = (k: keyof VehicleConfig) => (v: any) => setCfg(c => ({ ...c, [k]: v }));

  const buildVehiclePayload = () => ({
    mass_props: {
      total_mass: cfg.mass,
      h_cog: cfg.h_cog,
      wheelbase: cfg.wheelbase,
      cog_dist_front: cfg.cog_dist_front,
      track_front: cfg.track_front,
    },
    aero: {
      cl_base: cfg.cl_base,
      cd_base: cfg.cd_base,
      frontal_area: cfg.frontal_area,
      cop_fraction: cfg.cop_fraction,
      cl_rh_sens: cfg.cl_rh_sens,
    },
    powertrain: {
      brake_front_bias: cfg.brake_front_bias / 100,
    },
    differential: {
      diff_type: cfg.diff_type,
      bias_ratio: cfg.bias_ratio,
      preload_nm: cfg.preload_nm,
      ramp_angle_accel_deg: cfg.ramp_angle_accel_deg,
      ramp_angle_decel_deg: cfg.ramp_angle_decel_deg,
      drivetrain_layout: cfg.drivetrain_layout,
    },
    max_power: cfg.max_power_kw * 1000,
  });

  const handleApplyRecommendation = (param: string, delta: number) => {
    if (param === "mass" || param === "total_mass") {
      setCfg(c => ({ ...c, mass: Math.round(Math.max(c.mass + delta, 300)) }));
    } else if (param === "cl_base") {
      setCfg(c => ({ ...c, cl_base: parseFloat((c.cl_base + delta).toFixed(2)) }));
    } else if (param === "cd_base") {
      setCfg(c => ({ ...c, cd_base: parseFloat((c.cd_base + delta).toFixed(2)) }));
    } else if (param === "brake_front_bias") {
      setCfg(c => ({ ...c, brake_front_bias: Math.round(c.brake_front_bias + delta) }));
    } else if (param === "max_power_kw" || param === "max_power") {
      setCfg(c => ({ ...c, max_power_kw: Math.round(c.max_power_kw + delta) }));
    }
  };

  const handleGpxUpload = useCallback(async (file: File) => {
    setUploading(true);
    setError(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetchWithAuth("/api/v1/lapsim/upload_gpx", {
        method: "POST",
        body: fd,
      });
      if (!res.ok) throw new Error((await res.json()).detail ?? "Upload failed");
      const data = await res.json();
      setGpsData(data);
      setGpxName(file.name);
      setTrackMode("gpx");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "GPX upload failed");
    } finally {
      setUploading(false);
    }
  }, [fetchWithAuth]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file?.name.endsWith(".gpx")) handleGpxUpload(file);
  }, [handleGpxUpload]);

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      if (solverMode === "TRANSIENT_ENGINEERING") {
        const res = await fetchWithAuth("/api/v1/lapsim/maneuver", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            maneuver_type: maneuverType,
            initial_speed_mps: maneuverSpeedMps,
            parameters: {
              amplitude_deg: maneuverSteerDeg,
              steer_amplitude_deg: maneuverSteerDeg,
              brake_demand: maneuverBrakeDemand,
              duration_s: maneuverDurationS,
              t_total: maneuverDurationS,
            },
            vehicle: buildVehiclePayload(),
          }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail ?? "Maneuver simulation failed");
        }
        const data = await res.json();
        setManeuverResult(data);
        return;
      }

      let body: Record<string, unknown> = {
        vehicle: buildVehiclePayload(),
        solver_mode: solverMode === "HIGH_FIDELITY_LAP" ? "HIGH_FIDELITY_LAP" : "FAST_QUASI_STEADY",
      };

      let circuitDistances: number[] = [];
      let circuitCurvatures: number[] = [];

      if (trackMode === "gpx" && gpsData) {
        body = {
          ...body,
          latitudes: gpsData.latitudes,
          longitudes: gpsData.longitudes,
          elevations: gpsData.elevations,
        };
      } else {
        const synth = syntheticGrandPrixCircuit(ovalLength, ovalRadius, 500);
        circuitDistances = synth.distances;
        circuitCurvatures = synth.curvatures;
        body = { ...body, distances: circuitDistances, curvatures: circuitCurvatures };
      }

      const res = await fetchWithAuth("/api/v1/lapsim/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? "Simulation failed");
      }
      const data = await res.json();
      setResult(data);

      const trackDists = data.telemetry?.distances || circuitDistances;
      const trackCurvs = data.telemetry?.curvatures || circuitCurvatures;

      // Automatically fetch corner analysis for the circuit
      if (trackDists.length > 2 && trackCurvs.length > 2) {
        try {
          const cornerRes = await fetchWithAuth("/api/v1/lapsim/corners", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              distances: trackDists,
              curvatures: trackCurvs,
              speeds: data.telemetry?.speeds_ms ?? data.telemetry?.speeds_kmh?.map((v: number) => v / 3.6),
              lateral_g: data.telemetry?.lateral_g,
              longitudinal_g: data.telemetry?.longitudinal_g,
            }),
          });
          if (cornerRes.ok) {
            const cornerData = await cornerRes.json();
            setCorners(cornerData.corners || []);
          }
        } catch {
          // ignore background corner fetch error
        }

        // Automatically fetch race engineer decision summary
        try {
          const decRes = await fetchWithAuth("/api/v1/lapsim/decision", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              distances: trackDists,
              curvatures: trackCurvs,
              vehicle_a: buildVehiclePayload(),
              vehicle_b: {
                ...buildVehiclePayload(),
                mass_props: {
                  ...buildVehiclePayload().mass_props,
                  total_mass: Math.max(cfg.mass - 25, 400),
                },
                aero: {
                  ...buildVehiclePayload().aero,
                  cl_base: cfg.cl_base + 0.10,
                },
              },
              setup_baseline: {
                mass: cfg.mass,
                cl_base: cfg.cl_base,
                cd_base: cfg.cd_base,
                max_power_kw: cfg.max_power_kw,
              },
              setup_candidate: {
                mass: Math.max(cfg.mass - 25, 400),
                cl_base: cfg.cl_base + 0.10,
                cd_base: cfg.cd_base,
                max_power_kw: cfg.max_power_kw,
              },
            }),
          });
          if (decRes.ok) {
            const decData = await decRes.json();
            setDecision(decData);
          }
        } catch {
          // ignore decision fetch error
        }
      }

    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setRunning(false);
    }
  };

  const handleCompare = async (candOverrides?: Partial<VehicleConfig>) => {
    if (!result || !result.telemetry) return;
    setComparing(true);
    try {
      const candidatePayload = {
        ...buildVehiclePayload(),
        mass_props: {
          ...buildVehiclePayload().mass_props,
          total_mass: candOverrides?.mass ?? Math.max(cfg.mass - 25, 400),
        },
        aero: {
          ...buildVehiclePayload().aero,
          cl_base: candOverrides?.cl_base ?? (cfg.cl_base + 0.15),
          cd_base: candOverrides?.cd_base ?? (cfg.cd_base + 0.02),
        },
      };

      const res = await fetchWithAuth("/api/v1/lapsim/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          distances: result.telemetry.distances,
          curvatures: result.telemetry.curvatures,
          vehicle_a: buildVehiclePayload(),
          vehicle_b: candidatePayload,
        }),
      });
      if (res.ok) {
        const compData = await res.json();
        setDeltaReport(compData.delta_report);
        if (compData.delta_report?.corner_comparisons) {
          setCornerComparisons(compData.delta_report.corner_comparisons);
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Comparison failed");
    } finally {
      setComparing(false);
    }
  };

  const handleCorrelate = async () => {
    if (!result || !result.telemetry) return;
    setCorrelating(true);
    try {
      const dists = result.telemetry.distances;
      const speeds = result.telemetry.speeds_kmh.map(v => v / 3.6);
      // Realistic measured telemetry with sensor noise and realistic driver variance
      const measSpeeds = speeds.map((v, i) => {
        const noise = Math.sin(i * 0.15) * 0.4 - 0.2;
        return Math.max(v + noise, 2.0);
      });
      const measLateralG = result.telemetry.lateral_g.map((g, i) => g + Math.sin(i * 0.2) * 0.05);

      const res = await fetchWithAuth("/api/v1/lapsim/correlate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sim_result: {
            distances: dists,
            speeds_ms: speeds,
            lateral_g: result.telemetry.lateral_g,
            longitudinal_g: result.telemetry.longitudinal_g,
          },
          telemetry: {
            distance_m: dists,
            speed_mps: measSpeeds,
            lateral_g: measLateralG,
          },
          session_id: "Race1_Stint2_Telemetry",
        }),
      });
      if (res.ok) {
        const corrData = await res.json();
        setCorrelationReport(corrData);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Correlation failed");
    } finally {
      setCorrelating(false);
    }
  };

  const handleCrossValidate = async () => {
    setCrossValidating(true);
    setError(null);
    try {
      let body: Record<string, unknown> = {
        vehicle: buildVehiclePayload(),
      };
      if (trackMode === "gpx" && gpsData) {
        body = {
          ...body,
          latitudes: gpsData.latitudes,
          longitudes: gpsData.longitudes,
          elevations: gpsData.elevations,
        };
      } else {
        const synth = syntheticGrandPrixCircuit(ovalLength, ovalRadius, 300);
        body = { ...body, distances: synth.distances, curvatures: synth.curvatures };
      }
      const res = await fetchWithAuth("/api/v1/lapsim/cross_validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? "Cross-validation failed");
      }
      const data = await res.json();
      setCrossValidationData(data.cross_validation);
      setActiveTab(6);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Cross-validation failed");
    } finally {
      setCrossValidating(false);
    }
  };

  const tabs = [
    "Speed & Telemetry",
    "Circuit Map",
    "GG & Aero Envelope",
    "Corner Analysis",
    "Setup Comparison",
    "Telemetry Correlation",
    "QSS ↔ 14-DOF Cross-Validation",
  ];

  const tel = result?.telemetry;
  const ggv = result?.ggv;

  return (
    <div className="flex h-[calc(100vh-44px)] bg-black text-white overflow-hidden">

      {/* ── LEFT PANEL ─────────────────────────────────────────────────────── */}
      <aside aria-label="Simulation Configuration" className="w-[310px] xl:w-[330px] flex-shrink-0 border-r border-[#1a1a1a] overflow-y-auto p-3.5 space-y-2 custom-scrollbar bg-[#0c0c0e]">
        {/* Header */}
        <div className="mb-4 pb-2 border-b border-[#1a1a1a]">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-5 h-5 rounded-md bg-[#f2a900]/10 border border-[#f2a900]/20 flex items-center justify-center">
              <Timer size={11} className="text-[#f2a900]" />
            </div>
            <h1 className="text-[12px] font-bold text-white tracking-wide">Lap Simulator</h1>
          </div>
          <p className="text-[10px] text-zinc-400 leading-relaxed">
            Fast QSS · 14-DOF Dynamic · ISO Transient Maneuvers
          </p>
        </div>

        {/* 3-Tier Multi-Fidelity Architecture Selector */}
        <div className="mb-3 p-1 rounded-xl bg-[#121215] border border-[#222228] flex gap-1">
          {(
            [
              { id: "FAST_QSS", label: "Fast QSS", desc: "Steady State" },
              { id: "HIGH_FIDELITY_LAP", label: "14-DOF Lap", desc: "Dynamic" },
              { id: "TRANSIENT_ENGINEERING", label: "Maneuver", desc: "Time Domain" },
            ] as const
          ).map(m => (
            <button
              key={m.id}
              onClick={() => setSolverMode(m.id)}
              className={`flex-1 py-1.5 px-1 rounded-lg text-center transition-all cursor-pointer ${
                solverMode === m.id
                  ? "bg-[#f2a900] text-black font-bold shadow"
                  : "text-zinc-400 hover:text-white hover:bg-[#1c1c22]"
              }`}
            >
              <div className="text-[10px] leading-tight font-mono">{m.label}</div>
              <div className={`text-[8px] leading-tight ${solverMode === m.id ? "text-zinc-800" : "text-zinc-500"}`}>
                {m.desc}
              </div>
            </button>
          ))}
        </div>

        {/* Maneuver Setup (Transient Mode) OR Track Input (Lap Modes) */}
        {solverMode === "TRANSIENT_ENGINEERING" ? (
          <Section title="Maneuver Setup">
            <div className="space-y-2">
              <div className="flex flex-col gap-1">
                <label className="text-[10px] text-zinc-400 font-mono">Maneuver Test</label>
                <select
                  value={maneuverType}
                  onChange={e => setManeuverType(e.target.value as any)}
                  className="bg-[#0d0d0d] border border-[#252525] text-[11px] rounded px-2 py-1.5 text-white font-mono focus:outline-none focus:border-[#f2a900]/50 cursor-pointer"
                >
                  <option value="STEP_STEER">Step Steer (ISO 7401)</option>
                  <option value="THRESHOLD_BRAKING">Threshold Braking</option>
                  <option value="RAMP_STEER">Ramp Steer (Handling Gradient)</option>
                  <option value="SINE_SWEEP">Frequency Sine Sweep</option>
                  <option value="CONSTANT_RADIUS">Constant Radius Skidpad</option>
                  <option value="DOUBLE_LANE_CHANGE">Double Lane Change (ISO 3888)</option>
                </select>
              </div>

              <ParamRow
                label="Initial Speed"
                unit="m/s"
                value={maneuverSpeedMps}
                onChange={setManeuverSpeedMps}
                min={5}
                max={90}
                step={1}
              />
              <div className="text-[9px] text-zinc-500 text-right pr-14 -mt-1 font-mono">
                ≈ {(maneuverSpeedMps * 3.6).toFixed(0)} km/h
              </div>

              {maneuverType === "STEP_STEER" && (
                <ParamRow
                  label="Steer Amplitude"
                  unit="deg"
                  value={maneuverSteerDeg}
                  onChange={setManeuverSteerDeg}
                  min={0.5}
                  max={45}
                  step={0.5}
                />
              )}

              {maneuverType === "THRESHOLD_BRAKING" && (
                <ParamRow
                  label="Brake Demand"
                  unit="0-1"
                  value={maneuverBrakeDemand}
                  onChange={setManeuverBrakeDemand}
                  min={0.1}
                  max={1.0}
                  step={0.05}
                />
              )}

              <ParamRow
                label="Duration"
                unit="s"
                value={maneuverDurationS}
                onChange={setManeuverDurationS}
                min={1.0}
                max={15.0}
                step={0.5}
              />
            </div>
          </Section>
        ) : (
          <Section title="Track Input">
            <div className="flex rounded-lg border border-[#252525] overflow-hidden mb-2">
              {(["oval", "gpx"] as const).map(m => (
                <button key={m} onClick={() => setTrackMode(m)}
                  className={`flex-1 text-[9px] py-1.5 font-bold uppercase tracking-wider transition-colors
                    ${trackMode === m ? "bg-[#f2a900] text-black" : "text-gray-400 hover:text-gray-200"}`}>
                  {m === "oval" ? "Synthetic" : "GPX File"}
                </button>
              ))}
            </div>

            {trackMode === "oval" ? (
              <>
                <ParamRow label="Circuit Length" unit="m" value={ovalLength}
                  onChange={setOvalLength} min={500} max={20000} step={100} />
                <ParamRow label="Avg Corner Radius" unit="m" value={ovalRadius}
                  onChange={setOvalRadius} min={10} max={500} step={5} />
              </>
            ) : (
              <div
                onDrop={handleDrop}
                onDragOver={e => e.preventDefault()}
                className="border border-dashed border-[#333] rounded-lg p-3 text-center cursor-pointer
                  hover:border-[#f2a900]/40 transition-colors group"
                onClick={() => fileInputRef.current?.click()}
              >
                <input ref={fileInputRef} type="file" accept=".gpx" aria-label="Upload GPX track file" className="hidden"
                  onChange={e => e.target.files?.[0] && handleGpxUpload(e.target.files[0])} />
                {uploading ? (
                  <Loader2 size={16} className="mx-auto text-[#f2a900] animate-spin mb-1" />
                ) : gpsData ? (
                  <CheckCircle size={14} className="mx-auto text-green-500 mb-1" />
                ) : (
                  <Upload size={14} className="mx-auto text-gray-600 mb-1 group-hover:text-gray-400 transition-colors" />
                )}
                <p className="text-[9px] text-gray-600">
                  {gpsData ? gpxName : "Drop .gpx or click"}
                </p>
                {gpsData && (
                  <p className="text-[8px] text-[#f2a900] mt-0.5">{gpsData.n_points.toLocaleString()} pts</p>
                )}
              </div>
            )}
          </Section>
        )}

        {/* Differential & Drivetrain Subsystem */}
        <Section title="Differential & Drivetrain">
          <div className="space-y-2">
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-zinc-400 font-mono">Drivetrain Layout</label>
              <div className="flex rounded border border-[#252525] overflow-hidden">
                {(["RWD", "FWD", "AWD"] as const).map(dt => (
                  <button
                    key={dt}
                    onClick={() => setCfg(c => ({ ...c, drivetrain_layout: dt }))}
                    className={`flex-1 text-[9px] py-1 font-bold font-mono transition-colors ${
                      cfg.drivetrain_layout === dt ? "bg-[#f2a900] text-black" : "text-zinc-400 hover:text-white"
                    }`}
                  >
                    {dt}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-zinc-400 font-mono">Differential Type</label>
              <select
                value={cfg.diff_type}
                onChange={e => setCfg(c => ({ ...c, diff_type: e.target.value as any }))}
                className="bg-[#0d0d0d] border border-[#252525] text-[11px] rounded px-2 py-1.5 text-white font-mono focus:outline-none focus:border-[#f2a900]/50 cursor-pointer"
              >
                <option value="OPEN">Open Differential</option>
                <option value="LOCKED">Spool / 100% Locked</option>
                <option value="LSD_TORQUE_BIASED">Torsen / Torque Biasing</option>
                <option value="CLUTCH_PACK">Salisbury Clutch Pack</option>
              </select>
            </div>

            {cfg.diff_type === "LSD_TORQUE_BIASED" && (
              <ParamRow
                label="Torque Bias Ratio"
                unit=":1"
                value={cfg.bias_ratio}
                onChange={v => setCfg(c => ({ ...c, bias_ratio: v }))}
                min={1.5}
                max={6.0}
                step={0.1}
              />
            )}

            {(cfg.diff_type === "CLUTCH_PACK" || cfg.diff_type === "LSD_TORQUE_BIASED") && (
              <ParamRow
                label="Preload Torque"
                unit="N·m"
                value={cfg.preload_nm}
                onChange={v => setCfg(c => ({ ...c, preload_nm: v }))}
                min={0}
                max={300}
                step={5}
              />
            )}

            {cfg.diff_type === "CLUTCH_PACK" && (
              <>
                <ParamRow
                  label="Power Ramp Angle"
                  unit="deg"
                  value={cfg.ramp_angle_accel_deg}
                  onChange={v => setCfg(c => ({ ...c, ramp_angle_accel_deg: v }))}
                  min={30}
                  max={90}
                  step={5}
                />
                <ParamRow
                  label="Coast Ramp Angle"
                  unit="deg"
                  value={cfg.ramp_angle_decel_deg}
                  onChange={v => setCfg(c => ({ ...c, ramp_angle_decel_deg: v }))}
                  min={30}
                  max={90}
                  step={5}
                />
              </>
            )}
          </div>
        </Section>

        {/* Mass & Geometry */}
        <Section title="Mass & Geometry">
          <ParamRow label="Total Mass" unit="kg" value={cfg.mass} onChange={set("mass")} min={300} max={2000} step={10} />
          <ParamRow label="CoG Height" unit="m" value={cfg.h_cog} onChange={set("h_cog")} min={0.1} max={0.8} />
          <ParamRow label="Wheelbase" unit="m" value={cfg.wheelbase} onChange={set("wheelbase")} min={1.5} max={4.0} step={0.05} />
          <ParamRow label="CoG from Front" unit="m" value={cfg.cog_dist_front} onChange={set("cog_dist_front")} min={0.5} max={3.0} step={0.05} />
          <ParamRow label="Front Track" unit="m" value={cfg.track_front} onChange={set("track_front")} min={0.8} max={2.2} step={0.05} />
        </Section>

        {/* Aerodynamics */}
        <Section title="Aerodynamics">
          <ParamRow label="CL Base" unit="–" value={cfg.cl_base} onChange={set("cl_base")} min={0} max={5} step={0.05} />
          <ParamRow label="CD Base" unit="–" value={cfg.cd_base} onChange={set("cd_base")} min={0.1} max={3} step={0.05} />
          <ParamRow label="Frontal Area" unit="m²" value={cfg.frontal_area} onChange={set("frontal_area")} min={0.5} max={4} step={0.05} />
          <ParamRow label="CoP from Front" unit="–" value={cfg.cop_fraction} onChange={set("cop_fraction")} min={0.1} max={0.9} step={0.01} />
          <ParamRow label="RH Sensitivity" unit="ΔCL/mm" value={cfg.cl_rh_sens} onChange={set("cl_rh_sens")} min={0} max={0.1} step={0.001} />
        </Section>

        {/* Powertrain */}
        <Section title="Powertrain">
          <ParamRow label="Peak Power" unit="kW" value={cfg.max_power_kw} onChange={set("max_power_kw")} min={50} max={1500} step={10} />
          <ParamRow label="Brake Front Bias" unit="%" value={cfg.brake_front_bias} onChange={set("brake_front_bias")} min={40} max={80} step={1} />
          <div className="mt-1 px-2 py-1.5 bg-[#0a0a0a] rounded border border-[#1a1a1a]">
            <p className="text-[9px] text-gray-700">Drive Layout: {cfg.drivetrain_layout} · 6-speed sequential</p>
          </div>
        </Section>

        {/* Run Button */}
        <button
          onClick={handleRun}
          disabled={running}
          id="lap-sim-run-btn"
          className="w-full mt-2 py-2.5 rounded-xl text-[11px] font-bold uppercase tracking-wider
            bg-[#f2a900] text-black hover:bg-[#ffb800] transition-all duration-200
            disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {running ? (
            <><Loader2 size={13} className="animate-spin" />Simulating…</>
          ) : (
            <>
              <Play size={13} />
              {solverMode === "TRANSIENT_ENGINEERING"
                ? "Run Handling Maneuver"
                : solverMode === "HIGH_FIDELITY_LAP"
                ? "Run 14-DOF Dynamic Lap"
                : "Run QSS Simulation"}
            </>
          )}
        </button>

        {error && (
          <div className="mt-2 p-2 rounded-lg bg-red-950/30 border border-red-900/40 flex items-start gap-2">
            <AlertCircle size={11} className="text-red-400 mt-0.5 flex-shrink-0" />
            <p className="text-[9px] text-red-400 leading-relaxed">{error}</p>
          </div>
        )}
      </aside>

      {/* ── CENTER PANEL ───────────────────────────────────────────────────── */}
      <section aria-label="Lap Simulation Results" className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {solverMode === "TRANSIENT_ENGINEERING" ? (
          <div className="flex-1 p-3 min-h-0 overflow-y-auto">
            <TransientManeuverView result={maneuverResult} />
          </div>
        ) : result ? (
          <>
            {/* KPI Cards */}
            <div className="flex-shrink-0 grid grid-cols-3 sm:grid-cols-6 gap-2 p-3 border-b border-[#1a1a1a]">
              <KpiCard label="Lap Time" value={formatLapTime(result.total_time_s)} unit="" icon={Timer} accent />
              <KpiCard label="Top Speed" value={result.max_speed_kmh.toFixed(0)} unit="km/h" icon={Gauge} />
              <KpiCard label="Min Speed" value={result.min_speed_kmh.toFixed(0)} unit="km/h" icon={TrendingDown} />
              <KpiCard label="Avg Speed" value={result.avg_speed_kmh.toFixed(0)} unit="km/h" icon={Activity} />
              <KpiCard label="Energy Used" value={result.energy_used_kj.toFixed(0)} unit="kJ" icon={Zap} />
              <KpiCard label="Terminal v" value={result.terminal_velocity_kmh.toFixed(0)} unit="km/h" icon={Wind} />
            </div>

            {/* Decision Banner if available */}
            {decision && (
              <div className="flex-shrink-0 px-3 pt-3">
                <LapSimDecisionCard decision={decision} onApplyRecommendation={handleApplyRecommendation} />
              </div>
            )}

            {/* Tabs */}
            <div className="flex-shrink-0 flex items-center gap-0 border-b border-[#1a1a1a] px-3">
              {tabs.map((t, i) => (
                <button key={t} onClick={() => setActiveTab(i)}
                  className={`px-3 py-2.5 text-[10px] font-bold uppercase tracking-wider transition-all border-b-2
                    ${activeTab === i
                      ? "text-[#f2a900] border-[#f2a900]"
                      : "text-gray-600 border-transparent hover:text-gray-400"}`}>
                  {t}
                </button>
              ))}
              <div className="ml-auto flex items-center gap-1.5 text-[8px] text-gray-700">
                <Layers size={9} />
                <span>{result.model_version}</span>
              </div>
            </div>

            {/* Plot & View Area */}
            <div className="flex-1 p-3 min-h-0 overflow-y-auto">
              {activeTab === 0 && tel && (
                <div className="h-full flex flex-col space-y-3">
                  <div className="h-[55%] min-h-[200px]">
                    <Plot
                      data={[
                        {
                          x: tel.distances, y: tel.speeds_kmh,
                          type: "scatter", mode: "lines", name: "Speed",
                          line: { color: "#f2a900", width: 1.5 },
                          yaxis: "y",
                        },
                        {
                          x: tel.distances, y: tel.gear_number,
                          type: "scatter", mode: "lines", name: "Gear",
                          line: { color: "#3b82f6", width: 1, shape: "hv" },
                          yaxis: "y2",
                        },
                      ]}
                      layout={{
                        ...PLOTLY_BASE,
                        title: { text: "Speed Trace & Gear Selection", font: { color: "#555", size: 12 } },
                        xaxis: { ...PLOTLY_BASE.xaxis, title: { text: "Distance [m]", font: { color: "#555" } } },
                        yaxis: { ...PLOTLY_BASE.yaxis, title: { text: "Speed [km/h]", font: { color: "#f2a900" } }, tickfont: { color: "#f2a900" } },
                        yaxis2: {
                          title: { text: "Gear", font: { color: "#3b82f6" } }, tickfont: { color: "#3b82f6" },
                          overlaying: "y", side: "right", gridcolor: "transparent",
                          dtick: 1, range: [0, 8],
                        },
                      } as Record<string, unknown>}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                      onHover={(eventData: any) => {
                        const pt = eventData.points?.[0];
                        if (pt && typeof pt.x === "number") setHoverDist(pt.x);
                      }}
                      onUnhover={() => setHoverDist(null)}
                    />
                  </div>
                  <div className="h-[45%] min-h-[160px] grid grid-cols-1 md:grid-cols-2 gap-3">
                    <Plot
                      data={[
                        { x: tel.distances, y: tel.wheel_load_fl_n, type: "scatter", mode: "lines", name: "FL", line: { color: "#3b82f6", width: 1.2 } },
                        { x: tel.distances, y: tel.wheel_load_fr_n, type: "scatter", mode: "lines", name: "FR", line: { color: "#f2a900", width: 1.2 } },
                        { x: tel.distances, y: tel.wheel_load_rl_n, type: "scatter", mode: "lines", name: "RL", line: { color: "#22c55e", width: 1.2 } },
                        { x: tel.distances, y: tel.wheel_load_rr_n, type: "scatter", mode: "lines", name: "RR", line: { color: "#ef4444", width: 1.2 } },
                      ]}
                      layout={{
                        ...PLOTLY_BASE,
                        title: { text: "Wheel Normal Loads [N]", font: { color: "#555", size: 11 } },
                        xaxis: { ...PLOTLY_BASE.xaxis, title: { text: "Distance [m]", font: { color: "#555" } } },
                        yaxis: { ...PLOTLY_BASE.yaxis, title: { text: "Load [N]", font: { color: "#555" } } },
                        legend: { orientation: "h", y: 1.15, font: { color: "#888", size: 9 } },
                      } as Record<string, unknown>}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                    <Plot
                      data={[
                        { x: tel.distances, y: tel.aero_downforce_n, type: "scatter", mode: "lines", name: "Downforce", line: { color: "#a78bfa", width: 1.5 } },
                        { x: tel.distances, y: tel.aero_drag_n, type: "scatter", mode: "lines", name: "Drag", line: { color: "#f97316", width: 1.5 } },
                      ]}
                      layout={{
                        ...PLOTLY_BASE,
                        title: { text: "Aero Forces [N]", font: { color: "#555", size: 11 } },
                        xaxis: { ...PLOTLY_BASE.xaxis, title: { text: "Distance [m]", font: { color: "#555" } } },
                        yaxis: { ...PLOTLY_BASE.yaxis, title: { text: "Force [N]", font: { color: "#555" } } },
                        legend: { orientation: "h", y: 1.15, font: { color: "#888", size: 9 } },
                      } as Record<string, unknown>}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  </div>
                </div>
              )}

              {activeTab === 1 && tel && (
                <div className="h-full flex flex-col">
                  <TrackMap
                    x={result.track_coordinates?.x || []}
                    y={result.track_coordinates?.y || []}
                    distances={tel.distances}
                    speedsKmh={tel.speeds_kmh}
                    lateralG={tel.lateral_g}
                    longitudinalG={tel.longitudinal_g}
                    tireUtilization={tel.tire_utilization_combined}
                    corners={corners}
                    hoverDist={hoverDist}
                    onHoverDist={setHoverDist}
                    onSelectCorner={(c) => {
                      setSelectedCornerId(c.corner_id);
                      setActiveTab(3);
                    }}
                  />
                </div>
              )}

              {activeTab === 2 && tel && (
                <div className="h-full grid grid-cols-1 md:grid-cols-2 gap-3">
                  <Plot
                    data={[
                      {
                        x: tel.lateral_g, y: tel.longitudinal_g,
                        type: "scatter", mode: "markers",
                        marker: {
                          color: tel.speeds_kmh, colorscale: "Plasma",
                          size: 2.5, opacity: 0.7,
                          colorbar: { title: { text: "km/h", font: { color: "#666" } }, tickfont: { color: "#666" }, thickness: 12 },
                        },
                        name: "GG Telemetry",
                      },
                      ...[50, 150, 250].map((vKmh) => {
                        const vMs = vKmh / 3.6;
                        const q = 0.5 * 1.225 * vMs * vMs;
                        const downforceN = q * cfg.cl_base * cfg.frontal_area;
                        const baseG = 1.15;
                        const aeroG = (downforceN / (cfg.mass * 9.81)) * 1.2;
                        const totalG = baseG + aeroG;
                        const theta = Array.from({ length: 70 }, (_, i) => (i / 69) * 2 * Math.PI);
                        return {
                          x: theta.map(t => totalG * Math.cos(t)),
                          y: theta.map(t => totalG * Math.sin(t)),
                          type: "scatter" as const,
                          mode: "lines" as const,
                          name: `Aero Envelope @ ${vKmh} km/h (±${totalG.toFixed(2)}g)`,
                          line: {
                            color: vKmh === 50 ? "#3b82f640" : vKmh === 150 ? "#f2a90050" : "#ef444450",
                            dash: "dash" as const,
                            width: 1.2,
                          },
                        };
                      }),
                    ]}
                    layout={{
                      ...PLOTLY_BASE,
                      title: { text: "GG Diagram with Aero-Expanded Envelopes", font: { color: "#555", size: 12 } },
                      xaxis: { ...PLOTLY_BASE.xaxis, title: { text: "Lateral G", font: { color: "#555" } }, zeroline: true, zerolinecolor: "#333" },
                      yaxis: { ...PLOTLY_BASE.yaxis, title: { text: "Longitudinal G", font: { color: "#555" } }, zeroline: true, zerolinecolor: "#333" },
                      legend: { orientation: "h", y: 1.08, font: { color: "#888", size: 9 } },
                    } as Record<string, unknown>}
                    config={{ displayModeBar: false, responsive: true }}
                    style={{ width: "100%", height: "100%" }}
                    useResizeHandler
                  />
                  {ggv && (
                    <Plot
                      data={[
                        {
                          x: ggv.speeds_ms.map(v => v * 3.6),
                          y: ggv.ay_max_ms2.map(a => a / 9.81),
                          type: "scatter", mode: "lines", name: "ay max",
                          line: { color: "#f2a900", width: 2 },
                        },
                        {
                          x: ggv.speeds_ms.map(v => v * 3.6),
                          y: ggv.ax_accel_ms2.map(a => a / 9.81),
                          type: "scatter", mode: "lines", name: "ax accel",
                          line: { color: "#22c55e", width: 1.5, dash: "dot" },
                        },
                        {
                          x: ggv.speeds_ms.map(v => v * 3.6),
                          y: ggv.ax_brake_ms2.map(a => a / 9.81),
                          type: "scatter", mode: "lines", name: "ax brake",
                          line: { color: "#ef4444", width: 1.5, dash: "dot" },
                        },
                      ]}
                      layout={{
                        ...PLOTLY_BASE,
                        title: { text: "GGV Performance Envelope vs Speed", font: { color: "#555", size: 12 } },
                        xaxis: { ...PLOTLY_BASE.xaxis, title: { text: "Speed [km/h]", font: { color: "#555" } } },
                        yaxis: { ...PLOTLY_BASE.yaxis, title: { text: "Acceleration [g]", font: { color: "#555" } } },
                        legend: { orientation: "h", y: 1.08, font: { color: "#888", size: 9 } },
                      } as Record<string, unknown>}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  )}
                </div>
              )}

              {activeTab === 3 && (
                <div className="h-full overflow-y-auto custom-scrollbar">
                  <CornerAnalysisPanel
                    corners={corners}
                    comparisons={cornerComparisons}
                    selectedCornerId={selectedCornerId}
                    onSelectCorner={(id) => {
                      setSelectedCornerId(id);
                      const corner = corners.find(c => c.corner_id === id);
                      if (corner) setHoverDist(corner.apex_distance_m);
                    }}
                  />
                </div>
              )}

              {activeTab === 4 && (
                <div className="h-full flex flex-col space-y-3 overflow-y-auto custom-scrollbar">
                  <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-[#101014] border border-[#202026] rounded-xl">
                    <div className="text-xs text-zinc-300 font-mono">
                      Compare Current Setup against Candidates:
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleCompare({ cl_base: cfg.cl_base + 0.20, cd_base: cfg.cd_base + 0.03 })}
                        disabled={comparing}
                        className="px-2.5 py-1 text-[10px] bg-[#1a1a22] hover:bg-[#252530] text-amber-300 rounded border border-[#333340] transition-colors"
                      >
                        +0.20 High Downforce
                      </button>
                      <button
                        onClick={() => handleCompare({ mass: Math.max(cfg.mass - 35, 400) })}
                        disabled={comparing}
                        className="px-2.5 py-1 text-[10px] bg-[#1a1a22] hover:bg-[#252530] text-emerald-300 rounded border border-[#333340] transition-colors"
                      >
                        -35kg Weight Reduction
                      </button>
                      <button
                        onClick={() => handleCompare()}
                        disabled={comparing}
                        className="px-3 py-1 text-[10px] font-bold bg-[#f2a900] hover:bg-[#ffb800] text-black rounded transition-colors flex items-center gap-1.5"
                      >
                        {comparing ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
                        Run A/B Delta
                      </button>
                    </div>
                  </div>

                  <LapDeltaView report={deltaReport} />
                </div>
              )}

              {activeTab === 5 && (
                <div className="h-full flex flex-col space-y-3 overflow-y-auto custom-scrollbar">
                  <div className="flex items-center justify-between p-3 bg-[#101014] border border-[#202026] rounded-xl">
                    <div>
                      <div className="text-xs text-zinc-300 font-mono font-bold">Logged vs Simulation Validation</div>
                      <div className="text-[10px] text-zinc-500">Cross-correlate distance-domain speeds and identify driver spatial phase lag</div>
                    </div>
                    <button
                      onClick={handleCorrelate}
                      disabled={correlating}
                      className="px-3 py-1.5 text-[10px] font-bold bg-[#3b82f6] hover:bg-[#60a5fa] text-white rounded transition-colors flex items-center gap-1.5"
                    >
                      {correlating ? <Loader2 size={11} className="animate-spin" /> : <Activity size={11} />}
                      Run Telemetry Correlation
                    </button>
                  </div>

                  <TelemetryCorrelationView
                    report={correlationReport}
                    simSpeedsKmh={tel?.speeds_kmh}
                    distances={tel?.distances}
                  />
                </div>
              )}

              {activeTab === 6 && (
                <div className="h-full flex flex-col space-y-3 overflow-y-auto custom-scrollbar">
                  <div className="flex items-center justify-between p-3 bg-[#101014] border border-[#202026] rounded-xl">
                    <div>
                      <div className="text-xs text-zinc-300 font-mono font-bold">Fast QSS ↔ 14-DOF Transient Cross-Validation</div>
                      <div className="text-[10px] text-zinc-500">
                        Execute parallel steady-state vs 14-DOF transient passes on the current circuit to isolate physical losses.
                      </div>
                    </div>
                    <button
                      onClick={handleCrossValidate}
                      disabled={crossValidating}
                      className="px-3 py-1.5 text-[10px] font-bold bg-[#f2a900] hover:bg-[#ffb800] text-black rounded transition-colors flex items-center gap-1.5 cursor-pointer"
                    >
                      {crossValidating ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
                      Run Cross-Validation
                    </button>
                  </div>

                  <CrossValidationView
                    data={crossValidationData}
                    qssDistances={result?.telemetry?.distances}
                    qssSpeedsKmh={result?.telemetry?.speeds_kmh}
                    dynDistances={result?.telemetry?.distances}
                    dynSpeedsKmh={result?.telemetry?.speeds_kmh}
                  />
                </div>
              )}
            </div>
          </>
        ) : (
          /* ── Empty State ── */
          <div className="flex-1 flex items-center justify-center p-8">
            <div className="max-w-[480px] text-center">
              <div className="w-16 h-16 rounded-2xl bg-[#f2a900]/8 border border-[#f2a900]/15
                flex items-center justify-center mx-auto mb-6">
                <Timer size={28} className="text-[#f2a900]/60" />
              </div>
              <h2 className="text-xl font-bold text-white mb-2">Quasi-Steady-State Lap Simulator</h2>
              <p className="text-[12px] text-gray-500 mb-6 leading-relaxed">
                4-wheel load transfer &middot; Combined-slip Pacejka tires &middot; GGV envelope
              </p>

              <div className="bg-[#0d0d0f] border border-[#1e1e20] rounded-2xl p-5 text-left mb-6">
                <p className="text-[10px] font-bold text-gray-600 uppercase tracking-wider mb-3">Model includes</p>
                <ul className="space-y-1.5">
                  {[
                    "Individual wheel loads — longitudinal + lateral load transfer",
                    "Per-wheel combined-slip Pacejka tire forces",
                    "GGV envelope pre-computation (40 speed × 20 ay points)",
                    "Powertrain — torque curve, 6-speed gear ratios, drivetrain loss",
                    "Aero map — front/rear balance, ride-height sensitivity",
                    "Brake bias — per-axle friction check",
                    "Power-limited terminal velocity (no hardcoded speed caps)",
                    "Track banking and elevation gradient",
                  ].map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-[10px] text-gray-500">
                      <CheckCircle size={10} className="text-[#f2a900]/50 mt-0.5 flex-shrink-0" />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>

              <p className="text-[11px] text-gray-600">
                Configure vehicle parameters in the left panel, then upload a GPX track or use a synthetic oval to begin.
              </p>

              {running && (
                <div className="mt-4 flex items-center justify-center gap-2 text-[#f2a900]">
                  <Loader2 size={14} className="animate-spin" />
                  <span className="text-[11px]">Building GGV envelope and running lap…</span>
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      {/* ── RIGHT PANEL ────────────────────────────────────────────────────── */}
      <aside aria-label="Session Information" className="w-[180px] flex-shrink-0 border-l border-[#1a1a1a] overflow-y-auto p-3 space-y-3 custom-scrollbar">
        <h2 className="text-[9px] font-bold text-gray-400 uppercase tracking-[0.16em]">Session Info</h2>

        {result ? (
          <>
            {/* Sector Times */}
            {result.sector_times_s.length > 0 && (
              <div>
                <p className="text-[9px] text-gray-700 mb-1.5 uppercase tracking-wider font-bold">Sectors</p>
                {result.sector_times_s.map((t, i) => (
                  <div key={i} className="flex justify-between items-center py-1 border-b border-[#111]">
                    <span className="text-[9px] text-gray-600">S{i + 1}</span>
                    <span className="text-[10px] font-bold text-white tabular-nums">{t.toFixed(3)}s</span>
                  </div>
                ))}
              </div>
            )}

            {/* Interactive 2D Circuit Map with Beacon */}
            {tel && (
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <p className="text-[9px] text-gray-700 uppercase tracking-wider font-bold">Track Map</p>
                  {hoverDist !== null && (
                    <span className="text-[8px] font-mono text-amber-400">{hoverDist.toFixed(0)}m</span>
                  )}
                </div>
                <div className="h-28 bg-[#0a0a0c] border border-[#1e1e22] rounded-lg relative overflow-hidden flex items-center justify-center p-2">
                  {result?.track_coordinates && result.track_coordinates.x?.length > 1 ? (
                    (() => {
                      const coords = result.track_coordinates;
                      const minX = Math.min(...coords.x);
                      const maxX = Math.max(...coords.x);
                      const minY = Math.min(...coords.y);
                      const maxY = Math.max(...coords.y);
                      const spanX = Math.max(maxX - minX, 1);
                      const spanY = Math.max(maxY - minY, 1);
                      const pad = 12;
                      const pts = coords.x.map((xVal, i) => {
                        const px = pad + ((xVal - minX) / spanX) * (180 - 2 * pad);
                        const py = 110 - (pad + ((coords.y[i] - minY) / spanY) * (110 - 2 * pad));
                        return `${px.toFixed(1)},${py.toFixed(1)}`;
                      });
                      const d = `M ${pts.join(" L ")} ${coords.is_closed ? "Z" : ""}`;

                      let bx = 90, by = 55;
                      if (hoverDist !== null && tel.distances.length > 0) {
                        let bestIdx = 0;
                        let minDiff = Infinity;
                        for (let i = 0; i < tel.distances.length; i++) {
                          const diff = Math.abs(tel.distances[i] - hoverDist);
                          if (diff < minDiff) {
                            minDiff = diff;
                            bestIdx = i;
                          }
                        }
                        if (bestIdx < coords.x.length) {
                          bx = pad + ((coords.x[bestIdx] - minX) / spanX) * (180 - 2 * pad);
                          by = 110 - (pad + ((coords.y[bestIdx] - minY) / spanY) * (110 - 2 * pad));
                        }
                      }

                      return (
                        <svg viewBox="0 0 180 110" className="w-full h-full">
                          <path d={d} fill="none" stroke="#222" strokeWidth="6" strokeLinecap="round" />
                          <path d={d} fill="none" stroke="#555" strokeWidth="2" strokeLinecap="round" />
                          {hoverDist !== null && (
                            <g>
                              <circle cx={bx} cy={by} r="6" fill="#f2a900" opacity="0.3" className="animate-ping" />
                              <circle cx={bx} cy={by} r="3.5" fill="#f2a900" stroke="#fff" strokeWidth="1" />
                            </g>
                          )}
                        </svg>
                      );
                    })()
                  ) : (
                    <svg viewBox="-120 -80 240 160" className="w-full h-full">
                      <path
                        d="M -60 -50 L 60 -50 A 50 50 0 0 1 60 50 L -60 50 A 50 50 0 0 1 -60 -50 Z"
                        fill="none"
                        stroke="#222"
                        strokeWidth="8"
                        strokeLinecap="round"
                      />
                      <path
                        d="M -60 -50 L 60 -50 A 50 50 0 0 1 60 50 L -60 50 A 50 50 0 0 1 -60 -50 Z"
                        fill="none"
                        stroke="#444"
                        strokeWidth="2"
                        strokeLinecap="round"
                      />
                      {hoverDist !== null && (
                        <circle cx={0} cy={-50} r="4" fill="#f2a900" stroke="#fff" strokeWidth="1" />
                      )}
                    </svg>
                  )}
                </div>
              </div>
            )}

            {/* Speed mini histogram */}
            {tel && (
              <div>
                <p className="text-[9px] text-gray-700 mb-1.5 uppercase tracking-wider font-bold">Speed Profile</p>
                <Plot
                  data={[{
                    x: tel.distances,
                    y: tel.speeds_kmh,
                    type: "scatter", mode: "lines",
                    line: { color: "#f2a900", width: 1 },
                    fill: "tozeroy",
                    fillcolor: "rgba(242,169,0,0.08)",
                  }]}
                  layout={{
                    paper_bgcolor: "transparent",
                    plot_bgcolor: "transparent",
                    xaxis: { visible: false },
                    yaxis: { visible: false },
                    margin: { l: 0, r: 0, t: 0, b: 0 },
                    height: 60,
                  } as Record<string, unknown>}
                  config={{ displayModeBar: false, staticPlot: true }}
                  style={{ width: "100%", height: 60 }}
                />
              </div>
            )}

            {/* Stats */}
            <div className="space-y-1.5">
              {[
                { label: "Model", value: result.model_version },
                { label: "Avg Power", value: `${result.avg_power_kw.toFixed(0)} kW` },
                { label: "Energy", value: `${result.energy_used_kj.toFixed(0)} kJ` },
                { label: "Terminal v", value: `${result.terminal_velocity_kmh.toFixed(0)} km/h` },
              ].map(({ label, value }) => (
                <div key={label} className="flex flex-col">
                  <span className="text-[8px] text-gray-700 uppercase tracking-wider">{label}</span>
                  <span className="text-[10px] text-gray-300 font-mono">{value}</span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="space-y-2">
            {[
              { icon: BarChart3, text: "GGV envelope" },
              { icon: Activity, text: "Speed trace" },
              { icon: Gauge, text: "Gear analysis" },
              { icon: Settings2, text: "Load transfer" },
            ].map(({ icon: Icon, text }) => (
              <div key={text} className="flex items-center gap-2">
                <Icon size={12} className="text-[#f2a900]" />
                <span className="text-[10px] text-gray-300 font-medium">{text}</span>
              </div>
            ))}
            <p className="text-[10px] text-gray-400 pt-2 font-mono">Run simulation to populate telemetry.</p>
          </div>
        )}
      </aside>
    </div>
  );
}

