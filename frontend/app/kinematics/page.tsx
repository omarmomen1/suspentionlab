"use client";

import React, { useState, useCallback, useRef, useEffect, useMemo } from "react";
import Plot from "../../components/sim/Plot";
import { useAuth } from "../../contexts/AuthContext";
import KinematicsModelValidity from "../../components/kinematics/KinematicsModelValidity";
import SuspensionKinematics3D, { KinematicsGeometryMap } from "../../components/kinematics/SuspensionKinematics3D";
import KinematicsComparisonPanel from "../../components/kinematics/KinematicsComparisonPanel";
import KinematicsTargetBandsModal, { DEFAULT_TARGET_BANDS } from "../../components/kinematics/KinematicsTargetBandsModal";
import KinematicsExportModal from "../../components/kinematics/KinematicsExportModal";
import HardpointSensitivityMatrix from "../../components/kinematics/HardpointSensitivityMatrix";
import EngineeringQuestionModal from "../../components/kinematics/EngineeringQuestionModal";
import KinematicsOptimizerPanel from "../../components/kinematics/KinematicsOptimizerPanel";
import FailedPointModal from "../../components/kinematics/FailedPointModal";
import KinematicsBenchmarksModal from "../../components/kinematics/KinematicsBenchmarksModal";
import {
  KinematicsApi,
  KinematicsSolveResponse,
  KinematicsComparisonResponse,
  KinematicsSetupItem,
  KinematicPointResponse,
  HardpointSensitivityMatrixResponse,
  SolverPointDiagnostic,
} from "../../lib/api_client";
import {
  Play,
  Pause,
  RotateCcw,
  Sliders,
  ChevronRight,
  Layers,
  Eye,
  ShieldCheck,
  ShieldAlert,
  Cpu,
  Sparkles,
  RefreshCw,
  BarChart2,
  Box,
  Compass,
  CheckCircle2,
  AlertTriangle,
  ArrowRightLeft,
  Download,
  TrendingUp,
  Activity,
  FileSpreadsheet,
  Target,
  AlertOctagon,
  Award,
} from "lucide-react";

// ─── Coordinate Types ─────────────────────────────────────────────────────────
type HP3 = [number, number, number];

export interface Hardpoints {
  [key: string]: HP3;
  UWI_fwd: HP3;
  UWI_aft: HP3;
  UWO: HP3;
  LWI_fwd: HP3;
  LWI_aft: HP3;
  LWO: HP3;
  TRI: HP3;
  TRO: HP3;
  WC: HP3;
  CP: HP3;
  PRI: HP3;
  PRO: HP3;
}

// ─── Default Hardpoints (Right-front corner, Formula car) ──────────────────────
const DEFAULT_HP: Hardpoints = {
  UWI_fwd: [-50, 80, 300],
  UWI_aft: [50, 80, 300],
  UWO: [0, 650, 295],
  LWI_fwd: [-80, 80, 155],
  LWI_aft: [80, 80, 155],
  LWO: [0, 720, 145],
  TRI: [0, 150, 220],
  TRO: [-15, 710, 205],
  WC: [0, 760, 220],
  CP: [0, 760, 0],
  PRI: [-20, 300, 390],
  PRO: [-15, 690, 250],
};

// ─── Built-in Benchmark Catalog ───────────────────────────────────────────────
const BENCHMARK_CATALOG: Record<
  string,
  {
    id: string;
    name: string;
    category: string;
    description: string;
    zRange: [number, number];
    tireRadiusM: number;
    hardpoints: Hardpoints;
    /** Static camber built into the upright spindle [deg]; omitted = 0.0 (backend default). */
    static_camber_deg?: number;
    /** Static toe [deg, + = toe-out]; omitted = 0.0 (backend default). */
    static_toe_deg?: number;
  }
> = {
  gt3_touring: {
    id: "gt3_touring",
    name: "GT3 Touring Car (Baseline)",
    category: "GT / Sports Car",
    description: "Production-derived GT3 racecar double wishbone geometry with long control arms for high-speed stability.",
    zRange: [-50, 50],
    tireRadiusM: 0.330,
    static_camber_deg: -1.2,
    static_toe_deg: 0.0,
    hardpoints: {
      UWI_fwd: [-50.0, 300.0, 340.0],
      UWI_aft: [50.0, 300.0, 340.0],
      UWO: [-19.0, 660.0, 425.0],
      LWI_fwd: [-80.0, 300.0, 202.0],
      LWI_aft: [80.0, 300.0, 202.0],
      LWO: [0.0, 692.0, 235.0],
      TRI: [0.0, 200.0, 190.0],
      TRO: [-15.0, 710.0, 230.0],
      WC: [-7.05, 758.0, 330.0],
      CP: [-7.05, 758.0, 0.0],
      PRI: [-20.0, 350.0, 620.0],
      PRO: [-15.0, 610.0, 268.0],
    },
  },
  gt3_camber_shim_5mm: {
    id: "gt3_camber_shim_5mm",
    name: "GT3 Touring (+5mm Camber Shim / Lower Pivot Outboard)",
    category: "GT / Sports Car Variant",
    description: "GT3 corner modified with 5mm outboard shim at lower ball joint (LWO Y+5mm) for enhanced static camber & lateral grip.",
    zRange: [-50, 50],
    tireRadiusM: 0.330,
    static_camber_deg: -1.2,
    static_toe_deg: 0.0,
    hardpoints: {
      UWI_fwd: [-50.0, 300.0, 340.0],
      UWI_aft: [50.0, 300.0, 340.0],
      UWO: [-19.0, 660.0, 425.0],
      LWI_fwd: [-80.0, 300.0, 202.0],
      LWI_aft: [80.0, 300.0, 202.0],
      LWO: [0.0, 697.0, 235.0],
      TRI: [0.0, 200.0, 190.0],
      TRO: [-15.0, 710.0, 230.0],
      WC: [-7.05, 758.0, 330.0],
      CP: [-7.05, 758.0, 0.0],
      PRI: [-20.0, 350.0, 620.0],
      PRO: [-15.0, 610.0, 268.0],
    },
  },
  formula_sae: {
    id: "formula_sae",
    name: "Formula SAE Prototype",
    category: "Open Wheel Formula",
    description: "Open-wheel formula car with aggressive camber recovery, controlled roll center, and direct pushrod actuation.",
    zRange: [-30, 30],
    tireRadiusM: 0.254,
    hardpoints: {
      UWI_fwd: [-50.0, 100.0, 295.0],
      UWI_aft: [50.0, 100.0, 295.0],
      UWO: [-7.5, 495.0, 340.0],
      LWI_fwd: [-80.0, 100.0, 172.0],
      LWI_aft: [80.0, 100.0, 172.0],
      LWO: [7.5, 535.0, 185.0],
      TRI: [-15.0, 100.0, 215.1],
      TRO: [-20.0, 511.0, 239.2],
      WC: [0.0, 600.0, 254.0],
      CP: [0.0, 600.0, 0.0],
      PRI: [-20.0, 280.0, 445.0],
      PRO: [-15.0, 515.0, 200.0],
    },
  },
  formula_sae_low_rc: {
    id: "formula_sae_low_rc",
    name: "Formula SAE (Low Roll Center / Raised Inboard UWI)",
    category: "Open Wheel Formula Variant",
    description: "FSAE corner with raised upper wishbone inboard pivots (UWI Z+5mm), shifting roll center downward to soften front roll couple.",
    zRange: [-30, 30],
    tireRadiusM: 0.254,
    hardpoints: {
      UWI_fwd: [-50.0, 100.0, 300.0],
      UWI_aft: [50.0, 100.0, 300.0],
      UWO: [-7.5, 495.0, 340.0],
      LWI_fwd: [-80.0, 100.0, 172.0],
      LWI_aft: [80.0, 100.0, 172.0],
      LWO: [7.5, 535.0, 185.0],
      TRI: [-15.0, 100.0, 216.8],
      TRO: [-20.0, 511.0, 239.2],
      WC: [0.0, 600.0, 254.0],
      CP: [0.0, 600.0, 0.0],
      PRI: [-20.0, 280.0, 445.0],
      PRO: [-15.0, 515.0, 200.0],
    },
  },
  lmp_prototype: {
    id: "lmp_prototype",
    name: "LMP / Hypercar Prototype",
    category: "Endurance Prototype",
    description: "High-downforce endurance prototype with stiff kinematics, low scrub radius to minimize steering torque.",
    zRange: [-35, 35],
    tireRadiusM: 0.340,
    hardpoints: {
      UWI_fwd: [-60.0, 90.0, 370.0],
      UWI_aft: [60.0, 90.0, 370.0],
      UWO: [-9.0, 685.0, 435.0],
      LWI_fwd: [-90.0, 90.0, 215.0],
      LWI_aft: [90.0, 90.0, 215.0],
      LWO: [9.0, 735.0, 240.0],
      TRI: [-15.0, 90.0, 269.2],
      TRO: [-20.0, 707.5, 308.2],
      WC: [0.0, 820.0, 340.0],
      CP: [0.0, 820.0, 0.0],
      PRI: [-25.0, 410.0, 550.0],
      PRO: [-15.0, 710.0, 265.0],
    },
  },
};

