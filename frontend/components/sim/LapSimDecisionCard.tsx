"use client";

import React, { useState } from "react";
import {
  Compass,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  TrendingDown,
  TrendingUp,
  ShieldAlert,
  ChevronDown,
  Wrench,
  HelpCircle,
} from "lucide-react";

export interface SetupAction {
  parameter: string;
  parameter_label: string;
  suggested_delta: number;
  unit: string;
  expected_lap_gain_s: number;
  physical_rationale: string;
  confidence: string;
}

export interface RaceEngineerDecisionData {
  verdict: string;
  total_delta_s: number;
  where_time_lost: string;
  why_time_lost: string;
  primary_category: string;
  recommended_setup_change: string;
  supporting_evidence: string[];
  confidence_rating: string;
  ranked_actions: SetupAction[];
  model_limitations: string;
}

interface LapSimDecisionCardProps {
  decision: RaceEngineerDecisionData | null;
  onApplyRecommendation?: (param: string, delta: number) => void;
}

export default function LapSimDecisionCard({
  decision,
  onApplyRecommendation,
}: LapSimDecisionCardProps) {
  const [collapsed, setCollapsed] = useState(false);

  if (!decision) return null;

  const isFaster = decision.total_delta_s < -0.005;
  const isSlower = decision.total_delta_s > 0.005;

  return (
    <div className="w-full bg-[#0d0d10] border border-[#f2a900]/40 rounded-xl overflow-hidden shadow-2xl transition-all mb-4">
      {/* Top Header */}
      <div
        onClick={() => setCollapsed(!collapsed)}
        className="cursor-pointer bg-gradient-to-r from-[#18181e] to-[#121216] px-4 py-3 border-b border-[#222228] flex items-center justify-between"
      >
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-[#f2a900]/15 border border-[#f2a900]/30 flex items-center justify-center text-[#f2a900]">
            <Compass size={16} />
          </div>
          <div>
            <div className="text-[9px] text-[#f2a900] font-bold uppercase tracking-wider font-mono">
              Race Engineer Decision Engine
            </div>
            <div className="text-sm font-bold text-white flex items-center gap-2 font-mono">
              <span>{decision.verdict}</span>
              <span
                className={`text-xs px-2 py-0.5 rounded font-bold ${
                  isFaster ? "bg-emerald-950 text-emerald-400" : isSlower ? "bg-rose-950 text-rose-400" : "bg-gray-800 text-gray-400"
                }`}
              >
                {decision.total_delta_s < 0 ? "" : "+"}
                {decision.total_delta_s.toFixed(3)}s
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-[10px] font-mono">
            <span className="text-gray-400">Confidence:</span>
            <span
              className={`px-2 py-0.5 rounded font-bold uppercase text-[9px] ${
                decision.confidence_rating === "PROVEN"
                  ? "bg-blue-900/60 text-blue-300 border border-blue-700/50"
                  : decision.confidence_rating === "LIKELY"
                  ? "bg-emerald-900/60 text-emerald-300 border border-emerald-700/50"
                  : "bg-amber-900/60 text-amber-300 border border-amber-700/50"
              }`}
            >
              {decision.confidence_rating}
            </span>
          </div>
          <ChevronDown
            size={16}
            className={`text-gray-400 transition-transform ${collapsed ? "-rotate-90" : "rotate-0"}`}
          />
        </div>
      </div>

      {/* Expanded Content */}
      {!collapsed && (
        <div className="p-4 space-y-4">
          {/* 1. Where was time lost & Why */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-[#131317] border border-[#222228]">
              <div className="text-[10px] font-bold text-[#f2a900] uppercase font-mono tracking-wider flex items-center gap-1.5 mb-1">
                <span>📍 1. Where Was Time Lost?</span>
              </div>
              <p className="text-[11px] text-gray-200 leading-relaxed font-mono">
                {decision.where_time_lost}
              </p>
            </div>

            <div className="p-3 rounded-lg bg-[#131317] border border-[#222228]">
              <div className="text-[10px] font-bold text-[#f2a900] uppercase font-mono tracking-wider flex items-center gap-1.5 mb-1">
                <span>🔍 2. Why? (Physical Mechanism)</span>
              </div>
              <p className="text-[11px] text-gray-200 leading-relaxed font-mono">
                {decision.why_time_lost}
              </p>
            </div>
          </div>

          {/* 2. Supporting Evidence */}
          <div className="p-3 rounded-lg bg-[#131317] border border-[#222228]">
            <div className="text-[10px] font-bold text-gray-400 uppercase font-mono tracking-wider mb-2 flex items-center gap-1.5">
              <span>📊 3. Supporting Quantitative Evidence</span>
            </div>
            <ul className="space-y-1 text-[11px] text-gray-300 font-mono">
              {decision.supporting_evidence.map((ev, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <span className="text-[#f2a900] mt-0.5">•</span>
                  <span>{ev}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* 3. Actionable Prescriptive Setup Recommendations */}
          {decision.ranked_actions && decision.ranked_actions.length > 0 && (
            <div className="p-3 rounded-lg bg-[#131317] border border-[#222228]">
              <div className="text-[10px] font-bold text-emerald-400 uppercase font-mono tracking-wider mb-2 flex items-center gap-1.5">
                <Wrench size={12} />
                <span>4. What Setup Change Should I Test?</span>
              </div>
              <div className="space-y-2">
                {decision.ranked_actions.map((act, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 rounded bg-[#18181e] border border-[#272730] flex items-center justify-between"
                  >
                    <div className="space-y-0.5">
                      <div className="text-xs font-bold text-white font-mono flex items-center gap-2">
                        <span>{act.parameter_label}</span>
                        <span className="text-[#f2a900] bg-[#f2a900]/10 px-1.5 py-0.2 rounded text-[10px]">
                          {act.suggested_delta > 0 ? "+" : ""}
                          {act.suggested_delta} {act.unit}
                        </span>
                        <span className="text-emerald-400 text-[10px]">
                          (Est. {act.expected_lap_gain_s < 0 ? "" : "+"}
                          {act.expected_lap_gain_s.toFixed(3)}s)
                        </span>
                      </div>
                      <div className="text-[10px] text-gray-400 leading-snug">
                        {act.physical_rationale}
                      </div>
                    </div>

                    {onApplyRecommendation && (
                      <button
                        onClick={() => onApplyRecommendation(act.parameter, act.suggested_delta)}
                        className="px-2.5 py-1 text-[10px] font-bold font-mono bg-[#f2a900] hover:bg-[#ffb914] text-black rounded transition-colors flex items-center gap-1 flex-shrink-0 ml-3"
                      >
                        <span>Apply</span>
                        <ArrowRight size={11} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 4. Model Limitations Disclosure */}
          <div className="p-2.5 rounded bg-[#101014] border border-amber-500/20 text-[10px] text-gray-400 font-mono flex items-start gap-2">
            <ShieldAlert size={14} className="text-amber-400 flex-shrink-0 mt-0.5" />
            <div>
              <span className="text-gray-300 font-bold">Quasi-Steady Model Boundaries: </span>
              {decision.model_limitations}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
