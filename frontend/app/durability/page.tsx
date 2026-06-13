"use client";
import { useState } from "react";
import {
  Shield, AlertTriangle, CheckCircle, TrendingDown, Loader2,
  Car, Gauge, Thermometer, Wrench, BarChart2, ChevronDown
} from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ROAD_CLASSES = [
  { value: "A", label: "A — Perfect Highway",    color: "#22c55e", desc: "Motorway, brand-new asphalt" },
  { value: "B", label: "B — Good Highway",       color: "#84cc16", desc: "Well-maintained national road" },
  { value: "C", label: "C — Average Road",       color: "#eab308", desc: "Typical city road, some potholes" },
  { value: "D", label: "D — Poor Road",          color: "#f97316", desc: "Old urban road, frequent defects" },
  { value: "E", label: "E — Very Poor Road",     color: "#ef4444", desc: "Unmaintained rural track" },
  { value: "F", label: "F — Off-Road Track",     color: "#dc2626", desc: "Gravel/dirt track" },
  { value: "G", label: "G — Rough Off-Road",     color: "#991b1b", desc: "Rocky terrain, heavy off-road" },
  { value: "H", label: "H — Extreme Terrain",    color: "#7f1d1d", desc: "Extreme conditions" },
];

interface ComponentLife {
  name: string;
  display_name: string;
  life_km: number;
  life_label: string;
  condition: string;
  condition_color: string;
}

interface DurabilityResult {
  road_class: string;
  road_label: string;
  speed_kph: number;
  rms_body_accel: number;
  rms_body_accel_wk: number;
  vdv: number;
  peak_susp_travel_mm: number;
  rms_susp_travel_mm: number;
  rms_tire_load_n: number;
  durability_score: number;
  comfort_rating: string;
  iso_2631_class: string;
  components: ComponentLife[];
  summary: string;
  worst_component: string;
  best_range_km: number;
}

const COMPONENT_ICONS: Record<string, typeof Wrench> = {
  shock_absorber: Wrench,
  coil_spring: BarChart2,
  bushings: Thermometer,
  wheel_bearing: Gauge,
};

function ScoreGauge({ score }: { score: number }) {
  const color = score >= 70 ? "#22c55e" : score >= 40 ? "#eab308" : "#ef4444";
  const strokeDashoffset = 440 - (440 * score) / 100;
  return (
    <div className="relative flex items-center justify-center w-36 h-36">
      <svg className="absolute inset-0 -rotate-90" width="144" height="144" viewBox="0 0 144 144">
        <circle cx="72" cy="72" r="62" fill="none" stroke="#1a1a1a" strokeWidth="10" />
        <circle
          cx="72" cy="72" r="62" fill="none"
          stroke={color} strokeWidth="10" strokeLinecap="round"
          strokeDasharray="440" strokeDashoffset={strokeDashoffset}
          style={{ transition: "stroke-dashoffset 1s ease, stroke 0.5s ease" }}
        />
      </svg>
      <div className="text-center z-10">
        <div className="text-3xl font-black" style={{ color }}>{score}</div>
        <div className="text-[10px] text-gray-600 font-medium">/ 100</div>
      </div>
    </div>
  );
}

