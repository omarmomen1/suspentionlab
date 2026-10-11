"use client";

/**
 * components/sim/ParameterControls.tsx (P1-ARCH-02)
 * Shared collapsible section wrapper + debounced numeric parameter input.
 * Canonical version — previously duplicated across half-car, full-car,
 * handling, and quarter-car pages.
 */

import React, { useState, useEffect } from "react";

export function ParamSection({ title, children, defaultOpen = true }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const sectionId = `param-sec-${title.toLowerCase().replace(/[^a-z0-9]/g, '-')}`;

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-controls={sectionId}
        className="w-full text-[9px] font-bold text-gray-400 uppercase tracking-[0.16em] pb-1.5 border-b border-[#1e1e1e] cursor-pointer hover:text-white transition-colors flex justify-between items-center text-left"
      >
        <span>{title}</span>
        <span aria-hidden="true" className="text-[10px] transform transition-transform duration-200" style={{ rotate: isOpen ? '0deg' : '-90deg' }}>▼</span>
      </button>
      <div id={sectionId} className={isOpen ? "space-y-2" : "hidden"}>
        {children}
      </div>
    </div>
  );
}

export function ParameterInput({
  label, val, unit, step = 1, min, onChange, hasError
}: {
  label: string; val: number; unit: string;
  step?: number; min?: number; onChange: (v: number) => void;
  hasError?: boolean;
}) {
  const [localVal, setLocalVal] = useState(val.toString());
  const id = label.toLowerCase().replace(/[^a-z0-9]+/g, '-');

  useEffect(() => {
    setLocalVal(val.toString());
  }, [val]);

  const flush = (overrideVal?: number) => {
    const parsed = overrideVal !== undefined ? overrideVal : parseFloat(localVal);
    if (!isNaN(parsed)) {
      const clamped = min !== undefined ? Math.max(min, parsed) : parsed;
      onChange(clamped);
      setLocalVal(clamped.toString());
    } else {
      setLocalVal(val.toString());
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      flush();
    } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
      e.preventDefault();
      const multiplier = e.shiftKey ? 10 : (e.ctrlKey || e.altKey || e.metaKey) ? 100 : 1;
      const delta = (e.key === "ArrowUp" ? 1 : -1) * step * multiplier;
      const current = parseFloat(localVal) || 0;
      const nextVal = current + delta;
      flush(nextVal);
    }
  };

  return (
    <div className="flex justify-between items-center gap-2">
      <label htmlFor={id} className="text-[11px] text-gray-400 flex-1 min-w-0 leading-tight cursor-pointer hover:text-gray-200 transition-colors">
        {label}
      </label>
      <div className="relative shrink-0">
        <input
          id={id}
          type="number"
          step={step}
          value={localVal}
          min={min}
          aria-invalid={hasError ? "true" : undefined}
          title={`${label}: ${val} ${unit} (↑/↓: ${step}, Shift+↑/↓: ${step * 10}, Ctrl+↑/↓: ${step * 100})`}
          onChange={(e) => setLocalVal(e.target.value)}
          onBlur={() => flush()}
          onKeyDown={handleKeyDown}
          className={`bg-[#0d0d0d] border text-[11px] rounded-lg px-2 py-1.5 text-white w-28 text-right pr-9 focus:outline-none transition-all ${
            hasError ? "border-red-500/50 focus:border-red-500 focus:ring-1 focus:ring-red-500/50 text-red-100" : "border-[#252525] focus:border-ansys-yellow/60 focus:ring-1 focus:ring-ansys-yellow/50"
          }`}
        />
        <span aria-hidden="true" className={`absolute right-2 top-1/2 -translate-y-1/2 text-[9px] pointer-events-none ${hasError ? "text-red-400" : "text-gray-500"}`}>
          {unit}
        </span>
      </div>
    </div>
  );
}
