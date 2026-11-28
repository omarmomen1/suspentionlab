"use client";

import dynamic from "next/dynamic";
import React from "react";
import { type PlotParams } from "react-plotly.js";

const PlotlyCore = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full min-h-[180px] flex flex-col items-center justify-center bg-[#0d0d0f]/40 border border-white/[0.03] rounded-lg animate-pulse">
      <div className="flex items-center gap-2 text-xs font-mono tracking-widest text-zinc-300">
        <div className="w-1.5 h-1.5 rounded-full bg-signal/40 animate-ping" />
        INITIALIZING GRAPH
      </div>
    </div>
  ),
});

const DEFAULT_CONFIG: Partial<PlotParams["config"]> = {
  displaylogo: false,
  responsive: true,
  displayModeBar: true,
  // Keep the modebar lean so it never crowds the chart title
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
};

export default function Plot(props: PlotParams) {
  const { config, ...rest } = props;
  return <PlotlyCore config={{ ...DEFAULT_CONFIG, ...(config as object) }} {...rest} />;
}

