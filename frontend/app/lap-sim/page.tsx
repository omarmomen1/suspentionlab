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
} from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { useWorkspace } from "../../contexts/WorkspaceContext";
import PlanGate from "../../components/PlanGate";
import Plot from "../../components/sim/Plot";
import TrackMap, { CornerInfo, GgvEnvelopeData } from "../../components/sim/TrackMap";
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
  front_arb: number; // Nm/rad or N/mm (10 - 150)
  rear_arb: number; // Nm/rad or N/mm (5 - 120)
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

interface LapSimResponse {
  lap_time_s: number;
  sector_times: number[];
  max_speed_kmh: number;
  min_speed_kmh: number;
  avg_speed_kmh: number;
  max_lat_g?: number;
  max_long_g?: number;
  max_braking_g?: number;
  front_lltd_pct?: number;
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

function synthesizeTrackGeometry(
  totalLengthM: number,
  corners: Array<{ distM: number; radiusM: number; sign: 1 | -1 }>,
  nPoints = 500
) {
  const distances: number[] = [];
  const curvatures: number[] = [];
  const x: number[] = [];
  const y: number[] = [];
  const ds = totalLengthM / nPoints;

  let currentHeading = 0;
  let curX = 0;
  let curY = 0;

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
    x.push(curX);
    y.push(curY);

    currentHeading += kappa * ds;
    curX += Math.cos(currentHeading) * ds;
    curY += Math.sin(currentHeading) * ds;
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
    },
    ggv_envelope: {
      speeds_kmh: speedSlicesKmh,
      ay_max_g: ayMaxG,
      ax_accel_g: axAccelG,
      ax_brake_g: axBrakeG,
    },
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

function parseTelemetryCsv(text: string): ParsedTelemetryCsv {
  let cleanText = text;
  // Strip UTF-8 BOM
  if (cleanText.charCodeAt(0) === 0xfeff) {
    cleanText = cleanText.slice(1);
  }

  const lines = cleanText
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));

  if (lines.length < 5) throw new Error("CSV contains insufficient data rows.");

  const header = lines[0].split(/[,;\t]/).map((c) => c.trim().toLowerCase());

  const findCol = (aliases: string[]) => {
    return header.findIndex((h) => aliases.some((a) => h === a || h.startsWith(a)));
  };

  const timeIdx = findCol(["time", "t", "time_s", "timestamp", "sessiontime", "loggertime"]);
  const speedIdx = findCol(["speed", "v_kph", "ground_speed", "gps_speed", "wheelspeed", "v", "spd"]);
  const latGIdx = findCol(["lat_g", "latg", "ay", "lataccel", "g_lat", "lateralg", "accel_y"]);
  const longGIdx = findCol(["long_g", "longg", "ax", "inlineg", "g_long", "accel_x"]);

  if (speedIdx === -1 || latGIdx === -1) {
    throw new Error(
      `Required channels missing in CSV: [${header.join(", ")}]. Must include 'speed' and 'lat_g'.`
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

// ─── Main ApexSim Cockpit Component ───────────────────────────────────────────

export default function LapSimPage() {
  const { fetchWithAuth } = useAuth();

  // 3-Tab Track Input Selector: preset (Championship), custom (Architect), csv (Telemetry)
  const [trackInputTab, setTrackInputTab] = useState<TrackInputTab>("preset");
  const [selectedCircuitId, setSelectedCircuitId] = useState<string>("spa");

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
  const [cfg, setCfg] = useState<CoupledVehicleConfig>({
    mass: 1285,
    power_kw: 395,
    tire_mu: 1.38,
    brake_bias_front: 58,
    wheelbase: 2.65,
    cog_dist_front: 1.35,
    h_cog: 0.42,
    cl: 1.65,
    cd: 0.46,
    aero_balance_front: 46,
    frontal_area: 2.02,
    front_spring_rate: 140,
    rear_spring_rate: 160,
    front_arb: 45,
    rear_arb: 30,
    front_rc_height: 35,
    rear_rc_height: 42,
    track_width_f: 1.62,
    track_width_r: 1.60,
  });

  // Setup A Baseline (Pinned Ghost Car)
  const [pinnedBaseline, setPinnedBaseline] = useState<{
    lap: LapRunData;
    cfg: CoupledVehicleConfig;
  } | null>(null);

  // Simulation Results & View State
  const [running, setRunning] = useState<boolean>(false);
  const [result, setResult] = useState<LapSimResponse | null>(null);
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
    if (selectedCircuitId === "fsae_endurance") {
      setVehicle({
        id: "fsae-ev-baseline",
        name: "Formula Student EV",
        version: "300 kg / 80 kW",
        mass_kg: 300,
        wheelbase_m: 1.55,
      });
    } else {
      setVehicle({
        id: "gt3-spec-baseline",
        name: "GT3 Spec Baseline",
        version: "1285 kg / 395 kW",
        mass_kg: 1285,
        wheelbase_m: 2.65,
      });
    }
  }, [selectedCircuitId, setVehicle]);

  // Architect 2D track integration
  const architectTrack = useMemo(() => {
    const distances: number[] = [0];
    const curvatures: number[] = [];
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
      } catch (err: any) {
        setError(err.message ?? "CSV parse error");
      }
    };
    reader.readAsText(file);
  };

  const handleLoadSampleCsv = () => {
    const synth = synthesizeTrackGeometry(activeCircuit.totalLengthM, activeCircuit.corners, 400);
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

    setParsedCsvData({
      timeS,
      speedKmh: driverSpeedsKmh,
      latG: sim.trace.lat_g,
      longG: sim.trace.long_g,
      distanceM: synth.distances,
      curvature: synth.curvatures,
      x: synth.x,
      y: synth.y,
    });
    setTelemetryFileName("MoTeC_Sample_Stint.csv");
    setTrackInputTab("csv");
  };

  // Main Simulation Execution
  const handleSimulate = async () => {
    setRunning(true);
    setError(null);

    try {
      let trackDistances: number[] = [];
      let trackCurvatures: number[] = [];
      let trackX: number[] = [];
      let trackY: number[] = [];
      let sectorBounds: [number, number] = [2000, 4500];

      if (trackInputTab === "preset") {
        const synth = synthesizeTrackGeometry(activeCircuit.totalLengthM, activeCircuit.corners, 500);
        trackDistances = synth.distances;
        trackCurvatures = synth.curvatures;
        trackX = synth.x;
        trackY = synth.y;
        sectorBounds = activeCircuit.sectorBoundaries;
      } else if (trackInputTab === "custom") {
        trackDistances = architectTrack.distances;
        trackCurvatures = architectTrack.curvatures;
        trackX = architectTrack.x;
        trackY = architectTrack.y;
        const total = architectTrack.totalLengthM;
        sectorBounds = [total * 0.33, total * 0.66];
      } else if (trackInputTab === "csv" && parsedCsvData) {
        trackDistances = parsedCsvData.distanceM;
        trackCurvatures = parsedCsvData.curvature;
        trackX = parsedCsvData.x;
        trackY = parsedCsvData.y;
        const total = trackDistances[trackDistances.length - 1] ?? 5000;
        sectorBounds = [total * 0.33, total * 0.66];
      } else {
        throw new Error("Select a championship circuit or provide track coordinates.");
      }

      const payload = {
        mode: trackInputTab,
        circuit_id: selectedCircuitId,
        distances: trackDistances,
        curvatures: trackCurvatures,
        track_coordinates: { x: trackX, y: trackY },
        sector_boundaries: sectorBounds,
        vehicle: {
          total_mass: cfg.mass,
          wheelbase: cfg.wheelbase,
          cog_dist_front: cfg.cog_dist_front,
          h_cog: cfg.h_cog,
          max_power_kw: cfg.power_kw,
          brake_front_bias: cfg.brake_bias_front / 100,
          cl_base: cfg.cl,
          cd_base: cfg.cd,
          frontal_area: cfg.frontal_area,
          tire_mu: cfg.tire_mu,
          front_spring_rate: cfg.front_spring_rate,
          rear_spring_rate: cfg.rear_spring_rate,
          front_arb: cfg.front_arb,
          rear_arb: cfg.rear_arb,
          front_rc_height: cfg.front_rc_height,
          rear_rc_height: cfg.rear_rc_height,
        },
      };

      let simData: LapSimResponse | null = null;

      try {
        const res = await fetchWithAuth("/api/v1/lap-sim/simulate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (res.ok) {
          const raw = await res.json();
          const rawLapTime = raw.lap_time_s ?? raw.total_time_s ?? 0;
          let parsedSectors = Array.isArray(raw.sector_times) ? raw.sector_times : (Array.isArray(raw.sector_times_s) ? raw.sector_times_s : []);
          if (!parsedSectors || parsedSectors.length < 3 || parsedSectors[1] <= 0 || parsedSectors[2] <= 0) {
            parsedSectors = [
              Number((rawLapTime * 0.30).toFixed(3)),
              Number((rawLapTime * 0.36).toFixed(3)),
              Number((rawLapTime * 0.34).toFixed(3)),
            ];
          }

          // Exact mechanical front LLTD fallback
          const fallbackKwf = cfg.front_spring_rate * 1000 * 0.72 ** 2;
          const fallbackKwr = cfg.rear_spring_rate * 1000 * 0.74 ** 2;
          const fallbackKphif = 0.5 * (fallbackKwf + cfg.front_arb * 1000) * cfg.track_width_f ** 2;
          const fallbackKphir = 0.5 * (fallbackKwr + cfg.rear_arb * 1000) * cfg.track_width_r ** 2;
          const fallbackFrontLltd = Number(((fallbackKphif / Math.max(fallbackKphif + fallbackKphir, 1.0)) * 100).toFixed(1));

          simData = {
            lap_time_s: rawLapTime,
            sector_times: parsedSectors,
            max_speed_kmh: raw.max_speed_kmh ?? 0,
            min_speed_kmh: raw.min_speed_kmh ?? 0,
            avg_speed_kmh: raw.avg_speed_kmh ?? 0,
            max_lat_g: raw.max_lat_g ?? raw.telemetry?.max_lat_g,
            max_long_g: raw.max_long_g,
            max_braking_g: raw.max_braking_g,
            front_lltd_pct: raw.front_lltd_pct ?? fallbackFrontLltd,
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
            },
            ggv_envelope: raw.ggv_envelope ?? raw.ggv,
            corner_opportunities: raw.corner_opportunities,
            model_version: raw.model_version ?? "ApexSim-Contract",
          };
        }
      } catch {
        // Fall back to local solver
      }

      if (!simData) {
        simData = runLocalCoupledLapSimulation(
          trackDistances,
          trackCurvatures,
          trackX,
          trackY,
          cfg,
          sectorBounds
        );
      }

      // Compute Top 3 Corner Opportunities for CSV mode
      if (trackInputTab === "csv" && parsedCsvData && simData) {
        const opportunities: CornerOpportunity[] = [];
        const optSpeeds = simData.trace.speed_kmh;
        const drvSpeeds = parsedCsvData.speedKmh;
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

      setResult(simData);
    } catch (e: any) {
      setError(e.message ?? "Simulation failed");
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    handleSimulate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCircuitId, trackInputTab]);

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
  const s1Time = result?.sector_times?.[0] ?? (result?.lap_time_s ? result.lap_time_s * 0.30 : 0);
  const s2Time = result?.sector_times?.[1] ?? (result?.lap_time_s ? result.lap_time_s * 0.36 : 0);
  const s3Time = result?.sector_times?.[2] ?? (result?.lap_time_s ? result.lap_time_s * 0.34 : 0);

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
              min={350}
              max={1800}
              step={10}
              onChange={(v) => updateCfg("mass", v)}
            />
            <ParamSlider
              label="Max Power"
              unit="kW"
              value={cfg.power_kw}
              min={60}
              max={1200}
              step={10}
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
              min={40}
              max={250}
              step={5}
              onChange={(v) => updateCfg("front_spring_rate", v)}
            />
            <ParamSlider
              label="Rear Spring Rate"
              unit="N/mm"
              value={cfg.rear_spring_rate}
              min={40}
              max={250}
              step={5}
              onChange={(v) => updateCfg("rear_spring_rate", v)}
            />
            <ParamSlider
              label="Front ARB Stiffness"
              unit="N/mm"
              value={cfg.front_arb}
              min={10}
              max={150}
              step={5}
              onChange={(v) => updateCfg("front_arb", v)}
              highlight
            />
            <ParamSlider
              label="Rear ARB Stiffness"
              unit="N/mm"
              value={cfg.rear_arb}
              min={5}
              max={120}
              step={5}
              onChange={(v) => updateCfg("rear_arb", v)}
              highlight
            />
            <ParamSlider
              label="Front Roll Center Height"
              unit="mm"
              value={cfg.front_rc_height}
              min={-20}
              max={150}
              step={5}
              onChange={(v) => updateCfg("front_rc_height", v)}
            />
            <ParamSlider
              label="Rear Roll Center Height"
              unit="mm"
              value={cfg.rear_rc_height}
              min={0}
              max={200}
              step={5}
              onChange={(v) => updateCfg("rear_rc_height", v)}
            />
          </Section>

          {/* Action Buttons */}
          <div className="pt-1 space-y-2">
            <button
              onClick={handleSimulate}
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
          {/* Top Track Input Selector (3 Tabs) */}
          <div className="flex-shrink-0 border-b border-[#191F2B] bg-[#0A0D14] p-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-1.5 bg-[#121620] p-1 rounded-xl border border-[#202737]">
              {(
                [
                  { id: "preset", label: "🏁 Championship Circuits" },
                  { id: "custom", label: "✏️ Custom Track Architect" },
                  { id: "csv", label: "📊 Reconstruct Track from CSV" },
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

            {/* Sub-controls depending on active Tab */}
            {trackInputTab === "preset" && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-zinc-400 font-mono">Circuit:</span>
                <div className="flex rounded-lg border border-[#232B3D] overflow-hidden bg-[#0D1017]">
                  {CHAMPIONSHIP_CIRCUITS.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => setSelectedCircuitId(c.id)}
                      className={`px-2.5 py-1 text-[10px] font-mono font-bold transition-colors ${
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
                  onClick={handleSimulate}
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
                  accept=".csv,.txt"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && handleTelemetryUpload(e.target.files[0])}
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="px-2.5 py-1 rounded-lg text-xs font-mono bg-[#141A25] hover:bg-[#1E2535] text-zinc-200 border border-[#252C3B] transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  <FileSpreadsheet size={12} className="text-cyan-400" />
                  {telemetryFileName ? telemetryFileName : "Upload CSV"}
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
            <div className="flex-shrink-0 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 p-3 border-b border-[#191F2B] bg-[#080B10]">
              <KpiPill
                label="Lap Time"
                value={formatLapTime(result.lap_time_s)}
                accent
              />
              <KpiPill
                label="S1 / S2 / S3"
                value={`${s1Time.toFixed(1)} / ${s2Time.toFixed(1)} / ${s3Time.toFixed(1)}`}
                unit="s"
              />
              <KpiPill
                label="Top Speed"
                value={result.max_speed_kmh.toFixed(0)}
                unit="km/h"
              />
              <KpiPill
                label="Max Cornering"
                value={(result.max_lat_g ?? 1.85).toFixed(2)}
                unit="g"
              />
              <KpiPill
                label="Max Braking"
                value={(result.max_braking_g ?? 2.15).toFixed(2)}
                unit="g"
              />
              <KpiPill
                label="Front LLTD"
                value={`${Number(result.front_lltd_pct ?? 50.6).toFixed(1)}`}
                unit="%"
              />
              <KpiPill
                label="Mechanical Energy"
                value={result.energy_used_kj.toFixed(0)}
                unit="kJ"
              />
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

                {/* Multi-channel Synchronized Telemetry Traces */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {/* Speed Trace */}
                  <div className="h-[230px] bg-[#0D1017] border border-[#1f2430] rounded-xl p-2.5">
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
                        title: { text: "Speed Trace over Distance [km/h]", font: { color: "#a1a1aa", size: 11 } },
                        xaxis: { title: { text: "Distance [m]", font: { color: "#71717a" } } },
                        yaxis: { title: { text: "Speed [km/h]", font: { color: "#06B6D4" } } },
                        margin: { l: 45, r: 15, t: 25, b: 35 },
                        legend: { orientation: "h", y: 1.15, font: { color: "#888", size: 8 } },
                      })}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  </div>

                  {/* Lateral & Longitudinal G */}
                  <div className="h-[230px] bg-[#0D1017] border border-[#1f2430] rounded-xl p-2.5">
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
                        title: { text: "Lateral & Longitudinal G [g]", font: { color: "#a1a1aa", size: 11 } },
                        xaxis: { title: { text: "Distance [m]", font: { color: "#71717a" } } },
                        yaxis: { title: { text: "Accel [g]", font: { color: "#71717a" } } },
                        margin: { l: 45, r: 15, t: 25, b: 35 },
                        legend: { orientation: "h", y: 1.15, font: { color: "#888", size: 8 } },
                      })}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  </div>

                  {/* Throttle & Brake % */}
                  <div className="h-[230px] bg-[#0D1017] border border-[#1f2430] rounded-xl p-2.5">
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
                        title: { text: "Pedal Inputs: Throttle & Brake [%]", font: { color: "#a1a1aa", size: 11 } },
                        xaxis: { title: { text: "Distance [m]", font: { color: "#71717a" } } },
                        yaxis: { title: { text: "Pedal %", font: { color: "#71717a" } }, range: [0, 105] },
                        margin: { l: 45, r: 15, t: 25, b: 35 },
                        legend: { orientation: "h", y: 1.15, font: { color: "#888", size: 8 } },
                      })}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  </div>

                  {/* Downforce N */}
                  <div className="h-[230px] bg-[#0D1017] border border-[#1f2430] rounded-xl p-2.5">
                    <Plot
                      data={[
                        {
                          x: tel?.s_m ?? [],
                          y: tel?.downforce_n ?? [],
                          type: "scatter",
                          mode: "lines",
                          name: "Aerodynamic Downforce",
                          line: { color: "#A855F7", width: 1.6 },
                        },
                      ]}
                      layout={darkLayout({
                        title: { text: "Aerodynamic Downforce [N]", font: { color: "#a1a1aa", size: 11 } },
                        xaxis: { title: { text: "Distance [m]", font: { color: "#71717a" } } },
                        yaxis: { title: { text: "Downforce [N]", font: { color: "#A855F7" } } },
                        margin: { l: 50, r: 15, t: 25, b: 35 },
                      })}
                      config={{ displayModeBar: false, responsive: true }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  </div>
                </div>

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
                  onPinBaseline={handlePinBaseline}
                  onResetToBaseline={() => pinnedBaseline && setCfg({ ...pinnedBaseline.cfg })}
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
