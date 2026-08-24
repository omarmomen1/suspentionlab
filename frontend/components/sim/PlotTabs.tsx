"use client";

/**
 * components/sim/PlotTabs.tsx (P1-ARCH-01/P1-ARCH-02)
 * Shared tab bar for simulation plot views. Generic over the tab type —
 * pass an array of { label, icon } and controlled active/onChange.
 */

import React from "react";

export interface PlotTabDef {
  label: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  icon: React.ComponentType<any>;
}

interface PlotTabsProps {
  tabs: PlotTabDef[];
  activeTab: number;
  onChange: (index: number) => void;
}

export default function PlotTabs({ tabs, activeTab, onChange }: PlotTabsProps) {
  return (
    <div className="flex gap-1.5 shrink-0 overflow-x-auto custom-scrollbar" role="tablist">
      {tabs.map((tab, i) => {
        const Icon = tab.icon;
        const active = i === activeTab;
        return (
          <button
            key={tab.label}
            onClick={() => onChange(i)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-bold whitespace-nowrap transition-all ${
              active
                ? "bg-ansys-yellow/15 text-ansys-yellow border border-ansys-yellow/40"
                : "bg-[#141416] text-gray-500 border border-[#252525] hover:text-gray-300 hover:border-[#3a3a3a]"
            }`}
            aria-selected={active}
            role="tab"
          >
            <Icon size={13} />
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
