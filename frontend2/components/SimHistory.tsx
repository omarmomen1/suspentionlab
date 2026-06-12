"use client";
import { useState, useEffect } from "react";
import { History, ChevronRight, Clock, X } from "lucide-react";

interface HistoryEntry {
  id: string;
  timestamp: number;
  label: string;
  params: Record<string, any>;
  metrics: {
    rms_body_accel: number;
    peak_transmissibility: number;
    peak_susp_travel: number;
    f_n_s: number;
    zeta_s: number;
  };
}

const STORAGE_KEY = "sl_sim_history";
const MAX_ENTRIES = 20;

export function saveSimulationToHistory(
  params: Record<string, any>,
  results: Record<string, unknown>,
  label?: string,
) {
  const entry: HistoryEntry = {
    id:        `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    timestamp: Date.now(),
    label:     label || new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }),
    params,
    metrics: {
      rms_body_accel:       (results.rms_body_accel as number) ?? 0,
      peak_transmissibility:(results.peak_transmissibility as number) ?? 0,
      peak_susp_travel:     (results.peak_susp_travel as number) ?? 0,
      f_n_s:                (results.f_n_s as number) ?? 0,
      zeta_s:               (results.zeta_s as number) ?? 0,
    },
  };
  try {
    const raw      = localStorage.getItem(STORAGE_KEY);
    const existing = raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
    const updated  = [entry, ...existing].slice(0, MAX_ENTRIES);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  } catch {
    // localStorage unavailable (SSR or private mode)
  }
  return entry;
}

interface SimHistoryProps {
  onRestore: (params: Record<string, any>) => void;
}

export default function SimHistory({ onRestore }: SimHistoryProps) {
  const [open,    setOpen]    = useState(false);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    if (!open) return;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      setHistory(raw ? JSON.parse(raw) : []);
    } catch {
      setHistory([]);
    }
  }, [open]);

  const clearHistory = () => {
    localStorage.removeItem(STORAGE_KEY);
    setHistory([]);
  };

  const removeEntry = (id: string) => {
    const updated = history.filter((h) => h.id !== id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    setHistory(updated);
  };

  return (
    <div className="relative">
      <button onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-[#141416] border border-[#252525]
          hover:bg-[#1e1e20] rounded-lg text-xs font-medium transition-colors">
        <History size={13} /> History
        {history.length > 0 && (
          <span className="ml-0.5 text-[9px] font-bold bg-ansys-yellow/20 text-ansys-yellow
            rounded-full px-1.5 min-w-[18px] text-center">
            {history.length}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute top-full mt-2 right-0 z-50 w-[340px] bg-[#0d0d0f] border border-[#252525]
          rounded-xl shadow-2xl overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#1e1e1e]">
            <h3 className="text-xs font-bold text-white">Simulation History</h3>
            <div className="flex items-center gap-3">
              {history.length > 0 && (
                <button onClick={clearHistory} className="text-[10px] text-gray-600 hover:text-red-400 transition-colors">
                  Clear all
                </button>
              )}
              <button onClick={() => setOpen(false)} className="text-gray-600 hover:text-white transition-colors">
                <X size={13} />
              </button>
            </div>
          </div>

          <div className="max-h-[400px] overflow-y-auto custom-scrollbar">
            {history.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 gap-2">
                <Clock size={28} className="text-gray-700" />
                <p className="text-xs text-gray-600">No simulations yet. Run the solver to start building history.</p>
              </div>
            ) : (
              history.map((entry) => (
                <div key={entry.id}
                  className="px-4 py-3 border-b border-[#1a1a1a] flex items-start justify-between gap-2 hover:bg-[#111113]">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 mb-1">
                      <Clock size={10} className="text-gray-700 shrink-0" />
                      <span className="text-[10px] text-gray-500">
                        {new Date(entry.timestamp).toLocaleString("en-GB", {
                          day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
                        })}
                      </span>
                    </div>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-0.5">
                      {[
                        ["ks", entry.params.k_s],
                        ["c",  entry.params.c],
                        ["RMS", entry.metrics.rms_body_accel],
                        ["TX",  entry.metrics.peak_transmissibility],
                        ["ζ",   entry.metrics.zeta_s],
                        ["fₙ",  entry.metrics.f_n_s],
                      ].map(([label, val]) => (
                        <div key={String(label)} className="flex items-center gap-1">
                          <span className="text-[9px] text-gray-700">{label}:</span>
                          <span className="text-[9px] font-mono text-gray-400">
                            {typeof val === "number" ? val.toFixed(2) : val}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <button onClick={() => { onRestore(entry.params); setOpen(false); }}
                      className="flex items-center gap-0.5 text-[10px] text-ansys-yellow hover:text-white
                        font-bold transition-colors">
                      Load <ChevronRight size={11} />
                    </button>
                    <button onClick={() => removeEntry(entry.id)}
                      className="text-[9px] text-gray-700 hover:text-red-400 transition-colors">
                      Remove
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
