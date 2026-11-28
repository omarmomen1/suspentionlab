


"use client";

import Plot from "./sim/Plot";

interface GGFrictionCircleProps {
  maxG: number;
  latG: number;
  longG: number;
  /** Wave 5A: full sampled (lat, long) G point cloud from real telemetry. */
  points?: { latG: number[]; longG: number[] };
}

export default function GGFrictionCircle({ maxG, latG, longG, points }: GGFrictionCircleProps) {
  const currentTotalG = Math.sqrt(latG * latG + longG * longG);
  const exploitationPct = maxG > 0 ? ((currentTotalG / maxG) * 100).toFixed(0) : "0";
  const axisBound = Math.max(3, Math.ceil(Math.max(maxG || 1.5, Math.abs(latG), Math.abs(longG)) * 1.15 * 10) / 10);

  // We use Plotly shapes to draw the theoretical max G circle
  const circleShape: any = {
    type: "circle" as const,
    x0: -maxG,
    y0: -maxG,
    x1: maxG,
    y1: maxG,
    line: { color: "rgba(242, 169, 0, 0.5)", width: 2, dash: "dot" },
    fillcolor: "rgba(242, 169, 0, 0.05)"
  };

  return (
    <div
      role="region"
      aria-label="G-G Friction Circle"
      className="w-full h-full flex flex-col items-center justify-center bg-[#0d0d0f] rounded-xl border border-white/10 p-2 relative"
    >
      <span className="sr-only">
        G-G Friction Circle: Current Lateral acceleration is {latG.toFixed(2)} g, Longitudinal acceleration is {longG.toFixed(2)} g. Resultant acceleration {currentTotalG.toFixed(2)} g ({exploitationPct}% of {maxG.toFixed(2)} g tire limit).
      </span>
      <Plot
        data={[
          ...(points && points.latG.length > 0
            ? [{
                x: points.latG,
                y: points.longG,
                type: "scatter" as const,
                mode: "markers" as const,
                marker: { color: "rgba(242, 169, 0, 0.35)", size: 3, symbol: "circle" },
                name: "Sampled G-G points",
                hoverinfo: "skip" as const,
              }]
            : []),
          {
            x: [latG],
            y: [longG],
            type: "scatter",
            mode: "markers",
            marker: { color: "#C8F04B", size: 12, symbol: "circle" },
            name: "Actual G"
          }
        ]}
        layout={{
          title: { text: "G-G Friction Circle", font: { color: "#ffffff", size: 14 } },
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          xaxis: { 
            title: { text: "Lat G", font: { color: "#9ca3af" } },
            range: [-axisBound, axisBound], 
            gridcolor: "rgba(255,255,255,0.1)", 
            zerolinecolor: "rgba(255,255,255,0.3)",
            tickfont: { color: "#9ca3af" }
          },
          yaxis: { 
            title: { text: "Long G", font: { color: "#9ca3af" } },
            range: [-axisBound, axisBound], 
            gridcolor: "rgba(255,255,255,0.1)", 
            zerolinecolor: "rgba(255,255,255,0.3)",
            tickfont: { color: "#9ca3af" }
          },
          shapes: [circleShape],
          showlegend: false,
          margin: { l: 50, r: 40, t: 40, b: 50 },
          width: 300,
          height: 300
        }}
        config={{ displayModeBar: false }}
      />
    </div>
  );
}

