"use client";
import { useState, useCallback } from "react";
import { Upload, FileText, AlertCircle, CheckCircle2, X } from "lucide-react";

interface ParsedProfile {
  time: number[];
  displacement: number[];
  duration: number;
  sampleRate: number;
  pointCount: number;
  fileName: string;
}

interface RoadProfileUploadProps {
  onLoad: (profile: ParsedProfile) => void;
  onClear: () => void;
  loaded: ParsedProfile | null;
}

function parseCSV(text: string): { time: number[]; displacement: number[] } {
  const lines = text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#") && !l.match(/^[a-z]/i)); // skip header rows

  const time: number[] = [];
  const displacement: number[] = [];

  for (const line of lines) {
    const cols = line.split(/[\t,;]+/);
    if (cols.length < 2) continue;
    const t = parseFloat(cols[0]);
    const d = parseFloat(cols[1]);
    if (!isNaN(t) && !isNaN(d)) {
      time.push(t);
      displacement.push(d);
    }
  }
  if (time.length < 10) throw new Error("File must have at least 10 data rows (time, displacement).");
  return { time, displacement };
}

export default function RoadProfileUpload({ onLoad, onClear, loaded }: RoadProfileUploadProps) {
  const [dragging, setDragging] = useState(false);
  const [error,    setError]    = useState<string | null>(null);

  const handleFile = useCallback(async (file: File) => {
    setError(null);
    if (!file.name.match(/\.(csv|txt|dat)$/i)) {
      setError("Unsupported format. Please upload a .csv, .txt, or .dat file.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setError("File too large. Maximum 5 MB.");
      return;
    }
    try {
      const text = await file.text();
      const { time, displacement } = parseCSV(text);
      const duration   = time[time.length - 1] - time[0];
      const sampleRate = time.length / duration;
      onLoad({ time, displacement, duration, sampleRate, pointCount: time.length, fileName: file.name });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to parse file.");
    }
  }, [onLoad]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  if (loaded) {
    return (
      <div className="bg-[#0a1a0a] border border-emerald-900/40 rounded-xl p-3 flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          <CheckCircle2 size={14} className="text-emerald-500 mt-0.5 shrink-0" />
          <div className="min-w-0">
            <p className="text-xs font-semibold text-emerald-400 truncate">{loaded.fileName}</p>
            <p className="text-[10px] text-gray-600 mt-0.5">
              {loaded.pointCount.toLocaleString()} pts · {loaded.duration.toFixed(2)} s ·{" "}
              {loaded.sampleRate.toFixed(0)} Hz
            </p>
          </div>
        </div>
        <button onClick={onClear} className="text-gray-600 hover:text-red-400 shrink-0 transition-colors">
          <X size={13} />
        </button>
      </div>
    );
  }

  return (
    <div>
      <label
        htmlFor="road-csv-upload"
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center justify-center gap-2 p-4 rounded-xl border-2 border-dashed
          cursor-pointer transition-all ${
          dragging
            ? "border-ansys-yellow/60 bg-ansys-yellow/5"
            : "border-[#252525] hover:border-[#3a3a3a] bg-[#0d0d0f]"
        }`}
      >
        <Upload size={20} className={dragging ? "text-ansys-yellow" : "text-gray-700"} />
        <div className="text-center">
          <p className="text-xs font-medium text-gray-400">Drop road profile here</p>
          <p className="text-[10px] text-gray-700 mt-0.5">CSV · TXT · DAT — two columns: time (s), displacement (m)</p>
        </div>
        <span className="text-[10px] text-ansys-yellow font-semibold">Browse file</span>
        <input id="road-csv-upload" type="file" accept=".csv,.txt,.dat" className="sr-only"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
      </label>

      {error && (
        <div className="mt-2 flex items-center gap-1.5 text-[10px] text-red-400">
          <AlertCircle size={11} /> {error}
        </div>
      )}

      <div className="mt-2">
        <p className="text-[9px] text-gray-700 mb-1.5 font-bold uppercase tracking-widest">Expected format:</p>
        <div className="bg-black/60 rounded-lg px-3 py-2 font-mono text-[9px] text-gray-600 border border-[#1a1a1a]">
          # time(s), displacement(m)<br/>
          0.000, 0.000<br/>
          0.001, 0.000<br/>
          0.050, 0.048<br/>
          ...
        </div>
      </div>
    </div>
  );
}
