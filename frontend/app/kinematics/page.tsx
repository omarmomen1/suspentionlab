"use client";

import { useState, useCallback, useRef } from "react";
import dynamic from "next/dynamic";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

// ─── Types ────────────────────────────────────────────────────────────────────
type HP3 = [number, number, number];

interface Hardpoints {
  UWI_fwd: HP3; UWI_aft: HP3; UWO: HP3;
  LWI_fwd: HP3; LWI_aft: HP3; LWO: HP3;
  TRI: HP3; TRO: HP3;
  WC: HP3; CP: HP3;
  PRI: HP3; PRO: HP3;
}

interface KinResult {
  wheel_travel_mm: number[];
  camber_deg: number[];
  toe_deg: number[];
  caster_deg: number[];
  kpi_deg: number[];
  track_change_mm: number[];
  wheelbase_change_mm: number[];
  roll_center_height_mm: number[];
  motion_ratio: number[];
  scrub_radius_mm: number[];
  converged: boolean[];
  n_points: number;
  backend: string;
  all_converged: boolean;
}

// ─── Default hardpoints (right-front, open-wheel Formula car) ─────────────────
const DEFAULT_HP: Hardpoints = {
  UWI_fwd: [-50, 80, 300], UWI_aft: [50, 80, 300], UWO: [0, 650, 295],
  LWI_fwd: [-80, 80, 155], LWI_aft: [80, 80, 155], LWO: [0, 720, 145],
  TRI: [0, 150, 220], TRO: [-15, 710, 205],
  WC: [0, 760, 220], CP: [0, 760, 0],
  PRI: [-20, 300, 390], PRO: [-15, 690, 250],
};

// ─── Plot theme ───────────────────────────────────────────────────────────────
const THEME = {
  paper_bgcolor: "transparent", plot_bgcolor: "transparent",
  font: { color: "#777", size: 11, family: "Inter, monospace" },
  xaxis: { color: "#555", gridcolor: "#111", zerolinecolor: "#222",
           tickfont: { color: "#555", size: 10 } },
  yaxis: { color: "#555", gridcolor: "#111", zerolinecolor: "#222",
           tickfont: { color: "#555", size: 10 } },
  legend: { font: { color: "#777", size: 10 }, bgcolor: "rgba(0,0,0,0)",
            orientation: "h" as const, y: -0.2 },
  margin: { l: 60, r: 20, t: 36, b: 55 },
  autosize: true,
  hoverlabel: { bgcolor: "#0a0a0c", bordercolor: "#333", font: { color: "#ccc", size: 11 } },
};

function layout(title: string, xaxis?: object, yaxis?: object) {
  return {
    ...THEME,
    title: { text: title, font: { size: 12, color: "#555" }, x: 0.02 },
    xaxis: { ...THEME.xaxis, ...xaxis },
    yaxis: { ...THEME.yaxis, ...yaxis },
  };
}

const COLORS = {
  cyan:    "#22d3ee", violet: "#a78bfa", amber: "#fbbf24",
  emerald: "#34d399", rose:   "#fb7185", blue:  "#60a5fa",
  orange:  "#fb923c",
};

// ─── Small helpers ────────────────────────────────────────────────────────────
type Tab = "camber" | "toe" | "rc" | "mr" | "track" | "geometry";

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span className={`inline-block w-2 h-2 rounded-full ${ok ? "bg-emerald-500" : "bg-amber-500"}`} />
  );
}

function KPICard({ label, value, unit, sub, color = "#22d3ee" }:
  { label: string; value: string | number; unit?: string; sub?: string; color?: string }) {
  return (
    <div className="bg-[#0e0e10] border border-[#1e1e22] rounded-xl p-3 flex flex-col gap-0.5">
      <span className="text-[9px] font-bold tracking-[0.15em] text-gray-600 uppercase">{label}</span>
      <span className="text-[1.05rem] font-bold font-mono leading-tight" style={{ color }}>
        {typeof value === "number" ? value.toFixed(2) : value}
        {unit && <span className="text-[10px] font-normal text-gray-600 ml-1">{unit}</span>}
      </span>
      {sub && <span className="text-[9px] text-gray-700 leading-tight mt-0.5">{sub}</span>}
    </div>
  );
}

