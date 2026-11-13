/**
 * components/sim/theme.ts — centralized Plotly dark theme (P1-ARCH-02).
 * Unified Motorsport Carbon & Telemetry engineering plot theme.
 */

import type { PlotParams } from "react-plotly.js";

export const PLOT_COLORS = {
  primary: "#06B6D4",   // Telemetry Cyan — Primary / Baseline / Setup A
  secondary: "#F43F5E", // Racing Coral — Secondary / Perturbed / Setup B
  target: "#F59E0B",    // Precision Amber — Target / Optimal / Envelope
  validated: "#10B981", // Emerald — Validated / Pass Band
} as const;

export const PLOT_TRACE_PALETTE = [
  PLOT_COLORS.primary,
  PLOT_COLORS.secondary,
  PLOT_COLORS.target,
  PLOT_COLORS.validated,
] as const;

const MONO_FAMILY =
  "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";

const AXIS_FONT = {
  color: "#94A3B8",
  size: 10,
  family: MONO_FAMILY,
};

const AXIS_BASE = {
  color: "#94A3B8",
  gridcolor: "rgba(255, 255, 255, 0.06)",
  zerolinecolor: "rgba(255, 255, 255, 0.10)",
  linecolor: "rgba(255, 255, 255, 0.08)",
  tickfont: { ...AXIS_FONT },
  title: { font: { ...AXIS_FONT } },
};

const LEGACY_GRAY_COLORS = new Set([
  "#444",
  "#444444",
  "#555",
  "#555555",
  "#666",
  "#666666",
  "#777",
  "#777777",
  "#888",
  "#888888",
  "#71717a",
  "#9ca3af",
  "#a1a1aa",
]);

function normalizeFont(
  font: unknown,
  fallback: { color: string; size: number; family: string },
) {
  const f = (font && typeof font === "object" ? font : {}) as Record<string, unknown>;
  const rawColor = typeof f.color === "string" ? f.color.trim().toLowerCase() : "";
  const color =
    !rawColor || LEGACY_GRAY_COLORS.has(rawColor)
      ? fallback.color
      : rawColor === "#f2a900"
        ? PLOT_COLORS.target
        : (f.color as string);

  return {
    ...fallback,
    ...f,
    color,
    family: fallback.family,
  };
}

function mergeAxis(baseAxis: typeof AXIS_BASE, overrideAxis: unknown) {
  if (!overrideAxis || typeof overrideAxis !== "object") {
    return { ...baseAxis };
  }
  const ov = overrideAxis as Record<string, unknown>;
  const rawTitle = ov.title;
  const titleObj =
    typeof rawTitle === "string"
      ? { text: rawTitle, font: { ...AXIS_FONT } }
      : rawTitle && typeof rawTitle === "object"
        ? {
            ...(rawTitle as Record<string, unknown>),
            font: normalizeFont((rawTitle as Record<string, unknown>).font, AXIS_FONT),
          }
        : baseAxis.title;

  return {
    ...baseAxis,
    ...ov,
    color:
      typeof ov.color === "string" && LEGACY_GRAY_COLORS.has(ov.color.trim().toLowerCase())
        ? baseAxis.color
        : typeof ov.color === "string"
          ? ov.color
          : baseAxis.color,
    gridcolor: typeof ov.gridcolor === "string" ? ov.gridcolor : baseAxis.gridcolor,
    zerolinecolor: typeof ov.zerolinecolor === "string" ? ov.zerolinecolor : baseAxis.zerolinecolor,
    tickfont: normalizeFont(ov.tickfont, AXIS_FONT),
    title: titleObj,
  };
}

export const DARK_BASE = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "#0D1017",
  colorway: [...PLOT_TRACE_PALETTE],
  font: { color: "#94A3B8", size: 11, family: MONO_FAMILY },
  xaxis: { ...AXIS_BASE },
  yaxis: { ...AXIS_BASE },
  legend: {
    font: { ...AXIS_FONT },
    bgcolor: "rgba(0,0,0,0)",
    orientation: "h" as const,
    y: -0.15,
  },
  margin: { l: 58, r: 18, t: 32, b: 55 },
  autosize: true,
  hoverlabel: {
    bgcolor: "#11151F",
    bordercolor: "rgba(255, 255, 255, 0.12)",
    font: { color: "#E2E8F0", size: 11, family: MONO_FAMILY },
  },
};

export function darkLayout(overrides: Record<string, unknown> = {}): PlotParams["layout"] {
  const rawTitle = overrides.title;
  const titleFallback = { color: "#94A3B8", size: 11, family: MONO_FAMILY };
  const title =
    typeof rawTitle === "string"
      ? { text: rawTitle, font: titleFallback }
      : rawTitle && typeof rawTitle === "object"
        ? {
            ...(rawTitle as Record<string, unknown>),
            font: normalizeFont((rawTitle as Record<string, unknown>).font, titleFallback),
          }
        : undefined;

  return {
    ...DARK_BASE,
    ...overrides,
    ...(title ? { title } : {}),
    xaxis: mergeAxis(DARK_BASE.xaxis, overrides.xaxis),
    yaxis: mergeAxis(DARK_BASE.yaxis, overrides.yaxis),
    ...(overrides.yaxis2 ? { yaxis2: mergeAxis(DARK_BASE.yaxis, overrides.yaxis2) } : {}),
  } as PlotParams["layout"];
}
