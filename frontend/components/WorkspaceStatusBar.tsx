"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useWorkspace } from "../contexts/WorkspaceContext";
import { useAuth } from "../contexts/AuthContext";
import {
  Wrench,
  Car,
  Layers,
  ShieldCheck,
  Flag,
  RotateCcw,
  ChevronDown,
  SlidersHorizontal,
  ExternalLink,
  Sparkles,
} from "lucide-react";

export default function WorkspaceStatusBar() {
  const {
    mode,
    setMode,
    vehicle,
    setup,
    track,
    tire,
    simulation,
    validation,
    telemetry,
    sessionName,
    modelVersion,
    resetToDefaults,
  } = useWorkspace();

  const { user } = useAuth();
  const [isExpanded, setIsExpanded] = useState(false);

  const getValidationBadge = (status: string) => {
    switch (status) {
      case "VALIDATED":
        return "bg-emerald-950/60 border-emerald-500/40 text-emerald-400";
      case "CONDITIONAL":
        return "bg-amber-950/60 border-amber-500/40 text-amber-400";
      case "EXPERIMENTAL":
        return "bg-purple-950/60 border-purple-500/40 text-purple-400";
      case "OUT-OF-DOMAIN":
      default:
        return "bg-rose-950/60 border-rose-500/40 text-rose-400";
    }
  };

  return (
    <div id="workspace-status-bar" className="w-full bg-[#09090c] border-b border-white/[0.08] select-none z-30 shrink-0">
      {/* ── Sleek Collapsed Ribbon (Default State - Zero Horizontal Scrollbar) ── */}
      <div className="h-[34px] px-4 sm:px-6 flex items-center justify-between gap-3 text-[11px] font-mono">
        
        {/* Left: Essential Context Summary */}
        <div className="flex items-center gap-2.5 min-w-0 overflow-hidden">
          {/* Workspace Mode Badge */}
          <button
            type="button"
            onClick={() => setMode(mode === "PRODUCTION" ? "DEMO" : "PRODUCTION")}
            title="Click to toggle Workspace Mode"
            className={`px-2 py-0.5 rounded border font-bold text-[10px] tracking-wider transition-all flex items-center gap-1.5 shrink-0 ${
              mode === "PRODUCTION"
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20"
                : "bg-amber-500/10 border-amber-500/30 text-amber-400 hover:bg-amber-500/20"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                mode === "PRODUCTION" ? "bg-emerald-400 animate-pulse" : "bg-amber-400"
              }`}
            />
            {mode}
          </button>

          <span className="text-white/20 shrink-0">|</span>

          {/* Active Vehicle */}
          <div className="flex items-center gap-1.5 text-gray-300 min-w-0" title={`Active Vehicle: ${vehicle.name} (${vehicle.version})`}>
            <Car size={12} className="text-ansys-yellow shrink-0" />
            <span className="text-gray-500 text-[10px] uppercase font-bold tracking-wider hidden sm:inline shrink-0">Vehicle:</span>
            <span className="font-semibold text-white truncate max-w-[130px] sm:max-w-[190px]">{vehicle.name}</span>
            <span className="px-1.5 py-0.2 rounded bg-white/5 border border-white/10 text-[9px] text-ansys-yellow font-bold shrink-0">
              {vehicle.version}
            </span>
          </div>

          <span className="text-white/20 hidden md:inline shrink-0">|</span>

          {/* Active Setup (md+) */}
          <div className="hidden md:flex items-center gap-1.5 text-gray-300 min-w-0" title={`Active Setup: ${setup.name} (${setup.version})`}>
            <Wrench size={12} className="text-purple-400 shrink-0" />
            <span className="text-gray-500 text-[10px] uppercase font-bold tracking-wider shrink-0">Setup:</span>
            <span className="font-medium text-gray-200 truncate max-w-[140px] lg:max-w-[180px]">{setup.name}</span>
            <span className="px-1.5 py-0.2 rounded bg-purple-950/50 border border-purple-500/30 text-[9px] text-purple-300 font-bold shrink-0">
              {setup.version}
            </span>
          </div>

          <span className="text-white/20 hidden xl:inline shrink-0">|</span>

          {/* Active Track (xl+) */}
          <div className="hidden xl:flex items-center gap-1.5 text-gray-300 min-w-0" title={`Active Track: ${track.name}`}>
            <Flag size={12} className="text-cyan-400 shrink-0" />
            <span className="text-gray-500 text-[10px] uppercase font-bold tracking-wider shrink-0">Track:</span>
            <span className="font-medium text-gray-200 truncate max-w-[130px]">{track.name}</span>
          </div>
        </div>

        {/* Right: Trial Indicator, Validation Badge & Expandable Drawer Toggle */}
        <div className="flex items-center gap-2 shrink-0">
          {(user?.is_trial || user?.plan === "TRIAL") && (
            <Link
              href="/evaluation"
              className="px-2 py-0.5 rounded border border-ansys-yellow/40 bg-ansys-yellow/10 text-ansys-yellow hover:bg-ansys-yellow/20 text-[10px] font-bold tracking-wider flex items-center gap-1.5 shrink-0 transition-all"
              title="Active 7-Day Engineering Trial — Click to view Trial Hub"
            >
              <Sparkles size={11} className="text-ansys-yellow" />
              <span className="hidden sm:inline">7-DAY TRIAL</span>
              <span className="text-[9px] px-1 py-0.2 rounded bg-ansys-yellow/20 font-mono">HUB</span>
            </Link>
          )}

          <div
            className={`px-2 py-0.5 rounded border text-[10px] font-bold flex items-center gap-1.5 ${getValidationBadge(
              validation.status
            )}`}
            title={`Validation Status: ${validation.status} (${Math.round(validation.score)}% confidence score)`}
          >
            <ShieldCheck size={11} />
            <span className="hidden sm:inline">{validation.status}</span>
            <span className="font-mono">({Math.round(validation.score)}%)</span>
          </div>

          {/* Expand / Collapse Button */}
          <button
            id="status-bar-expand-toggle"
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            aria-expanded={isExpanded}
            aria-label="Toggle Workspace Context Panel"
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold border transition-all ${
              isExpanded
                ? "bg-ansys-yellow/15 border-ansys-yellow/40 text-ansys-yellow shadow-[0_0_12px_rgba(242,169,0,0.12)]"
                : "bg-white/[0.04] border-white/[0.08] text-gray-300 hover:text-white hover:bg-white/[0.08]"
            }`}
          >
            <SlidersHorizontal size={11} className={isExpanded ? "text-ansys-yellow" : "text-gray-400"} />
            <span className="hidden sm:inline">{isExpanded ? "Collapse" : "Workspace Details"}</span>
            <ChevronDown size={11} className={`transition-transform duration-200 ${isExpanded ? "rotate-180 text-ansys-yellow" : "text-gray-400"}`} />
          </button>
        </div>

      </div>

      {/* ── Expandable Engineering Context Drawer ── */}
      {isExpanded && (
        <div id="workspace-status-drawer" className="w-full bg-[#0e0e13] border-t border-white/[0.06] shadow-2xl px-4 sm:px-6 py-4 animate-in slide-in-from-top-1 duration-150">
          <div className="max-w-[1560px] mx-auto flex flex-col gap-3.5">
            
            {/* Header / Subtitle */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-ansys-yellow">
                <Layers size={14} />
                <span>Active Engineering Workspace State & Parameters</span>
              </div>
              <span className="text-[10px] text-gray-500 font-mono">
                Session: <strong className="text-gray-300">{sessionName}</strong>
              </span>
            </div>

            {/* 4-Card Responsive Engineering Matrix */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs font-mono">
              
              {/* Card 1: Active Vehicle */}
              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-white/[0.12] transition-colors flex flex-col justify-between">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 font-bold uppercase flex items-center gap-1.5 text-[10px] tracking-wider">
                      <Car size={13} className="text-ansys-yellow" /> Active Vehicle
                    </span>
                    <span className="px-1.5 py-0.2 rounded bg-white/5 border border-white/10 text-[9px] text-ansys-yellow font-bold">
                      {vehicle.version}
                    </span>
                  </div>
                  <div className="font-semibold text-white text-sm truncate">{vehicle.name}</div>
                  <div className="text-[11px] text-gray-400 space-y-0.5 pt-1">
                    <div><span className="text-gray-500">Total Mass:</span> {vehicle.mass_kg} kg</div>
                    <div><span className="text-gray-500">Wheelbase:</span> {vehicle.wheelbase_m} m</div>
                  </div>
                </div>
                <Link
                  href="/garage"
                  className="mt-3 text-[10px] text-ansys-yellow hover:underline font-semibold flex items-center gap-1"
                >
                  Configure in Garage <ExternalLink size={10} />
                </Link>
              </div>

              {/* Card 2: Active Setup */}
              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-white/[0.12] transition-colors flex flex-col justify-between">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 font-bold uppercase flex items-center gap-1.5 text-[10px] tracking-wider">
                      <Wrench size={13} className="text-purple-400" /> Active Setup
                    </span>
                    <span className="px-1.5 py-0.2 rounded bg-purple-950/50 border border-purple-500/30 text-[9px] text-purple-300 font-bold">
                      {setup.version}
                    </span>
                  </div>
                  <div className="font-semibold text-white text-sm truncate">{setup.name}</div>
                  <div className="text-[11px] text-gray-400 space-y-0.5 pt-1">
                    <div><span className="text-gray-500">Spring Front:</span> {setup.k_spring_front.toLocaleString()} N/m</div>
                    <div><span className="text-gray-500">Spring Rear:</span> {setup.k_spring_rear.toLocaleString()} N/m</div>
                    <div><span className="text-gray-500">Damper Front:</span> {setup.c_damper_front.toLocaleString()} Ns/m</div>
                  </div>
                </div>
                <Link
                  href="/quarter-car"
                  className="mt-3 text-[10px] text-purple-400 hover:underline font-semibold flex items-center gap-1"
                >
                  Tune in Simulation <ExternalLink size={10} />
                </Link>
              </div>

              {/* Card 3: Track & Conditions */}
              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-white/[0.12] transition-colors flex flex-col justify-between">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 font-bold uppercase flex items-center gap-1.5 text-[10px] tracking-wider">
                      <Flag size={13} className="text-cyan-400" /> Circuit & Tires
                    </span>
                    <span className="text-[10px] text-cyan-400 font-bold font-mono">{track.length_m.toLocaleString()} m</span>
                  </div>
                  <div className="font-semibold text-white text-sm truncate">{track.name}</div>
                  <div className="text-[11px] text-gray-400 space-y-0.5 pt-1">
                    <div><span className="text-gray-500">Track Temp:</span> {track.track_temp_c}°C ({track.weather})</div>
                    <div><span className="text-gray-500">Tire Model:</span> {tire.name}</div>
                    <div><span className="text-gray-500">Nominal Pressure:</span> {tire.nominal_pressure_kpa} kPa</div>
                  </div>
                </div>
                <div className="mt-3 text-[10px] text-gray-400 truncate">
                  <span className="text-gray-500">Telemetry:</span> {telemetry.sessionId}
                </div>
              </div>

              {/* Card 4: Solver & Validation */}
              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-white/[0.12] transition-colors flex flex-col justify-between">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-400 font-bold uppercase flex items-center gap-1.5 text-[10px] tracking-wider">
                      <ShieldCheck size={13} className="text-emerald-400" /> Governance & Solver
                    </span>
                    <span className={`px-1.5 py-0.2 rounded border text-[9px] font-bold ${getValidationBadge(validation.status)}`}>
                      {Math.round(validation.score)}% Score
                    </span>
                  </div>
                  <div className="font-semibold text-emerald-400 text-sm">{validation.status}</div>
                  <div className="text-[11px] text-gray-400 space-y-0.5 pt-1">
                    <div><span className="text-gray-500">Solver:</span> {simulation.solverInfo.solver}</div>
                    <div><span className="text-gray-500">Model Ver:</span> {modelVersion}</div>
                    <div><span className="text-gray-500">Build:</span> {simulation.solverInfo.build}</div>
                  </div>
                </div>
                <Link
                  href={`/report?run_id=${encodeURIComponent(simulation.activeRunId || "latest")}`}
                  className="mt-3 text-[10px] text-emerald-400 hover:underline font-semibold flex items-center gap-1 truncate"
                >
                  Active Run: {simulation.activeRunId || "RUN-VAL-7ceb75"} <ExternalLink size={10} />
                </Link>
              </div>

            </div>

            {/* Action Footer */}
            <div className="flex items-center justify-between pt-2.5 border-t border-white/[0.06] text-xs">
              <button
                type="button"
                onClick={resetToDefaults}
                className="px-3 py-1.5 rounded-lg border border-red-500/20 text-red-400 hover:bg-red-500/10 text-[11px] font-mono flex items-center gap-1.5 transition-colors"
              >
                <RotateCcw size={12} />
                Reset Workspace to Defaults
              </button>

              <button
                type="button"
                onClick={() => setIsExpanded(false)}
                className="px-3 py-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-gray-300 hover:text-white text-[11px] font-medium transition-colors flex items-center gap-1.5"
              >
                <ChevronDown size={12} className="rotate-180" />
                Collapse Panel
              </button>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
