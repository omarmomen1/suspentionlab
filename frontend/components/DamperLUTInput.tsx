"use client";
import { useState, useRef } from "react";
import { Upload, X, Check, Activity, BarChart2 } from "lucide-react";

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

      let hasHeader = false;
      lines.forEach((line, i) => {
        const parts = line.split(/[,\t]+/).map(p => p.trim());
        if (parts.length < 2) return;
        
        const vVal = Number(parts[0]);
        const fVal = Number(parts[1]);

        if (i === 0 && (isNaN(vVal) || isNaN(fVal))) {
          hasHeader = true; // Skip header row
          return;
        }

        if (isNaN(vVal) || isNaN(fVal)) throw new Error(`Invalid number on row ${i + 1}`);
        v.push(vVal);
        f.push(fVal);
      });

      if (v.length < 2) throw new Error("Could not parse data points.");

      // Ensure monotonically increasing velocity
      for (let i = 1; i < v.length; i++) {
        if (v[i] <= v[i - 1]) throw new Error("Velocities must be monotonically increasing (sort your data).");
      }

      onApply(v, f);
      setError("");
      setIsOpen(false);
    } catch (err: any) {
      setError(err.message || "Failed to parse CSV.");
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
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
        <label className="text-[11px] text-gray-500 flex-1 min-w-0 leading-tight flex items-center gap-1.5">
          {label}
          {isActive && <Check size={10} className="text-emerald-400" />}
        </label>
        
        {isActive ? (
          <button onClick={onClear}
            className="text-[10px] bg-red-950/30 text-red-400 border border-red-900/40 px-2 py-0.5 rounded flex items-center gap-1 hover:bg-red-900/50 transition-colors">
            <X size={10} /> Clear LUT
          </button>
        ) : (
          <button onClick={() => setIsOpen(!isOpen)}
            className="text-[10px] bg-[#1e1e20] text-gray-300 border border-[#2a2a2a] px-2 py-0.5 rounded flex items-center gap-1 hover:border-ansys-yellow hover:text-ansys-yellow transition-colors">
            <BarChart2 size={10} /> Add LUT
          </button>
        )}
      </div>

      {isOpen && !isActive && (
        <div className="bg-[#0d0d0f] border border-[#252525] rounded-lg p-2.5 mt-1 space-y-2 animate-in fade-in slide-in-from-top-1">
          <div className="flex justify-between items-center">
            <span className="text-[9px] font-mono text-gray-400 uppercase tracking-widest">CSV (Velocity, Force)</span>
            <button onClick={() => fileInputRef.current?.click()}
              className="text-[10px] text-ansys-yellow flex items-center gap-1 hover:underline">
              <Upload size={10} /> Upload .csv
            </button>
            <input type="file" accept=".csv,.txt" ref={fileInputRef} className="hidden" onChange={handleFileUpload} />
          </div>
          <textarea
            value={csvText}
            onChange={(e) => setCsvText(e.target.value)}
            placeholder={"-1.5, -4000\n-1.0, -3000\n0.0, 0\n1.0, 3000\n1.5, 4000"}
            className="w-full h-24 bg-[#141416] border border-[#1e1e1e] rounded p-2 text-[10px] font-mono text-gray-300 focus:outline-none focus:border-ansys-yellow/50"
          />
          {error && <p className="text-[10px] text-red-400 font-medium leading-tight">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <button onClick={() => setIsOpen(false)} className="text-[10px] text-gray-500 hover:text-gray-300">Cancel</button>
            <button onClick={() => parseAndApply(csvText)}
              className="text-[10px] bg-ansys-yellow text-black px-2 py-0.5 rounded font-bold hover:brightness-110">
              Apply Curve
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