export default function DurabilityPage() {
  const { token } = useAuth();
  const [roadClass, setRoadClass] = useState("C");
  const [speed, setSpeed] = useState(80);
  const [params, setParams] = useState({
    m_s: 300, m_u: 35, k_s: 25000, c: 2050, k_t: 200000, MR: 0.85
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DurabilityResult | null>(null);
  const [error, setError] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const selectedRoad = ROAD_CLASSES.find(r => r.value === roadClass)!;

  const handleAnalyze = async () => {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const resp = await fetch(`${API_BASE}/simulate/durability`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ road_class: roadClass, speed_kph: speed, ...params }),
      });
      if (!resp.ok) {
        const d = await resp.json().catch(() => ({}));
        throw new Error(d.detail || "Analysis failed");
      }
      setResult(await resp.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-full bg-black text-white">
      {/* Header */}
      <div className="border-b border-[#1a1a1a] px-8 py-6">
        <div className="max-w-5xl mx-auto flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-orange-500 to-red-500 flex items-center justify-center shadow-lg shadow-orange-500/20">
            <Shield size={18} className="text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">Road Durability Analyzer</h1>
            <p className="text-xs text-gray-500">ISO 8608 road profiles · Fatigue life prediction · ISO 2631-1 comfort rating</p>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-8 py-8 space-y-6">
        {/* Road Class Selector */}
        <div className="rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-6 space-y-4">
          <h2 className="text-sm font-semibold text-gray-300">Select Road Class (ISO 8608)</h2>
          <div className="grid grid-cols-4 gap-2">
            {ROAD_CLASSES.map(r => (
              <button
                key={r.value}
                onClick={() => setRoadClass(r.value)}
                className={`relative p-3 rounded-xl border text-left transition-all ${
                  roadClass === r.value
                    ? "border-[color:var(--rc)] bg-[color:var(--rc)]/10"
                    : "border-[#222] hover:border-[#333]"
                }`}
                style={{ "--rc": r.color } as React.CSSProperties}
              >
                <div className="font-bold text-sm" style={{ color: r.color }}>{r.value}</div>
                <div className="text-[10px] text-gray-500 mt-0.5 leading-tight">{r.desc}</div>
                {roadClass === r.value && (
                  <div className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full" style={{ backgroundColor: r.color }} />
                )}
              </button>
            ))}
          </div>

          {/* Speed slider */}
          <div className="space-y-2 pt-2">
            <div className="flex justify-between text-xs">
              <span className="text-gray-400">Vehicle Speed</span>
              <span className="text-white font-bold">{speed} km/h</span>
            </div>
            <input
              type="range" min={10} max={200} step={5} value={speed}
              onChange={e => setSpeed(Number(e.target.value))}
              className="w-full h-1.5 rounded-full appearance-none bg-[#222] accent-orange-500 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-gray-700">
              <span>10 km/h</span><span>200 km/h</span>
            </div>
          </div>
        </div>

        {/* Advanced Params */}
        <div className="rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] overflow-hidden">
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="w-full flex items-center justify-between px-6 py-4 hover:bg-[#0d0d0d] transition-colors"
          >
            <span className="text-sm font-medium text-gray-400">Vehicle Parameters (Optional)</span>
            <ChevronDown size={14} className={`text-gray-600 transition-transform ${showAdvanced ? "rotate-180" : ""}`} />
          </button>
          {showAdvanced && (
            <div className="px-6 pb-6 grid grid-cols-3 gap-4 border-t border-[#111]">
              {[
                { key: "m_s", label: "Sprung Mass", unit: "kg" },
                { key: "m_u", label: "Unsprung Mass", unit: "kg" },
                { key: "k_s", label: "Spring Rate", unit: "N/m" },
                { key: "c", label: "Damping", unit: "Ns/m" },
                { key: "k_t", label: "Tire Stiffness", unit: "N/m" },
                { key: "MR", label: "Motion Ratio", unit: "" },
              ].map(({ key, label, unit }) => (
                <div key={key} className="space-y-1.5 pt-4">
                  <label className="text-xs text-gray-500">{label} {unit && <span className="text-gray-700">[{unit}]</span>}</label>
                  <input
                    type="number"
                    value={params[key as keyof typeof params]}
                    onChange={e => setParams(p => ({ ...p, [key]: parseFloat(e.target.value) || 0 }))}
                    className="w-full bg-[#111] border border-[#222] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-orange-500/50 transition-colors"
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Analyze Button */}
        <button
          onClick={handleAnalyze}
          disabled={loading}
          className="w-full py-3.5 rounded-xl bg-gradient-to-r from-orange-600 to-red-600 text-white font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50 hover:brightness-110 transition-all shadow-lg shadow-orange-500/20"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Car size={16} />}
          {loading ? "Running Durability Analysis..." : `Analyze on ${selectedRoad.label}`}
        </button>

        {error && (
          <div className="flex items-center gap-3 p-4 rounded-xl border border-red-500/20 bg-red-500/5">
            <AlertTriangle size={16} className="text-red-400 shrink-0" />
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="space-y-5 animate-in fade-in duration-500">
            {/* Score + top metrics */}
            <div className="grid grid-cols-3 gap-4">
              {/* Durability Score */}
              <div className="col-span-1 rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-6 flex flex-col items-center justify-center gap-2">
                <ScoreGauge score={result.durability_score} />
                <p className="text-xs text-gray-500 text-center">Durability Score</p>
              </div>

              {/* Key metrics */}
              <div className="col-span-2 rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-6 grid grid-cols-2 gap-4">
                {[
                  { label: "Comfort Rating", value: result.comfort_rating, sub: result.iso_2631_class },
                  { label: "Body Accel (Wk-weighted)", value: `${result.rms_body_accel_wk.toFixed(3)} m/s²`, sub: "ISO 2631-1" },
                  { label: "Vibration Dose Value", value: `${result.vdv.toFixed(3)} m/s¹·⁷⁵`, sub: "VDV" },
                  { label: "Best Component Life", value: result.best_range_km >= 1000 ? `${(result.best_range_km/1000).toFixed(0)}k km` : `${result.best_range_km} km`, sub: result.worst_component },
                ].map(({ label, value, sub }) => (
                  <div key={label} className="space-y-1">
                    <p className="text-[10px] text-gray-600 uppercase tracking-wider">{label}</p>
                    <p className="text-base font-bold text-white">{value}</p>
                    <p className="text-[10px] text-gray-600">{sub}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Component Life Table */}
            <div className="rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-6 space-y-4">
              <h3 className="text-sm font-semibold text-gray-300">Component Life Predictions</h3>
              <div className="space-y-3">
                {result.components.map(comp => {
                  const Icon = COMPONENT_ICONS[comp.name] || Wrench;
                  const barPct = Math.min(100, (comp.life_km / 200000) * 100);
                  return (
                    <div key={comp.name} className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Icon size={13} className="text-gray-600" />
                          <span className="text-sm text-gray-300">{comp.display_name}</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-sm font-bold text-white">{comp.life_label}</span>
                          <span className="text-xs font-medium px-2 py-0.5 rounded-full" style={{ color: comp.condition_color, backgroundColor: comp.condition_color + "15" }}>
                            {comp.condition}
                          </span>
                        </div>
                      </div>
                      <div className="h-1.5 rounded-full bg-[#1a1a1a] overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-1000"
                          style={{ width: `${barPct}%`, backgroundColor: comp.condition_color }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Summary */}
            <div className="rounded-2xl border border-orange-500/20 bg-orange-500/5 p-5 flex gap-3">
              <CheckCircle size={16} className="text-orange-400 mt-0.5 shrink-0" />
              <p className="text-sm text-gray-200 leading-relaxed">{result.summary}</p>
            </div>

            {/* Physics metrics */}
            <div className="rounded-2xl border border-[#1a1a1a] bg-[#0a0a0a] p-5 grid grid-cols-3 gap-4">
              {[
                { label: "RMS Body Accel", value: `${result.rms_body_accel.toFixed(4)} m/s²` },
                { label: "RMS Susp Travel", value: `${result.rms_susp_travel_mm.toFixed(2)} mm` },
                { label: "Peak Susp Travel", value: `${result.peak_susp_travel_mm.toFixed(2)} mm` },
                { label: "RMS Tire Load", value: `${result.rms_tire_load_n.toFixed(1)} N` },
                { label: "Road Class", value: `ISO 8608 Class ${result.road_class}` },
                { label: "Speed", value: `${result.speed_kph} km/h` },
              ].map(({ label, value }) => (
                <div key={label} className="space-y-0.5">
                  <p className="text-[10px] text-gray-600">{label}</p>
                  <p className="text-sm font-semibold text-white">{value}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
