"use client";

import React, { useState } from "react";
import {
  Layers,
  Upload,
  GitCompare,
  Download,
  FileCode,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  Copy,
  Hash,
  Activity,
  Cpu,
  RefreshCw,
  Sliders,
  Database,
  ExternalLink,
} from "lucide-react";

/** Safe finite-number formatting: renders "N/A" for null/NaN/Infinity so
    ingestion and comparison metrics can never crash the ErrorBoundary. */
function fmt(v: unknown, digits: number, suffix = ""): string {
  if (v == null || v === "" || typeof v === "boolean") return "N/A";
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? `${n.toFixed(digits)}${suffix}` : "N/A";
}
import {
  CaeApi,
  CaeImportRequest,
  CaeNormalizedDataset,
  CaeSolverComparisonResult,
  CaeExportResponse,
} from "../../lib/api_client";

const SAMPLE_ADAMS_CSV = `time,ddz_s,susp_travel,tire_load
0.00,0.000,0.0000,4120.2
0.01,0.120,0.0012,4145.8
0.02,0.450,0.0035,4210.1
0.03,0.890,0.0068,4320.5
0.04,1.420,0.0105,4480.0
0.05,1.980,0.0142,4650.4
0.06,2.350,0.0175,4790.2
0.07,2.480,0.0198,4850.1
0.08,2.320,0.0205,4780.0
0.09,1.890,0.0195,4610.3
0.10,1.250,0.0168,4380.7
0.11,0.520,0.0125,4120.0
0.12,-0.180,0.0075,3890.4
0.13,-0.750,0.0028,3720.1
0.14,-1.120,-0.0010,3610.8
0.15,-1.280,-0.0035,3570.2
0.16,-1.190,-0.0048,3600.0
0.17,-0.920,-0.0049,3690.5
0.18,-0.550,-0.0039,3820.2
0.19,-0.180,-0.0022,3980.0
0.20,0.120,-0.0005,4115.0`;

