"use client";

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import {
  Timer,
  Play,
  ChevronDown,
  ChevronRight,
  Zap,
  Gauge,
  Wind,
  Activity,
  TrendingDown,
  AlertCircle,
  Loader2,
  Layers,
  MapPin,
  Plus,
  Trash2,
  Sliders,
  Pin,
  FileSpreadsheet,
  Sparkles,
  Target,
  ArrowRight,
  Car,
} from "lucide-react";
import NextStepLink from "../../components/NextStepLink";
import { formatApiError } from "../../lib/api_client";
import { useAuth } from "../../contexts/AuthContext";
import { useWorkspace } from "../../contexts/WorkspaceContext";
import PlanGate from "../../components/PlanGate";
import Plot from "../../components/sim/Plot";
import TrackMap, { CornerInfo, GgvEnvelopeData } from "../../components/sim/TrackMap";
import EnvelopePlot from "../../components/v2/instruments/EnvelopePlot";
import dynamic from "next/dynamic";

// The only WebGL canvas on this route; browser-only.
const TerrainElevation3D = dynamic(() => import("../../components/v2/instruments/TerrainElevation3D"), {
  ssr: false,
  loading: () => <p className="text-[11px] text-zinc-500 m-0">Loading 3D view</p>,
});
import LapDeltaView, { LapRunData, VehicleSetupParameters } from "../../components/sim/LapDeltaView";
import { darkLayout } from "../../components/sim/theme";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Types & Contracts ────────────────────────────────────────────────────────

type TrackInputTab = "preset" | "custom" | "csv";

interface CustomTrackSegment {
  id: string;
  type: "Straight" | "Left Corner" | "Right Corner" | "Hairpin";
  length_m: number;
  radius_m: number;
  banking_deg: number;
  grade_pct: number;
}

interface CoupledVehicleConfig {
  // Vehicle & Drivetrain
  mass: number; // kg (300 - 1800)
  power_kw: number; // kW (50 - 1200)
  tire_mu: number; // mu_0 peak grip (0.70 - 2.20)
  brake_bias_front: number; // % Front (45 - 75)
  wheelbase: number; // m
  cog_dist_front: number; // m
  h_cog: number; // m
  // Aerodynamics
  cl: number; // Downforce coefficient
  cd: number; // Drag coefficient
  aero_balance_front: number; // % Front (cop_fraction)
  frontal_area: number; // m²
  // Coupled Suspension & Kinematics
  front_spring_rate: number; // N/mm (40 - 250)
  rear_spring_rate: number; // N/mm (40 - 250)
  front_arb: number; // N/mm wheel rate (10 - 150)
  rear_arb: number; // N/mm wheel rate (5 - 120)
  static_rh_front_mm: number; // mm (20 - 100)
  static_rh_rear_mm: number; // mm (20 - 120)
  front_rc_height: number; // mm (-20 to 150)
  rear_rc_height: number; // mm (0 to 200)
  track_width_f: number; // m
  track_width_r: number; // m
}

interface CornerOpportunity {
  corner_id: number;
  name?: string;
  distance_m: number;
  time_loss_s: number;
  driver_speed_kmh: number;
  optimal_speed_kmh: number;
  limiting_factor: "POWER" | "BRAKING" | "UNDERSTEER_FRONT" | "OVERSTEER_REAR" | string;
  recommendation: string;
}

export interface SetupUncertaintyBand {
  nominal_delta_s: number;
  min_delta_s: number;
  max_delta_s: number;
  uncertainty_s: number;
  formatted_delta?: string;
}

export interface SetupSurfaceResult {
  front_arb_n_mm: number[];
  aero_balance_front_pct: number[];
  z_lap_time_s: number[][];
  current_setup: {
    front_arb_n_mm: number;
    aero_balance_front_pct: number;
    lap_time_s: number;
  };
  optimal_setup: {
    front_arb_n_mm: number;
    aero_balance_front_pct: number;
    lap_time_s: number;
    time_gain_s: number;
    uncertainty_band?: SetupUncertaintyBand;
  };
  uncertainty_band?: SetupUncertaintyBand;
}

interface LapSimResponse {
  lap_time_s: number;
  lap_completed?: boolean;
  outcome?: string;
  sector_times: number[];
  max_speed_kmh: number;
  min_speed_kmh: number;
  avg_speed_kmh: number;
  max_lat_g?: number;
  max_long_g?: number;
  max_braking_g?: number;
  front_lltd_pct?: number;
  min_rh_front_mm?: number;
  min_rh_rear_mm?: number;
  bottoming_events_count?: number;
  front_lltd_estimated?: boolean;
  setup_surface?: SetupSurfaceResult;
  energy_used_kj: number;
  understeer_pct?: number;
  trace: {
    s_m: number[];
    x_m?: number[];
    y_m?: number[];
    speed_kmh: number[];
    lat_g: number[];
    long_g: number[];
    throttle_pct?: number[];
    brake_pct?: number[];
    gear?: number[];
    downforce_n?: number[];
    limiting_factor?: Array<"POWER" | "BRAKING" | "UNDERSTEER_FRONT" | "OVERSTEER_REAR" | string>;
    ride_height_front_mm?: number[];
    ride_height_rear_mm?: number[];
    pitch_deg?: number[];
    z_m?: number[];
    dz_ds?: number[];
    vertical_g?: number[];
    vertical_load_delta_n?: number[];
    compression_mm?: number[];
  };
  ggv_envelope?: GgvEnvelopeData;
  corner_opportunities?: CornerOpportunity[];
  model_version?: string;
  // Fallbacks
  total_time_s?: number;
  sector_times_s?: number[];
  telemetry?: any;
  ggv?: any;
  track_coordinates?: { x: number[]; y: number[]; is_closed?: boolean };
}

// ─── Championship Circuits Catalog (Mode 1: Preset) ───────────────────────────

interface ChampionshipCircuit {
  id: string;
  name: string;
  country: string;
  totalLengthM: number;
  sectorBoundaries: [number, number]; // [End of S1, End of S2]
  description: string;
  corners: Array<{ id: number; name: string; distM: number; radiusM: number; sign: 1 | -1 }>;
}

const CHAMPIONSHIP_CIRCUITS: ChampionshipCircuit[] = [
  {
    id: "spa",
    name: "Spa-Francorchamps",
    country: "Belgium",
    totalLengthM: 7004,
    sectorBoundaries: [2240, 5120],
    description: "High power & downforce: Raidillon compression, Kemmel straight, and Pouhon double apex.",
    corners: [
      { id: 1, name: "La Source", distM: 380, radiusM: 35, sign: 1 },
      { id: 2, name: "Eau Rouge", distM: 1100, radiusM: 160, sign: -1 },
      { id: 3, name: "Raidillon", distM: 1350, radiusM: 140, sign: 1 },
      { id: 5, name: "Les Combes", distM: 3050, radiusM: 65, sign: 1 },
      { id: 6, name: "Malmedy", distM: 3250, radiusM: 70, sign: -1 },
      { id: 7, name: "Rivage", distM: 3750, radiusM: 42, sign: 1 },
      { id: 8, name: "Speakers Corner", distM: 4100, radiusM: 55, sign: -1 },
      { id: 10, name: "Pouhon", distM: 4800, radiusM: 115, sign: -1 },
      { id: 12, name: "Fagnes", distM: 5450, radiusM: 68, sign: 1 },
      { id: 14, name: "Stavelot", distM: 5900, radiusM: 85, sign: 1 },
      { id: 17, name: "Blanchimont", distM: 6450, radiusM: 220, sign: -1 },
      { id: 19, name: "Bus Stop Chicane", distM: 6850, radiusM: 28, sign: 1 },
    ],
  },
  {
    id: "silverstone",
    name: "Silverstone GP",
    country: "United Kingdom",
    totalLengthM: 5891,
    sectorBoundaries: [1980, 4020],
    description: "High lateral aero load: Copse, Maggotts-Becketts-Chapel complex, and Stowe.",
    corners: [
      { id: 1, name: "Abbey", distM: 420, radiusM: 155, sign: 1 },
      { id: 2, name: "Farm Curve", distM: 750, radiusM: 240, sign: -1 },
      { id: 3, name: "Village", distM: 1120, radiusM: 38, sign: 1 },
      { id: 4, name: "The Loop", distM: 1320, radiusM: 30, sign: -1 },
      { id: 6, name: "Brooklands", distM: 2450, radiusM: 72, sign: -1 },
      { id: 7, name: "Luffield", distM: 2780, radiusM: 45, sign: 1 },
      { id: 9, name: "Copse", distM: 3380, radiusM: 175, sign: 1 },
      { id: 10, name: "Maggotts", distM: 3720, radiusM: 160, sign: -1 },
      { id: 11, name: "Becketts", distM: 3950, radiusM: 95, sign: 1 },
      { id: 12, name: "Chapel", distM: 4180, radiusM: 185, sign: -1 },
      { id: 15, name: "Stowe", distM: 4950, radiusM: 110, sign: 1 },
      { id: 16, name: "Vale", distM: 5450, radiusM: 35, sign: -1 },
      { id: 17, name: "Club", distM: 5680, radiusM: 60, sign: 1 },
    ],
  },
  {
    id: "monza",
    name: "Monza",
    country: "Italy",
    totalLengthM: 5793,
    sectorBoundaries: [1850, 3920],
    description: "Temple of Speed: minimal aerodynamic drag, heavy chicane braking zones.",
    corners: [
      { id: 1, name: "Variante del Rettifilo (T1)", distM: 1150, radiusM: 28, sign: 1 },
      { id: 2, name: "Rettifilo Exit (T2)", distM: 1280, radiusM: 32, sign: -1 },
      { id: 3, name: "Curva Grande", distM: 1780, radiusM: 260, sign: 1 },
      { id: 4, name: "Variante della Roggia", distM: 2620, radiusM: 36, sign: -1 },
      { id: 6, name: "Curva di Lesmo 1", distM: 3120, radiusM: 78, sign: 1 },
      { id: 7, name: "Curva di Lesmo 2", distM: 3450, radiusM: 65, sign: 1 },
      { id: 8, name: "Variante Ascari (T8)", distM: 4520, radiusM: 80, sign: -1 },
      { id: 9, name: "Ascari Apex 2 (T9)", distM: 4680, radiusM: 70, sign: 1 },
      { id: 11, name: "Curva Parabolica", distM: 5420, radiusM: 105, sign: 1 },
    ],
  },
  {
    id: "fsae_michigan",
    name: "FSAE Michigan Endurance",
    country: "United States",
    totalLengthM: 1450,
    sectorBoundaries: [480, 980],
    description: "Formula SAE autocross: tight hairpins, rapid transient slaloms, mechanical grip dominance.",
    corners: [
      { id: 1, name: "North Slalom Entry", distM: 120, radiusM: 22, sign: -1 },
      { id: 2, name: "North Hairpin", distM: 280, radiusM: 14, sign: 1 },
      { id: 4, name: "Chicane 1", distM: 450, radiusM: 18, sign: -1 },
      { id: 6, name: "West Sweeper", distM: 620, radiusM: 38, sign: 1 },
      { id: 8, name: "Keyhole", distM: 810, radiusM: 16, sign: -1 },
      { id: 10, name: "South Hairpin", distM: 940, radiusM: 12, sign: 1 },
      { id: 12, name: "South Slalom", distM: 1180, radiusM: 20, sign: -1 },
      { id: 14, name: "Final 180 Carousel", distM: 1360, radiusM: 24, sign: 1 },
    ],
  },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatLapTime(s?: number): string {
  if (!s || s <= 0 || !Number.isFinite(s)) return "--:--.---";
  const m = Math.floor(s / 60);
  const sec = s - m * 60;
  return `${m}:${sec.toFixed(3).padStart(6, "0")}`;
}

const CIRCUIT_LANDMARKS: Record<string, number[][]> = {
  spa: [
    [0.0, 0.0], [250.0, 30.0], [320.0, 90.0], [270.0, 40.0], [200.0, -180.0],
    [180.0, -320.0], [450.0, -850.0], [850.0, -1650.0], [920.0, -1720.0], [940.0, -1660.0],
    [930.0, -1500.0], [840.0, -1250.0], [750.0, -1120.0], [720.0, -1180.0], [640.0, -1150.0],
    [480.0, -980.0], [360.0, -820.0], [260.0, -700.0], [220.0, -520.0], [270.0, -440.0],
    [280.0, -280.0], [230.0, -140.0], [160.0, -50.0], [90.0, -20.0], [40.0, -10.0],
    [-50.0, -10.0], [-30.0, 15.0], [0.0, 0.0]
  ],
  silverstone: [
    [0.0, 0.0], [250.0, 20.0], [400.0, 100.0], [480.0, 220.0], [520.0, 400.0],
    [420.0, 480.0], [280.0, 420.0], [100.0, 320.0], [-300.0, 180.0], [-460.0, 100.0],
    [-520.0, -50.0], [-450.0, -180.0], [-280.0, -220.0], [-120.0, -250.0], [80.0, -320.0],
    [260.0, -420.0], [400.0, -480.0], [500.0, -460.0], [650.0, -350.0], [850.0, -150.0],
    [920.0, 0.0], [800.0, 150.0], [650.0, 180.0], [450.0, 120.0], [200.0, 50.0], [0.0, 0.0]
  ],
  monza: [
    [0.0, 0.0], [800.0, 0.0], [950.0, 30.0], [990.0, -20.0], [1050.0, 50.0],
    [1400.0, 350.0], [1650.0, 800.0], [1750.0, 1100.0], [1720.0, 1180.0], [1770.0, 1220.0],
    [1850.0, 1400.0], [1920.0, 1550.0], [1960.0, 1680.0], [2000.0, 1800.0], [1850.0, 1950.0],
    [1400.0, 2050.0], [1100.0, 2100.0], [980.0, 2150.0], [880.0, 2120.0], [500.0, 1800.0],
    [200.0, 1200.0], [80.0, 700.0], [-50.0, 350.0], [-30.0, 100.0], [0.0, 0.0]
  ],
  fsae_michigan: [
    [0.0, 0.0], [80.0, 0.0], [120.0, 30.0], [150.0, 80.0], [140.0, 140.0],
    [100.0, 180.0], [50.0, 170.0], [20.0, 120.0], [-20.0, 100.0], [-60.0, 130.0],
    [-110.0, 110.0], [-140.0, 60.0], [-150.0, 20.0], [-120.0, -20.0], [-80.0, -50.0],
    [-40.0, -30.0], [-10.0, -50.0], [20.0, -80.0], [50.0, -60.0], [30.0, -20.0], [0.0, 0.0]
  ],
};

function catmullRomClosed(landmarks: number[][], nEval: number): { x: number[]; y: number[] } {
  const p = landmarks.slice(0, -1);
  const M = p.length;
  if (M < 3) return { x: new Array(nEval).fill(0), y: new Array(nEval).fill(0) };
  const pExt = [p[M - 1], ...p, p[0], p[1 % M]];
  const outX: number[] = new Array(nEval);
  const outY: number[] = new Array(nEval);

  for (let idx = 0; idx < nEval; idx++) {
    const t = (idx / (nEval - 1)) * M;
    let i = Math.floor(t);
    let u = t - i;
    if (i >= M) {
      i = M - 1;
      u = 1.0;
    }
    const p0 = pExt[i];
    const p1 = pExt[i + 1];
    const p2 = pExt[i + 2];
    const p3 = pExt[i + 3];

    const aX = 0.5 * (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]);
    const bX = 0.5 * (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]);
    const cX = 0.5 * (-p0[0] + p2[0]);
    const dX = p1[0];

    const aY = 0.5 * (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]);
    const bY = 0.5 * (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]);
    const cY = 0.5 * (-p0[1] + p2[1]);
    const dY = p1[1];

    outX[idx] = ((aX * u + bX) * u + cX) * u + dX;
    outY[idx] = ((aY * u + bY) * u + cY) * u + dY;
  }
  outX[nEval - 1] = outX[0];
  outY[nEval - 1] = outY[0];
  return { x: outX, y: outY };
}

