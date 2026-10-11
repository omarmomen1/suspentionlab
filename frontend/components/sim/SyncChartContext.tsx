"use client";

import React, { createContext, useContext, useState, ReactNode } from "react";

export interface SyncChartState {
  cursorTime: number | null;
  setCursorTime: (t: number | null) => void;
  pinnedTime: number | null;
  setPinnedTime: (t: number | null) => void;
  activePhase: string | null;
  trackPositionM: number | null;
  setTelemetryCursor: (time: number | null, phase?: string, posM?: number) => void;
}

const SyncChartContext = createContext<SyncChartState | null>(null);

export function SyncChartProvider({ children }: { children: ReactNode }) {
  const [cursorTime, setCursorTime] = useState<number | null>(null);
  const [pinnedTime, setPinnedTime] = useState<number | null>(null);
  const [activePhase, setActivePhase] = useState<string | null>(null);
  const [trackPositionM, setTrackPositionM] = useState<number | null>(null);

  const setTelemetryCursor = (time: number | null, phase?: string, posM?: number) => {
    if (pinnedTime !== null) return; // Keep frozen if user pinned it
    setCursorTime(time);
    if (phase !== undefined) setActivePhase(phase);
    if (posM !== undefined) setTrackPositionM(posM);
  };

  return (
    <SyncChartContext.Provider
      value={{
        cursorTime: pinnedTime !== null ? pinnedTime : cursorTime,
        setCursorTime,
        pinnedTime,
        setPinnedTime,
        activePhase,
        trackPositionM,
        setTelemetryCursor,
      }}
    >
      {children}
    </SyncChartContext.Provider>
  );
}

export function useSyncChart() {
  const ctx = useContext(SyncChartContext);
  if (!ctx) {
    // Fallback if not inside provider so components don't crash
    return {
      cursorTime: null,
      setCursorTime: () => {},
      pinnedTime: null,
      setPinnedTime: () => {},
      activePhase: null,
      trackPositionM: null,
      setTelemetryCursor: () => {},
    };
  }
  return ctx;
}
