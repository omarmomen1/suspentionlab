"use client";
import { useState, Suspense } from "react";
import dynamic from "next/dynamic";
import { Settings2, Activity, Play, Wrench, BarChart2 } from "lucide-react";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const DARK_BASE = {
  paper_bgcolor: "transparent",
  plot_bgcolor:  "transparent",
  font:          { color: "#666", size: 11, family: "Inter, monospace" },
  xaxis:         { color: "#444", gridcolor: "#161618", zerolinecolor: "#2a2a2a", tickfont: { color: "#555", size: 10 } },
  yaxis:         { color: "#444", gridcolor: "#161618", zerolinecolor: "#2a2a2a", tickfont: { color: "#555", size: 10 } },
  legend:        { font: { color: "#777", size: 10 }, bgcolor: "rgba(0,0,0,0)", orientation: "h" as const, y: -0.15 },
  margin:        { l: 58, r: 18, t: 32, b: 55 },
  autosize:      true,
  hoverlabel:    { bgcolor: "#0d0d0f", bordercolor: "#333", font: { color: "#ccc", size: 11 } },
};

function darkLayout(overrides: Record<string, unknown> = {}) {
  return { ...DARK_BASE, ...overrides };
}

function intersectLines(p1: [number, number], p2: [number, number], p3: [number, number], p4: [number, number]) {
  const [x1, y1] = p1; const [x2, y2] = p2;
  const [x3, y3] = p3; const [x4, y4] = p4;
  const denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4);
  if (Math.abs(denom) < 1e-6) return null;
  const px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom;
  const py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom;
  return [px, py];
}

type Status = "good" | "warn" | "bad" | "neutral";

function KPICard({ label, value, unit, sub, status = "neutral" }: { label: string; value: number | string; unit?: string; sub?: string; status?: Status; }) {
  const colours: Record<Status, string> = { good: "text-emerald-400", warn: "text-amber-400", bad: "text-red-400", neutral: "text-white" };
  const borders: Record<Status, string> = { good: "border-emerald-900/40 bg-emerald-950/10", warn: "border-amber-900/40 bg-amber-950/10", bad: "border-red-900/40 bg-red-950/10", neutral: "border-[#252525]" };
  return (
    <div className={`bg-[#141416] border ${borders[status]} rounded-xl p-3 flex flex-col gap-0.5`}>
      <span className="text-[9px] font-bold tracking-[0.16em] text-gray-600 uppercase">{label}</span>
      <span className={`text-[1.1rem] font-bold font-mono leading-tight ${colours[status]}`}>
        {typeof value === "number" ? value.toFixed(1) : value}
        {unit && <span className="text-[11px] font-normal text-gray-600 ml-1">{unit}</span>}
      </span>
      {sub && <span className="text-[9px] text-gray-700 leading-tight mt-0.5">{sub}</span>}
    </div>
  );
}

function ParamSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h3 className="text-[9px] font-bold text-gray-700 uppercase tracking-[0.16em] pb-1.5 border-b border-[#1e1e1e]">
        {title}
      </h3>
      {children}
    </div>
  );
}

function ParameterInput({ label, val, unit, step = 1, min, onChange }: { label: string; val: number; unit: string; step?: number; min?: number; onChange: (v: number) => void; }) {
  return (
    <div className="flex justify-between items-center gap-2">
      <label className="text-[11px] text-gray-500 flex-1 min-w-0 leading-tight">{label}</label>
      <div className="relative shrink-0">
        <input type="number" step={step} value={val} min={min} onChange={(e) => onChange(Number(e.target.value))}
          className="bg-[#0d0d0d] border border-[#252525] text-[11px] rounded-lg px-2 py-1.5 text-white w-28 text-right pr-9 focus:outline-none focus:border-ansys-yellow/60 focus:ring-1 focus:ring-ansys-yellow/15 transition-all"
        />
        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[9px] text-gray-700 pointer-events-none">{unit}</span>
      </div>
    </div>
  );
}

function PlotBox({ children }: { children: React.ReactNode }) {
  return <div className="flex-1 min-w-0 min-h-0 relative">{children}</div>;
}

