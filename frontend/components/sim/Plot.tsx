"use client";

import dynamic from "next/dynamic";
import React from "react";
import { type PlotParams } from "react-plotly.js";

const PlotlyCore = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full min-h-[180px] flex flex-col items-center justify-center bg-[#0d0d0f]/40 border border-white/[0.03] rounded-lg animate-pulse">
      <div className="flex items-center gap-2 text-[10px] font-mono tracking-widest text-gray-600">
        <div className="w-1.5 h-1.5 rounded-full bg-ansys-yellow/40 animate-ping" />
        INITIALIZING GRAPH
      </div>
    </div>
  ),
});

export default function Plot(props: PlotParams) {
  return <PlotlyCore {...props} />;
}

