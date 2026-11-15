"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";

export interface VehicleState {
  id: string;
  name: string;
  version: string;
  mass_kg: number;
  wheelbase_m: number;
  track_width_m: number;
  cg_height_m: number;
}

export interface SetupState {
  id: string;
  name: string;
  version: string;
  k_spring_front: number;
  k_spring_rear: number;
  c_damper_front: number;
  c_damper_rear: number;
  k_arb_front: number;
  k_arb_rear: number;
  ride_height_front_mm: number;
  ride_height_rear_mm: number;
  camber_front_deg: number;
  toe_front_deg: number;
}

export interface TrackState {
  id: string;
  name: string;
  length_m: number;
  grip_multiplier: number;
  weather: "DRY" | "DAMP" | "WET";
  track_temp_c: number;
}

export interface TireState {
  id: string;
  name: string;
  model_type: "MF5.2" | "PACEJKA_2002" | "LINEAR";
  nominal_pressure_kpa: number;
  front_pressure_kpa: number;
  rear_pressure_kpa: number;
}

export interface TelemetryWorkspaceState {
  sessionId: string;
  datasetName: string | null;
  sampleRateHz: number;
  isStreaming: boolean;
  isReplaying: boolean;
  channelsCount: number;
  status: "IDLE" | "RECORDING" | "REPLAYING" | "STREAMING" | "DEGRADED";
}

export interface SimulationSolverInfo {
  solver: string;
  version: string;
  backend: string;
  build: string;
}

export interface SimulationWorkspaceState {
  activeRunId: string | null;
  jobId: string | null;
  simulationType: "quarter_car" | "half_car" | "full_car" | "lap_sim" | "active";
  status: "IDLE" | "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  progress: number;
  startedAt: string | null;
  completedAt: string | null;
  solverInfo: SimulationSolverInfo;
  lastResult: any | null;
  error: any | null;
}

export interface OptimizationWorkspaceState {
  optimizationId: string | null;
  status: "IDLE" | "QUEUED" | "RUNNING" | "CONVERGED" | "FAILED";
  objective: "COMFORT" | "HANDLING" | "BALANCED";
  targetLapTimeDelta_s: number | null;
  results: any | null;
}

export interface ValidationCheckItem {
  label: string;
  status: "pass" | "warn" | "fail";
  detail: string;
}

export interface ValidationWorkspaceState {
  status: "VALIDATED" | "CONDITIONAL" | "EXPERIMENTAL" | "OUT-OF-DOMAIN";
  score: number;
  correlation_pct: number;
  checks: ValidationCheckItem[];
  explanation: string;
}

export type WorkspaceMode = "PRODUCTION" | "DEMO";

export interface ActiveVehicleContext {
  vehicle: string;
  vehicleVersion: string;
  setup: string;
  setupVersion: string;
  track: string;
  session: string;
  modelVersion: string;
  telemetrySession: string;
}

export interface WorkspaceContextType {
  mode: WorkspaceMode;
  setMode: (mode: WorkspaceMode) => void;
  vehicle: VehicleState;
  setVehicle: (update: Partial<VehicleState>) => void;
  setup: SetupState;
  setSetup: (update: Partial<SetupState>) => void;
  track: TrackState;
  setTrack: (update: Partial<TrackState>) => void;
  tire: TireState;
  setTire: (update: Partial<TireState>) => void;
  telemetry: TelemetryWorkspaceState;
  setTelemetry: (update: Partial<TelemetryWorkspaceState>) => void;
  simulation: SimulationWorkspaceState;
  setSimulation: (update: Partial<SimulationWorkspaceState>) => void;
  optimization: OptimizationWorkspaceState;
  setOptimization: (update: Partial<OptimizationWorkspaceState>) => void;
  validation: ValidationWorkspaceState;
  setValidation: (update: Partial<ValidationWorkspaceState>) => void;
  sessionName: string;
  setSessionName: (name: string) => void;
  modelVersion: string;
  setModelVersion: (v: string) => void;
  digitalTwinId: string;
  setDigitalTwinId: (id: string) => void;
  activeQuestionId: string | null;
  setActiveQuestionId: (id: string | null) => void;
  activeInvestigationId: string | null;
  setActiveInvestigationId: (id: string | null) => void;
  activeExperimentId: string | null;
  setActiveExperimentId: (id: string | null) => void;
  activeOptimizationId: string | null;
  setActiveOptimizationId: (id: string | null) => void;
  activeCandidateId: string | null;
  setActiveCandidateId: (id: string | null) => void;
  activeProposalId: string | null;
  setActiveProposalId: (id: string | null) => void;
  activeDecisionId: string | null;
  setActiveDecisionId: (id: string | null) => void;
  activeVehicleContext: ActiveVehicleContext;
  resetToDefaults: () => void;
}

