"use client";

import React from "react";
import { AlertTriangle, AlertCircle, ShieldAlert } from "lucide-react";

interface ConstraintWarningProps {
  constraintName: string;
  currentValue: number | string;
  limitValue: number | string;
  unit?: string;
  severity?: "WARNING" | "CRITICAL";
  subsystem?: string;
  recommendation?: string;
  className?: string;
}

export default function ConstraintWarning({
  constraintName,
  currentValue,
  limitValue,
  unit = "",
  severity = "WARNING",
  subsystem,
  recommendation,
  className = "",
}: ConstraintWarningProps) {
  const isCritical = severity === "CRITICAL";

  return (
    <div
      className={`p-4 rounded-2xl border font-mono text-xs ${
        isCritical
          ? "bg-rose-950/25 border-rose-500/40 text-rose-300"
          : "bg-amber-950/25 border-amber-500/40 text-amber-300"
      } ${className}`}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          {isCritical ? (
            <AlertCircle size={16} className="text-rose-400 shrink-0" />
          ) : (
            <AlertTriangle size={16} className="text-amber-400 shrink-0" />
          )}
          <span className="font-bold text-white text-sm tracking-tight font-sans">
            {constraintName}
          </span>
        </div>
        <span
          className={`px-2 py-0.5 rounded text-xs font-bold uppercase border ${
            isCritical
              ? "bg-rose-950/60 border-rose-500/50 text-rose-300"
              : "bg-amber-950/60 border-amber-500/50 text-amber-300"
          }`}
        >
          {severity}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 my-2 p-2 rounded-xl bg-black/40 border border-white/5 text-xs">
        <div>
          <span className="text-gray-400">Observed Value:</span>{" "}
          <strong className="text-white font-bold">{currentValue} {unit}</strong>
        </div>
        <div>
          <span className="text-gray-400">Target Envelope Limit:</span>{" "}
          <strong className="text-white font-bold">{limitValue} {unit}</strong>
        </div>
      </div>

      {subsystem && (
        <div className="text-xs text-gray-400 mb-1">
          Affected Subsystem: <span className="text-gray-300">{subsystem}</span>
        </div>
      )}

      {recommendation && (
        <div className="text-xs text-gray-300 font-sans mt-2 pt-2 border-t border-white/10 leading-relaxed">
          <strong className="text-signal font-mono text-xs uppercase mr-1">Corrective Action:</strong>
          {recommendation}
        </div>
      )}
    </div>
  );
}
