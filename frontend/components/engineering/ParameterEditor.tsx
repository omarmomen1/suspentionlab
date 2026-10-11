"use client";

import React from "react";
import { Sliders, AlertTriangle } from "lucide-react";

interface ParameterEditorProps {
  label: string;
  unit: string;
  value: number;
  baselineValue: number;
  min: number;
  max: number;
  step?: number;
  onChange: (newVal: number) => void;
  className?: string;
}

export default function ParameterEditor({
  label,
  unit,
  value,
  baselineValue,
  min,
  max,
  step = 1,
  onChange,
  className = "",
}: ParameterEditorProps) {
  const delta = value - baselineValue;
  const deltaPct = baselineValue !== 0 ? (delta / baselineValue) * 100 : 0;
  const isOutOfLimits = value < min || value > max;

  return (
    <div className={`p-4 rounded-2xl bg-[#111116] border ${isOutOfLimits ? "border-rose-500/40" : "border-white/[0.08]"} font-mono text-xs flex flex-col justify-between ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="font-bold text-gray-300 flex items-center gap-1.5 font-sans">
          <Sliders size={13} className="text-ansys-yellow shrink-0" />
          {label}
        </span>
        <div className="flex items-center gap-1 font-bold">
          <span className="text-white text-sm">{value}</span>
          <span className="text-gray-500 font-normal">{unit}</span>
        </div>
      </div>

      {/* Slider Input */}
      <div className="my-2">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full h-1.5 bg-white/10 rounded-lg appearance-none cursor-pointer accent-ansys-yellow"
        />
        <div className="flex items-center justify-between text-[10px] text-gray-500 mt-1">
          <span>{min} {unit}</span>
          <span>Baseline: {baselineValue} {unit}</span>
          <span>{max} {unit}</span>
        </div>
      </div>

      {/* Delta Row */}
      <div className="flex items-center justify-between pt-2 border-t border-white/[0.06] text-[11px]">
        <span className="text-gray-500">Delta vs Baseline:</span>
        <div className="flex items-center gap-1 font-bold">
          <span
            className={
              delta === 0
                ? "text-gray-400"
                : delta > 0
                ? "text-cyan-400"
                : "text-purple-400"
            }
          >
            {delta > 0 ? `+${delta}` : delta} {unit} ({deltaPct > 0 ? `+${deltaPct.toFixed(1)}` : deltaPct.toFixed(1)}%)
          </span>
        </div>
      </div>

      {isOutOfLimits && (
        <div className="mt-2 text-[10px] text-rose-400 flex items-center gap-1">
          <AlertTriangle size={11} /> Value exceeds physically calibrated domain!
        </div>
      )}
    </div>
  );
}
