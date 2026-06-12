"use client";
import { useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import PlanGate from "./PlanGate";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface CAEExportProps {
  params: Record<string, any>;
  vehicleType: "QUARTER_CAR" | "FULL_CAR";
}

export default function CAEExport({ params, vehicleType }: CAEExportProps) {
  const { authHeader } = useAuth();
  const [isExporting, setIsExporting] = useState<"simulink" | "adams" | null>(null);
  const [showMenu, setShowMenu] = useState(false);

  // We only support full-car for now based on backend
  if (vehicleType !== "FULL_CAR") return null;

  const handleExport = async (format: "simulink" | "adams") => {
    setIsExporting(format);
    setShowMenu(false);
    try {
      const b = params.L * (params.weight_dist / 100.0);
      const a = params.L - b;
      
      const payload = {
        params: {
          m_s: params.m_s, I_x: params.I_x, I_y: params.I_y, 
          m_uf: params.m_uf, m_ur: params.m_ur, 
          k_sf: params.k_sf, k_sr: params.k_sr, 
          c_f: params.c_f, c_r: params.c_r, 
          k_arb_f: params.k_arb_f, k_arb_r: params.k_arb_r, 
          k_tf: 250000.0, k_tr: 250000.0, 
          L: params.L, a, b, 
          tw_f: params.tw_f, tw_r: params.tw_r, 
          speed_mps: params.speed_kph / 3.6, 
          c_tf: 0.0, c_tr: 0.0
        }
      };

      const res = await fetch(`${API_BASE}/export/${format}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeader(),
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error(`Failed to export ${format}`);

      const content = await res.text();
      const ext = format === "simulink" ? "m" : "adm";
      
      const blob = new Blob([content], { type: "text/plain" });
      const url = window.URL.createObjectURL(blob);
      const a_tag = document.createElement("a");
      a_tag.href = url;
      a_tag.download = `SuspensionLab_FullCar_${Math.round(params.m_s)}.${ext}`;
      document.body.appendChild(a_tag);
      a_tag.click();
      document.body.removeChild(a_tag);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
      alert(`Failed to export ${format}.`);
    } finally {
      setIsExporting(null);
    }
  };

  return (
    <PlanGate required="ENTERPRISE">
      <div className="relative">
        <button
          onClick={() => setShowMenu(!showMenu)}
          disabled={isExporting !== null}
          className="px-3 py-1.5 bg-[#141416] border border-[#252525] hover:bg-[#1e1e20] hover:border-[#00aeff]/50 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-40"
        >
          {isExporting ? (
            <Loader2 size={13} className="text-[#00aeff] animate-spin" />
          ) : (
            <Download size={13} className="text-[#00aeff]" />
          )}
          CAE Export
        </button>

        {showMenu && (
          <>
            <div 
              className="fixed inset-0 z-40" 
              onClick={() => setShowMenu(false)} 
            />
            <div className="absolute right-0 mt-2 w-48 bg-[#0d0d0f] border border-[#1e1e1e] rounded-xl shadow-2xl py-1.5 z-50 overflow-hidden">
              <button
                onClick={() => handleExport("simulink")}
                className="w-full text-left px-3 py-2 text-[11px] text-gray-300 hover:bg-[#1a1a1c] hover:text-[#f2a900] transition-colors flex items-center gap-2"
              >
                Simulink State-Space (.m)
              </button>
              <button
                onClick={() => handleExport("adams")}
                className="w-full text-left px-3 py-2 text-[11px] text-gray-300 hover:bg-[#1a1a1c] hover:text-[#ff2d55] transition-colors flex items-center gap-2"
              >
                MSC ADAMS Solver (.adm)
              </button>
            </div>
          </>
        )}
      </div>
    </PlanGate>
  );
}
