"use client";

/**
 * components/sim/PlotBox.tsx — shared plot container (P1-ARCH-02).
 * Previously duplicated as function PlotBox in every sim page.
 */

import React from "react";

export default function PlotBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-[#0f0f11] border border-[#1e1e1e] rounded-xl p-2 h-full min-h-0 overflow-hidden">
      {children}
    </div>
  );
}