function KinematicsDashboard() {
  const [params, setParams] = useState({
    lca_in_y: 300.0, lca_in_z: 200.0,
    lca_out_y: 700.0, lca_out_z: 180.0,
    uca_in_y: 350.0, uca_in_z: 450.0,
    uca_out_y: 680.0, uca_out_z: 480.0,
    tire_radius: 320.0,
    bump_travel: 0.0
  });

  const LCA_in: [number, number] = [params.lca_in_y, params.lca_in_z];
  const LCA_out: [number, number] = [params.lca_out_y, params.lca_out_z + params.bump_travel];
  const UCA_in: [number, number] = [params.uca_in_y, params.uca_in_z];
  const UCA_out: [number, number] = [params.uca_out_y, params.uca_out_z + params.bump_travel];

  const IC = intersectLines(LCA_in, LCA_out, UCA_in, UCA_out);
  const CP: [number, number] = [params.lca_out_y + 50, 0];
  const RC = IC ? intersectLines(IC as [number, number], CP, [0, -1000], [0, 1000]) : null;

  const rc_z = RC ? RC[1] : 0;
  const ic_dist = IC ? Math.sqrt(Math.pow(IC[0] - params.lca_out_y, 2) + Math.pow(IC[1] - params.lca_out_z, 2)) : 0;
  const camber_gain = IC ? -1 * (1 / ic_dist) * (180 / Math.PI) * 1000 : 0;

  const traces: any[] = [
    { x: [0, 0], y: [-100, 800], mode: "lines", line: { color: "rgba(255,255,255,0.1)", dash: "dash", width: 1 }, showlegend: false },
    { x: [-200, 1500], y: [0, 0], mode: "lines", line: { color: "#333", width: 2 }, name: "Ground Point" },
    { x: [LCA_in[0], LCA_out[0]], y: [LCA_in[1], LCA_out[1]], mode: "lines+markers", line: { color: "#00aeff", width: 2.5 }, marker: { size: 6, color: "#fff" }, name: "Lower Wishbone" },
    { x: [UCA_in[0], UCA_out[0]], y: [UCA_in[1], UCA_out[1]], mode: "lines+markers", line: { color: "#00aeff", width: 2.5 }, marker: { size: 6, color: "#fff" }, name: "Upper Wishbone" },
    { x: [LCA_out[0], UCA_out[0]], y: [LCA_out[1], UCA_out[1]], mode: "lines+markers", line: { color: "#f2a900", width: 3 }, marker: { size: 5, color: "#fff" }, name: "Knuckle / Upright" }
  ];

  const theta = Array.from({ length: 50 }, (_, i) => (i * 2 * Math.PI) / 49);
  const tire_y = theta.map(th => params.lca_out_y + 50 + params.tire_radius * Math.cos(th));
  const tire_z = theta.map(th => params.tire_radius + params.bump_travel + params.tire_radius * Math.sin(th));
  traces.push({
    x: tire_y, y: tire_z, mode: "lines", line: { color: "rgba(255,255,255,0.3)", width: 1.5 }, name: "Tire Patch", fill: "toself", fillcolor: "rgba(255,255,255,0.03)"
  });

  if (IC && Math.abs(IC[0]) < 5000) {
    traces.push(
      { x: [IC[0], LCA_out[0]], y: [IC[1], LCA_out[1]], mode: "lines", line: { color: "rgba(0,174,255,0.2)", dash: "dot", width: 1 }, showlegend: false },
      { x: [IC[0], UCA_out[0]], y: [IC[1], UCA_out[1]], mode: "lines", line: { color: "rgba(0,174,255,0.2)", dash: "dot", width: 1 }, showlegend: false },
      { x: [IC[0]], y: [IC[1]], mode: "markers", marker: { color: "#ff2d55", size: 6, symbol: "x" }, name: "Instant Center (IC)" }
    );
    if (RC) {
      traces.push(
        { x: [IC[0], CP[0]], y: [IC[1], CP[1]], mode: "lines", line: { color: "rgba(242,169,0,0.3)", dash: "dash", width: 1 }, name: "Force Line" },
        { x: [0], y: [rc_z], mode: "markers", marker: { color: "#00ff87", size: 8, symbol: "diamond" }, name: "Roll Center (RC)" }
      );
    }
  }

  return (
    <div className="h-full flex flex-col p-5 pt-3 gap-3 min-h-0">
      <div className="flex items-center justify-between shrink-0 pb-3 border-b border-[#1e1e1e]">
        <div className="flex flex-col">
          <span className="text-[9px] font-bold tracking-[0.25em] text-ansys-yellow uppercase">Double Wishbone Front-View</span>
          <h1 className="text-2xl font-semibold tracking-tight text-white leading-tight">Kinematics Analyzer</h1>
        </div>
      </div>

      <div className="flex flex-1 gap-4 overflow-hidden min-h-0">
        <div className="w-60 shrink-0 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-y-auto custom-scrollbar">
          <div className="px-4 py-3 border-b border-[#1e1e1e] sticky top-0 bg-[#0d0d0f] z-10"><h2 className="text-xs font-semibold text-gray-300 flex items-center gap-2"><Settings2 size={13} className="text-ansys-yellow" /> Hardpoints</h2></div>
          <div className="p-4 space-y-5">
            <ParamSection title="Lower Wishbone">
              <ParameterInput label="Inner Y" val={params.lca_in_y} unit="mm" onChange={(v) => setParams({ ...params, lca_in_y: v })} />
              <ParameterInput label="Inner Z" val={params.lca_in_z} unit="mm" onChange={(v) => setParams({ ...params, lca_in_z: v })} />
              <ParameterInput label="Outer Y" val={params.lca_out_y} unit="mm" onChange={(v) => setParams({ ...params, lca_out_y: v })} />
              <ParameterInput label="Outer Z" val={params.lca_out_z} unit="mm" onChange={(v) => setParams({ ...params, lca_out_z: v })} />
            </ParamSection>
            <ParamSection title="Upper Wishbone">
              <ParameterInput label="Inner Y" val={params.uca_in_y} unit="mm" onChange={(v) => setParams({ ...params, uca_in_y: v })} />
              <ParameterInput label="Inner Z" val={params.uca_in_z} unit="mm" onChange={(v) => setParams({ ...params, uca_in_z: v })} />
              <ParameterInput label="Outer Y" val={params.uca_out_y} unit="mm" onChange={(v) => setParams({ ...params, uca_out_y: v })} />
              <ParameterInput label="Outer Z" val={params.uca_out_z} unit="mm" onChange={(v) => setParams({ ...params, uca_out_z: v })} />
            </ParamSection>
            <ParamSection title="Travel & Wheel">
              <ParameterInput label="Loaded Radius" val={params.tire_radius} unit="mm" onChange={(v) => setParams({ ...params, tire_radius: v })} />
              <div className="pt-2 border-t border-[#1e1e1e]">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-[11px] text-gray-500">Bump Travel</span>
                  <span className="text-[11px] font-mono text-ansys-yellow bg-ansys-yellow/10 px-1.5 py-0.5 rounded">{params.bump_travel > 0 ? "+" : ""}{params.bump_travel} mm</span>
                </div>
                <input type="range" min="-80" max="80" step="1" value={params.bump_travel} onChange={(e) => setParams({ ...params, bump_travel: Number(e.target.value) })} className="w-full accent-ansys-yellow" />
              </div>
            </ParamSection>
          </div>
        </div>

        <div className="flex-1 flex flex-col gap-3 min-w-0 overflow-hidden">
          <div className="grid grid-cols-4 gap-2 shrink-0">
            <KPICard label="Roll Center Z" value={rc_z} unit="mm" status="neutral" />
            <KPICard label="IC Swing Arm Length" value={ic_dist} unit="mm" status="neutral" />
            <KPICard label="Camber Gain" value={camber_gain} unit="deg/m" status="neutral" />
          </div>

          <div className="flex gap-1.5 shrink-0">
            <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-ansys-yellow text-black shadow-[0_0_12px_rgba(242,169,0,0.2)]">
              <Wrench size={12} /> Front-View Geometry (FVSA)
            </button>
          </div>

          <div className="flex-1 bg-[#111113] border border-[#1e1e1e] rounded-xl overflow-hidden min-h-0">
            <div className="grid grid-cols-1 grid-rows-1 h-full gap-px bg-[#181818]">
              <PlotBox>
                <Plot
                  data={traces}
                  layout={darkLayout({
                    title: { text: "Roll Center & Instant Center Synthesis", font: { color: "#888", size: 11 } },
                    xaxis: { ...DARK_BASE.xaxis, title: { text: "Lateral Y (mm)", font: { color: "#444", size: 10 } }, scaleanchor: "y", scaleratio: 1 },
                    yaxis: { ...DARK_BASE.yaxis, title: { text: "Vertical Z (mm)", font: { color: "#444", size: 10 } } }
                  })}
                  useResizeHandler style={{ width: "100%", height: "100%" }} config={{ responsive: true, displayModeBar: false }}
                />
              </PlotBox>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div className="h-full flex items-center justify-center text-gray-600 text-sm">Loading environment…</div>}>
      <KinematicsDashboard />
    </Suspense>
  );
}
