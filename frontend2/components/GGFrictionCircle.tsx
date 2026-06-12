// @ts-nocheck

"use client";

import dynamic from "next/dynamic";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface GGFrictionCircleProps {
  maxG: number;
  latG: number;
  longG: number;
}

export default function GGFrictionCircle({ maxG, latG, longG }: GGFrictionCircleProps) {
  // We use Plotly shapes to draw the theoretical max G circle
  const circleShape = {
    type: "circle" as const,
    x0: -maxG,
    y0: -maxG,
    x1: maxG,
    y1: maxG,
    line: { color: "rgba(242, 169, 0, 0.5)", width: 2, dash: "dot" }, // Ansys Yellow outline
    fillcolor: "rgba(242, 169, 0, 0.05)"
  };

  return (
    <div className="w-full h-full flex items-center justify-center bg-[#0d0d0f] rounded-xl border border-white/10 p-2">
      <Plot
        data={[
          {
            x: [latG],
            y: [longG],
            type: "scatter",
            mode: "markers",
            marker: { color: "#f2a900", size: 12, symbol: "circle" }, // The actual car dot
            name: "Actual G"
          }
        ]}
        layout={{
          title: { text: "G-G Friction Circle", font: { color: "#ffffff", size: 14 } },
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          xaxis: { 
            title: { text: "Lat G", font: { color: "#888" } },
            range: [-3, 3], 
            gridcolor: "rgba(255,255,255,0.1)", 
            zerolinecolor: "rgba(255,255,255,0.3)",
            tickfont: { color: "#888" }
          },
          yaxis: { 
            title: { text: "Long G", font: { color: "#888" } },
            range: [-3, 3], 
            gridcolor: "rgba(255,255,255,0.1)", 
            zerolinecolor: "rgba(255,255,255,0.3)",
            tickfont: { color: "#888" }
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