export default function CaeInteroperabilityPage() {
  const [activeTab, setActiveTab] = useState<"import" | "compare" | "export">("import");

  // Import State
  const [sourceTool, setSourceTool] = useState("MSC Adams");
  const [version, setVersion] = useState("Adams 2024.1");
  const [solver, setSolver] = useState("WSTIFF");
  const [csvTrace, setCsvTrace] = useState(SAMPLE_ADAMS_CSV);
  const [importing, setImporting] = useState(false);
  const [normalizedData, setNormalizedData] = useState<CaeNormalizedDataset | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  // Setup Parameters
  const [params, setParams] = useState({
    m_s: 320.0,
    m_u: 45.0,
    k_s: 35000.0,
    c: 2200.0,
    k_t: 220000.0,
    MR: 0.85,
  });

  // Comparison State
  const [comparing, setComparing] = useState(false);
  const [comparisonResult, setComparisonResult] = useState<CaeSolverComparisonResult | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);

  // Export State
  const [exportFormat, setExportFormat] = useState<"adams_adm" | "adams_cmd" | "adams_py" | "matlab_m">("adams_adm");
  const [exporting, setExporting] = useState(false);
  const [exportedDeck, setExportedDeck] = useState<CaeExportResponse | null>(null);
  const [exportCopied, setExportCopied] = useState(false);

  // Handle Import
  const handleImport = async () => {
    setImporting(true);
    setImportError(null);
    try {
      const payload: CaeImportRequest = {
        source_tool: sourceTool,
        version,
        solver,
        parameters: params,
        raw_trace_csv: csvTrace,
        execution_environment: "External CAE Host (x86_64)",
      };
      const res = await CaeApi.importExternal(payload);
      setNormalizedData(res);
    } catch (err: any) {
      setImportError(err.message || "Failed to normalize CAE dataset");
    } finally {
      setImporting(false);
    }
  };

  // Handle Solver Compare
  const handleCompare = async () => {
    setComparing(true);
    setCompareError(null);
    try {
      const payload = {
        import_payload: {
          source_tool: sourceTool,
          version,
          solver,
          parameters: params,
          raw_trace_csv: csvTrace,
          execution_environment: "External CAE Host (x86_64)",
        },
        override_native_params: params,
      };
      const res = await CaeApi.compareSolvers(payload);
      setComparisonResult(res);
      setActiveTab("compare");
    } catch (err: any) {
      setCompareError(err.message || "Failed to compare solvers");
    } finally {
      setComparing(false);
    }
  };

  // Handle Export
  const handleExport = async (format: "adams_adm" | "adams_cmd" | "adams_py" | "matlab_m") => {
    setExportFormat(format);
    setExporting(true);
    try {
      const res = await CaeApi.exportDeck(format, params);
      setExportedDeck(res);
    } catch (err: any) {
      console.error("Export failed:", err);
    } finally {
      setExporting(false);
    }
  };

  const copyDeck = () => {
    if (exportedDeck?.code) {
      navigator.clipboard.writeText(exportedDeck.code);
      setExportCopied(true);
      setTimeout(() => setExportCopied(false), 2000);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0c] text-zinc-100 pt-20 pb-16 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-zinc-800">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-xl bg-purple-500/10 border border-purple-500/30 text-purple-400">
                <Layers className="w-5 h-5" />
              </div>
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white">
                Incumbent CAE Interoperability Hub
              </h1>
              <span className="px-2 py-0.5 rounded text-xs font-mono uppercase bg-purple-950/40 text-purple-300 border border-purple-500/30">
                ADAMS • SIMULINK • CARMAKER • FMI
              </span>
            </div>
            <p className="mt-1 text-xs sm:text-sm text-zinc-400 max-w-3xl">
              Seamlessly ingest external multi-body simulations, preserve immutable provenance with artifact SHA-256 fingerprints, execute side-by-side solver comparisons against native forward ODEs, and export verified parameter decks.
            </p>
          </div>

          {/* Tab Navigation */}
          <div className="flex items-center p-1 bg-zinc-900 border border-zinc-800 rounded-xl shrink-0">
            <button
              onClick={() => setActiveTab("import")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === "import"
                  ? "bg-zinc-800 text-white shadow"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              <Upload className="w-3.5 h-3.5" />
              <span>Import &amp; Normalize</span>
            </button>
            <button
              onClick={() => setActiveTab("compare")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === "compare"
                  ? "bg-zinc-800 text-white shadow"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              <GitCompare className="w-3.5 h-3.5 text-signal" />
              <span>Solver Benchmark</span>
            </button>
            <button
              onClick={() => {
                setActiveTab("export");
                if (!exportedDeck) handleExport(exportFormat);
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeTab === "export"
                  ? "bg-zinc-800 text-white shadow"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              <Download className="w-3.5 h-3.5 text-cyan-400" />
              <span>Deck Exporter</span>
            </button>
          </div>
        </div>

        {/* TAB 1: IMPORT & NORMALIZE */}
        {activeTab === "import" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left: Input Form (5 cols) */}
            <div className="lg:col-span-5 space-y-4">
              <div className="p-5 rounded-2xl bg-zinc-900/60 border border-zinc-800 space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-bold text-white flex items-center gap-2">
                    <Database className="w-4 h-4 text-purple-400" />
                    External CAE Tool Source
                  </h2>
                  <span className="text-xs font-mono text-zinc-400">Pillar 2 Interop</span>
                </div>

                {/* Tool Selector */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-mono text-zinc-400 block mb-1">Source CAE Tool</label>
                    <select
                      value={sourceTool}
                      onChange={(e) => {
                        setSourceTool(e.target.value);
                        if (e.target.value === "MSC Adams") {
                          setVersion("Adams 2024.1");
                          setSolver("WSTIFF");
                        } else if (e.target.value === "MATLAB / Simulink") {
                          setVersion("R2024b");
                          setSolver("ode45 (Dormand-Prince)");
                        } else if (e.target.value === "IPG CarMaker") {
                          setVersion("CarMaker 13.0");
                          setSolver("RK4 Multi-Rate");
                        } else {
                          setVersion("FMI 2.0 Co-Sim");
                          setSolver("CVODE");
                        }
                      }}
                      className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-xs text-zinc-200 font-mono focus:border-purple-500 outline-none"
                    >
                      <option value="MSC Adams">MSC Adams</option>
                      <option value="MATLAB / Simulink">MATLAB / Simulink</option>
                      <option value="IPG CarMaker">IPG CarMaker</option>
                      <option value="FMI / FMU">FMI / FMU Standard</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-mono text-zinc-400 block mb-1">Solver Algorithm</label>
                    <input
                      type="text"
                      value={solver}
                      onChange={(e) => setSolver(e.target.value)}
                      className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-xs text-zinc-200 font-mono focus:border-purple-500 outline-none"
                    />
                  </div>
                </div>

                {/* Version */}
                <div>
                  <label className="text-xs font-mono text-zinc-400 block mb-1">Software Version / Build</label>
                  <input
                    type="text"
                    value={version}
                    onChange={(e) => setVersion(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-xs text-zinc-200 font-mono focus:border-purple-500 outline-none"
                  />
                </div>

                {/* Setup Parameters */}
                <div>
                  <label className="text-xs font-mono text-zinc-400 block mb-1">Vehicle Setup Baseline</label>
                  <div className="grid grid-cols-3 gap-2 text-xs font-mono">
                    <div className="bg-zinc-950 p-2 rounded border border-zinc-850">
                      <span className="text-xs text-zinc-400 block">m_s (kg)</span>
                      <input
                        type="number"
                        value={params.m_s}
                        onChange={(e) => setParams({ ...params, m_s: parseFloat(e.target.value) || 320 })}
                        className="w-full bg-transparent text-zinc-200 outline-none"
                      />
                    </div>
                    <div className="bg-zinc-950 p-2 rounded border border-zinc-850">
                      <span className="text-xs text-zinc-400 block">k_s (N/m)</span>
                      <input
                        type="number"
                        value={params.k_s}
                        onChange={(e) => setParams({ ...params, k_s: parseFloat(e.target.value) || 35000 })}
                        className="w-full bg-transparent text-zinc-200 outline-none"
                      />
                    </div>
                    <div className="bg-zinc-950 p-2 rounded border border-zinc-850">
                      <span className="text-xs text-zinc-400 block">c (Ns/m)</span>
                      <input
                        type="number"
                        value={params.c}
                        onChange={(e) => setParams({ ...params, c: parseFloat(e.target.value) || 2200 })}
                        className="w-full bg-transparent text-zinc-200 outline-none"
                      />
                    </div>
                  </div>
                </div>

                {/* Raw Trace CSV Input */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-xs font-mono text-zinc-400">Raw Simulation CSV Trace</label>
                    <button
                      type="button"
                      onClick={() => setCsvTrace(SAMPLE_ADAMS_CSV)}
                      className="text-xs font-mono text-purple-400 hover:underline"
                    >
                      Reset Preset
                    </button>
                  </div>
                  <textarea
                    rows={7}
                    value={csvTrace}
                    onChange={(e) => setCsvTrace(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2.5 text-xs text-zinc-300 font-mono focus:border-purple-500 outline-none custom-scrollbar"
                  />
                  <p className="text-xs text-zinc-400 mt-1">
                    Accepts ISO 8855 channels or vendor synonyms (time, vert_g, ddz_s, susp_travel, tire_load).
                  </p>
                </div>

                {importError && (
                  <div className="p-3 rounded-lg bg-red-950/40 border border-red-500/40 text-xs text-red-300 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 shrink-0 text-red-400" />
                    <span>{importError}</span>
                  </div>
                )}

                {/* Action Buttons */}
                <div className="flex items-center gap-3 pt-2">
                  <button
                    onClick={handleImport}
                    disabled={importing}
                    className="flex-1 py-2 px-4 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-semibold text-xs transition-all flex items-center justify-center gap-2 shadow-lg"
                  >
                    {importing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                    <span>Normalize &amp; Ingest Dataset</span>
                  </button>
                  <button
                    onClick={handleCompare}
                    disabled={comparing}
                    className="py-2 px-4 rounded-xl bg-signal text-carbon border border-signal font-bold text-xs hover:bg-[#d6f56e] transition-colors flex items-center gap-1.5"
                  >
                    <GitCompare className="w-3.5 h-3.5" />
                    <span>Compare Solvers</span>
                  </button>
                </div>
              </div>
            </div>

            {/* Right: Normalized Dataset & Provenance Identity (7 cols) */}
            <div className="lg:col-span-7 space-y-4">
              {normalizedData ? (
                <div className="p-5 rounded-2xl bg-zinc-900/60 border border-zinc-800 space-y-5">
                  {/* Provenance Header */}
                  <div className="flex items-start justify-between gap-4 pb-4 border-b border-zinc-800">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-bold text-sm text-white">Normalized External Dataset</h3>
                        <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-amber-500/10 text-amber-400 border border-amber-500/30 flex items-center gap-1">
                          <ShieldAlert className="w-3 h-3" />
                          ORIGIN: EXTERNAL_CAE
                        </span>
                      </div>
                      <div className="text-xs text-zinc-400 mt-1 flex items-center gap-3 font-mono">
                        <span>Source: <strong className="text-zinc-200">{normalizedData.identity.source_tool}</strong></span>
                        <span>Solver: <strong className="text-zinc-200">{normalizedData.identity.solver}</strong></span>
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-xs text-zinc-400 font-mono">SHA-256 Artifact Hash</div>
                      <div className="text-xs font-mono text-zinc-300 flex items-center justify-end gap-1">
                        <Hash className="w-3 h-3 text-purple-400" />
                        <span>{normalizedData.identity.artifact_hash.slice(0, 16)}...</span>
                      </div>
                    </div>
                  </div>

                  {/* Summary Metrics */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-3 rounded-xl bg-zinc-950/80 border border-zinc-800">
                      <span className="text-xs text-zinc-400 font-mono uppercase block">Samples Ingested</span>
                      <span className="text-base font-bold text-white font-mono">{normalizedData.sample_count}</span>
                    </div>
                    <div className="p-3 rounded-xl bg-zinc-950/80 border border-zinc-800">
                      <span className="text-xs text-zinc-400 font-mono uppercase block">Time Window</span>
                      <span className="text-base font-bold text-white font-mono">
                        {fmt(normalizedData.time_start, 2, "s")} - {fmt(normalizedData.time_end, 2, "s")}
                      </span>
                    </div>
                    <div className="p-3 rounded-xl bg-zinc-950/80 border border-zinc-800">
                      <span className="text-xs text-zinc-400 font-mono uppercase block">Mean Timestep</span>
                      <span className="text-base font-bold text-emerald-400 font-mono">
                        {fmt(normalizedData.dt_mean != null ? normalizedData.dt_mean * 1000 : null, 1, " ms")}
                      </span>
                    </div>
                    <div className="p-3 rounded-xl bg-zinc-950/80 border border-zinc-800">
                      <span className="text-xs text-zinc-400 font-mono uppercase block">Channels Mapped</span>
                      <span className="text-base font-bold text-cyan-400 font-mono">
                        {normalizedData.channels_present.length} ISO
                      </span>
                    </div>
                  </div>

                  {/* Channels Present */}
                  <div>
                    <h4 className="text-xs font-mono text-zinc-400 mb-2">Normalized ISO 8855 Channels</h4>
                    <div className="flex flex-wrap gap-2">
                      {normalizedData.channels_present.map((ch) => (
                        <span
                          key={ch}
                          className="px-2.5 py-1 rounded-lg bg-zinc-950 border border-zinc-800 text-xs font-mono text-zinc-300 flex items-center gap-1.5"
                        >
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          {ch}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Anti-Tautology Notice */}
                  <div className="p-3.5 rounded-xl bg-zinc-950/60 border border-zinc-800/80 space-y-1 text-xs">
                    <span className="font-bold text-zinc-300 flex items-center gap-1.5">
                      <ShieldAlert className="w-3.5 h-3.5 text-signal" />
                      Anti-Tautology &amp; Verification Rule
                    </span>
                    <p className="text-zinc-400 text-xs leading-relaxed">
                      SuspensionLab strictly separates external CAE data from native forward calculations. This ingested artifact is flagged as <strong className="text-zinc-200">EXTERNAL_CAE</strong> with an immutable cryptographic digest. It will never be passed off as native forward-model truth.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="p-12 rounded-2xl bg-zinc-900/30 border border-dashed border-zinc-800 text-center space-y-3">
                  <div className="w-12 h-12 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center mx-auto text-zinc-400">
                    <Upload className="w-6 h-6" />
                  </div>
                  <h3 className="text-sm font-semibold text-zinc-300">No External Dataset Ingested Yet</h3>
                  <p className="text-xs text-zinc-400 max-w-sm mx-auto">
                    Select a CAE tool, verify the vehicle setup, and click &quot;Normalize &amp; Ingest Dataset&quot; to inspect normalized telemetry.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: SOLVER BENCHMARK */}
        {activeTab === "compare" && (
          <div className="space-y-6">
            {comparisonResult ? (
              <div className="p-6 rounded-2xl bg-zinc-900/60 border border-zinc-800 space-y-6">
                {/* Benchmark Header */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-zinc-800">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-base font-bold text-white">Solver Correlation &amp; Verification Report</h2>
                      <span className="px-2 py-0.5 rounded text-xs font-mono uppercase bg-emerald-950/40 text-emerald-300 border border-emerald-500/30">
                        Independent Forward Solvers
                      </span>
                    </div>
                    <p className="text-xs text-zinc-400 mt-0.5">
                      {comparisonResult.external_identity.source_tool} ({comparisonResult.external_identity.solver}) vs. SuspensionLab PRO Native ({comparisonResult.native_identity.solver})
                    </p>
                  </div>

                  <button
                    onClick={handleCompare}
                    disabled={comparing}
                    className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs font-mono text-zinc-200 flex items-center gap-1.5 transition-colors"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${comparing ? "animate-spin" : ""}`} />
                    Re-run Solver Benchmark
                  </button>
                </div>

                {/* Solvers Identity Cards */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                  {/* External */}
                  <div className="p-4 rounded-xl bg-zinc-950/80 border border-zinc-800 space-y-2">
                    <div className="flex items-center justify-between text-zinc-400">
                      <span className="uppercase text-xs text-zinc-400">External Model Deck</span>
                      <span className="px-1.5 py-0.5 rounded text-xs bg-zinc-900 border border-zinc-800 text-zinc-400">
                        ORIGIN: EXTERNAL_CAE
                      </span>
                    </div>
                    <div className="text-sm font-bold text-white">{comparisonResult.external_identity.source_tool}</div>
                    <div className="text-zinc-400 text-xs">Solver: {comparisonResult.external_identity.solver}</div>
                    <div className="text-xs text-zinc-400 truncate">Hash: {comparisonResult.external_identity.artifact_hash}</div>
                  </div>

                  {/* Native */}
                  <div className="p-4 rounded-xl bg-zinc-950/80 border border-zinc-800 space-y-2">
                    <div className="flex items-center justify-between text-zinc-400">
                      <span className="uppercase text-xs text-zinc-400">SuspensionLab PRO Native</span>
                      <span className="px-1.5 py-0.5 rounded text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                        ORIGIN: NATIVE_SIMULATION
                      </span>
                    </div>
                    <div className="text-sm font-bold text-emerald-400">{comparisonResult.native_identity.solver}</div>
                    <div className="text-zinc-400 text-xs">Model Version: {comparisonResult.native_identity.model_version}</div>
                    <div className="text-xs text-zinc-400">Backend: {comparisonResult.native_identity.backend}</div>
                  </div>
                </div>

                {/* Channel Metrics Grid */}
                <div className="space-y-3">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-400 font-mono">
                    Channel-by-Channel Physical Correlation
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {Object.entries(comparisonResult.channel_metrics).map(([channel, metric]) => {
                      const isStrong = metric.agreement_status === "STRONG_CORRELATION";
                      return (
                        <div
                          key={channel}
                          className={`p-4 rounded-xl border bg-zinc-950/60 ${
                            isStrong ? "border-emerald-500/30" : "border-amber-500/30"
                          } space-y-3`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-zinc-200 text-xs font-mono">{channel}</span>
                            <span
                              className={`px-1.5 py-0.5 rounded text-xs font-mono font-bold uppercase ${
                                isStrong
                                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                                  : "bg-amber-500/10 text-amber-400 border border-amber-500/30"
                              }`}
                            >
                              {metric.agreement_status.replace("_", " ")}
                            </span>
                          </div>

                          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                            <div className="bg-zinc-900/60 p-2 rounded border border-zinc-800">
                              <span className="text-xs text-zinc-400 block">R² Correlation</span>
                              <span className="font-bold text-white">{fmt(metric.r_squared, 3)}</span>
                            </div>
                            <div className="bg-zinc-900/60 p-2 rounded border border-zinc-800">
                              <span className="text-xs text-zinc-400 block">RMS Residual</span>
                              <span className="font-bold text-white">{fmt(metric.rms_residual, 4)}</span>
                            </div>
                            <div className="bg-zinc-900/60 p-2 rounded border border-zinc-800">
                              <span className="text-xs text-zinc-400 block">Max Abs Error</span>
                              <span className="font-bold text-zinc-300">{fmt(metric.max_absolute_error, 4)}</span>
                            </div>
                            <div className="bg-zinc-900/60 p-2 rounded border border-zinc-800">
                              <span className="text-xs text-zinc-400 block">Mean Error %</span>
                              <span className="font-bold text-zinc-300">{fmt(metric.mean_percentage_error, 1, "%")}</span>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Engineering Interpretation */}
                <div className="p-4 rounded-xl bg-purple-950/20 border border-purple-500/30 space-y-1">
                  <span className="text-xs font-bold text-purple-300 uppercase tracking-wider flex items-center gap-1.5">
                    <Activity className="w-3.5 h-3.5 text-purple-400" />
                    Engineering Interpretation &amp; Solver Dynamics
                  </span>
                  <p className="text-xs text-zinc-300 leading-relaxed font-sans">
                    {comparisonResult.engineering_interpretation}
                  </p>
                  <p className="text-xs text-zinc-400 mt-2 font-sans leading-relaxed">
                    Boundary Notes: {comparisonResult.boundary_notes}
                  </p>
                </div>
              </div>
            ) : (
              <div className="p-12 rounded-2xl bg-zinc-900/30 border border-dashed border-zinc-800 text-center space-y-3">
                <div className="w-12 h-12 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center mx-auto text-zinc-400">
                  <GitCompare className="w-6 h-6 text-signal" />
                </div>
                <h3 className="text-sm font-semibold text-zinc-300">No Active Solver Benchmark</h3>
                <p className="text-xs text-zinc-400 max-w-sm mx-auto">
                  Click &quot;Compare Solvers&quot; in the Import panel to run the native RK45 ODE solver side-by-side with your external CAE trace.
                </p>
                <button
                  onClick={handleCompare}
                  disabled={comparing}
                  className="mt-2 px-4 py-2 rounded-xl bg-signal text-carbon border border-signal font-bold text-xs hover:bg-[#d6f56e] transition-all inline-flex items-center gap-1.5"
                >
                  <GitCompare className="w-3.5 h-3.5" />
                  <span>Run Comparison Now</span>
                </button>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: DECK EXPORTER */}
        {activeTab === "export" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left Options (4 cols) */}
            <div className="lg:col-span-4 space-y-4">
              <div className="p-5 rounded-2xl bg-zinc-900/60 border border-zinc-800 space-y-4">
                <h2 className="text-sm font-bold text-white flex items-center gap-2">
                  <FileCode className="w-4 h-4 text-cyan-400" />
                  Target CAE Tool Deck
                </h2>

                <div className="space-y-2">
                  {[
                    { id: "adams_adm", label: "MSC Adams Dataset (.adm)", desc: "Quarter-car multi-body dataset" },
                    { id: "adams_cmd", label: "MSC Adams Command (.cmd)", desc: "Interactive command script deck" },
                    { id: "adams_py", label: "MSC Adams Python API (.py)", desc: "Automated Adams View Python script" },
                    { id: "matlab_m", label: "MATLAB / Simulink (.m)", desc: "Simulink parameters & state-space matrices" },
                  ].map((deck) => (
                    <button
                      key={deck.id}
                      onClick={() => handleExport(deck.id as any)}
                      className={`w-full p-3 rounded-xl border text-left transition-all ${
                        exportFormat === deck.id
                          ? "bg-cyan-950/20 border-cyan-500/40 text-cyan-200"
                          : "bg-zinc-950/60 border-zinc-800 text-zinc-400 hover:border-zinc-700 hover:text-white"
                      }`}
                    >
                      <div className="font-semibold text-xs text-white">{deck.label}</div>
                      <div className="text-xs text-zinc-400 mt-0.5">{deck.desc}</div>
                    </button>
                  ))}
                </div>

                {/* Setup Parameters Snapshot */}
                <div className="pt-2 border-t border-zinc-800 space-y-2">
                  <span className="text-xs font-mono uppercase text-zinc-400 block">Exported Parameters</span>
                  <div className="grid grid-cols-2 gap-2 text-xs font-mono text-zinc-300">
                    <div className="bg-zinc-950 p-2 rounded border border-zinc-850">m_s: {params.m_s} kg</div>
                    <div className="bg-zinc-950 p-2 rounded border border-zinc-850">k_s: {params.k_s} N/m</div>
                    <div className="bg-zinc-950 p-2 rounded border border-zinc-850">c: {params.c} Ns/m</div>
                    <div className="bg-zinc-950 p-2 rounded border border-zinc-850">MR: {params.MR}</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Deck Viewer (8 cols) */}
            <div className="lg:col-span-8 space-y-4">
              {exportedDeck ? (
                <div className="p-5 rounded-2xl bg-zinc-900/60 border border-zinc-800 space-y-4">
                  <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-white font-mono">{exportedDeck.filename}</span>
                        {exportedDeck.syntax_validated && (
                          <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" /> SYNTAX VALIDATED
                          </span>
                        )}
                      </div>
                      <span className="text-xs text-zinc-400 mt-0.5 block">{exportedDeck.notes}</span>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={copyDeck}
                        className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-xs font-mono text-zinc-200 flex items-center gap-1.5 transition-colors"
                      >
                        {exportCopied ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                        <span>{exportCopied ? "Copied" : "Copy Code"}</span>
                      </button>
                    </div>
                  </div>

                  {/* Code Block */}
                  <pre className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 font-mono text-xs text-zinc-200 overflow-x-auto max-h-[500px] custom-scrollbar leading-relaxed">
                    {exportedDeck.code}
                  </pre>
                </div>
              ) : (
                <div className="p-12 rounded-2xl bg-zinc-900/30 border border-dashed border-zinc-800 text-center space-y-3">
                  <div className="w-12 h-12 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center mx-auto text-zinc-400">
                    <FileCode className="w-6 h-6" />
                  </div>
                  <h3 className="text-sm font-semibold text-zinc-300">Select a deck format to generate</h3>
                  <p className="text-xs text-zinc-400 max-w-sm mx-auto">
                    Export your suspension model parameters into MSC Adams dataset decks or MATLAB simulation files.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