// ─── Hardpoint editor row ─────────────────────────────────────────────────────
function HPRow({ label, name, value, onChange }:
  { label: string; name: keyof Hardpoints; value: HP3;
    onChange: (k: keyof Hardpoints, v: HP3) => void }) {
  const axes = ["X", "Y", "Z"];
  return (
    <div className="grid grid-cols-[5rem_1fr_1fr_1fr] gap-1.5 items-center">
      <span className="text-[10px] text-gray-500 font-mono truncate">{label}</span>
      {[0, 1, 2].map(i => (
        <input
          key={i}
          type="number"
          step="1"
          value={value[i]}
          title={`${label} ${axes[i]}`}
          aria-label={`${label} ${axes[i]}`}
          className="w-full bg-[#0d0d0f] border border-[#1e1e22] rounded px-2 py-1
                     text-[10px] text-gray-300 font-mono text-center
                     focus:border-cyan-700 focus:outline-none hover:border-[#333] transition-colors"
          onChange={e => {
            const next = [...value] as HP3;
            next[i] = parseFloat(e.target.value) || 0;
            onChange(name, next);
          }}
        />
      ))}
    </div>
  );
}

// ─── Front-view geometry diagram ──────────────────────────────────────────────
function FrontViewDiagram({ hp, result, travelIdx }:
  { hp: Hardpoints; result: KinResult | null; travelIdx: number }) {
  // Project all points to Y-Z plane (columns 1 and 2)
  const pts = hp;
  const scale = 0.55; // px per mm
  const offsetY = 400; const offsetZ = 320;

  const py = (y: number) => offsetY - y * scale;
  const pz = (z: number) => offsetZ - z * scale;

  // Wishbone arm midpoints
  const uwiMY = (pts.UWI_fwd[1] + pts.UWI_aft[1]) / 2;
  const uwiMZ = (pts.UWI_fwd[2] + pts.UWI_aft[2]) / 2;
  const lwiMY = (pts.LWI_fwd[1] + pts.LWI_aft[1]) / 2;
  const lwiMZ = (pts.LWI_fwd[2] + pts.LWI_aft[2]) / 2;

  // Live RC and camber from result if available
  const rcHeight = result ? result.roll_center_height_mm[travelIdx] : 0;
  const camberDeg = result ? result.camber_deg[travelIdx] : 0;
  const dz = result ? result.wheel_travel_mm[travelIdx] : 0;

  // Wheel centre with travel applied
  const wcY = pts.WC[1];
  const wcZ = pts.WC[2] + dz;

  return (
    <svg width="100%" viewBox="0 0 600 400" className="w-full" style={{ maxHeight: 260 }}>
      {/* Ground line */}
      <line x1="0" y1={pz(0)} x2="600" y2={pz(0)} stroke="#222" strokeWidth="1" />
      <text x="8" y={pz(0) - 4} fill="#333" fontSize="9" fontFamily="monospace">ground</text>

      {/* Vehicle centreline */}
      <line x1={py(0)} y1="0" x2={py(0)} y2="400" stroke="#1a1a1a" strokeWidth="1" strokeDasharray="4,4" />

      {/* Lower wishbone arm */}
      <line x1={py(lwiMY)} y1={pz(lwiMZ)}
            x2={py(pts.LWO[1])} y2={pz(pts.LWO[2] + dz)}
            stroke={COLORS.blue} strokeWidth="2.5" strokeLinecap="round" />

      {/* Upper wishbone arm */}
      <line x1={py(uwiMY)} y1={pz(uwiMZ)}
            x2={py(pts.UWO[1])} y2={pz(pts.UWO[2] + dz)}
            stroke={COLORS.violet} strokeWidth="2.5" strokeLinecap="round" />

      {/* Upright */}
      <line x1={py(pts.LWO[1])} y1={pz(pts.LWO[2] + dz)}
            x2={py(pts.UWO[1])} y2={pz(pts.UWO[2] + dz)}
            stroke="#aaa" strokeWidth="2" strokeLinecap="round" />

      {/* Tierod */}
      <line x1={py(pts.TRI[1])} y1={pz(pts.TRI[2])}
            x2={py(pts.TRO[1])} y2={pz(pts.TRO[2] + dz)}
            stroke={COLORS.amber} strokeWidth="1.5" strokeDasharray="3,2" strokeLinecap="round" />

      {/* Wheel (tilted by camber) */}
      {(() => {
        const angle = camberDeg * (Math.PI / 180);
        const r = 110 * scale;
        const cy2 = py(wcY);
        const cz2 = pz(wcZ);
        const dy = Math.cos(angle) * r;
        const dz2 = -Math.sin(angle) * r;
        return (
          <>
            <line x1={cy2 - dy} y1={cz2 - dz2} x2={cy2 + dy} y2={cz2 + dz2}
                  stroke={COLORS.emerald} strokeWidth="4" strokeLinecap="round" opacity="0.8" />
            {/* Contact patch */}
            <circle cx={cy2} cy={pz(0)} r="3" fill={COLORS.emerald} opacity="0.6" />
          </>
        );
      })()}

      {/* Ball joints */}
      <circle cx={py(pts.UWO[1])} cy={pz(pts.UWO[2] + dz)} r="4" fill={COLORS.violet} />
      <circle cx={py(pts.LWO[1])} cy={pz(pts.LWO[2] + dz)} r="4" fill={COLORS.blue} />

      {/* Inboard pivots */}
      <rect x={py(uwiMY) - 4} y={pz(uwiMZ) - 4} width="8" height="8"
            fill="#1a1a2e" stroke={COLORS.violet} strokeWidth="1.5" />
      <rect x={py(lwiMY) - 4} y={pz(lwiMZ) - 4} width="8" height="8"
            fill="#1a1a2e" stroke={COLORS.blue} strokeWidth="1.5" />

      {/* Roll centre */}
      {result && (
        <>
          <circle cx={py(0)} cy={pz(rcHeight)} r="5" fill="none"
                  stroke={COLORS.rose} strokeWidth="2" />
          <line x1={py(0) - 8} y1={pz(rcHeight)} x2={py(0) + 8} y2={pz(rcHeight)}
                stroke={COLORS.rose} strokeWidth="1.5" />
          <line x1={py(0)} y1={pz(rcHeight) - 8} x2={py(0)} y2={pz(rcHeight) + 8}
                stroke={COLORS.rose} strokeWidth="1.5" />
          <text x={py(0) + 10} y={pz(rcHeight) + 4} fill={COLORS.rose}
                fontSize="9" fontFamily="monospace">
            RC {rcHeight.toFixed(0)} mm
          </text>
        </>
      )}

      {/* Legend */}
      <g transform="translate(8, 8)">
        <rect width="130" height="56" rx="4" fill="rgba(0,0,0,0.6)" />
        {[
          [COLORS.violet, "Upper wishbone"],
          [COLORS.blue,   "Lower wishbone"],
          [COLORS.amber,  "Tierod"],
          [COLORS.rose,   "Roll centre"],
        ].map(([c, l], i) => (
          <g key={l as string} transform={`translate(8, ${12 + i * 12})`}>
            <rect width="12" height="3" rx="1" fill={c as string} y="1" />
            <text x="16" y="8" fill="#666" fontSize="8.5" fontFamily="monospace">{l}</text>
          </g>
        ))}
      </g>
    </svg>
  );
}

// ─── Main page component ──────────────────────────────────────────────────────
export default function KinematicsPage() {
  const [hp, setHP]           = useState<Hardpoints>(DEFAULT_HP);
  const [zMin, setZMin]       = useState(-80);
  const [zMax, setZMax]       = useState(80);
  const [nSteps, setNSteps]   = useState(33);
  const [result, setResult]   = useState<KinResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("camber");
  const [travelIdx, setTravelIdx] = useState(0);

  const handleHP = useCallback((k: keyof Hardpoints, v: HP3) => {
    setHP(prev => ({ ...prev, [k]: v }));
  }, []);

  const solve = async () => {
    setLoading(true); setError(null);
    try {
      const res = await fetch("/api/v1/kinematics/solve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hardpoints: hp,
          z_min_mm: zMin, z_max_mm: zMax, n_steps: nSteps,
        }),
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail || `HTTP ${res.status}`);
      }
      const data: KinResult = await res.json();
      setResult(data);
      setTravelIdx(Math.floor(data.n_points / 2)); // start at neutral
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  // ── KPI values at current travel index ──────────────────────────────────
  const at = (key: keyof KinResult) =>
    result ? (result[key] as number[])[travelIdx] : null;

  const tabs: { id: Tab; label: string }[] = [
    { id: "camber",   label: "Camber & Toe" },
    { id: "rc",       label: "Roll Centre" },
    { id: "mr",       label: "Motion Ratio" },
    { id: "track",    label: "Track / WB" },
    { id: "toe",      label: "Caster / KPI" },
    { id: "geometry", label: "Front View" },
  ];

  const dz = result?.wheel_travel_mm ?? [];

  return (
    <div className="min-h-screen bg-[#070709] text-gray-200 font-['Inter',sans-serif]">
      <div className="flex h-screen overflow-hidden">

        {/* ── LEFT PANEL: Config ────────────────────────────────────────────── */}
        <div className="w-72 flex-shrink-0 border-r border-[#111] flex flex-col overflow-y-auto bg-[#080809]">
          <div className="px-4 pt-5 pb-3 border-b border-[#111]">
            <h1 className="text-sm font-bold text-white tracking-tight">
              Suspension Kinematics
            </h1>
            <p className="text-[10px] text-gray-600 mt-0.5">
              Double-wishbone · C++ Newton–Raphson solver
            </p>
          </div>

          <div className="px-4 py-3 space-y-4 flex-1">
            {/* Travel sweep */}
            <section>
              <h3 className="text-[9px] font-bold text-gray-700 uppercase tracking-[0.15em] pb-1.5 border-b border-[#111]">
                Travel Sweep
              </h3>
              <div className="grid grid-cols-3 gap-2 mt-2">
                {[
                  { label: "Droop mm", val: zMin, set: setZMin },
                  { label: "Bump mm",  val: zMax, set: setZMax },
                  { label: "Steps",    val: nSteps, set: setNSteps },
                ].map(({ label, val, set }) => (
                  <div key={label}>
                    <label className="text-[9px] text-gray-600">{label}</label>
                    <input
                      type="number" value={val} step="5"
                      aria-label={label}
                      className="w-full mt-0.5 bg-[#0d0d0f] border border-[#1e1e22] rounded px-2 py-1
                                 text-[11px] text-gray-300 font-mono text-center
                                 focus:border-cyan-700 focus:outline-none"
                      onChange={e => (set as any)(parseInt(e.target.value) || 0)}
                    />
                  </div>
                ))}
              </div>
            </section>

            {/* Hardpoints */}
            {([
              ["Upper Wishbone", [
                ["UWI_fwd", "UWI fwd"],
                ["UWI_aft", "UWI aft"],
                ["UWO",     "UWO (UBJ)"],
              ]],
              ["Lower Wishbone", [
                ["LWI_fwd", "LWI fwd"],
                ["LWI_aft", "LWI aft"],
                ["LWO",     "LWO (LBJ)"],
              ]],
              ["Tierod", [
                ["TRI", "TR inboard"],
                ["TRO", "TR outboard"],
              ]],
              ["Wheel / Patch", [
                ["WC", "Wheel ctr"],
                ["CP", "Contact pt"],
              ]],
              ["Pushrod", [
                ["PRI", "PR inboard"],
                ["PRO", "PR outboard"],
              ]],
            ] as [string, [keyof Hardpoints, string][]][]).map(([section, rows]) => (
              <section key={section}>
                <h3 className="text-[9px] font-bold text-gray-700 uppercase tracking-[0.15em] pb-1.5 border-b border-[#111]">
                  {section}
                </h3>
                <div className="mt-2 space-y-1.5">
                  <div className="grid grid-cols-[5rem_1fr_1fr_1fr] gap-1.5 mb-1">
                    <span />
                    {["X", "Y", "Z"].map(a => (
                      <span key={a} className="text-[9px] text-center text-gray-700 font-mono">{a}</span>
                    ))}
                  </div>
                  {rows.map(([key, label]) => (
                    <HPRow key={key} label={label} name={key} value={hp[key]} onChange={handleHP} />
                  ))}
                </div>
              </section>
            ))}
          </div>

          {/* Solve button */}
          <div className="px-4 py-4 border-t border-[#111]">
            <button
              id="kinematics-solve-btn"
              onClick={solve}
              disabled={loading}
              className="w-full py-2.5 rounded-lg font-bold text-sm transition-all
                         bg-gradient-to-r from-cyan-600 to-violet-700
                         hover:from-cyan-500 hover:to-violet-600
                         disabled:opacity-40 disabled:cursor-not-allowed
                         text-white shadow-lg shadow-cyan-900/30"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Solving…
                </span>
              ) : "Solve Kinematics"}
            </button>
            {error && (
              <p className="mt-2 text-[10px] text-rose-400 leading-tight">{error}</p>
            )}
            {result && (
              <p className="mt-2 text-[9px] text-gray-600 text-center">
                <StatusDot ok={result.all_converged} />{" "}
                {result.n_points} pts · {result.backend.includes("C++") ? "⚡ C++ core" : "🐍 Python"}
              </p>
            )}
          </div>
        </div>

        {/* ── CENTRE: Plots ─────────────────────────────────────────────────── */}
        <div className="flex-1 flex flex-col overflow-hidden">

          {/* KPI strip */}
          {result ? (
            <div className="px-4 pt-4 pb-3 grid grid-cols-6 gap-2 border-b border-[#111]">
              <KPICard label="Camber" value={at("camber_deg") ?? 0} unit="°"
                       sub={`at dz=${result.wheel_travel_mm[travelIdx].toFixed(0)}mm`}
                       color={COLORS.cyan} />
              <KPICard label="Toe"    value={at("toe_deg") ?? 0} unit="°"
                       sub="positive = toe-out" color={COLORS.violet} />
              <KPICard label="RC Height" value={at("roll_center_height_mm") ?? 0} unit="mm"
                       sub="above ground" color={COLORS.amber} />
              <KPICard label="Motion Ratio" value={at("motion_ratio") ?? 0}
                       sub="spring/wheel" color={COLORS.emerald} />
              <KPICard label="Track Δ" value={at("track_change_mm") ?? 0} unit="mm"
                       sub="from neutral" color={COLORS.blue} />
              <KPICard label="Scrub R" value={at("scrub_radius_mm") ?? 0} unit="mm"
                       sub="CP vs SA" color={COLORS.rose} />
            </div>
          ) : (
            <div className="px-4 pt-4 pb-3 flex items-center gap-3 border-b border-[#111]">
              <div className="w-2 h-2 rounded-full bg-cyan-600 animate-pulse" />
              <span className="text-[11px] text-gray-600">Configure hardpoints and press Solve Kinematics</span>
            </div>
          )}

          {/* Travel scrubber */}
          {result && (
            <div className="px-4 py-2 border-b border-[#111] flex items-center gap-3">
              <span className="text-[10px] text-gray-600 w-20 flex-shrink-0">
                dz = {result.wheel_travel_mm[travelIdx].toFixed(1)} mm
              </span>
              <input
                type="range"
                min={0} max={result.n_points - 1}
                value={travelIdx}
                aria-label="Wheel travel scrubber"
                className="flex-1 accent-cyan-500"
                onChange={e => setTravelIdx(parseInt(e.target.value))}
              />
              <span className="text-[9px] text-gray-700 w-16 text-right flex-shrink-0">
                {result.wheel_travel_mm[0].toFixed(0)} → {result.wheel_travel_mm[result.n_points-1].toFixed(0)} mm
              </span>
            </div>
          )}

          {/* Tabs */}
          <div className="flex border-b border-[#111] px-4 pt-1">
            {tabs.map(t => (
              <button
                key={t.id}
                id={`kin-tab-${t.id}`}
                onClick={() => setActiveTab(t.id)}
                className={`px-3 py-2 text-[10px] font-semibold transition-colors mr-1 border-b-2
                  ${activeTab === t.id
                    ? "border-cyan-500 text-cyan-400"
                    : "border-transparent text-gray-600 hover:text-gray-400"}`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Plot area */}
          <div className="flex-1 p-4 overflow-hidden">
            {!result ? (
              <EmptyState />
            ) : (
              <div className="w-full h-full">

                {activeTab === "camber" && (
                  <Plot
                    data={[
                      {
                        x: dz, y: result.camber_deg, name: "Camber",
                        type: "scatter", mode: "lines",
                        line: { color: COLORS.cyan, width: 2.5 },
                      },
                      {
                        x: dz, y: result.toe_deg, name: "Toe",
                        type: "scatter", mode: "lines", yaxis: "y2",
                        line: { color: COLORS.violet, width: 2, dash: "dash" },
                      },
                    ]}
                    layout={{
                      ...layout("Camber & Toe vs Wheel Travel",
                        { title: { text: "Wheel Travel [mm]", font: { size: 10, color: "#555" } } },
                        { title: { text: "Camber [°]", font: { size: 10, color: "#555" } } }),
                      yaxis2: {
                        ...THEME.yaxis,
                        title: { text: "Toe [°]", font: { size: 10, color: "#555" } },
                        overlaying: "y", side: "right",
                      },
                      shapes: [{
                        type: "line" as const, x0: dz[travelIdx], x1: dz[travelIdx],
                        y0: 0, y1: 1, yref: "paper",
                        line: { color: COLORS.amber, width: 1, dash: "dot" },
                      }],
                    }}
                    config={{ responsive: true, displaylogo: false }}
                    style={{ width: "100%", height: "100%" }}
                    useResizeHandler
                  />
                )}

                {activeTab === "rc" && (
                  <Plot
                    data={[{
                      x: dz, y: result.roll_center_height_mm, name: "RC Height",
                      type: "scatter", mode: "lines",
                      fill: "tozeroy", fillcolor: "rgba(251,113,133,0.08)",
                      line: { color: COLORS.rose, width: 2.5 },
                    }]}
                    layout={layout("Roll-Centre Height vs Wheel Travel",
                      { title: { text: "Wheel Travel [mm]", font: { size: 10, color: "#555" } } },
                      { title: { text: "RC Height [mm]", font: { size: 10, color: "#555" } } })}
                    config={{ responsive: true, displaylogo: false }}
                    style={{ width: "100%", height: "100%" }}
                    useResizeHandler
                  />
                )}

                {activeTab === "mr" && (
                  <Plot
                    data={[
                      {
                        x: dz.slice(1), y: result.motion_ratio.slice(1), name: "Motion Ratio",
                        type: "scatter", mode: "lines",
                        line: { color: COLORS.emerald, width: 2.5 },
                      },
                    ]}
                    layout={layout("Motion Ratio vs Wheel Travel",
                      { title: { text: "Wheel Travel [mm]", font: { size: 10, color: "#555" } } },
                      { title: { text: "MR = Δspring / Δwheel [−]", font: { size: 10, color: "#555" } } })}
                    config={{ responsive: true, displaylogo: false }}
                    style={{ width: "100%", height: "100%" }}
                    useResizeHandler
                  />
                )}

                {activeTab === "track" && (
                  <Plot
                    data={[
                      {
                        x: dz, y: result.track_change_mm, name: "Track Change",
                        type: "scatter", mode: "lines",
                        line: { color: COLORS.blue, width: 2.5 },
                      },
                      {
                        x: dz, y: result.wheelbase_change_mm, name: "Wheelbase Change",
                        type: "scatter", mode: "lines",
                        line: { color: COLORS.orange, width: 2, dash: "dash" },
                      },
                    ]}
                    layout={layout("Track Width & Wheelbase Change vs Wheel Travel",
                      { title: { text: "Wheel Travel [mm]", font: { size: 10, color: "#555" } } },
                      { title: { text: "Δ [mm]", font: { size: 10, color: "#555" } } })}
                    config={{ responsive: true, displaylogo: false }}
                    style={{ width: "100%", height: "100%" }}
                    useResizeHandler
                  />
                )}

                {activeTab === "toe" && (
                  <Plot
                    data={[
                      {
                        x: dz, y: result.caster_deg, name: "Caster",
                        type: "scatter", mode: "lines",
                        line: { color: COLORS.amber, width: 2.5 },
                      },
                      {
                        x: dz, y: result.kpi_deg, name: "KPI",
                        type: "scatter", mode: "lines",
                        line: { color: COLORS.orange, width: 2, dash: "dot" },
                      },
                      {
                        x: dz, y: result.scrub_radius_mm, name: "Scrub Radius",
                        type: "scatter", mode: "lines", yaxis: "y2",
                        line: { color: COLORS.rose, width: 1.5, dash: "dash" },
                      },
                    ]}
                    layout={{
                      ...layout("Caster, KPI & Scrub Radius vs Wheel Travel",
                        { title: { text: "Wheel Travel [mm]", font: { size: 10, color: "#555" } } },
                        { title: { text: "Angle [°]", font: { size: 10, color: "#555" } } }),
                      yaxis2: {
                        ...THEME.yaxis,
                        title: { text: "Scrub Radius [mm]", font: { size: 10, color: "#555" } },
                        overlaying: "y", side: "right",
                      },
                    }}
                    config={{ responsive: true, displaylogo: false }}
                    style={{ width: "100%", height: "100%" }}
                    useResizeHandler
                  />
                )}

                {activeTab === "geometry" && (
                  <div className="w-full h-full flex flex-col gap-3">
                    <FrontViewDiagram hp={hp} result={result} travelIdx={travelIdx} />
                    <p className="text-[9px] text-gray-700 text-center">
                      Front view (Y–Z plane). Scrub ball → drag scrubber above to animate.
                    </p>
                  </div>
                )}

              </div>
            )}
          </div>
        </div>

        {/* ── RIGHT PANEL: Outputs table ────────────────────────────────────── */}
        <div className="w-52 flex-shrink-0 border-l border-[#111] flex flex-col overflow-y-auto bg-[#080809]">
          <div className="px-3 pt-4 pb-2 border-b border-[#111]">
            <span className="text-[9px] font-bold text-gray-700 uppercase tracking-[0.15em]">
              At dz = {result ? result.wheel_travel_mm[travelIdx].toFixed(1) : "—"} mm
            </span>
          </div>

          {result ? (
            <div className="px-3 py-3 space-y-1.5">
              {([
                ["Camber",     result.camber_deg[travelIdx],            "°",   COLORS.cyan],
                ["Toe",        result.toe_deg[travelIdx],               "°",   COLORS.violet],
                ["Caster",     result.caster_deg[travelIdx],            "°",   COLORS.amber],
                ["KPI",        result.kpi_deg[travelIdx],               "°",   COLORS.orange],
                ["RC Height",  result.roll_center_height_mm[travelIdx], "mm",  COLORS.rose],
                ["Track Δ",    result.track_change_mm[travelIdx],       "mm",  COLORS.blue],
                ["WB Δ",       result.wheelbase_change_mm[travelIdx],   "mm",  COLORS.blue],
                ["MR",         result.motion_ratio[travelIdx],          "−",   COLORS.emerald],
                ["Scrub R",    result.scrub_radius_mm[travelIdx],       "mm",  COLORS.rose],
              ] as [string, number, string, string][]).map(([label, val, unit, color]) => (
                <div key={label} className="flex items-center justify-between py-1 border-b border-[#111]">
                  <span className="text-[9px] text-gray-600">{label}</span>
                  <span className="text-[10px] font-mono font-bold" style={{ color }}>
                    {val.toFixed(2)} <span className="text-gray-700 font-normal">{unit}</span>
                  </span>
                </div>
              ))}

              <div className="pt-2">
                <div className="text-[8px] text-gray-700 space-y-0.5">
                  <div>Convergence: {result.all_converged ? "✓ all" : "⚠ partial"}</div>
                  <div>Points: {result.n_points}</div>
                  <div className="leading-tight">
                    {result.backend.includes("C++") ? "⚡ C++ kinematics_core" : "🐍 Python fallback"}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="px-3 py-4 text-[10px] text-gray-700 space-y-1">
              <p>Outputs appear here after solving.</p>
            </div>
          )}

          {/* Coordinate system reference */}
          <div className="mt-auto px-3 py-4 border-t border-[#111]">
            <p className="text-[8px] text-gray-700 font-bold uppercase tracking-widest mb-1.5">
              Coord System
            </p>
            <div className="text-[8px] text-gray-700 space-y-0.5 font-mono">
              <div><span className="text-cyan-700">X</span> → forward</div>
              <div><span className="text-violet-700">Y</span> → outboard</div>
              <div><span className="text-emerald-700">Z</span> ↑ up</div>
              <div className="mt-1 text-gray-800">All inputs: mm</div>
              <div className="text-gray-800">Angles: degrees</div>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────────
function EmptyState() {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center gap-5 select-none">
      {/* Animated geometry diagram */}
      <svg width="180" height="140" viewBox="0 0 180 140" className="opacity-60">
        {/* Ground */}
        <line x1="10" y1="128" x2="170" y2="128" stroke="#1a1a1a" strokeWidth="1.5" />
        {/* Lower wishbone */}
        <line x1="40" y1="90" x2="140" y2="80" stroke="#60a5fa" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate"
            values="0 40 90; 2 40 90; 0 40 90" dur="3s" repeatCount="indefinite" />
        </line>
        {/* Upper wishbone */}
        <line x1="50" y1="40" x2="138" y2="38" stroke="#a78bfa" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate"
            values="0 50 40; -2 50 40; 0 50 40" dur="3s" repeatCount="indefinite" />
        </line>
        {/* Upright */}
        <line x1="138" y1="38" x2="140" y2="80" stroke="#888" strokeWidth="2" strokeLinecap="round" />
        {/* Wheel */}
        <ellipse cx="140" cy="104" rx="24" ry="24" fill="none" stroke="#34d399"
                 strokeWidth="3" opacity="0.6">
          <animateTransform attributeName="transform" type="translate"
            values="0 0; 0 -4; 0 0" dur="3s" repeatCount="indefinite" />
        </ellipse>
        {/* Ball joints */}
        <circle cx="140" cy="38" r="4" fill="#a78bfa" />
        <circle cx="140" cy="80" r="4" fill="#60a5fa" />
        {/* RC dot */}
        <circle cx="0" cy="104" r="5" fill="none" stroke="#fb7185" strokeWidth="1.5">
          <animate attributeName="cy" values="100; 110; 100" dur="3s" repeatCount="indefinite" />
        </circle>
      </svg>
      <div className="text-center space-y-1.5">
        <p className="text-sm font-semibold text-gray-500">
          Double-Wishbone Kinematics Solver
        </p>
        <p className="text-[10px] text-gray-700 max-w-xs leading-relaxed">
          C++ Newton–Raphson on 5 rigid-link constraints.<br />
          Outputs: camber · toe · caster · KPI · RC height · motion ratio · scrub radius.
        </p>
      </div>
      <div className="grid grid-cols-3 gap-3 text-[9px] text-gray-700">
        {["Camber vs travel", "RC migration", "Motion ratio", "Track change", "Caster", "Scrub radius"].map(f => (
          <span key={f} className="flex items-center gap-1">
            <span className="text-cyan-800">◆</span> {f}
          </span>
        ))}
      </div>
    </div>
  );
}
