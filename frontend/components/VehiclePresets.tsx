"use client";
import { useState } from "react";
import { Zap, ChevronRight } from "lucide-react";

export interface VehiclePreset {
  name: string;
  category: string;
  description: string;
  params: {
    m_s: number; m_u: number; k_s: number; c: number;
    k_t: number; MR: number; c_t: number;
  };
  road_profile: { profile_type: string; amplitude: number; frequency: number; duration: number };
}

export const VEHICLE_PRESETS: VehiclePreset[] = [
  {
    name: "Compact Hatchback",
    category: "Road Car",
    description: "Typical FWD city car. Comfort-biased, soft springs.",
    params: { m_s: 280, m_u: 32, k_s: 18000, c: 1500, k_t: 180000, MR: 0.90, c_t: 0 },
    road_profile: { profile_type: "random", amplitude: 0.03, frequency: 2, duration: 8 },
  },
  {
    name: "Sports Saloon",
    category: "Road Car",
    description: "Balanced handling and comfort — think BMW 3-Series.",
    params: { m_s: 320, m_u: 38, k_s: 28000, c: 2200, k_t: 200000, MR: 0.87, c_t: 0 },
    road_profile: { profile_type: "sine", amplitude: 0.04, frequency: 3, duration: 6 },
  },
  {
    name: "Track Day Car",
    category: "Performance",
    description: "High spring rates, heavy damping. Prioritises grip over comfort.",
    params: { m_s: 250, m_u: 30, k_s: 55000, c: 4500, k_t: 250000, MR: 0.80, c_t: 0 },
    road_profile: { profile_type: "sine", amplitude: 0.02, frequency: 5, duration: 5 },
  },
  {
    name: "Formula Student",
    category: "Racing",
    description: "Single-seater aero car. Very stiff, low travel.",
    params: { m_s: 120, m_u: 15, k_s: 90000, c: 3500, k_t: 300000, MR: 0.70, c_t: 0 },
    road_profile: { profile_type: "step", amplitude: 0.015, frequency: 2, duration: 4 },
  },
  {
    name: "Full-Size SUV",
    category: "Off-Road",
    description: "Heavy body-on-frame SUV. Very soft, high travel.",
    params: { m_s: 550, m_u: 65, k_s: 22000, c: 3800, k_t: 160000, MR: 0.95, c_t: 0 },
    road_profile: { profile_type: "pothole", amplitude: 0.08, frequency: 1, duration: 8 },
  },
  {
    name: "LMP Prototype",
    category: "Racing",
    description: "Le Mans Prototype. Extreme downforce dependency, tiny ride height.",
    params: { m_s: 190, m_u: 22, k_s: 150000, c: 8000, k_t: 350000, MR: 0.65, c_t: 0 },
    road_profile: { profile_type: "sine", amplitude: 0.008, frequency: 8, duration: 4 },
  },
  {
    name: "Motorcycle (Rear)",
    category: "Motorcycle",
    description: "Rear single-shock quarter-car equivalent. High MR due to linkage.",
    params: { m_s: 100, m_u: 10, k_s: 40000, c: 2800, k_t: 250000, MR: 0.60, c_t: 0 },
    road_profile: { profile_type: "sine", amplitude: 0.025, frequency: 4, duration: 5 },
  },
  {
    name: "ISO Comfort Test",
    category: "Standard",
    description: "ISO 2631-1 benchmark setup for repeatable comfort evaluation.",
    params: { m_s: 300, m_u: 35, k_s: 25000, c: 2050, k_t: 200000, MR: 0.85, c_t: 0 },
    road_profile: { profile_type: "random", amplitude: 0.05, frequency: 2, duration: 10 },
  },
];

const CATEGORY_COLOURS: Record<string, string> = {
  "Road Car":     "text-blue-400",
  "Performance":  "text-orange-400",
  "Racing":       "text-red-400",
  "Off-Road":     "text-green-400",
  "Motorcycle":   "text-purple-400",
  "Standard":     "text-gray-400",
};

interface VehiclePresetsProps {
  onSelect: (preset: VehiclePreset) => void;
}

export default function VehiclePresets({ onSelect }: VehiclePresetsProps) {
  const [open, setOpen] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);

  return (
    <div className="relative">
      <button onClick={() => setOpen(true)}
        className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-[#141416] border border-[#252525]
          hover:bg-[#1e1e20] hover:border-ansys-yellow/30 rounded-lg text-xs font-bold transition-all shadow-sm">
        <Zap size={14} className="text-ansys-yellow" /> Vehicle Library
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="w-full max-w-[360px] bg-[#0d0d0f] border border-[#252525] rounded-xl shadow-2xl overflow-hidden relative">
            <button 
              onClick={() => setOpen(false)}
              className="absolute top-3 right-3 text-gray-500 hover:text-white"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            </button>
            <div className="px-4 py-3 border-b border-[#1e1e1e]">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Zap size={14} className="text-ansys-yellow" />
                Vehicle Preset Library
              </h3>
              <p className="text-[11px] text-gray-500 mt-1">Select a configuration to load parameters. Then run the solver.</p>
            </div>
            <div className="max-h-[500px] overflow-y-auto custom-scrollbar py-1">
              {VEHICLE_PRESETS.map((preset) => (
                <button key={preset.name}
                  onClick={() => { onSelect(preset); setOpen(false); }}
                  onMouseEnter={() => setHovered(preset.name)}
                  onMouseLeave={() => setHovered(null)}
                  className={`w-full flex items-center justify-between px-4 py-3 border-b border-[#1a1a1a] last:border-0 transition-colors ${
                    hovered === preset.name ? "bg-[#161618]" : ""
                  }`}
                >
                  <div className="text-left min-w-0 pr-4">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-bold text-white">{preset.name}</span>
                      <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-sm bg-[#111] ${CATEGORY_COLOURS[preset.category] ?? "text-gray-500"}`}>
                        {preset.category}
                      </span>
                    </div>
                    <p className="text-[11px] text-gray-500 leading-snug">{preset.description}</p>
                  </div>
                  <ChevronRight size={14} className="text-gray-700 shrink-0" />
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
