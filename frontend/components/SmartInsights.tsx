"use client";

/**
 * SmartInsights.tsx
 * ==================
 * Revolutionary Feature: Auto Engineering Insights Panel
 *
 * Analyzes quarter-car simulation results using production-grade engineering
 * heuristics and generates actionable, color-coded setup recommendations.
 *
 * This is NOT an LLM call — it's deterministic engineering logic based on:
 *   - ISO 2631-1:1997 comfort thresholds
 *   - Rajalingham et al. (1997) suspension performance indices
 *   - Dixon (2009) Shock Absorber Handbook guidelines
 *   - Milliken & Milliken "Race Car Vehicle Dynamics"
 */

import React, { useMemo } from "react";
import { AlertTriangle, CheckCircle2, Info, ChevronRight, Zap, Target } from "lucide-react";

interface QuarterCarResult {
  f_n_s: number;
  f_n_u: number;
  zeta_s: number;
  zeta_u: number;
  rms_body_accel_wk: number;
  rms_body_accel: number;
  rms_susp_travel: number;
  peak_susp_travel: number;
  rms_tire_load: number;
  peak_transmissibility: number;
  freq_at_peak_tx: number;
  k_w: number;
  [key: string]: unknown;
}

export interface Insight {
  severity: "critical" | "warning" | "good" | "info";
  category: string;
  finding: string;
  action: string;
  value: string;
  patch?: Record<string, number>;
  patchLabel?: string;
}

export interface SmartInsightsProps {
  result: QuarterCarResult | null;
  onApplyRecommendation?: (patch: Record<string, number>) => void;
}

const SEVERITY_CONFIG = {
  critical: {
    bg: "bg-red-950/30 border-red-800/40",
    text: "text-red-400",
    icon: <AlertTriangle size={13} />,
    label: "Critical",
  },
  warning: {
    bg: "bg-amber-950/30 border-amber-800/30",
    text: "text-amber-400",
    icon: <AlertTriangle size={13} />,
    label: "Warning",
  },
  good: {
    bg: "bg-emerald-950/20 border-emerald-800/25",
    text: "text-emerald-400",
    icon: <CheckCircle2 size={13} />,
    label: "Good",
  },
  info: {
    bg: "bg-[#141416] border-[#252525]",
    text: "text-gray-400",
    icon: <Info size={13} />,
    label: "Note",
  },
};