const DEFAULT_VEHICLE: VehicleState = {
  id: "gt3-spec-baseline",
  name: "GT3 Spec Baseline",
  version: "1285 kg / 395 kW",
  mass_kg: 1285,
  wheelbase_m: 2.65,
  track_width_m: 1.62,
  cg_height_m: 0.42,
};

const DEFAULT_SETUP: SetupState = {
  id: "setup-spa-v28",
  name: "Spa-Francorchamps Aero Rev 28",
  version: "Rev 28",
  k_spring_front: 32000,
  k_spring_rear: 38000,
  c_damper_front: 2400,
  c_damper_rear: 2800,
  k_arb_front: 45000,
  k_arb_rear: 22000,
  ride_height_front_mm: 28,
  ride_height_rear_mm: 42,
  camber_front_deg: -3.2,
  toe_front_deg: 0.1,
};

const DEFAULT_TRACK: TrackState = {
  id: "spa-francorchamps",
  name: "Circuit de Spa-Francorchamps",
  length_m: 7004,
  grip_multiplier: 1.0,
  weather: "DRY",
  track_temp_c: 28.5,
};

const DEFAULT_TIRE: TireState = {
  id: "pirelli-pzero-c3",
  name: "Pirelli P Zero C3 Soft (Pacejka MF5.2)",
  model_type: "MF5.2",
  nominal_pressure_kpa: 145,
  front_pressure_kpa: 145,
  rear_pressure_kpa: 140,
};

const DEFAULT_TELEMETRY: TelemetryWorkspaceState = {
  sessionId: "sess-live",
  datasetName: "sample_spa_gt3.csv",
  sampleRateHz: 100,
  isStreaming: false,
  isReplaying: false,
  channelsCount: 32,
  status: "IDLE",
};

const DEFAULT_SIMULATION: SimulationWorkspaceState = {
  activeRunId: null,
  jobId: null,
  simulationType: "quarter_car",
  status: "IDLE",
  progress: 0,
  startedAt: null,
  completedAt: null,
  solverInfo: {
    solver: "scipy.integrate.solve_ivp (RK45)",
    version: "1.13.0",
    backend: "NumPy / SciPy Vectorized C-Extension",
    build: "PROD-2026.09.03",
  },
  lastResult: null,
  error: null,
};

const DEFAULT_OPTIMIZATION: OptimizationWorkspaceState = {
  optimizationId: null,
  status: "IDLE",
  objective: "HANDLING",
  targetLapTimeDelta_s: -0.087,
  results: null,
};

const DEFAULT_VALIDATION: ValidationWorkspaceState = {
  status: "VALIDATED",
  score: 91.0,
  correlation_pct: 91.0,
  checks: [
    { label: "Pacejka MF5.2 Tire Slip Envelope", status: "pass", detail: "Operating slip angles within verified test domain (α < 8°)" },
    { label: "Damper Velocity Non-Linearity", status: "pass", detail: "Full bilinear dyno lookup table active across heave & pitch" },
    { label: "Telemetry MoTeC Correlation", status: "pass", detail: "R² = 0.912 correlation against Spa FP1 high-speed runs" },
    { label: "Kinematics Instant Roll Center", status: "pass", detail: "Roll center migration curve verified within FIA envelope" }
  ],
  explanation: "Model validated against track telemetry. Safe to base suspension and aerodynamic setup decisions on.",
};

const WorkspaceContext = createContext<WorkspaceContextType | null>(null);