/** Static alignment (spindle camber/toe) for a preset, sent to the solver alongside the hardpoints. */
function staticAlignmentFor(presetId: string): { static_camber_deg: number; static_toe_deg: number } {
  const p = BENCHMARK_CATALOG[presetId];
  return { static_camber_deg: p?.static_camber_deg ?? 0.0, static_toe_deg: p?.static_toe_deg ?? 0.0 };
}

// ─── Plot Theme ───────────────────────────────────────────────────────────────
const THEME = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { color: "#94A3B8", size: 11, family: "Inter, monospace" },
  xaxis: {
    color: "#94A3B8",
    gridcolor: "#161820",
    zerolinecolor: "#2a2d3d",
    tickfont: { color: "#94A3B8", size: 10 },
  },
  yaxis: {
    color: "#94A3B8",
    gridcolor: "#161820",
    zerolinecolor: "#2a2d3d",
    tickfont: { color: "#94A3B8", size: 10 },
  },
  legend: {
    font: { color: "#94A3B8", size: 10 },
    bgcolor: "rgba(0,0,0,0)",
    orientation: "h" as const,
    y: -0.22,
  },
  margin: { l: 55, r: 25, t: 36, b: 50 },
  autosize: true,
  hoverlabel: { bgcolor: "#0a0c14", bordercolor: "#2f3347", font: { color: "#e2e8f0", size: 11 } },
};

function plotLayout(
  title: string,
  zMin: number,
  zMax: number,
  currentTravel: number,
  xaxis?: object,
  yaxis?: object,
  extraShapes?: any[],
  targetBand?: [number, number]
) {
  const shapes: any[] = [
    // Shaded Droop Region (z < 0)
    {
      type: "rect",
      xref: "x",
      yref: "paper",
      x0: zMin,
      x1: 0,
      y0: 0,
      y1: 1,
      fillcolor: "rgba(56, 189, 248, 0.04)",
      line: { width: 0 },
    },
    // Shaded Bump Region (z > 0)
    {
      type: "rect",
      xref: "x",
      yref: "paper",
      x0: 0,
      x1: zMax,
      y0: 0,
      y1: 1,
      fillcolor: "rgba(251, 146, 60, 0.04)",
      line: { width: 0 },
    },
    // Static Neutral Reference Line (z = 0)
    {
      type: "line",
      xref: "x",
      yref: "paper",
      x0: 0,
      x1: 0,
      y0: 0,
      y1: 1,
      line: { color: "#64748b", width: 1.5, dash: "dash" },
    },
    // Interactive Travel Cursor Indicator
    {
      type: "line",
      xref: "x",
      yref: "paper",
      x0: currentTravel,
      x1: currentTravel,
      y0: 0,
      y1: 1,
      line: { color: "#fbbf24", width: 2, dash: "dot" },
    },
  ];

  // Optional target band corridor shading
  if (targetBand) {
    shapes.push({
      type: "rect",
      xref: "paper",
      yref: "y",
      x0: 0,
      x1: 1,
      y0: targetBand[0],
      y1: targetBand[1],
      fillcolor: "rgba(34, 197, 94, 0.07)",
      line: { color: "rgba(34, 197, 94, 0.3)", width: 1, dash: "dot" },
    });
  }

  if (extraShapes) {
    shapes.push(...extraShapes);
  }

  const annotations: any[] = [
    {
      xref: "x",
      yref: "paper",
      x: zMin * 0.5,
      y: 0.98,
      text: "DROOP",
      showarrow: false,
      font: { size: 9, color: "#38bdf8" },
    },
    {
      xref: "x",
      yref: "paper",
      x: zMax * 0.5,
      y: 0.98,
      text: "BUMP",
      showarrow: false,
      font: { size: 9, color: "#fb923c" },
    },
    {
      xref: "x",
      yref: "paper",
      x: 0,
      y: 0.02,
      text: "STATIC (0mm)",
      showarrow: false,
      font: { size: 8, color: "#94a3b8" },
    },
  ];

  return {
    ...THEME,
    title: { text: title, font: { size: 12, color: "#94a3b8" }, x: 0.02 },
    xaxis: { ...THEME.xaxis, ...xaxis },
    yaxis: { ...THEME.yaxis, ...yaxis },
    shapes,
    annotations,
  };
}

const COLORS = {
  cyan: "#06B6D4",
  violet: "#F59E0B",
  amber: "#F59E0B",
  emerald: "#10B981",
  rose: "#F43F5E",
  blue: "#06B6D4",
  orange: "#F59E0B",
  candidateAmber: "#F59E0B",
  candidateViolet: "#10B981",
};