function analyzeResults(r: QuarterCarResult): Insight[] {
  const insights: Insight[] = [];
  const cCrit = (r.c_crit_s as number) || 4500;
  const currentKs = (r.k_s as number) || (r.k_w as number) || 25000;

  // ── 1. Ride Comfort (ISO 2631-1) ──────────────────────────────────────────
  const wkRms = r.rms_body_accel_wk ?? r.rms_body_accel;
  if (wkRms > 2.0) {
    insights.push({
      severity: "critical",
      category: "Ride Comfort",
      finding: `Wk-weighted RMS = ${wkRms.toFixed(3)} m/s² — ISO 2631-1 classifies this as "Very Uncomfortable". Human subjects report nausea above 2.0 m/s².`,
      action: "Increase spring rate by 15–25% OR increase damping ratio to 0.35–0.45. Consider softer tire (reduce k_t by 10%).",
      value: `${wkRms.toFixed(3)} m/s²`,
      patch: { c: Math.round(cCrit * 0.35) },
      patchLabel: `Set Damping to ζ = 0.35 (${Math.round(cCrit * 0.35)} N·s/m)`,
    });
  } else if (wkRms > 1.0) {
    insights.push({
      severity: "warning",
      category: "Ride Comfort",
      finding: `Wk RMS = ${wkRms.toFixed(3)} m/s² — "Uncomfortable" per ISO 2631-1. Threshold for road cars is typically < 0.8 m/s².`,
      action: "Reduce spring rate by 10–15% and increase damping (target ζ = 0.30–0.40).",
      value: `${wkRms.toFixed(3)} m/s²`,
      patch: { k_s: Math.round(currentKs * 0.88), c: Math.round(cCrit * 0.33) },
      patchLabel: `Tune Spring & Damper for Comfort (${Math.round(currentKs * 0.88)} N/m, ${Math.round(cCrit * 0.33)} N·s/m)`,
    });
  } else if (wkRms < 0.315) {
    insights.push({
      severity: "good",
      category: "Ride Comfort",
      finding: `Wk RMS = ${wkRms.toFixed(3)} m/s² — Excellent. ISO 2631-1 "Not Uncomfortable". Comfortably within passenger car targets.`,
      action: "Maintain setup. Could explore spring rate increase for sharper handling if travel budget allows.",
      value: `${wkRms.toFixed(3)} m/s²`,
    });
  }

  // ── 2. Damping Ratio ζ ────────────────────────────────────────────────────
  const zeta = r.zeta_s;
  if (zeta < 0.15) {
    insights.push({
      severity: "critical",
      category: "Damping",
      finding: `Sprung damping ratio ζ = ${zeta.toFixed(3)} — Severely underdamped. Expect prolonged oscillation (settling time > 5 cycles). Risk of tire lift over consecutive bumps.`,
      action: `Increase damping coefficient by at least ${Math.round((0.25 - zeta) * 100)}% of critical. Target ζ = 0.25–0.35 for road, 0.35–0.45 for race.`,
      value: `ζ = ${zeta.toFixed(3)}`,
      patch: { c: Math.round(cCrit * 0.30) },
      patchLabel: `Set Damping to Target ζ = 0.30 (${Math.round(cCrit * 0.30)} N·s/m)`,
    });
  } else if (zeta > 0.7) {
    insights.push({
      severity: "warning",
      category: "Damping",
      finding: `ζ = ${zeta.toFixed(3)} — Overdamped. Suspension will feel "wooden". Slow response to road perturbations, poor dynamic tire contact.`,
      action: "Reduce damping by 20–30%. Check motion ratio — high MR amplifies effective damping at wheel.",
      value: `ζ = ${zeta.toFixed(3)}`,
      patch: { c: Math.round(cCrit * 0.38) },
      patchLabel: `Reduce Damping to ζ = 0.38 (${Math.round(cCrit * 0.38)} N·s/m)`,
    });
  } else if (zeta >= 0.25 && zeta <= 0.5) {
    insights.push({
      severity: "good",
      category: "Damping",
      finding: `ζ = ${zeta.toFixed(3)} — Well-tuned. Falls within the Dixon optimal range for ride/handling balance (0.25–0.50).`,
      action: "No action required. Fine-tune within band for specific use case (road/track).",
      value: `ζ = ${zeta.toFixed(3)}`,
    });
  }

  // ── 3. Suspension Travel ──────────────────────────────────────────────────
  const peakTravMM = r.peak_susp_travel * 1000;
  if (peakTravMM > 150) {
    insights.push({
      severity: "critical",
      category: "Suspension Travel",
      finding: `Peak travel = ${peakTravMM.toFixed(1)} mm — Exceeds typical bump stop clearance for road cars (100–130 mm). Bump stop contact likely.`,
      action: "Increase spring rate (k_s +20%) OR reduce bump amplitude in test profile. Check motion ratio.",
      value: `${peakTravMM.toFixed(1)} mm`,
      patch: { k_s: Math.round(currentKs * 1.20) },
      patchLabel: `Stiffen Spring (+20% to ${Math.round(currentKs * 1.20)} N/m)`,
    });
  } else if (peakTravMM > 80) {
    insights.push({
      severity: "warning",
      category: "Suspension Travel",
      finding: `Peak travel = ${peakTravMM.toFixed(1)} mm — Moderate. Approaching typical road-car bump stop at 100 mm. Race cars typically target < 50 mm.`,
      action: "Consider stiffening spring rate by 10% or adding progressive bump stop.",
      value: `${peakTravMM.toFixed(1)} mm`,
      patch: { k_s: Math.round(currentKs * 1.10) },
      patchLabel: `Stiffen Spring (+10% to ${Math.round(currentKs * 1.10)} N/m)`,
    });
  } else {
    insights.push({
      severity: "good",
      category: "Suspension Travel",
      finding: `Peak travel = ${peakTravMM.toFixed(1)} mm — Good. Well within typical 100 mm bump stop clearance.`,
      action: "Adequate travel margin. Verify with pothole/ISO 8608 Class D profile for worst-case.",
      value: `${peakTravMM.toFixed(1)} mm`,
    });
  }

  // ── 4. Natural Frequencies ────────────────────────────────────────────────
  const fn_s = r.f_n_s;
  const fn_u = r.f_n_u;

  if (fn_s < 0.8) {
    insights.push({
      severity: "warning",
      category: "Natural Frequency",
      finding: `Sprung frequency f_n = ${fn_s.toFixed(2)} Hz — Below typical comfort range (1–2 Hz). May excite human vestibular sensitivity. Common in luxury long-travel setups.`,
      action: "Increase spring rate or reduce sprung mass. Target f_n ≥ 1.0 Hz for most vehicles.",
      value: `${fn_s.toFixed(2)} Hz`,
      patch: { k_s: Math.round(currentKs * 1.30) },
      patchLabel: `Increase Spring Rate to Target f_n ~ 1.1 Hz (${Math.round(currentKs * 1.30)} N/m)`,
    });
  } else if (fn_s > 4.0) {
    insights.push({
      severity: "warning",
      category: "Natural Frequency",
      finding: `Sprung frequency f_n = ${fn_s.toFixed(2)} Hz — High. Race-car territory (>3 Hz). Road noise and harshness will be elevated for road use.`,
      action: "Accept if targeting track performance. For road use, reduce k_s to achieve f_n 1.5–2.5 Hz.",
      value: `${fn_s.toFixed(2)} Hz`,
      patch: { k_s: Math.round(currentKs * 0.70) },
      patchLabel: `Soften Spring Rate for Road (${Math.round(currentKs * 0.70)} N/m)`,
    });
  }

  if (fn_u < 8.0) {
    insights.push({
      severity: "warning",
      category: "Wheel-Hop Frequency",
      finding: `Unsprung f_n = ${fn_u.toFixed(2)} Hz — Below typical 8–15 Hz wheel-hop range. Tire-road contact may be poor at medium speeds.`,
      action: "Check tire stiffness k_t (may be too low). Reduce unsprung mass if possible.",
      value: `${fn_u.toFixed(2)} Hz`,
    });
  }

  // ── 5. Frequency Separation Check ─────────────────────────────────────────
  const freqRatio = fn_u / Math.max(fn_s, 0.0001);
  if (freqRatio < 3.0) {
    insights.push({
      severity: "warning",
      category: "Mode Separation",
      finding: `Frequency ratio f_u/f_s = ${freqRatio.toFixed(2)} — Close modal coupling. Sprung and unsprung modes interact, causing complex resonance behaviour. Rajalingham (1997) recommends ratio > 3.`,
      action: "Increase tire stiffness (k_t) or reduce unsprung mass. Target f_u/f_s > 4 for optimal mode isolation.",
      value: `Ratio = ${freqRatio.toFixed(2)}`,
    });
  } else {
    insights.push({
      severity: "good",
      category: "Mode Separation",
      finding: `Frequency ratio f_u/f_s = ${freqRatio.toFixed(2)} — Good mode separation. Sprung and unsprung resonances are well isolated, minimizing coupling.`,
      action: "Well-separated modes. No action required.",
      value: `Ratio = ${freqRatio.toFixed(2)}`,
    });
  }

  // ── 6. Peak Transmissibility ───────────────────────────────────────────────
  const tx = r.peak_transmissibility;
  if (tx > 4.0) {
    insights.push({
      severity: "critical",
      category: "Transmissibility",
      finding: `Peak TX = ${tx.toFixed(2)} at ${r.freq_at_peak_tx.toFixed(2)} Hz — Resonance amplification is severe (>4×). Body acceleration at resonance will be 4× the road excitation.`,
      action: "Increase damping immediately. Current ζ = " + zeta.toFixed(3) + ". Target ζ ≥ 0.30 to reduce peak TX below 2.5.",
      value: `${tx.toFixed(2)}×`,
      patch: { c: Math.round(cCrit * 0.32) },
      patchLabel: `Increase Damping to Suppress Resonance (${Math.round(cCrit * 0.32)} N·s/m)`,
    });
  } else if (tx > 2.5) {
    insights.push({
      severity: "warning",
      category: "Transmissibility",
      finding: `Peak TX = ${tx.toFixed(2)} — Moderate resonance amplification. Acceptable for performance cars; marginal for road use.`,
      action: "Consider increasing damping ratio by 0.05–0.10 to reduce peak TX.",
      value: `${tx.toFixed(2)}×`,
      patch: { c: Math.round(cCrit * (zeta + 0.08)) },
      patchLabel: `Increase Damping by +0.08 ζ (${Math.round(cCrit * (zeta + 0.08))} N·s/m)`,
    });
  }

  // ── 7. Tire Load Variation ────────────────────────────────────────────────
  const tireLoad = r.rms_tire_load;
  if (tireLoad > 1500) {
    insights.push({
      severity: "warning",
      category: "Tire Grip",
      finding: `RMS tire load variation = ${tireLoad.toFixed(0)} N — High. Traction circle grip is compromised when dynamic load variation exceeds ~30% of static load.`,
      action: "Reduce unsprung mass OR increase tire stiffness (k_t). Consider stiffer spring rate to limit travel.",
      value: `${tireLoad.toFixed(0)} N`,
    });
  }

  const order = { critical: 0, warning: 1, good: 2, info: 3 };
  insights.sort((a, b) => order[a.severity] - order[b.severity]);

  return insights;
}

