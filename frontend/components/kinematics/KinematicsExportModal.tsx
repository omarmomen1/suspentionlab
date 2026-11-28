"use client";

import React, { useState } from "react";
import { Download, FileText, Code2, X, CheckCircle2 } from "lucide-react";
import { KinematicsApi } from "../../lib/api_client";
import PlanGate from "../PlanGate";

interface KinematicsExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  hardpoints: Record<string, number[]>;
  sweepData?: any;
  setupName: string;
  zMin: number;
  zMax: number;
  nSteps: number;
}

export default function KinematicsExportModal({
  isOpen,
  onClose,
  hardpoints,
  sweepData,
  setupName,
  zMin,
  zMax,
  nSteps,
}: KinematicsExportModalProps) {
  const [downloadingCsv, setDownloadingCsv] = useState(false);
  const [downloadingJson, setDownloadingJson] = useState(false);
  const [lastExport, setLastExport] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleExportCsv = async () => {
    try {
      setDownloadingCsv(true);
      const blob = await KinematicsApi.exportCsv({
        sweep_data: sweepData ?? undefined,
        hardpoints,
        format: "csv",
        setup_name: setupName,
        z_min_mm: zMin,
        z_max_mm: zMax,
        n_steps: nSteps,
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `kinematics_sweep_${setupName.toLowerCase().replace(/\s+/g, "_")}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      setLastExport("CSV exported successfully");
    } catch (err: any) {
      console.error("Export CSV failed:", err);
      setLastExport(`Export failed: ${err.message || "Unknown error"}`);
    } finally {
      setDownloadingCsv(false);
    }
  };

  const handleExportJson = async () => {
    try {
      setDownloadingJson(true);
      const blob = await KinematicsApi.exportJson({
        sweep_data: sweepData ?? undefined,
        hardpoints,
        format: "json",
        setup_name: setupName,
        z_min_mm: zMin,
        z_max_mm: zMax,
        n_steps: nSteps,
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `kinematics_sweep_${setupName.toLowerCase().replace(/\s+/g, "_")}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      setLastExport("JSON exported successfully");
    } catch (err: any) {
      console.error("Export JSON failed:", err);
      setLastExport(`Export failed: ${err.message || "Unknown error"}`);
    } finally {
      setDownloadingJson(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
      <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-md w-full p-6 shadow-2xl flex flex-col gap-5 text-slate-200">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2 text-indigo-400 font-semibold text-base">
            <Download className="w-5 h-5" />
            <span>Export Kinematic Sweep Data</span>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="text-xs text-slate-400 space-y-2">
          <p>
            Export complete high-resolution kinematic sweep dataset for <strong>{setupName}</strong>.
          </p>
          <div className="p-3 bg-slate-800/60 rounded-lg border border-slate-700/60 font-mono text-xs text-slate-300 space-y-1">
            <div>• Travel Range: [{zMin} mm, {zMax} mm] ({nSteps} points)</div>
            <div>• Quantities: Camber, Toe, Roll Center (Z & Y), Track, KPI, Caster, MR</div>
            <div>• Derivatives: Camber Gain (°/100mm & °/m), Toe Gain, RC Migration Rate</div>
            <div>• Metadata: Hardpoint coordinates, solver version, SHA-256 geometry hash</div>
          </div>
        </div>

        {lastExport && (
          <div className="flex items-center gap-2 text-xs text-emerald-400 bg-emerald-950/30 p-2.5 rounded border border-emerald-800/40">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>{lastExport}</span>
          </div>
        )}

        <PlanGate required="PRO" feature="Kinematics CSV & JSON Export">
          <div className="grid grid-cols-2 gap-3 pt-1">
            <button
              onClick={handleExportCsv}
              disabled={downloadingCsv}
              className="flex flex-col items-center justify-center gap-2 p-4 rounded-xl bg-slate-800 hover:bg-slate-750 border border-slate-700 hover:border-indigo-500/50 transition group disabled:opacity-50"
            >
              <FileText className="w-6 h-6 text-indigo-400 group-hover:scale-110 transition" />
              <div className="text-center">
                <div className="text-xs font-semibold text-slate-200">
                  {downloadingCsv ? "Generating..." : "Download CSV"}
                </div>
                <div className="text-xs text-slate-400">Excel / MATLAB / MoTeC</div>
              </div>
            </button>

            <button
              onClick={handleExportJson}
              disabled={downloadingJson}
              className="flex flex-col items-center justify-center gap-2 p-4 rounded-xl bg-slate-800 hover:bg-slate-750 border border-slate-700 hover:border-indigo-500/50 transition group disabled:opacity-50"
            >
              <Code2 className="w-6 h-6 text-emerald-400 group-hover:scale-110 transition" />
              <div className="text-center">
                <div className="text-xs font-semibold text-slate-200">
                  {downloadingJson ? "Generating..." : "Download JSON"}
                </div>
                <div className="text-xs text-slate-400">CAE / Python / REST API</div>
              </div>
            </button>
          </div>
        </PlanGate>

        <div className="flex justify-end pt-2 border-t border-slate-800">
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-xs text-slate-300 hover:bg-slate-800 rounded-lg transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
