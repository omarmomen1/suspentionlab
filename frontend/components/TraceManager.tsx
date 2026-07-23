"use client";
import { useState } from "react";
import { SplitSquareHorizontal, X, Eye, EyeOff, Trash2 } from "lucide-react";

export interface Trace {
  id: string;
  name: string;
  color: string;
  visible: boolean;
  params: Record<string, any>;
  data: any;
}

interface TraceManagerProps {
  currentResult: any | null;
  currentParams: Record<string, any>;
  traces: Trace[];
  setTraces: React.Dispatch<React.SetStateAction<Trace[]>>;
  deltaMode: boolean;
  setDeltaMode: React.Dispatch<React.SetStateAction<boolean>>;
}

const TRACE_COLORS = ["#00aeff", "#ff3366", "#00ffcc", "#cc66ff", "#ff9900", "#33cc33"];

export default function TraceManager({ currentResult, currentParams, traces, setTraces, deltaMode, setDeltaMode }: TraceManagerProps) {
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");

  const pinCurrent = () => {
    if (!currentResult) return;
    const color = TRACE_COLORS[traces.length % TRACE_COLORS.length];
    const newTrace: Trace = {
      id: Math.random().toString(36).substring(2, 9),
      name: `Run ${traces.length + 1}`,
      color,
      visible: true,
      params: { ...currentParams },
      data: currentResult,
    };
    setTraces([...traces, newTrace]);
  };

  const toggleVisibility = (id: string) => {
    setTraces(traces.map(t => t.id === id ? { ...t, visible: !t.visible } : t));
  };

  const deleteTrace = (id: string) => {
    setTraces(traces.filter(t => t.id !== id));
  };

  const startEditing = (trace: Trace) => {
    setEditingId(trace.id);
    setEditName(trace.name);
  };

  const saveName = (id: string) => {
    setTraces(traces.map(t => t.id === id ? { ...t, name: editName || t.name } : t));
    setEditingId(null);
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-[#141416] border border-[#252525]
          hover:bg-[#1e1e20] rounded-lg text-xs font-medium transition-colors">
        <SplitSquareHorizontal size={13} className="text-[#0af]" />
        Traces {traces.length > 0 && <span className="ml-1 bg-[#0af]/20 text-[#0af] px-1.5 py-0.5 rounded-full text-[9px] font-bold">{traces.length}</span>}
      </button>
    );
  }

  const renderDelta = (current: number | undefined, pinned: number | undefined) => {
    if (current === undefined || pinned === undefined) return null;
    const diff = current - pinned;
    const pct = pinned !== 0 ? (diff / Math.abs(pinned)) * 100 : 0;
    const better = diff < 0; // lower is better for our KPIs
    if (Math.abs(pct) < 0.1) return <span className="text-gray-600 ml-1">(=)</span>;
    return (
      <span className={`ml-1 text-[9px] font-bold ${better ? 'text-emerald-400' : 'text-red-400'}`}>
        {diff > 0 ? '+' : ''}{pct.toFixed(1)}%
      </span>
    );
  };

  const exportAllTraces = () => {
    const dataObj: any = { current: { params: currentParams, results: currentResult } };
    traces.forEach((t, i) => { dataObj[`Trace_${i+1}_${t.name}`] = { params: t.params, results: t.data }; });
    const blob = new Blob([JSON.stringify(dataObj, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `qcar_multirun_export_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-full sm:w-[320px] bg-[#0a0a0c] border-l border-[#1e1e1e]
      flex flex-col shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-[#1e1e1e] shrink-0">
        <div className="flex items-center gap-2">
          <SplitSquareHorizontal size={14} className="text-[#0af]" />
          <span className="text-sm font-semibold text-white">Trace Manager</span>
        </div>
        <button onClick={() => setOpen(false)} className="text-gray-600 hover:text-white transition-colors">
          <X size={14} />
        </button>
      </div>

      <div className="p-4 border-b border-[#1e1e1e] shrink-0 flex flex-col gap-2">
        <button onClick={pinCurrent} disabled={!currentResult}
          className="w-full px-4 py-2 bg-[#0af]/10 border border-[#0af]/20 text-[#0af] text-xs font-bold
            rounded-lg hover:bg-[#0af]/20 transition-colors disabled:opacity-40">
          📌 Pin Current Run
        </button>
        <div className="flex gap-2">
          <button onClick={() => setDeltaMode(!deltaMode)} disabled={traces.length === 0}
            className={`flex-1 px-3 py-1.5 border text-xs font-bold rounded-lg transition-colors disabled:opacity-40
              ${deltaMode ? 'bg-[#ff3366]/20 border-[#ff3366]/30 text-[#ff3366]' : 'bg-[#141416] border-[#252525] text-gray-300 hover:text-white'}`}>
            {deltaMode ? 'Δ Curves Active' : 'Show Δ Curves'}
          </button>
          <button onClick={exportAllTraces} disabled={!currentResult && traces.length === 0}
            className="px-3 py-1.5 bg-[#141416] border border-[#252525] text-gray-300 text-xs font-bold
              rounded-lg hover:text-white transition-colors disabled:opacity-40" title="Export All Traces JSON">
            Export
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {traces.length === 0 && (
          <p className="text-xs text-gray-600 text-center mt-4">No pinned traces yet.</p>
        )}
        
        {traces.map(t => (
          <div key={t.id} className="bg-[#141416] border border-[#252525] rounded-xl p-3 flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2 border-b border-[#1e1e1e] pb-2">
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: t.color }} />
                {editingId === t.id ? (
                  <input
                    autoFocus
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    onBlur={() => saveName(t.id)}
                    onKeyDown={(e) => e.key === "Enter" && saveName(t.id)}
                    className="bg-[#0d0d0f] border border-[#2a2a2a] rounded px-1.5 py-0.5 text-xs text-white w-full focus:outline-none focus:border-[#0af]"
                  />
                ) : (
                  <span className="text-xs font-semibold text-gray-300 truncate cursor-pointer hover:text-white transition-colors" onClick={() => startEditing(t)}>
                    {t.name}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 shrink-0 text-gray-500">
                <button onClick={() => toggleVisibility(t.id)} className="p-1 hover:text-white transition-colors">
                  {t.visible ? <Eye size={12} /> : <EyeOff size={12} />}
                </button>
                <button onClick={() => deleteTrace(t.id)} className="p-1 hover:text-red-400 transition-colors">
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
            
            <div className="text-[10px] text-gray-500 font-mono grid grid-cols-2 gap-x-2 gap-y-1 mt-1">
              <span className="col-span-2 text-[#0af] font-bold mb-1">Δ Current vs This Run</span>
              <div className="flex items-center justify-between">
                <span>Accel:</span>
                <span>{renderDelta(currentResult?.rms_body_accel, t.data?.rms_body_accel)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Travel:</span>
                <span>{renderDelta(currentResult?.rms_susp_travel, t.data?.rms_susp_travel)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Tire Ld:</span>
                <span>{renderDelta(currentResult?.rms_tire_load, t.data?.rms_tire_load)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Transm:</span>
                <span>{renderDelta(currentResult?.peak_transmissibility, t.data?.peak_transmissibility)}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
