"use client";

import React from "react";
import { FlaskConical } from "lucide-react";

interface SampleDemoTelemetryBadgeProps {
  size?: "xs" | "sm" | "md";
  className?: string;
}

export default function SampleDemoTelemetryBadge({
  size = "sm",
  className = "",
}: SampleDemoTelemetryBadgeProps) {
  const sizeClasses = {
    xs: "px-1.5 py-0.5 text-xs gap-1",
    sm: "px-2 py-0.5 text-xs gap-1.5",
    md: "px-2.5 py-1 text-xs gap-1.5",
  }[size];

  const iconSizes = { xs: 10, sm: 11, md: 13 }[size];

  return (
    <span
      data-testid="sample-demo-telemetry-badge"
      className={`inline-flex items-center font-mono font-bold uppercase tracking-wider rounded-md border bg-amber-950/50 border-amber-500/40 text-amber-300 ${sizeClasses} ${className}`}
      title="Built-in synthetic demo telemetry dataset for parser verification and demonstration — not live car DAQ data."
    >
      <FlaskConical size={iconSizes} className="shrink-0 text-amber-400" />
      <span>Sample Demo Telemetry</span>
    </span>
  );
}
