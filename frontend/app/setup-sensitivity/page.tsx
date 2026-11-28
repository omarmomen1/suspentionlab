"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import {
  Sliders, BarChart3, Activity, TrendingDown, TrendingUp,
  AlertCircle, CheckCircle, Info, RefreshCw, Zap,
  Wind, Gauge, ChevronDown, ChevronRight, GitCompare,
} from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import PlanGate from "../../components/PlanGate";
import SetupDiffViewer from "../../components/sim/SetupDiffViewer";
import Plot from "../../components/sim/Plot";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Types ───────────────────────────────────────────────────────────────────

interface SuspensionSetup {
  k_spring_front: number;   // N/m
  k_spring_rear:  number;   // N/m
  k_arb_front:    number;   // N/m
  k_arb_rear:     number;   // N/m
  ride_height_front: number; // mm
  ride_height_rear:  number; // mm
}

interface SensitivityResult {
  arb_balance: {
    baseline_arb_balance:        number;
    perturbed_arb_balance:       number;
    delta_lat_transfer_front_n:  number;
    delta_lat_transfer_rear_n:   number;
    understeer_tendency:         string;
  };
  ride_height_sensitivity: {
    delta_rh_front_mm:         number;
    delta_downforce_total_n:   number;
    delta_downforce_front_n:   number;
    delta_downforce_rear_n:    number;
    note:                      string;
  };
  suspension_info: {
    k_spring_front_nm:          number;
    k_spring_rear_nm:           number;
    k_arb_front_nm:             number;
    k_arb_rear_nm:              number;
    ride_height_front_mm:       number;
    ride_height_rear_mm:        number;
    roll_stiffness_front_nmrad: number;
    roll_stiffness_rear_nmrad:  number;
    roll_stiffness_total_nmrad: number;
    pitch_stiffness_nmrad:      number;
    arb_balance_fraction:       number;
  };
  operating_point: {
    speed_ms:     number;
    speed_kmh:    number;
    lateral_g:    number;
    q_dynamic_pa: number;
  };
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const PLOTLY_BASE = {
  paper_bgcolor: "transparent",
  plot_bgcolor:  "transparent",
  font:  { color: "#94A3B8", size: 11, family: "Inter, monospace" },
  xaxis: { color: "#94A3B8", gridcolor: "#1a1a1c", zerolinecolor: "#252525", tickfont: { color: "#94A3B8" } },
  yaxis: { color: "#94A3B8", gridcolor: "#1a1a1c", zerolinecolor: "#252525", tickfont: { color: "#94A3B8" } },
  margin: { l: 55, r: 20, t: 36, b: 50 },
  autosize: true,
  legend: { font: { color: "#888", size: 10 } },
};

function Slider({
  label, unit, value, min, max, step = 100,
  onChange, fmt = (v: number) => v.toFixed(0),
}: {
  label: string; unit: string; value: number;
  min: number; max: number; step?: number;
  onChange: (v: number) => void;
  fmt?: (v: number) => string;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-400">{label}</span>
        <span className="text-xs font-mono text-white">
          {fmt(value)} <span className="text-zinc-300 text-xs">{unit}</span>
        </span>
      </div>
      <div className="relative h-1.5 bg-[#1a1a1c] rounded-full">
        <div
          className="absolute h-full bg-gradient-to-r from-[#C8F04B]/60 to-[#C8F04B] rounded-full"
          style={{ width: `${pct}%` }}
        />
        <input
          type="range" min={min} max={max} step={step} value={value}
          onChange={e => onChange(Number(e.target.value))}
          className="absolute inset-0 w-full opacity-0 cursor-pointer h-full"
        />
      </div>
      <div className="flex justify-between text-xs text-zinc-300">
        <span>{min.toLocaleString()}</span>
        <span>{max.toLocaleString()}</span>
      </div>
    </div>
  );
}

function Badge({
  label, value, ok, unit = "",
}: { label: string; value: string | number; ok?: boolean; unit?: string }) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-[#1a1a1c] last:border-0">
      <span className="text-xs text-zinc-400">{label}</span>
      <div className="flex items-center gap-1.5">
        {ok !== undefined && (
          ok
            ? <CheckCircle size={10} className="text-emerald-500" />
            : <AlertCircle size={10} className="text-red-500" />
        )}
        <span className="text-xs font-mono text-white">{value}{unit && <span className="text-zinc-300 ml-0.5 text-xs">{unit}</span>}</span>
      </div>
    </div>
  );
}

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-[#111113] border border-[#252525] rounded-xl p-4 ${className}`}>
      {children}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-xs font-bold text-zinc-300 uppercase tracking-[0.16em] mb-3">{children}</div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

function SetupSensitivityContent() {
  const { fetchWithAuth } = useAuth();
  const [viewMode, setViewMode] = useState<"diff" | "sensitivity">("diff");

  const [setup, setSetup] = useState<SuspensionSetup>({
    k_spring_front:    35_000,
    k_spring_rear:     45_000,
    k_arb_front:       15_000,
    k_arb_rear:        10_000,
    ride_height_front: 30,
    ride_height_rear:  60,
  });

  const [operatingPoint, setOperatingPoint] = useState({
    speed_ms:         50,
    lateral_g:        2.0,
    delta_arb_front:  5_000,
    delta_ride_height: 5,
  });

  const [result, setResult] = useState<SensitivityResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Debounced auto-fetch on setup change
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchSensitivity = useCallback(async (s: SuspensionSetup, op: typeof operatingPoint) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithAuth("/api/v1/lapsim/sensitivity", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          speed_ms:          op.speed_ms,
          lateral_g:         op.lateral_g,
          delta_arb_front:   op.delta_arb_front,
          delta_ride_height: op.delta_ride_height,
          vehicle: {
            mass_props: { total_mass: 800, h_cog: 0.30, wheelbase: 2.70,
                          cog_dist_front: 1.35, track_front: 1.55, track_rear: 1.52 },
            aero: { cl_base: 1.8, cd_base: 0.95, frontal_area: 1.70,
                    cop_fraction: 0.45, cl_rh_sens: 0.02 },
            suspension: {
              k_spring_front: s.k_spring_front,
              k_spring_rear:  s.k_spring_rear,
              k_arb_front:    s.k_arb_front,
              k_arb_rear:     s.k_arb_rear,
              ride_height_front: s.ride_height_front,
              ride_height_rear:  s.ride_height_rear,
            },
          },
        }),
      });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      setResult(await res.json());
    } catch (e: any) {
      setError(e.message ?? "Request failed");
    } finally {
      setLoading(false);
    }
  }, [fetchWithAuth]);

  // Debounce slider changes
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchSensitivity(setup, operatingPoint);
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [setup, operatingPoint, fetchSensitivity]);

  // Update individual setup field
  const setS = (key: keyof SuspensionSetup) => (v: number) =>
    setSetup(prev => ({ ...prev, [key]: v }));

  // Derived roll stiffness (client-side preview, updated from result when available)
  const K_phi_f = ((setup.k_spring_front + setup.k_arb_front) * 1.55 ** 2) / 2;
  const K_phi_r = ((setup.k_spring_rear  + setup.k_arb_rear)  * 1.52 ** 2) / 2;
  const arb_bal_preview = K_phi_f / (K_phi_f + K_phi_r);

  const si = result?.suspension_info;
  const ab = result?.arb_balance;
  const rh = result?.ride_height_sensitivity;

  // ── Pareto chart: ARB balance vs relative load transfer ───────────────────
  const arbChartData = ab ? [
    {
      type: "bar" as const,
      name: "Baseline",
      x: ["Front Δ Load Transfer"],
      y: [0],
      marker: { color: "#C8F04B" },
    },
    {
      type: "bar" as const,
      name: `+${operatingPoint.delta_arb_front.toLocaleString()} N/m ARB`,
      x: ["Front Δ Load Transfer"],
      y: [ab.delta_lat_transfer_front_n],
      marker: { color: ab.delta_lat_transfer_front_n > 0 ? "#ef4444" : "#22c55e" },
    },
  ] : [];

  // ── Roll stiffness donut data ─────────────────────────────────────────────
  const donutData: any[] = si
    ? [({
        type: "pie" as const,
        values: [si.roll_stiffness_front_nmrad, si.roll_stiffness_rear_nmrad],
        labels: ["Front", "Rear"],
        hole: 0.62,
        marker: { colors: ["#C8F04B", "#3b82f6"] },
        textinfo: "none",
        hovertemplate: "%{label}: %{value:.0f} N·m/rad<extra></extra>",
      } as any)]
    : [];

  // ── Downforce sensitivity bar ─────────────────────────────────────────────
  const dfData = rh
    ? [{
        type: "bar" as const,
        x: ["Total", "Front", "Rear"],
        y: [rh.delta_downforce_total_n, rh.delta_downforce_front_n, rh.delta_downforce_rear_n],
        marker: {
          color: [
            rh.delta_downforce_total_n > 0 ? "#22c55e" : "#ef4444",
            rh.delta_downforce_front_n > 0 ? "#22c55e" : "#ef4444",
            rh.delta_downforce_rear_n  > 0 ? "#22c55e" : "#ef4444",
          ],
        },
        text: [
          `${rh.delta_downforce_total_n > 0 ? "+" : ""}${rh.delta_downforce_total_n.toFixed(0)}N`,
          `${rh.delta_downforce_front_n > 0 ? "+" : ""}${rh.delta_downforce_front_n.toFixed(0)}N`,
          `${rh.delta_downforce_rear_n  > 0 ? "+" : ""}${rh.delta_downforce_rear_n.toFixed(0)}N`,
        ],
        textposition: "outside" as const,
        textfont: { color: "#888", size: 10 },
      }]
    : [];

  // ── UI ────────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#0a0a0b] text-white px-4 py-6">
      <div className="max-w-[1600px] mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-lg font-bold text-white flex items-center gap-2">
              <Sliders size={18} className="text-[#C8F04B]" />
              Setup Sensitivity
            </h1>
            <p className="text-xs text-zinc-400 mt-0.5">
              Real-time suspension setup analysis — ARB balance, ride height, aero coupling
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center bg-white/5 border border-white/10 rounded-xl p-1">
              <button
                onClick={() => setViewMode("diff")}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold flex items-center gap-1.5 transition-all ${
                  viewMode === "diff"
                    ? "bg-signal text-carbon shadow-md"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                <GitCompare size={13} />
                Setup Diff (A vs B)
              </button>
              <button
                onClick={() => setViewMode("sensitivity")}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold flex items-center gap-1.5 transition-all ${
                  viewMode === "sensitivity"
                    ? "bg-signal text-carbon shadow-md"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                <Sliders size={13} />
                Sensitivity Sliders
              </button>
            </div>
            {loading && <RefreshCw size={13} className="text-[#C8F04B] animate-spin" />}
            {error && (
              <span className="text-xs text-red-400 flex items-center gap-1">
                <AlertCircle size={11} /> {error}
              </span>
            )}
          </div>
        </div>

        {viewMode === "diff" ? (
          <div className="animate-in fade-in duration-200">
            <SetupDiffViewer activeSetup={setup} />
          </div>
        ) : (
          <div className="grid grid-cols-[320px_1fr] gap-4">

          {/* ── Left panel: sliders ─────────────────────────────────────── */}
          <div className="space-y-4">

            <Card>
              <SectionTitle>Spring Rates (kN/m · N/mm)</SectionTitle>
              <div className="space-y-4">
                <Slider label="Front spring" unit="kN/m (N/mm)" value={setup.k_spring_front}
                  min={10_000} max={80_000} step={500} onChange={setS("k_spring_front")}
                  fmt={v => (v/1000).toFixed(1)} />
                <Slider label="Rear spring" unit="kN/m (N/mm)" value={setup.k_spring_rear}
                  min={10_000} max={80_000} step={500} onChange={setS("k_spring_rear")}
                  fmt={v => (v/1000).toFixed(1)} />
              </div>
            </Card>

            <Card>
              <SectionTitle>Anti-Roll Bars (kN/m · N/mm)</SectionTitle>
              <div className="space-y-4">
                <Slider label="Front ARB" unit="kN/m (N/mm)" value={setup.k_arb_front}
                  min={0} max={50_000} step={1_000} onChange={setS("k_arb_front")}
                  fmt={v => (v/1000).toFixed(1)} />
                <Slider label="Rear ARB" unit="kN/m (N/mm)" value={setup.k_arb_rear}
                  min={0} max={50_000} step={1_000} onChange={setS("k_arb_rear")}
                  fmt={v => (v/1000).toFixed(1)} />
              </div>
            </Card>

            <Card>
              <SectionTitle>Ride Height</SectionTitle>
              <div className="space-y-4">
                <Slider label="Front RH" unit="mm" value={setup.ride_height_front}
                  min={10} max={80} step={1} onChange={setS("ride_height_front")}
                  fmt={v => v.toFixed(0)} />
                <Slider label="Rear RH" unit="mm" value={setup.ride_height_rear}
                  min={15} max={100} step={1} onChange={setS("ride_height_rear")}
                  fmt={v => v.toFixed(0)} />
              </div>
            </Card>

            <Card>
              <SectionTitle>Operating Point</SectionTitle>
              <div className="space-y-4">
                <Slider label="Corner speed" unit="km/h"
                  value={operatingPoint.speed_ms * 3.6}
                  min={36} max={324} step={3.6}
                  onChange={v => setOperatingPoint(p => ({ ...p, speed_ms: v / 3.6 }))}
                  fmt={v => v.toFixed(0)} />
                <Slider label="Lateral G" unit="g"
                  value={operatingPoint.lateral_g}
                  min={0.5} max={4.0} step={0.1}
                  onChange={v => setOperatingPoint(p => ({ ...p, lateral_g: v }))}
                  fmt={v => v.toFixed(1)} />
                <Slider label="ARB perturbation" unit="kN/m (N/mm)"
                  value={operatingPoint.delta_arb_front}
                  min={500} max={20_000} step={500}
                  onChange={v => setOperatingPoint(p => ({ ...p, delta_arb_front: v }))}
                  fmt={v => (v/1000).toFixed(1)} />
                <Slider label="RH perturbation" unit="mm"
                  value={operatingPoint.delta_ride_height}
                  min={1} max={20} step={1}
                  onChange={v => setOperatingPoint(p => ({ ...p, delta_ride_height: v }))}
                  fmt={v => v.toFixed(0)} />
              </div>
            </Card>

            {/* Quick stats */}
            {si && (
              <Card>
                <SectionTitle>Stiffness Summary</SectionTitle>
                <div className="space-y-0">
                  <Badge label="Front roll stiffness" value={si.roll_stiffness_front_nmrad.toFixed(0)} unit=" N·m/rad" />
                  <Badge label="Rear roll stiffness"  value={si.roll_stiffness_rear_nmrad.toFixed(0)}  unit=" N·m/rad" />
                  <Badge label="Total roll stiffness" value={si.roll_stiffness_total_nmrad.toFixed(0)} unit=" N·m/rad" />
                  <Badge label="Pitch stiffness"      value={si.pitch_stiffness_nmrad.toFixed(0)}      unit=" N·m/rad" />
                </div>
              </Card>
            )}
          </div>

          {/* ── Right panel: charts ─────────────────────────────────────── */}
          <div className="space-y-4">

            {/* ARB balance + understeer row */}
            <div className="grid grid-cols-3 gap-4">

              {/* ARB balance gauge */}
              <Card className="flex flex-col">
                <SectionTitle>ARB Balance</SectionTitle>
                <div className="flex-1 flex flex-col items-center justify-center gap-2">
                  <div className="relative w-24 h-24">
                    <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
                      <circle cx="50" cy="50" r="40" fill="none"
                        stroke="#1a1a1c" strokeWidth="12" />
                      {/* Front (gold) */}
                      <circle cx="50" cy="50" r="40" fill="none"
                        stroke="#C8F04B" strokeWidth="12"
                        strokeDasharray={`${(si?.arb_balance_fraction ?? arb_bal_preview) * 251.2} 251.2`}
                        strokeLinecap="round" />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center rotate-0">
                      <span className="text-xl font-bold text-[#C8F04B]">
                        {((si?.arb_balance_fraction ?? arb_bal_preview) * 100).toFixed(1)}%
                      </span>
                      <span className="text-xs text-zinc-300">front</span>
                    </div>
                  </div>
                  <div className="text-xs text-zinc-400 text-center leading-relaxed">
                    <span className="text-[#C8F04B]">● </span> Front &nbsp;
                    <span className="text-blue-400">● </span> Rear
                  </div>
                  <div className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                    (si?.arb_balance_fraction ?? arb_bal_preview) > 0.52
                      ? "bg-red-500/10 text-red-400"
                      : (si?.arb_balance_fraction ?? arb_bal_preview) < 0.45
                        ? "bg-blue-500/10 text-blue-400"
                        : "bg-emerald-500/10 text-emerald-400"
                  }`}>
                    {(si?.arb_balance_fraction ?? arb_bal_preview) > 0.52
                      ? "Understeer bias"
                      : (si?.arb_balance_fraction ?? arb_bal_preview) < 0.45
                        ? "Oversteer bias"
                        : "Balanced"}
                  </div>
                </div>
              </Card>

              {/* Roll stiffness donut */}
              <Card>
                <SectionTitle>Roll Stiffness Split</SectionTitle>
                {donutData.length > 0 ? (
                  <Plot
                    data={donutData}
                    layout={{
                      ...PLOTLY_BASE,
                      height: 160,
                      showlegend: true,
                      legend: { orientation: "h", y: -0.2, font: { color: "#888", size: 9 } },
                      margin: { l: 0, r: 0, t: 10, b: 30 },
                    }}
                    config={{ displayModeBar: false }}
                    style={{ width: "100%", height: 160 }}
                  />
                ) : (
                  <div className="h-40 flex items-center justify-center text-xs text-zinc-300">
                    Loading…
                  </div>
                )}
              </Card>

              {/* Understeer effect card */}
              <Card className="flex flex-col justify-center gap-3">
                <SectionTitle>ARB Perturbation Effect</SectionTitle>
                {ab ? (
                  <>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-400">Front Δ Load Transfer</span>
                        <span className={`text-[13px] font-bold font-mono ${
                          ab.delta_lat_transfer_front_n > 0 ? "text-red-400" : "text-emerald-400"
                        }`}>
                          {ab.delta_lat_transfer_front_n > 0 ? "+" : ""}
                          {ab.delta_lat_transfer_front_n.toFixed(0)}
                          <span className="text-xs ml-0.5 text-zinc-300">N</span>
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-400">Rear Δ Load Transfer</span>
                        <span className={`text-[13px] font-bold font-mono ${
                          ab.delta_lat_transfer_rear_n > 0 ? "text-red-400" : "text-emerald-400"
                        }`}>
                          {ab.delta_lat_transfer_rear_n > 0 ? "+" : ""}
                          {ab.delta_lat_transfer_rear_n.toFixed(0)}
                          <span className="text-xs ml-0.5 text-zinc-300">N</span>
                        </span>
                      </div>
                    </div>
                    <div className={`text-xs font-medium px-2 py-1 rounded-lg text-center ${
                      ab.understeer_tendency === "more"
                        ? "bg-red-500/10 text-red-400 border border-red-500/20"
                        : ab.understeer_tendency === "less"
                          ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                          : "bg-gray-800/50 text-gray-400 border border-gray-700/30"
                    }`}>
                      {ab.understeer_tendency === "more"
                        ? "↑ More understeer"
                        : ab.understeer_tendency === "less"
                          ? "↓ Less understeer"
                          : "Balanced response"}
                    </div>
                    <div className="text-xs text-gray-400">
                      Stiffening front ARB by{" "}
                      <span className="text-gray-200">{(operatingPoint.delta_arb_front/1000).toFixed(1)} kN/m</span>
                    </div>
                  </>
                ) : (
                  <div className="text-xs text-gray-400">Fetching…</div>
                )}
              </Card>
            </div>

            {/* ARB load transfer bar chart */}
            <Card>
              <SectionTitle>
                Load Transfer Change — ARB +{(operatingPoint.delta_arb_front/1000).toFixed(1)} kN/m Front
              </SectionTitle>
              {arbChartData.length > 0 ? (
                <Plot
                  data={[
                    {
                      type: "bar",
                      x: ["Baseline front LT", `With +${(operatingPoint.delta_arb_front/1000).toFixed(0)}k ARB`],
                      y: [
                        ab ? (ab.baseline_arb_balance * 800 * operatingPoint.lateral_g * 9.81 * 0.30 / 1.55) : 0,
                        ab ? (ab.perturbed_arb_balance * 800 * operatingPoint.lateral_g * 9.81 * 0.30 / 1.55) : 0,
                      ],
                      marker: { color: ["#C8F04B", ab?.understeer_tendency === "more" ? "#ef4444" : "#22c55e"] },
                      text: [
                        ab ? `${(ab.baseline_arb_balance * 100).toFixed(1)}% front` : "",
                        ab ? `${(ab.perturbed_arb_balance * 100).toFixed(1)}% front` : "",
                      ],
                      textposition: "outside" as const,
                      textfont: { color: "#888", size: 10 },
                    },
                  ]}
                  layout={{
                    ...PLOTLY_BASE,
                    height: 200,
                    yaxis: { ...PLOTLY_BASE.yaxis, title: { text: "Front Lateral Load Transfer [N]", font: { size: 9, color: "#94A3B8" } } },
                  }}
                  config={{ displayModeBar: false }}
                  style={{ width: "100%", height: 200 }}
                />
              ) : (
                <div className="h-40 flex items-center justify-center text-xs text-zinc-300">Fetching…</div>
              )}
            </Card>

            {/* Ride height / aero sensitivity row */}
            <div className="grid grid-cols-2 gap-4">
              <Card>
                <SectionTitle>
                  Aero Δ — Ride Height {operatingPoint.delta_ride_height > 0 ? "−" : "+"}{Math.abs(operatingPoint.delta_ride_height)}mm
                </SectionTitle>
                {dfData.length > 0 ? (
                  <Plot
                    data={dfData}
                    layout={{
                      ...PLOTLY_BASE,
                      height: 200,
                      yaxis: { ...PLOTLY_BASE.yaxis, title: { text: "ΔDownforce [N]", font: { size: 9, color: "#94A3B8" } } },
                    }}
                    config={{ displayModeBar: false }}
                    style={{ width: "100%", height: 200 }}
                  />
                ) : (
                  <div className="h-40 flex items-center justify-center text-xs text-zinc-300">Fetching…</div>
                )}
              </Card>

              <Card>
                <SectionTitle>Setup Summary</SectionTitle>
                {si && ab && rh ? (
                  <div className="space-y-0">
                    <Badge label="Front spring rate"
                      value={(si.k_spring_front_nm / 1000).toFixed(1)} unit=" kN/m (N/mm)" />
                    <Badge label="Rear spring rate"
                      value={(si.k_spring_rear_nm / 1000).toFixed(1)} unit=" kN/m (N/mm)" />
                    <Badge label="Front ARB rate"
                      value={(si.k_arb_front_nm / 1000).toFixed(1)} unit=" kN/m (N/mm)" />
                    <Badge label="Rear ARB rate"
                      value={(si.k_arb_rear_nm / 1000).toFixed(1)} unit=" kN/m (N/mm)" />
                    <Badge label="ARB balance (front)"
                      value={(si.arb_balance_fraction * 100).toFixed(1)} unit="%"
                      ok={si.arb_balance_fraction >= 0.44 && si.arb_balance_fraction <= 0.54} />
                    <Badge label="Front ride height"
                      value={si.ride_height_front_mm.toFixed(0)} unit=" mm"
                      ok={si.ride_height_front_mm >= 15} />
                    <Badge label="Rear ride height"
                      value={si.ride_height_rear_mm.toFixed(0)} unit=" mm"
                      ok={si.ride_height_rear_mm >= 25} />
                    <Badge label={`Δ Downforce (±${operatingPoint.delta_ride_height}mm RH)`}
                      value={rh.delta_downforce_total_n > 0 ? "+" + rh.delta_downforce_total_n.toFixed(0) : rh.delta_downforce_total_n.toFixed(0)} unit=" N" />
                    <Badge label="Speed (operating point)"
                      value={result!.operating_point.speed_kmh.toFixed(0)} unit=" km/h" />
                    <Badge label="Dynamic pressure"
                      value={result!.operating_point.q_dynamic_pa.toFixed(0)} unit=" Pa" />
                  </div>
                ) : (
                  <div className="h-40 flex items-center justify-center text-xs text-zinc-300">Fetching…</div>
                )}
              </Card>
            </div>

            {/* Info note */}
            {rh?.note && (
              <Card className="border-blue-500/20 bg-blue-500/5">
                <div className="flex gap-2">
                  <Info size={12} className="text-blue-400 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-blue-300/70 leading-relaxed">{rh.note}</p>
                </div>
              </Card>
            )}
          </div>
        </div>
        )}
      </div>
    </div>
  );
}

export default function SetupSensitivityPage() {
  return (
    <PlanGate required="PRO" feature="Setup Sensitivity & ARB / Ride-Height Sweeps">
      <SetupSensitivityContent />
    </PlanGate>
  );
}

