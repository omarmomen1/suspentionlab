"use client";
import { useState, useCallback } from "react";
import { Download, Loader2, FileCode2 } from "lucide-react";

interface DataExportProps {
  results: Record<string, unknown> | null;
  fileName?: string;
  className?: string;
}

export default function DataExport({ results, fileName = "suspensionlab_export", className = "" }: DataExportProps) {
  const [exporting, setExporting] = useState(false);

  const handleExport = useCallback(() => {
    if (!results) return;
    setExporting(true);
    
    try {
      let mScript = `% SuspensionLab Simulation Export\n`;
      mScript += `% Generated on: ${new Date().toISOString()}\n\n`;
      
      const arrays: Record<string, number[]> = {};
      const scalars: Record<string, number | string> = {};

      // Parse results into arrays and scalars
      for (const [key, value] of Object.entries(results)) {
        if (Array.isArray(value) && value.length > 0 && typeof value[0] === "number") {
          arrays[key] = value as number[];
        } else if (typeof value === "number" || typeof value === "string") {
          scalars[key] = value;
        }
      }

      // Write scalars
      mScript += `% --- Parameters & KPIs ---\n`;
      for (const [key, value] of Object.entries(scalars)) {
        if (typeof value === "string") {
          mScript += `${key} = '${value.replace(/'/g, "''")}';\n`;
        } else {
          mScript += `${key} = ${value};\n`;
        }
      }
      mScript += `\n`;

      // Write arrays
      mScript += `% --- Time Series & Arrays ---\n`;
      for (const [key, value] of Object.entries(arrays)) {
        // Format array as MATLAB vector: [v1, v2, v3, ...]
        mScript += `${key} = [`;
        mScript += value.map(v => Number.isFinite(v) ? v.toString() : "NaN").join(", ");
        mScript += `];\n`;
      }
      mScript += `\n`;

      // Add basic plotting if time exists
      if (arrays["time"]) {
        mScript += `% --- Basic Visualization ---\n`;
        mScript += `figure('Name', 'SuspensionLab Results', 'Color', 'w');\n`;
        
        const yVars = ["z_s", "ddz_s", "susp_travel", "a_y", "yaw_rate"];
        const toPlot = yVars.filter(v => arrays[v]);
        
        if (toPlot.length > 0) {
          toPlot.forEach((v, idx) => {
            mScript += `subplot(${toPlot.length}, 1, ${idx + 1});\n`;
            mScript += `plot(time, ${v}, 'LineWidth', 1.5);\n`;
            mScript += `grid on;\n`;
            mScript += `ylabel('${v.replace(/_/g, "\\_")}');\n`;
            if (idx === toPlot.length - 1) mScript += `xlabel('Time (s)');\n`;
          });
        }
      }

      // Trigger download
      const blob = new Blob([mScript], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${fileName}.m`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export failed:", err);
      alert("Failed to generate MATLAB script.");
    } finally {
      setExporting(false);
    }
  }, [results, fileName]);

  return (
    <button onClick={handleExport} disabled={exporting || !results}
      className={`flex items-center gap-1.5 px-3 py-1.5 bg-[#141416] border border-[#252525]
        hover:bg-[#1e1e20] rounded-lg text-xs font-medium transition-colors disabled:opacity-40 ${className}`}>
      {exporting
        ? <><Loader2 size={13} className="animate-spin" /> Generating .m…</>
        : <><FileCode2 size={13} /> Export MATLAB</>}
    </button>
  );
}
