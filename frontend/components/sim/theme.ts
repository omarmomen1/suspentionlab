/**
 * components/sim/theme.ts — centralized Plotly dark theme (P1-ARCH-02).
 * Previously duplicated as DARK_BASE + darkLayout() in every sim page.
 */

export const DARK_BASE = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { color: "#9ca3af", size: 11, family: "Inter, monospace" },
  xaxis: { color: "#888888", gridcolor: "#1e1e24", zerolinecolor: "#3f3f46", tickfont: { color: "#9ca3af", size: 10 } },
  yaxis: { color: "#888888", gridcolor: "#1e1e24", zerolinecolor: "#3f3f46", tickfont: { color: "#9ca3af", size: 10 } },
  legend: { font: { color: "#a1a1aa", size: 10 }, bgcolor: "rgba(0,0,0,0)", orientation: "h" as const, y: -0.15 },
  margin: { l: 58, r: 18, t: 32, b: 55 },
  autosize: true,
  hoverlabel: { bgcolor: "#0d0d0f", bordercolor: "#333", font: { color: "#f3f4f6", size: 11 } },
};

export function darkLayout(overrides: Record<string, unknown> = {}) {
  return { ...DARK_BASE, ...overrides };
}