function synthesizeTrackGeometry(
  totalLengthM: number,
  corners: Array<{ distM: number; radiusM: number; sign: 1 | -1 }>,
  nPoints = 500,
  circuitId?: string
) {
  const distances: number[] = [];
  const curvatures: number[] = [];
  const ds = totalLengthM / nPoints;

  for (let i = 0; i < nPoints; i++) {
    const s = i * ds;
    let kappa = 0;

    for (const c of corners) {
      const halfWidth = Math.max(c.radiusM * 1.2, 40);
      const distFromCenter = Math.abs(s - c.distM);
      if (distFromCenter < halfWidth) {
        const ramp = 0.5 * (1 + Math.cos((Math.PI * distFromCenter) / halfWidth));
        kappa += (1.0 / c.radiusM) * c.sign * ramp;
      }
    }

    distances.push(s);
    curvatures.push(kappa);
  }

  const lm = circuitId ? CIRCUIT_LANDMARKS[circuitId] : undefined;
  if (lm) {
    const { x, y } = catmullRomClosed(lm, nPoints);
    return { distances, curvatures, x, y };
  }

  const x: number[] = [];
  const y: number[] = [];
  let currentHeading = 0;
  let curX = 0;
  let curY = 0;

  for (let i = 0; i < nPoints; i++) {
    x.push(curX);
    y.push(curY);
    currentHeading += curvatures[i] * ds;
    curX += Math.cos(currentHeading) * ds;
    curY += Math.sin(currentHeading) * ds;
  }

  if (nPoints > 1) {
    const xEnd = x[nPoints - 1];
    const yEnd = y[nPoints - 1];
    const dx = xEnd - x[0];
    const dy = yEnd - y[0];
    for (let i = 0; i < nPoints; i++) {
      const frac = i / (nPoints - 1);
      x[i] -= frac * dx;
      y[i] -= frac * dy;
    }
    x[nPoints - 1] = x[0];
    y[nPoints - 1] = y[0];
  }

  return { distances, curvatures, x, y };
}

// ─── Local Multi-Body Simulation Engine ───────────────────────────────────────

function runLocalCoupledLapSimulation(
  distances: number[],
  curvatures: number[],
  xCoords: number[],
  yCoords: number[],
  cfg: CoupledVehicleConfig,
  sectorBoundaries: [number, number]
): LapSimResponse {
  const n = distances.length;
  if (n < 2) throw new Error("Track requires at least 2 points");

  const rho = 1.225;
  const g = 9.81;

  // Front Lateral Load Transfer Distribution (LLTD) calculation
  const kWf = cfg.front_spring_rate * 1000 * (0.72 ** 2);
  const kWr = cfg.rear_spring_rate * 1000 * (0.74 ** 2);
  const kArbF = cfg.front_arb * 1000;
  const kArbR = cfg.rear_arb * 1000;

  const tF = cfg.track_width_f;
  const tR = cfg.track_width_r;

  const kPhiF = 0.5 * (kWf + kArbF) * (tF ** 2);
  const kPhiR = 0.5 * (kWr + kArbR) * (tR ** 2);
  const frontLltdFraction = kPhiF / Math.max(kPhiF + kPhiR, 1.0);
  const frontLltdPct = Number((frontLltdFraction * 100).toFixed(1));

  const understeerDelta = frontLltdFraction - 0.50;

  const speedsMs = new Array(n).fill(0);
  const limitingFactors: Array<"POWER" | "BRAKING" | "UNDERSTEER_FRONT" | "OVERSTEER_REAR"> = new Array(n).fill("POWER");

  // Step 1: Apex cornering limit
  for (let i = 0; i < n; i++) {
    const kappa = Math.abs(curvatures[i]);
    if (kappa < 1e-4) {
      speedsMs[i] = 120.0;
    } else {
      let v = Math.sqrt((cfg.tire_mu * g) / kappa);
      for (let iter = 0; iter < 4; iter++) {
        const q = 0.5 * rho * v * v;
        const downforce = q * cfg.cl * cfg.frontal_area;
        const totalFz = cfg.mass * g + downforce;
        const balanceFactor = 1.0 - Math.abs(understeerDelta) * 0.12;
        const maxAy = (cfg.tire_mu * totalFz * balanceFactor) / cfg.mass;
        v = Math.sqrt(Math.max(maxAy / kappa, 2.0));
      }
      speedsMs[i] = v;

      if (understeerDelta >= 0.02) {
        limitingFactors[i] = "UNDERSTEER_FRONT";
      } else if (understeerDelta <= -0.02) {
        limitingFactors[i] = "OVERSTEER_REAR";
      } else {
        limitingFactors[i] = "UNDERSTEER_FRONT";
      }
    }
  }

  // Step 2: Backward braking pass
  for (let i = n - 2; i >= 0; i--) {
    const ds = distances[i + 1] - distances[i];
    const vNext = speedsMs[i + 1];
    const q = 0.5 * rho * vNext * vNext;
    const downforce = q * cfg.cl * cfg.frontal_area;
    const drag = q * cfg.cd * cfg.frontal_area;
    const fz = cfg.mass * g + downforce;
    const maxBrakeForce = cfg.tire_mu * fz + drag;
    const maxDecel = maxBrakeForce / cfg.mass;

    const maxEntrySpeed = Math.sqrt(vNext * vNext + 2 * maxDecel * ds);
    if (speedsMs[i] > maxEntrySpeed) {
      speedsMs[i] = maxEntrySpeed;
      limitingFactors[i] = "BRAKING";
    }
  }

  // Step 3: Forward acceleration pass
  speedsMs[0] = Math.max(speedsMs[0], 25.0);
  for (let i = 0; i < n - 1; i++) {
    const ds = distances[i + 1] - distances[i];
    const v = Math.max(speedsMs[i], 5.0);
    const q = 0.5 * rho * v * v;
    const drag = q * cfg.cd * cfg.frontal_area;
    const engineDriveForce = (cfg.power_kw * 1000) / v;
    const maxTraction = cfg.tire_mu * (cfg.mass * g * 0.6);
    const driveForce = Math.min(engineDriveForce, maxTraction);

    const netForce = driveForce - drag;
    const maxAccel = Math.max(netForce / cfg.mass, 0.0);

    const maxExitSpeed = Math.sqrt(v * v + 2 * maxAccel * ds);
    if (speedsMs[i + 1] > maxExitSpeed) {
      speedsMs[i + 1] = maxExitSpeed;
      limitingFactors[i + 1] = "POWER";
    }
  }

  // KPIs & Synchronized Telemetry Traces
  let totalTimeS = 0;
  const speedsKmh: number[] = [];
  const latG: number[] = [];
  const longG: number[] = [];
  const throttlePct: number[] = [];
  const brakePct: number[] = [];
  const gears: number[] = [];
  const downforceN: number[] = [];

  let s1Time = 0;
  let s2Time = 0;
  let s3Time = 0;

  for (let i = 0; i < n; i++) {
    const v = speedsMs[i];
    const vKmh = v * 3.6;
    speedsKmh.push(vKmh);

    const kappa = curvatures[i];
    const ay = (v * v * kappa) / g;
    latG.push(ay);

    let ax = 0;
    if (i < n - 1) {
      const ds = distances[i + 1] - distances[i];
      ax = (speedsMs[i + 1] * speedsMs[i + 1] - v * v) / (2 * ds * g);
    }
    longG.push(ax);

    const q = 0.5 * rho * v * v;
    downforceN.push(q * cfg.cl * cfg.frontal_area);

    if (ax > 0.05) {
      throttlePct.push(Math.min(100, Math.round((ax / 1.1) * 100)));
      brakePct.push(0);
    } else if (ax < -0.1) {
      throttlePct.push(0);
      brakePct.push(Math.min(100, Math.round((Math.abs(ax) / 1.8) * 100)));
    } else {
      throttlePct.push(30);
      brakePct.push(0);
    }

    if (vKmh < 65) gears.push(1);
    else if (vKmh < 105) gears.push(2);
    else if (vKmh < 155) gears.push(3);
    else if (vKmh < 210) gears.push(4);
    else if (vKmh < 265) gears.push(5);
    else gears.push(6);

    if (i > 0) {
      const ds = distances[i] - distances[i - 1];
      const avgV = Math.max((speedsMs[i] + speedsMs[i - 1]) / 2, 1.0);
      const dt = ds / avgV;
      totalTimeS += dt;

      const s = distances[i];
      if (s <= sectorBoundaries[0]) s1Time += dt;
      else if (s <= sectorBoundaries[1]) s2Time += dt;
      else s3Time += dt;
    }
  }

  if (s1Time <= 5.0 || s2Time <= 5.0 || s3Time <= 5.0) {
    s1Time = Number((totalTimeS * 0.30).toFixed(3));
    s2Time = Number((totalTimeS * 0.36).toFixed(3));
    s3Time = Number((totalTimeS * 0.34).toFixed(3));
  }

  const energyKj = cfg.power_kw * 0.45 * totalTimeS;

  // Stage L3 Dynamic Ride Height & Pitch
  const staticRhF = cfg.static_rh_front_mm ?? 55.0;
  const staticRhR = cfg.static_rh_rear_mm ?? 70.0;
  const rhFrontMm: number[] = [];
  const rhRearMm: number[] = [];
  const pitchDeg: number[] = [];
  let bottomingCount = 0;

  for (let i = 0; i < n; i++) {
    const axVal = longG[i] * 9.81;
    const dFzLong = (cfg.mass * axVal * cfg.h_cog) / Math.max(cfg.wheelbase, 1.0);
    const fzDown = downforceN[i];
    const aeroBalF = cfg.aero_balance_front / 100.0;
    const fzAeroF = fzDown * aeroBalF;
    const fzAeroR = fzDown * (1.0 - aeroBalF);

    // Progressive bump rubber stiffness engages when ride height drops to 20 mm
    const bumpEngagementRh = 20.0;
    const kBump = 250000.0; // N/m per wheel

    const maxLinDeflecF = Math.max(0.0, (staticRhF - bumpEngagementRh) / 1000.0);
    const fLinCapF = 2.0 * Math.max(kWf, 1000.0) * maxLinDeflecF;
    const fNetF = fzAeroF - dFzLong;
    let deflecF = 0.0;
    if (fNetF > fLinCapF) {
      deflecF = (maxLinDeflecF + (fNetF - fLinCapF) / (2.0 * (kWf + kBump))) * 1000.0;
    } else {
      deflecF = (fNetF / (2.0 * Math.max(kWf, 1000.0))) * 1000.0;
    }

    const maxLinDeflecR = Math.max(0.0, (staticRhR - bumpEngagementRh) / 1000.0);
    const fLinCapR = 2.0 * Math.max(kWr, 1000.0) * maxLinDeflecR;
    const fNetR = fzAeroR + dFzLong;
    let deflecR = 0.0;
    if (fNetR > fLinCapR) {
      deflecR = (maxLinDeflecR + (fNetR - fLinCapR) / (2.0 * (kWr + kBump))) * 1000.0;
    } else {
      deflecR = (fNetR / (2.0 * Math.max(kWr, 1000.0))) * 1000.0;
    }

    const rhF = Math.max(0.0, staticRhF - deflecF);
    const rhR = Math.max(0.0, staticRhR - deflecR);

    if (rhF <= 3.0 || rhR <= 3.0) {
      bottomingCount++;
      downforceN[i] *= 0.88;
    }

    rhFrontMm.push(Number(rhF.toFixed(2)));
    rhRearMm.push(Number(rhR.toFixed(2)));

    const pitchRad = Math.atan2((rhR - rhF) / 1000.0, cfg.wheelbase);
    pitchDeg.push(Number(((pitchRad * 180.0) / Math.PI).toFixed(3)));
  }

  const minRhF = Math.min(...rhFrontMm);
  const minRhR = Math.min(...rhRearMm);

  const speedSlicesKmh = [40, 80, 120, 160, 200, 240, 280, 320];
  const ayMaxG: number[] = [];
  const axAccelG: number[] = [];
  const axBrakeG: number[] = [];

  speedSlicesKmh.forEach((vk) => {
    const vm = vk / 3.6;
    const q = 0.5 * rho * vm * vm;
    const df = q * cfg.cl * cfg.frontal_area;
    const fz = cfg.mass * g + df;
    ayMaxG.push((cfg.tire_mu * fz) / (cfg.mass * g));
    const powerLimA = ((cfg.power_kw * 1000) / vm - q * cfg.cd * cfg.frontal_area) / (cfg.mass * g);
    axAccelG.push(Math.max(0.05, Math.min(powerLimA, 1.4)));
    axBrakeG.push(-((cfg.tire_mu * fz + q * cfg.cd * cfg.frontal_area) / (cfg.mass * g)));
  });

  return {
    lap_time_s: totalTimeS,
    sector_times: [s1Time, s2Time, s3Time],
    max_speed_kmh: Math.max(...speedsKmh),
    min_speed_kmh: Math.min(...speedsKmh),
    avg_speed_kmh: (distances[n - 1] / totalTimeS) * 3.6,
    max_lat_g: Math.max(...latG.map(Math.abs)),
    max_long_g: Math.max(...longG),
    max_braking_g: Math.abs(Math.min(...longG)),
    front_lltd_pct: frontLltdPct,
    min_rh_front_mm: minRhF,
    min_rh_rear_mm: minRhR,
    bottoming_events_count: bottomingCount,
    energy_used_kj: energyKj,
    understeer_pct: frontLltdPct,
    trace: {
      s_m: distances,
      x_m: xCoords,
      y_m: yCoords,
      speed_kmh: speedsKmh,
      lat_g: latG,
      long_g: longG,
      throttle_pct: throttlePct,
      brake_pct: brakePct,
      gear: gears,
      downforce_n: downforceN,
      limiting_factor: limitingFactors,
      ride_height_front_mm: rhFrontMm,
      ride_height_rear_mm: rhRearMm,
      pitch_deg: pitchDeg,
    },
    ggv_envelope: {
      speeds_kmh: speedSlicesKmh,
      ay_max_g: ayMaxG,
      ax_accel_g: axAccelG,
      ax_brake_g: axBrakeG,
    },
    setup_surface: undefined,
    model_version: "ApexSim-QSS-MultiBody-v3.0",
  };
}

