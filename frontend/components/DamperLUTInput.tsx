"use client";
import { useState, useRef } from "react";
import { Upload, X, Check, BarChart2 } from "lucide-react";

interface DamperLUTInputProps {
  label: string;
  onApply: (v: number[], f: number[]) => void;
  onClear: () => void;
  isActive: boolean;
}

export default function DamperLUTInput({ label, onApply, onClear, isActive }: DamperLUTInputProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [csvText, setCsvText] = useState("");
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const parseAndApply = (text: string) => {
    try {
      const lines = text.split("\n").map(l => l.trim()).filter(l => l.length > 0);
      if (lines.length < 2) throw new Error("At least 2 rows required.");

      const v: number[] = [];
      const f: number[] = [];

      
      lines.forEach((line, i) => {
        const parts = line.split(/[,\t\s]+/).map(p => p.trim());
        if (parts.length < 2) return;
        if (parts[0] === "" || parts[1] === "") return;
        
        const vVal = Number(parts[0]);
        const fVal = Number(parts[1]);

        if (i === 0 && (isNaN(vVal) || isNaN(fVal))) {
          
          return;
        }

        if (!Number.isFinite(vVal) || !Number.isFinite(fVal)) throw new Error(`Invalid number on row ${i + 1}`);
        v.push(vVal);
        f.push(fVal);
      });

      if (v.length < 2) throw new Error("Could not parse data points.");

      // Ensure monotonically increasing velocity
      for (let i = 1; i < v.length; i++) {
        if (v[i] <= v[i - 1]) throw new Error("Velocities must be monotonically increasing (sort your data).");
      }

      // Check passivity (warning if damping force opposes standard dissipation quadrant)
      let nonPassivePoints = 0;
      for (let i = 0; i < v.length; i++) {
        if ((v[i] > 0.01 && f[i] < -10) || (v[i] < -0.01 && f[i] > 10)) {
          nonPassivePoints++;
        }
      }
      if (nonPassivePoints > 0) {
        // We still allow it with a soft warning or proceed
        console.warn(`Damper LUT contains ${nonPassivePoints} non-dissipative points.`);
      }

      onApply(v, f);
      setError("");
      setIsOpen(false);
    } catch (err: unknown) {
      setError((err as Error).message || "Failed to parse CSV.");
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setError("File size exceeds 5MB limit.");
      return;
    }
    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      setCsvText(text);
      parseAndApply(text);
    };
    reader.readAsText(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between items-center gap-2">
        <label className="text-[11px] text-gray-400 flex-1 min-w-0 leading-tight flex items-center gap-1.5">
          {label}
          {isActive && <Check size={10} className="text-emerald-400" />}
        </label>
        
        {isActive ? (
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] font-mono text-emerald-400/80 bg-emerald-950/40 px-1.5 py-0.5 rounded border border-emerald-800/40">
              Active
            </span>
            <button
              type="button"
              onClick={onClear}
              aria-label={`Clear ${label} look up table`}
              className="text-[10px] bg-red-950/30 text-red-400 border border-red-900/40 px-2 py-0.5 rounded flex items-center gap-1 hover:bg-red-900/50 transition-colors"
            >
              <X size={10} /> Clear
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setIsOpen(!isOpen)}
            aria-expanded={isOpen}
            aria-label={`Add ${label} look up table`}
            className="text-[10px] bg-[#1e1e20] text-gray-300 border border-[#2a2a2a] px-2 py-0.5 rounded flex items-center gap-1 hover:border-ansys-yellow hover:text-ansys-yellow transition-colors"
          >
            <BarChart2 size={10} /> Add LUT
          </button>
        )}
      </div>

      {isOpen && !isActive && (
        <div className="bg-[#0d0d0f] border border-[#252525] rounded-lg p-2.5 mt-1 space-y-2 animate-in fade-in slide-in-from-top-1">
          <div className="flex justify-between items-center">
            <span className="text-[9px] font-mono text-gray-400 uppercase tracking-widest">CSV (Velocity, Force)</span>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              aria-label="Upload CSV file for Damper LUT"
              className="text-[10px] text-ansys-yellow flex items-center gap-1 hover:underline"
            >
              <Upload size={10} /> Upload .csv
            </button>
            <input type="file" accept=".csv,.txt" ref={fileInputRef} className="hidden" aria-label="Upload CSV file" onChange={handleFileUpload} />
          </div>
          <label htmlFor="damper-lut-textarea" className="sr-only">Damper Look-Up Table CSV data</label>
          <textarea
            id="damper-lut-textarea"
            value={csvText}
            onChange={(e) => setCsvText(e.target.value)}
            placeholder={"-1.5, -4000\n-1.0, -3000\n0.0, 0\n1.0, 3000\n1.5, 4000"}
            className="w-full h-24 bg-[#141416] border border-[#1e1e1e] rounded p-2 text-[10px] font-mono text-gray-300 focus:outline-none focus:border-ansys-yellow/50"
          />
          {error && <p role="alert" aria-live="polite" className="text-[10px] text-red-400 font-medium leading-tight">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={() => setIsOpen(false)} className="text-[10px] text-gray-400 hover:text-gray-200">Cancel</button>
            <button
              type="button"
              onClick={() => parseAndApply(csvText)}
              className="text-[10px] bg-ansys-yellow text-black px-2 py-0.5 rounded font-bold hover:brightness-110"
            >
              Apply Curve
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
