"use client";
import { useState, useCallback } from "react";
import { Upload, AlertCircle, CheckCircle2, X } from "lucide-react";

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
  // Strip UTF-8 BOM if present
  const cleanText = text.replace(/^\uFEFF/, "");
  const lines = cleanText
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));

  if (lines.length === 0) {
    throw new Error("Uploaded file is empty.");
  }

  // Detect header row and column aliases
  const timeAliases = ["time", "t", "time_s", "timestamp", "sec", "seconds", "elapsed_time", "t_s"];
  const dispAliases = [
    "displacement", "disp", "z_r", "z_road", "road_z", "elevation",
    "profile", "height", "elevation_m", "displacement_m", "z_profile", "road_displacement"
  ];

  let headerIndex = -1;
  let timeCol = 0;
  let dispCol = 1;

  for (let i = 0; i < Math.min(lines.length, 5); i++) {
    const rawCols = lines[i].split(/[\t,;]+/).map((c) => c.trim().toLowerCase().replace(/[^a-z0-9_]+/g, ""));
    const tIdx = rawCols.findIndex((c) => timeAliases.includes(c) || c.startsWith("time"));
    const dIdx = rawCols.findIndex((c) => dispAliases.includes(c) || c.includes("disp") || c.includes("elev") || c.includes("height"));

    if (tIdx !== -1 && dIdx !== -1 && tIdx !== dIdx) {
      headerIndex = i;
      timeCol = tIdx;
      dispCol = dIdx;
      break;
    }
  }

  const dataLines = headerIndex !== -1 ? lines.slice(headerIndex + 1) : lines;
  const time: number[] = [];
  const displacement: number[] = [];

  for (const line of dataLines) {
    const cols = line.split(/[\t,;]+/);
    if (cols.length <= Math.max(timeCol, dispCol)) continue;
    const tStr = cols[timeCol]?.trim() ?? "";
    const dStr = cols[dispCol]?.trim() ?? "";
    if (tStr === "" || dStr === "") continue;

    const t = parseFloat(tStr);
    const d = parseFloat(dStr);
    if (Number.isFinite(t) && Number.isFinite(d)) {
      time.push(t);
      displacement.push(d);
    }
  }

  if (time.length < 10) {
    throw new Error(
      "Unable to map required columns. Please ensure CSV contains 'time' (s) and 'displacement' (m) columns (or at least 10 valid numeric rows)."
    );
  }
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
      const duration   = Math.max(0.001, time[time.length - 1] - time[0]);
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
            <p className="text-xs text-gray-400 mt-0.5">
              {loaded.pointCount.toLocaleString()} pts · {loaded.duration.toFixed(2)} s ·{" "}
              {loaded.sampleRate.toFixed(0)} Hz
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClear}
          aria-label="Remove loaded road profile"
          className="text-gray-400 hover:text-red-400 shrink-0 transition-colors p-1"
        >
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
            ? "border-signal/60 bg-signal/5"
            : "border-[#252525] hover:border-[#3a3a3a] bg-[#0d0d0f]"
        }`}
      >
        <Upload size={20} className={dragging ? "text-signal" : "text-gray-400"} />
        <div className="text-center">
          <p className="text-xs font-medium text-gray-300">Drop road profile here</p>
          <p className="text-xs text-gray-400 mt-0.5">CSV · TXT · DAT — two columns: time (s), displacement (m)</p>
        </div>
        <span className="text-xs text-signal font-semibold">Browse file</span>
        <input id="road-csv-upload" type="file" accept=".csv,.txt,.dat" className="sr-only"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
      </label>

      {error && (
        <div role="alert" aria-live="polite" className="mt-2 flex items-center gap-1.5 text-xs text-red-400">
          <AlertCircle size={11} /> {error}
        </div>
      )}

      <div className="mt-2">
        <p className="text-xs text-gray-400 mb-1.5 font-bold uppercase tracking-widest">Expected format:</p>
        <div className="bg-black/60 rounded-lg px-3 py-2 font-mono text-xs text-gray-300 border border-[#1a1a1a]">
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
