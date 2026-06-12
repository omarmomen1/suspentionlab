"use client";
import { useRef, useState } from "react";
import { Upload, Activity, Check, X } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";

interface TelemetryUploaderProps {
  onParsed: (data: Record<string, unknown>) => void;
  onClear: () => void;
  hasData: boolean;
}

export default function TelemetryUploader({ onParsed, onClear, hasData }: TelemetryUploaderProps) {
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { authHeader } = useAuth();

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    setIsUploading(true);
    const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const formData = new FormData();
    formData.append("file", file);

    const headers = { ...authHeader() } as Record<string, string>;
    delete headers["Content-Type"];

    try {
      const res = await fetch(`${API_BASE}/parse-telemetry`, {
        method: "POST",
        headers,
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        onParsed(data);
      } else {
        alert("Failed to parse Telemetry file.");
      }
    } catch (err) {
      alert("Network error parsing Telemetry file.");
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div className="flex flex-col gap-1.5 mt-2 p-2 bg-[#0d0d0f] border border-[#252525] rounded-lg">
      <div className="flex justify-between items-center">
        <label className="text-[11px] text-gray-400 flex items-center gap-1.5 font-semibold">
          <Activity size={12} className={hasData ? "text-blue-400" : "text-gray-500"} />
          Telemetry Overlay (CSV)
          {hasData && <Check size={10} className="text-blue-400" />}
        </label>
        
        {hasData ? (
          <button onClick={onClear}
            className="text-[10px] bg-red-950/30 text-red-400 border border-red-900/40 px-2 py-0.5 rounded flex items-center gap-1 hover:bg-red-900/50 transition-colors">
            <X size={10} /> Clear
          </button>
        ) : (
          <button onClick={() => fileInputRef.current?.click()} disabled={isUploading}
            className="text-[10px] bg-ansys-yellow text-black px-2 py-0.5 rounded flex items-center gap-1 font-bold hover:brightness-110 disabled:opacity-50 transition-all shadow-[0_0_10px_rgba(242,169,0,0.2)]">
            {isUploading ? "..." : <><Upload size={10} /> Upload</>}
          </button>
        )}
      </div>
      
      <input type="file" accept=".csv" ref={fileInputRef} className="hidden" onChange={handleUpload} />
      
      {hasData ? (
        <p className="text-[9px] text-blue-500/70 leading-tight">
          MoTeC/AiM telemetry loaded. View in plots.
        </p>
      ) : (
        <p className="text-[9px] text-gray-600 leading-tight">
          Upload a MoTeC or AiM CSV file to correlate real-world data with the simulation.
        </p>
      )}
    </div>
  );
}