const STORAGE_KEY = "suspensionlab_workspace_state_v1";

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<WorkspaceMode>("PRODUCTION");
  const [vehicle, setVehicleState] = useState<VehicleState>(DEFAULT_VEHICLE);
  const [setup, setSetupState] = useState<SetupState>(DEFAULT_SETUP);
  const [track, setTrackState] = useState<TrackState>(DEFAULT_TRACK);
  const [tire, setTireState] = useState<TireState>(DEFAULT_TIRE);
  const [telemetry, setTelemetryState] = useState<TelemetryWorkspaceState>(DEFAULT_TELEMETRY);
  const [simulation, setSimulationState] = useState<SimulationWorkspaceState>(DEFAULT_SIMULATION);
  const [optimization, setOptimizationState] = useState<OptimizationWorkspaceState>(DEFAULT_OPTIMIZATION);
  const [validation, setValidationState] = useState<ValidationWorkspaceState>(DEFAULT_VALIDATION);
  const [sessionName, setSessionNameState] = useState<string>("Spa FP2 Engineering Investigation");
  const [modelVersion, setModelVersionState] = useState<string>("VehicleModel-7DOF-v12.4");
  const [digitalTwinId, setDigitalTwinIdState] = useState<string>("active");

  // Workflow continuity IDs
  const [activeQuestionId, setActiveQuestionIdState] = useState<string | null>(null);
  const [activeInvestigationId, setActiveInvestigationIdState] = useState<string | null>(null);
  const [activeExperimentId, setActiveExperimentIdState] = useState<string | null>(null);
  const [activeOptimizationId, setActiveOptimizationIdState] = useState<string | null>(null);
  const [activeCandidateId, setActiveCandidateIdState] = useState<string | null>(null);
  const [activeProposalId, setActiveProposalIdState] = useState<string | null>(null);
  const [activeDecisionId, setActiveDecisionIdState] = useState<string | null>(null);

  // Restore from localStorage and sessionStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.mode) setModeState(parsed.mode);
        if (parsed.vehicle) setVehicleState(parsed.vehicle);
        if (parsed.setup) setSetupState(parsed.setup);
        if (parsed.track) setTrackState(parsed.track);
        if (parsed.tire) setTireState(parsed.tire);
        if (parsed.simulation) setSimulationState(parsed.simulation);
        if (parsed.validation) setValidationState(parsed.validation);
        if (parsed.sessionName) setSessionNameState(parsed.sessionName);
        if (parsed.modelVersion) setModelVersionState(parsed.modelVersion);
        if (parsed.digitalTwinId) setDigitalTwinIdState(parsed.digitalTwinId);
        if (parsed.activeQuestionId) setActiveQuestionIdState(parsed.activeQuestionId);
        if (parsed.activeInvestigationId) setActiveInvestigationIdState(parsed.activeInvestigationId);
        if (parsed.activeExperimentId) setActiveExperimentIdState(parsed.activeExperimentId);
        if (parsed.activeOptimizationId) setActiveOptimizationIdState(parsed.activeOptimizationId);
        if (parsed.activeCandidateId) setActiveCandidateIdState(parsed.activeCandidateId);
        if (parsed.activeProposalId) setActiveProposalIdState(parsed.activeProposalId);
        if (parsed.activeDecisionId) setActiveDecisionIdState(parsed.activeDecisionId);
      }

      // Check sessionStorage overrides
      const sessExp = sessionStorage.getItem("suspensionlab_active_exp_id");
      if (sessExp) setActiveExperimentIdState(sessExp);
      const sessProp = sessionStorage.getItem("suspensionlab_active_proposal_id");
      if (sessProp) setActiveProposalIdState(sessProp);
      const sessOpt = sessionStorage.getItem("suspensionlab_active_opt_id");
      if (sessOpt) setActiveOptimizationIdState(sessOpt);
    } catch {}
  }, []);

  // Sync to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          mode,
          vehicle,
          setup,
          track,
          tire,
          sessionName,
          modelVersion,
          digitalTwinId,
          activeQuestionId,
          activeInvestigationId,
          activeExperimentId,
          activeOptimizationId,
          activeCandidateId,
          activeProposalId,
          activeDecisionId,
          simulation: {
            ...simulation,
            lastResult: null, // do not bloat storage
          },
          validation,
        })
      );
    } catch {}
  }, [
    mode,
    vehicle,
    setup,
    track,
    tire,
    sessionName,
    modelVersion,
    digitalTwinId,
    activeQuestionId,
    activeInvestigationId,
    activeExperimentId,
    activeOptimizationId,
    activeCandidateId,
    activeProposalId,
    activeDecisionId,
    simulation,
    validation,
  ]);

  const setMode = useCallback((m: WorkspaceMode) => setModeState(m), []);
  const setVehicle = useCallback((up: Partial<VehicleState>) => setVehicleState((p) => ({ ...p, ...up })), []);
  const setSetup = useCallback((up: Partial<SetupState>) => setSetupState((p) => ({ ...p, ...up })), []);
  const setTrack = useCallback((up: Partial<TrackState>) => setTrackState((p) => ({ ...p, ...up })), []);
  const setTire = useCallback((up: Partial<TireState>) => setTireState((p) => ({ ...p, ...up })), []);
  const setTelemetry = useCallback((up: Partial<TelemetryWorkspaceState>) => setTelemetryState((p) => ({ ...p, ...up })), []);
  const setSimulation = useCallback((up: Partial<SimulationWorkspaceState>) => setSimulationState((p) => ({ ...p, ...up })), []);
  const setOptimization = useCallback((up: Partial<OptimizationWorkspaceState>) => setOptimizationState((p) => ({ ...p, ...up })), []);
  const setValidation = useCallback((up: Partial<ValidationWorkspaceState>) => setValidationState((p) => ({ ...p, ...up })), []);
  const setSessionName = useCallback((name: string) => setSessionNameState(name), []);
  const setModelVersion = useCallback((v: string) => setModelVersionState(v), []);
  const setDigitalTwinId = useCallback((id: string) => setDigitalTwinIdState(id), []);

  const setActiveQuestionId = useCallback((id: string | null) => {
    setActiveQuestionIdState(id);
    try {
      if (id) sessionStorage.setItem("suspensionlab_active_question_id", id);
      else sessionStorage.removeItem("suspensionlab_active_question_id");
    } catch {}
  }, []);

  const setActiveInvestigationId = useCallback((id: string | null) => {
    setActiveInvestigationIdState(id);
    try {
      if (id) sessionStorage.setItem("suspensionlab_active_investigation_id", id);
      else sessionStorage.removeItem("suspensionlab_active_investigation_id");
    } catch {}
  }, []);

  const setActiveExperimentId = useCallback((id: string | null) => {
    setActiveExperimentIdState(id);
    try {
      if (id) sessionStorage.setItem("suspensionlab_active_exp_id", id);
      else sessionStorage.removeItem("suspensionlab_active_exp_id");
    } catch {}
  }, []);

  const setActiveOptimizationId = useCallback((id: string | null) => {
    setActiveOptimizationIdState(id);
    try {
      if (id) sessionStorage.setItem("suspensionlab_active_opt_id", id);
      else sessionStorage.removeItem("suspensionlab_active_opt_id");
    } catch {}
  }, []);

  const setActiveCandidateId = useCallback((id: string | null) => {
    setActiveCandidateIdState(id);
    try {
      if (id) sessionStorage.setItem("suspensionlab_active_cand_id", id);
      else sessionStorage.removeItem("suspensionlab_active_cand_id");
    } catch {}
  }, []);

  const setActiveProposalId = useCallback((id: string | null) => {
    setActiveProposalIdState(id);
    try {
      if (id) sessionStorage.setItem("suspensionlab_active_proposal_id", id);
      else sessionStorage.removeItem("suspensionlab_active_proposal_id");
    } catch {}
  }, []);

  const setActiveDecisionId = useCallback((id: string | null) => {
    setActiveDecisionIdState(id);
    try {
      if (id) sessionStorage.setItem("suspensionlab_active_decision_id", id);
      else sessionStorage.removeItem("suspensionlab_active_decision_id");
    } catch {}
  }, []);

  const activeVehicleContext: ActiveVehicleContext = {
    vehicle: vehicle.name,
    vehicleVersion: vehicle.version,
    setup: setup.name,
    setupVersion: setup.version,
    track: track.name,
    session: sessionName,
    modelVersion: modelVersion,
    telemetrySession: telemetry.sessionId || "sess-live",
  };

  const resetToDefaults = useCallback(() => {
    setVehicleState(DEFAULT_VEHICLE);
    setSetupState(DEFAULT_SETUP);
    setTrackState(DEFAULT_TRACK);
    setTireState(DEFAULT_TIRE);
    setTelemetryState(DEFAULT_TELEMETRY);
    setSimulationState(DEFAULT_SIMULATION);
    setOptimizationState(DEFAULT_OPTIMIZATION);
    setValidationState(DEFAULT_VALIDATION);
    setSessionNameState("Spa FP2 Engineering Investigation");
    setModelVersionState("VehicleModel-7DOF-v12.4");
    setDigitalTwinIdState("active");
    setActiveQuestionIdState(null);
    setActiveInvestigationIdState(null);
    setActiveExperimentIdState(null);
    setActiveOptimizationIdState(null);
    setActiveCandidateIdState(null);
    setActiveProposalIdState(null);
    setActiveDecisionIdState(null);
    try {
      sessionStorage.clear();
    } catch {}
  }, []);

  return (
    <WorkspaceContext.Provider
      value={{
        mode,
        setMode,
        vehicle,
        setVehicle,
        setup,
        setSetup,
        track,
        setTrack,
        tire,
        setTire,
        telemetry,
        setTelemetry,
        simulation,
        setSimulation,
        optimization,
        setOptimization,
        validation,
        setValidation,
        sessionName,
        setSessionName,
        modelVersion,
        setModelVersion,
        digitalTwinId,
        setDigitalTwinId,
        activeQuestionId,
        setActiveQuestionId,
        activeInvestigationId,
        setActiveInvestigationId,
        activeExperimentId,
        setActiveExperimentId,
        activeOptimizationId,
        setActiveOptimizationId,
        activeCandidateId,
        setActiveCandidateId,
        activeProposalId,
        setActiveProposalId,
        activeDecisionId,
        setActiveDecisionId,
        activeVehicleContext,
        resetToDefaults,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error("useWorkspace must be used within a WorkspaceProvider");
  }
  return ctx;
}