// ─── KPI Card Component ───────────────────────────────────────────────────────
function KPICard({
  label,
  value,
  unit,
  sub,
  color = "#22d3ee",
  targetRange,
}: {
  label: string;
  value: string | number;
  unit?: string;
  sub?: string;
  color?: string;
  targetRange?: [number, number];
}) {
  const numVal = typeof value === "number" ? value : parseFloat(value);
  const isOutOfBand = targetRange && !isNaN(numVal) && (numVal < targetRange[0] || numVal > targetRange[1]);

  return (
    <div
      className={`bg-[#0b0c12] border rounded-xl p-2.5 flex flex-col gap-0.5 shadow-sm transition-colors ${
        isOutOfBand ? "border-amber-500/60 bg-amber-950/10" : "border-[#1d202b] hover:border-[#2a2f42]"
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="text-[9px] font-bold tracking-[0.14em] text-gray-400 uppercase truncate">
          {label}
        </span>
        {isOutOfBand && (
          <span className="text-[8px] font-mono px-1 py-0.2 rounded bg-amber-500/20 text-amber-300 font-bold">
            OUT
          </span>
        )}
      </div>
      <span className="text-[1.1rem] font-bold font-mono leading-tight tracking-tight" style={{ color }}>
        {typeof value === "number" ? value.toFixed(2) : value}
        {unit && <span className="text-[10px] font-normal text-gray-400 ml-1">{unit}</span>}
      </span>
      {sub && <span className="text-[9px] text-gray-500 leading-tight truncate mt-0.5">{sub}</span>}
    </div>
  );
}

// ─── Hardpoint Editor Row ─────────────────────────────────────────────────────
function HPRow({
  label,
  name,
  value,
  onChange,
  isHovered,
  onHover,
}: {
  label: string;
  name: string;
  value: HP3;
  onChange: (k: string, v: HP3) => void;
  isHovered?: boolean;
  onHover?: (k: string | null) => void;
}) {
  const axes = ["X", "Y", "Z"];
  return (
    <div
      onMouseEnter={() => onHover?.(name)}
      onMouseLeave={() => onHover?.(null)}
      className={`grid grid-cols-[5.2rem_1fr_1fr_1fr] gap-1.5 items-center px-2 py-1 rounded-md transition-colors ${
        isHovered ? "bg-cyan-950/40 border border-cyan-500/60" : "border border-transparent hover:bg-[#12141c]"
      }`}
    >
      <span className={`text-[11px] font-mono truncate ${isHovered ? "text-cyan-300 font-bold" : "text-gray-400"}`}>
        {label}
      </span>
      {[0, 1, 2].map((i) => (
        <input
          key={i}
          type="number"
          step="1"
          value={value[i]}
          title={`${label} ${axes[i]}`}
          aria-label={`${label} ${axes[i]}`}
          className="w-full bg-[#0a0b10] border border-[#1e2230] rounded px-1.5 py-1 text-[11px] text-gray-200 font-mono text-center focus:border-cyan-500 focus:outline-none hover:border-[#333a52] transition-colors"
          onChange={(e) => {
            const next = [...value] as HP3;
            next[i] = parseFloat(e.target.value) || 0;
            onChange(name, next);
          }}
        />
      ))}
    </div>
  );
}

// ─── Main Page Component ──────────────────────────────────────────────────────
export default function KinematicsPage() {
  const { fetchWithAuth } = useAuth();

  // State: Setup A (Baseline / Primary)
  const [hp, setHP] = useState<Hardpoints>(DEFAULT_HP);
  const [hoveredHP, setHoveredHP] = useState<string | null>(null);
  const [selectedPreset, setSelectedPreset] = useState<string>("gt3_touring");

  // State: Setup B (Candidate for Comparison)
  const [hpB, setHPB] = useState<Hardpoints>(BENCHMARK_CATALOG["gt3_camber_shim_5mm"].hardpoints);
  const [selectedPresetB, setSelectedPresetB] = useState<string>("gt3_camber_shim_5mm");
  const [resultB, setResultB] = useState<KinematicsSolveResponse | null>(null);

  // Setup comparison mode toggle
  const [isComparisonMode, setIsComparisonMode] = useState<boolean>(false);
  const [comparisonResult, setComparisonResult] = useState<KinematicsComparisonResponse | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState<boolean>(false);

  // Sweep configuration bounds
  const [zMin, setZMin] = useState<number>(-50);
  const [zMax, setZMax] = useState<number>(50);
  const [nSteps, setNSteps] = useState<number>(33);
  const [tireRadiusM, setTireRadiusM] = useState<number>(0.33);

  // Modals state
  const [isTargetBandsOpen, setIsTargetBandsOpen] = useState<boolean>(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState<boolean>(false);
  const [targetBands, setTargetBands] = useState<Record<string, [number, number]>>(DEFAULT_TARGET_BANDS);

  // Solvers outputs
  const [result, setResult] = useState<KinematicsSolveResponse | null>(null);
  const [backendInfo, setBackendInfo] = useState<{
    backend: string;
    cpp_loaded?: boolean;
    fallback?: boolean;
    solver_version?: string;
    execution_time_ms?: number;
  }>({
    backend: "C++ kinematics_core",
    cpp_loaded: true,
    solver_version: "2.1.0-simd",
  });

  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Travel slider & animation
  const [travelIdx, setTravelIdx] = useState<number>(16);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const animDirectionRef = useRef<number>(1);
  const animTimerRef = useRef<any>(null);

  // Active view tab
  type ViewTab =
    | "workspace"
    | "camber"
    | "rc"
    | "mr"
    | "track"
    | "caster"
    | "derivatives"
    | "comparison"
    | "sensitivity"
    | "optimizer";
  const [activeTab, setActiveTab] = useState<ViewTab>("workspace");

  // Sensitivity Matrix State
  const [sensitivityData, setSensitivityData] = useState<HardpointSensitivityMatrixResponse | null>(null);
  const [loadingSensitivity, setLoadingSensitivity] = useState<boolean>(false);
  const [sensitivityStepSize, setSensitivityStepSize] = useState<number>(1.0);

  // Engineering Question Modal State
  const [isQuestionModalOpen, setIsQuestionModalOpen] = useState<boolean>(false);

  // Benchmarks Modal State
  const [isBenchmarksOpen, setIsBenchmarksOpen] = useState<boolean>(false);

  // Failed Point Root-Cause Modal State
  const [isFailedModalOpen, setIsFailedModalOpen] = useState<boolean>(false);
  const [selectedFailedPoint, setSelectedFailedPoint] = useState<{
    idx: number;
    diag: SolverPointDiagnostic;
    travel: number;
    converged: boolean;
  } | null>(null);

  // Compute sensitivity callback
  const handleComputeSensitivity = useCallback(async () => {
    setLoadingSensitivity(true);
    try {
      const res = await KinematicsApi.computeSensitivity({
        hardpoints: hp,
        target_hardpoints: ["UWI_fwd", "UWI_aft", "UWO", "LWI_fwd", "LWI_aft", "LWO", "TRI", "TRO"],
        axes: ["X", "Y", "Z"],
        step_size_mm: sensitivityStepSize,
        z_min_mm: zMin,
        z_max_mm: zMax,
        n_steps: nSteps,
      });
      setSensitivityData(res);
    } catch (err: any) {
      console.error("Failed to compute sensitivity:", err);
    } finally {
      setLoadingSensitivity(false);
    }
  }, [hp, sensitivityStepSize, zMin, zMax, nSteps]);

  // Handle hardpoint coordinate changes for Setup A
  const handleHP = useCallback((k: keyof Hardpoints, v: HP3) => {
    setHP((prev) => ({ ...prev, [k]: v }));
    setSelectedPreset("custom");
  }, []);

  // Convert presets catalog into KinematicsSetupItem array
  const setupCatalogList: KinematicsSetupItem[] = useMemo(() => {
    return Object.values(BENCHMARK_CATALOG).map((b) => ({
      id: b.id,
      name: b.name,
      category: b.category,
      description: b.description,
      wheel_travel_range: b.zRange,
      tire_radius_m: b.tireRadiusM,
      hardpoints: b.hardpoints as Record<string, [number, number, number]>,
    }));
  }, []);

  // Solve Sweep Function for Setup A
  const solve = useCallback(async () => {
    setLoading(true);
    setError(null);
    const startTime = performance.now();
    try {
      const res = await fetchWithAuth("/api/v1/kinematics/solve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hardpoints: { ...hp, ...staticAlignmentFor(selectedPreset) },
          z_min_mm: zMin,
          z_max_mm: zMax,
          n_steps: nSteps,
        }),
      });

      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `HTTP ${res.status}`);
      }

      const data: KinematicsSolveResponse = await res.json();
      const elapsedMs = performance.now() - startTime;

      setResult(data);
      setBackendInfo({
        backend: data.active_backend || data.backend,
        cpp_loaded: data.backend.toLowerCase().includes("c++"),
        fallback: data.fallback_reason !== null,
        solver_version: data.solver_version,
        execution_time_ms: elapsedMs,
      });

      // Find neutral static step (closest to dz = 0)
      const zeroIdx = data.wheel_travel_mm.findIndex((z) => Math.abs(z) < 1.0);
      setTravelIdx(zeroIdx >= 0 ? zeroIdx : Math.floor(data.n_points / 2));
    } catch (err: any) {
      setError(err.message || "Failed to solve suspension kinematics");
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth, hp, selectedPreset, zMin, zMax, nSteps]);

  // Solve Sweep for Setup B (for comparison overlay)
  const solveSetupB = useCallback(async () => {
    try {
      const res = await fetchWithAuth("/api/v1/kinematics/solve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hardpoints: { ...hpB, ...staticAlignmentFor(selectedPresetB) },
          z_min_mm: zMin,
          z_max_mm: zMax,
          n_steps: nSteps,
        }),
      });
      if (res.ok) {
        const data: KinematicsSolveResponse = await res.json();
        setResultB(data);
      }
    } catch (err) {
      console.error("Failed to solve Setup B sweep:", err);
    }
  }, [fetchWithAuth, hpB, selectedPresetB, zMin, zMax, nSteps]);

  // Run full physics comparison between Setup A and Setup B
  const runComparison = useCallback(async () => {
    setComparisonLoading(true);
    try {
      const nameA = BENCHMARK_CATALOG[selectedPreset]?.name || "Setup A";
      const nameB = BENCHMARK_CATALOG[selectedPresetB]?.name || "Setup B";

      const compData = await KinematicsApi.compareSetups({
        setup_a: { name: nameA, hardpoints: hp },
        setup_b: { name: nameB, hardpoints: hpB },
        z_min_mm: zMin,
        z_max_mm: zMax,
        n_steps: nSteps,
      });

      setComparisonResult(compData);
      await solveSetupB();
    } catch (err: any) {
      console.error("Comparison failed:", err);
    } finally {
      setComparisonLoading(false);
    }
  }, [selectedPreset, selectedPresetB, hp, hpB, zMin, zMax, nSteps, solveSetupB]);

  // Load benchmark preset for Setup A
  const applyPreset = (key: string) => {
    setSelectedPreset(key);
    if (BENCHMARK_CATALOG[key]) {
      const b = BENCHMARK_CATALOG[key];
      setHP(b.hardpoints);
      setZMin(b.zRange[0]);
      setZMax(b.zRange[1]);
      setTireRadiusM(b.tireRadiusM);
    }
  };

  // Load benchmark preset for Setup B
  const applyPresetB = (key: string) => {
    setSelectedPresetB(key);
    if (BENCHMARK_CATALOG[key]) {
      const b = BENCHMARK_CATALOG[key];
      setHPB(b.hardpoints);
    }
  };

  // Swap Setups A and B
  const handleSwapSetups = () => {
    const tempHP = { ...hp };
    const tempPreset = selectedPreset;
    setHP({ ...hpB });
    setSelectedPreset(selectedPresetB);
    setHPB(tempHP);
    setSelectedPresetB(tempPreset);
  };

  // Solve automatically on initial mount
  useEffect(() => {
    solve();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Solve when preset A changes
  useEffect(() => {
    if (selectedPreset !== "custom") {
      solve();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPreset]);

  // Auto-recompute sweep (debounced 250ms) when hardpoints or sweep bounds are edited
  const didInitAutoSolveRef = useRef<boolean>(false);
  useEffect(() => {
    if (!didInitAutoSolveRef.current) {
      didInitAutoSolveRef.current = true;
      return;
    }
    const timer = setTimeout(() => {
      solve();
    }, 250);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hp, zMin, zMax, nSteps]);

  // Automatically solve Setup B and run comparison when comparison mode is enabled
  useEffect(() => {
    if (isComparisonMode) {
      runComparison();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isComparisonMode, selectedPresetB]);

  // Animation player effect for cyclic travel bump <-> droop
  useEffect(() => {
    if (!isPlaying || !result || result.n_points <= 1) {
      if (animTimerRef.current) clearInterval(animTimerRef.current);
      return;
    }

    animTimerRef.current = setInterval(() => {
      setTravelIdx((prev) => {
        let next = prev + animDirectionRef.current;
        if (next >= result.n_points - 1) {
          next = result.n_points - 1;
          animDirectionRef.current = -1;
        } else if (next <= 0) {
          next = 0;
          animDirectionRef.current = 1;
        }
        return next;
      });
    }, 45);

    return () => {
      if (animTimerRef.current) clearInterval(animTimerRef.current);
    };
  }, [isPlaying, result]);

  // Extract live metrics at current travel slider index
  const currentTravel = result?.wheel_travel_mm[travelIdx] ?? 0;
  const currentCamber = result?.camber_deg[travelIdx] ?? 0;
  const currentToe = result?.toe_deg[travelIdx] ?? 0;
  const currentCaster = result?.caster_deg[travelIdx] ?? 0;
  const currentKPI = result?.kpi_deg[travelIdx] ?? 0;
  const currentRC = result?.roll_center_height_mm[travelIdx] ?? 0;
  const currentRCLateral = result?.roll_center_lateral_mm ? result.roll_center_lateral_mm[travelIdx] : 0;
  const currentTrack = result?.track_change_mm[travelIdx] ?? 0;
  const currentWB = result?.wheelbase_change_mm[travelIdx] ?? 0;
  const currentMR = result?.motion_ratio[travelIdx] ?? 0;
  const currentScrub = result?.scrub_radius_mm[travelIdx] ?? 0;

  // Live derivative rates at current index
  const currentCamberGain = result?.derivatives?.camber_gain_deg_per_100mm
    ? result.derivatives.camber_gain_deg_per_100mm[travelIdx]
    : 0;
  const currentToeGain = result?.derivatives?.toe_gain_deg_per_100mm
    ? result.derivatives.toe_gain_deg_per_100mm[travelIdx]
    : 0;
  const currentRCRate = result?.derivatives?.rc_migration_rate
    ? result.derivatives.rc_migration_rate[travelIdx]
    : 0;

  // Geometry mapping for 3D Viewport
  const current3DGeometry: KinematicsGeometryMap =
    result?.geometry_steps && result.geometry_steps[travelIdx]
      ? (result.geometry_steps[travelIdx] as KinematicsGeometryMap)
      : {
          UWI_fwd: hp.UWI_fwd,
          UWI_aft: hp.UWI_aft,
          UWO: [hp.UWO[0], hp.UWO[1], hp.UWO[2] + currentTravel],
          LWI_fwd: hp.LWI_fwd,
          LWI_aft: hp.LWI_aft,
          LWO: [hp.LWO[0], hp.LWO[1], hp.LWO[2] + currentTravel],
          TRI: hp.TRI,
          TRO: [hp.TRO[0], hp.TRO[1], hp.TRO[2] + currentTravel],
          WC: [hp.WC[0], hp.WC[1], hp.WC[2] + currentTravel],
          CP: [hp.CP[0], hp.CP[1], 0],
          PRI: hp.PRI,
          PRO: [hp.PRO[0], hp.PRO[1], hp.PRO[2] + currentTravel],
          ic_fv: undefined,
          ic_sv: undefined,
          rc: [0, currentRCLateral, currentRC],
          steering_pierce: undefined,
        };

  const dz = result?.wheel_travel_mm ?? [];
  const dzB = resultB?.wheel_travel_mm ?? [];

  // Helper to inject null at diverged points to prevent fake interpolation
  const maskDiverged = useCallback(
    (arr: number[] | undefined, conv: boolean[] | undefined) => {
      if (!arr) return [];
      if (!conv) return arr;
      return arr.map((v, i) => (conv[i] === false ? (null as any) : v));
    },
    []
  );

  // Identify all diverged points with attached diagnostics
  const failedPoints = useMemo(() => {
    if (!result || !result.point_diagnostics) return [];
    return result.point_diagnostics
      .map((diag, idx) => ({
        idx,
        diag,
        travel: result.wheel_travel_mm[idx],
        converged: result.converged[idx],
      }))
      .filter((p) => p.converged === false || p.diag.convergence_status === "FAILED");
  }, [result]);

  // Dedicated scatter trace for divergence markers
  const failureTrace = useCallback(
    (yGetter: (idx: number) => number) => {
      if (failedPoints.length === 0) return [];
      return [
        {
          x: failedPoints.map((p) => p.travel),
          y: failedPoints.map((p) => yGetter(p.idx)),
          name: "⚠ Divergence (Click to Inspect)",
          type: "scatter" as const,
          mode: "markers" as const,
          marker: {
            symbol: "x",
            size: 11,
            color: "#f43f5e",
            line: { width: 2.5, color: "#ffe4e6" },
          },
          hoverinfo: "text" as const,
          hovertext: failedPoints.map(
            (p) =>
              `⚠ Solver Divergence @ ${
                p.travel >= 0 ? `+${p.travel.toFixed(1)}` : p.travel.toFixed(1)
              } mm\nClick marker to view 5-point root-cause analysis`
          ),
        },
      ];
    },
    [failedPoints]
  );

  // Click handler on plot to inspect root cause of failed point
  const handlePlotClick = useCallback(
    (data: any) => {
      if (data?.points && data.points.length > 0) {
        const pt = data.points[0];
        const clickedX = pt.x;
        const match = failedPoints.find((p) => Math.abs(p.travel - clickedX) < 1e-2);
        if (match) {
          setSelectedFailedPoint(match);
          setIsFailedModalOpen(true);
        }
      }
    },
    [failedPoints]
  );

  return (
    <div className="min-h-screen bg-[#07080c] text-gray-200 font-['Inter',sans-serif]">
      {/* ── Top Header Navigation Bar ───────────────────────────────────────── */}
      <header className="border-b border-[#181a24] bg-[#0a0b10]/90 backdrop-blur-md px-5 py-3 sticky top-0 z-30 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[#10141d] border border-cyan-500/40 flex items-center justify-center shadow-md shadow-black/40">
            <Box className="w-4 h-4 text-cyan-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold text-white tracking-tight uppercase">
                Suspension Kinematics & 3D CAE Study
              </h1>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-cyan-950/60 text-cyan-300 border border-cyan-800/40">
                PRO
              </span>
            </div>
            <p className="text-[10px] text-gray-500">
              Multibody kinematics · C++ Newton–Raphson solver · Derivatives & Setup Causal Attribution
            </p>
          </div>
        </div>

        {/* Action Controls: Comparison Toggle, Target Bands, Export, Recompute */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Comparison Mode Toggle */}
          <button
            onClick={() => {
              const next = !isComparisonMode;
              setIsComparisonMode(next);
              if (next && activeTab !== "comparison") {
                setActiveTab("comparison");
              }
            }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition ${
              isComparisonMode
                ? "bg-amber-500/20 text-amber-300 border-amber-500/50 shadow-sm"
                : "bg-[#10121a] text-gray-400 hover:text-white border-[#222536]"
            }`}
          >
            <ArrowRightLeft className="w-3.5 h-3.5" />
            <span>{isComparisonMode ? "Setup A vs B: Active" : "Compare Setups"}</span>
          </button>

          {/* Ask Engineering Question Button */}
          <button
            onClick={() => setIsQuestionModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-amber-500/20 to-orange-500/20 hover:from-amber-500/30 hover:to-orange-500/30 text-amber-300 border border-amber-500/50 shadow-sm transition"
            title="Ask Design Engineering Question (Sensitivity-Based Recommendations)"
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>Ask Question</span>
          </button>

          {/* Target Bands Config Button */}
          <button
            onClick={() => setIsTargetBandsOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#10121a] hover:bg-[#181b28] text-gray-300 border border-[#222536] transition"
            title="Configure Target Design Corridors"
          >
            <Sliders className="w-3.5 h-3.5 text-cyan-400" />
            <span>Target Bands</span>
          </button>

          {/* Export Button */}
          <button
            onClick={() => setIsExportModalOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#10121a] hover:bg-[#181b28] text-gray-300 border border-[#222536] transition"
            title="Export Full Sweep Data to CSV or JSON"
          >
            <Download className="w-3.5 h-3.5 text-emerald-400" />
            <span>Export</span>
          </button>

          {/* Preset Selector */}
          <div className="flex items-center gap-1.5 bg-[#10121a] border border-[#222536] px-2.5 py-1.5 rounded-lg">
            <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
              Preset:
            </span>
            <select
              value={selectedPreset}
              onChange={(e) => applyPreset(e.target.value)}
              className="bg-transparent text-xs font-mono text-cyan-300 focus:outline-none cursor-pointer"
            >
              {Object.values(BENCHMARK_CATALOG).map((preset) => (
                <option key={preset.id} value={preset.id} className="bg-[#10121a] text-gray-200">
                  {preset.name}
                </option>
              ))}
              <option value="custom" className="bg-[#10121a] text-gray-200">
                Custom User Geometry
              </option>
            </select>
          </div>

          <button
            onClick={solve}
            disabled={loading}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg font-bold text-xs bg-amber-500 hover:bg-amber-400 text-black border border-amber-400/50 shadow-lg shadow-black/40 disabled:opacity-50 transition-all cursor-pointer"
          >
            {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            <span>{loading ? "Solving…" : "Recompute Sweep"}</span>
          </button>
        </div>
      </header>

      {/* ── Main Workspace Grid ─────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row min-h-[calc(100vh-57px)]">
        {/* ── LEFT SIDEBAR: Hardpoint Controls & Travel Config ──────────────── */}
        <aside className="w-full lg:w-80 flex-shrink-0 border-r border-[#171924] bg-[#090a0f] flex flex-col lg:max-h-[calc(100vh-57px)] lg:sticky lg:top-[57px] overflow-y-auto">
          <div className="p-3.5 border-b border-[#181a24] bg-[#0d0e16]">
            <h2 className="text-[11px] font-bold text-gray-300 uppercase tracking-wider flex items-center justify-between">
              <span>{isComparisonMode ? "Setup A Hardpoints (mm)" : "Corner Hardpoints (mm)"}</span>
              <span className="text-[9px] font-mono text-cyan-400">Right-Front</span>
            </h2>
            <p className="text-[10px] text-gray-500 mt-0.5">
              Hover rows to highlight corresponding nodes in 3D canvas.
            </p>
          </div>

          <div className="p-3 space-y-3.5 flex-1">
            {/* Travel Sweep Parameters */}
            <div className="bg-[#0e0f17] border border-[#1c1f2c] rounded-lg p-2.5 space-y-2">
              <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider block">
                Wheel Travel Sweep Bounds
              </span>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="text-[9px] text-gray-400">Droop (mm)</label>
                  <input
                    type="number"
                    value={zMin}
                    onChange={(e) => {
                      const v = parseFloat(e.target.value);
                      setZMin(Number.isFinite(v) ? v : -50);
                    }}
                    className="w-full mt-0.5 bg-[#08090d] border border-[#232738] rounded px-1.5 py-1 text-[11px] text-gray-200 font-mono text-center focus:border-cyan-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-[9px] text-gray-400">Bump (mm)</label>
                  <input
                    type="number"
                    value={zMax}
                    onChange={(e) => {
                      const v = parseFloat(e.target.value);
                      setZMax(Number.isFinite(v) ? v : 50);
                    }}
                    className="w-full mt-0.5 bg-[#08090d] border border-[#232738] rounded px-1.5 py-1 text-[11px] text-gray-200 font-mono text-center focus:border-cyan-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="text-[9px] text-gray-400">Steps</label>
                  <input
                    type="number"
                    value={nSteps}
                    onChange={(e) => {
                      const v = parseInt(e.target.value, 10);
                      setNSteps(Number.isFinite(v) && v > 1 ? v : 33);
                    }}
                    className="w-full mt-0.5 bg-[#08090d] border border-[#232738] rounded px-1.5 py-1 text-[11px] text-gray-200 font-mono text-center focus:border-cyan-500 focus:outline-none"
                  />
                </div>
              </div>
            </div>

            {/* Hardpoint Coordinate Tables */}
            {(
              [
                [
                  "Upper Wishbone",
                  [
                    ["UWI_fwd", "UWI fwd"],
                    ["UWI_aft", "UWI aft"],
                    ["UWO", "UWO (UBJ)"],
                  ],
                ],
                [
                  "Lower Wishbone",
                  [
                    ["LWI_fwd", "LWI fwd"],
                    ["LWI_aft", "LWI aft"],
                    ["LWO", "LWO (LBJ)"],
                  ],
                ],
                [
                  "Steering Tie Rod",
                  [
                    ["TRI", "TR Inboard"],
                    ["TRO", "TR Outboard"],
                  ],
                ],
                [
                  "Wheel Spindle & Patch",
                  [
                    ["WC", "Wheel Ctr"],
                    ["CP", "Contact Pt"],
                  ],
                ],
                [
                  "Pushrod / Actuation",
                  [
                    ["PRI", "PR Inboard"],
                    ["PRO", "PR Outboard"],
                  ],
                ],
              ] as [string, [string, string][]][]
            ).map(([section, rows]) => (
              <div key={section} className="space-y-1">
                <span className="text-[9px] font-bold text-gray-400 uppercase tracking-widest pl-1">
                  {section}
                </span>
                <div className="bg-[#0e0f17] border border-[#1b1e2a] rounded-lg p-1.5 space-y-1">
                  <div className="grid grid-cols-[5.2rem_1fr_1fr_1fr] gap-1.5 px-2 text-[9px] text-gray-600 font-mono text-center">
                    <span />
                    <span>X</span>
                    <span>Y</span>
                    <span>Z</span>
                  </div>
                  {rows.map(([key, label]) => (
                    <HPRow
                      key={key}
                      label={label}
                      name={key}
                      value={hp[key]}
                      onChange={handleHP}
                      isHovered={hoveredHP === key}
                      onHover={setHoveredHP}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Sidebar Footer Error / Summary */}
          {error && (
            <div className="p-3 bg-rose-950/40 border-t border-rose-500/40 text-rose-300 text-xs">
              <span className="font-bold flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                Solver Error
              </span>
              <p className="mt-1 font-mono text-[10px] text-rose-200/80 leading-relaxed">{error}</p>
            </div>
          )}
        </aside>

        {/* ── MAIN VIEWPORT AREA ────────────────────────────────────────────── */}
        <main className="flex-1 flex flex-col overflow-y-auto bg-[#07080c] p-4 space-y-4">
          {/* Decoupled Model Validity Component */}
          <KinematicsModelValidity
            report={result?.validation_report}
            modelValidity={result?.model_validity}
            numericalStatus={result?.numerical_status}
            physicalStatus={result?.physical_status}
            overallStatus={result?.overall_model_status}
            convergenceSummary={result?.convergence_summary}
            reproducibility={result?.reproducibility}
            benchmarks={result?.benchmarks}
            onOpenBenchmarks={() => setIsBenchmarksOpen(true)}
            backendInfo={backendInfo}
            allConverged={result?.all_converged ?? true}
            travelMm={currentTravel}
          />

          {/* ── 9 Real-Time Engineering KPI Cards (with Target Band Highlights) ── */}
          <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-9 gap-2">
            <KPICard
              label="1. Camber"
              value={currentCamber}
              unit="°"
              sub={currentCamber < 0 ? "Negative camber" : "Positive camber"}
              color={COLORS.cyan}
            />
            <KPICard
              label="2. Toe"
              value={currentToe}
              unit="°"
              sub={currentToe < 0 ? "Toe-in" : "Toe-out"}
              color={COLORS.violet}
            />
            <KPICard
              label="3. RC Height"
              value={currentRC}
              unit="mm"
              sub="Roll center Z"
              color={COLORS.rose}
              targetRange={targetBands.roll_center_height_mm}
            />
            <KPICard
              label="4. Motion Ratio"
              value={currentMR}
              unit=""
              sub="Δspring / Δwheel"
              color={COLORS.emerald}
              targetRange={targetBands.motion_ratio}
            />
            <KPICard
              label="5. Track Change"
              value={currentTrack}
              unit="mm"
              sub="Transverse scrub"
              color={COLORS.blue}
            />
            <KPICard
              label="6. Wheelbase Δ"
              value={currentWB}
              unit="mm"
              sub="Fore-aft scrub"
              color={COLORS.blue}
            />
            <KPICard
              label="7. Caster"
              value={currentCaster}
              unit="°"
              sub="Steering axis caster angle"
              color={COLORS.amber}
            />
            <KPICard
              label="8. KPI"
              value={currentKPI}
              unit="°"
              sub="Kingpin angle"
              color={COLORS.orange}
            />
            <KPICard
              label="9. Scrub Radius"
              value={currentScrub}
              unit="mm"
              sub="Ground offset"
              color={COLORS.rose}
              targetRange={targetBands.scrub_radius_mm}
            />
          </div>

          {/* ── Real-Time Kinematic Derivative / Rate Metrics Bar ────────────── */}
          <div className="bg-[#0b0c12] border border-[#1d202b] rounded-xl px-4 py-2.5 flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-2 text-cyan-400 font-semibold">
              <TrendingUp className="w-4 h-4" />
              <span>Real Finite-Difference Kinematic Rates (at {currentTravel.toFixed(1)} mm):</span>
            </div>
            <div className="flex items-center gap-6 font-mono text-[11px] flex-wrap">
              <div>
                <span className="text-gray-400">dγ/dz (Camber Gain): </span>
                <span className="font-bold text-cyan-300">{currentCamberGain.toFixed(2)} °/100mm</span>
                <span className="text-gray-400 text-[10px] ml-1">
                  ({(currentCamberGain * 10.0).toFixed(1)} °/m)
                </span>
              </div>
              <div>
                <span className="text-gray-400">dToe/dz (Bump Steer): </span>
                <span className="font-bold text-amber-300">{currentToeGain.toFixed(2)} °/100mm</span>
              </div>
              <div>
                <span className="text-gray-400">dRC/dz (Migration Rate): </span>
                <span className="font-bold text-rose-300">{currentRCRate.toFixed(2)} mm/mm</span>
              </div>
              <div>
                <span className="text-gray-400">RC Lateral (Y): </span>
                <span className="font-bold text-amber-300">{currentRCLateral.toFixed(1)} mm</span>
              </div>
            </div>
          </div>

          {/* ── Live Wheel Travel Scrubber Control Bar ──────────────────────── */}
          <div className="bg-[#0b0c12] border border-[#1e2230] rounded-xl p-3 flex flex-col sm:flex-row items-center justify-between gap-3 shadow-md">
            {/* Play/Pause & Reset Controls */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                className={`p-2 rounded-lg border transition-colors ${
                  isPlaying
                    ? "bg-cyan-500/20 border-cyan-500/50 text-cyan-300"
                    : "bg-[#141622] border-[#292d40] text-gray-300 hover:text-white hover:bg-[#1a1d2c]"
                }`}
                title={isPlaying ? "Pause Travel Motion" : "Play Continuous Bump/Droop Cycle"}
              >
                {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
              </button>

              <button
                onClick={() => {
                  setIsPlaying(false);
                  if (result) {
                    const zeroIdx = result.wheel_travel_mm.findIndex((z) => Math.abs(z) < 1.0);
                    setTravelIdx(zeroIdx >= 0 ? zeroIdx : Math.floor(result.n_points / 2));
                  }
                }}
                className="p-2 rounded-lg bg-[#141622] border border-[#292d40] text-gray-400 hover:text-gray-200 hover:bg-[#1a1d2c] transition-colors"
                title="Reset to Static Neutral (0 mm)"
              >
                <RotateCcw className="w-4 h-4" />
              </button>

              <div className="flex flex-col ml-1">
                <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
                  Wheel Travel Position
                </span>
                <span className="text-xs font-mono font-bold text-cyan-300">
                  {currentTravel >= 0 ? `+${currentTravel.toFixed(1)}` : currentTravel.toFixed(1)} mm
                  <span className="text-[10px] text-gray-500 font-normal ml-1">
                    {currentTravel > 0 ? "(BUMP)" : currentTravel < 0 ? "(DROOP)" : "(STATIC)"}
                  </span>
                </span>
              </div>
            </div>

            {/* Travel Scrubber Range Slider */}
            <div className="flex items-center gap-3 w-full sm:w-auto flex-1 max-w-xl px-2">
              <span className="text-[10px] font-mono text-gray-500 w-16 text-right">
                {result ? `${result.wheel_travel_mm[0].toFixed(0)} mm` : `${zMin} mm`}
              </span>
              <input
                type="range"
                min={0}
                max={result ? result.n_points - 1 : 32}
                value={travelIdx}
                onChange={(e) => {
                  setIsPlaying(false);
                  setTravelIdx(parseInt(e.target.value));
                }}
                aria-label="Interactive Wheel Travel Slider"
                className="flex-1 accent-cyan-400 cursor-pointer h-2 bg-[#171924] rounded-lg"
              />
              <span className="text-[10px] font-mono text-gray-500 w-16 text-left">
                {result ? `+${result.wheel_travel_mm[result.n_points - 1].toFixed(0)} mm` : `+${zMax} mm`}
              </span>
            </div>
          </div>

          {/* ── CAE Hostile Auditor Alert Banner ─────────────────────────────── */}
          {failedPoints.length > 0 && (
            <div className="bg-rose-950/40 border border-rose-500/50 rounded-xl p-3.5 flex flex-wrap items-center justify-between gap-3 text-xs text-rose-200 shadow-lg animate-in fade-in duration-200">
              <div className="flex items-center gap-2.5">
                <AlertTriangle className="w-5 h-5 text-rose-400 flex-shrink-0 animate-pulse" />
                <div>
                  <span className="font-bold text-rose-300 uppercase tracking-wide">
                    CAE Hostile Audit Notice: {failedPoints.length} travel point(s) diverged / failed solver tolerances!
                  </span>
                  <p className="text-[11px] text-rose-300/80 mt-0.5">
                    Curve interpolation across failed points is suppressed to prevent fabricated results. Red divergence markers are placed on plot curves. Click any marker to view the 5-point root-cause analysis.
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setSelectedFailedPoint(failedPoints[0]);
                  setIsFailedModalOpen(true);
                }}
                className="px-3 py-1.5 rounded-lg bg-rose-600/30 hover:bg-rose-600/50 text-rose-100 border border-rose-500/50 text-xs font-semibold whitespace-nowrap transition shadow-sm"
              >
                Inspect Divergence Diagnostic
              </button>
            </div>
          )}

          {/* ── View Navigation Tabs ────────────────────────────────────────── */}
          <div className="flex items-center gap-1 border-b border-[#1b1e2a] pb-1 overflow-x-auto">
            {[
              { id: "workspace", label: "3D Suspension Workspace", icon: Box },
              { id: "camber", label: "Camber & Toe Curves", icon: BarChart2 },
              { id: "rc", label: "Roll Center Migration (Z & Y)", icon: Compass },
              { id: "derivatives", label: "Rate Curves (dγ/dz, Bump Steer)", icon: TrendingUp },
              { id: "mr", label: "Motion Ratio", icon: Sliders },
              { id: "track", label: "Track & Wheelbase Δ", icon: Layers },
              { id: "caster", label: "Caster, KPI & Scrub", icon: Eye },
              { id: "comparison", label: "Setup A vs B Study", icon: ArrowRightLeft },
              { id: "sensitivity", label: "Sensitivity Matrix (Jacobian)", icon: Activity },
              { id: "optimizer", label: "Design Optimizer & Pareto", icon: Target },
            ].map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  data-testid={`tab-${tab.id}`}
                  onClick={() => setActiveTab(tab.id as ViewTab)}
                  className={`flex items-center gap-2 px-3 py-2 text-xs font-semibold rounded-t-lg transition-colors border-b-2 ${
                    isActive
                      ? "border-cyan-500 text-cyan-300 bg-[#0f111a]"
                      : "border-transparent text-gray-500 hover:text-gray-300 hover:bg-[#0c0d14]"
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {/* ── Tab Content Views ───────────────────────────────────────────── */}
          <div className="flex-1 min-h-[520px]">
            {/* Tab 1: 3D Suspension Workspace */}
            {activeTab === "workspace" && (
              <div className="space-y-3">
                <SuspensionKinematics3D
                  geometry={current3DGeometry}
                  camberDeg={currentCamber}
                  toeDeg={currentToe}
                  rollCenterHeightMm={currentRC}
                  scrubRadiusMm={currentScrub}
                  tireRadiusM={tireRadiusM}
                  hoveredNode={hoveredHP}
                  onHoverNode={setHoveredHP}
                />

                <div className="p-3 bg-[#0a0c12] border border-[#1c1f2e] rounded-xl flex flex-wrap items-center justify-between gap-4 text-xs">
                  <div className="flex items-center gap-2 text-gray-400">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
                    <span>Rigid-Body Kinematic Parity: C++ Newton-Raphson & Python fallback matched.</span>
                  </div>
                  <div className="flex items-center gap-4 text-gray-500 font-mono text-[11px]">
                    <span>Left Drag: Orbit 3D</span>
                    <span>Right Drag: Pan</span>
                    <span>Wheel: Zoom</span>
                  </div>
                </div>
              </div>
            )}

            {/* Tab 2: Camber & Toe Curves */}
            {activeTab === "camber" && (
              <div className="bg-[#080a10] border border-[#1c1f2e] rounded-xl p-4 h-[520px]">
                <Plot
                  data={[
                    // Setup A Traces
                    {
                      x: dz,
                      y: maskDiverged(result?.camber_deg, result?.converged),
                      name: isComparisonMode ? "Setup A — Camber Angle" : "Camber Angle",
                      type: "scatter",
                      mode: "lines",
                      line: { color: COLORS.cyan, width: 2.5 },
                    },
                    {
                      x: dz,
                      y: maskDiverged(result?.toe_deg, result?.converged),
                      name: isComparisonMode ? "Setup A — Toe Angle (Bump Steer)" : "Toe Angle (Bump Steer)",
                      type: "scatter",
                      mode: "lines",
                      yaxis: "y2",
                      line: { color: COLORS.violet, width: 2, dash: "dash" },
                    },
                    // Setup B Traces (Overlay when in comparison mode)
                    ...(isComparisonMode && resultB
                      ? [
                          {
                            x: dzB,
                            y: maskDiverged(resultB.camber_deg, resultB.converged),
                            name: "Setup B — Camber Angle",
                            type: "scatter" as const,
                            mode: "lines" as const,
                            line: { color: COLORS.candidateAmber, width: 2.5, dash: "dot" as const },
                          },
                          {
                            x: dzB,
                            y: maskDiverged(resultB.toe_deg, resultB.converged),
                            name: "Setup B — Toe Angle",
                            type: "scatter" as const,
                            mode: "lines" as const,
                            yaxis: "y2",
                            line: { color: COLORS.candidateViolet, width: 2, dash: "dot" as const },
                          },
                        ]
                      : []),
                    ...failureTrace((idx) => result?.camber_deg?.[idx] ?? 0),
                  ]}
                  layout={{
                    ...plotLayout(
                      isComparisonMode
                        ? "Setup A vs Setup B: Camber & Toe across Travel (Droop / Bump)"
                        : "Camber & Toe vs Wheel Travel (Droop / Bump)",
                      zMin,
                      zMax,
                      currentTravel,
                      { title: { text: "Wheel Travel [mm]", font: { size: 11, color: "#94A3B8" } } },
                      { title: { text: "Camber [°]", font: { size: 11, color: "#94A3B8" } } }
                    ),
                    yaxis2: {
                      ...THEME.yaxis,
                      title: { text: "Toe [°]", font: { size: 11, color: "#94A3B8" } },
                      overlaying: "y",
                      side: "right",
                    },
                  }}
                  config={{ responsive: true, displaylogo: false }}
                  style={{ width: "100%", height: "100%" }}
                  useResizeHandler
                  onClick={handlePlotClick}
                />
              </div>
            )}

            {/* Tab 3: Roll Center Migration (Z & Lateral Y) */}
            {activeTab === "rc" && (
              <div className="bg-[#080a10] border border-[#1c1f2e] rounded-xl p-4 h-[520px]">
                <Plot
                  data={[
                    // Setup A Roll Center Height
                    {
                      x: dz,
                      y: maskDiverged(result?.roll_center_height_mm, result?.converged),
                      name: isComparisonMode ? "Setup A — RC Height (Z)" : "Roll Center Height (Z)",
                      type: "scatter",
                      mode: "lines",
                      line: { color: COLORS.rose, width: 2.5 },
                    },
                    // Setup A Roll Center Lateral Migration
                    {
                      x: dz,
                      y: maskDiverged(result?.roll_center_lateral_mm, result?.converged),
                      name: isComparisonMode ? "Setup A — RC Lateral (Y)" : "Roll Center Lateral (Y)",
                      type: "scatter",
                      mode: "lines",
                      yaxis: "y2",
                      line: { color: COLORS.blue, width: 2, dash: "dash" },
                    },
                    // Setup B Overlays
                    ...(isComparisonMode && resultB
                      ? [
                          {
                            x: dzB,
                            y: maskDiverged(resultB.roll_center_height_mm, resultB.converged),
                            name: "Setup B — RC Height (Z)",
                            type: "scatter" as const,
                            mode: "lines" as const,
                            line: { color: COLORS.candidateAmber, width: 2.5, dash: "dot" as const },
                          },
                          {
                            x: dzB,
                            y: maskDiverged(resultB.roll_center_lateral_mm || [], resultB.converged),
                            name: "Setup B — RC Lateral (Y)",
                            type: "scatter" as const,
                            mode: "lines" as const,
                            yaxis: "y2",
                            line: { color: COLORS.candidateViolet, width: 2, dash: "dot" as const },
                          },
                        ]
                      : []),
                    ...failureTrace((idx) => result?.roll_center_height_mm?.[idx] ?? 0),
                  ]}
                  layout={{
                    ...plotLayout(
                      "Roll-Center Height & Lateral Migration vs Wheel Travel",
                      zMin,
                      zMax,
                      currentTravel,
                      { title: { text: "Wheel Travel [mm]", font: { size: 11, color: "#94A3B8" } } },
                      { title: { text: "Roll Center Height (Z) [mm]", font: { size: 11, color: "#94A3B8" } } },
                      undefined,
                      targetBands.roll_center_height_mm
                    ),
                    yaxis2: {
                      ...THEME.yaxis,
                      title: { text: "RC Lateral Migration (Y) [mm]", font: { size: 11, color: "#94A3B8" } },
                      overlaying: "y",
                      side: "right",
                    },
                  }}
                  config={{ responsive: true, displaylogo: false }}
                  style={{ width: "100%", height: "100%" }}
                  useResizeHandler
                  onClick={handlePlotClick}
                />
              </div>
            )}

            {/* Tab 4: Kinematic Rate / Derivative Curves */}
            {activeTab === "derivatives" && (
              <div className="bg-[#080a10] border border-[#1c1f2e] rounded-xl p-4 h-[520px]">
                <Plot
                  data={[
                    {
                      x: dz,
                      y: maskDiverged(result?.derivatives?.camber_gain_deg_per_100mm, result?.converged),
                      name: "Camber Gain Rate dγ/dz [°/100mm]",
                      type: "scatter",
                      mode: "lines",
                      line: { color: COLORS.cyan, width: 2.5 },
                    },
                    {
                      x: dz,
                      y: maskDiverged(result?.derivatives?.toe_gain_deg_per_100mm, result?.converged),
                      name: "Bump Steer Rate dToe/dz [°/100mm]",
                      type: "scatter",
                      mode: "lines",
                      line: { color: COLORS.violet, width: 2, dash: "dash" },
                    },
                    {
                      x: dz,
                      y: maskDiverged(result?.derivatives?.rc_migration_rate, result?.converged),
                      name: "RC Migration Rate dRC/dz [mm/mm]",
                      type: "scatter",
                      mode: "lines",
                      yaxis: "y2",
                      line: { color: COLORS.rose, width: 2, dash: "dot" },
                    },
                    ...(isComparisonMode && resultB?.derivatives
                      ? [
                          {
                            x: dzB,
                            y: maskDiverged(resultB.derivatives.camber_gain_deg_per_100mm, resultB.converged),
                            name: "Setup B — Camber Gain [°/100mm]",
                            type: "scatter" as const,
                            mode: "lines" as const,
                            line: { color: COLORS.candidateAmber, width: 2.5, dash: "dot" as const },
                          },
                        ]
                      : []),
                    ...failureTrace((idx) => result?.derivatives?.camber_gain_deg_per_100mm?.[idx] ?? 0),
                  ]}
                  layout={{
                    ...plotLayout(
                      "Kinematic Rates & Derivatives across Wheel Travel (Finite Differences)",
                      zMin,
                      zMax,
                      currentTravel,
                      { title: { text: "Wheel Travel [mm]", font: { size: 11, color: "#94A3B8" } } },
                      { title: { text: "Angular Rate [°/100mm]", font: { size: 11, color: "#94A3B8" } } },
                      undefined,
                      targetBands.camber_gain_deg_per_100mm
                    ),
                    yaxis2: {
                      ...THEME.yaxis,
                      title: { text: "Linear Rate [mm/mm]", font: { size: 11, color: "#94A3B8" } },
                      overlaying: "y",
                      side: "right",
                    },
                  }}
                  config={{ responsive: true, displaylogo: false }}
                  style={{ width: "100%", height: "100%" }}
                  useResizeHandler
                  onClick={handlePlotClick}
                />
              </div>
            )}

            {/* Tab 5: Motion Ratio */}
            {activeTab === "mr" && (
              <div className="bg-[#080a10] border border-[#1c1f2e] rounded-xl p-4 h-[520px]">
                <Plot
                  data={[
                    {
                      x: dz,
                      y: maskDiverged(result?.motion_ratio, result?.converged),
                      name: isComparisonMode ? "Setup A — Motion Ratio" : "Motion Ratio",
                      type: "scatter",
                      mode: "lines",
                      line: { color: COLORS.emerald, width: 2.5 },
                    },
                    ...(isComparisonMode && resultB
                      ? [
                          {
                            x: dzB,
                            y: maskDiverged(resultB.motion_ratio, resultB.converged),
                            name: "Setup B — Motion Ratio",
                            type: "scatter" as const,
                            mode: "lines" as const,
                            line: { color: COLORS.candidateAmber, width: 2.5, dash: "dot" as const },
                          },
                        ]
                      : []),
                    ...failureTrace((idx) => result?.motion_ratio?.[idx] ?? 0),
                  ]}
                  layout={{
                    ...plotLayout(
                      "Damper Motion Ratio (Spring / Wheel Deflection Rate) vs Wheel Travel",
                      zMin,
                      zMax,
                      currentTravel,
                      { title: { text: "Wheel Travel [mm]", font: { size: 11, color: "#94A3B8" } } },
                      { title: { text: "Motion Ratio [mm/mm]", font: { size: 11, color: "#94A3B8" } } },
                      undefined,
                      targetBands.motion_ratio
                    ),
                  }}
                  config={{ responsive: true, displaylogo: false }}
                  style={{ width: "100%", height: "100%" }}
                  useResizeHandler
                  onClick={handlePlotClick}
                />
              </div>
            )}

            {/* Tab 6: Track & Wheelbase Change */}
            {activeTab === "track" && (
              <div className="bg-[#080a10] border border-[#1c1f2e] rounded-xl p-4 h-[520px]">
                <Plot
                  data={[
                    {
                      x: dz,
                      y: maskDiverged(result?.track_change_mm, result?.converged),
                      name: isComparisonMode ? "Setup A — Track Width Change" : "Track Width Change (Scrub)",
                      type: "scatter",
                      mode: "lines",
                      line: { color: COLORS.blue, width: 2.5 },
                    },
                    {
                      x: dz,
                      y: maskDiverged(result?.wheelbase_change_mm, result?.converged),
                      name: isComparisonMode ? "Setup A — Wheelbase Change" : "Wheelbase Change",
                      type: "scatter",
                      mode: "lines",
                      line: { color: COLORS.orange, width: 2, dash: "dash" },
                    },
                    ...(isComparisonMode && resultB
                      ? [
                          {
                            x: dzB,
                            y: maskDiverged(resultB.track_change_mm, resultB.converged),
                            name: "Setup B — Track Width Change",
                            type: "scatter" as const,
                            mode: "lines" as const,
                            line: { color: COLORS.candidateAmber, width: 2.5, dash: "dot" as const },
                          },
                        ]
                      : []),
                    ...failureTrace((idx) => result?.track_change_mm?.[idx] ?? 0),
                  ]}
                  layout={{
                    ...plotLayout(
                      "Track Width & Wheelbase Migration vs Wheel Travel",
                      zMin,
                      zMax,
                      currentTravel,
                      { title: { text: "Wheel Travel [mm]", font: { size: 11, color: "#94A3B8" } } },
                      { title: { text: "Δ [mm]", font: { size: 11, color: "#94A3B8" } } }
                    ),
                  }}
                  config={{ responsive: true, displaylogo: false }}
                  style={{ width: "100%", height: "100%" }}
                  useResizeHandler
                  onClick={handlePlotClick}
                />
              </div>
            )}

            {/* Tab 7: Caster, KPI & Scrub Radius */}
            {activeTab === "caster" && (
              <div className="bg-[#080a10] border border-[#1c1f2e] rounded-xl p-4 h-[520px]">
                <Plot
                  data={[
                    {
                      x: dz,
                      y: maskDiverged(result?.caster_deg, result?.converged),
                      name: "Caster Angle",
                      type: "scatter",
                      mode: "lines",
                      line: { color: COLORS.amber, width: 2.5 },
                    },
                    {
                      x: dz,
                      y: maskDiverged(result?.kpi_deg, result?.converged),
                      name: "Kingpin Inclination (KPI)",
                      type: "scatter",
                      mode: "lines",
                      line: { color: COLORS.orange, width: 2, dash: "dot" },
                    },
                    {
                      x: dz,
                      y: maskDiverged(result?.scrub_radius_mm, result?.converged),
                      name: "Scrub Radius",
                      type: "scatter",
                      mode: "lines",
                      yaxis: "y2",
                      line: { color: COLORS.rose, width: 2, dash: "dash" },
                    },
                    ...failureTrace((idx) => result?.caster_deg?.[idx] ?? 0),
                  ]}
                  layout={{
                    ...plotLayout(
                      "Steering Axis Geometry: Caster, KPI & Scrub Radius vs Wheel Travel",
                      zMin,
                      zMax,
                      currentTravel,
                      { title: { text: "Wheel Travel [mm]", font: { size: 11, color: "#94A3B8" } } },
                      { title: { text: "Angle [°]", font: { size: 11, color: "#94A3B8" } } }
                    ),
                    yaxis2: {
                      ...THEME.yaxis,
                      title: { text: "Scrub Radius [mm]", font: { size: 11, color: "#94A3B8" } },
                      overlaying: "y",
                      side: "right",
                    },
                  }}
                  config={{ responsive: true, displaylogo: false }}
                  style={{ width: "100%", height: "100%" }}
                  useResizeHandler
                  onClick={handlePlotClick}
                />
              </div>
            )}

            {/* Tab 8: Setup A vs B Study Panel */}
            {activeTab === "comparison" && (
              <KinematicsComparisonPanel
                comparison={comparisonResult}
                loading={comparisonLoading}
                setups={setupCatalogList}
                selectedSetupAId={selectedPreset}
                selectedSetupBId={selectedPresetB}
                onSelectSetupA={(id) => applyPreset(id)}
                onSelectSetupB={(id) => applyPresetB(id)}
                onSwapSetups={handleSwapSetups}
                onRunComparison={runComparison}
              />
            )}

            {/* Tab 9: Hardpoint Sensitivity Matrix (Jacobian) */}
            {activeTab === "sensitivity" && (
              <HardpointSensitivityMatrix
                data={sensitivityData}
                loading={loadingSensitivity}
                stepSizeMm={sensitivityStepSize}
                onChangeStepSize={(sz) => setSensitivityStepSize(sz)}
                onRecompute={handleComputeSensitivity}
                onSelectCandidate={(targetHp, targetAxis) => {
                  setIsQuestionModalOpen(true);
                }}
              />
            )}

            {/* Tab 10: Multi-Objective Bounded Optimizer & Pareto */}
            {activeTab === "optimizer" && (
              <KinematicsOptimizerPanel
                hardpoints={hp}
                onApplyCandidate={(candHp, label) => {
                  setHP(candHp as Hardpoints);
                  setSelectedPreset("custom");
                  setActiveTab("workspace");
                }}
                onSetAsSetupB={(candHp, label) => {
                  setHPB(candHp as Hardpoints);
                  setSelectedPresetB("custom");
                  setIsComparisonMode(true);
                  setActiveTab("comparison");
                  runComparison();
                }}
              />
            )}
          </div>
        </main>
      </div>

      {/* ── Modals ──────────────────────────────────────────────────────────── */}
      <EngineeringQuestionModal
        isOpen={isQuestionModalOpen}
        onClose={() => setIsQuestionModalOpen(false)}
        hardpoints={hp}
        onApplyCandidateToWorkspace={(candHp, label) => {
          setHP(candHp as Hardpoints);
          setSelectedPreset("custom");
          setIsQuestionModalOpen(false);
          setActiveTab("workspace");
        }}
      />

      <KinematicsTargetBandsModal
        isOpen={isTargetBandsOpen}
        onClose={() => setIsTargetBandsOpen(false)}
        bands={targetBands}
        onSaveBands={(bands) => setTargetBands(bands)}
      />

      <KinematicsExportModal
        isOpen={isExportModalOpen}
        onClose={() => setIsExportModalOpen(false)}
        hardpoints={hp}
        sweepData={result}
        setupName={BENCHMARK_CATALOG[selectedPreset]?.name || "Custom Setup"}
        zMin={zMin}
        zMax={zMax}
        nSteps={nSteps}
      />

      <FailedPointModal
        isOpen={isFailedModalOpen}
        onClose={() => setIsFailedModalOpen(false)}
        diagnostic={selectedFailedPoint?.diag ?? null}
        travelMm={selectedFailedPoint?.travel ?? 0}
      />

      <KinematicsBenchmarksModal
        isOpen={isBenchmarksOpen}
        onClose={() => setIsBenchmarksOpen(false)}
        benchmarks={result?.benchmarks || []}
      />
    </div>
  );
}