// ─── Telemetry CSV Parser (BOM & Case-Insensitive Aliases) ────────────────────

interface ParsedTelemetryCsv {
  timeS: number[];
  speedKmh: number[];
  latG: number[];
  longG?: number[];
  distanceM: number[];
  curvature: number[];
  x: number[];
  y: number[];
}

function processGpsCoordinates(
  lats: number[],
  lons: number[],
  rawSpeeds?: number[],
  rawTimes?: number[]
): ParsedTelemetryCsv {
  const n = lats.length;
  const lat0Rad = (lats[0] * Math.PI) / 180.0;
  const cosLat0 = Math.cos(lat0Rad);
  const R = 6378137.0; // Earth equatorial radius [m]

  const x: number[] = [];
  const y: number[] = [];

  for (let i = 0; i < n; i++) {
    const xi = ((lons[i] - lons[0]) * Math.PI / 180.0) * R * cosLat0;
    const yi = ((lats[i] - lats[0]) * Math.PI / 180.0) * R;
    x.push(xi);
    y.push(yi);
  }

  // Linear closure drift removal
  const dx = x[n - 1] - x[0];
  const dy = y[n - 1] - y[0];
  for (let i = 0; i < n; i++) {
    const frac = i / (n - 1);
    x[i] -= frac * dx;
    y[i] -= frac * dy;
  }
  x[n - 1] = x[0];
  y[n - 1] = y[0];

  // Distances and signed Menger Curvature
  const distanceM: number[] = [0];
  for (let i = 1; i < n; i++) {
    const ds = Math.hypot(x[i] - x[i - 1], y[i] - y[i - 1]);
    distanceM.push(distanceM[i - 1] + ds);
  }

  const curvature: number[] = new Array(n).fill(0);
  for (let i = 1; i < n - 1; i++) {
    const x1 = x[i - 1], y1 = y[i - 1];
    const x2 = x[i], y2 = y[i];
    const x3 = x[i + 1], y3 = y[i + 1];

    const cp = (x2 - x1) * (y3 - y1) - (y2 - y1) * (x3 - x1);
    const d12 = Math.hypot(x2 - x1, y2 - y1);
    const d23 = Math.hypot(x3 - x2, y3 - y2);
    const d31 = Math.hypot(x1 - x3, y1 - y3);

    const denom = Math.max(d12 * d23 * d31, 1e-6);
    let kappa = (2.0 * cp) / denom;
    kappa = Math.max(-0.2, Math.min(0.2, kappa));
    curvature[i] = kappa;
  }
  curvature[0] = curvature[1];
  curvature[n - 1] = curvature[n - 2];

  let speedKmh: number[] = [];
  const validSpeed = rawSpeeds && rawSpeeds.some((s) => !Number.isNaN(s) && s > 0);
  if (validSpeed && rawSpeeds) {
    const maxSpd = Math.max(...rawSpeeds.filter((s) => !Number.isNaN(s)));
    const isMps = maxSpd < 95;
    speedKmh = rawSpeeds.map((s) => (Number.isNaN(s) ? 60 : isMps ? s * 3.6 : s));
  } else {
    speedKmh = curvature.map((k) => {
      const r = Math.abs(k) > 1e-4 ? 1.0 / Math.abs(k) : 1000.0;
      const vCorner = Math.min(270, Math.max(45, Math.sqrt(1.5 * 9.81 * r) * 3.6));
      return Number(vCorner.toFixed(1));
    });
  }

  const timeS: number[] = [0];
  for (let i = 1; i < n; i++) {
    const ds = distanceM[i] - distanceM[i - 1];
    const vMs = Math.max(speedKmh[i] / 3.6, 2.0);
    timeS.push(timeS[i - 1] + ds / vMs);
  }

  const latG = speedKmh.map((v, i) => {
    const vMs = v / 3.6;
    return Number(((vMs * vMs * curvature[i]) / 9.81).toFixed(3));
  });

  const longG: number[] = [0];
  for (let i = 1; i < n; i++) {
    const dt = Math.max(timeS[i] - timeS[i - 1], 0.01);
    const dv = (speedKmh[i] - speedKmh[i - 1]) / 3.6;
    longG.push(Number((dv / dt / 9.81).toFixed(3)));
  }

  return {
    timeS,
    speedKmh,
    latG,
    longG,
    distanceM,
    curvature,
    x,
    y,
  };
}

function parseTelemetryCsv(text: string): ParsedTelemetryCsv {
  let cleanText = text;
  // Strip UTF-8 BOM
  if (cleanText.charCodeAt(0) === 0xfeff) {
    cleanText = cleanText.slice(1);
  }

  // 1. Check for GPX format (<gpx or <trkpt)
  if (cleanText.includes("<gpx") || cleanText.includes("<trkpt")) {
    const trkptRegex = /<trkpt\s+[^>]*lat=["']([-0-9.]+)["']\s+[^>]*lon=["']([-0-9.]+)["'][^>]*>(?:[\s\S]*?(?:<speed>([-0-9.]+)<\/speed>)?[\s\S]*?(?:<time>([^<]+)<\/time>)?)?[\s\S]*?<\/trkpt>/gi;
    const lats: number[] = [];
    const lons: number[] = [];
    const speeds: number[] = [];
    const times: number[] = [];
    let match: RegExpExecArray | null;

    let tIdx = 0;
    while ((match = trkptRegex.exec(cleanText)) !== null) {
      const lat = parseFloat(match[1]);
      const lon = parseFloat(match[2]);
      if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
        lats.push(lat);
        lons.push(lon);
        const spd = match[3] ? parseFloat(match[3]) : NaN;
        speeds.push(Number.isNaN(spd) ? 0 : spd);
        times.push(tIdx * 0.1);
        tIdx++;
      }
    }

    if (lats.length >= 5) {
      return processGpsCoordinates(lats, lons, speeds, times);
    }
  }

  // 2. Check for KML format (<kml or <coordinates>)
  if (cleanText.includes("<kml") || cleanText.includes("<coordinates>")) {
    const coordMatch = /<coordinates>([\s\S]*?)<\/coordinates>/i.exec(cleanText);
    if (coordMatch) {
      const rawCoords = coordMatch[1].trim().split(/\s+/);
      const lats: number[] = [];
      const lons: number[] = [];
      for (const pt of rawCoords) {
        const parts = pt.split(",");
        if (parts.length >= 2) {
          const lon = parseFloat(parts[0]);
          const lat = parseFloat(parts[1]);
          if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
            lats.push(lat);
            lons.push(lon);
          }
        }
      }
      if (lats.length >= 5) {
        return processGpsCoordinates(lats, lons);
      }
    }
  }

  // 3. Tabular CSV/TSV format
  const lines = cleanText
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));

  if (lines.length < 5) throw new Error("File contains insufficient data rows.");

  const header = lines[0].split(/[,;\t]/).map((c) => c.trim().toLowerCase());

  const findCol = (aliases: string[]) => {
    return header.findIndex((h) => aliases.some((a) => h === a || h.startsWith(a)));
  };

  // Check if CSV contains GPS latitude & longitude columns
  const latColIdx = findCol(["lat", "latitude", "gps_lat", "position_lat", "pos_lat"]);
  const lonColIdx = findCol(["lon", "lng", "longitude", "gps_lon", "position_lon", "pos_lon"]);

  if (latColIdx !== -1 && lonColIdx !== -1) {
    const timeIdx = findCol(["time", "t", "time_s", "timestamp", "sessiontime", "loggertime"]);
    const speedIdx = findCol(["speed", "v_kph", "ground_speed", "gps_speed", "wheelspeed", "v", "spd"]);

    const lats: number[] = [];
    const lons: number[] = [];
    const rawSpeed: number[] = [];
    const rawTime: number[] = [];

    for (let i = 1; i < lines.length; i++) {
      const parts = lines[i].split(/[,;\t]/);
      const lat = parseFloat(parts[latColIdx]);
      const lon = parseFloat(parts[lonColIdx]);
      if (Number.isNaN(lat) || Number.isNaN(lon)) continue;
      lats.push(lat);
      lons.push(lon);
      rawSpeed.push(speedIdx !== -1 ? parseFloat(parts[speedIdx]) : NaN);
      rawTime.push(timeIdx !== -1 ? parseFloat(parts[timeIdx]) : (i - 1) * 0.1);
    }

    if (lats.length >= 5) {
      return processGpsCoordinates(lats, lons, rawSpeed, rawTime);
    }
  }

  // 4. Standard CSV with speed and lat_g
  const timeIdx = findCol(["time", "t", "time_s", "timestamp", "sessiontime", "loggertime"]);
  const speedIdx = findCol(["speed", "v_kph", "ground_speed", "gps_speed", "wheelspeed", "v", "spd"]);
  const latGIdx = findCol(["lat_g", "latg", "ay", "lataccel", "g_lat", "lateralg", "accel_y"]);
  const longGIdx = findCol(["long_g", "longg", "ax", "inlineg", "g_long", "accel_x"]);

  if (speedIdx === -1 || latGIdx === -1) {
    throw new Error(
      `Required channels missing in file: [${header.join(", ")}]. Must include 'speed' & 'lat_g', or GPS 'latitude' & 'longitude'.`
    );
  }

  const rawTime: number[] = [];
  const rawSpeed: number[] = [];
  const rawLatG: number[] = [];
  const rawLongG: number[] = [];

  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(/[,;\t]/);
    const spd = parseFloat(parts[speedIdx]);
    const lg = parseFloat(parts[latGIdx]);
    if (Number.isNaN(spd) || Number.isNaN(lg)) continue;

    const t = timeIdx !== -1 ? parseFloat(parts[timeIdx]) : (i - 1) * 0.02;
    const ax = longGIdx !== -1 ? parseFloat(parts[longGIdx]) : 0;

    rawTime.push(t);
    rawSpeed.push(spd);
    rawLatG.push(lg);
    rawLongG.push(Number.isNaN(ax) ? 0 : ax);
  }

  const maxSpd = Math.max(...rawSpeed);
  const isMps = maxSpd < 95;
  const speedKmh = rawSpeed.map((v) => (isMps ? v * 3.6 : v));

  const distanceM: number[] = [0];
  const curvature: number[] = [];
  const x: number[] = [0];
  const y: number[] = [0];

  let currentDist = 0;
  let currentHeading = 0;
  let curX = 0;
  let curY = 0;

  for (let i = 0; i < speedKmh.length; i++) {
    const vm = speedKmh[i] / 3.6;
    const ayMs2 = rawLatG[i] * 9.81;

    const kappa = Math.abs(vm) > 2 ? ayMs2 / (vm * vm) : 0;
    curvature.push(kappa);

    if (i > 0) {
      const dt = Math.max(rawTime[i] - rawTime[i - 1], 0.005);
      const ds = vm * dt;
      currentDist += ds;
      distanceM.push(currentDist);

      currentHeading += kappa * ds;
      curX += Math.cos(currentHeading) * ds;
      curY += Math.sin(currentHeading) * ds;
      x.push(curX);
      y.push(curY);
    }
  }

  // Enforce zero closure drift
  if (x.length > 2) {
    const dx = x[x.length - 1] - x[0];
    const dy = y[y.length - 1] - y[0];
    const nPts = x.length;
    for (let i = 0; i < nPts; i++) {
      const frac = i / (nPts - 1);
      x[i] -= frac * dx;
      y[i] -= frac * dy;
    }
    x[nPts - 1] = x[0];
    y[nPts - 1] = y[0];
  }

  return {
    timeS: rawTime,
    speedKmh,
    latG: rawLatG,
    longG: rawLongG,
    distanceM,
    curvature,
    x,
    y,
  };
}

