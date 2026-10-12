"use client";

import React, { useState, useEffect } from "react";
import {
  Layers,
  Upload,
  Download,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  FileText,
  Cpu,
  RefreshCw,
  ExternalLink,
  Info,
  Clock,
  Hash,
  Database,
  ArrowRight,
} from "lucide-react";
import {
  SolverInteropApi,
  AdapterCapabilityDTO,
  SolverOperationResponseDTO,
  SolverDiagnosticsResponseDTO,
} from "../../lib/api_client";

export function SolverInteropWorkspace() {
  const [adapters, setAdapters] = useState<AdapterCapabilityDTO[]>([]);
  const [selectedAdapterId, setSelectedAdapterId] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"import" | "export" | "inspect">("import");
  const [loading, setLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Import form state
  const [importFilename, setImportFilename] = useState<string>("quarter_car.adm");
  const [importContent, setImportContent] = useState<string>(
    "! MSC ADAMS / Solver Dataset\nADAMS/View model dataset export\nPART/1, MASS = 300.0\nPART/2, MASS = 35.0\nSPRING/1, K = 25000.0, C = 2050.0\nEND"
  );
  const [expectedSha256, setExpectedSha256] = useState<string>("");

  // Export form state
  const [exportFormat, setExportFormat] = useState<string>(".adm");
  const [exportManifestJson, setExportManifestJson] = useState<string>(
    JSON.stringify(
      {
        schema_version: "1.0.0",
        source_application: "SuspensionLab PRO",
        source_solver: "SuspensionLab",
        engineering_model_id: "MDL-QCAR-PROD-01",
        parameters: {
          m_s: { name: "m_s", value: 300.0, unit: "kg", dimension: "MASS" },
          m_u: { name: "m_u", value: 35.0, unit: "kg", dimension: "MASS" },
          k_s: { name: "k_s", value: 25000.0, unit: "N/m", dimension: "TRANSLATIONAL_STIFFNESS" },
          c: { name: "c", value: 2050.0, unit: "Ns/m", dimension: "TRANSLATIONAL_DAMPING" },
          k_t: { name: "k_t", value: 200000.0, unit: "N/m", dimension: "TRANSLATIONAL_STIFFNESS" },
          MR: { name: "MR", value: 0.85, unit: "-", dimension: "DIMENSIONLESS" },
        },
        coordinate_frame: {
          name: "ISO_8855",
          x_axis: "FORWARD",
          y_axis: "LEFT",
          z_axis: "UP",
          handedness: "RIGHT_HANDED",
        },
      },
      null,
      2
    )
  );

  // Active / Inspected Operation
  const [currentOperation, setCurrentOperation] = useState<SolverOperationResponseDTO | null>(null);
  const [diagnostics, setDiagnostics] = useState<SolverDiagnosticsResponseDTO | null>(null);
  const [operationIdInput, setOperationIdInput] = useState<string>("");

  useEffect(() => {
    loadAdapters();
  }, []);

  const loadAdapters = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const list = await SolverInteropApi.listAdapters();
      setAdapters(list);
      if (list.length > 0 && !selectedAdapterId) {
        setSelectedAdapterId(list[0].adapter_id);
        if (list[0].supported_export_formats.length > 0) {
          setExportFormat(list[0].supported_export_formats[0]);
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to load solver adapters.");
    } finally {
      setLoading(false);
    }
  };

  const selectedAdapter = adapters.find((a) => a.adapter_id === selectedAdapterId);

  const handleAdapterChange = (id: string) => {
    setSelectedAdapterId(id);
    const ad = adapters.find((a) => a.adapter_id === id);
    if (ad) {
      if (ad.supported_export_formats.length > 0) {
        setExportFormat(ad.supported_export_formats[0]);
      }
      if (ad.supported_import_formats.length > 0) {
        setImportFilename(`model${ad.supported_import_formats[0]}`);
      }
    }
  };

  const handleRunImport = async () => {
    if (!selectedAdapterId) return;
    try {
      setLoading(true);
      setErrorMsg(null);
      const op = await SolverInteropApi.startImport({
        adapter_id: selectedAdapterId,
        filename: importFilename,
        content: importContent,
        expected_sha256: expectedSha256.trim() || undefined,
      });
      setCurrentOperation(op);
      await fetchDiagnostics(op.id);
    } catch (err: any) {
      setErrorMsg(err.message || "Import operation failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleRunExport = async () => {
    if (!selectedAdapterId) return;
    try {
      setLoading(true);
      setErrorMsg(null);
      let parsedManifest: Record<string, any>;
      try {
        parsedManifest = JSON.parse(exportManifestJson);
      } catch (e: any) {
        setErrorMsg(`Invalid manifest JSON syntax: ${e.message}`);
        return;
      }

      const op = await SolverInteropApi.startExport({
        adapter_id: selectedAdapterId,
        target_format: exportFormat,
        manifest: parsedManifest,
      });
      setCurrentOperation(op);
      await fetchDiagnostics(op.id);
    } catch (err: any) {
      setErrorMsg(err.message || "Export operation failed.");
    } finally {
      setLoading(false);
    }
  };

  const fetchDiagnostics = async (opId: string) => {
    try {
      const diag = await SolverInteropApi.getDiagnostics(opId);
      setDiagnostics(diag);
    } catch {
      setDiagnostics(null);
    }
  };

  const handleInspectOperation = async () => {
    if (!operationIdInput.trim()) return;
    try {
      setLoading(true);
      setErrorMsg(null);
      const op = await SolverInteropApi.getOperation(operationIdInput.trim());
      setCurrentOperation(op);
      await fetchDiagnostics(op.id);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to locate operation.");
      setCurrentOperation(null);
      setDiagnostics(null);
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadArtifact = async (opId: string) => {
    try {
      const blob = await SolverInteropApi.downloadArtifact(opId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `artifact_${opId}.dat`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to download artifact.");
    }
  };

  return (
    <div className="w-full max-w-7xl mx-auto p-6 space-y-8 bg-slate-950 text-slate-100 min-h-screen">
      {/* Header */}
      <div className="border-b border-slate-800 pb-5 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Layers className="w-7 h-7 text-indigo-400" />
            <h1 className="text-2xl font-bold tracking-tight">Solver Interoperability Workspace</h1>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Secure, auditable CAE and external solver exchange with immutable provenance and strict epistemic verification.
          </p>
        </div>
        <button
          onClick={loadAdapters}
          className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh Adapters
        </button>
      </div>

      {/* Epistemic Truth Banners */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-lg border border-amber-900/40 bg-amber-950/20 flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-semibold text-amber-300 block">EXPORTED ≠ EXECUTED</span>
            <span className="text-slate-400">Exporting CAE input files does not prove external solver ran.</span>
          </div>
        </div>
        <div className="p-3.5 rounded-lg border border-sky-900/40 bg-sky-950/20 flex items-start gap-2.5">
          <ShieldCheck className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-semibold text-sky-300 block">IMPORTED ≠ VALIDATED</span>
            <span className="text-slate-400">Parsing success is not physical simulation validation.</span>
          </div>
        </div>
        <div className="p-3.5 rounded-lg border border-purple-900/40 bg-purple-950/20 flex items-start gap-2.5">
          <Info className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-semibold text-purple-300 block">SCHEMA VALID ≠ CORRECT</span>
            <span className="text-slate-400">JSON schema compliance does not imply dynamic validity.</span>
          </div>
        </div>
        <div className="p-3.5 rounded-lg border border-emerald-900/40 bg-emerald-950/20 flex items-start gap-2.5">
          <Cpu className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-semibold text-emerald-300 block">METADATA ≠ RUNNER</span>
            <span className="text-slate-400">FMI XML ingestion excludes binary co-simulation execution.</span>
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="p-4 rounded-lg bg-red-950/40 border border-red-800 text-red-200 text-sm flex items-start gap-3">
          <XCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold block">Operation Error</span>
            <span>{errorMsg}</span>
          </div>
          <button onClick={() => setErrorMsg(null)} className="text-red-400 hover:text-red-200">
            &times;
          </button>
        </div>
      )}

      {/* Main Grid: Adapter Specs (Left) + Workflow Tabs (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Adapter Discovery & Specs */}
        <div className="space-y-6">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
            <h2 className="text-base font-semibold text-slate-200 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-indigo-400" />
              Registered Solver Adapters
            </h2>

            <div>
              <label className="text-xs text-slate-400 block mb-1">Select Adapter</label>
              <select
                value={selectedAdapterId}
                onChange={(e) => handleAdapterChange(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-md p-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
              >
                {adapters.map((a) => (
                  <option key={a.adapter_id} value={a.adapter_id}>
                    {a.solver_name} ({a.adapter_id})
                  </option>
                ))}
              </select>
            </div>

            {selectedAdapter && (
              <div className="space-y-3 pt-2 text-xs">
                <div className="flex justify-between py-1 border-b border-slate-800">
                  <span className="text-slate-400">Adapter Version</span>
                  <span className="font-mono text-slate-200">{selectedAdapter.adapter_version}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800">
                  <span className="text-slate-400">Import Capability</span>
                  <span
                    className={`font-semibold ${
                      selectedAdapter.import_capability === "SUPPORTED"
                        ? "text-emerald-400"
                        : selectedAdapter.import_capability === "PARTIALLY_SUPPORTED"
                        ? "text-amber-400"
                        : "text-rose-400"
                    }`}
                  >
                    {selectedAdapter.import_capability}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-800">
                  <span className="text-slate-400">Export Capability</span>
                  <span
                    className={`font-semibold ${
                      selectedAdapter.export_capability === "SUPPORTED"
                        ? "text-emerald-400"
                        : "text-rose-400"
                    }`}
                  >
                    {selectedAdapter.export_capability}
                  </span>
                </div>
                <div className="py-1 border-b border-slate-800">
                  <span className="text-slate-400 block mb-1">Supported Import Formats</span>
                  <div className="flex flex-wrap gap-1">
                    {selectedAdapter.supported_import_formats.length > 0 ? (
                      selectedAdapter.supported_import_formats.map((fmt) => (
                        <span key={fmt} className="px-1.5 py-0.5 rounded bg-slate-800 text-indigo-300 font-mono text-[10px]">
                          {fmt}
                        </span>
                      ))
                    ) : (
                      <span className="text-slate-500 italic">None (Export-only)</span>
                    )}
                  </div>
                </div>
                <div className="py-1 border-b border-slate-800">
                  <span className="text-slate-400 block mb-1">Supported Export Formats</span>
                  <div className="flex flex-wrap gap-1">
                    {selectedAdapter.supported_export_formats.map((fmt) => (
                      <span key={fmt} className="px-1.5 py-0.5 rounded bg-slate-800 text-emerald-300 font-mono text-[10px]">
                        {fmt}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Host Dependency Status */}
                <div className="py-2 border-b border-slate-800">
                  <span className="text-slate-400 block mb-1 font-semibold">Host Dependencies</span>
                  {selectedAdapter.required_dependencies.map((dep) => (
                    <div key={dep.name} className="flex items-center justify-between py-1 bg-slate-950/60 px-2 rounded mt-1">
                      <div>
                        <span className="text-slate-300 font-medium block">{dep.name}</span>
                        <span className="text-[10px] text-slate-500">{dep.description}</span>
                      </div>
                      <span
                        className={`px-1.5 py-0.5 text-[10px] rounded font-semibold ${
                          dep.is_available
                            ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                            : "bg-rose-950 text-rose-300 border border-rose-800"
                        }`}
                      >
                        {dep.is_available ? "INSTALLED" : "UNAVAILABLE"}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Known Limitations */}
                {selectedAdapter.known_limitations.length > 0 && (
                  <div className="pt-1">
                    <span className="text-slate-400 block mb-1 font-semibold">Technical Limitations</span>
                    <ul className="list-disc list-inside space-y-1 text-slate-400 text-[11px]">
                      {selectedAdapter.known_limitations.map((lim, idx) => (
                        <li key={idx}>{lim}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right 2 Columns: Workflow Tabs */}
        <div className="lg:col-span-2 space-y-6">
          {/* Tabs */}
          <div className="flex border-b border-slate-800 space-x-4">
            <button
              onClick={() => setActiveTab("import")}
              className={`pb-2.5 text-sm font-medium transition flex items-center gap-2 border-b-2 ${
                activeTab === "import"
                  ? "border-indigo-500 text-indigo-400"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Upload className="w-4 h-4" />
              Import Solver Artifact
            </button>
            <button
              onClick={() => setActiveTab("export")}
              className={`pb-2.5 text-sm font-medium transition flex items-center gap-2 border-b-2 ${
                activeTab === "export"
                  ? "border-indigo-500 text-indigo-400"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Download className="w-4 h-4" />
              Export Engineering Model
            </button>
            <button
              onClick={() => setActiveTab("inspect")}
              className={`pb-2.5 text-sm font-medium transition flex items-center gap-2 border-b-2 ${
                activeTab === "inspect"
                  ? "border-indigo-500 text-indigo-400"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Database className="w-4 h-4" />
              Inspect Operation
            </button>
          </div>

          {/* TAB 1: IMPORT */}
          {activeTab === "import" && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <Upload className="w-4 h-4 text-indigo-400" />
                Ingest External CAE Dataset
              </h3>

              {selectedAdapter?.import_capability === "UNSUPPORTED" ? (
                <div className="p-4 rounded-lg bg-rose-950/30 border border-rose-800 text-rose-300 text-xs">
                  The selected adapter (<strong>{selectedAdapter.solver_name}</strong>) is strictly export-only.
                  Ingestion of arbitrary code decks is prohibited to prevent script execution.
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs text-slate-400 block mb-1">Target Filename</label>
                      <input
                        type="text"
                        value={importFilename}
                        onChange={(e) => setImportFilename(e.target.value)}
                        placeholder="e.g. model.adm"
                        className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-sm font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400 block mb-1">
                        Expected SHA-256 Hash <span className="text-slate-500">(Optional tamper check)</span>
                      </label>
                      <input
                        type="text"
                        value={expectedSha256}
                        onChange={(e) => setExpectedSha256(e.target.value)}
                        placeholder="e.g. a1b2c3..."
                        className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-sm font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Payload Content (UTF-8)</label>
                    <textarea
                      rows={7}
                      value={importContent}
                      onChange={(e) => setImportContent(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-700 rounded p-2.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  <button
                    onClick={handleRunImport}
                    disabled={loading || !importFilename.trim()}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 text-white rounded-md text-sm font-medium transition flex items-center gap-2"
                  >
                    <Upload className="w-4 h-4" />
                    {loading ? "Processing Ingestion..." : "Start Persistent Import"}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: EXPORT */}
          {activeTab === "export" && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <Download className="w-4 h-4 text-emerald-400" />
                Export Engineering Model
              </h3>

              <div className="space-y-4">
                <div className="w-full md:w-1/2">
                  <label className="text-xs text-slate-400 block mb-1">Target Format</label>
                  <select
                    value={exportFormat}
                    onChange={(e) => setExportFormat(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-sm text-slate-200 focus:outline-none focus:border-emerald-500"
                  >
                    {selectedAdapter?.supported_export_formats.map((fmt) => (
                      <option key={fmt} value={fmt}>
                        {fmt}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-xs text-slate-400 block mb-1">Canonical Exchange Manifest (JSON)</label>
                  <textarea
                    rows={10}
                    value={exportManifestJson}
                    onChange={(e) => setExportManifestJson(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded p-2.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <button
                  onClick={handleRunExport}
                  disabled={loading}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 text-white rounded-md text-sm font-medium transition flex items-center gap-2"
                >
                  <Download className="w-4 h-4" />
                  {loading ? "Exporting Artifact..." : "Execute Supported Export"}
                </button>
              </div>
            </div>
          )}

          {/* TAB 3: INSPECT */}
          {activeTab === "inspect" && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
              <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <Database className="w-4 h-4 text-purple-400" />
                Inspect Historical Exchange Operation
              </h3>

              <div className="flex gap-2">
                <input
                  type="text"
                  value={operationIdInput}
                  onChange={(e) => setOperationIdInput(e.target.value)}
                  placeholder="Enter Operation UUID (e.g. 3fa85f64-5717-4562-b3fc-2c963f66afa6)"
                  className="flex-1 bg-slate-950 border border-slate-700 rounded p-2 text-sm font-mono text-slate-200 focus:outline-none focus:border-purple-500"
                />
                <button
                  onClick={handleInspectOperation}
                  disabled={loading || !operationIdInput.trim()}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-slate-800 text-white rounded-md text-sm font-medium transition"
                >
                  Search
                </button>
              </div>
            </div>
          )}

          {/* OPERATION DETAILS & PROVENANCE RECORD */}
          {currentOperation && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-5">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-sm text-slate-200">
                    Operation #{currentOperation.id.substring(0, 8)}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                    {currentOperation.operation_type}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`text-xs px-2.5 py-0.5 rounded-full font-semibold ${
                      currentOperation.state === "COMPLETED"
                        ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                        : currentOperation.state === "REJECTED"
                        ? "bg-rose-950 text-rose-300 border border-rose-800"
                        : currentOperation.state === "FAILED"
                        ? "bg-red-950 text-red-300 border border-red-800"
                        : "bg-amber-950 text-amber-300 border border-amber-800"
                    }`}
                  >
                    {currentOperation.state}
                  </span>
                  {currentOperation.state === "COMPLETED" && (
                    <button
                      onClick={() => handleDownloadArtifact(currentOperation.id)}
                      className="px-2.5 py-1 text-xs rounded bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium transition flex items-center gap-1.5"
                    >
                      <Download className="w-3.5 h-3.5 text-emerald-400" />
                      Download Artifact
                    </button>
                  )}
                </div>
              </div>

              {/* Provenance Metadata Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div className="bg-slate-950 p-2.5 rounded border border-slate-800/80">
                  <span className="text-slate-500 block mb-0.5">Adapter</span>
                  <span className="font-mono text-slate-300">{currentOperation.adapter_id}</span>
                </div>
                <div className="bg-slate-950 p-2.5 rounded border border-slate-800/80">
                  <span className="text-slate-500 block mb-0.5">Solver</span>
                  <span className="font-mono text-slate-300">{currentOperation.solver_name}</span>
                </div>
                <div className="bg-slate-950 p-2.5 rounded border border-slate-800/80">
                  <span className="text-slate-500 block mb-0.5">Manifest Hash</span>
                  <span className="font-mono text-slate-300 truncate block">
                    {currentOperation.manifest_hash ? currentOperation.manifest_hash.substring(0, 12) + "..." : "N/A"}
                  </span>
                </div>
                <div className="bg-slate-950 p-2.5 rounded border border-slate-800/80">
                  <span className="text-slate-500 block mb-0.5">Execution Status</span>
                  <span className="font-semibold text-rose-400">NOT EXECUTED</span>
                </div>
              </div>

              {/* Failure / Rejection Reason */}
              {currentOperation.failure_reason && (
                <div className="p-3 rounded bg-rose-950/20 border border-rose-800/60 text-xs text-rose-300">
                  <span className="font-semibold block mb-0.5">Failure Reason:</span>
                  {currentOperation.failure_reason}
                </div>
              )}

              {/* Diagnostics Summary */}
              {diagnostics && (
                <div className="space-y-3 pt-2 text-xs">
                  <h4 className="font-semibold text-slate-300 flex items-center gap-1.5">
                    <FileText className="w-3.5 h-3.5 text-indigo-400" />
                    Diagnostics & Parameter Lineage
                  </h4>
                  <div className="bg-slate-950 p-3 rounded border border-slate-800 font-mono text-[11px] overflow-x-auto max-h-48 text-slate-300">
                    <pre>{JSON.stringify(diagnostics.mapping_diagnostics, null, 2)}</pre>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
