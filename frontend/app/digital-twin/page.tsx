"use client";

import React, { useState, useRef, useEffect } from "react";
import { useAuth } from "../../contexts/AuthContext";
import GGFrictionCircle from "../../components/GGFrictionCircle";
import TelemetryGauges from "../../components/TelemetryGauges";
import {
  Upload, Activity, CheckCircle, AlertTriangle, XCircle, Zap,
  Clock, Gauge, ChevronRight, BarChart3, Radio, Play, Square,
  FileSpreadsheet
} from "lucide-react";

export default function DigitalTwinPage() {
  const { fetchWithAuth } = useAuth();
  const [activeTab, setActiveTab] = useState<"analysis" | "live">("analysis");

  // Analysis State
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isAnalysing, setIsAnalysing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  // Live State
  const [isLiveActive, setIsLiveActive] = useState(false);
  const [telemetry, setTelemetry] = useState({ speed_ms: 0, lat_g: 0, long_g: 0, steer_rad: 0 });

  // File Upload Handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFile(e.dataTransfer.files[0]);
    }
  };
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
    }
  };

  const handleAnalyse = async () => {
    if (!file) return;
    setIsAnalysing(true);
    setError(null);
    setAnalysisResult(null);

    const formData = new FormData();
    formData.append("file", file);
    // Optional: formData.append("model_params", JSON.stringify({...}));

    try {
      // /telemetry/analyse is an authenticated endpoint (API key or cookie +
      // CSRF double-submit) — route through fetchWithAuth so cookies and the
      // X-CSRF-Token header are attached and 401s trigger token refresh.
      const res = await fetchWithAuth("/api/telemetry/analyse", {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const data = await res.json();
      setAnalysisResult(data);
    } catch (err: any) {
      setError(err.message || "Failed to analyse telemetry");
    } finally {
      setIsAnalysing(false);
    }
  };

  // Live Mock
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isLiveActive) {
      interval = setInterval(() => {
        setTelemetry({
          speed_ms: 15 + Math.random() * 10,
          lat_g: (Math.random() - 0.5) * 2,
          long_g: (Math.random() - 0.5) * 2,
          steer_rad: (Math.random() - 0.5) * 0.5,
        });
      }, 100);
    }
    return () => clearInterval(interval);
  }, [isLiveActive]);

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-slate-200 p-8 font-sans selection:bg-amber-500/30">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-light text-white tracking-tight mb-2">Digital Twin</h1>
          <p className="text-slate-400">Real-time suspension telemetry analysis â€” upload a session to calibrate your model</p>
        </div>

        {/* Tabs */}
        <div className="flex space-x-1 bg-slate-900/50 p-1 rounded-lg w-fit border border-slate-800">
          <button
            onClick={() => setActiveTab("analysis")}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeTab === "analysis"
                ? "bg-amber-500/10 text-amber-500 shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <div className="flex items-center space-x-2">
              <BarChart3 className="w-4 h-4" />
              <span>Session Analysis</span>
            </div>
          </button>
          <button
            onClick={() => setActiveTab("live")}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-all ${
              activeTab === "live"
                ? "bg-amber-500/10 text-amber-500 shadow-sm"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <div className="flex items-center space-x-2">
              <Radio className="w-4 h-4" />
              <span>Live Monitor</span>
            </div>
          </button>
        </div>

        {/* Tab Content */}
        {activeTab === "analysis" ? (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Upload Zone */}
            <div
              className={`relative border-2 border-dashed rounded-xl p-10 text-center transition-all ${
                isDragging
                  ? "border-amber-500 bg-amber-500/5"
                  : "border-slate-800 bg-slate-900/20 hover:border-slate-700 hover:bg-slate-900/40"
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <input
                type="file"
                accept=".csv"
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                onChange={handleFileSelect}
              />
              <div className="flex flex-col items-center space-y-4 pointer-events-none">
                <div className="p-4 rounded-full bg-slate-800/50">
                  <Upload className="w-8 h-8 text-slate-400" />
                </div>
                <div>
                  <p className="text-lg font-medium text-slate-200">
                    {file ? file.name : "Drag and drop telemetry CSV"}
                  </p>
                  <p className="text-sm text-slate-500 mt-1">
                    Supports AiM, MoTeC, Pi System, and generic headers
                  </p>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between">
              {error && (
                <div className="flex items-center space-x-2 text-red-400 text-sm bg-red-400/10 px-4 py-2 rounded-md">
                  <AlertTriangle className="w-4 h-4" />
                  <span>{error}</span>
                </div>
              )}
              <div className="flex-1" />
              <button
                onClick={handleAnalyse}
                disabled={!file || isAnalysing}
                className="flex items-center space-x-2 bg-amber-600 hover:bg-amber-500 text-white px-6 py-2.5 rounded-lg font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-amber-900/20"
              >
                {isAnalysing ? (
                  <>
                    <Activity className="w-5 h-5 animate-spin" />
                    <span>Analysing...</span>
                  </>
                ) : (
                  <>
                    <Activity className="w-5 h-5" />
                    <span>Analyse Session</span>
                  </>
                )}
              </button>
            </div>

            {/* Results */}
            {analysisResult && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-in fade-in duration-700">
                {/* Channel Map */}
                <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-6 backdrop-blur-sm">
                  <h3 className="text-lg font-medium text-white flex items-center space-x-2 mb-4">
                    <FileSpreadsheet className="w-5 h-5 text-amber-500" />
                    <span>Channel Map</span>
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left">
                      <thead className="text-xs text-slate-400 uppercase bg-slate-800/50">
                        <tr>
                          <th className="px-4 py-3 rounded-tl-lg">Std Key</th>
                          <th className="px-4 py-3">Raw Name</th>
                          <th className="px-4 py-3">Unit</th>
                          <th className="px-4 py-3 rounded-tr-lg">Confidence</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/50">
                        {Object.values(analysisResult.channel_map).map((info: any, i) => (
                          <tr key={i} className="hover:bg-slate-800/20 transition-colors">
                            <td className="px-4 py-3 font-mono text-amber-500/90">{info.standard_key}</td>
                            <td className="px-4 py-3 text-slate-300">{info.raw_name}</td>
                            <td className="px-4 py-3 text-slate-400">{info.inferred_unit}</td>
                            <td className="px-4 py-3">
                              <div className="flex items-center space-x-2">
                                <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                                  <div
                                    className="h-full bg-emerald-500"
                                    style={{ width: `${info.confidence * 100}%` }}
                                  />
                                </div>
                                <span className="text-xs text-slate-500">{Math.round(info.confidence * 100)}%</span>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Data Quality & Summary */}
                <div className="space-y-6">
                  <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-6 backdrop-blur-sm">
                    <h3 className="text-lg font-medium text-white flex items-center space-x-2 mb-4">
                      <CheckCircle className="w-5 h-5 text-amber-500" />
                      <span>Data Quality</span>
                    </h3>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-slate-800/30 p-4 rounded-lg border border-slate-800/50">
                        <div className="text-sm text-slate-400 mb-1 flex items-center space-x-2"><Zap className="w-4 h-4"/> <span>Sample Rate</span></div>
                        <div className="text-2xl font-light text-white">{analysisResult.qa?.sample_rate_hz || "-"} <span className="text-sm text-slate-500">Hz</span></div>
                      </div>
                      <div className="bg-slate-800/30 p-4 rounded-lg border border-slate-800/50">
                        <div className="text-sm text-slate-400 mb-1 flex items-center space-x-2"><Clock className="w-4 h-4"/> <span>Duration</span></div>
                        <div className="text-2xl font-light text-white">{analysisResult.qa?.duration_s || "-"} <span className="text-sm text-slate-500">s</span></div>
                      </div>
                      <div className="bg-slate-800/30 p-4 rounded-lg border border-slate-800/50">
                        <div className="text-sm text-slate-400 mb-1 flex items-center space-x-2"><AlertTriangle className="w-4 h-4"/> <span>Warnings</span></div>
                        <div className="text-2xl font-light text-amber-500">{analysisResult.qa?.total_warnings || 0}</div>
                      </div>
                      <div className="bg-slate-800/30 p-4 rounded-lg border border-slate-800/50">
                        <div className="text-sm text-slate-400 mb-1 flex items-center space-x-2"><XCircle className="w-4 h-4"/> <span>Dead Channels</span></div>
                        <div className="text-2xl font-light text-red-400">{analysisResult.qa?.dead_channels?.length || 0}</div>
                      </div>
                    </div>
                  </div>

                  {/* Sim vs Telemetry */}
                  <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-6 backdrop-blur-sm">
                    <h3 className="text-lg font-medium text-white flex items-center space-x-2 mb-4">
                      <Gauge className="w-5 h-5 text-amber-500" />
                      <span>Sim vs Telemetry</span>
                    </h3>
                    {analysisResult.comparison && analysisResult.comparison.length > 0 ? (
                      <div className="space-y-3">
                        {analysisResult.comparison.map((row: any, i: number) => (
                          <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-slate-800/20 border border-slate-800/50">
                            <div>
                              <div className="text-sm font-medium text-slate-200">{row.description}</div>
                              <div className="text-xs text-slate-500 font-mono">{row.channel} [{row.unit}]</div>
                            </div>
                            <div className="flex items-center space-x-4">
                              <div className="text-right">
                                <div className="text-xs text-slate-500">Sim</div>
                                <div className="text-sm text-slate-300">{row.sim_value ?? "-"}</div>
                              </div>
                              <div className="text-right">
                                <div className="text-xs text-slate-500">Telem</div>
                                <div className="text-sm text-slate-300">{row.telem_value ?? "-"}</div>
                              </div>
                              <div className={`px-2 py-1 rounded text-xs font-medium ${
                                row.status === "good" ? "bg-emerald-500/10 text-emerald-400" :
                                row.status === "warning" ? "bg-amber-500/10 text-amber-400" :
                                row.status === "error" ? "bg-red-500/10 text-red-400" :
                                "bg-slate-500/10 text-slate-400"
                              }`}>
                                {row.error_pct != null ? `${row.error_pct > 0 ? '+' : ''}${row.error_pct}%` : "N/A"}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-sm text-slate-500 text-center py-4">No comparison data available</div>
                    )}
                  </div>
                </div>

                {/* Lap Segments Timeline */}
                <div className="lg:col-span-2 bg-slate-900/40 border border-slate-800 rounded-xl p-6 backdrop-blur-sm">
                  <h3 className="text-lg font-medium text-white flex items-center space-x-2 mb-4">
                    <ChevronRight className="w-5 h-5 text-amber-500" />
                    <span>Lap Segments</span>
                  </h3>
                  {analysisResult.segments && analysisResult.segments.length > 0 ? (
                    <div className="relative h-8 bg-slate-800 rounded-md overflow-hidden flex w-full group">
                      {analysisResult.segments.map((seg: any, i: number) => {
                        const totalDuration = analysisResult.summary.duration_s || 1;
                        const widthPct = (seg.duration_s / totalDuration) * 100;
                        let colorClass = "bg-slate-600";
                        if (seg.label === "straight") colorClass = "bg-blue-500/80";
                        if (seg.label === "braking") colorClass = "bg-red-500/80";
                        if (seg.label.includes("corner")) colorClass = "bg-amber-500/80";
                        
                        return (
                          <div 
                            key={i} 
                            style={{ width: `${widthPct}%` }}
                            className={`h-full ${colorClass} border-r border-slate-900/50 hover:brightness-110 transition-all cursor-crosshair relative`}
                            title={`${seg.label} (${seg.duration_s}s)\nSpeed: ${seg.peak_speed.toFixed(1)}m/s\nLatG: ${seg.peak_lat_g.toFixed(2)}`}
                          />
                        );
                      })}
                    </div>
                  ) : (
                    <div className="text-sm text-slate-500 text-center py-4">No segments identified</div>
                  )}
                  <div className="flex items-center justify-center space-x-6 mt-4 text-xs text-slate-400">
                    <div className="flex items-center space-x-2"><div className="w-3 h-3 rounded-full bg-blue-500/80"/><span>Straight</span></div>
                    <div className="flex items-center space-x-2"><div className="w-3 h-3 rounded-full bg-red-500/80"/><span>Braking</span></div>
                    <div className="flex items-center space-x-2"><div className="w-3 h-3 rounded-full bg-amber-500/80"/><span>Corner</span></div>
                  </div>
                </div>

              </div>
            )}
          </div>
        ) : (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex items-center justify-between bg-slate-900/40 p-6 rounded-xl border border-slate-800 backdrop-blur-sm">
              <div>
                <h3 className="text-lg font-medium text-white mb-1">Live Telemetry Session</h3>
                <p className="text-sm text-slate-400">Monitoring real-time physics data from vehicle DAQ</p>
              </div>
              <button
                onClick={() => setIsLiveActive(!isLiveActive)}
                className={`flex items-center space-x-2 px-6 py-2.5 rounded-lg font-medium transition-all ${
                  isLiveActive 
                    ? "bg-slate-800 text-slate-200 hover:bg-slate-700" 
                    : "bg-emerald-600 text-white hover:bg-emerald-500 shadow-lg shadow-emerald-900/20"
                }`}
              >
                {isLiveActive ? (
                  <><Square className="w-4 h-4" /><span>Stop Session</span></>
                ) : (
                  <><Play className="w-4 h-4" /><span>Start Session</span></>
                )}
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="bg-slate-900/40 p-6 rounded-xl border border-slate-800 flex items-center justify-center backdrop-blur-sm h-96">
                <GGFrictionCircle maxG={2.5} latG={telemetry.lat_g} longG={telemetry.long_g} />
              </div>
              <div className="bg-slate-900/40 p-6 rounded-xl border border-slate-800 backdrop-blur-sm h-96">
                <TelemetryGauges speedMs={telemetry.speed_ms} divergencePct={0} status="Live" />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

