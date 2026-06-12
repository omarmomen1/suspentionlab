"use client";
import { useState } from "react";
import { FileText, Loader2 } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import PlanGate from "./PlanGate";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ISOReportExportProps {
  params: Record<string, any>;
  profile: Record<string, any>;
}

export default function ISOReportExport({ params, profile }: ISOReportExportProps) {
  const { authHeader } = useAuth();
  const [isExporting, setIsExporting] = useState(false);

  const generateReport = async () => {
    setIsExporting(true);
    try {
      const res = await fetch(`${API_BASE}/reports/iso2631`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...authHeader(),
        },
        body: JSON.stringify({ params, profile }),
      });

      if (!res.ok) {
        throw new Error("Failed to generate report");
      }

      const htmlContent = await res.text();
      
      // Trigger download
      const blob = new Blob([htmlContent], { type: "text/html" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ISO_2631_Report_${Math.round(params.k_s)}_${Math.round(params.c)}.html`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
      alert("Failed to generate ISO report.");
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <PlanGate required="ENTERPRISE">
      <button
        onClick={generateReport}
        disabled={isExporting}
        className="px-3 py-1.5 bg-[#141416] border border-[#252525] hover:bg-[#1e1e20] hover:border-emerald-500/50 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-40"
      >
        {isExporting ? (
          <Loader2 size={13} className="text-emerald-400 animate-spin" />
        ) : (
          <FileText size={13} className="text-emerald-400" />
        )}
        ISO Report
      </button>
    </PlanGate>
  );
}