export default function SmartInsights({ result, onApplyRecommendation }: SmartInsightsProps) {
  const insights = useMemo(() => {
    if (!result) return [];
    return analyzeResults(result);
  }, [result]);

  const critCount = insights.filter((i) => i.severity === "critical").length;
  const warnCount = insights.filter((i) => i.severity === "warning").length;
  const goodCount = insights.filter((i) => i.severity === "good").length;

  if (!result) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8 bg-[#111113] border border-[#1e1e1e] rounded-xl">
        <Zap size={24} className="text-gray-700 mb-2" />
        <p className="text-xs text-gray-500 font-medium">Run simulation to generate engineering insights</p>
        <p className="text-[10px] text-gray-700 mt-1">Evaluates ISO 2631 comfort, Dixon damping bands, and frequency separation automatically</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 h-full overflow-y-auto custom-scrollbar pr-1">
      <div className="flex items-center gap-3 shrink-0 bg-[#141416] border border-[#252525] rounded-xl px-4 py-2.5">
        <div className="flex items-center gap-1.5">
          <Zap size={12} className="text-ansys-yellow" />
          <span className="text-[9px] font-bold tracking-[0.2em] text-gray-600 uppercase">Auto Engineering Analysis</span>
        </div>
        <div className="flex items-center gap-3 ml-auto">
          {critCount > 0 && (
            <span className="flex items-center gap-1 text-xs font-bold text-red-400">
              <AlertTriangle size={11} /> {critCount} Critical
            </span>
          )}
          {warnCount > 0 && (
            <span className="flex items-center gap-1 text-xs font-semibold text-amber-400">
              <AlertTriangle size={11} /> {warnCount} Warning{warnCount > 1 ? "s" : ""}
            </span>
          )}
          {goodCount > 0 && (
            <span className="flex items-center gap-1 text-xs font-semibold text-emerald-400">
              <CheckCircle2 size={11} /> {goodCount} Good
            </span>
          )}
          {critCount === 0 && warnCount === 0 && (
            <span className="flex items-center gap-1 text-xs font-semibold text-emerald-400">
              <Target size={11} /> Setup validated
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {insights.map((insight, idx) => {
          const cfg = SEVERITY_CONFIG[insight.severity];
          return (
            <div
              key={idx}
              className={`border rounded-xl px-4 py-3 ${cfg.bg} flex flex-col gap-1.5`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={cfg.text}>{cfg.icon}</span>
                  <span className={`text-[9px] font-bold tracking-[0.15em] uppercase ${cfg.text}`}>
                    {cfg.label} · {insight.category}
                  </span>
                </div>
                <span className={`text-xs font-mono font-bold ${cfg.text}`}>{insight.value}</span>
              </div>
              <p className="text-[11px] text-gray-400 leading-relaxed">{insight.finding}</p>
              <div className="flex items-start gap-1.5 mt-0.5">
                <ChevronRight size={11} className="text-gray-600 mt-0.5 shrink-0" />
                <p className="text-[11px] text-gray-600 leading-relaxed">{insight.action}</p>
              </div>

              {insight.patch && onApplyRecommendation && (
                <button
                  onClick={() => onApplyRecommendation(insight.patch!)}
                  className="mt-2 self-start flex items-center gap-1.5 px-3 py-1.5 bg-ansys-yellow/10 border border-ansys-yellow/30 hover:bg-ansys-yellow/20 text-ansys-yellow rounded-lg text-[10px] font-bold transition-all shadow-sm group"
                >
                  <Zap size={11} className="group-hover:scale-110 transition-transform" />
                  {insight.patchLabel || "Apply Recommendation & Re-Solve"}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
