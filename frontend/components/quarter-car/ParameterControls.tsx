"use client";

/**
 * components/quarter-car/ParameterControls.tsx (P1-ARCH-01)
 * Extracted from quarter-car/page.tsx — collapsible section wrapper and
 * the debounced numeric parameter input.
 */

import React, { useState, useEffect } from "react";

export function ParamSection({ title, children, defaultOpen = true }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  return (
    <div className="space-y-2">
      <h3
        onClick={() => setIsOpen(!isOpen)}
        className="text-[9px] font-bold text-gray-700 uppercase tracking-[0.16em] pb-1.5 border-b border-[#1e1e1e] cursor-pointer hover:text-gray-500 transition-colors flex justify-between items-center"
      >
        {title}
        <span className="text-[10px] transform transition-transform duration-200" style={{ rotate: isOpen ? '0deg' : '-90deg' }}>▼</span>
      </h3>
      {isOpen && children}
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
  const id = label.toLowerCase().replace(/\s+/g, '-');

  useEffect(() => {
    setLocalVal(val.toString());
  }, [val]);

  const flush = () => {
    const parsed = parseFloat(localVal);
    if (!isNaN(parsed)) {
      onChange(parsed);
    } else {
      setLocalVal(val.toString());
    }
  };

  return (
    <div className="flex justify-between items-center gap-2">
      <label htmlFor={id} className="text-[11px] text-gray-500 flex-1 min-w-0 leading-tight cursor-pointer hover:text-gray-300 transition-colors">{label}</label>
      <div className="relative shrink-0">
        <input
          id={id}
          type="number" step={step} value={localVal} min={min}
          onChange={(e) => setLocalVal(e.target.value)}
          onBlur={flush}
          onKeyDown={(e) => e.key === "Enter" && flush()}
          className={`bg-[#0d0d0d] border text-[11px] rounded-lg px-2 py-1.5 text-white w-28 text-right pr-9 focus:outline-none transition-all ${
            hasError ? "border-red-500/50 focus:border-red-500 focus:ring-1 focus:ring-red-500/50 text-red-100" : "border-[#252525] focus:border-ansys-yellow/60 focus:ring-1 focus:ring-ansys-yellow/50"
          }`}
        />
        <span className={`absolute right-2 top-1/2 -translate-y-1/2 text-[9px] pointer-events-none ${hasError ? "text-red-500/70" : "text-gray-700"}`}>
          {unit}
        </span>
      </div>
    </div>
  );
}