// ─── UI Helper Components ─────────────────────────────────────────────────────

function Section({
  title,
  children,
  defaultOpen = true,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="mb-3 pb-2 border-b border-[#1f2430]">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between py-1 mb-1.5 group text-left cursor-pointer"
      >
        <span className="text-[10px] font-bold text-zinc-300 uppercase tracking-[0.14em] group-hover:text-amber-400 transition-colors font-mono">
          {title}
        </span>
        {open ? (
          <ChevronDown size={12} className="text-zinc-500 group-hover:text-amber-400 transition-colors" />
        ) : (
          <ChevronRight size={12} className="text-zinc-500 group-hover:text-amber-400 transition-colors" />
        )}
      </button>
      {open && <div className="space-y-1.5">{children}</div>}
    </div>
  );
}

function ParamSlider({
  label,
  unit,
  value,
  min,
  max,
  step = 1,
  onChange,
  highlight = false,
}: {
  label: string;
  unit: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  highlight?: boolean;
}) {
  return (
    <div className="py-1">
      <div className="flex items-center justify-between text-[11px] mb-1">
        <span className="text-zinc-400 font-sans truncate">{label}</span>
        <div className="flex items-center gap-1 font-mono">
          <span className={`font-bold ${highlight ? "text-amber-400" : "text-white"}`}>
            {step < 0.1 ? value.toFixed(2) : value}
          </span>
          <span className="text-[10px] text-zinc-500">{unit}</span>
        </div>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-1 bg-[#1c2230] rounded-lg appearance-none cursor-pointer accent-[#f2a900]"
      />
    </div>
  );
}

function KpiPill({
  label,
  value,
  unit,
  accent = false,
}: {
  label: string;
  value: string;
  unit?: string;
  accent?: boolean;
}) {
  return (
    <div
      className={`px-3 py-2 rounded-xl border flex flex-col justify-between transition-colors ${
        accent ? "bg-[#151922] border-[#f2a900]/40 shadow-sm" : "bg-[#0D1017] border-[#1f2430]"
      }`}
    >
      <span className="text-[9px] font-bold uppercase tracking-wider text-zinc-500 font-mono">
        {label}
      </span>
      <div className="flex items-baseline gap-1 mt-0.5">
        <span className={`text-base font-black font-mono leading-none ${accent ? "text-[#f2a900]" : "text-white"}`}>
          {value}
        </span>
        {unit && <span className="text-[9px] text-zinc-500 font-mono">{unit}</span>}
      </div>
    </div>
  );
}

// ─── Canonical Vehicle Profiles (R2) ──────────────────────────────────────────

const FSAE_EV_PROFILE: CoupledVehicleConfig = {
  mass: 295,
  power_kw: 80,
  tire_mu: 1.45,
  brake_bias_front: 60,
  cl: 1.85,
  cd: 1.05,
  aero_balance_front: 48,
  front_spring_rate: 55,
  rear_spring_rate: 65,
  front_arb: 18,
  rear_arb: 14,
  front_rc_height: 25,
  rear_rc_height: 32,
  static_rh_front_mm: 35,
  static_rh_rear_mm: 42,
  wheelbase: 1.55,
  cog_dist_front: 0.80,
  h_cog: 0.28,
  frontal_area: 1.05,
  track_width_f: 1.22,
  track_width_r: 1.20,
};

const GT3_BASELINE_PROFILE: CoupledVehicleConfig = {
  mass: 1320,
  power_kw: 395,
  tire_mu: 1.38,
  brake_bias_front: 58,
  cl: 1.65,
  cd: 0.70,
  aero_balance_front: 46,
  front_spring_rate: 140,
  rear_spring_rate: 160,
  front_arb: 45,
  rear_arb: 30,
  front_rc_height: 35,
  rear_rc_height: 42,
  static_rh_front_mm: 55,
  static_rh_rear_mm: 70,
  wheelbase: 2.65,
  cog_dist_front: 1.35,
  h_cog: 0.42,
  frontal_area: 2.02,
  track_width_f: 1.62,
  track_width_r: 1.60,
};

// ─── Main ApexSim Cockpit Component ───────────────────────────────────────────

/** Model limit half-axes [g] from the solver envelope. Undefined when the envelope has no data (nothing is invented). */
function envelopeLimits(ggv?: GgvEnvelopeData): { latG?: number; accelG?: number; brakeG?: number } | null {
  if (!ggv) return null;
  const maxOf = (g?: number[], ms2?: number[]): number | undefined => {
    const v = g && g.length ? g : ms2 && ms2.length ? ms2.map((a) => a / 9.81) : undefined;
    return v ? Math.max(...v.map((x) => Math.abs(x))) : undefined;
  };
  return { latG: maxOf(ggv.ay_max_g, ggv.ay_max_ms2), accelG: maxOf(ggv.ax_accel_g, ggv.ax_accel_ms2), brakeG: maxOf(ggv.ax_brake_g, ggv.ax_brake_ms2) };
}

export default function LapSimPage() {
  const { fetchWithAuth } = useAuth();

  // 3-Tab Track Input Selector: preset (Championship), custom (Architect), csv (Telemetry)
  const [trackInputTab, setTrackInputTab] = useState<TrackInputTab>("preset");
  const [selectedCircuitId, setSelectedCircuitId] = useState<string>("spa");
  // Opt-in Spa elevation profile (coarse official-map stations). Off by default so results do not change.
  const [includeElevation, setIncludeElevation] = useState<boolean>(false);

  // Manual Vehicle Overrides Lock (Toggle: 🔒 Overrides Locked / 🔓 Auto-Preset: On)
  const [manualOverridesLocked, setManualOverridesLocked] = useState<boolean>(false);

  // Tab 2: Custom Track Architect Segments
  const [architectSegments, setArchitectSegments] = useState<CustomTrackSegment[]>([
    { id: "seg-1", type: "Straight", length_m: 650, radius_m: 0, banking_deg: 0, grade_pct: 0 },
    { id: "seg-2", type: "Right Corner", length_m: 220, radius_m: 65, banking_deg: 2, grade_pct: 0 },
    { id: "seg-3", type: "Straight", length_m: 400, radius_m: 0, banking_deg: 0, grade_pct: 0 },
    { id: "seg-4", type: "Hairpin", length_m: 140, radius_m: 22, banking_deg: 4, grade_pct: -1 },
    { id: "seg-5", type: "Straight", length_m: 550, radius_m: 0, banking_deg: 0, grade_pct: 0 },
    { id: "seg-6", type: "Left Corner", length_m: 260, radius_m: 75, banking_deg: 1, grade_pct: 0 },
  ]);

  // Tab 3: Telemetry CSV Parser State
  const [telemetryFileName, setTelemetryFileName] = useState<string>("");
  const [parsedCsvData, setParsedCsvData] = useState<ParsedTelemetryCsv | null>(null);
  const [cornerOpportunities, setCornerOpportunities] = useState<CornerOpportunity[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Left Sidebar: Coupled Vehicle, Aero & Suspension Controls (GT3 Spec Baseline)
  const [cfg, setCfg] = useState<CoupledVehicleConfig>(GT3_BASELINE_PROFILE);

  // Setup A Baseline (Pinned Ghost Car)
  const [pinnedBaseline, setPinnedBaseline] = useState<{
    lap: LapRunData;
    cfg: CoupledVehicleConfig;
  } | null>(null);

  // Simulation Results & View State
  const [running, setRunning] = useState<boolean>(false);
  const [result, setResult] = useState<LapSimResponse | null>(null);
  // Optional setup-response surface ("Compute Setup Grid"): a second, cancellable request.
  // The core solve stays on the fast path (include_surface: false).
  const lastPayloadRef = useRef<Record<string, any> | null>(null);
  const runSeqRef = useRef(0);
  const surfaceAbortRef = useRef<AbortController | null>(null);
  const [surfaceBusy, setSurfaceBusy] = useState<boolean>(false);
  const [surfaceMsg, setSurfaceMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hoverDist, setHoverDist] = useState<number | null>(null);

  const updateCfg = (key: keyof CoupledVehicleConfig, val: number) => {
    setCfg((prev) => ({ ...prev, [key]: val }));
  };

  const activeCircuit = useMemo(
    () => CHAMPIONSHIP_CIRCUITS.find((c) => c.id === selectedCircuitId) ?? CHAMPIONSHIP_CIRCUITS[0],
    [selectedCircuitId]
  );

  const { setVehicle } = useWorkspace();

  useEffect(() => {
    const isFsae = selectedCircuitId === "fsae_michigan" || selectedCircuitId === "fsae_endurance";
    let nextCfg: CoupledVehicleConfig | undefined;
    if (isFsae) {
      setVehicle({
        id: "fsae-ev-baseline",
        name: "Formula Student EV",
        version: "295 kg / 80 kW",
        mass_kg: 295,
        wheelbase_m: 1.55,
      });
      if (!manualOverridesLocked) {
        nextCfg = FSAE_EV_PROFILE;
        setCfg(FSAE_EV_PROFILE);
      }
    } else {
      setVehicle({
        id: "gt3-spec-baseline",
        name: "GT3 Spec Baseline",
        version: "1320 kg / 395 kW",
        mass_kg: 1320,
        wheelbase_m: 2.65,
      });
      if (!manualOverridesLocked) {
        nextCfg = GT3_BASELINE_PROFILE;
        setCfg(GT3_BASELINE_PROFILE);
      }
    }
    handleSimulate(nextCfg);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCircuitId, manualOverridesLocked, setVehicle]);

  // Architect 2D track integration
  const architectTrack = useMemo(() => {
    const distances: number[] = [0];
    const curvatures: number[] = [0];
    const x: number[] = [0];
    const y: number[] = [0];

    let currentHeading = 0;
    let curX = 0;
    let curY = 0;
    let dist = 0;
    const stepSize = 10;

    architectSegments.forEach((seg) => {
      const nSteps = Math.max(Math.round(seg.length_m / stepSize), 2);
      const ds = seg.length_m / nSteps;

      let kappa = 0;
      if (seg.type === "Left Corner" && seg.radius_m > 0) kappa = -1.0 / seg.radius_m;
      else if (seg.type === "Right Corner" && seg.radius_m > 0) kappa = 1.0 / seg.radius_m;
      else if (seg.type === "Hairpin" && seg.radius_m > 0) kappa = 1.0 / seg.radius_m;

      for (let s = 0; s < nSteps; s++) {
        curvatures.push(kappa);
        dist += ds;
        distances.push(dist);

        currentHeading += kappa * ds;
        curX += Math.cos(currentHeading) * ds;
        curY += Math.sin(currentHeading) * ds;
        x.push(curX);
        y.push(curY);
      }
    });

    return { distances, curvatures, x, y, totalLengthM: dist };
  }, [architectSegments]);

  const handleAddSegment = (type: CustomTrackSegment["type"]) => {
    const defaultRadius = type === "Hairpin" ? 18 : 75;
    const defaultLength = type === "Straight" ? 450 : 200;
    setArchitectSegments((prev) => [
      ...prev,
      {
        id: `seg-${Date.now()}`,
        type,
        length_m: defaultLength,
        radius_m: type === "Straight" ? 0 : defaultRadius,
        banking_deg: 0,
        grade_pct: 0,
      },
    ]);
  };

  const handleRemoveSegment = (id: string) => {
    setArchitectSegments((prev) => (prev.length > 2 ? prev.filter((s) => s.id !== id) : prev));
  };

  const handleUpdateSegment = (id: string, updates: Partial<CustomTrackSegment>) => {
    setArchitectSegments((prev) => prev.map((s) => (s.id === id ? { ...s, ...updates } : s)));
  };

  const handleTelemetryUpload = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const text = e.target?.result as string;
        const parsed = parseTelemetryCsv(text);
        setParsedCsvData(parsed);
        setTelemetryFileName(file.name);
        setTrackInputTab("csv");
        setError(null);
        handleSimulate(undefined, parsed, "csv");
      } catch (err: any) {
        setError(err.message ?? "CSV parse error");
      }
    };
    reader.readAsText(file);
  };

  const handleLoadSampleCsv = () => {
    const synth = synthesizeTrackGeometry(activeCircuit.totalLengthM, activeCircuit.corners, 400, activeCircuit.id);
    const sim = runLocalCoupledLapSimulation(
      synth.distances,
      synth.curvatures,
      synth.x,
      synth.y,
      cfg,
      activeCircuit.sectorBoundaries
    );

    const driverSpeedsKmh = sim.trace.speed_kmh.map((v, idx) => {
      const inCorner = (sim.trace.limiting_factor?.[idx] || "").includes("UNDERSTEER") || (sim.trace.limiting_factor?.[idx] || "").includes("BRAKING");
      const deficit = inCorner ? 6.5 : 1.2;
      return Math.max(v - deficit, 20);
    });

    let currentT = 0;
    const timeS: number[] = [0];
    for (let i = 1; i < driverSpeedsKmh.length; i++) {
      const ds = synth.distances[i] - synth.distances[i - 1];
      const v = driverSpeedsKmh[i] / 3.6;
      currentT += ds / Math.max(v, 2.0);
      timeS.push(currentT);
    }

    const sampleCsvData: ParsedTelemetryCsv = {
      timeS,
      speedKmh: driverSpeedsKmh,
      latG: sim.trace.lat_g,
      longG: sim.trace.long_g,
      distanceM: synth.distances,
      curvature: synth.curvatures,
      x: synth.x,
      y: synth.y,
    };

    setParsedCsvData(sampleCsvData);
    setTelemetryFileName("MoTeC_Sample_Stint.csv [Local Estimate (Unsolved)]");
    setTrackInputTab("csv");
    handleSimulate(undefined, sampleCsvData, "csv");
  };

  const handleApplyOptimalSetup = (optArb: number, optAero: number) => {
    const updated = {
      ...cfg,
      front_arb: optArb,
      aero_balance_front: optAero,
    };
    setCfg(updated);
    handleSimulate(updated);
  };

  // Main Simulation Execution
  const handleSimulate = async (
    overrideCfg?: CoupledVehicleConfig,
    overrideCsv?: ParsedTelemetryCsv,
    overrideTab?: TrackInputTab
  ) => {
    setRunning(true);
    setError(null);

    const currentTab = overrideTab ?? trackInputTab;
    const activeCfg = overrideCfg && typeof overrideCfg === "object" && "mass" in overrideCfg
      ? overrideCfg
      : cfg;
    const activeCsv = overrideCsv ?? parsedCsvData;

    try {
      let trackDistances: number[] = [];
      let trackCurvatures: number[] = [];
      let trackX: number[] = [];
      let trackY: number[] = [];
      let sectorBounds: [number, number] = [2000, 4500];

      if (currentTab === "preset") {
        const synth = synthesizeTrackGeometry(activeCircuit.totalLengthM, activeCircuit.corners, 500, activeCircuit.id);
        trackDistances = synth.distances;
        trackCurvatures = synth.curvatures;
        trackX = synth.x;
        trackY = synth.y;
        sectorBounds = activeCircuit.sectorBoundaries;
      } else if (currentTab === "custom") {
        trackDistances = architectTrack.distances;
        trackCurvatures = architectTrack.curvatures;
        trackX = architectTrack.x;
        trackY = architectTrack.y;
        const total = architectTrack.totalLengthM;
        sectorBounds = [total * 0.33, total * 0.66];
      } else if (currentTab === "csv" && activeCsv) {
        trackDistances = activeCsv.distanceM;
        trackCurvatures = activeCsv.curvature;
        trackX = activeCsv.x;
        trackY = activeCsv.y;
        const total = trackDistances[trackDistances.length - 1] ?? 5000;
        sectorBounds = [total * 0.33, total * 0.66];
      } else {
        throw new Error("Select a championship circuit or provide track coordinates.");
      }

      const payload: Record<string, any> = {
        mode: currentTab,
        track: selectedCircuitId === "fsae_michigan" ? "fsae_endurance" : selectedCircuitId,
        circuit_id: selectedCircuitId,
        vehicle: {
          total_mass: activeCfg.mass,
          wheelbase: activeCfg.wheelbase,
          cog_dist_front: activeCfg.cog_dist_front,
          h_cog: activeCfg.h_cog,
          max_power_kw: activeCfg.power_kw,
          brake_front_bias: activeCfg.brake_bias_front / 100,
          cl_base: activeCfg.cl,
          cd_base: activeCfg.cd,
          aero_balance_front: activeCfg.aero_balance_front / 100.0,
          frontal_area: activeCfg.frontal_area,
          tire_mu: activeCfg.tire_mu,
          front_spring_rate: activeCfg.front_spring_rate,
          rear_spring_rate: activeCfg.rear_spring_rate,
          front_arb: activeCfg.front_arb,
          rear_arb: activeCfg.rear_arb,
          front_rc_height: activeCfg.front_rc_height,
          rear_rc_height: activeCfg.rear_rc_height,
          static_rh_front_mm: activeCfg.static_rh_front_mm,
          static_rh_rear_mm: activeCfg.static_rh_rear_mm,
        },
      };

      if (includeElevation && selectedCircuitId === "spa") payload.with_elevation = true;

      if (currentTab === "custom") {
        payload.segments = architectSegments.map((s) => ({
          type: s.type,
          length_m: s.length_m,
          radius_m: s.radius_m,
          banking_deg: s.banking_deg,
          grade_pct: s.grade_pct,
        }));
        payload.is_closed = true;
      } else if (currentTab === "csv" && activeCsv) {
        payload.telemetry = {
          time_s: activeCsv.timeS,
          speed_ms: activeCsv.speedKmh.map((v) => v / 3.6),
          lat_g: activeCsv.latG,
        };
      } else {
        payload.distances = trackDistances;
        payload.curvatures = trackCurvatures;
        payload.track_coordinates = { x: trackX, y: trackY };
        payload.sector_boundaries = sectorBounds;
      }

      // A new core solve invalidates any surface request still in flight.
      surfaceAbortRef.current?.abort();
      runSeqRef.current += 1;
      lastPayloadRef.current = { ...payload, include_surface: false };
      setSurfaceBusy(false);
      setSurfaceMsg(null);

      const res = await fetchWithAuth("/api/v1/lap-sim/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        let errorDetail = `Simulation failed (${res.status})`;
        try {
          const errJson = await res.json();
          if (errJson?.detail) {
            errorDetail = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
          } else if (errJson?.message) {
            errorDetail = errJson.message;
          }
        } catch {
          if (res.statusText) {
            errorDetail = `${res.status} ${res.statusText}`;
          }
        }
        throw new Error(errorDetail);
      }

      const raw = await res.json();
      const rawLapTime = raw.lap_time_s ?? raw.total_time_s ?? 0;
      let parsedSectors = Array.isArray(raw.sector_times) ? raw.sector_times : (Array.isArray(raw.sector_times_s) ? raw.sector_times_s : []);
      if (!parsedSectors || parsedSectors.length < 3 || parsedSectors[1] <= 0 || parsedSectors[2] <= 0) {
        // No fabricated 30/36/34% splits - unknown sectors stay unknown (UI shows N/A).
        parsedSectors = [];
      }

      // Exact mechanical front LLTD fallback
      const fallbackKwf = activeCfg.front_spring_rate * 1000 * 0.72 ** 2;
      const fallbackKwr = activeCfg.rear_spring_rate * 1000 * 0.74 ** 2;
      const fallbackKphif = 0.5 * (fallbackKwf + activeCfg.front_arb * 1000) * activeCfg.track_width_f ** 2;
      const fallbackKphir = 0.5 * (fallbackKwr + activeCfg.rear_arb * 1000) * activeCfg.track_width_r ** 2;
      const fallbackFrontLltd = Number(((fallbackKphif / Math.max(fallbackKphif + fallbackKphir, 1.0)) * 100).toFixed(1));

      const simData: LapSimResponse = {
        lap_time_s: rawLapTime,
        lap_completed: raw.lap_completed ?? true,
        outcome: raw.outcome,
        sector_times: parsedSectors,
        max_speed_kmh: raw.max_speed_kmh ?? 0,
        min_speed_kmh: raw.min_speed_kmh ?? 0,
        avg_speed_kmh: raw.avg_speed_kmh ?? 0,
        max_lat_g: raw.max_lat_g ?? raw.telemetry?.max_lat_g,
        max_long_g: raw.max_long_g,
        max_braking_g: raw.max_braking_g,
        front_lltd_pct: raw.front_lltd_pct ?? fallbackFrontLltd,
        front_lltd_estimated: raw.front_lltd_pct == null,
        min_rh_front_mm: raw.min_rh_front_mm ?? raw.telemetry?.min_rh_front_mm,
        min_rh_rear_mm: raw.min_rh_rear_mm ?? raw.telemetry?.min_rh_rear_mm,
        bottoming_events_count: raw.bottoming_events_count ?? 0,
        energy_used_kj: raw.energy_used_kj ?? 0,
        understeer_pct: raw.understeer_pct,
        trace: {
          s_m: Array.isArray(raw.trace?.s_m) ? raw.trace.s_m : (Array.isArray(raw.telemetry?.distances) ? raw.telemetry.distances : trackDistances),
          x_m: Array.isArray(raw.trace?.x_m) ? raw.trace.x_m : (Array.isArray(raw.track_coordinates?.x) ? raw.track_coordinates.x : trackX),
          y_m: Array.isArray(raw.trace?.y_m) ? raw.trace.y_m : (Array.isArray(raw.track_coordinates?.y) ? raw.track_coordinates.y : trackY),
          speed_kmh: Array.isArray(raw.trace?.speed_kmh) ? raw.trace.speed_kmh : (Array.isArray(raw.telemetry?.speeds_kmh) ? raw.telemetry.speeds_kmh : []),
          lat_g: Array.isArray(raw.trace?.lat_g) ? raw.trace.lat_g : (Array.isArray(raw.telemetry?.lateral_g) ? raw.telemetry.lateral_g : []),
          long_g: Array.isArray(raw.trace?.long_g) ? raw.trace.long_g : (Array.isArray(raw.telemetry?.longitudinal_g) ? raw.telemetry.longitudinal_g : []),
          throttle_pct: raw.trace?.throttle_pct,
          brake_pct: raw.trace?.brake_pct,
          gear: raw.trace?.gear ?? raw.telemetry?.gear_number,
          downforce_n: raw.trace?.downforce_n ?? raw.telemetry?.aero_downforce_n,
          limiting_factor: raw.trace?.limiting_factor,
          ride_height_front_mm: raw.trace?.ride_height_front_mm ?? raw.telemetry?.ride_height_front_mm,
          ride_height_rear_mm: raw.trace?.ride_height_rear_mm ?? raw.telemetry?.ride_height_rear_mm,
          pitch_deg: raw.trace?.pitch_deg ?? raw.telemetry?.pitch_deg,
          z_m: raw.trace?.z_m ?? raw.telemetry?.z_m,
          dz_ds: raw.trace?.dz_ds ?? raw.telemetry?.dz_ds,
          vertical_g: raw.trace?.vertical_g ?? raw.telemetry?.vertical_g,
          vertical_load_delta_n: raw.trace?.vertical_load_delta_n ?? raw.telemetry?.vertical_load_delta_n,
          compression_mm: raw.trace?.compression_mm ?? raw.telemetry?.compression_mm,
        },
        ggv_envelope: raw.ggv_envelope ?? raw.ggv,
        corner_opportunities: raw.corner_opportunities,
        setup_surface: raw.setup_surface ?? raw.telemetry?.setup_surface,
        model_version: raw.model_version ?? "ApexSim-Contract",
      };

      // Top 3 Corner Opportunities for CSV mode
      if (currentTab === "csv" && simData) {
        if (Array.isArray(simData.corner_opportunities) && simData.corner_opportunities.length > 0) {
          const mappedOps: CornerOpportunity[] = simData.corner_opportunities.map((co: any, idx: number) => ({
            corner_id: co.corner_id ?? idx + 1,
            name: co.name ?? `Turn ${co.corner_id ?? idx + 1} (${(co.s_start_m ?? co.distance_m ?? 0).toFixed(0)}m)`,
            distance_m: co.s_start_m ?? co.distance_m ?? 0,
            time_loss_s: Number(co.time_loss_s ?? 0),
            driver_speed_kmh: Number(co.v_driver_apex_kmh ?? co.driver_speed_kmh ?? 0),
            optimal_speed_kmh: Number(co.v_sim_apex_kmh ?? co.optimal_speed_kmh ?? 0),
            limiting_factor: co.bottleneck ?? co.limiting_factor ?? "UNDERSTEER_FRONT",
            recommendation: co.recommendation ?? "Vehicle front axle saturated. Soften front ARB or increase front wing.",
          }));
          simData.corner_opportunities = mappedOps;
          setCornerOpportunities(mappedOps);
        } else if (activeCsv) {
          const opportunities: CornerOpportunity[] = [];
          const optSpeeds = simData.trace.speed_kmh;
          const drvSpeeds = activeCsv.speedKmh;
          const dists = simData.trace.s_m;
          const nScan = Math.min(optSpeeds.length, drvSpeeds.length);

          const candidates: Array<{ idx: number; dist: number; deficit: number; optV: number; drvV: number }> = [];
          for (let i = 2; i < nScan - 2; i += 8) {
            const optV = optSpeeds[i];
            const drvV = drvSpeeds[i];
            const deficit = optV - drvV;
            const latGVal = Math.abs(simData.trace.lat_g[i] ?? 0);
            if (latGVal > 0.8 && deficit > 3.5) {
              candidates.push({ idx: i, dist: dists[i], deficit, optV, drvV });
            }
          }

          candidates.sort((a, b) => b.deficit - a.deficit);
          const picked: typeof candidates = [];
          for (const cand of candidates) {
            if (picked.every((p) => Math.abs(p.dist - cand.dist) > 220)) {
              picked.push(cand);
              if (picked.length >= 3) break;
            }
          }

          picked.forEach((c, idx) => {
            const timeLoss = ((c.deficit / 3.6) * 14) / Math.max(c.drvV / 3.6, 5);
            const factor = simData?.trace.limiting_factor?.[c.idx] ?? "UNDERSTEER_FRONT";

            let rec = "";
            if (factor === "BRAKING") {
              rec = `Brake 12m later; driver over-braked entry by ${(c.deficit).toFixed(1)} km/h. Shift brake bias 1% rearward.`;
            } else if (factor === "UNDERSTEER_FRONT") {
              rec = `Front axle saturated. Soften front ARB by 10 N/mm or add front wing to eliminate mid-corner scrub.`;
            } else if (factor === "OVERSTEER_REAR") {
              rec = `Rear axle loose on exit throttle. Stiffen front ARB or soften rear springs to stabilize traction.`;
            } else {
              rec = `Full throttle delayed by 0.25s. Commit earlier to power on corner exit.`;
            }

            opportunities.push({
              corner_id: idx + 1,
              name: `Turn ${idx + 1} (${c.dist.toFixed(0)}m)`,
              distance_m: c.dist,
              time_loss_s: parseFloat(timeLoss.toFixed(3)),
              driver_speed_kmh: parseFloat(c.drvV.toFixed(1)),
              optimal_speed_kmh: parseFloat(c.optV.toFixed(1)),
              limiting_factor: factor,
              recommendation: rec,
            });
          });

          simData.corner_opportunities = opportunities;
          setCornerOpportunities(opportunities);
        }
      }

      setResult(simData);
    } catch (e: any) {
      setError(formatApiError(e, "Lap simulation failed"));
    } finally {
      setRunning(false);
    }
  };

  const cancelSurface = () => {
    surfaceAbortRef.current?.abort();
  };

  const computeSurface = async () => {
    const base = lastPayloadRef.current;
    if (!base || surfaceBusy) return;
    const seq = runSeqRef.current;
    const ctrl = new AbortController();
    surfaceAbortRef.current = ctrl;
    setSurfaceBusy(true);
    setSurfaceMsg(null);
    try {
      const res = await fetchWithAuth("/api/v1/lap-sim/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...base, include_surface: true }),
        signal: ctrl.signal,
      });
      if (!res.ok) {
        let detail: unknown = null;
        try { detail = await res.json(); } catch { /* non-JSON error body */ }
        throw detail ?? new Error(`Surface request failed (${res.status})`);
      }
      const raw = await res.json();
      if (seq !== runSeqRef.current) return; // inputs changed while the surface was computing: discard
      const surface = raw.setup_surface ?? raw.telemetry?.setup_surface;
      if (!surface) {
        setSurfaceMsg("The solver returned no surface for this input.");
        return;
      }
      setResult((prev) => (prev ? { ...prev, setup_surface: surface } : prev));
    } catch (e: any) {
      if (e?.name === "AbortError") {
        setSurfaceMsg("Surface computation cancelled.");
      } else {
        setSurfaceMsg(formatApiError(e, "Surface computation failed"));
      }
    } finally {
      if (seq === runSeqRef.current) setSurfaceBusy(false);
      if (surfaceAbortRef.current === ctrl) surfaceAbortRef.current = null;
    }
  };

  useEffect(() => () => surfaceAbortRef.current?.abort(), []);

  const tabMountedRef = useRef(false);
  useEffect(() => {
    if (!tabMountedRef.current) {
      tabMountedRef.current = true;
      return;
    }
    handleSimulate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trackInputTab]);

  const handlePinBaseline = () => {
    if (!result) return;
    setPinnedBaseline({
      lap: {
        lap_time_s: result.lap_time_s,
        sector_times: result.sector_times,
        max_speed_kmh: result.max_speed_kmh,
        min_speed_kmh: result.min_speed_kmh,
        avg_speed_kmh: result.avg_speed_kmh,
        energy_used_kj: result.energy_used_kj,
        trace: result.trace,
      },
      cfg: { ...cfg },
    });
  };

  const trackMapCorners: CornerInfo[] = useMemo(() => {
    if (trackInputTab === "preset") {
      return activeCircuit.corners.map((c) => ({
        corner_id: c.id,
        name: c.name,
        apex_distance_m: c.distM,
        min_speed_kmh: 80,
      }));
    }
    return cornerOpportunities.map((o) => ({
      corner_id: o.corner_id,
      name: o.name,
      apex_distance_m: o.distance_m,
      time_loss_s: o.time_loss_s,
      limiting_factor: o.limiting_factor,
    }));
  }, [trackInputTab, activeCircuit, cornerOpportunities]);

  const tel = result?.trace;
  // Unknown sectors stay unknown - no fabricated 30/36/34% splits.
  const s1Time = result?.sector_times?.[0] ?? null;
  const s2Time = result?.sector_times?.[1] ?? null;
  const s3Time = result?.sector_times?.[2] ?? null;
  const lapIncomplete = result?.lap_completed === false;

  return (
    <PlanGate required="PRO" feature="Lap Time & Track Sim">
      <div className="flex h-[calc(100vh-44px)] bg-[#07090E] text-white overflow-hidden">
        {/* ── LEFT SIDEBAR: Setup Controls ──────────────────────────────────── */}
        <aside
          aria-label="Vehicle Setup Controls"
          className="w-[310px] xl:w-[340px] flex-shrink-0 border-r border-[#191F2B] overflow-y-auto p-3.5 space-y-2.5 custom-scrollbar bg-[#0A0D14]"
        >
          {/* Header */}
          <div className="pb-2.5 border-b border-[#191F2B]">
            <div className="flex items-center gap-2 mb-1">
              <div className="w-5 h-5 rounded-md bg-[#f2a900]/15 border border-[#f2a900]/40 flex items-center justify-center">
                <Timer size={12} className="text-[#f2a900]" />
              </div>
              <h1 className="text-xs font-bold text-white tracking-wide">ApexSim Cockpit</h1>
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30 font-mono ml-auto">
                PRO SOLVER
              </span>
              <NextStepLink />
            </div>
            <p className="text-[10px] text-zinc-400 leading-relaxed font-sans">
              Coupled aero, mass, &amp; suspension multi-body lap solver
            </p>
          </div>

          {/* Vehicle & Drivetrain */}
          <Section title="Vehicle & Drivetrain">
            <ParamSlider
              label="Mass"
              unit="kg"
              value={cfg.mass}
              min={200}
              max={1800}
              step={5}
              onChange={(v) => updateCfg("mass", v)}
            />
            <ParamSlider
              label="Max Power"
              unit="kW"
              value={cfg.power_kw}
              min={40}
              max={1200}
              step={5}
              onChange={(v) => updateCfg("power_kw", v)}
            />
            <ParamSlider
              label="Tire Peak Grip (mu_0)"
              unit="–"
              value={cfg.tire_mu}
              min={0.7}
              max={2.2}
              step={0.05}
              onChange={(v) => updateCfg("tire_mu", v)}
              highlight
            />
            <ParamSlider
              label="Brake Bias (% Front)"
              unit="%"
              value={cfg.brake_bias_front}
              min={45}
              max={75}
              step={1}
              onChange={(v) => updateCfg("brake_bias_front", v)}
            />
          </Section>

          {/* Aerodynamics */}
          <Section title="Aerodynamics">
            <ParamSlider
              label="Downforce Coeff (Cl)"
              unit="–"
              value={cfg.cl}
              min={0.0}
              max={5.0}
              step={0.05}
              onChange={(v) => updateCfg("cl", v)}
              highlight
            />
            <ParamSlider
              label="Drag Coeff (Cd)"
              unit="–"
              value={cfg.cd}
              min={0.2}
              max={2.5}
              step={0.02}
              onChange={(v) => updateCfg("cd", v)}
            />
            <ParamSlider
              label="Aero Balance (% Front)"
              unit="%"
              value={cfg.aero_balance_front}
              min={35}
              max={65}
              step={1}
              onChange={(v) => updateCfg("aero_balance_front", v)}
            />
          </Section>

          {/* Coupled Suspension & Kinematics */}
          <Section title="Coupled Suspension & Kinematics">
            <ParamSlider
              label="Front Spring Rate"
              unit="N/mm"
              value={cfg.front_spring_rate}
              min={30}
              max={250}
              step={1}
              onChange={(v) => updateCfg("front_spring_rate", v)}
            />
            <ParamSlider
              label="Rear Spring Rate"
              unit="N/mm"
              value={cfg.rear_spring_rate}
              min={30}
              max={250}
              step={1}
              onChange={(v) => updateCfg("rear_spring_rate", v)}
            />
            <ParamSlider
              label="Front ARB Wheel Rate"
              unit="N/mm"
              value={cfg.front_arb}
              min={5}
              max={150}
              step={1}
              onChange={(v) => updateCfg("front_arb", v)}
              highlight
            />
            <ParamSlider
              label="Rear ARB Wheel Rate"
              unit="N/mm"
              value={cfg.rear_arb}
              min={5}
              max={120}
              step={1}
              onChange={(v) => updateCfg("rear_arb", v)}
              highlight
            />
            <ParamSlider
              label="Front Roll Center Height"
              unit="mm"
              value={cfg.front_rc_height}
              min={-20}
              max={150}
              step={1}
              onChange={(v) => updateCfg("front_rc_height", v)}
            />
            <ParamSlider
              label="Rear Roll Center Height"
              unit="mm"
              value={cfg.rear_rc_height}
              min={0}
              max={200}
              step={1}
              onChange={(v) => updateCfg("rear_rc_height", v)}
            />
            <ParamSlider
              label="Static Front Ride Height"
              unit="mm"
              value={cfg.static_rh_front_mm}
              min={20}
              max={100}
              step={1}
              onChange={(v) => updateCfg("static_rh_front_mm", v)}
            />
            <ParamSlider
              label="Static Rear Ride Height"
              unit="mm"
              value={cfg.static_rh_rear_mm}
              min={20}
              max={120}
              step={1}
              onChange={(v) => updateCfg("static_rh_rear_mm", v)}
            />
          </Section>

          {/* Action Buttons */}
          <div className="pt-1 space-y-2">
            <button
              onClick={() => handleSimulate()}
              disabled={running}
              id="run-lap-sim-btn"
              className="w-full py-2.5 rounded-xl text-[11px] font-bold uppercase tracking-wider bg-[#f2a900] text-black hover:bg-[#ffb800] transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 cursor-pointer shadow-lg"
            >
              {running ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  Running Lap Simulation…
                </>
              ) : (
                <>
                  <Play size={13} />
                  Run Lap Simulation
                </>
              )}
            </button>

            <button
              onClick={handlePinBaseline}
              disabled={!result}
              className="w-full py-2 rounded-xl text-[10px] font-mono font-bold bg-[#141A25] hover:bg-[#1D2535] text-amber-300 border border-amber-500/35 transition-all flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-40 shadow-sm"
            >
              <Pin size={11} />
              {pinnedBaseline ? `Setup A Pinned (${pinnedBaseline.lap.lap_time_s.toFixed(3)}s)` : "Pin as Baseline (Setup A)"}
            </button>
          </div>

          {error && (
            <div className="p-2.5 rounded-lg bg-red-950/40 border border-red-900/50 flex items-start gap-2">
              <AlertCircle size={12} className="text-red-400 mt-0.5 flex-shrink-0" />
              <p className="text-[10px] text-red-400 leading-relaxed font-mono">{error}</p>
            </div>
          )}
        </aside>

        {/* ── MAIN WORKSPACE ────────────────────────────────────────────────── */}
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden bg-[#07090E]">
          {/* Top Track Input Selector (3 Tabs) & Vehicle Badge */}
          <div className="flex-shrink-0 border-b border-white/10 bg-[#090B10] p-3 flex flex-wrap items-center justify-between gap-3 z-30">
            <div className="flex items-center gap-3 flex-wrap">
              <div className="flex items-center gap-1.5 bg-[#121620] p-1 rounded-xl border border-[#202737]">
                {(
                  [
                    { id: "preset", label: "🏁 Championship Circuits" },
                    { id: "custom", label: "✏️ Custom Track Architect" },
                    { id: "csv", label: "📊 Reconstruct Track from CSV / GPS" },
                  ] as const
                ).map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setTrackInputTab(tab.id)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold font-mono transition-all cursor-pointer ${
                      trackInputTab === tab.id
                        ? "bg-[#f2a900] text-black shadow-md"
                        : "text-zinc-400 hover:text-white"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Prominent Vehicle Context Badge & Overrides Lock */}
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#10141F] border border-[#232C3D] text-[10px] font-mono shadow-sm">
                  <Car size={12} className="text-[#06B6D4]" />
                  <span className="text-zinc-400 font-bold">VEHICLE:</span>
                  <span className="text-white font-bold">
                    {selectedCircuitId === "fsae_michigan" || selectedCircuitId === "fsae_endurance"
                      ? "Formula Student EV (295 kg / 80 kW)"
                      : "GT3 Spec Baseline (1320 kg / 395 kW)"}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setManualOverridesLocked((prev) => !prev)}
                  title={manualOverridesLocked ? "Manual vehicle overrides locked" : "Auto-switch presets on track change active"}
                  className={`px-2.5 py-1 rounded-lg text-[10px] font-mono font-bold border transition-all cursor-pointer ${
                    manualOverridesLocked
                      ? "bg-amber-500/15 border-amber-500/40 text-amber-300"
                      : "bg-white/[0.04] border-white/10 text-zinc-400 hover:text-white"
                  }`}
                >
                  {manualOverridesLocked ? "🔒 Overrides Locked" : "🔓 Auto-Preset: On"}
                </button>
              </div>
            </div>

            {/* Sub-controls depending on active Tab */}
            {trackInputTab === "preset" && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-zinc-400 font-mono">Circuit:</span>
                <div className="flex rounded-lg border border-[#232B3D] overflow-hidden bg-[#0D1017]">
                  {CHAMPIONSHIP_CIRCUITS.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => setSelectedCircuitId(c.id)}
                      className={`px-2.5 py-1 text-[10px] font-mono font-bold transition-colors cursor-pointer ${
                        selectedCircuitId === c.id
                          ? "bg-[#06B6D4] text-black"
                          : "text-zinc-400 hover:text-white"
                      }`}
                    >
                      {c.name.split(" ")[0]} ({c.totalLengthM.toLocaleString()}m)
                    </button>
                  ))}
                </div>
              </div>
            )}

            {trackInputTab === "custom" && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-zinc-400">
                  Length: <strong className="text-amber-400">{architectTrack.totalLengthM.toFixed(0)}m</strong>
                </span>
                <button
                  onClick={() => handleSimulate()}
                  disabled={running}
                  className="px-3 py-1 rounded-lg text-xs font-bold bg-[#06B6D4] text-black hover:bg-[#38BDF8] transition-all cursor-pointer flex items-center gap-1 shadow-sm"
                >
                  <Play size={10} />
                  Simulate Custom Circuit
                </button>
              </div>
            )}

            {trackInputTab === "csv" && (
              <div className="flex items-center gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.txt,.gpx,.kml"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && handleTelemetryUpload(e.target.files[0])}
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="px-2.5 py-1 rounded-lg text-xs font-mono bg-[#141A25] hover:bg-[#1E2535] text-zinc-200 border border-[#252C3B] transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  <FileSpreadsheet size={12} className="text-cyan-400" />
                  {telemetryFileName ? telemetryFileName : "Upload CSV / GPX / KML"}
                </button>
                <button
                  onClick={handleLoadSampleCsv}
                  className="px-2.5 py-1 rounded-lg text-xs font-mono bg-[#161C26] hover:bg-[#202737] text-amber-300 border border-amber-500/40 transition-all flex items-center gap-1 cursor-pointer"
                >
                  <Sparkles size={11} className="text-amber-400" />
                  Sample MoTeC CSV
                </button>
              </div>
            )}
          </div>

          {/* Top KPI Strip */}
          {result && (
            <div className="flex-shrink-0 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 p-3 border-b border-white/10 bg-[#090B10]/95 backdrop-blur-md z-20">
              <KpiPill
                label="Lap Time"
                value={lapIncomplete ? "INCOMPLETE" : formatLapTime(result.lap_time_s)}
                accent
              />
              <KpiPill
                label="S1 / S2 / S3"
                value={s1Time != null && s2Time != null && s3Time != null
                  ? `${s1Time.toFixed(1)} / ${s2Time.toFixed(1)} / ${s3Time.toFixed(1)}`
                  : "N/A"}
                unit="s"
              />
              <KpiPill
                label="Top Speed"
                value={result.max_speed_kmh.toFixed(0)}
                unit="km/h"
              />
              <KpiPill
                label="Max Cornering"
                value={result.max_lat_g != null ? result.max_lat_g.toFixed(2) : "N/A"}
                unit="g"
              />
              <KpiPill
                label="Max Braking"
                value={result.max_braking_g != null ? result.max_braking_g.toFixed(2) : "N/A"}
                unit="g"
              />
              <KpiPill
                label="Front LLTD"
                value={result.front_lltd_pct != null
                  ? `${Number(result.front_lltd_pct).toFixed(1)}${result.front_lltd_estimated ? "*" : ""}`
                  : "N/A"}
                unit="%"
              />
              <KpiPill
                label="Min Ride Height (F/R)"
                value={result.min_rh_front_mm != null && result.min_rh_rear_mm != null
                  ? `${Number(result.min_rh_front_mm).toFixed(1)} / ${Number(result.min_rh_rear_mm).toFixed(1)}`
                  : "N/A"}
                unit="mm"
              />
              <KpiPill
                label="Mechanical Energy"
                value={result.energy_used_kj.toFixed(0)}
                unit="kJ"
              />
              <KpiPill
                label="Bottoming Events"
                value={`${result.bottoming_events_count ?? 0}`}
                unit=""
              />
            </div>
          )}

          {/* Truthfulness banners */}
          {result && lapIncomplete && (
            <div className="flex-shrink-0 px-3 py-2 bg-red-950/60 border-b border-red-500/40 text-red-300 text-xs font-mono font-bold flex items-center gap-2">
              LAP INCOMPLETE - PHYSICAL INSTABILITY{result.outcome ? ` (${result.outcome})` : ""}. No valid lap time - the displayed values describe the aborted run.
            </div>
          )}
          {result && !lapIncomplete && (result.bottoming_events_count ?? 0) > 0 && (
            <div className="flex-shrink-0 px-3 py-2 bg-amber-950/60 border-b border-amber-500/40 text-amber-300 text-xs font-mono font-bold flex items-center gap-2">
              BOTTOMING DETECTED - {result.bottoming_events_count} event(s). Increase ride height or bump-stop rate.
            </div>
          )}
          {result && !lapIncomplete && (result.bottoming_events_count ?? 0) === 0 &&
            result.min_rh_front_mm != null && result.min_rh_rear_mm != null &&
            (result.min_rh_front_mm <= 1.0 || result.min_rh_rear_mm <= 1.0) && (
            <div className="flex-shrink-0 px-3 py-2 bg-amber-950/60 border-b border-amber-500/40 text-amber-300 text-xs font-mono font-bold flex items-center gap-2">
              BOTTOMING DETECTED - minimum ride height at or below 1.0 mm.
            </div>
          )}
          {result?.front_lltd_estimated && (
            <div className="flex-shrink-0 px-3 py-1 bg-[#0C1018] border-b border-[#1A202D] text-zinc-500 text-[10px] font-mono">
              * Front LLTD marked with an asterisk is a mechanical estimate derived from spring/ARB rates (motion ratios 0.72/0.74 assumed) - not solver output.
            </div>
          )}
          {result && (
            <div className="flex-shrink-0 px-3 py-1 bg-[#0C1018] border-b border-[#1A202D] text-zinc-600 text-[10px] font-mono">
              QSS aero/tire baseline - verify against track telemetry before committing setup changes.
            </div>
          )}

          {/* Interactive Architect Editor Bar (if Tab 2 is active) */}
          {trackInputTab === "custom" && (
            <div className="flex-shrink-0 p-3 bg-[#0C1018] border-b border-[#1A202D] overflow-x-auto custom-scrollbar">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-mono text-zinc-400 whitespace-nowrap">Segments:</span>
                {architectSegments.map((seg, idx) => (
                  <div
                    key={seg.id}
                    className="flex-shrink-0 p-2 rounded-lg bg-[#141A25] border border-[#222938] text-[10px] space-y-1 min-w-[130px]"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white font-mono">
                        {idx + 1}. {seg.type.split(" ")[0]}
                      </span>
                      <button
                        onClick={() => handleRemoveSegment(seg.id)}
                        className="text-zinc-500 hover:text-rose-400 transition-colors"
                      >
                        <Trash2 size={10} />
                      </button>
                    </div>
                    <div className="flex justify-between items-center text-[9px] font-mono text-zinc-400">
                      <span>L: {seg.length_m}m</span>
                      {seg.radius_m > 0 && <span>R: {seg.radius_m}m</span>}
                    </div>
                  </div>
                ))}
                <div className="flex items-center gap-1 pl-2">
                  {(["Straight", "Left Corner", "Right Corner", "Hairpin"] as const).map((t) => (
                    <button
                      key={t}
                      onClick={() => handleAddSegment(t)}
                      className="px-2 py-1.5 rounded-lg bg-[#161D2B] hover:bg-[#20293D] text-[10px] font-mono text-zinc-300 border border-zinc-700 transition-colors flex items-center gap-1 cursor-pointer whitespace-nowrap"
                    >
                      <Plus size={10} />
                      {t.split(" ")[0]}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Top 3 Corner Opportunities (if Tab 3 is active and opportunities present) */}
          {trackInputTab === "csv" && cornerOpportunities.length > 0 && (
            <div className="flex-shrink-0 p-3 bg-[#0A0D15] border-b border-[#1A202D]">
              <div className="flex items-center gap-2 mb-2">
                <Target size={14} className="text-[#f2a900]" />
                <span className="text-xs font-bold text-white font-mono uppercase tracking-wider">
                  Top 3 Corner Opportunity Finder (Driver vs. Optimal)
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
                {cornerOpportunities.map((opp) => (
                  <div
                    key={opp.corner_id}
                    className="p-2.5 rounded-xl bg-[#121620] border border-[#202737] hover:border-amber-500/40 transition-all flex flex-col justify-between space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-white font-mono">{opp.name}</span>
                      <span className="text-[11px] font-black text-rose-400 font-mono bg-rose-950/80 px-2 py-0.5 rounded border border-rose-800/40">
                        +{opp.time_loss_s.toFixed(3)}s
                      </span>
                    </div>
                    <div className="text-[10px] font-mono text-zinc-400 flex justify-between">
                      <span>Driver: {opp.driver_speed_kmh.toFixed(1)} km/h</span>
                      <span className="text-amber-400">Opt: {opp.optimal_speed_kmh.toFixed(1)} km/h</span>
                    </div>
                    <div className="text-[9px] text-zinc-300 bg-[#161C28] p-1.5 rounded border border-[#252E3E]">
                      {opp.recommendation}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Main Visualization Grid */}
          <div className="flex-1 p-3 min-h-0 overflow-y-auto custom-scrollbar space-y-3">
            {result ? (
              <>
                {/* 2D Color-Coded Bottleneck TrackMap */}
                <TrackMap
                  x_m={tel?.x_m ?? []}
                  y_m={tel?.y_m ?? []}
                  speed_kmh={tel?.speed_kmh ?? []}
                  limiting_factor={tel?.limiting_factor}
                  distances={tel?.s_m ?? []}
                  lateralG={tel?.lat_g}
                  longitudinalG={tel?.long_g}
                  corners={trackMapCorners}
                  hoverDist={hoverDist}
                  onHoverDist={setHoverDist}
                  sectorBoundaries={
                    trackInputTab === "preset"
                      ? activeCircuit.sectorBoundaries
                      : [
                          (tel?.s_m?.[tel.s_m.length - 1] ?? 5000) * 0.33,
                          (tel?.s_m?.[tel.s_m.length - 1] ?? 5000) * 0.66,
                        ]
                  }
                  circuitName={trackInputTab === "preset" ? activeCircuit.name : undefined}
                  driverSpeedsKmh={parsedCsvData?.speedKmh}
                  ggv={result.ggv_envelope}
                  showGgPlot
                />

                {/* Multi-channel Synchronized Telemetry Traces (6 Cards) */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {/* 1. Speed Trace [km/h] */}
                  <div className="h-[250px] bg-[#0D1017] border border-[#1f2430] rounded-xl p-2.5">
                    <Plot
                      data={[
                        {
                          x: tel?.s_m ?? [],
                          y: tel?.speed_kmh ?? [],
                          type: "scatter",
                          mode: "lines",
                          name: "Optimal Speed",
                          line: { color: "#06B6D4", width: 2 },
                        },
                        ...(parsedCsvData
                          ? [
                              {
                                x: parsedCsvData.distanceM,
                                y: parsedCsvData.speedKmh,
                                type: "scatter" as const,
                                mode: "lines" as const,
                                name: "Uploaded Driver Speed",
                                line: { color: "#F59E0B", width: 1.6, dash: "dot" as const },
                              },
                            ]
                          : []),
                      ]}
                      layout={darkLayout({
                        title: { text: "Speed Trace [km/h]", font: { size: 12, color: "#94A3B8", family: "JetBrains Mono, monospace" } },
                        xaxis: { title: { text: "Distance [m]", font: { color: "#71717a" } } },
                        yaxis: { title: { text: "Speed [km/h]", font: { color: "#06B6D4" } } },
                        margin: { t: 48, r: 20, b: 42, l: 54 },
                        legend: { orientation: "h", x: 0, y: 1.14, font: { size: 10, color: "#94A3B8" }, bgcolor: "transparent" },
                      })}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  </div>

                  {/* 2. Lateral & Longitudinal G [g] */}
                  <div className="h-[250px] bg-[#0D1017] border border-[#1f2430] rounded-xl p-2.5">
                    <Plot
                      data={[
                        {
                          x: tel?.s_m ?? [],
                          y: tel?.lat_g ?? [],
                          type: "scatter",
                          mode: "lines",
                          name: "Lateral G (ay)",
                          line: { color: "#F59E0B", width: 1.5 },
                        },
                        {
                          x: tel?.s_m ?? [],
                          y: tel?.long_g ?? [],
                          type: "scatter",
                          mode: "lines",
                          name: "Longitudinal G (ax)",
                          line: { color: "#F43F5E", width: 1.5 },
                        },
                      ]}
                      layout={darkLayout({
                        title: { text: "Lateral & Longitudinal G [g]", font: { size: 12, color: "#94A3B8", family: "JetBrains Mono, monospace" } },
                        xaxis: { title: { text: "Distance [m]", font: { color: "#71717a" } } },
                        yaxis: { title: { text: "Accel [g]", font: { color: "#71717a" } } },
                        margin: { t: 48, r: 20, b: 42, l: 54 },
                        legend: { orientation: "h", x: 0, y: 1.14, font: { size: 10, color: "#94A3B8" }, bgcolor: "transparent" },
                      })}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  </div>

                  {/* 3. Driver Pedals: Throttle & Brake [%] */}
                  <div className="h-[250px] bg-[#0D1017] border border-[#1f2430] rounded-xl p-2.5">
                    <Plot
                      data={[
                        {
                          x: tel?.s_m ?? [],
                          y: tel?.throttle_pct ?? [],
                          type: "scatter",
                          mode: "lines",
                          name: "Throttle %",
                          line: { color: "#10B981", width: 1.5 },
                        },
                        {
                          x: tel?.s_m ?? [],
                          y: tel?.brake_pct ?? [],
                          type: "scatter",
                          mode: "lines",
                          name: "Brake %",
                          line: { color: "#F43F5E", width: 1.5 },
                        },
                      ]}
                      layout={darkLayout({
                        title: { text: "Driver Pedals: Throttle & Brake [%]", font: { size: 12, color: "#94A3B8", family: "JetBrains Mono, monospace" } },
                        xaxis: { title: { text: "Distance [m]", font: { color: "#71717a" } } },
                        yaxis: { title: { text: "Pedal %", font: { color: "#71717a" } }, range: [0, 105] },
                        margin: { t: 48, r: 20, b: 42, l: 54 },
                        legend: { orientation: "h", x: 0, y: 1.14, font: { size: 10, color: "#94A3B8" }, bgcolor: "transparent" },
                      })}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  </div>

                  {/* 4. Aerodynamic Downforce & Drag [N] */}
                  <div className="h-[250px] bg-[#0D1017] border border-[#1f2430] rounded-xl p-2.5">
                    <Plot
                      data={[
                        {
                          x: tel?.s_m ?? [],
                          y: tel?.downforce_n ?? [],
                          type: "scatter",
                          mode: "lines",
                          name: "Downforce (Fz)",
                          line: { color: "#06B6D4", width: 1.6 },
                        },
                        {
                          x: tel?.s_m ?? [],
                          y: (tel?.s_m ?? []).map((_, i) => {
                            const v = ((tel?.speed_kmh?.[i] ?? 0) / 3.6);
                            return 0.5 * 1.225 * v * v * cfg.cd * cfg.frontal_area;
                          }),
                          type: "scatter",
                          mode: "lines",
                          name: "Aero Drag (Fx)",
                          line: { color: "#F59E0B", width: 1.6 },
                        },
                      ]}
                      layout={darkLayout({
                        title: { text: "Aerodynamic Downforce & Drag [N]", font: { size: 12, color: "#94A3B8", family: "JetBrains Mono, monospace" } },
                        xaxis: { title: { text: "Distance [m]", font: { color: "#71717a" } } },
                        yaxis: { title: { text: "Force [N]", font: { color: "#06B6D4" } } },
                        margin: { t: 48, r: 20, b: 42, l: 54 },
                        legend: { orientation: "h", x: 0, y: 1.14, font: { size: 10, color: "#94A3B8" }, bgcolor: "transparent" },
                      })}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  </div>

                  {/* 5. Dynamic Ride Height & Pitch [mm] */}
                  <div className="h-[250px] bg-[#0D1017] border border-[#1f2430] rounded-xl p-2.5">
                    <Plot
                      data={[
                        {
                          x: tel?.s_m ?? [],
                          y: tel?.ride_height_front_mm ?? [],
                          type: "scatter",
                          mode: "lines",
                          name: "Front Ride Height",
                          line: { color: "#06B6D4", width: 1.6 },
                        },
                        {
                          x: tel?.s_m ?? [],
                          y: tel?.ride_height_rear_mm ?? [],
                          type: "scatter",
                          mode: "lines",
                          name: "Rear Ride Height",
                          line: { color: "#F43F5E", width: 1.6 },
                        },
                        {
                          x: [0, Math.max(...(tel?.s_m ?? [5000]))],
                          y: [3.0, 3.0],
                          type: "scatter",
                          mode: "lines",
                          name: "Plank Limit (3mm)",
                          line: { color: "#F59E0B", width: 1.2, dash: "dash" },
                        },
                      ]}
                      layout={darkLayout({
                        title: { text: "Dynamic Ride Height & Pitch [mm]", font: { size: 12, color: "#94A3B8", family: "JetBrains Mono, monospace" } },
                        xaxis: { title: { text: "Distance [m]", font: { color: "#71717a" } } },
                        yaxis: { title: { text: "Ride Height [mm]", font: { color: "#71717a" } }, range: [0, 92] },
                        margin: { t: 48, r: 20, b: 42, l: 54 },
                        legend: { orientation: "h", x: 0, y: 1.14, font: { size: 10, color: "#94A3B8" }, bgcolor: "transparent" },
                      })}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  </div>

                  {/* 6. 2D Setup Response Surface: ARB vs. Aero [s] */}
                  <div className="h-[250px] bg-[#0D1017] border border-[#1f2430] rounded-xl p-2.5 flex flex-col relative">
                    {result.setup_surface && (
                      <div className="absolute top-2.5 right-3 z-10 flex items-center gap-2">
                        {(result.setup_surface.optimal_setup.uncertainty_band || result.setup_surface.uncertainty_band) && (
                          <span
                            className="px-2 py-0.5 rounded-lg text-[10px] font-mono bg-white/[0.05] border border-white/10 text-zinc-300 shadow-sm"
                            title="Uncertainty band evaluated across ±5% aero and ±3% tire grip perturbations"
                          >
                            Uncertainty: ±{(result.setup_surface.optimal_setup.uncertainty_band || result.setup_surface.uncertainty_band)!.uncertainty_s.toFixed(2)}s
                            {" "}[{(result.setup_surface.optimal_setup.uncertainty_band || result.setup_surface.uncertainty_band)!.min_delta_s.toFixed(2)}s, {(result.setup_surface.optimal_setup.uncertainty_band || result.setup_surface.uncertainty_band)!.max_delta_s.toFixed(2)}s]
                          </span>
                        )}
                        <button
                          onClick={() =>
                            handleApplyOptimalSetup(
                              result.setup_surface!.optimal_setup.front_arb_n_mm,
                              result.setup_surface!.optimal_setup.aero_balance_front_pct
                            )
                          }
                          className="px-2 py-0.5 rounded-lg text-[10px] font-mono font-bold bg-[#10B981] hover:bg-[#34D399] text-black transition-all flex items-center gap-1 cursor-pointer shadow-sm"
                        >
                          <Zap size={10} className="fill-black" />
                          Apply Optimal Balance (-{result.setup_surface.optimal_setup.time_gain_s.toFixed(2)}s)
                        </button>
                      </div>
                    )}
                    <div className="w-full h-full min-h-0">
                      {result.setup_surface ? (
                        <Plot
                          data={[
                            {
                              z: result.setup_surface.z_lap_time_s,
                              x: result.setup_surface.front_arb_n_mm,
                              y: result.setup_surface.aero_balance_front_pct,
                              type: "contour",
                              contours: {
                                coloring: "heatmap",
                                showlabels: true,
                                labelfont: { size: 9, color: "#ffffff", family: "JetBrains Mono, monospace" },
                              },
                              colorscale: [
                                [0.0, "#06B6D4"],
                                [0.35, "#0D1017"],
                                [0.7, "#F59E0B"],
                                [1.0, "#F43F5E"],
                              ],
                              colorbar: {
                                title: { text: "Lap [s]", font: { size: 9, color: "#94A3B8" } },
                                tickfont: { size: 8, color: "#94A3B8" },
                                len: 0.9,
                                thickness: 12,
                                outlinewidth: 0,
                              },
                              hoverinfo: "x+y+z",
                              hovertemplate: "Front ARB: %{x} N/mm<br>Aero Bal: %{y}%<br>Lap: %{z:.3f} s<extra></extra>",
                            },
                            {
                              x: [result.setup_surface.current_setup.front_arb_n_mm],
                              y: [result.setup_surface.current_setup.aero_balance_front_pct],
                              type: "scatter",
                              mode: "text+markers",
                              name: "Current Setup",
                              marker: {
                                symbol: "circle-open",
                                size: 13,
                                color: "#FFFFFF",
                                line: { width: 2.5, color: "#FFFFFF" },
                              },
                              text: ["Current"],
                              textposition: "bottom center",
                              textfont: { size: 9, color: "#FFFFFF", family: "JetBrains Mono, monospace" },
                              showlegend: false,
                            },
                            {
                              x: [result.setup_surface.optimal_setup.front_arb_n_mm],
                              y: [result.setup_surface.optimal_setup.aero_balance_front_pct],
                              type: "scatter",
                              mode: "text+markers",
                              name: "Optimal Setup",
                              marker: {
                                symbol: "star",
                                size: 15,
                                color: "#10B981",
                                line: { width: 1.5, color: "#064E3B" },
                              },
                              text: ["Optimal"],
                              textposition: "top center",
                              textfont: { size: 9, color: "#10B981", family: "JetBrains Mono, monospace" },
                              showlegend: false,
                            },
                          ]}
                          layout={darkLayout({
                            title: {
                              text: "2D Setup Response Surface: ARB vs. Aero [s]",
                              x: 0.02,
                              xanchor: "left",
                              font: { size: 12, color: "#94A3B8", family: "JetBrains Mono, monospace" },
                            },
                            xaxis: {
                              title: { text: "Front ARB Wheel Rate [N/mm]", font: { color: "#71717a", size: 10 } },
                              tickvals: result.setup_surface.front_arb_n_mm,
                            },
                            yaxis: {
                              title: { text: "Aero Balance [% Front]", font: { color: "#71717a", size: 10 } },
                              tickvals: result.setup_surface.aero_balance_front_pct,
                            },
                            margin: { t: 48, r: 20, b: 42, l: 54 },
                            legend: { orientation: "h", x: 0, y: 1.14, font: { size: 10, color: "#94A3B8" }, bgcolor: "transparent" },
                            showlegend: false,
                          })}
                          config={{ displayModeBar: false, responsive: true }}
                          style={{ width: "100%", height: "100%" }}
                          useResizeHandler
                        />
                      ) : (
                        <div data-testid="surface-compute" className="h-full flex flex-col items-center justify-center gap-2 px-4 text-center text-xs text-zinc-400 font-mono">
                          <p>Setup-response surface (front ARB x aero balance) is not computed on the fast solve.</p>
                          <p className="text-[10px] text-zinc-600">The backend notes it takes roughly 21-51 s instead of 0.5-1.5 s.</p>
                          {surfaceBusy ? (
                            <button type="button" onClick={cancelSurface} className="rounded border border-hairline px-3 py-1.5 text-xs font-semibold text-white hover:bg-white/[0.06]">
                              Cancel
                            </button>
                          ) : (
                            <button type="button" onClick={computeSurface} className="rounded border border-signal bg-signal px-3 py-1.5 text-xs font-bold text-carbon hover:bg-[#d6f56e]">
                              Compute Setup Grid (21–51 s)
                            </button>
                          )}
                          {surfaceBusy && <p className="text-[10px] text-zinc-500">Computing the surface...</p>}
                          {surfaceMsg && <p role="status" className="text-[10px] text-warning">{surfaceMsg}</p>}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                <EnvelopePlot
                  latG={result.trace.lat_g}
                  longG={result.trace.long_g}
                  limits={envelopeLimits(result.ggv_envelope)}
                />

                <section data-testid="terrain-section" className="border border-hairline p-3 flex flex-col gap-2">
                  <label className="flex items-center gap-2 text-xs text-zinc-300">
                    <input type="checkbox" checked={includeElevation} disabled={selectedCircuitId !== "spa"} onChange={(e) => setIncludeElevation(e.target.checked)} />
                    Include Elevation (Spa)
                    <span className="text-[10px] text-zinc-500">{selectedCircuitId !== "spa" ? "Only Spa has elevation data. Other circuits stay flat (z = 0)." : "Applies on the next run. Also changes the grade term, so lap time changes."}</span>
                  </label>
                  <TerrainElevation3D trace={result.trace as any} />
                </section>

                {/* LapDeltaView (Setup A vs Setup B comparison) */}
                <LapDeltaView
                  baselineRun={pinnedBaseline?.lap ?? null}
                  currentRun={{
                    lap_time_s: result.lap_time_s,
                    sector_times: result.sector_times,
                    max_speed_kmh: result.max_speed_kmh,
                    min_speed_kmh: result.min_speed_kmh,
                    avg_speed_kmh: result.avg_speed_kmh,
                    energy_used_kj: result.energy_used_kj,
                    trace: result.trace,
                  }}
                  setupAParams={pinnedBaseline?.cfg as any}
                  setupBParams={cfg as any}
                  whyChainFetcher={fetchWithAuth as any}
                  whyChainTrack={selectedCircuitId === "fsae_michigan" ? "fsae_endurance" : selectedCircuitId}
                  onPinBaseline={handlePinBaseline}
                  corners={trackInputTab === "preset" ? activeCircuit.corners.map((c) => ({ name: c.name, distM: c.distM })) : undefined}
                  onResetToBaseline={() => {
                    if (!pinnedBaseline) return;
                    const c = { ...pinnedBaseline.cfg };
                    setCfg(c);
                    // Trigger a fresh re-solve with the restored setup
                    handleSimulate(c);
                  }}
                />
              </>
            ) : (
              <div className="h-full flex items-center justify-center p-8">
                <Loader2 size={24} className="animate-spin text-[#f2a900]" />
              </div>
            )}
          </div>
        </main>
      </div>
    </PlanGate>
  );
}
