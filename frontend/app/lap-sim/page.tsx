"use client";

import { useState, useCallback, useRef } from "react";
import dynamic from "next/dynamic";
import {
  Timer, Upload, Play, ChevronDown, ChevronRight,
  Zap, Gauge, Wind, Activity, BarChart3, TrendingDown,
  AlertCircle, CheckCircle, Loader2, Settings2, Layers,
} from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

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
  };
  ggv: {
    speeds_ms: number[];
    ay_max_ms2: number[];
    ax_accel_ms2: number[];
    ax_brake_ms2: number[];
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

function syntheticOval(lengthM: number, avgRadiusM: number, nPoints = 200) {
  const circLen = 2 * Math.PI * avgRadiusM;
  const straightLen = Math.max((lengthM - circLen) / 2, 10);
  const curvCorner = 1 / Math.max(avgRadiusM, 1);
  const distances: number[] = [];
  const curvatures: number[] = [];
  let d = 0;
  const ds = lengthM / nPoints;
  for (let i = 0; i < nPoints; i++) {
    const frac = (i / nPoints) * 4;
    const seg = Math.floor(frac);
    const isCorner = seg === 1 || seg === 3;
    distances.push(d);
    curvatures.push(isCorner ? curvCorner : 0);
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
    <div className="mb-3">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-1.5 mb-2 group"
      >
        <span className="text-[9px] font-bold text-gray-700 uppercase tracking-[0.16em] group-hover:text-gray-500 transition-colors flex-1 text-left">
          {title}
        </span>
        {open ? <ChevronDown size={10} className="text-gray-700" /> : <ChevronRight size={10} className="text-gray-700" />}
      </button>
      {open && <div className="space-y-2">{children}</div>}
    </div>
  );
}

function ParamRow({ label, unit, value, onChange, min, max, step = 0.01 }: {
  label: string; unit: string; value: number;
  onChange: (v: number) => void; min?: number; max?: number; step?: number;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <label className="text-[10px] text-gray-500 flex-1 leading-tight">{label}</label>
      <div className="flex items-center gap-1">
        <input
          type="number"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={e => onChange(parseFloat(e.target.value) || 0)}
          className="w-[68px] bg-[#0d0d0d] border border-[#252525] text-[11px] rounded px-2 py-1 text-white
            focus:outline-none focus:border-[#f2a900]/50 focus:ring-1 focus:ring-[#f2a900]/30 text-right"
        />
        <span className="text-[9px] text-gray-700 w-8 leading-none">{unit}</span>
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
  const { authHeader } = useAuth();
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
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [cfg, setCfg] = useState<VehicleConfig>({
    mass: 800, h_cog: 0.30, wheelbase: 2.70, cog_dist_front: 1.35, track_front: 1.55,
    cl_base: 1.80, cd_base: 0.95, frontal_area: 1.70, cop_fraction: 0.45, cl_rh_sens: 0.0,
    max_power_kw: 350, brake_front_bias: 65,
  });

  const set = (k: keyof VehicleConfig) => (v: number) => setCfg(c => ({ ...c, [k]: v }));

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
    max_power: cfg.max_power_kw * 1000,
  });

  const handleGpxUpload = useCallback(async (file: File) => {
    setUploading(true);
    setError(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch(`${API}/api/v1/lapsim/upload_gpx`, {
        method: "POST",
        headers: authHeader() as HeadersInit,
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
  }, [authHeader]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file?.name.endsWith(".gpx")) handleGpxUpload(file);
  }, [handleGpxUpload]);

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    try {
      let body: Record<string, unknown> = { vehicle: buildVehiclePayload() };

      if (trackMode === "gpx" && gpsData) {
        body = {
          ...body,
          latitudes: gpsData.latitudes,
          longitudes: gpsData.longitudes,
          elevations: gpsData.elevations,
        };
      } else {
        const { distances, curvatures } = syntheticOval(ovalLength, ovalRadius);
        body = { ...body, distances, curvatures };
      }

      const res = await fetch(`${API}/api/v1/lapsim/run`, {
        method: "POST",
        headers: { ...authHeader(), "Content-Type": "application/json" } as HeadersInit,
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail ?? "Simulation failed");
      }
      setResult(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setRunning(false);
    }
  };

  const tabs = ["Speed Trace", "GG Diagram", "Load Transfer", "Aero", "GGV Envelope"];

  const tel = result?.telemetry;
  const ggv = result?.ggv;

  return (
    <div className="flex h-[calc(100vh-44px)] bg-black text-white overflow-hidden">

      {/* ── LEFT PANEL ─────────────────────────────────────────────────────── */}
      <aside className="w-[220px] flex-shrink-0 border-r border-[#1a1a1a] overflow-y-auto p-3 space-y-1 custom-scrollbar">
        {/* Header */}
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-5 h-5 rounded-md bg-[#f2a900]/10 border border-[#f2a900]/20 flex items-center justify-center">
              <Timer size={11} className="text-[#f2a900]" />
            </div>
            <span className="text-[11px] font-bold text-white">Lap Simulator</span>
          </div>
          <p className="text-[9px] text-gray-600 leading-relaxed">
            QSS · 4-wheel LT · Pacejka tires · GGV envelope
          </p>
        </div>

        {/* Track Input */}
        <Section title="Track Input">
          <div className="flex rounded-lg border border-[#252525] overflow-hidden mb-2">
            {(["oval", "gpx"] as const).map(m => (
              <button key={m} onClick={() => setTrackMode(m)}
                className={`flex-1 text-[9px] py-1.5 font-bold uppercase tracking-wider transition-colors
                  ${trackMode === m ? "bg-[#f2a900] text-black" : "text-gray-500 hover:text-gray-300"}`}>
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
              <input ref={fileInputRef} type="file" accept=".gpx" className="hidden"
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
            <p className="text-[9px] text-gray-700">Drive Layout: RWD · 6-speed sequential</p>
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
            <><Loader2 size={13} className="animate-spin" />Running…</>
          ) : (
            <><Play size={13} />Run Simulation</>
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
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {result ? (
          <>
            {/* KPI Cards */}
            <div className="flex-shrink-0 grid grid-cols-6 gap-2 p-3 border-b border-[#1a1a1a]">
              <KpiCard label="Lap Time" value={formatLapTime(result.total_time_s)} unit="" icon={Timer} accent />
              <KpiCard label="Top Speed" value={result.max_speed_kmh.toFixed(0)} unit="km/h" icon={Gauge} />
              <KpiCard label="Min Speed" value={result.min_speed_kmh.toFixed(0)} unit="km/h" icon={TrendingDown} />
              <KpiCard label="Avg Speed" value={result.avg_speed_kmh.toFixed(0)} unit="km/h" icon={Activity} />
              <KpiCard label="Energy Used" value={result.energy_used_kj.toFixed(0)} unit="kJ" icon={Zap} />
              <KpiCard label="Terminal v" value={result.terminal_velocity_kmh.toFixed(0)} unit="km/h" icon={Wind} />
            </div>

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

            {/* Plot Area */}
            <div className="flex-1 p-3 min-h-0">
              {activeTab === 0 && tel && (
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
                    title: { text: "Speed Trace & Gear", font: { color: "#555", size: 12 } },
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
                />
              )}

              {activeTab === 1 && tel && (
                <Plot
                  data={[
                    {
                      x: tel.lateral_g, y: tel.longitudinal_g,
                      type: "scatter", mode: "markers",
                      marker: {
                        color: tel.speeds_kmh, colorscale: "Plasma",
                        size: 2.5, opacity: 0.7,
                        colorbar: { title: "km/h", titlefont: { color: "#666" }, tickfont: { color: "#666" }, thickness: 12 },
                      },
                      name: "GG Points",
                    },
                    // Friction circle reference
                    (() => {
                      const r = Math.max(...tel.lateral_g.map(Math.abs), ...tel.longitudinal_g.map(Math.abs));
                      const theta = Array.from({ length: 100 }, (_, i) => (i / 99) * 2 * Math.PI);
                      return {
                        x: theta.map(t => r * Math.cos(t)), y: theta.map(t => r * Math.sin(t)),
                        type: "scatter" as const, mode: "lines" as const, name: "Friction Circle",
                        line: { color: "#ffffff18", dash: "dot", width: 1 },
                      };
                    })(),
                  ]}
                  layout={{
                    ...PLOTLY_BASE,
                    title: { text: "GG Diagram", font: { color: "#555", size: 12 } },
                    xaxis: { ...PLOTLY_BASE.xaxis, title: { text: "Lateral G", font: { color: "#555" } }, zeroline: true, zerolinecolor: "#333" },
                    yaxis: { ...PLOTLY_BASE.yaxis, title: { text: "Longitudinal G", font: { color: "#555" } }, zeroline: true, zerolinecolor: "#333" },
                  } as Record<string, unknown>}
                  config={{ displayModeBar: false, responsive: true }}
                  style={{ width: "100%", height: "100%" }}
                  useResizeHandler
                />
              )}

              {activeTab === 2 && tel && (
                <Plot
                  data={[
                    { x: tel.distances, y: tel.wheel_load_fl_n, type: "scatter", mode: "lines", name: "FL", line: { color: "#3b82f6", width: 1.2 } },
                    { x: tel.distances, y: tel.wheel_load_fr_n, type: "scatter", mode: "lines", name: "FR", line: { color: "#f2a900", width: 1.2 } },
                    { x: tel.distances, y: tel.wheel_load_rl_n, type: "scatter", mode: "lines", name: "RL", line: { color: "#22c55e", width: 1.2 } },
                    { x: tel.distances, y: tel.wheel_load_rr_n, type: "scatter", mode: "lines", name: "RR", line: { color: "#ef4444", width: 1.2 } },
                  ]}
                  layout={{
                    ...PLOTLY_BASE,
                    title: { text: "Individual Wheel Loads", font: { color: "#555", size: 12 } },
                    xaxis: { ...PLOTLY_BASE.xaxis, title: { text: "Distance [m]", font: { color: "#555" } } },
                    yaxis: { ...PLOTLY_BASE.yaxis, title: { text: "Vertical Load [N]", font: { color: "#555" } } },
                    legend: { orientation: "h", y: 1.08, font: { color: "#888", size: 10 } },
                  } as Record<string, unknown>}
                  config={{ displayModeBar: false, responsive: true }}
                  style={{ width: "100%", height: "100%" }}
                  useResizeHandler
                />
              )}

              {activeTab === 3 && tel && (
                <Plot
                  data={[
                    { x: tel.distances, y: tel.aero_downforce_n, type: "scatter", mode: "lines", name: "Downforce", line: { color: "#a78bfa", width: 1.5 } },
                    { x: tel.distances, y: tel.aero_drag_n, type: "scatter", mode: "lines", name: "Drag", line: { color: "#f97316", width: 1.5 } },
                  ]}
                  layout={{
                    ...PLOTLY_BASE,
                    title: { text: "Aerodynamic Forces", font: { color: "#555", size: 12 } },
                    xaxis: { ...PLOTLY_BASE.xaxis, title: { text: "Distance [m]", font: { color: "#555" } } },
                    yaxis: { ...PLOTLY_BASE.yaxis, title: { text: "Force [N]", font: { color: "#555" } } },
                    legend: { orientation: "h", y: 1.08, font: { color: "#888", size: 10 } },
                  } as Record<string, unknown>}
                  config={{ displayModeBar: false, responsive: true }}
                  style={{ width: "100%", height: "100%" }}
                  useResizeHandler
                />
              )}

              {activeTab === 4 && ggv && (
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
                    title: { text: "GGV Performance Envelope", font: { color: "#555", size: 12 } },
                    xaxis: { ...PLOTLY_BASE.xaxis, title: { text: "Speed [km/h]", font: { color: "#555" } } },
                    yaxis: { ...PLOTLY_BASE.yaxis, title: { text: "Acceleration [g]", font: { color: "#555" } } },
                    legend: { orientation: "h", y: 1.08, font: { color: "#888", size: 10 } },
                  } as Record<string, unknown>}
                  config={{ displayModeBar: false, responsive: true }}
                  style={{ width: "100%", height: "100%" }}
                  useResizeHandler
                />
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
      </main>

      {/* ── RIGHT PANEL ────────────────────────────────────────────────────── */}
      <aside className="w-[180px] flex-shrink-0 border-l border-[#1a1a1a] overflow-y-auto p-3 space-y-3 custom-scrollbar">
        <p className="text-[9px] font-bold text-gray-700 uppercase tracking-[0.16em]">Session Info</p>

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
              <div key={text} className="flex items-center gap-2 opacity-30">
                <Icon size={10} className="text-[#f2a900]" />
                <span className="text-[9px] text-gray-500">{text}</span>
              </div>
            ))}
            <p className="text-[9px] text-gray-700 pt-2">Run simulation to populate.</p>
          </div>
        )}
      </aside>
    </div>
  );
}
