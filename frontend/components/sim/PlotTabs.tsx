"use client";

/**
 * components/sim/PlotTabs.tsx (P1-ARCH-01/P1-ARCH-02)
 * Shared tab bar for simulation plot views. Generic over the tab type —
 * pass an array of { label, icon } and controlled active/onChange.
 */

import React from "react";

export interface PlotTabDef {
  label: string;
  
  icon: React.ComponentType<any>;
}

interface PlotTabsProps {
  tabs: PlotTabDef[];
  activeTab: number;
  onChange: (index: number) => void;
}

export default function PlotTabs({ tabs, activeTab, onChange }: PlotTabsProps) {
  const tabRefs = React.useRef<(HTMLButtonElement | null)[]>([]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    let nextIndex = activeTab;
    if (e.key === "ArrowRight") {
      e.preventDefault();
      nextIndex = (activeTab + 1) % tabs.length;
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      nextIndex = (activeTab - 1 + tabs.length) % tabs.length;
    } else if (e.key === "Home") {
      e.preventDefault();
      nextIndex = 0;
    } else if (e.key === "End") {
      e.preventDefault();
      nextIndex = tabs.length - 1;
    }

    if (nextIndex !== activeTab) {
      onChange(nextIndex);
      tabRefs.current[nextIndex]?.focus();
    }
  };

  return (
    <div
      className="flex gap-1.5 shrink-0 overflow-x-auto custom-scrollbar"
      role="tablist"
      aria-label="Simulation Analysis Views"
      onKeyDown={handleKeyDown}
    >
      {tabs.map((tab, i) => {
        const Icon = tab.icon;
        const active = i === activeTab;
        return (
          <button
            key={tab.label}
            ref={(el) => { tabRefs.current[i] = el; }}
            id={`sim-tab-${i}`}
            aria-controls={`sim-tabpanel-${i}`}
            onClick={() => onChange(i)}
            tabIndex={active ? 0 : -1}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold whitespace-nowrap transition-all ${
              active
                ? "bg-signal/15 text-signal border border-signal/40"
                : "bg-[#141416] text-gray-400 border border-[#252525] hover:text-white hover:border-[#3a3a3a]"
            }`}
            aria-selected={active}
            role="tab"
          >
            <Icon size={13} aria-hidden="true" />
            <span>{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}
