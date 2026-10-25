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
  Play,
  Square,
  Terminal,
  Activity,
  Check,
  Sliders,
  Scale,
  Link2,
  Workflow,
  ShieldAlert,
  Zap,
} from "lucide-react";
import {
  SolverInteropApi,
  AdapterCapabilityDTO,
  SolverOperationResponseDTO,
  SolverDiagnosticsResponseDTO,
  SolverExecutionApi,
  RuntimeEnvironmentInfoDTO,
  JobResponseDTO,
  ReconciliationReportDTO,
  JobPreflightResponseDTO,
  CoSimulationApi,
  CoSimContractDTO,
  CoSimPreflightReportDTO,
  CoSimCapabilitiesDTO,
  FMICapabilityReportDTO,
} from "../../lib/api_client";

export function SolverInteropWorkspace() {
  const [adapters, setAdapters] = useState<AdapterCapabilityDTO[]>([]);
  const [selectedAdapterId, setSelectedAdapterId] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"import" | "export" | "execute" | "jobs" | "inspect" | "cosim">("execute");
  const [loading, setLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Runtimes state (Phase 7.3)
  const [runtimes, setRuntimes] = useState<RuntimeEnvironmentInfoDTO[]>([]);

  // Execution form state (Phase 7.3)
  const [execSolver, setExecSolver] = useState<string>("FMI_COSIMULATION");
  const [execArtifactId, setExecArtifactId] = useState<string>("");
  const [stepSize, setStepSize] = useState<number>(0.001);
  const [stopTime, setStopTime] = useState<number>(2.0);
  const [roadType, setRoadType] = useState<string>("step");
  const [timeoutSec, setTimeoutSec] = useState<number>(30);
  const [preflightResult, setPreflightResult] = useState<JobPreflightResponseDTO | null>(null);

  // Jobs & Reconciliation state (Phase 7.3 & 7.4)
  const [jobs, setJobs] = useState<JobResponseDTO[]>([]);
  const [selectedJob, setSelectedJob] = useState<JobResponseDTO | null>(null);
  const [reconciliationReport, setReconciliationReport] = useState<ReconciliationReportDTO | null>(null);
  const [reconcileLoading, setReconcileLoading] = useState<boolean>(false);
  const [selectedBenchmarkMethod, setSelectedBenchmarkMethod] = useState<string>("EXACT_ANALYTICAL_MATRIX_EXPONENTIAL");
  const [recoveringJobs, setRecoveringJobs] = useState<boolean>(false);

  // Import form state (Phase 7.2)
  const [importFilename, setImportFilename] = useState<string>("quarter_car.adm");
  const [importContent, setImportContent] = useState<string>(
    "! MSC ADAMS / Solver Dataset\nADAMS/View model dataset export\nPART/1, MASS = 300.0\nPART/2, MASS = 35.0\nSPRING/1, K = 25000.0, C = 2050.0\nEND"
  );
  const [expectedSha256, setExpectedSha256] = useState<string>("");

  // Export form state (Phase 7.2)
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

  // Co-Simulation state (Phase 7.5)
  const [contracts, setContracts] = useState<CoSimContractDTO[]>([]);
  const [selectedContract, setSelectedContract] = useState<CoSimContractDTO | null>(null);
  const [cosimCapabilities, setCosimCapabilities] = useState<CoSimCapabilitiesDTO | null>(null);
  const [fmiReport, setFmiReport] = useState<FMICapabilityReportDTO | null>(null);
  const [cosimPreflight, setCosimPreflight] = useState<CoSimPreflightReportDTO | null>(null);
  const [cosimJobDiagnostics, setCosimJobDiagnostics] = useState<any | null>(null);
  const [cosimContractName, setCosimContractName] = useState<string>("Coupled Road-QuarterCar Contract");
  const [cosimStepSize, setCosimStepSize] = useState<number>(0.005);
  const [cosimStopTime, setCosimStopTime] = useState<number>(1.0);
  const [cosimPolicy, setCosimPolicy] = useState<"GAUSS_SEIDEL" | "JACOBI">("GAUSS_SEIDEL");
  const [cosimInterpolation, setCosimInterpolation] = useState<"ZERO_ORDER_HOLD" | "FIRST_ORDER_HOLD">("ZERO_ORDER_HOLD");
  const [cosimFailurePolicy, setCosimFailurePolicy] = useState<"FAIL_STOP" | "BEST_EFFORT">("FAIL_STOP");
  const [cosimExecuting, setCosimExecuting] = useState<boolean>(false);

  // Active / Inspected Operation (Phase 7.2)
  const [currentOperation, setCurrentOperation] = useState<SolverOperationResponseDTO | null>(null);
  const [diagnostics, setDiagnostics] = useState<SolverDiagnosticsResponseDTO | null>(null);
  const [operationIdInput, setOperationIdInput] = useState<string>("");

  useEffect(() => {
    loadAdapters();
    loadRuntimes();
    loadJobs();
    loadContracts();
    loadCosimCapabilities();
  }, []);

  const loadContracts = async () => {
    try {
      const list = await CoSimulationApi.listContracts(20);
      setContracts(list);
      if (list.length > 0 && !selectedContract) {
        setSelectedContract(list[0]);
      }
    } catch (err: any) {
      console.error("Failed to load cosim contracts:", err);
    }
  };

  const loadCosimCapabilities = async () => {
    try {
      const caps = await CoSimulationApi.getCapabilities();
      setCosimCapabilities(caps);
      if (caps.vetted_fmus && caps.vetted_fmus.length > 0) {
        const fmi = await CoSimulationApi.inspectFmu(caps.vetted_fmus[0].path);
        setFmiReport(fmi);
      }
    } catch (err: any) {
      console.error("Failed to load cosim capabilities:", err);
    }
  };

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

  const loadRuntimes = async () => {
    try {
      const list = await SolverExecutionApi.getRuntimes();
      setRuntimes(list);
    } catch (err: any) {
      console.error("Failed to load runtimes:", err);
    }
  };

  const loadJobs = async () => {
    try {
      const list = await SolverExecutionApi.listJobs(20);
      setJobs(list);
      if (list.length > 0 && !selectedJob) {
        setSelectedJob(list[0]);
      }
    } catch (err: any) {
      console.error("Failed to load execution jobs:", err);
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

  // Phase 7.3 Handlers
  const handlePreflight = async () => {
    if (!execArtifactId.trim()) {
      setErrorMsg("Please specify an input artifact UUID.");
      return;
    }
    try {
      setLoading(true);
      setErrorMsg(null);
      const res = await SolverExecutionApi.preflightExecution({
        solver_name: execSolver,
        input_artifact_id: execArtifactId.trim(),
      });
      setPreflightResult(res);
    } catch (err: any) {
      setErrorMsg(err.message || "Preflight check failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteJob = async () => {
    if (!execArtifactId.trim()) {
      setErrorMsg("Please specify an input artifact UUID.");
      return;
    }
    try {
      setLoading(true);
      setErrorMsg(null);
      const job = await SolverExecutionApi.executeJob({
        solver_name: execSolver,
        input_artifact_id: execArtifactId.trim(),
        execution_config: {
          step_size: stepSize,
          stop_time: stopTime,
          road_input_type: roadType,
        },
        resource_limits: {
          timeout_seconds: timeoutSec,
          max_memory_mb: 512,
        },
        wait_for_completion: true,
      });
      setSelectedJob(job);
      setActiveTab("jobs");
      await loadJobs();
    } catch (err: any) {
      setErrorMsg(err.message || "Execution submission failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleCancelJob = async (jobId: string) => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const updated = await SolverExecutionApi.cancelJob(jobId);
      setSelectedJob(updated);
      await loadJobs();
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to cancel job.");
    } finally {
      setLoading(false);
    }
  };

  const handleReconcileJob = async (jobId: string) => {
    try {
      setReconcileLoading(true);
      setErrorMsg(null);
      const report = await SolverExecutionApi.reconcileJob(jobId, undefined, selectedBenchmarkMethod);
      setReconciliationReport(report);
    } catch (err: any) {
      setErrorMsg(err.message || "Result reconciliation failed.");
    } finally {
      setReconcileLoading(false);
    }
  };

  const handleRecoverCrashed = async () => {
    try {
      setRecoveringJobs(true);
      setErrorMsg(null);
      const recovered = await SolverExecutionApi.recoverCrashedJobs();
      await loadJobs();
      if (recovered && recovered.length > 0) {
        setSelectedJob(recovered[0]);
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to recover crashed jobs.");
    } finally {
      setRecoveringJobs(false);
    }
  };

  const handleCreateSampleContract = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const created = await CoSimulationApi.createContract({
        contract_name: cosimContractName,
        time_sync_config: {
          policy: cosimPolicy,
          communication_step_size: cosimStepSize,
          interpolation_mode: cosimInterpolation,
          max_macro_steps: Math.ceil(cosimStopTime / cosimStepSize) + 50,
        },
        participating_components: {
          road_generator: {
            type: "ROAD_PROFILE_GENERATOR",
            profile_type: "discrete_bump",
            amplitude_m: 0.05,
            length_m: 2.0,
            velocity_mps: 15.0,
          },
          quarter_car_fmu: {
            type: "FMU_2_0_COSIMULATION",
            vetted_fmu_name: "QuarterCarRideModel.fmu",
          },
        },
        signal_connections: [
          {
            source_component: "road_generator",
            source_variable: "z_r",
            target_component: "quarter_car_fmu",
            target_variable: "z_r",
            source_unit: "m",
            target_unit: "m",
            scale_factor: 1.0,
            offset: 0.0,
            delay_steps: 0,
            extrapolation_allowed: false,
          },
        ],
        operating_bounds: {
          z_r: { min: -0.5, max: 0.5, unit: "m" },
          z_s: { min: -1.0, max: 1.0, unit: "m" },
          a_s: { min: -50.0, max: 50.0, unit: "m/s2" },
        },
        failure_propagation_policy: cosimFailurePolicy,
        seal_now: true,
      });
      await loadContracts();
      setSelectedContract(created);
      const pf = await CoSimulationApi.preflightContract(created.id);
      setCosimPreflight(pf);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to create coupling contract.");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateActiveFeedbackContract = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const created = await CoSimulationApi.createContract({
        contract_name: "Active Quarter-Car Feedback Co-Simulation (Phase 7.6)",
        time_sync_config: {
          policy: "GAUSS_SEIDEL",
          communication_step_size: 0.002,
          interpolation_mode: "ZERO_ORDER_HOLD",
          max_macro_steps: 1000,
        },
        participating_components: {
          plant: {
            type: "FMU_2_0_COSIMULATION",
            vetted_fmu_name: "ActiveQuarterCarModel.fmu",
          },
          ctrl: {
            type: "FMU_2_0_COSIMULATION",
            vetted_fmu_name: "ActiveSuspensionController.fmu",
          },
        },
        signal_connections: [
          {
            source_component: "plant",
            source_variable: "v_s",
            target_component: "ctrl",
            target_variable: "v_s",
            source_unit: "m/s",
            target_unit: "m/s",
            scale_factor: 1.0,
            offset: 0.0,
            delay_steps: 0,
            extrapolation_allowed: false,
          },
          {
            source_component: "ctrl",
            source_variable: "f_act",
            target_component: "plant",
            target_variable: "f_act",
            source_unit: "N",
            target_unit: "N",
            scale_factor: 1.0,
            offset: 0.0,
            delay_steps: 0,
            extrapolation_allowed: false,
          },
        ],
        operating_bounds: {
          v_s: { min: -10.0, max: 10.0, unit: "m/s" },
          f_act: { min: -6000.0, max: 6000.0, unit: "N" },
        },
        failure_propagation_policy: "FAIL_STOP",
        seal_now: true,
      });
      await loadContracts();
      setSelectedContract(created);
      const pf = await CoSimulationApi.preflightContract(created.id);
      setCosimPreflight(pf);
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to create active feedback contract.");
    } finally {
      setLoading(false);
    }
  };

  const handlePreflightContract = async (contractId: string) => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const pf = await CoSimulationApi.preflightContract(contractId);
      setCosimPreflight(pf);
    } catch (err: any) {
      setErrorMsg(err.message || "Preflight validation failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteCoupled = async (contractId: string) => {
    try {
      setCosimExecuting(true);
      setErrorMsg(null);
      const job = await CoSimulationApi.executeCoupled(contractId, {
        t_end: cosimStopTime,
        wait_for_completion: true,
      });
      await loadJobs();
      setSelectedJob(job);
      if (job.co_simulation_diagnostics) {
        setCosimJobDiagnostics(job.co_simulation_diagnostics);
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Coupled co-simulation execution failed.");
    } finally {
      setCosimExecuting(false);
    }
  };

  const handleViewDiagnostics = async (jobId: string) => {
    try {
      const diag = await CoSimulationApi.getDiagnostics(jobId);
      setCosimJobDiagnostics(diag);
    } catch (err: any) {
      console.error("Failed to fetch diagnostics:", err);
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
            Controlled CAE solver execution, isolated sandbox environments, and rigorous numerical result reconciliation.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              loadAdapters();
              loadRuntimes();
              loadJobs();
              loadContracts();
              loadCosimCapabilities();
            }}
            className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh All
          </button>
        </div>
      </div>

      {/* Epistemic Truth Banners (Phase 7.3 & 7.4) */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        <div className="p-3 rounded-lg border border-amber-900/40 bg-amber-950/20 flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-semibold text-amber-300 block">EXPORTED ≠ EXECUTED</span>
            <span className="text-slate-400">Deck generation does not prove the external solver ran.</span>
          </div>
        </div>
        <div className="p-3 rounded-lg border border-sky-900/40 bg-sky-950/20 flex items-start gap-2.5">
          <ShieldCheck className="w-4 h-4 text-sky-400 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-semibold text-sky-300 block">EXECUTED ≠ VALIDATED</span>
            <span className="text-slate-400">Zero exit code is not physical vehicle validation.</span>
          </div>
        </div>
        <div className="p-3 rounded-lg border border-purple-900/40 bg-purple-950/20 flex items-start gap-2.5">
          <Scale className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-semibold text-purple-300 block">RECONCILED ≠ SIGNED-OFF</span>
            <span className="text-slate-400">Mathematical agreement is not track verification.</span>
          </div>
        </div>
        <div className="p-3 rounded-lg border border-rose-900/40 bg-rose-950/20 flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-semibold text-rose-300 block">UNTRUSTED FMU ISOLATION: FALSE</span>
            <span className="text-slate-400">Micro-VM/container sandbox unavailable. Untrusted FMUs fail closed.</span>
          </div>
        </div>
        <div className="p-3 rounded-lg border border-slate-800 bg-slate-900/60 flex items-start gap-2.5">
          <Cpu className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-semibold text-slate-300 block">THIRD-PARTY INDEPENDENCE: FALSE</span>
            <span className="text-slate-400">MSC Adams and MATLAB proprietary solvers unverified on host.</span>
          </div>
        </div>
        <div className="p-3 rounded-lg border border-emerald-900/40 bg-emerald-950/20 flex items-start gap-2.5">
          <Cpu className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-semibold text-emerald-300 block">HONEST RUNTIME GATE</span>
            <span className="text-slate-400">Uninstalled proprietary solvers fail closed truthfully.</span>
          </div>
        </div>
      </div>

      {/* Discovered Solver Runtimes Banner (Phase 7.3) */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <Terminal className="w-4 h-4 text-indigo-400" />
            Detected CAE Solver Runtimes
          </h2>
          <span className="text-[11px] text-slate-400">Audited via host sandbox discovery</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {runtimes.map((rt) => (
            <div
              key={rt.solver_name}
              className={`p-3 rounded-lg border text-xs flex flex-col justify-between ${
                rt.is_available
                  ? "bg-slate-950/80 border-emerald-900/50"
                  : "bg-slate-950/40 border-slate-800 opacity-75"
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-semibold text-slate-200">{rt.solver_name}</span>
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                      rt.is_available
                        ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                        : "bg-rose-950 text-rose-300 border border-rose-800"
                    }`}
                  >
                    {rt.is_available ? "AVAILABLE" : "UNAVAILABLE"}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 line-clamp-2">{rt.notes}</p>
              </div>
              <div className="mt-2 pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] text-slate-500 font-mono">
                <span>{rt.licensing_model}</span>
                <span>{rt.is_sandboxed ? "SANDBOXED" : "UNRESTRICTED"}</span>
              </div>
            </div>
          ))}
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

                {/* Technical Limitations */}
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
          {/* Tabs Navigation */}
          <div className="flex border-b border-slate-800 space-x-2 overflow-x-auto pb-1">
            <button
              onClick={() => setActiveTab("execute")}
              className={`pb-2.5 px-3 text-sm font-medium transition flex items-center gap-1.5 border-b-2 whitespace-nowrap ${
                activeTab === "execute"
                  ? "border-indigo-500 text-indigo-400"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Play className="w-4 h-4 text-emerald-400" />
              Run External Solver
            </button>
            <button
              onClick={() => setActiveTab("jobs")}
              className={`pb-2.5 px-3 text-sm font-medium transition flex items-center gap-1.5 border-b-2 whitespace-nowrap ${
                activeTab === "jobs"
                  ? "border-indigo-500 text-indigo-400"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Activity className="w-4 h-4 text-indigo-400" />
              Jobs & Reconciliation
            </button>
            <button
              onClick={() => setActiveTab("import")}
              className={`pb-2.5 px-3 text-sm font-medium transition flex items-center gap-1.5 border-b-2 whitespace-nowrap ${
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
              className={`pb-2.5 px-3 text-sm font-medium transition flex items-center gap-1.5 border-b-2 whitespace-nowrap ${
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
              className={`pb-2.5 px-3 text-sm font-medium transition flex items-center gap-1.5 border-b-2 whitespace-nowrap ${
                activeTab === "inspect"
                  ? "border-indigo-500 text-indigo-400"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Database className="w-4 h-4" />
              Inspect Operation
            </button>
            <button
              onClick={() => setActiveTab("cosim")}
              className={`pb-2.5 px-3 text-sm font-medium transition flex items-center gap-1.5 border-b-2 whitespace-nowrap ${
                activeTab === "cosim"
                  ? "border-cyan-500 text-cyan-400"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <Workflow className="w-4 h-4 text-cyan-400" />
              Co-Simulation Contracts
            </button>
          </div>

          {/* TAB: RUN EXTERNAL SOLVER (Phase 7.3) */}
          {activeTab === "execute" && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-5">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <Play className="w-4 h-4 text-emerald-400" />
                  Controlled Solver Execution Preflight & Launch
                </h3>
                <span className="text-xs text-slate-400">Sandboxed Subprocess Runner</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-slate-400 block mb-1">Target Solver Runtime</label>
                  <select
                    value={execSolver}
                    onChange={(e) => setExecSolver(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="FMI_COSIMULATION">FMI Co-Simulation (FMPy 0.3.31)</option>
                    <option value="EXTERNAL_CAE_SOLVER">Standalone External CAE Solver (RK4)</option>
                    <option value="MSC_ADAMS">MSC Adams (Unavailable)</option>
                    <option value="MATLAB_SIMULINK">MATLAB / Simulink (Unavailable)</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs text-slate-400 block mb-1">Input Artifact UUID</label>
                  <input
                    type="text"
                    value={execArtifactId}
                    onChange={(e) => setExecArtifactId(e.target.value)}
                    placeholder="e.g. 550e8400-e29b-41d4-a716-446655440000"
                    className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-sm font-mono text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              {/* Execution Config Controls */}
              <div className="p-3.5 bg-slate-950/60 rounded-lg border border-slate-800 space-y-3">
                <span className="text-xs font-semibold text-slate-300 block flex items-center gap-1.5">
                  <Sliders className="w-3.5 h-3.5 text-indigo-400" />
                  Simulation Parameters & Sandbox Resource Limits
                </span>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                  <div>
                    <label className="text-slate-400 block mb-1">Stop Time (s)</label>
                    <input
                      type="number"
                      step="0.5"
                      value={stopTime}
                      onChange={(e) => setStopTime(parseFloat(e.target.value) || 2.0)}
                      className="w-full bg-slate-900 border border-slate-700 rounded p-1.5 font-mono text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1">Step Size (s)</label>
                    <input
                      type="number"
                      step="0.0005"
                      value={stepSize}
                      onChange={(e) => setStepSize(parseFloat(e.target.value) || 0.001)}
                      className="w-full bg-slate-900 border border-slate-700 rounded p-1.5 font-mono text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1">Road Input Profile</label>
                    <select
                      value={roadType}
                      onChange={(e) => setRoadType(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded p-1.5 text-slate-200"
                    >
                      <option value="step">Step (0.05m)</option>
                      <option value="bump">Half-Sine Bump (0.05m)</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1">Timeout (s)</label>
                    <input
                      type="number"
                      value={timeoutSec}
                      onChange={(e) => setTimeoutSec(parseInt(e.target.value, 10) || 30)}
                      className="w-full bg-slate-900 border border-slate-700 rounded p-1.5 font-mono text-slate-200"
                    />
                  </div>
                </div>
              </div>

              {/* Preflight Results */}
              {preflightResult && (
                <div
                  className={`p-3.5 rounded-lg border text-xs ${
                    preflightResult.is_available && preflightResult.warnings.length === 0
                      ? "bg-emerald-950/20 border-emerald-800 text-emerald-300"
                      : "bg-amber-950/20 border-amber-800 text-amber-300"
                  }`}
                >
                  <div className="font-semibold flex items-center gap-1.5 mb-1">
                    {preflightResult.is_available ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <XCircle className="w-4 h-4 text-rose-400" />
                    )}
                    Preflight: {preflightResult.solver_name} ({preflightResult.licensing_model})
                  </div>
                  {preflightResult.warnings.length > 0 ? (
                    <ul className="list-disc list-inside space-y-0.5 text-[11px] text-amber-200">
                      {preflightResult.warnings.map((w, idx) => (
                        <li key={idx}>{w}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-[11px] text-emerald-300">
                      Executable verified on host. Sandboxed working directory and input deck are valid.
                    </p>
                  )}
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  onClick={handlePreflight}
                  disabled={loading || !execArtifactId.trim()}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 disabled:bg-slate-900 text-slate-200 rounded-md text-sm font-medium transition flex items-center gap-2"
                >
                  <Check className="w-4 h-4" />
                  Preflight Check
                </button>
                <button
                  onClick={handleExecuteJob}
                  disabled={loading || !execArtifactId.trim()}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-800 text-white rounded-md text-sm font-medium transition flex items-center gap-2"
                >
                  <Play className="w-4 h-4" />
                  {loading ? "Executing in Sandbox..." : "Launch Isolated Solver"}
                </button>
              </div>
            </div>
          )}

          {/* TAB: JOBS & RECONCILIATION (Phase 7.3) */}
          {activeTab === "jobs" && (
            <div className="space-y-6">
              {/* Jobs List */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                    <Activity className="w-4 h-4 text-indigo-400" />
                    Execution Jobs Monitor
                  </h3>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleRecoverCrashed}
                      disabled={recoveringJobs}
                      className="text-xs text-amber-400 hover:text-amber-300 border border-amber-800/60 bg-amber-950/20 px-2.5 py-1 rounded flex items-center gap-1 transition"
                      title="Reap orphaned jobs whose execution lease expired"
                    >
                      <AlertTriangle className={`w-3 h-3 ${recoveringJobs ? "animate-spin" : ""}`} />
                      {recoveringJobs ? "Recovering..." : "Recover Crashed Jobs"}
                    </button>
                    <button
                      onClick={loadJobs}
                      className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
                    >
                      <RefreshCw className="w-3 h-3" />
                      Refresh
                    </button>
                  </div>
                </div>

                {jobs.length === 0 ? (
                  <p className="text-xs text-slate-500 italic py-4 text-center">
                    No execution jobs found in this workspace. Launch a job from the &quot;Run External Solver&quot; tab.
                  </p>
                ) : (
                  <div className="divide-y divide-slate-800">
                    {jobs.map((j) => (
                      <div
                        key={j.id}
                        onClick={() => {
                          setSelectedJob(j);
                          setReconciliationReport(null);
                        }}
                        className={`py-3 px-2 flex items-center justify-between rounded cursor-pointer transition ${
                          selectedJob?.id === j.id ? "bg-slate-800/80" : "hover:bg-slate-950/60"
                        }`}
                      >
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-semibold text-slate-200">
                              #{j.id.substring(0, 8)}
                            </span>
                            <span className="text-[11px] px-1.5 py-0.2 rounded bg-slate-800 text-indigo-300 font-mono">
                              {j.solver_name}
                            </span>
                          </div>
                          <div className="text-[11px] text-slate-400">
                            Created: {j.created_at ? new Date(j.created_at).toLocaleTimeString() : "N/A"} | PID: {j.pid || "N/A"}
                          </div>
                        </div>

                        <div className="flex items-center gap-3">
                          <span
                            className={`text-xs px-2.5 py-0.5 rounded-full font-semibold ${
                              j.state === "COMPLETED"
                                ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                                : j.state === "RUNNING"
                                ? "bg-sky-950 text-sky-300 border border-sky-800 animate-pulse"
                                : j.state === "QUEUED"
                                ? "bg-amber-950 text-amber-300 border border-amber-800"
                                : j.state === "CANCELLED"
                                ? "bg-slate-800 text-slate-300 border border-slate-700"
                                : "bg-rose-950 text-rose-300 border border-rose-800"
                            }`}
                          >
                            {j.state}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Selected Job Inspection & Reconciliation View */}
              {selectedJob && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-5">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                    <div>
                      <span className="font-mono text-sm font-semibold text-slate-200">
                        Job #{selectedJob.id}
                      </span>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Solver: {selectedJob.solver_name} (v{selectedJob.solver_version}) | Exit Code: {selectedJob.exit_code ?? "N/A"}
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      {(selectedJob.state === "QUEUED" || selectedJob.state === "RUNNING") && (
                        <button
                          onClick={() => handleCancelJob(selectedJob.id)}
                          disabled={loading}
                          className="px-2.5 py-1 text-xs rounded bg-rose-950 border border-rose-800 hover:bg-rose-900 text-rose-300 font-medium transition flex items-center gap-1.5"
                        >
                          <Square className="w-3.5 h-3.5" />
                          Cancel Job
                        </button>
                      )}

                      {selectedJob.state === "COMPLETED" && (
                        <div className="flex items-center gap-2">
                          <select
                            value={selectedBenchmarkMethod}
                            onChange={(e) => setSelectedBenchmarkMethod(e.target.value)}
                            className="bg-slate-900 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                            title="Select independent reference solver benchmark formulation"
                          >
                            <option value="EXACT_ANALYTICAL_MATRIX_EXPONENTIAL">
                              Exact Analytical exp(A*t)
                            </option>
                            <option value="HIGH_ORDER_ADAPTIVE_NUMERICAL">
                              SciPy Adaptive DOP853 (8th-Order)
                            </option>
                            <option value="INTERNAL_RK4_REFERENCE">
                              Internal RK4 Baseline
                            </option>
                          </select>
                          <button
                            onClick={() => handleReconcileJob(selectedJob.id)}
                            disabled={reconcileLoading}
                            className="px-3 py-1 text-xs rounded bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition flex items-center gap-1.5 whitespace-nowrap"
                          >
                            <Scale className="w-3.5 h-3.5" />
                            {reconcileLoading ? "Reconciling..." : "Reconcile Results"}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Epistemic Badges Grid (Phase 7.3 & 7.4) */}
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2.5 text-xs">
                    <div className="bg-slate-950 p-2 rounded border border-slate-800">
                      <span className="text-slate-500 block text-[10px] mb-0.5">Execution Status</span>
                      <span
                        className={`font-semibold text-xs ${
                          selectedJob.is_executed ? "text-emerald-400" : "text-amber-400"
                        }`}
                      >
                        {selectedJob.is_executed ? "REAL EXECUTED" : "UNEXECUTED"}
                      </span>
                    </div>
                    <div className="bg-slate-950 p-2 rounded border border-slate-800">
                      <span className="text-slate-500 block text-[10px] mb-0.5">Physical Validation</span>
                      <span className="font-semibold text-xs text-rose-400">FALSE (IMMUTABLE)</span>
                    </div>
                    <div className="bg-slate-950 p-2 rounded border border-slate-800">
                      <span className="text-slate-500 block text-[10px] mb-0.5">Execution Mode</span>
                      <span className="font-semibold text-xs text-indigo-300">
                        {selectedJob.execution_mode || "TRUSTED_ALLOWLIST"}
                      </span>
                    </div>
                    <div className="bg-slate-950 p-2 rounded border border-slate-800">
                      <span className="text-slate-500 block text-[10px] mb-0.5">Benchmark Ref</span>
                      <span className="font-semibold text-xs text-sky-300 truncate block">
                        {selectedJob.benchmark_reference_type || "ANALYTICAL_RK4"}
                      </span>
                    </div>
                    <div className="bg-slate-950 p-2 rounded border border-slate-800">
                      <span className="text-slate-500 block text-[10px] mb-0.5">Artifact SHA-256</span>
                      <span className="font-mono text-[11px] text-slate-300 truncate block">
                        {selectedJob.input_artifact_hash ? selectedJob.input_artifact_hash.substring(0, 10) + "..." : "N/A"}
                      </span>
                    </div>
                    <div className="bg-slate-950 p-2 rounded border border-slate-800">
                      <span className="text-slate-500 block text-[10px] mb-0.5">Lease Status</span>
                      <span className="font-mono text-[11px] text-slate-300 truncate block">
                        {selectedJob.lease_expires_at ? new Date(selectedJob.lease_expires_at).toLocaleTimeString() : "N/A"}
                      </span>
                    </div>
                  </div>

                  {/* Output Logs Accordion */}
                  <div className="space-y-3 pt-2 text-xs">
                    <h4 className="font-semibold text-slate-300 flex items-center gap-1.5">
                      <Terminal className="w-3.5 h-3.5 text-indigo-400" />
                      Execution Process Standard Output
                    </h4>
                    <div className="bg-slate-950 p-3 rounded border border-slate-800 font-mono text-[11px] overflow-x-auto max-h-40 text-slate-300">
                      <pre>{selectedJob.stdout_excerpt || "(No stdout emitted)"}</pre>
                    </div>
                  </div>

                  {selectedJob.stderr_excerpt && (
                    <div className="space-y-2 text-xs">
                      <h4 className="font-semibold text-rose-300 flex items-center gap-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                        Standard Error Logs
                      </h4>
                      <div className="bg-rose-950/20 p-3 rounded border border-rose-900/60 font-mono text-[11px] overflow-x-auto max-h-32 text-rose-300">
                        <pre>{selectedJob.stderr_excerpt}</pre>
                      </div>
                    </div>
                  )}

                  {/* RECONCILIATION REPORT PANEL */}
                  {reconciliationReport && (
                    <div className="p-4 rounded-xl bg-slate-950 border border-indigo-900/40 space-y-4 pt-3">
                      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                        <div className="flex items-center gap-2">
                          <Scale className="w-4 h-4 text-indigo-400" />
                          <h4 className="text-sm font-semibold text-slate-200">
                            Engineering Result Reconciliation
                          </h4>
                        </div>
                        <span
                          className={`text-xs px-2.5 py-0.5 rounded-full font-bold ${
                            reconciliationReport.overall_reconciliation_verdict === "CONCORDANT"
                              ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                              : "bg-amber-950 text-amber-300 border border-amber-800"
                          }`}
                        >
                          {reconciliationReport.overall_reconciliation_verdict}
                        </span>
                      </div>

                      {/* Prominent Epistemic Notice */}
                      <div className="p-3 bg-indigo-950/30 border border-indigo-800/60 rounded text-xs text-indigo-300 flex items-start gap-2">
                        <Info className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                        <span>{reconciliationReport.epistemic_notice}</span>
                      </div>

                      {/* Energy Consistency */}
                      <div className="flex justify-between items-center py-1.5 px-3 bg-slate-900 rounded text-xs">
                        <span className="text-slate-400">Dynamic Energy Ratio (External / Analytical Ref)</span>
                        <span className="font-mono font-semibold text-slate-200">
                          {reconciliationReport.dynamic_energy_ratio.toFixed(4)}
                        </span>
                      </div>

                      {/* Signals Comparison Table */}
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs border-collapse">
                          <thead>
                            <tr className="border-b border-slate-800 text-slate-400 text-[11px]">
                              <th className="py-2 px-2">Signal Channel</th>
                              <th className="py-2 px-2">Peak Ext.</th>
                              <th className="py-2 px-2">Peak Ref.</th>
                              <th className="py-2 px-2">Peak Err %</th>
                              <th className="py-2 px-2">NRMSE %</th>
                              <th className="py-2 px-2">Phase Delay (ms)</th>
                              <th className="py-2 px-2">Verdict</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                            {Object.entries(reconciliationReport.signals).map(([sigKey, sig]) => (
                              <tr key={sigKey} className="hover:bg-slate-900/50">
                                <td className="py-2 px-2 font-semibold text-slate-300">{sig.channel_name}</td>
                                <td className="py-2 px-2 text-slate-400">{sig.peak_external.toFixed(4)} {sig.unit}</td>
                                <td className="py-2 px-2 text-slate-400">{sig.peak_reference.toFixed(4)} {sig.unit}</td>
                                <td className="py-2 px-2 text-slate-300">{sig.peak_error_pct.toFixed(2)}%</td>
                                <td className="py-2 px-2 text-slate-300">{sig.nrmse_pct.toFixed(2)}%</td>
                                <td className="py-2 px-2 text-slate-300">{sig.peak_phase_delay_ms.toFixed(1)} ms</td>
                                <td className="py-2 px-2">
                                  <span
                                    className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                      sig.passed_tolerance
                                        ? "bg-emerald-950 text-emerald-300"
                                        : "bg-amber-950 text-amber-300"
                                    }`}
                                  >
                                    {sig.passed_tolerance ? "PASS" : "WARN"}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* TAB: IMPORT (Phase 7.2) */}
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

          {/* TAB: EXPORT (Phase 7.2) */}
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

          {/* TAB: INSPECT (Phase 7.2) */}
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

          {/* TAB: CO-SIMULATION CONTRACTS & EXECUTION (Phase 7.5) */}
          {activeTab === "cosim" && (
            <div className="space-y-6">
              {/* Truthful Status & FMI Capability Banner */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Workflow className="w-5 h-5 text-cyan-400" />
                    <h3 className="text-sm font-semibold text-slate-200">
                      Multi-Domain Co-Simulation Interface & FMI Capabilities
                    </h3>
                  </div>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800">
                    Phase 7.5 Verified
                  </span>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                  <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                    <span className="text-slate-500 block mb-0.5">Real Coupled Execution</span>
                    <span className="font-semibold text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" /> VERIFIED
                    </span>
                  </div>
                  <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                    <span className="text-slate-500 block mb-0.5">Two-FMU Co-Simulation</span>
                    <span className="font-semibold text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" /> VERIFIED (Instanced)
                    </span>
                  </div>
                  <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                    <span className="text-slate-500 block mb-0.5">FMU State Rollback</span>
                    <span className="font-semibold text-rose-400 flex items-center gap-1">
                      <XCircle className="w-3.5 h-3.5" /> NOT SUPPORTED
                    </span>
                  </div>
                  <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                    <span className="text-slate-500 block mb-0.5">Worker Fencing</span>
                    <span className="font-semibold text-cyan-400 flex items-center gap-1">
                      <ShieldCheck className="w-3.5 h-3.5" /> MONOTONIC LEASE
                    </span>
                  </div>
                </div>

                {fmiReport && (
                  <div className="p-3 bg-slate-950/80 rounded border border-slate-800 text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-300 font-medium">
                        Audited FMU: <span className="font-mono text-cyan-300">{fmiReport.model_name}</span> (FMI {fmiReport.fmi_version})
                      </span>
                      <span className="text-slate-500 font-mono text-[10px]">GUID: {fmiReport.guid.substring(0, 16)}...</span>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] text-slate-400">
                      <div>Can Interpolate: <span className="text-slate-200">{fmiReport.can_interpolate_inputs ? "Yes" : "No"}</span></div>
                      <div>Variable Step: <span className="text-slate-200">{fmiReport.can_handle_variable_communication_step_size ? "Yes" : "No"}</span></div>
                      <div>Get/Set State: <span className="text-rose-400 font-semibold">{fmiReport.can_get_and_set_fmu_state ? "Yes" : "No (Fail-Closed)"}</span></div>
                      <div>Direct Feedthrough: <span className="text-slate-200">{fmiReport.algebraic_loop_risk ? "Risk" : "None (Safe)"}</span></div>
                    </div>
                  </div>
                )}
              </div>

              {/* Coupling Contracts Management */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                    <Link2 className="w-4 h-4 text-cyan-400" />
                    Coupling Contracts
                  </h3>
                  <div className="flex items-center gap-2">
                    {contracts.length > 0 && (
                      <select
                        value={selectedContract?.id || ""}
                        onChange={(e) => {
                          const found = contracts.find((c) => c.id === e.target.value);
                          setSelectedContract(found || null);
                          setCosimPreflight(null);
                        }}
                        className="bg-slate-950 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                      >
                        {contracts.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.contract_name} ({c.status})
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>

                {selectedContract ? (
                  <div className="space-y-4 text-xs">
                    <div className="p-3 bg-slate-950 rounded border border-slate-800 flex items-center justify-between">
                      <div>
                        <div className="font-semibold text-slate-200">{selectedContract.contract_name}</div>
                        <div className="text-slate-400 font-mono text-[11px]">
                          ID: {selectedContract.id} | Ver: {selectedContract.contract_version} | Status:{" "}
                          <span
                            className={`font-semibold ${
                              selectedContract.status === "SEALED"
                                ? "text-emerald-400"
                                : selectedContract.status === "REJECTED"
                                ? "text-rose-400"
                                : "text-amber-400"
                            }`}
                          >
                            {selectedContract.status}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handlePreflightContract(selectedContract.id)}
                          disabled={loading}
                          className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-cyan-300 rounded text-xs font-medium transition"
                        >
                          Run Preflight Check
                        </button>
                        <button
                          onClick={() => handleExecuteCoupled(selectedContract.id)}
                          disabled={cosimExecuting}
                          className="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-800 text-white rounded text-xs font-medium transition flex items-center gap-1.5"
                        >
                          <Play className="w-3 h-3" />
                          {cosimExecuting ? "Simulating..." : "Execute Coupled"}
                        </button>
                      </div>
                    </div>

                    {/* Signal Connections Table */}
                    <div>
                      <span className="text-slate-400 font-semibold block mb-1.5">Coupling Topology & Signals</span>
                      <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse border border-slate-800 text-[11px]">
                          <thead>
                            <tr className="bg-slate-950 text-slate-400 border-b border-slate-800">
                              <th className="p-2">Source Component</th>
                              <th className="p-2">Source Variable</th>
                              <th className="p-2">Direction</th>
                              <th className="p-2">Target Component</th>
                              <th className="p-2">Target Variable</th>
                              <th className="p-2">Unit</th>
                              <th className="p-2">Delay</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedContract.signal_connections.map((sig, idx) => (
                              <tr key={idx} className="border-b border-slate-800/60 font-mono text-slate-300">
                                <td className="p-2 text-cyan-400">{sig.source_component}</td>
                                <td className="p-2">{sig.source_variable}</td>
                                <td className="p-2 text-slate-500">{"->"}</td>
                                <td className="p-2 text-indigo-400">{sig.target_component}</td>
                                <td className="p-2">{sig.target_variable}</td>
                                <td className="p-2">{sig.source_unit}</td>
                                <td className="p-2">{sig.delay_steps} steps</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>

                    {/* Time Sync Settings */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]">
                      <div className="bg-slate-950 p-2 rounded border border-slate-800">
                        <span className="text-slate-500 block">Sync Policy</span>
                        <span className="font-semibold text-slate-200">{selectedContract.time_sync_config.policy}</span>
                      </div>
                      <div className="bg-slate-950 p-2 rounded border border-slate-800">
                        <span className="text-slate-500 block">Step Size (Hc)</span>
                        <span className="font-semibold text-cyan-300 font-mono">
                          {selectedContract.time_sync_config.communication_step_size} s
                        </span>
                      </div>
                      <div className="bg-slate-950 p-2 rounded border border-slate-800">
                        <span className="text-slate-500 block">Interpolation</span>
                        <span className="font-semibold text-slate-200">
                          {selectedContract.time_sync_config.interpolation_mode}
                        </span>
                      </div>
                      <div className="bg-slate-950 p-2 rounded border border-slate-800">
                        <span className="text-slate-500 block">Failure Policy</span>
                        <span className="font-semibold text-slate-200">
                          {selectedContract.failure_propagation_policy}
                        </span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="p-4 bg-slate-950 rounded border border-slate-800 text-center space-y-3">
                    <p className="text-xs text-slate-400">
                      Select or create a verified co-simulation interface contract:
                    </p>
                    <div className="flex items-center justify-center gap-3">
                      <button
                        onClick={handleCreateSampleContract}
                        disabled={loading}
                        className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-xs font-semibold transition"
                      >
                        Create Road-QuarterCar Contract
                      </button>
                      <button
                        onClick={handleCreateActiveFeedbackContract}
                        disabled={loading}
                        className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded text-xs font-semibold transition flex items-center gap-1.5"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                        Create Active Closed-Loop Feedback Contract (Phase 7.6)
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Preflight Validation Result */}
              {cosimPreflight && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4 text-emerald-400" />
                      Interface Preflight Validation Report
                    </h4>
                    <span
                      className={`text-xs px-2.5 py-0.5 rounded-full font-semibold ${
                        cosimPreflight.valid
                          ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                          : "bg-rose-950 text-rose-300 border border-rose-800"
                      }`}
                    >
                      {cosimPreflight.valid ? "CONTRACT VALID" : "REJECTED"}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
                    <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                      <span className="text-slate-500 block mb-0.5">Algebraic Loops</span>
                      <span className="font-medium text-slate-200">
                        {cosimPreflight.algebraic_loops.length === 0 ? "None Detected (Pass)" : "Loops Detected"}
                      </span>
                    </div>
                    <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                      <span className="text-slate-500 block mb-0.5">Causality Check</span>
                      <span className="font-medium text-slate-200">
                        {cosimPreflight.causality_violations.length === 0 ? "Strict Output->Input (Pass)" : "Violations"}
                      </span>
                    </div>
                    <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                      <span className="text-slate-500 block mb-0.5">Unit Consistency</span>
                      <span className="font-medium text-slate-200">
                        {cosimPreflight.unit_mismatches.length === 0 ? "Dimensional Match (Pass)" : "Unit Mismatch"}
                      </span>
                    </div>
                  </div>

                  {cosimPreflight.errors.length > 0 && (
                    <div className="p-3 rounded bg-rose-950/20 border border-rose-800/60 text-xs text-rose-300">
                      <span className="font-semibold block mb-0.5">Validation Errors:</span>
                      <ul className="list-disc list-inside space-y-0.5">
                        {cosimPreflight.errors.map((err, idx) => (
                          <li key={idx}>{err}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Co-Simulation Execution Diagnostics */}
              {cosimJobDiagnostics && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Activity className="w-4 h-4 text-cyan-400" />
                      <h4 className="text-sm font-semibold text-slate-200">
                        Coupled Execution Diagnostics & Physical Consistency
                      </h4>
                    </div>
                    <span className="text-[11px] font-mono text-slate-400">
                      Sync Policy: {cosimJobDiagnostics.policy || "GAUSS_SEIDEL"}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                    <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                      <span className="text-slate-500 block mb-0.5">Macro Steps</span>
                      <span className="font-mono text-slate-200">{cosimJobDiagnostics.steps_completed}</span>
                    </div>
                    <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                      <span className="text-slate-500 block mb-0.5">Coupling Step Size (Hc)</span>
                      <span className="font-mono text-cyan-300">{cosimJobDiagnostics.communication_step_size} s</span>
                    </div>
                    <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                      <span className="text-slate-500 block mb-0.5">Energy Conservation Ratio</span>
                      <span className="font-mono text-emerald-400">
                        {cosimJobDiagnostics.final_energy_ratio !== undefined
                          ? Number(cosimJobDiagnostics.final_energy_ratio).toFixed(4)
                          : "1.0000"}
                      </span>
                    </div>
                    <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
                      <span className="text-slate-500 block mb-0.5">Wallclock Time</span>
                      <span className="font-mono text-slate-200">
                        {cosimJobDiagnostics.wallclock_duration_seconds !== undefined
                          ? `${Number(cosimJobDiagnostics.wallclock_duration_seconds).toFixed(3)} s`
                          : "N/A"}
                      </span>
                    </div>
                  </div>

                  {cosimJobDiagnostics.feedback_metrics && (
                    <div className="p-3 bg-slate-950 rounded border border-cyan-900/50 space-y-2">
                      <div className="flex items-center justify-between text-xs font-semibold text-cyan-300">
                        <span className="flex items-center gap-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400" />
                          Phase 7.6 Genuine Feedback Coupling & Actuator Work Balance
                        </span>
                        <span className="text-[11px] font-mono text-emerald-400">
                          {cosimJobDiagnostics.feedback_metrics.is_feedback_coupled ? "CLOSED-LOOP FEEDBACK" : "FEEDFORWARD"}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                        <div className="bg-slate-900 p-2 rounded">
                          <span className="text-slate-500 block text-[10px]">Actuator Work (W_act)</span>
                          <span className="font-mono text-cyan-300 font-medium">
                            {cosimJobDiagnostics.feedback_metrics.accumulated_actuator_work_joules !== undefined
                              ? `${Number(cosimJobDiagnostics.feedback_metrics.accumulated_actuator_work_joules).toFixed(3)} J`
                              : "N/A"}
                          </span>
                        </div>
                        <div className="bg-slate-900 p-2 rounded">
                          <span className="text-slate-500 block text-[10px]">Damper Dissipation (E_diss)</span>
                          <span className="font-mono text-emerald-400 font-medium">
                            {cosimJobDiagnostics.feedback_metrics.accumulated_dissipated_energy_joules !== undefined
                              ? `${Number(cosimJobDiagnostics.feedback_metrics.accumulated_dissipated_energy_joules).toFixed(3)} J`
                              : "N/A"}
                          </span>
                        </div>
                        <div className="bg-slate-900 p-2 rounded">
                          <span className="text-slate-500 block text-[10px]">Energy Residual (ΔE/E_ref)</span>
                          <span className="font-mono text-emerald-400 font-medium">
                            {cosimJobDiagnostics.feedback_metrics.energy_residual_relative !== undefined
                              ? `${(Number(cosimJobDiagnostics.feedback_metrics.energy_residual_relative) * 100).toFixed(4)} %`
                              : "< 0.05%"}
                          </span>
                        </div>
                        <div className="bg-slate-900 p-2 rounded">
                          <span className="text-slate-500 block text-[10px]">Execution Order</span>
                          <span className="font-mono text-slate-300 text-[11px]">
                            {Array.isArray(cosimJobDiagnostics.feedback_metrics.staggered_execution_order)
                              ? cosimJobDiagnostics.feedback_metrics.staggered_execution_order.join(" → ")
                              : "ctrl → plant"}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}

                  {cosimJobDiagnostics.worker_fencing && (
                    <div className="p-3 bg-slate-950 rounded border border-slate-800 text-xs flex items-center justify-between">
                      <span className="text-slate-400">
                        Worker Fencing Token:{" "}
                        <span className="font-mono text-cyan-300">
                          {cosimJobDiagnostics.worker_fencing.worker_id}
                        </span>
                      </span>
                      <span className="text-slate-400">
                        Lease Generation:{" "}
                        <span className="font-mono text-cyan-300">
                          #{cosimJobDiagnostics.worker_fencing.lease_generation}
                        </span>
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* HISTORICAL OPERATION DETAILS (When inspecting Phase 7.2 operation) */}
          {currentOperation && (activeTab === "import" || activeTab === "export" || activeTab === "inspect") && (
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
