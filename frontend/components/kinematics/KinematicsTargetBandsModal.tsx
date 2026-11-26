"use client";

import React, { useState } from "react";
import { Sliders, RotateCcw, Check, X, ShieldAlert } from "lucide-react";

export interface TargetBandConfig {
  key: string;
  label: string;
  unit: string;
  min: number;
  max: number;
  step: number;
  description: string;
}

import { GT3_MOTION_RATIO_BAND } from "../../lib/v2/instruments";

export const DEFAULT_TARGET_BANDS: Record<string, [number, number]> = {
  camber_gain_deg_per_100mm: [-1.2, -0.4],
  toe_gain_deg_per_100mm: [-0.15, 0.15],
  roll_center_height_mm: [30.0, 110.0],
  motion_ratio: [...GT3_MOTION_RATIO_BAND],
  scrub_radius_mm: [10.0, 45.0],
};

const BAND_DEFINITIONS: TargetBandConfig[] = [
  {
    key: "camber_gain_deg_per_100mm",
    label: "Camber Gain Rate",
    unit: "°/100mm",
    min: -3.0,
    max: 1.0,
    step: 0.05,
    description: "Rate of dynamic camber angle change per 100mm of wheel travel in bump.",
  },
  {
    key: "toe_gain_deg_per_100mm",
    label: "Bump Steer (Toe Gain)",
    unit: "°/100mm",
    min: -1.0,
    max: 1.0,
    step: 0.02,
    description: "Steering angle variation per 100mm of wheel travel (near-zero preferred).",
  },
  {
    key: "roll_center_height_mm",
    label: "Roll Center Height",
    unit: "mm",
    min: -50.0,
    max: 200.0,
    step: 5.0,
    description: "Static and dynamic kinematic roll center height above ground plane.",
  },
  {
    key: "motion_ratio",
    label: "Damper Motion Ratio",
    unit: "mm/mm",
    min: 0.3,
    max: 1.2,
    step: 0.02,
    description: "Ratio of spring/damper deflection to wheel vertical travel.",
  },
  {
    key: "scrub_radius_mm",
    label: "Scrub Radius",
    unit: "mm",
    min: -50.0,
    max: 100.0,
    step: 2.0,
    description: "Distance from contact patch center to kingpin axis ground intersection.",
  },
];

interface KinematicsTargetBandsModalProps {
  isOpen: boolean;
  onClose: () => void;
  bands: Record<string, [number, number]>;
  onSaveBands: (bands: Record<string, [number, number]>) => void;
}

export default function KinematicsTargetBandsModal({
  isOpen,
  onClose,
  bands,
  onSaveBands,
}: KinematicsTargetBandsModalProps) {
  const [currentBands, setCurrentBands] = useState<Record<string, [number, number]>>({
    ...DEFAULT_TARGET_BANDS,
    ...bands,
  });

  if (!isOpen) return null;

  const handleChange = (key: string, idx: 0 | 1, value: number) => {
    setCurrentBands((prev) => {
      const current = prev[key] || DEFAULT_TARGET_BANDS[key] || [0, 0];
      const updated: [number, number] = [...current];
      updated[idx] = value;
      return { ...prev, [key]: updated };
    });
  };

  const handleReset = () => {
    setCurrentBands({ ...DEFAULT_TARGET_BANDS });
  };

  const handleSave = () => {
    onSaveBands(currentBands);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
      <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-xl w-full p-6 shadow-2xl flex flex-col gap-5 text-slate-200">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2 text-indigo-400 font-semibold text-base">
            <Sliders className="w-5 h-5" />
            <span>Kinematic Target Bands Configuration</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className="text-xs text-slate-400">
          Define acceptable design corridors. When kinematics curves or derivative rates migrate
          outside these target bounds, the workspace highlights them as out-of-band warnings.
        </p>

        <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
          {BAND_DEFINITIONS.map((def) => {
            const pair = currentBands[def.key] || DEFAULT_TARGET_BANDS[def.key] || [def.min, def.max];
            return (
              <div
                key={def.key}
                className="p-3.5 bg-slate-800/60 rounded-lg border border-slate-700/60 flex flex-col gap-2"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-200">
                    {def.label} <span className="text-slate-400 font-normal font-mono">({def.unit})</span>
                  </span>
                  <span className="text-[11px] font-mono text-indigo-300 font-medium">
                    Target: [{pair[0].toFixed(2)}, {pair[1].toFixed(2)}] {def.unit}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400">{def.description}</div>
                <div className="grid grid-cols-2 gap-3 pt-1">
                  <div>
                    <label className="text-[10px] text-slate-400 block mb-1">Lower Limit ({def.unit})</label>
                    <input
                      type="number"
                      step={def.step}
                      value={pair[0]}
                      onChange={(e) => handleChange(def.key, 0, parseFloat(e.target.value) || 0)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 font-mono"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-400 block mb-1">Upper Limit ({def.unit})</label>
                    <input
                      type="number"
                      step={def.step}
                      value={pair[1]}
                      onChange={(e) => handleChange(def.key, 1, parseFloat(e.target.value) || 0)}
                      className="w-full bg-slate-900 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 font-mono"
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex items-center justify-between pt-3 border-t border-slate-800">
          <button
            onClick={handleReset}
            className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 transition px-2 py-1 rounded hover:bg-slate-800"
          >
            <RotateCcw className="w-3.5 h-3.5" /> Reset to Defaults
          </button>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 rounded-lg transition"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              className="px-4 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg shadow transition flex items-center gap-1.5"
            >
              <Check className="w-3.5 h-3.5" /> Apply Bands
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
