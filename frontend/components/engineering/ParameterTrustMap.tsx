"use client";

import React, { useState, useEffect } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  Clock,
  History,
  FileCheck2,
  HelpCircle,
  Hash,
  Database,
  Layers,
  Search,
  RefreshCw,
  Sliders,
  CheckCircle2,
  FileText,
  Scale,
  Target,
  FlaskConical,
  Workflow,
  GitCommit,
  Activity,
  TrendingUp,
  Lock,
  Unlock,
  ClipboardList,
  CheckSquare,
  XCircle,
  ArrowRight,
} from "lucide-react";
import {
  ParameterTrustApi,
  ValidationPlanningApi,
  ParameterTrustResponseDTO,
  ParameterTrustHistoryItemDTO,
  ParameterTrustState,
  ValidationCoverage,
  BatchIngestSummaryDTO,
  ParameterSweepAnalysisResponseDTO,
  FleetSynchronizationResponseDTO,
  AssemblyImpactAssessmentResponseDTO,
  SensitivityEvidenceResponseDTO,
  DecisionExposureAssessmentResponseDTO,
  DecisionHistoryItemDTO,
  DecisionDependenciesResponseDTO,
  DecisionGapsResponseDTO,
  RobustnessPreflightResponseDTO,
  RobustnessAnalysisResponseDTO,
  DecisionBoundariesResponseDTO,
  DecisionVOIResponseDTO,
  ValidationPlanResponseDTO,
  ValidationPlanCreateRequestDTO,
  ValidationPlanTransitionRequestDTO,
  EvidenceSubmissionRequestDTO,
  EvidenceItemResponseDTO,
  ClosureAssessmentResponseDTO,
  DecisionReassessmentResponseDTO,
  AcceptanceCriterionDTO,
  DecisionDossierApi,
  EngineeringDecisionDossierResponseDTO,
  SourceVerificationResponseDTO,
  ReviewActionType,
  TrustedSourceRegistryResponseDTO,
} from "../../lib/api_client";

interface ParameterTrustMapProps {
  initialEntityType?: string;
  initialEntityId?: string;
  initialParameter?: string;
  onLoaded?: (data: ParameterTrustResponseDTO) => void;
}

export function ParameterTrustMap({
  initialEntityType = "SetupCandidate",
  initialEntityId = "SETUP-P3L-CAND-01",
  initialParameter = "front_spring_rate",
  onLoaded,
}: ParameterTrustMapProps) {
  const [entityType, setEntityType] = useState(initialEntityType);
  const [entityId, setEntityId] = useState(initialEntityId);
  const [parameter, setParameter] = useState(initialParameter);

  const [trustData, setTrustData] = useState<ParameterTrustResponseDTO | null>(null);
  const [historyItems, setHistoryItems] = useState<ParameterTrustHistoryItemDTO[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<
    "overview" | "evidence" | "history" | "sweep" | "ingestion" | "fleet" | "propagation" | "decisions" | "robustness" | "validation" | "dossiers"
  >("overview");

  // Phase 6.2 Ingestion & Sweep State
  const [ingestSummary, setIngestSummary] = useState<BatchIngestSummaryDTO | null>(null);
  const [ingestLoading, setIngestLoading] = useState(false);
  const [ingestError, setIngestError] = useState<string | null>(null);

  const [sweepData, setSweepData] = useState<ParameterSweepAnalysisResponseDTO | null>(null);
  const [sweepLoading, setSweepLoading] = useState(false);
  const [sweepError, setSweepError] = useState<string | null>(null);

  // Phase 6.3 Fleet & Propagation State
  const [fleetData, setFleetData] = useState<FleetSynchronizationResponseDTO | null>(null);
  const [fleetLoading, setFleetLoading] = useState(false);
  const [fleetError, setFleetError] = useState<string | null>(null);
  const [fleetId, setFleetId] = useState("FLEET-GT3-2026");

  const [impactData, setImpactData] = useState<AssemblyImpactAssessmentResponseDTO | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [impactError, setImpactError] = useState<string | null>(null);

  // Phase 6.4 Decision Trust State
  const [decisionId, setDecisionId] = useState("DEC-12");
  const [decisionType, setDecisionType] = useState("EngineeringDecision");
  const [decisionExposureData, setDecisionExposureData] = useState<DecisionExposureAssessmentResponseDTO | null>(null);
  const [decisionLoading, setDecisionLoading] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [decisionHistoryItems, setDecisionHistoryItems] = useState<DecisionHistoryItemDTO[]>([]);

  const fetchDecisionExposure = async (
    targetDecisionId: string,
    targetDecisionType: string = "EngineeringDecision",
    forceReassess: boolean = false
  ) => {
    if (!targetDecisionId) return;
    setDecisionLoading(true);
    setDecisionError(null);
    try {
      const res = await ParameterTrustApi.assessDecisionExposure({
        decision_id: targetDecisionId,
        decision_type: targetDecisionType,
        force_reassess: forceReassess,
        persist_record: true,
      });
      setDecisionExposureData(res);
      try {
        const histRes = await ParameterTrustApi.getDecisionHistory(targetDecisionId);
        setDecisionHistoryItems(histRes.history || []);
      } catch {
        setDecisionHistoryItems([]);
      }
    } catch (err: any) {
      setDecisionError(err?.message || "Failed to assess decision exposure.");
      setDecisionExposureData(null);
      setDecisionHistoryItems([]);
    } finally {
      setDecisionLoading(false);
    }
  };

  // Phase 6.5 Decision Robustness State
  const [robustnessDecisionId, setRobustnessDecisionId] = useState("DEC-12");
  const [robustnessData, setRobustnessData] = useState<RobustnessAnalysisResponseDTO | null>(null);
  const [robustnessLoading, setRobustnessLoading] = useState(false);
  const [robustnessError, setRobustnessError] = useState<string | null>(null);
  const [preflightData, setPreflightData] = useState<RobustnessPreflightResponseDTO | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [preflightError, setPreflightError] = useState<string | null>(null);
  const [boundariesData, setBoundariesData] = useState<DecisionBoundariesResponseDTO | null>(null);
  const [voiData, setVoiData] = useState<DecisionVOIResponseDTO | null>(null);
  const [robustnessHistoryItems, setRobustnessHistoryItems] = useState<any[]>([]);

  const handleRunRobustnessPreflight = async (targetDecisionId: string) => {
    if (!targetDecisionId) return;
    setPreflightLoading(true);
    setPreflightError(null);
    try {
      const res = await ParameterTrustApi.preflightDecisionRobustness({
        decision_id: targetDecisionId,
      });
      setPreflightData(res);
    } catch (err: any) {
      setPreflightError(err?.message || "Failed to run robustness preflight.");
      setPreflightData(null);
    } finally {
      setPreflightLoading(false);
    }
  };

  const handleRunRobustnessAnalysis = async (
    targetDecisionId: string,
    forceReassess: boolean = false
  ) => {
    if (!targetDecisionId) return;
    setRobustnessLoading(true);
    setRobustnessError(null);
    try {
      const res = await ParameterTrustApi.runDecisionRobustness({
        decision_id: targetDecisionId,
        persist_record: true,
      });
      setRobustnessData(res);
      try {
        const boundsRes = await ParameterTrustApi.getDecisionBoundaries(targetDecisionId);
        setBoundariesData(boundsRes);
      } catch {
        setBoundariesData(null);
      }
      try {
        const voiRes = await ParameterTrustApi.getDecisionVOI(targetDecisionId);
        setVoiData(voiRes);
      } catch {
        setVoiData(null);
      }
      try {
        const histRes = await ParameterTrustApi.getDecisionRobustnessHistory(targetDecisionId);
        setRobustnessHistoryItems(histRes.history || []);
      } catch {
        setRobustnessHistoryItems([]);
      }
    } catch (err: any) {
      setRobustnessError(err?.message || "Failed to analyze decision robustness.");
      setRobustnessData(null);
    } finally {
      setRobustnessLoading(false);
    }
  };

  // Phase 6.6 Validation Planning State
  const [validationDecisionId, setValidationDecisionId] = useState("DEC-12");
  const [validationPlans, setValidationPlans] = useState<ValidationPlanResponseDTO[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<ValidationPlanResponseDTO | null>(null);
  const [validationLoading, setValidationLoading] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  // New Plan Modal State
  const [showNewPlanModal, setShowNewPlanModal] = useState(false);
  const [newPlanParam, setNewPlanParam] = useState("front_spring_rate");
  const [newPlanMethod, setNewPlanMethod] = useState("RIG_TEST_4_POST");
  const [newPlanObjective, setNewPlanObjective] = useState("Empirically characterize spring stiffness and uncertainty bounds");
  const [newPlanUnit, setNewPlanUnit] = useState("N/mm");
  const [newPlanMeasurementDef, setNewPlanMeasurementDef] = useState("Quasi-static deflection load cell measurement");
  const [newPlanTargetValue, setNewPlanTargetValue] = useState<number>(80.0);
  const [newPlanToleranceLow, setNewPlanToleranceLow] = useState<number>(76.0);
  const [newPlanToleranceHigh, setNewPlanToleranceHigh] = useState<number>(84.0);

  // Evidence Submission Modal State
  const [showSubmitEvidenceModal, setShowSubmitEvidenceModal] = useState(false);
  const [evidenceSourceId, setEvidenceSourceId] = useState("TEST-RIG-4P-2026-001");
  const [evidenceSourceType, setEvidenceSourceType] = useState("PHYSICAL_RIG_MEASUREMENT");
  const [evidenceObservedVal, setEvidenceObservedVal] = useState<number>(80.4);
  const [evidenceLowBound, setEvidenceLowBound] = useState<number>(78.5);
  const [evidenceHighBound, setEvidenceHighBound] = useState<number>(82.3);
  const [evidenceUnit, setEvidenceUnit] = useState("N/mm");
  const [isPhysicallyValidated, setIsPhysicallyValidated] = useState(true);
  const [evidenceLimitation, setEvidenceLimitation] = useState("Finite run: 25 dry track cycles at 22C");

  // Closure & Reassessment State
  const [closureAssessment, setClosureAssessment] = useState<ClosureAssessmentResponseDTO | null>(null);
  const [closureLoading, setClosureLoading] = useState(false);
  const [reassessmentResult, setReassessmentResult] = useState<DecisionReassessmentResponseDTO | null>(null);
  const [reassessmentLoading, setReassessmentLoading] = useState(false);
  const [historicalReassessments, setHistoricalReassessments] = useState<DecisionReassessmentResponseDTO[]>([]);

  // Phase 6.7 Decision Dossiers & Source Verification State
  const [dossiers, setDossiers] = useState<EngineeringDecisionDossierResponseDTO[]>([]);
  const [selectedDossier, setSelectedDossier] = useState<EngineeringDecisionDossierResponseDTO | null>(null);
  const [dossierLoading, setDossierLoading] = useState(false);
  const [dossierError, setDossierError] = useState<string | null>(null);
  const [showCompileModal, setShowCompileModal] = useState(false);
  const [compilePlanId, setCompilePlanId] = useState("");
  const [compileClosureId, setCompileClosureId] = useState("");
  const [compileReassessmentId, setCompileReassessmentId] = useState("");
  const [compileQuestion, setCompileQuestion] = useState("Is front spring stiffness robust against reversal under measured bump loads?");
  const [compileDecisionType, setCompileDecisionType] = useState("EngineeringDecision");

  // Source Verification Modal State
  const [showVerifySourceModal, setShowVerifySourceModal] = useState(false);
  const [verifyingEvidenceId, setVerifyingEvidenceId] = useState<string | null>(null);
  const [verifyMethod, setVerifyMethod] = useState<string>("AUTHORIZED_CUSTODIAN_REVIEW");
  const [verifierIdentity, setVerifierIdentity] = useState("Lead Validation Auditor");
  const [verificationNotes, setVerificationNotes] = useState("Source calibration certificate and raw telemetry records verified.");

  const fetchValidationPlans = async (targetDecisionId: string) => {
    if (!targetDecisionId) return;
    setValidationLoading(true);
    setValidationError(null);
    try {
      const res = await ValidationPlanningApi.listValidationPlansForDecision(targetDecisionId);
      setValidationPlans(res.plans || []);
      if (res.plans && res.plans.length > 0) {
        setSelectedPlan((prev) => (prev ? res.plans.find((p) => p.id === prev.id) || res.plans[0] : res.plans[0]));
      } else {
        setSelectedPlan(null);
      }
      try {
        const histRes = await ValidationPlanningApi.getDecisionReassessments(targetDecisionId);
        setHistoricalReassessments(histRes.reassessments || []);
      } catch {
        setHistoricalReassessments([]);
      }
    } catch (err: any) {
      setValidationError(err?.message || "Failed to load validation plans.");
      setValidationPlans([]);
      setSelectedPlan(null);
    } finally {
      setValidationLoading(false);
    }
  };

  const handleCreateValidationPlan = async () => {
    setValidationLoading(true);
    setValidationError(null);
    try {
      const criteria: AcceptanceCriterionDTO[] = [
        {
          metric_name: `${newPlanParam}_rate_limit`,
          target_value: Number(newPlanTargetValue),
          tolerance_band: [Number(newPlanToleranceLow), Number(newPlanToleranceHigh)],
          unit: newPlanUnit,
          status: "PROPOSED",
          rationale: "Established from preliminary sensitivity thresholds",
        },
      ];

      const res = await ValidationPlanningApi.createValidationPlan({
        decision_id: validationDecisionId,
        parameter_name: newPlanParam,
        validation_method: newPlanMethod,
        validation_objective: newPlanObjective,
        measurement_definition: newPlanMeasurementDef,
        unit: newPlanUnit,
        acceptance_criteria: criteria,
        operating_conditions: {
          temperature_min_c: 15.0,
          temperature_max_c: 35.0,
          regime: "TRACK_DRY",
        },
      });

      setShowNewPlanModal(false);
      await fetchValidationPlans(validationDecisionId);
      setSelectedPlan(res);
    } catch (err: any) {
      setValidationError(err?.message || "Failed to create validation plan.");
    } finally {
      setValidationLoading(false);
    }
  };

  const handleTransitionPlan = async (planId: string, targetStatus: string) => {
    setValidationLoading(true);
    setValidationError(null);
    try {
      const res = await ValidationPlanningApi.transitionValidationPlan(planId, {
        target_status: targetStatus,
      });
      setSelectedPlan(res);
      await fetchValidationPlans(validationDecisionId);
    } catch (err: any) {
      setValidationError(err?.message || `Failed to transition plan to ${targetStatus}`);
    } finally {
      setValidationLoading(false);
    }
  };

  const handleSubmitEvidence = async (planId: string) => {
    if (!selectedPlan) return;
    setValidationLoading(true);
    setValidationError(null);
    try {
      await ValidationPlanningApi.submitValidationEvidence(planId, {
        source_identifier: evidenceSourceId,
        evidence_source_type: evidenceSourceType,
        observed_value: Number(evidenceObservedVal),
        observed_interval: [Number(evidenceLowBound), Number(evidenceHighBound)],
        unit: evidenceUnit,
        is_physically_validated: isPhysicallyValidated,
        physical_limitations: evidenceLimitation,
        provenance: {
          facility: "DynoLab-Chassis-01",
          rig_id: "RIG-4P-A",
          test_engineer: "Lead Validation Engineer",
        },
        operating_scope: {
          temperature_min_c: 18.0,
          temperature_max_c: 28.0,
          regime: "TRACK_DRY",
        },
      });
      setShowSubmitEvidenceModal(false);
      const updated = await ValidationPlanningApi.getValidationPlan(planId);
      setSelectedPlan(updated);
      await fetchValidationPlans(validationDecisionId);
    } catch (err: any) {
      setValidationError(err?.message || "Failed to submit evidence.");
    } finally {
      setValidationLoading(false);
    }
  };

  const handleReviewEvidence = async (planId: string, evidenceId: string, reviewStatus: string) => {
    setValidationLoading(true);
    setValidationError(null);
    try {
      await ValidationPlanningApi.reviewValidationEvidence(planId, evidenceId, {
        review_status: reviewStatus,
        review_notes: `Reviewed by Lead Validation Engineer: ${reviewStatus}`,
      });
      const updated = await ValidationPlanningApi.getValidationPlan(planId);
      setSelectedPlan(updated);
      await fetchValidationPlans(validationDecisionId);
    } catch (err: any) {
      setValidationError(err?.message || "Failed to review evidence item.");
    } finally {
      setValidationLoading(false);
    }
  };

  const handleEvaluateClosure = async (planId: string) => {
    setClosureLoading(true);
    setValidationError(null);
    try {
      const res = await ValidationPlanningApi.evaluateEvidenceClosure(planId);
      setClosureAssessment(res);
      const updated = await ValidationPlanningApi.getValidationPlan(planId);
      setSelectedPlan(updated);
      await fetchValidationPlans(validationDecisionId);
    } catch (err: any) {
      setValidationError(err?.message || "Failed to evaluate evidence closure.");
    } finally {
      setClosureLoading(false);
    }
  };

  const handleExecuteReassessment = async (planId: string) => {
    setReassessmentLoading(true);
    setValidationError(null);
    try {
      const res = await ValidationPlanningApi.reassessDecision(planId);
      setReassessmentResult(res);
      await fetchValidationPlans(validationDecisionId);
    } catch (err: any) {
      setValidationError(err?.message || "Failed to execute decision reassessment.");
    } finally {
      setReassessmentLoading(false);
    }
  };

  // Phase 6.7 Decision Dossier & Verification Handlers
  const fetchDossiers = async (targetDecisionId: string) => {
    if (!targetDecisionId) return;
    setDossierLoading(true);
    setDossierError(null);
    try {
      const res = await DecisionDossierApi.listDossiersForDecision(targetDecisionId);
      setDossiers(res.dossiers || []);
      if (res.dossiers && res.dossiers.length > 0) {
        setSelectedDossier(res.dossiers[0]);
      } else {
        setSelectedDossier(null);
      }
    } catch (err: any) {
      setDossierError(err?.message || "Failed to fetch decision dossiers.");
      setDossiers([]);
      setSelectedDossier(null);
    } finally {
      setDossierLoading(false);
    }
  };

  const handleCompileDossier = async () => {
    setDossierLoading(true);
    setDossierError(null);
    try {
      const created = await DecisionDossierApi.compileDecisionDossier({
        decision_id: validationDecisionId,
        plan_id: compilePlanId || (selectedPlan?.id ?? ""),
        closure_id: compileClosureId || (closureAssessment?.id ?? ""),
        reassessment_id: compileReassessmentId || (reassessmentResult?.id ?? ""),
        engineering_question: compileQuestion,
        decision_type: compileDecisionType,
      });
      setShowCompileModal(false);
      await fetchDossiers(validationDecisionId);
      setSelectedDossier(created);
    } catch (err: any) {
      setDossierError(err?.message || "Failed to compile decision dossier.");
    } finally {
      setDossierLoading(false);
    }
  };

  const handleAdvanceDossierGovernance = async (dossierId: string, actionType: ReviewActionType, rationale?: string) => {
    setDossierLoading(true);
    setDossierError(null);
    try {
      const updated = await DecisionDossierApi.advanceDossierGovernance(dossierId, {
        action_type: actionType,
        rationale: rationale || `Executed governance transition: ${actionType}`,
      });
      setSelectedDossier(updated);
      await fetchDossiers(validationDecisionId);
    } catch (err: any) {
      setDossierError(err?.message || `Failed to execute ${actionType} on dossier.`);
    } finally {
      setDossierLoading(false);
    }
  };

  const handleSupersedeDossier = async (dossierId: string) => {
    setDossierLoading(true);
    setDossierError(null);
    try {
      const superseded = await DecisionDossierApi.supersedeDossier(dossierId, {
        reason: "Superseded with updated empirical evidence and reassessment cycle.",
      });
      await fetchDossiers(validationDecisionId);
      setSelectedDossier(superseded);
    } catch (err: any) {
      setDossierError(err?.message || "Failed to supersede dossier.");
    } finally {
      setDossierLoading(false);
    }
  };

  const handleVerifyEvidenceSource = async (evidenceId: string) => {
    setValidationLoading(true);
    setValidationError(null);
    try {
      await DecisionDossierApi.verifyEvidenceSource(evidenceId, {
        verification_method: verifyMethod,
        verifier_identity: verifierIdentity,
        verification_notes: verificationNotes,
      });
      setShowVerifySourceModal(false);
      setVerifyingEvidenceId(null);
      if (selectedPlan) {
        const updated = await ValidationPlanningApi.getValidationPlan(selectedPlan.id);
        setSelectedPlan(updated);
      }
    } catch (err: any) {
      setValidationError(err?.message || "Failed to verify evidence source.");
    } finally {
      setValidationLoading(false);
    }
  };

  const handleRevokeEvidenceSource = async (evidenceId: string) => {
    setValidationLoading(true);
    setValidationError(null);
    try {
      await DecisionDossierApi.revokeEvidenceSource(evidenceId, {
        reason: "Source authorization revoked due to calibration dispute or custodian notice.",
      });
      if (selectedPlan) {
        const updated = await ValidationPlanningApi.getValidationPlan(selectedPlan.id);
        setSelectedPlan(updated);
      }
    } catch (err: any) {
      setValidationError(err?.message || "Failed to revoke evidence source.");
    } finally {
      setValidationLoading(false);
    }
  };

  const fetchTrustData = async (type: string, id: string, param: string) => {
    if (!type || !id || !param) return;
    setLoading(true);
    setError(null);
    try {
      const data = await ParameterTrustApi.getParameterTrust(type, id, param);
      setTrustData(data);
      if (onLoaded) onLoaded(data);

      try {
        const histRes = await ParameterTrustApi.getParameterTrustHistory(type, id, param);
        setHistoryItems(histRes.history || []);
      } catch {
        setHistoryItems([]);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load parameter trust assessment.");
      setTrustData(null);
      setHistoryItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrustData(entityType, entityId, parameter);
  }, []);

  const handleQuery = (e: React.FormEvent) => {
    e.preventDefault();
    fetchTrustData(entityType, entityId, parameter);
  };

  const handleRunIngest = async () => {
    setIngestLoading(true);
    setIngestError(null);
    try {
      const res = await ParameterTrustApi.ingestEntity(entityType, entityId);
      setIngestSummary(res);
      await fetchTrustData(entityType, entityId, parameter);
    } catch (err: any) {
      setIngestError(err?.message || "Automated ingestion failed.");
    } finally {
      setIngestLoading(false);
    }
  };

  const handleRunSweep = async () => {
    setSweepLoading(true);
    setSweepError(null);
    try {
      const res = await ParameterTrustApi.analyzeSweep({
        parameter_name: parameter,
        candidates: [
          { entity_type: entityType, entity_id: entityId },
          { entity_type: "SetupCandidate", entity_id: "SETUP-P3L-CAND-02" },
          { entity_type: "SimulationRun", entity_id: "RUN-000183" },
        ],
      });
      setSweepData(res);
    } catch (err: any) {
      setSweepError(err?.message || "Parameter sweep analysis failed.");
    } finally {
      setSweepLoading(false);
    }
  };

  const handleRunFleetSync = async () => {
    setFleetLoading(true);
    setFleetError(null);
    try {
      const res = await ParameterTrustApi.compareFleet({
        fleet_id: fleetId,
        parameter_name: parameter,
        members: [
          { entity_type: entityType, entity_id: entityId },
          { entity_type: "VehicleProfile", entity_id: "VEH-GT3-02" },
          { entity_type: "VehicleProfile", entity_id: "VEH-GT3-03" },
          { entity_type: "VehicleProfile", entity_id: "VEH-GT3-04" },
        ],
        persist_report: false,
      });
      setFleetData(res);
    } catch (err: any) {
      setFleetError(err?.message || "Fleet synchronization failed.");
    } finally {
      setFleetLoading(false);
    }
  };

  const handleRunAssemblyImpact = async () => {
    setImpactLoading(true);
    setImpactError(null);
    try {
      const res = await ParameterTrustApi.getAssemblyImpact(entityId, parameter);
      setImpactData(res);
    } catch (err: any) {
      setImpactError(err?.message || "Assembly impact assessment failed.");
    } finally {
      setImpactLoading(false);
    }
  };

  // State styling helper
  const getTrustStateBadge = (state: ParameterTrustState) => {
    switch (state) {
      case "HIGH_CONFIDENCE":
        return {
          bg: "bg-emerald-950/80 border-emerald-500/50 text-emerald-300",
          icon: ShieldCheck,
          label: "HIGH CONFIDENCE",
        };
      case "VALIDATED":
        return {
          bg: "bg-blue-950/80 border-blue-500/50 text-blue-300",
          icon: ShieldCheck,
          label: "VALIDATED",
        };
      case "SUPPORTED":
        return {
          bg: "bg-cyan-950/80 border-cyan-500/50 text-cyan-300",
          icon: FileCheck2,
          label: "SUPPORTED",
        };
      case "PROVISIONAL":
        return {
          bg: "bg-amber-950/80 border-amber-500/50 text-amber-300",
          icon: Clock,
          label: "PROVISIONAL",
        };
      case "CONFLICTED":
        return {
          bg: "bg-rose-950/80 border-rose-500/50 text-rose-300",
          icon: AlertTriangle,
          label: "CONFLICTED",
        };
      case "STALE":
        return {
          bg: "bg-zinc-900 border-zinc-700 text-zinc-400",
          icon: Clock,
          label: "STALE",
        };
      case "REJECTED":
        return {
          bg: "bg-red-950/90 border-red-500/60 text-red-300",
          icon: ShieldAlert,
          label: "REJECTED",
        };
      case "INSUFFICIENT_EVIDENCE":
        return {
          bg: "bg-orange-950/80 border-orange-500/50 text-orange-300",
          icon: HelpCircle,
          label: "INSUFFICIENT EVIDENCE",
        };
      case "UNASSESSED":
      default:
        return {
          bg: "bg-gray-900 border-gray-700 text-gray-400",
          icon: HelpCircle,
          label: "UNASSESSED",
        };
    }
  };

  const getValidationCoverageBadge = (coverage: ValidationCoverage) => {
    switch (coverage) {
      case "VALIDATED":
        return "bg-emerald-950/70 border-emerald-500/40 text-emerald-300";
      case "PARTIAL_VALIDATION":
        return "bg-amber-950/70 border-amber-500/40 text-amber-300";
      case "CONFLICTING_VALIDATION":
        return "bg-rose-950/70 border-rose-500/40 text-rose-300";
      case "NO_VALIDATION":
      default:
        return "bg-zinc-900 border-zinc-700 text-zinc-400";
    }
  };

  const getRobustnessBadge = (classification: string) => {
    switch (classification) {
      case "ROBUST_WITHIN_CREDIBLE_RANGE":
        return {
          bg: "bg-emerald-950/80 border-emerald-500/50 text-emerald-300",
          icon: ShieldCheck,
          label: "ROBUST WITHIN CREDIBLE RANGE",
        };
      case "POTENTIALLY_SENSITIVE":
        return {
          bg: "bg-amber-950/80 border-amber-500/50 text-amber-300",
          icon: AlertTriangle,
          label: "POTENTIALLY SENSITIVE",
        };
      case "VULNERABLE_TO_REVERSAL":
        return {
          bg: "bg-rose-950/80 border-rose-500/50 text-rose-300",
          icon: ShieldAlert,
          label: "VULNERABLE TO REVERSAL",
        };
      case "UNCERTAINTY_INSUFFICIENT_EVIDENCE":
      default:
        return {
          bg: "bg-zinc-900 border-zinc-700 text-zinc-400",
          icon: HelpCircle,
          label: "UNCERTAINTY INSUFFICIENT EVIDENCE",
        };
    }
  };

  return (
    <div className="w-full max-w-6xl mx-auto rounded-xl border border-zinc-800 bg-[#0c0d0e] text-zinc-100 shadow-2xl p-6 font-sans">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-6 border-b border-zinc-800 gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono tracking-widest uppercase px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
              Phase 6.1
            </span>
            <span className="text-[10px] font-mono text-zinc-400">
              POLICY: {trustData?.policy_version || "TRUST_POLICY_V1"}
            </span>
          </div>
          <h1 className="text-2xl font-bold mt-1 text-white flex items-center gap-2">
            <Layers className="w-6 h-6 text-amber-400" />
            Parameter Trust Map
          </h1>
          <p className="text-xs text-zinc-400 mt-0.5">
            Provenance-aware engineering confidence grounded in authoritative evidence and validation history.
          </p>
        </div>

        {/* Query Controls */}
        <form onSubmit={handleQuery} className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
            placeholder="Entity Type"
            className="px-3 py-1.5 text-xs bg-zinc-900 border border-zinc-700 rounded text-zinc-200 focus:outline-none focus:border-amber-400 w-36 font-mono"
            data-testid="input-entity-type"
          />
          <input
            type="text"
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
            placeholder="Entity ID"
            className="px-3 py-1.5 text-xs bg-zinc-900 border border-zinc-700 rounded text-zinc-200 focus:outline-none focus:border-amber-400 w-44 font-mono"
            data-testid="input-entity-id"
          />
          <input
            type="text"
            value={parameter}
            onChange={(e) => setParameter(e.target.value)}
            placeholder="Parameter Name"
            className="px-3 py-1.5 text-xs bg-zinc-900 border border-zinc-700 rounded text-zinc-200 focus:outline-none focus:border-amber-400 w-40 font-mono"
            data-testid="input-parameter"
          />
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-1.5 text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-black rounded transition flex items-center gap-1.5 disabled:opacity-50"
            data-testid="btn-query-trust"
          >
            <Search className="w-3.5 h-3.5" />
            {loading ? "Evaluating..." : "Inspect"}
          </button>
        </form>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mt-4 p-4 rounded-lg bg-red-950/50 border border-red-500/40 text-red-300 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 text-red-400" />
          <span>{error}</span>
        </div>
      )}

      {/* Main Content */}
      {trustData && (
        <div className="mt-6 space-y-6">
          {/* Parameter Identity & Primary Trust State */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 p-5 rounded-lg bg-zinc-900/60 border border-zinc-800">
            {/* 1. Parameter */}
            <div>
              <div className="text-[10px] uppercase font-mono tracking-wider text-zinc-400">Parameter</div>
              <div className="text-base font-semibold text-white mt-1 font-mono break-all" data-testid="param-name">
                {trustData.parameter_identity.parameter_name}
              </div>
              <div className="text-[11px] text-zinc-500 font-mono truncate mt-0.5" title={trustData.parameter_identity.parameter_path}>
                {trustData.parameter_identity.parameter_path}
              </div>
            </div>

            {/* 2. Value & Unit */}
            <div>
              <div className="text-[10px] uppercase font-mono tracking-wider text-zinc-400">Value & Unit</div>
              <div className="text-lg font-bold text-white mt-1 flex items-baseline gap-1.5 font-mono">
                <span data-testid="param-value">
                  {typeof trustData.value_reference.value === "number"
                    ? trustData.value_reference.value.toLocaleString()
                    : String(trustData.value_reference.value)}
                </span>
                <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-amber-400 border border-zinc-700" data-testid="param-unit">
                  {trustData.unit || "—"}
                </span>
              </div>
              <div className="text-[10px] text-zinc-500 font-mono mt-0.5">
                Hash: {trustData.value_reference.value_identity}
              </div>
            </div>

            {/* 3. Trust State */}
            <div>
              <div className="text-[10px] uppercase font-mono tracking-wider text-zinc-400">Trust State</div>
              <div className="mt-1">
                {(() => {
                  const badge = getTrustStateBadge(trustData.current_trust_state);
                  const Icon = badge.icon;
                  return (
                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold border ${badge.bg}`}
                      data-testid="param-trust-state"
                    >
                      <Icon className="w-3.5 h-3.5" />
                      {badge.label}
                    </span>
                  );
                })()}
              </div>
              <div className="text-[10px] text-zinc-500 mt-1">
                Deterministic: {trustData.assessment_hash.slice(0, 12)}...
              </div>
            </div>

            {/* 4. Validation Coverage */}
            <div>
              <div className="text-[10px] uppercase font-mono tracking-wider text-zinc-400">Validation Coverage</div>
              <div className="mt-1">
                <span
                  className={`inline-block px-2.5 py-1 rounded-md text-xs font-semibold border ${getValidationCoverageBadge(
                    trustData.validation_coverage
                  )}`}
                  data-testid="param-validation-coverage"
                >
                  {trustData.validation_coverage.replace("_", " ")}
                </span>
              </div>
              <div className="text-[10px] text-zinc-500 mt-1">
                {trustData.recency.latest_supporting_validation
                  ? `Latest: ${trustData.recency.latest_supporting_validation}`
                  : "No out-of-sample gate"}
              </div>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex items-center gap-2 border-b border-zinc-800 pb-2">
            <button
              onClick={() => setActiveTab("overview")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "overview"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Overview & Scope
            </button>
            <button
              onClick={() => setActiveTab("evidence")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "evidence"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Supporting Evidence ({trustData.supporting_evidence.length})
            </button>
            <button
              onClick={() => setActiveTab("history")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "history"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
            >
              Audit History ({historyItems.length})
            </button>
            <button
              onClick={() => setActiveTab("sweep")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "sweep"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
              data-testid="tab-sweep"
            >
              Sweep Analysis
            </button>
            <button
              onClick={() => setActiveTab("ingestion")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "ingestion"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
              data-testid="tab-ingestion"
            >
              Automated Ingestion
            </button>
            <button
              onClick={() => setActiveTab("fleet")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "fleet"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
              data-testid="tab-fleet"
            >
              Fleet Sync
            </button>
            <button
              onClick={() => setActiveTab("propagation")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "propagation"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
              data-testid="tab-propagation"
            >
              Assembly Propagation
            </button>
            <button
              onClick={() => setActiveTab("decisions")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "decisions"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
              data-testid="tab-decisions"
            >
              Decision Trust
            </button>
            <button
              onClick={() => setActiveTab("robustness")}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "robustness"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
              data-testid="tab-robustness"
            >
              Decision Robustness
            </button>
            <button
              onClick={() => {
                setActiveTab("validation");
                if (validationPlans.length === 0) {
                  fetchValidationPlans(validationDecisionId);
                }
              }}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "validation"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
              data-testid="tab-validation-planning"
            >
              Validation Planning
            </button>
            <button
              onClick={() => {
                setActiveTab("dossiers");
                if (dossiers.length === 0) {
                  fetchDossiers(validationDecisionId);
                }
              }}
              className={`px-3 py-1.5 text-xs font-semibold rounded transition ${
                activeTab === "dossiers"
                  ? "bg-zinc-800 text-white border border-zinc-700"
                  : "text-zinc-400 hover:text-white"
              }`}
              data-testid="tab-decision-dossiers"
            >
              Decision Dossiers
            </button>
          </div>

          {/* Tab 1: Overview & Scope */}
          {activeTab === "overview" && (
            <div className="space-y-6">
              {/* Conflict Alert (if any) */}
              {trustData.conflicts && trustData.conflicts.length > 0 && (
                <div className="p-4 rounded-lg bg-rose-950/40 border border-rose-500/50 text-rose-200" data-testid="conflicts-container">
                  <div className="flex items-center gap-2 font-semibold text-xs text-rose-300">
                    <AlertTriangle className="w-4 h-4" />
                    Conflict Detected ({trustData.conflicts.length})
                  </div>
                  <div className="mt-2 space-y-2">
                    {trustData.conflicts.map((c, i) => (
                      <div key={i} className="text-xs p-2.5 rounded bg-rose-950/60 border border-rose-500/30">
                        <div className="font-mono font-medium">{c.conflict_type}</div>
                        <div className="text-zinc-300 mt-1">{c.detail}</div>
                        {c.delta_pct !== null && c.delta_pct !== undefined && (
                          <div className="text-[11px] text-rose-400 mt-0.5">
                            Divergence: {c.delta_pct}% (Delta: {c.delta})
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Scope / Applicability */}
              <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800" data-testid="scope-container">
                <div className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-2">
                  <Database className="w-3.5 h-3.5 text-amber-400" />
                  Scope & Applicability Envelope
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3 text-xs">
                  {Object.entries(trustData.scope).map(([k, v]) => (
                    <div key={k} className="p-2 rounded bg-zinc-900 border border-zinc-800 font-mono">
                      <div className="text-[10px] text-zinc-500 uppercase">{k}</div>
                      <div className="text-zinc-200 truncate mt-0.5" title={String(v)}>
                        {String(v ?? "—")}
                      </div>
                    </div>
                  ))}
                  {Object.keys(trustData.scope).length === 0 && (
                    <div className="text-xs text-zinc-500 italic">No scope boundaries recorded.</div>
                  )}
                </div>
              </div>

              {/* Trust Explanation */}
              <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800" data-testid="explanation-container">
                <div className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-2">
                  <FileCheck2 className="w-3.5 h-3.5 text-amber-400" />
                  Auditable Trust Explanation
                </div>
                <div className="mt-3 space-y-2">
                  {trustData.explanation.reasons.map((r, i) => (
                    <div key={i} className="text-xs text-zinc-300 flex items-start gap-2">
                      <span className="text-amber-400 font-mono">▸</span>
                      <span>{r}</span>
                    </div>
                  ))}
                </div>

                {trustData.explanation.limitations && trustData.explanation.limitations.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-zinc-800">
                    <div className="text-[10px] uppercase font-mono text-zinc-500 tracking-wider">
                      Known Limitations
                    </div>
                    <ul className="mt-1 list-disc list-inside text-xs text-zinc-400 space-y-1">
                      {trustData.explanation.limitations.map((lim, i) => (
                        <li key={i}>{lim}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Recency Metadata (TRUST_RECENCY_POLICY_V1) */}
              <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800" data-testid="recency-container">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-2">
                    <Clock className="w-3.5 h-3.5 text-amber-400" />
                    Validation Recency Metadata
                  </div>
                  {trustData.recency.recency_condition && (
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-zinc-800 text-amber-300 border border-zinc-700">
                      {trustData.recency.recency_condition}
                    </span>
                  )}
                </div>

                {/* Recency Warning / Advisory if recommended */}
                {trustData.recency.reassessment_recommended && (
                  <div className="mt-3 p-2.5 rounded bg-amber-950/40 border border-amber-500/30 text-xs text-amber-200 flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold text-amber-300">Reassessment Recommended</div>
                      <div className="text-zinc-300 mt-0.5">{trustData.recency.reassessment_reason}</div>
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3 text-xs font-mono">
                  <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                    <div className="text-[10px] text-zinc-500 uppercase">Evidence Timestamp</div>
                    <div className="text-zinc-200 mt-0.5">{trustData.recency.evidence_timestamp || "—"}</div>
                  </div>
                  <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                    <div className="text-[10px] text-zinc-500 uppercase">Validation Timestamp</div>
                    <div className="text-zinc-200 mt-0.5">{trustData.recency.validation_timestamp || "—"}</div>
                  </div>
                  <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                    <div className="text-[10px] text-zinc-500 uppercase">Source Version</div>
                    <div className="text-zinc-200 mt-0.5">{trustData.recency.source_version || "—"}</div>
                  </div>
                  <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                    <div className="text-[10px] text-zinc-500 uppercase">Age (Days)</div>
                    <div className="text-zinc-200 mt-0.5">{trustData.recency.age_days ?? "—"}</div>
                  </div>
                </div>

                {/* Epistemic Aging Invariant Note */}
                <div className="mt-3 p-2 rounded bg-zinc-900/60 border border-zinc-800/80 text-[11px] text-zinc-400 flex items-start gap-2">
                  <span className="text-amber-400 font-bold shrink-0">ℹ</span>
                  <span>
                    <strong>Epistemic Invariant:</strong> {trustData.recency.epistemic_aging_note || "Evidence aging reflects temporal epistemic recency, NOT physical component degradation or mechanical fatigue."}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Tab 2: Supporting Evidence */}
          {activeTab === "evidence" && (
            <div className="space-y-4" data-testid="evidence-container">
              {trustData.supporting_evidence.length === 0 ? (
                <div className="p-6 text-center text-xs text-zinc-500 italic rounded-lg bg-zinc-900/40 border border-zinc-800">
                  No supporting evidence artifacts connected in the Evidence Graph.
                </div>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-zinc-800">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-zinc-900/80 text-zinc-400 uppercase font-mono text-[10px] border-b border-zinc-800">
                      <tr>
                        <th className="p-3">Relationship</th>
                        <th className="p-3">Artifact Type</th>
                        <th className="p-3">Artifact ID</th>
                        <th className="p-3">Artifact Hash</th>
                        <th className="p-3">Timestamp</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-800/60 font-mono">
                      {trustData.supporting_evidence.map((ev, i) => (
                        <tr key={i} className="hover:bg-zinc-900/40">
                          <td className="p-3 text-amber-400 font-semibold">{ev.relationship}</td>
                          <td className="p-3 text-zinc-300">{ev.evidence_type}</td>
                          <td className="p-3 text-white">{ev.evidence_id}</td>
                          <td className="p-3 text-zinc-500 text-[11px] truncate max-w-xs" title={ev.artifact_hash}>
                            {ev.artifact_hash.slice(0, 16)}...
                          </td>
                          <td className="p-3 text-zinc-400 text-[11px]">{ev.timestamp || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Tab 3: History */}
          {activeTab === "history" && (
            <div className="space-y-4" data-testid="history-container">
              {historyItems.length === 0 ? (
                <div className="p-6 text-center text-xs text-zinc-500 italic rounded-lg bg-zinc-900/40 border border-zinc-800">
                  No historical assessments recorded yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {historyItems.map((h, i) => (
                    <div
                      key={h.id || i}
                      className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-zinc-400 text-[11px]">{h.created_at}</span>
                          <span className="font-mono text-[10px] text-zinc-600">ID: {h.id.slice(0, 8)}</span>
                        </div>
                        <div className="mt-1 flex items-center gap-2">
                          <span className="font-semibold text-white">{h.trust_state}</span>
                          <span className="text-zinc-500">•</span>
                          <span className="text-zinc-400">{h.validation_coverage}</span>
                          <span className="text-zinc-500">•</span>
                          <span className="text-zinc-500 font-mono text-[11px]">
                            Policy: {h.policy_version}
                          </span>
                        </div>
                      </div>
                      <div className="text-right font-mono text-[11px] text-zinc-500">
                        <div title={h.assessment_hash}>Hash: {h.assessment_hash.slice(0, 16)}...</div>
                        <div title={h.value_identity}>Val: {h.value_identity}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Tab 4: Sweep Analysis */}
          {activeTab === "sweep" && (
            <div className="space-y-6" data-testid="sweep-container">
              <div className="flex items-center justify-between p-4 rounded-lg bg-zinc-900/40 border border-zinc-800">
                <div>
                  <div className="text-xs font-semibold text-white flex items-center gap-2">
                    <Sliders className="w-4 h-4 text-amber-400" />
                    Cross-Variant Parameter Sweep Analysis
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-1">
                    Evaluates comparability across candidate setups, sweeps, and simulation runs.
                  </div>
                </div>
                <button
                  onClick={handleRunSweep}
                  disabled={sweepLoading}
                  className="px-3 py-1.5 text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-black rounded transition flex items-center gap-1.5 disabled:opacity-50"
                  data-testid="btn-run-sweep"
                >
                  <Sliders className="w-3.5 h-3.5" />
                  {sweepLoading ? "Analyzing Sweep..." : "Run Sweep Analysis"}
                </button>
              </div>

              {sweepError && (
                <div className="p-3 rounded bg-red-950/40 border border-red-500/30 text-red-300 text-xs">
                  {sweepError}
                </div>
              )}

              {sweepData && (
                <div className="space-y-4">
                  {/* Sweep Metrics Cards */}
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-3 font-mono">
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Min Value</div>
                      <div className="text-base font-bold text-white mt-1">
                        {sweepData.summary_metrics.min ?? "—"} <span className="text-xs font-normal text-amber-400">{sweepData.canonical_unit}</span>
                      </div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Max Value</div>
                      <div className="text-base font-bold text-white mt-1">
                        {sweepData.summary_metrics.max ?? "—"} <span className="text-xs font-normal text-amber-400">{sweepData.canonical_unit}</span>
                      </div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Delta (Range)</div>
                      <div className="text-base font-bold text-white mt-1">
                        {sweepData.summary_metrics.delta ?? "—"} <span className="text-xs font-normal text-amber-400">{sweepData.canonical_unit}</span>
                      </div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Mean Value</div>
                      <div className="text-base font-bold text-white mt-1">
                        {sweepData.summary_metrics.mean ?? "—"} <span className="text-xs font-normal text-amber-400">{sweepData.canonical_unit}</span>
                      </div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Comparable</div>
                      <div className="text-base font-bold text-emerald-400 mt-1">
                        {sweepData.comparable_count} / {sweepData.total_observations}
                      </div>
                    </div>
                  </div>

                  {/* Evidence Gaps */}
                  <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800">
                    <div className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center justify-between">
                      <span>Validation Coverage Across Sweep</span>
                      <span className="font-mono text-amber-400">{sweepData.evidence_gaps.coverage_pct}% Validated</span>
                    </div>
                    <div className="mt-2 text-xs text-zinc-400 flex items-center gap-4">
                      <span>Validated: {sweepData.evidence_gaps.validated_candidates.length}</span>
                      <span>Unvalidated: {sweepData.evidence_gaps.unvalidated_candidates.length}</span>
                      <span>Excluded: {sweepData.excluded_count}</span>
                    </div>
                  </div>

                  {/* Observations Table */}
                  <div className="rounded-lg border border-zinc-800 overflow-hidden">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-zinc-900 text-zinc-400 font-mono text-[11px] uppercase">
                        <tr>
                          <th className="p-3">Candidate / Entity</th>
                          <th className="p-3">Observed Value</th>
                          <th className="p-3">Trust State</th>
                          <th className="p-3">Validation</th>
                          <th className="p-3">Comparability</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800 bg-zinc-900/20 font-mono">
                        {sweepData.observations.map((obs, i) => (
                          <tr key={i} className="hover:bg-zinc-900/40">
                            <td className="p-3 text-white font-medium">{obs.entity_type}:{obs.entity_id}</td>
                            <td className="p-3 text-zinc-300">{obs.value} {obs.unit}</td>
                            <td className="p-3">{obs.trust_state}</td>
                            <td className="p-3 text-zinc-400">{obs.validation_coverage}</td>
                            <td className="p-3">
                              {obs.is_comparable ? (
                                <span className="text-emerald-400">Comparable</span>
                              ) : (
                                <span className="text-rose-400" title={obs.exclusion_reason || ""}>Not Comparable</span>
                              )}
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

          {/* Tab 5: Automated Ingestion */}
          {activeTab === "ingestion" && (
            <div className="space-y-6" data-testid="ingestion-container">
              <div className="flex items-center justify-between p-4 rounded-lg bg-zinc-900/40 border border-zinc-800">
                <div>
                  <div className="text-xs font-semibold text-white flex items-center gap-2">
                    <RefreshCw className="w-4 h-4 text-amber-400" />
                    Automated Trust Ingestion & Reconciliation
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-1">
                    Discovers all eligible parameters from {entityType}:{entityId} and reconciles trust assessments idempotently.
                  </div>
                </div>
                <button
                  onClick={handleRunIngest}
                  disabled={ingestLoading}
                  className="px-3 py-1.5 text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-black rounded transition flex items-center gap-1.5 disabled:opacity-50"
                  data-testid="btn-run-ingest"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${ingestLoading ? "animate-spin" : ""}`} />
                  {ingestLoading ? "Ingesting..." : "Ingest Entity Parameters"}
                </button>
              </div>

              {ingestError && (
                <div className="p-3 rounded bg-red-950/40 border border-red-500/30 text-red-300 text-xs">
                  {ingestError}
                </div>
              )}

              {ingestSummary && (
                <div className="space-y-4">
                  {/* Summary KPI grid */}
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-3 font-mono text-xs">
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Discovered</div>
                      <div className="text-base font-bold text-white mt-1">{ingestSummary.discovered_parameters}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">New Profiles</div>
                      <div className="text-base font-bold text-emerald-400 mt-1">{ingestSummary.new_profiles}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Refreshed</div>
                      <div className="text-base font-bold text-cyan-400 mt-1">{ingestSummary.refreshed_assessments}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Unchanged</div>
                      <div className="text-base font-bold text-zinc-400 mt-1">{ingestSummary.unchanged_assessments}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Evidence Linked</div>
                      <div className="text-base font-bold text-amber-400 mt-1">{ingestSummary.linked_evidence_count}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Conflicts</div>
                      <div className="text-base font-bold text-rose-400 mt-1">{ingestSummary.conflicts_found}</div>
                    </div>
                  </div>

                  {/* Profiles Table */}
                  <div className="rounded-lg border border-zinc-800 overflow-hidden">
                    <table className="w-full text-xs text-left">
                      <thead className="bg-zinc-900 text-zinc-400 font-mono text-[11px] uppercase">
                        <tr>
                          <th className="p-3">Parameter Name</th>
                          <th className="p-3">Unit</th>
                          <th className="p-3">Trust State</th>
                          <th className="p-3">Validation</th>
                          <th className="p-3">Recency</th>
                          <th className="p-3">Assessment Hash</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800 bg-zinc-900/20 font-mono">
                        {ingestSummary.profiles.map((p, i) => (
                          <tr key={i} className="hover:bg-zinc-900/40">
                            <td className="p-3 text-white font-medium">{p.parameter_name}</td>
                            <td className="p-3 text-zinc-400">{p.unit || "—"}</td>
                            <td className="p-3">{p.trust_state}</td>
                            <td className="p-3 text-zinc-400">{p.validation_coverage}</td>
                            <td className="p-3 text-zinc-400">{p.recency_condition}</td>
                            <td className="p-3 text-zinc-500">{p.assessment_hash.slice(0, 12)}...</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Tab 6: Fleet Trust Synchronization */}
          {activeTab === "fleet" && (
            <div className="space-y-6" data-testid="fleet-container">
              <div className="flex flex-col md:flex-row md:items-center justify-between p-4 rounded-lg bg-zinc-900/40 border border-zinc-800 gap-3">
                <div>
                  <div className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
                    Fleet-Wide Trust Synchronization
                  </div>
                  <div className="text-xs text-zinc-400 mt-0.5">
                    Multi-vehicle parameter comparability without merging incompatible evidence or overwriting local records.
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={fleetId}
                    onChange={(e) => setFleetId(e.target.value)}
                    placeholder="Fleet Cohort ID"
                    className="px-3 py-1.5 text-xs bg-zinc-900 border border-zinc-700 rounded text-zinc-200 focus:outline-none focus:border-amber-400 font-mono w-44"
                    data-testid="input-fleet-id"
                  />
                  <button
                    onClick={handleRunFleetSync}
                    disabled={fleetLoading}
                    className="px-4 py-1.5 text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-black rounded transition flex items-center gap-1.5 disabled:opacity-50"
                    data-testid="btn-run-fleet-sync"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${fleetLoading ? "animate-spin" : ""}`} />
                    {fleetLoading ? "Synchronizing..." : "Synchronize Cohort"}
                  </button>
                </div>
              </div>

              {fleetError && (
                <div className="p-3 rounded bg-red-950/40 border border-red-500/30 text-red-300 text-xs">
                  {fleetError}
                </div>
              )}

              {fleetData && (
                <div className="space-y-6">
                  {/* Summary Stats Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-3 font-mono text-xs">
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Cohort Size</div>
                      <div className="text-base font-bold text-white mt-1">{fleetData.cohort_size}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Comparable</div>
                      <div className="text-base font-bold text-emerald-400 mt-1">{fleetData.comparable_count}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Missing</div>
                      <div className="text-base font-bold text-zinc-400 mt-1">{fleetData.missing_count}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Excluded</div>
                      <div className="text-base font-bold text-rose-400 mt-1">{fleetData.excluded_count}</div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Range (Min - Max)</div>
                      <div className="text-xs font-bold text-amber-400 mt-1 truncate">
                        {fleetData.summary_metrics.min ?? "—"} – {fleetData.summary_metrics.max ?? "—"}
                      </div>
                    </div>
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800">
                      <div className="text-[10px] text-zinc-500 uppercase">Median / Mean</div>
                      <div className="text-xs font-bold text-cyan-400 mt-1 truncate">
                        {fleetData.summary_metrics.median ?? "—"} / {fleetData.summary_metrics.mean ?? "—"}
                      </div>
                    </div>
                  </div>

                  {/* Outliers Alert Box */}
                  {fleetData.outliers && fleetData.outliers.length > 0 && (
                    <div className="p-4 rounded-lg bg-amber-950/40 border border-amber-500/40 text-amber-200 space-y-2">
                      <div className="flex items-center gap-2 font-semibold text-xs text-amber-300">
                        <AlertTriangle className="w-4 h-4" />
                        Statistical Outliers Detected ({fleetData.outliers.length})
                      </div>
                      <div className="text-[11px] text-amber-300/80 italic">
                        Notice: Statistical outlier does not constitute an engineering defect or automatic rejection.
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
                        {fleetData.outliers.map((outlier, idx) => (
                          <div key={idx} className="p-2.5 rounded bg-zinc-900/80 border border-zinc-800 text-xs font-mono">
                            <div className="text-white font-semibold">{outlier.vehicle_ref}</div>
                            <div className="text-amber-400 mt-1">Value: {outlier.value}</div>
                            <div className="text-[10px] text-zinc-400 mt-0.5">{outlier.note}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Comparable Instances Table */}
                  <div className="rounded-lg border border-zinc-800 overflow-hidden">
                    <div className="bg-zinc-900 p-3 text-xs font-semibold uppercase font-mono text-zinc-300">
                      Comparable Fleet Instances ({fleetData.comparable_instances.length})
                    </div>
                    <table className="w-full text-xs text-left">
                      <thead className="bg-zinc-900/80 text-zinc-400 font-mono text-[11px] uppercase">
                        <tr>
                          <th className="p-3">Vehicle Ref</th>
                          <th className="p-3">Normalized Value</th>
                          <th className="p-3">Unit</th>
                          <th className="p-3">Trust State</th>
                          <th className="p-3">Validation</th>
                          <th className="p-3">Provenance</th>
                          <th className="p-3">Assessment Hash</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-800 bg-zinc-900/20 font-mono">
                        {fleetData.comparable_instances.map((inst, idx) => (
                          <tr key={idx} className="hover:bg-zinc-900/40">
                            <td className="p-3 text-white font-medium">{inst.vehicle_ref}</td>
                            <td className="p-3 text-amber-400 font-bold">{inst.normalized_value}</td>
                            <td className="p-3 text-zinc-400">{inst.canonical_unit}</td>
                            <td className="p-3">{inst.trust_state}</td>
                            <td className="p-3 text-zinc-400">{inst.validation_coverage}</td>
                            <td className="p-3 text-zinc-400">{inst.provenance_class}</td>
                            <td className="p-3 text-zinc-500">{inst.assessment_hash?.slice(0, 10)}...</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Tab 7: Assembly Propagation & Sensitivity */}
          {activeTab === "propagation" && (
            <div className="space-y-6" data-testid="propagation-container">
              {/* Invariant Alert */}
              <div className="p-4 rounded-lg bg-blue-950/40 border border-blue-500/40 text-blue-200 text-xs">
                <div className="flex items-center gap-2 font-semibold text-blue-300">
                  <Layers className="w-4 h-4 shrink-0" />
                  Strict Invariant: Direct Trust is Decoupled from Propagated Impact
                </div>
                <p className="mt-1 text-zinc-300">
                  A component parameter has direct trust (e.g. PROVISIONAL or VALIDATED); an affected assembly has an impact assessment.
                  Downstream uncertainty does not rewrite local parameter trust.
                </p>
                <div className="mt-3">
                  <button
                    onClick={handleRunAssemblyImpact}
                    disabled={impactLoading}
                    className="px-4 py-1.5 text-xs font-semibold bg-blue-500 hover:bg-blue-400 text-white rounded transition flex items-center gap-1.5 disabled:opacity-50"
                    data-testid="btn-run-assembly-impact"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${impactLoading ? "animate-spin" : ""}`} />
                    {impactLoading ? "Evaluating..." : "Evaluate Assembly Impact"}
                  </button>
                </div>
              </div>

              {impactError && (
                <div className="p-3 rounded bg-red-950/40 border border-red-500/30 text-red-300 text-xs">
                  {impactError}
                </div>
              )}

              {impactData && (
                <div className="space-y-6">
                  {/* Dependency Path Breadcrumbs */}
                  {impactData.dependency_path && (
                    <div className="p-3 rounded bg-zinc-900 border border-zinc-800 text-xs font-mono text-zinc-300 flex items-center gap-2">
                      <span className="text-zinc-500 uppercase text-[10px]">Structural Lineage:</span>
                      <span className="text-amber-400 font-semibold">{impactData.dependency_path.join(" ➔ ")}</span>
                    </div>
                  )}

                  {/* Impact & Direct Trust Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Direct Parameter Assessment */}
                    <div className="p-4 rounded-lg bg-zinc-900 border border-zinc-800">
                      <div className="text-xs font-semibold uppercase font-mono text-zinc-400">
                        Direct Component Trust
                      </div>
                      <div className="mt-2 space-y-1 font-mono text-xs">
                        <div className="text-white">
                          Trust State: <span className="font-semibold text-amber-400">{impactData.direct_trust_assessment?.trust_state}</span>
                        </div>
                        <div className="text-zinc-400">
                          Coverage: {impactData.direct_trust_assessment?.validation_coverage}
                        </div>
                        <div className="text-zinc-400">
                          Conflicts: {impactData.direct_trust_assessment?.conflicts_count ?? 0}
                        </div>
                      </div>
                    </div>

                    {/* Propagated Assembly Impact */}
                    <div className="p-4 rounded-lg bg-zinc-900 border border-zinc-800">
                      <div className="text-xs font-semibold uppercase font-mono text-zinc-400">
                        Propagated Assembly Impact
                      </div>
                      <div className="mt-2 space-y-1 font-mono text-xs">
                        <div className="text-white font-semibold">
                          Classification: <span className="text-cyan-400">{impactData.impact_assessment?.impact_classification}</span>
                        </div>
                        <div className="text-zinc-300 text-[11px] mt-1 font-sans">
                          {impactData.impact_assessment?.impact_summary}
                        </div>
                        <div className="text-zinc-400 text-[10px] mt-2 pt-2 border-t border-zinc-800/80 font-mono">
                          Threshold Provenance: <span className="text-amber-300">{impactData.impact_assessment?.threshold_provenance || "PROVISIONAL"}</span> (Analytical Screening Bins)
                        </div>
                        <div className="text-zinc-500 text-[10px] mt-1 font-sans italic">
                          Deployment Safety: Independent Governance Gate (Not Inferred)
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Sensitivity Evidence Details */}
                  {impactData.sensitivity_evidence && (
                    <div className="p-4 rounded-lg bg-zinc-900/60 border border-zinc-800 space-y-3">
                      <div className="text-xs font-semibold uppercase font-mono text-zinc-300 flex items-center justify-between">
                        <span>Authoritative Sensitivity Evidence</span>
                        <span className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 text-amber-400 border border-zinc-700">
                          STATUS: {impactData.sensitivity_evidence.status}
                        </span>
                      </div>

                      {impactData.sensitivity_evidence.status === "SENSITIVITY_UNAVAILABLE" ? (
                        <div className="p-3 rounded bg-amber-950/30 border border-amber-500/30 text-amber-300 text-xs">
                          {impactData.sensitivity_evidence.warning || "Sensitivity evidence unavailable. Missing sensitivity is never treated as zero."}
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 font-mono text-xs">
                            <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                              <div className="text-[10px] text-zinc-500 uppercase">Source</div>
                              <div className="text-white truncate">{impactData.sensitivity_evidence.source_type}:{impactData.sensitivity_evidence.source_id}</div>
                            </div>
                            <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                              <div className="text-[10px] text-zinc-500 uppercase">Method</div>
                              <div className="text-white truncate">{impactData.sensitivity_evidence.method}</div>
                            </div>
                            <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                              <div className="text-[10px] text-zinc-500 uppercase">Regime</div>
                              <div className="text-white truncate">{impactData.sensitivity_evidence.operating_regime}</div>
                            </div>
                            <div className="p-2 rounded bg-zinc-900 border border-zinc-800">
                              <div className="text-[10px] text-zinc-500 uppercase">Artifact Hash</div>
                              <div className="text-zinc-400 truncate">{impactData.sensitivity_evidence.artifact_hash?.slice(0, 10)}...</div>
                            </div>
                          </div>

                          {/* Downstream KPIs */}
                          {impactData.impact_assessment?.downstream_metrics && impactData.impact_assessment.downstream_metrics.length > 0 && (
                            <div className="rounded border border-zinc-800 overflow-hidden">
                              <table className="w-full text-xs text-left">
                                <thead className="bg-zinc-900 text-zinc-400 font-mono text-[11px] uppercase">
                                  <tr>
                                    <th className="p-2.5">Downstream KPI</th>
                                    <th className="p-2.5">Sensitivity Unit</th>
                                    <th className="p-2.5">Elasticity / Magnitude</th>
                                    <th className="p-2.5">Direction</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-zinc-800 bg-zinc-900/20 font-mono">
                                  {impactData.impact_assessment.downstream_metrics.map((m: any, idx: number) => (
                                    <tr key={idx}>
                                      <td className="p-2.5 text-white font-medium">{m.metric || m.kpi}</td>
                                      <td className="p-2.5 text-zinc-400">{m.unit || "unit(y)/unit(x)"}</td>
                                      <td className="p-2.5 text-amber-400 font-semibold">{m.elasticity ?? m.sensitivity ?? "—"}</td>
                                      <td className="p-2.5 text-zinc-300">{m.direction || "—"}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Tab 8: Decision-Aware Trust & Exposure Engine (Phase 6.4) */}
          {activeTab === "decisions" && (
            <div className="space-y-6" data-testid="tab-decisions-content">
              {/* Decision Query Controls */}
              <div className="p-4 rounded-lg bg-zinc-900/60 border border-zinc-800 space-y-3">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                      <Target className="w-4 h-4 text-amber-400" />
                      Engineering Decision Exposure & Evidence Integration
                    </h3>
                    <p className="text-xs text-zinc-400">
                      Grounded uncertainty quantification: connects decisions to parameter trust, quantitative sensitivities, and prioritized validation gaps.
                    </p>
                  </div>
                  {/* Preset Decision Chips */}
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-[10px] uppercase font-mono text-zinc-500">Presets:</span>
                    {["DEC-12", "DEC-P3L-01", "PROB-P3L-01", "INV-91"].map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        onClick={() => {
                          setDecisionId(preset);
                          const dtype = preset.startsWith("PROB") ? "EngineeringProblem" : preset.startsWith("INV") ? "Investigation" : "EngineeringDecision";
                          setDecisionType(dtype);
                          fetchDecisionExposure(preset, dtype);
                        }}
                        className="px-2 py-0.5 text-[10px] font-mono rounded bg-zinc-800 hover:bg-zinc-700 text-amber-300 border border-zinc-700 transition"
                      >
                        {preset}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-zinc-800/80">
                  <input
                    type="text"
                    value={decisionId}
                    onChange={(e) => setDecisionId(e.target.value)}
                    placeholder="Decision ID (e.g. DEC-12)"
                    className="px-3 py-1.5 text-xs bg-zinc-900 border border-zinc-700 rounded text-zinc-200 focus:outline-none focus:border-amber-400 w-44 font-mono"
                    data-testid="input-decision-id"
                  />
                  <select
                    value={decisionType}
                    onChange={(e) => setDecisionType(e.target.value)}
                    className="px-3 py-1.5 text-xs bg-zinc-900 border border-zinc-700 rounded text-zinc-200 focus:outline-none focus:border-amber-400 font-mono"
                    data-testid="select-decision-type"
                  >
                    <option value="EngineeringDecision">EngineeringDecision</option>
                    <option value="EngineeringProblem">EngineeringProblem</option>
                    <option value="Investigation">Investigation</option>
                  </select>
                  <button
                    type="button"
                    onClick={() => fetchDecisionExposure(decisionId, decisionType, false)}
                    disabled={decisionLoading}
                    className="px-3.5 py-1.5 text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-black rounded transition flex items-center gap-1.5 disabled:opacity-50"
                    data-testid="btn-assess-decision"
                  >
                    <Search className="w-3.5 h-3.5" />
                    {decisionLoading ? "Evaluating..." : "Assess Exposure"}
                  </button>
                  <button
                    type="button"
                    onClick={() => fetchDecisionExposure(decisionId, decisionType, true)}
                    disabled={decisionLoading}
                    className="px-3 py-1.5 text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 rounded transition flex items-center gap-1.5 disabled:opacity-50"
                    data-testid="btn-reassess-decision"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    Reassess (Supersede)
                  </button>
                </div>
              </div>

              {/* Error banner */}
              {decisionError && (
                <div className="p-3 rounded-lg bg-red-950/50 border border-red-500/40 text-red-300 text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0 text-red-400" />
                  <span>{decisionError}</span>
                </div>
              )}

              {/* Assessment Results */}
              {decisionExposureData && (
                <div className="space-y-6">
                  {/* Primary Exposure Classification Card */}
                  <div className="p-5 rounded-lg bg-zinc-900/60 border border-zinc-800">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-mono tracking-widest uppercase px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                            POLICY: {decisionExposureData.policy_version}
                          </span>
                          <span className="text-[10px] font-mono text-zinc-500">
                            DECISION: {decisionExposureData.decision_id} ({decisionExposureData.decision_type})
                          </span>
                        </div>
                        <h2 className="text-lg font-bold text-white mt-1">
                          Decision Exposure Posture
                        </h2>
                        <p className="text-xs text-zinc-300 mt-1 max-w-3xl" data-testid="decision-exposure-summary">
                          {decisionExposureData.exposure_summary}
                        </p>
                      </div>

                      <div className="text-right">
                        <div className="text-[10px] text-zinc-400 uppercase font-mono mb-1">Exposure Classification</div>
                        <span
                          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-bold border ${
                            decisionExposureData.exposure_classification === "LOW_EXPOSURE"
                              ? "bg-emerald-950/70 border-emerald-500/40 text-emerald-300"
                              : decisionExposureData.exposure_classification === "MODERATE_EXPOSURE"
                              ? "bg-amber-950/70 border-amber-500/40 text-amber-300"
                              : decisionExposureData.exposure_classification === "HIGH_EXPOSURE"
                              ? "bg-orange-950/70 border-orange-500/40 text-orange-300"
                              : decisionExposureData.exposure_classification === "CRITICAL_CONFLICT_EXPOSURE"
                              ? "bg-rose-950/70 border-rose-500/40 text-rose-300"
                              : "bg-zinc-800 border-zinc-700 text-zinc-300"
                          }`}
                          data-testid="decision-exposure-badge"
                        >
                          <Scale className="w-3.5 h-3.5" />
                          {decisionExposureData.exposure_classification}
                        </span>
                        <div className="text-[10px] text-zinc-500 font-mono mt-1.5">
                          Thresholds: <span className="text-amber-300">{decisionExposureData.threshold_provenance || "PROVISIONAL"}</span> (Analytical Screening)
                        </div>
                      </div>
                    </div>

                    {/* Hashes & Lineage */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-4 pt-4 border-t border-zinc-800 text-[11px] font-mono">
                      <div className="p-2 rounded bg-zinc-950/60 border border-zinc-800/80">
                        <span className="text-zinc-500">Input Snapshot Hash:</span>{" "}
                        <span className="text-zinc-300">{decisionExposureData.input_snapshot_hash}</span>
                      </div>
                      <div className="p-2 rounded bg-zinc-950/60 border border-zinc-800/80">
                        <span className="text-zinc-500">Assessment Hash:</span>{" "}
                        <span className="text-amber-400">{decisionExposureData.assessment_hash}</span>
                      </div>
                    </div>
                  </div>

                  {/* Strict Governance Separation (6-Pillar Card) */}
                  <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800 space-y-3">
                    <div className="flex items-center gap-2">
                      <Workflow className="w-4 h-4 text-amber-400" />
                      <span className="text-xs font-semibold uppercase font-mono text-zinc-300">
                        Strict Governance Separation (Non-Conflated Architecture)
                      </span>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2 text-xs font-mono">
                      <div className="p-2.5 rounded bg-zinc-900 border border-zinc-800">
                        <div className="text-[9px] uppercase text-zinc-500">1. Parameter Trust</div>
                        <div className="text-white font-semibold mt-1">
                          {Object.keys(decisionExposureData.governance_separation.parameter_trust_states).length} Parameters
                        </div>
                        <div className="text-[10px] text-zinc-400 truncate mt-0.5">Local component posture</div>
                      </div>

                      <div className="p-2.5 rounded bg-zinc-900 border border-zinc-800">
                        <div className="text-[9px] uppercase text-zinc-500">2. Sensitivity / Impact</div>
                        <div className="text-white font-semibold mt-1">Physical Deriv.</div>
                        <div className="text-[10px] text-zinc-400 truncate mt-0.5">∂(KPI) / ∂(Param)</div>
                      </div>

                      <div className="p-2.5 rounded bg-zinc-900 border border-zinc-800">
                        <div className="text-[9px] uppercase text-zinc-500">3. Completeness</div>
                        <div className="text-white font-semibold mt-1">Evidence Coverage</div>
                        <div className="text-[10px] text-zinc-400 truncate mt-0.5">Holdout validation & recency</div>
                      </div>

                      <div className="p-2.5 rounded bg-zinc-900 border border-zinc-800">
                        <div className="text-[9px] uppercase text-zinc-500">4. Decision Exposure</div>
                        <div className="text-amber-400 font-semibold mt-1 truncate">
                          {decisionExposureData.exposure_classification}
                        </div>
                        <div className="text-[10px] text-zinc-400 truncate mt-0.5">Premise vulnerability</div>
                      </div>

                      <div className="p-2.5 rounded bg-zinc-900 border border-zinc-800">
                        <div className="text-[9px] uppercase text-zinc-500">5. Human Approval</div>
                        <div className="text-emerald-400 font-semibold mt-1">
                          {decisionExposureData.governance_separation.approval_authorization.decision_status}
                        </div>
                        <div className="text-[10px] text-zinc-400 truncate mt-0.5">
                          {decisionExposureData.governance_separation.approval_authorization.is_human_approved ? "Signed" : "Pending Sign-off"}
                        </div>
                      </div>

                      <div className="p-2.5 rounded bg-zinc-900 border border-zinc-800">
                        <div className="text-[9px] uppercase text-zinc-500">6. Deployment Safety</div>
                        <div className="text-rose-400 font-semibold mt-1">NOT ESTABLISHED</div>
                        <div className="text-[10px] text-zinc-400 truncate mt-0.5">Independent Commissioning</div>
                      </div>
                    </div>

                    <div className="p-2.5 rounded bg-zinc-950/60 border border-zinc-800 text-[11px] text-zinc-400 font-sans italic">
                      {decisionExposureData.governance_separation_notice}
                    </div>
                  </div>

                  {/* Differential Reassessment Notice (if present) */}
                  {decisionExposureData.differential && (
                    <div className="p-4 rounded-lg bg-amber-950/30 border border-amber-500/40 text-amber-200 text-xs space-y-1">
                      <div className="font-semibold flex items-center gap-1.5">
                        <RefreshCw className="w-3.5 h-3.5" />
                        Supersession Differential Analysis
                      </div>
                      <p>{decisionExposureData.differential.rationale}</p>
                      <div className="text-[10px] font-mono text-amber-400/80 pt-1">
                        Previous Hash: {decisionExposureData.differential.previous_hash.slice(0, 16)}... → New Hash: {decisionExposureData.differential.new_hash.slice(0, 16)}...
                      </div>
                    </div>
                  )}

                  {/* Parameter Dependencies Table */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-semibold uppercase font-mono text-zinc-300 flex items-center gap-2">
                        <FileText className="w-4 h-4 text-amber-400" />
                        Decision Parameter Dependencies ({decisionExposureData.parameter_dependencies.length})
                      </h3>
                      <span className="text-[10px] font-mono text-zinc-500">
                        Direct vs Quantitative vs Qualitative vs Unresolved
                      </span>
                    </div>

                    <div className="rounded-lg border border-zinc-800 overflow-hidden bg-zinc-900/30">
                      <table className="w-full text-xs text-left" data-testid="table-decision-dependencies">
                        <thead className="bg-zinc-900 text-zinc-400 font-mono text-[11px] uppercase border-b border-zinc-800">
                          <tr>
                            <th className="p-3">Parameter & Entity</th>
                            <th className="p-3">Dependency Nature</th>
                            <th className="p-3">Downstream KPIs</th>
                            <th className="p-3">Numerical Sensitivity</th>
                            <th className="p-3">Local Trust Posture</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-800 font-mono text-xs">
                          {decisionExposureData.parameter_dependencies.map((dep, idx) => (
                            <tr key={idx} className="hover:bg-zinc-900/50 transition">
                              <td className="p-3">
                                <div className="text-white font-semibold">{dep.parameter_name}</div>
                                <div className="text-[10px] text-zinc-500">{dep.entity_type}:{dep.entity_id}</div>
                              </td>
                              <td className="p-3">
                                <span
                                  className={`inline-block px-2 py-0.5 text-[10px] font-bold rounded border ${
                                    dep.dependency_nature === "DIRECTLY_EVIDENCED"
                                      ? "bg-blue-950/70 border-blue-500/40 text-blue-300"
                                      : dep.dependency_nature === "QUANTITATIVELY_SENSITIVE"
                                      ? "bg-purple-950/70 border-purple-500/40 text-purple-300"
                                      : dep.dependency_nature === "QUALITATIVE_HYPOTHESIS"
                                      ? "bg-amber-950/70 border-amber-500/40 text-amber-300"
                                      : "bg-zinc-800 border-zinc-700 text-zinc-400"
                                  }`}
                                >
                                  {dep.dependency_nature}
                                </span>
                              </td>
                              <td className="p-3 text-zinc-300">
                                {dep.kpi_metrics && dep.kpi_metrics.length > 0 ? dep.kpi_metrics.join(", ") : "—"}
                              </td>
                              <td className="p-3">
                                {dep.elasticity !== null && dep.elasticity !== undefined ? (
                                  <div>
                                    <span className="text-amber-400 font-semibold">{dep.elasticity}</span>
                                    <span className="text-[10px] text-zinc-500 ml-1">({dep.derivative_unit || "ratio"})</span>
                                  </div>
                                ) : (
                                  <span className="text-zinc-500 text-[11px] italic">
                                    {dep.dependency_nature === "QUALITATIVE_HYPOTHESIS" ? "Directional trend only" : "Unavailable"}
                                  </span>
                                )}
                              </td>
                              <td className="p-3">
                                <div className="flex items-center gap-1.5">
                                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-200">
                                    {dep.direct_profile.trust_state}
                                  </span>
                                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-800 text-zinc-400">
                                    {dep.direct_profile.validation_coverage}
                                  </span>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Actionable Evidence Gaps & Experiment Recommendations */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-semibold uppercase font-mono text-zinc-300 flex items-center gap-2">
                        <FlaskConical className="w-4 h-4 text-amber-400" />
                        Actionable Evidence Gaps & Candidate Experiments ({decisionExposureData.evidence_gaps.length})
                      </h3>
                      <span className="text-[10px] font-mono text-zinc-500">
                        Prioritized uncertainty reduction designs
                      </span>
                    </div>

                    {decisionExposureData.evidence_gaps.length === 0 ? (
                      <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800 text-center text-xs text-zinc-400">
                        Zero actionable evidence gaps identified. All parameters backed by validated physical evidence.
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="container-evidence-gaps">
                        {decisionExposureData.evidence_gaps.map((gap, idx) => (
                          <div
                            key={idx}
                            className={`p-4 rounded-lg border space-y-2.5 ${
                              gap.severity === "CRITICAL"
                                ? "bg-rose-950/20 border-rose-500/40"
                                : gap.severity === "WARNING"
                                ? "bg-amber-950/20 border-amber-500/40"
                                : "bg-blue-950/20 border-blue-500/40"
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold text-white font-mono">{gap.parameter_name}</span>
                              <span
                                className={`px-2 py-0.5 text-[9px] font-bold rounded uppercase ${
                                  gap.severity === "CRITICAL"
                                    ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                                    : gap.severity === "WARNING"
                                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                                    : "bg-blue-500/20 text-blue-300 border border-blue-500/40"
                                }`}
                              >
                                {gap.severity} GAP
                              </span>
                            </div>

                            <p className="text-xs text-zinc-300">{gap.reason}</p>

                            <div className="p-2.5 rounded bg-zinc-950/60 border border-zinc-800 text-xs space-y-1 font-mono">
                              <div className="text-[10px] text-amber-400 uppercase font-semibold">Recommended Candidate Experiment</div>
                              <div className="text-white">{gap.candidate_experiment_type}</div>
                              <div className="text-[11px] text-zinc-400 mt-1">
                                <span className="text-zinc-500">Expected Info Gain:</span> {gap.expected_information_gain}
                              </div>
                            </div>

                            <div className="text-[10px] text-zinc-500 italic font-sans">
                              {gap.recommendation_disclaimer}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Audit History & Revisions */}
                  {decisionHistoryItems.length > 0 && (
                    <div className="space-y-3 pt-4 border-t border-zinc-800">
                      <div className="flex items-center justify-between">
                        <h3 className="text-xs font-semibold uppercase font-mono text-zinc-300 flex items-center gap-2">
                          <History className="w-4 h-4 text-amber-400" />
                          Historical Revisions & Supersession Lineage ({decisionHistoryItems.length})
                        </h3>
                        <span className="text-[10px] font-mono text-zinc-500">Append-only audit trail</span>
                      </div>

                      <div className="space-y-2">
                        {decisionHistoryItems.map((hist, idx) => (
                          <div
                            key={idx}
                            className={`p-3 rounded-lg border text-xs font-mono flex flex-col md:flex-row md:items-center justify-between gap-2 ${
                              hist.is_active
                                ? "bg-zinc-900/80 border-amber-500/40 text-white"
                                : "bg-zinc-950/40 border-zinc-800 text-zinc-400"
                            }`}
                          >
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-bold">{hist.exposure_classification}</span>
                                {hist.is_active ? (
                                  <span className="px-1.5 py-0.2 rounded text-[9px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                                    ACTIVE
                                  </span>
                                ) : (
                                  <span className="px-1.5 py-0.2 rounded text-[9px] bg-zinc-800 text-zinc-500">
                                    SUPERSEDED
                                  </span>
                                )}
                              </div>
                              <div className="text-[11px] text-zinc-400 mt-0.5">{hist.exposure_summary}</div>
                            </div>
                            <div className="text-right text-[10px] text-zinc-500">
                              <div>Hash: {hist.assessment_hash.slice(0, 16)}...</div>
                              <div>{hist.created_at ? new Date(hist.created_at).toLocaleString() : ""}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Tab 8: Decision Robustness (Phase 6.5) */}
          {activeTab === "robustness" && (
            <div className="space-y-6" data-testid="container-robustness">
              {/* Decision ID Search / Trigger Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 p-4 rounded-lg bg-zinc-900/40 border border-zinc-800">
                <div className="flex items-center gap-2">
                  <Activity className="w-5 h-5 text-amber-400" />
                  <div>
                    <div className="text-xs font-bold text-white uppercase font-mono">
                      Phase 6.5 — Decision Robustness & Uncertainty Propagation
                    </div>
                    <div className="text-[10px] text-zinc-400">
                      Bounded intervals, reversal identification, parameter boundary bisection, and VOI prioritization
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={robustnessDecisionId}
                    onChange={(e) => setRobustnessDecisionId(e.target.value)}
                    placeholder="Decision ID (e.g. DEC-12)"
                    className="px-2.5 py-1 text-xs rounded bg-zinc-950 border border-zinc-700 text-white font-mono focus:border-amber-500 focus:outline-none"
                    data-testid="input-robustness-decision-id"
                  />
                  <button
                    onClick={() => handleRunRobustnessPreflight(robustnessDecisionId)}
                    disabled={preflightLoading}
                    className="px-3 py-1 text-xs font-semibold rounded bg-zinc-800 text-zinc-200 border border-zinc-700 hover:bg-zinc-700 transition disabled:opacity-50"
                    data-testid="btn-robustness-preflight"
                  >
                    {preflightLoading ? "Checking..." : "Preflight Check"}
                  </button>
                  <button
                    onClick={() => handleRunRobustnessAnalysis(robustnessDecisionId, false)}
                    disabled={robustnessLoading}
                    className="px-3 py-1 text-xs font-semibold rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500/30 transition disabled:opacity-50"
                    data-testid="btn-run-robustness-analysis"
                  >
                    {robustnessLoading ? "Evaluating Envelope..." : "Analyze Robustness"}
                  </button>
                  <button
                    onClick={() => handleRunRobustnessAnalysis(robustnessDecisionId, true)}
                    disabled={robustnessLoading}
                    className="px-2 py-1 text-xs rounded bg-zinc-800 text-zinc-400 hover:text-white transition disabled:opacity-50"
                    title="Force Reassess & Persist Revision"
                    data-testid="btn-force-reassess-robustness"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {/* Preflight Results */}
              {preflightError && (
                <div className="p-3 rounded bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs">
                  {preflightError}
                </div>
              )}
              {preflightData && (
                <div className="p-4 rounded-lg bg-zinc-900/60 border border-zinc-800 space-y-3" data-testid="container-preflight-results">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-zinc-200 font-mono">
                      PREFLIGHT AUDIT: {preflightData.decision_id}
                    </span>
                    <span className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                      preflightData.is_ready ? "bg-emerald-950/80 border border-emerald-500/40 text-emerald-300" : "bg-rose-950/80 border border-rose-500/40 text-rose-300"
                    }`}>
                      {preflightData.is_ready ? "READY FOR PROPAGATION" : "BLOCKED"}
                    </span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs font-mono">
                    <div className="p-2 rounded bg-zinc-950/60 border border-zinc-800/80">
                      <span className="text-[10px] text-zinc-500 block">Verified Parameters</span>
                      <span className="text-white font-semibold">{preflightData.matched_parameters_count}</span>
                    </div>
                    <div className="p-2 rounded bg-zinc-950/60 border border-zinc-800/80">
                      <span className="text-[10px] text-zinc-500 block">Missing Uncertainty Evidence</span>
                      <span className={preflightData.missing_evidence_parameters.length > 0 ? "text-amber-400 font-semibold" : "text-emerald-400 font-semibold"}>
                        {preflightData.missing_evidence_parameters.length}
                      </span>
                    </div>
                    <div className="p-2 rounded bg-zinc-950/60 border border-zinc-800/80">
                      <span className="text-[10px] text-zinc-500 block">Recomputable Modal KPIs</span>
                      <span className="text-cyan-400 font-semibold">{preflightData.recomputable_kpis?.map((k) => k.kpi).join(", ") || "None"}</span>
                    </div>
                  </div>
                  {preflightData.warnings.length > 0 && (
                    <div className="p-2 rounded bg-amber-950/30 border border-amber-500/30 text-amber-200 text-xs">
                      {preflightData.warnings.map((w, idx) => (
                        <div key={idx} className="flex items-center gap-1.5">
                          <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                          <span>{w}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Analysis Error / Loading */}
              {robustnessError && (
                <div className="p-4 rounded-lg bg-rose-950/40 border border-rose-500/50 text-rose-200 text-xs">
                  {robustnessError}
                </div>
              )}

              {/* Robustness Analysis Results */}
              {robustnessData && (
                <div className="space-y-6" data-testid="container-robustness-results">
                  {/* Governance Notice */}
                  <div
                    className="p-4 rounded-lg bg-amber-950/30 border border-amber-500/50 text-amber-200 text-xs space-y-1.5"
                    data-testid="robustness-governance-notice"
                  >
                    <div className="font-semibold flex items-center gap-2 text-amber-300">
                      <AlertTriangle className="w-4 h-4" />
                      GOVERNANCE & DEPLOYMENT SAFETY SEPARATION
                    </div>
                    <p className="text-zinc-300">
                      {robustnessData.governance_separation_notice}
                    </p>
                    <div className="flex flex-wrap gap-4 pt-1 font-mono text-[11px]">
                      <span>
                        Deployment Safety Inferred:{" "}
                        <strong className="text-rose-400">
                          {String(robustnessData.deployment_safety_inferred)}
                        </strong>
                      </span>
                      <span>
                        Deployment Authorization Gate:{" "}
                        <strong className="text-amber-400">
                          {robustnessData.deployment_authorization}
                        </strong>
                      </span>
                      <span>
                        Policy Version:{" "}
                        <strong className="text-zinc-300">
                          {robustnessData.policy_version}
                        </strong>
                      </span>
                    </div>
                  </div>

                  {/* Summary Metric Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4 p-4 rounded-lg bg-zinc-900/60 border border-zinc-800">
                    <div>
                      <div className="text-[10px] uppercase font-mono tracking-wider text-zinc-400">
                        Robustness Posture
                      </div>
                      <div className="mt-1">
                        {(() => {
                          const badge = getRobustnessBadge(robustnessData.robustness_classification);
                          const Icon = badge.icon;
                          return (
                            <span
                              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-bold border ${badge.bg}`}
                              data-testid="robustness-classification-badge"
                            >
                              <Icon className="w-3.5 h-3.5" />
                              {badge.label}
                            </span>
                          );
                        })()}
                      </div>
                    </div>

                    <div>
                      <div className="text-[10px] uppercase font-mono tracking-wider text-zinc-400">
                        Target KPI & Selection
                      </div>
                      <div className="mt-1 text-sm font-bold text-white font-mono">
                        {robustnessData.target_kpi}
                      </div>
                      <div className="text-[10px] text-zinc-500 font-mono">
                        Selected: {robustnessData.selected_option}
                      </div>
                    </div>

                    <div>
                      <div className="text-[10px] uppercase font-mono tracking-wider text-zinc-400">
                        Scenarios & Reversals
                      </div>
                      <div className="mt-1 text-sm font-bold font-mono">
                        <span className="text-white">{robustnessData.evaluated_scenarios_count} Evaluated</span>
                        <span className="text-zinc-500 mx-1">/</span>
                        <span className={robustnessData.reversals_count > 0 ? "text-rose-400" : "text-emerald-400"}>
                          {robustnessData.reversals_count} Reversals
                        </span>
                      </div>
                      <div className="text-[10px] text-zinc-500 font-mono">
                        Boundaries: {robustnessData.boundary_crossings?.length || 0}
                      </div>
                    </div>

                    <div>
                      <div className="text-[10px] uppercase font-mono tracking-wider text-zinc-400">
                        Cryptographic Provenance
                      </div>
                      <div className="text-[11px] text-zinc-300 font-mono mt-1 truncate" title={robustnessData.analysis_hash}>
                        Analysis: {robustnessData.analysis_hash.slice(0, 14)}...
                      </div>
                      <div className="text-[10px] text-zinc-500 font-mono truncate" title={robustnessData.input_snapshot_hash}>
                        Snapshot: {robustnessData.input_snapshot_hash.slice(0, 14)}...
                      </div>
                    </div>
                  </div>

                  {/* Summary Text */}
                  <div className="p-3 rounded-lg bg-zinc-900/30 border border-zinc-800 text-xs text-zinc-300">
                    <span className="font-semibold text-white">Assessment Summary: </span>
                    {robustnessData.robustness_summary}
                  </div>

                  {/* Solver Failures (Preserved Unmasked) */}
                  {robustnessData.solver_failures && robustnessData.solver_failures.length > 0 && (
                    <div className="p-4 rounded-lg bg-rose-950/30 border border-rose-500/50 text-rose-200 text-xs space-y-2">
                      <div className="font-semibold flex items-center gap-1.5 text-rose-300">
                        <AlertTriangle className="w-4 h-4" />
                        Numerical Solver Failures Preserved ({robustnessData.solver_failures.length})
                      </div>
                      <p className="text-zinc-400 text-[11px]">
                        The following scenarios triggered physical constraint violations or numerical non-convergence and are preserved as explicit failure results rather than masked.
                      </p>
                      <div className="space-y-1 font-mono text-[10px]">
                        {robustnessData.solver_failures.map((sf, idx) => (
                          <div key={idx} className="p-2 rounded bg-zinc-950/60 border border-rose-500/30">
                            Scenario: {sf.scenario_id} | Status: {sf.convergence_status} | Reason: {sf.failure_reason}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Demonstrated Reversal Scenarios Table */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-semibold uppercase font-mono text-zinc-300 flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4 text-rose-400" />
                        Demonstrated Ranking Reversals ({robustnessData.reversal_scenarios?.length || 0})
                      </h3>
                      <span className="text-[10px] font-mono text-zinc-500">
                        Parameter combinations that flip the engineering conclusion
                      </span>
                    </div>

                    {(!robustnessData.reversal_scenarios || robustnessData.reversal_scenarios.length === 0) ? (
                      <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800 text-center text-xs text-zinc-400">
                        Zero ranking reversals demonstrated within the credible parameter uncertainty envelope.
                      </div>
                    ) : (
                      <div className="rounded-lg border border-zinc-800 overflow-hidden bg-zinc-900/30">
                        <table className="w-full text-xs text-left" data-testid="table-reversal-scenarios">
                          <thead className="bg-zinc-900 text-zinc-400 font-mono text-[11px] uppercase border-b border-zinc-800">
                            <tr>
                              <th className="p-3">Scenario</th>
                              <th className="p-3">Reversal Winner</th>
                              <th className="p-3">Decision Margin</th>
                              <th className="p-3">Nature</th>
                              <th className="p-3">Parameter Values</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-zinc-800 font-mono text-xs">
                            {robustnessData.reversal_scenarios.map((rev, idx) => (
                              <tr key={idx} className="hover:bg-zinc-900/50 transition">
                                <td className="p-3 text-amber-400 font-semibold">{rev.scenario_id}</td>
                                <td className="p-3 text-rose-300 font-semibold">
                                  {rev.scenario_winner} <span className="text-[10px] text-zinc-500">(vs {rev.original_selection})</span>
                                </td>
                                <td className="p-3 text-zinc-300">
                                  {rev.decision_margin !== undefined && rev.decision_margin !== null ? rev.decision_margin.toFixed(4) : "—"}
                                </td>
                                <td className="p-3 text-cyan-300">{rev.nature}</td>
                                <td className="p-3 text-zinc-400 text-[10px]">
                                  {rev.parameter_values ? JSON.stringify(rev.parameter_values) : "—"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  {/* Decision Boundary Crossings Table */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-semibold uppercase font-mono text-zinc-300 flex items-center gap-2">
                        <Target className="w-4 h-4 text-cyan-400" />
                        Decision Boundary Crossings ({robustnessData.boundary_crossings?.length || 0})
                      </h3>
                      <span className="text-[10px] font-mono text-zinc-500">
                        Bisection analysis of parameter shifts required to flip decision
                      </span>
                    </div>

                    {(!robustnessData.boundary_crossings || robustnessData.boundary_crossings.length === 0) ? (
                      <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800 text-center text-xs text-zinc-400">
                        No continuous single-parameter boundary crossings identified within the evaluated bounds.
                      </div>
                    ) : (
                      <div className="rounded-lg border border-zinc-800 overflow-hidden bg-zinc-900/30">
                        <table className="w-full text-xs text-left" data-testid="table-decision-boundaries">
                          <thead className="bg-zinc-900 text-zinc-400 font-mono text-[11px] uppercase border-b border-zinc-800">
                            <tr>
                              <th className="p-3">Type</th>
                              <th className="p-3">Parameter</th>
                              <th className="p-3">Nominal Value</th>
                              <th className="p-3">Boundary Value</th>
                              <th className="p-3">Shift %</th>
                              <th className="p-3">Description</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-zinc-800 font-mono text-xs">
                            {robustnessData.boundary_crossings.map((bc, idx) => (
                              <tr key={idx} className="hover:bg-zinc-900/50 transition">
                                <td className="p-3">
                                  <span className={`px-2 py-0.5 text-[9px] font-bold rounded ${
                                    bc.crossing_type === "BISECTION_APPROXIMATED" ? "bg-cyan-950/70 border border-cyan-500/40 text-cyan-300" : "bg-zinc-800 text-zinc-300"
                                  }`}>
                                    {bc.crossing_type}
                                  </span>
                                </td>
                                <td className="p-3 text-white font-semibold">
                                  {bc.critical_parameter || bc.critical_parameters?.join(", ") || "—"}
                                </td>
                                <td className="p-3 text-zinc-400">{bc.nominal_value ?? "—"}</td>
                                <td className="p-3 text-amber-300 font-semibold">{bc.boundary_value !== undefined ? bc.boundary_value.toFixed(2) : "—"}</td>
                                <td className="p-3 text-rose-300 font-semibold">
                                  {bc.parameter_shift_pct !== undefined ? `${bc.parameter_shift_pct.toFixed(1)}%` : "—"}
                                </td>
                                <td className="p-3 text-zinc-400 text-[11px] font-sans">{bc.description}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  {/* Dominant Uncertainties Ranking Table */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-semibold uppercase font-mono text-zinc-300 flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-amber-400" />
                        Dominant Decision Uncertainties ({robustnessData.dominant_uncertainties?.length || 0})
                      </h3>
                      <span className="text-[10px] font-mono text-zinc-500">
                        Ranked by elasticity × uncertainty span & reversal participation
                      </span>
                    </div>

                    {(!robustnessData.dominant_uncertainties || robustnessData.dominant_uncertainties.length === 0) ? (
                      <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800 text-center text-xs text-zinc-400">
                        Zero dominant uncertainties identified.
                      </div>
                    ) : (
                      <div className="rounded-lg border border-zinc-800 overflow-hidden bg-zinc-900/30">
                        <table className="w-full text-xs text-left" data-testid="table-dominant-uncertainties">
                          <thead className="bg-zinc-900 text-zinc-400 font-mono text-[11px] uppercase border-b border-zinc-800">
                            <tr>
                              <th className="p-3">Rank</th>
                              <th className="p-3">Parameter</th>
                              <th className="p-3">Impact Score</th>
                              <th className="p-3">Sensitivity Elasticity</th>
                              <th className="p-3">Uncertainty Span %</th>
                              <th className="p-3">Reversals Driven</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-zinc-800 font-mono text-xs">
                            {robustnessData.dominant_uncertainties.map((du, idx) => (
                              <tr key={idx} className="hover:bg-zinc-900/50 transition">
                                <td className="p-3 text-zinc-500 font-bold">#{idx + 1}</td>
                                <td className="p-3 text-white font-semibold">{du.parameter_name}</td>
                                <td className="p-3 text-amber-400 font-bold">{du.impact_score !== undefined ? du.impact_score.toFixed(4) : "—"}</td>
                                <td className="p-3 text-zinc-300">{du.elasticity !== undefined ? du.elasticity.toFixed(3) : "—"}</td>
                                <td className="p-3 text-cyan-300">{du.relative_uncertainty_span_pct !== undefined ? du.relative_uncertainty_span_pct.toFixed(1) : "—"}%</td>
                                <td className="p-3 text-rose-300 font-semibold">{du.reversals_participated}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  {/* Value of Information (VOI) Prioritizations */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-semibold uppercase font-mono text-zinc-300 flex items-center gap-2">
                        <FlaskConical className="w-4 h-4 text-emerald-400" />
                        Value of Information (VOI) Prioritizations ({robustnessData.voi_prioritizations?.length || 0})
                      </h3>
                      <span className="text-[10px] font-mono text-zinc-500">
                        Concrete experiments mapped to uncertainty reduction (No fabricated dollar EVOI)
                      </span>
                    </div>

                    {(!robustnessData.voi_prioritizations || robustnessData.voi_prioritizations.length === 0) ? (
                      <div className="p-4 rounded-lg bg-zinc-900/40 border border-zinc-800 text-center text-xs text-zinc-400">
                        Zero VOI recommendations required.
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="table-voi-prioritizations">
                        {robustnessData.voi_prioritizations.map((voi, idx) => (
                          <div
                            key={idx}
                            className={`p-4 rounded-lg border space-y-2.5 ${
                              voi.priority_level === "HIGH"
                                ? "bg-rose-950/20 border-rose-500/40"
                                : voi.priority_level === "MEDIUM"
                                ? "bg-amber-950/20 border-amber-500/40"
                                : "bg-blue-950/20 border-blue-500/40"
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold text-white font-mono">{voi.parameter_name}</span>
                              <span
                                className={`px-2 py-0.5 text-[9px] font-bold rounded uppercase ${
                                  voi.priority_level === "HIGH"
                                    ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                                    : voi.priority_level === "MEDIUM"
                                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                                    : "bg-blue-500/20 text-blue-300 border border-blue-500/40"
                                }`}
                              >
                                {voi.priority_level} PRIORITY ({voi.urgency})
                              </span>
                            </div>

                            <div className="p-2.5 rounded bg-zinc-950/60 border border-zinc-800 text-xs space-y-1 font-mono">
                              <div className="text-[10px] text-amber-400 uppercase font-semibold">Recommended Physical Experiment</div>
                              <div className="text-white">{voi.recommended_experiment}</div>
                              <div className="text-[11px] text-zinc-400 mt-1 flex justify-between">
                                <span>Elasticity: {voi.elasticity}</span>
                                <span>Trust: {voi.current_trust_state}</span>
                              </div>
                            </div>

                            <p className="text-xs text-zinc-300 font-sans">{voi.justification}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Historical Robustness Runs */}
                  {robustnessHistoryItems.length > 0 && (
                    <div className="space-y-3 pt-4 border-t border-zinc-800" data-testid="robustness-history">
                      <div className="flex items-center justify-between">
                        <h3 className="text-xs font-semibold uppercase font-mono text-zinc-300 flex items-center gap-2">
                          <History className="w-4 h-4 text-amber-400" />
                          Robustness Analysis Lineage ({robustnessHistoryItems.length})
                        </h3>
                        <span className="text-[10px] font-mono text-zinc-500">Append-only audit trail</span>
                      </div>

                      <div className="space-y-2">
                        {robustnessHistoryItems.map((hist, idx) => (
                          <div
                            key={idx}
                            className={`p-3 rounded-lg border text-xs font-mono flex flex-col md:flex-row md:items-center justify-between gap-2 ${
                              hist.is_active
                                ? "bg-zinc-900/80 border-amber-500/40 text-white"
                                : "bg-zinc-950/40 border-zinc-800 text-zinc-400"
                            }`}
                          >
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-bold">{hist.robustness_classification}</span>
                                {hist.is_active ? (
                                  <span className="px-1.5 py-0.2 rounded text-[9px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                                    ACTIVE
                                  </span>
                                ) : (
                                  <span className="px-1.5 py-0.2 rounded text-[9px] bg-zinc-800 text-zinc-500">
                                    SUPERSEDED
                                  </span>
                                )}
                              </div>
                              <div className="text-[11px] text-zinc-400 mt-0.5">{hist.robustness_summary}</div>
                            </div>
                            <div className="text-right text-[10px] text-zinc-500">
                              <div>Hash: {hist.analysis_hash ? `${hist.analysis_hash.slice(0, 16)}...` : ""}</div>
                              <div>{hist.created_at ? new Date(hist.created_at).toLocaleString() : ""}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Tab 9: Validation Planning, Evidence Closure & Decision Reassessment (Phase 6.6) */}
          {activeTab === "validation" && (
            <div className="space-y-6" data-testid="container-validation-planning">
              {/* Governance & Validation Separation Banner */}
              <div
                className="p-4 rounded-lg bg-zinc-900/80 border border-amber-500/40 text-xs space-y-2"
                data-testid="governance-separation-banner"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 font-bold text-amber-400 uppercase font-mono tracking-wider">
                    <Scale className="w-4 h-4 text-amber-400" />
                    Governance & Validation Separation Notice
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className="px-2 py-0.5 rounded text-[10px] font-mono bg-zinc-800 text-zinc-300 border border-zinc-700"
                      data-testid="badge-safety-inferred"
                    >
                      deployment_safety_inferred = false
                    </span>
                    <span
                      className="px-2 py-0.5 rounded text-[10px] font-mono bg-rose-950/70 text-rose-300 border border-rose-500/40"
                      data-testid="badge-deployment-auth"
                    >
                      Deployment: NOT_ESTABLISHED
                    </span>
                  </div>
                </div>
                <p className="text-zinc-300 font-sans leading-relaxed">
                  Strict Separation Invariant: Plan approval != Activity permission != Evidence acceptance !=
                  Decision approval != Deployment safety. Satisfying validation acceptance criteria or closing an
                  evidence gap establishes epistemic bounding, not operational safety authorization.
                </p>
              </div>

              {/* Decision Query & Plan Creation Bar */}
              <div className="flex flex-col md:flex-row md:items-center justify-between p-4 rounded-lg bg-zinc-900/50 border border-zinc-800 gap-3">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono uppercase text-zinc-400">Decision ID:</span>
                  <input
                    type="text"
                    value={validationDecisionId}
                    onChange={(e) => setValidationDecisionId(e.target.value)}
                    className="px-3 py-1.5 text-xs bg-zinc-950 border border-zinc-700 rounded text-white font-mono w-44"
                    placeholder="e.g. DEC-12"
                    data-testid="input-validation-decision-id"
                  />
                  <button
                    onClick={() => fetchValidationPlans(validationDecisionId)}
                    disabled={validationLoading}
                    className="px-3 py-1.5 text-xs font-semibold rounded bg-amber-500 hover:bg-amber-400 text-black transition flex items-center gap-1.5 disabled:opacity-50"
                    data-testid="btn-fetch-plans"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${validationLoading ? "animate-spin" : ""}`} />
                    Load Plans
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowNewPlanModal(true)}
                    className="px-3 py-1.5 text-xs font-semibold rounded bg-zinc-800 hover:bg-zinc-700 text-white border border-zinc-700 transition flex items-center gap-1.5"
                    data-testid="btn-open-new-plan-modal"
                  >
                    <ClipboardList className="w-3.5 h-3.5 text-amber-400" />
                    New Validation Plan
                  </button>
                </div>
              </div>

              {/* Error Alert */}
              {validationError && (
                <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-500/50 text-rose-200 text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
                  <span>{validationError}</span>
                </div>
              )}

              {/* Plan Selection Tabs */}
              {validationPlans.length > 0 && (
                <div className="flex items-center gap-2 overflow-x-auto pb-1">
                  {validationPlans.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => setSelectedPlan(p)}
                      className={`px-3 py-1.5 text-xs font-mono rounded border transition flex items-center gap-2 ${
                        selectedPlan?.id === p.id
                          ? "bg-amber-500/10 border-amber-500 text-amber-300"
                          : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                      }`}
                      data-testid={`btn-select-plan-${p.plan_id}`}
                    >
                      <span className="font-bold">{p.plan_id}</span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                        {p.status}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {/* Active Plan Detail Card */}
              {selectedPlan ? (
                <div className="space-y-6" data-testid="card-validation-plan">
                  {/* Plan Header & Lifecycle State */}
                  <div className="p-5 rounded-lg bg-zinc-900/60 border border-zinc-800 space-y-4">
                    <div className="flex flex-col md:flex-row md:items-center justify-between pb-3 border-b border-zinc-800 gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold font-mono text-white" data-testid="plan-code">
                            {selectedPlan.plan_id}
                          </span>
                          <span className="text-xs px-2 py-0.5 rounded font-mono font-bold bg-amber-500/20 text-amber-400 border border-amber-500/40">
                            v{selectedPlan.plan_version}
                          </span>
                          <span
                            className="text-xs px-2.5 py-0.5 rounded font-mono font-bold bg-zinc-800 text-zinc-200 border border-zinc-700"
                            data-testid="plan-status-badge"
                          >
                            {selectedPlan.status}
                          </span>
                        </div>
                        <p className="text-xs text-zinc-400 mt-1">{selectedPlan.validation_objective}</p>
                      </div>

                      {/* Lifecycle Transition Controls */}
                      <div className="flex items-center gap-2 flex-wrap" data-testid="plan-lifecycle-controls">
                        {selectedPlan.status === "DRAFT" && (
                          <button
                            onClick={() => handleTransitionPlan(selectedPlan.id, "PROPOSED")}
                            disabled={validationLoading}
                            className="px-2.5 py-1 text-xs font-semibold rounded bg-zinc-800 hover:bg-zinc-700 text-white border border-zinc-700 transition"
                            data-testid="btn-transition-propose"
                          >
                            Propose Plan
                          </button>
                        )}
                        {selectedPlan.status === "PROPOSED" && (
                          <>
                            <button
                              onClick={() => handleTransitionPlan(selectedPlan.id, "AUTHORIZED")}
                              disabled={validationLoading}
                              className="px-2.5 py-1 text-xs font-semibold rounded bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-1"
                              data-testid="btn-transition-authorize"
                            >
                              <Lock className="w-3 h-3" />
                              Authorize Plan (Lead)
                            </button>
                            <button
                              onClick={() => handleTransitionPlan(selectedPlan.id, "REJECTED")}
                              disabled={validationLoading}
                              className="px-2.5 py-1 text-xs font-semibold rounded bg-rose-900/60 hover:bg-rose-800 text-rose-200 border border-rose-700 transition"
                              data-testid="btn-transition-reject"
                            >
                              Reject Plan
                            </button>
                          </>
                        )}
                        {selectedPlan.status === "AUTHORIZED" && (
                          <button
                            onClick={() => handleTransitionPlan(selectedPlan.id, "IN_PROGRESS")}
                            disabled={validationLoading}
                            className="px-2.5 py-1 text-xs font-semibold rounded bg-amber-600 hover:bg-amber-500 text-black font-bold transition"
                            data-testid="btn-transition-inprogress"
                          >
                            Start Validation
                          </button>
                        )}
                        {selectedPlan.status === "IN_PROGRESS" && (
                          <button
                            onClick={() => setShowSubmitEvidenceModal(true)}
                            className="px-2.5 py-1 text-xs font-semibold rounded bg-blue-600 hover:bg-blue-500 text-white transition flex items-center gap-1"
                            data-testid="btn-open-submit-evidence"
                          >
                            <FlaskConical className="w-3 h-3" />
                            Submit Evidence
                          </button>
                        )}
                        {selectedPlan.status === "EVIDENCE_SUBMITTED" && (
                          <button
                            onClick={() => handleTransitionPlan(selectedPlan.id, "UNDER_REVIEW")}
                            disabled={validationLoading}
                            className="px-2.5 py-1 text-xs font-semibold rounded bg-indigo-600 hover:bg-indigo-500 text-white transition"
                            data-testid="btn-transition-under-review"
                          >
                            Submit for Review
                          </button>
                        )}
                        {selectedPlan.status === "UNDER_REVIEW" && (
                          <>
                            <button
                              onClick={() => handleTransitionPlan(selectedPlan.id, "ACCEPTED")}
                              disabled={validationLoading}
                              className="px-2.5 py-1 text-xs font-semibold rounded bg-emerald-600 hover:bg-emerald-500 text-white transition"
                              data-testid="btn-transition-accept"
                            >
                              Accept Plan (Lead)
                            </button>
                            <button
                              onClick={() => handleTransitionPlan(selectedPlan.id, "INCONCLUSIVE")}
                              disabled={validationLoading}
                              className="px-2.5 py-1 text-xs font-semibold rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition"
                              data-testid="btn-transition-inconclusive"
                            >
                              Inconclusive
                            </button>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Metadata Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono">
                      <div>
                        <span className="text-zinc-500 block text-[10px] uppercase">Target Parameter</span>
                        <span className="text-white font-bold" data-testid="plan-target-param">{selectedPlan.parameter_name}</span>
                      </div>
                      <div>
                        <span className="text-zinc-500 block text-[10px] uppercase">Method</span>
                        <span className="text-zinc-200">{selectedPlan.validation_method}</span>
                      </div>
                      <div>
                        <span className="text-zinc-500 block text-[10px] uppercase">Canonical Unit</span>
                        <span className="text-amber-400 font-bold">{selectedPlan.unit || "—"}</span>
                      </div>
                      <div>
                        <span className="text-zinc-500 block text-[10px] uppercase">Plan Hash</span>
                        <span className="text-zinc-400 truncate block" title={selectedPlan.plan_hash || ""}>
                          {selectedPlan.plan_hash ? `${selectedPlan.plan_hash.slice(0, 16)}...` : "—"}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Acceptance Criteria Table with Immutability Notice */}
                  <div className="p-5 rounded-lg bg-zinc-900/40 border border-zinc-800 space-y-3" data-testid="section-acceptance-criteria">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <CheckSquare className="w-4 h-4 text-amber-400" />
                        <h3 className="text-xs font-semibold uppercase font-mono text-zinc-200">
                          Authorized Acceptance Criteria
                        </h3>
                        {selectedPlan.status !== "DRAFT" && selectedPlan.status !== "PROPOSED" && (
                          <span
                            className="px-2 py-0.5 rounded text-[10px] font-mono bg-zinc-800 text-emerald-400 border border-emerald-500/40 flex items-center gap-1"
                            data-testid="badge-criteria-sealed"
                          >
                            <Lock className="w-3 h-3 text-emerald-400" />
                            CRITERIA SEALED UPON AUTHORIZATION
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] font-mono text-zinc-500">
                        {selectedPlan.acceptance_criteria ? selectedPlan.acceptance_criteria.length : 0} criteria defined
                      </span>
                    </div>

                    <div className="overflow-x-auto">
                      <table className="w-full text-xs text-left font-mono border border-zinc-800 rounded">
                        <thead className="bg-zinc-950 text-zinc-400 text-[10px] uppercase">
                          <tr>
                            <th className="p-2.5">Metric</th>
                            <th className="p-2.5">Target Value</th>
                            <th className="p-2.5">Tolerance Band</th>
                            <th className="p-2.5">Unit</th>
                            <th className="p-2.5">Status</th>
                            <th className="p-2.5">Provenance</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-800">
                          {selectedPlan.acceptance_criteria && selectedPlan.acceptance_criteria.length > 0 ? (
                            selectedPlan.acceptance_criteria.map((c: any, idx: number) => (
                              <tr key={idx} className="hover:bg-zinc-800/30">
                                <td className="p-2.5 text-white font-semibold">{c.metric_name}</td>
                                <td className="p-2.5 text-zinc-300">{c.target_value ?? "—"}</td>
                                <td className="p-2.5 text-zinc-300">
                                  {c.tolerance_band ? `[${c.tolerance_band[0]}, ${c.tolerance_band[1]}]` : "—"}
                                </td>
                                <td className="p-2.5 text-amber-400">{c.unit}</td>
                                <td className="p-2.5">
                                  <span
                                    className={`px-1.5 py-0.5 rounded text-[10px] ${
                                      c.status === "AUTHORIZED" || c.status === "ESTABLISHED"
                                        ? "bg-emerald-950/60 text-emerald-400 border border-emerald-500/30"
                                        : "bg-amber-950/60 text-amber-400 border border-amber-500/30"
                                    }`}
                                  >
                                    {c.status}
                                  </span>
                                </td>
                                <td className="p-2.5 text-zinc-500 truncate max-w-xs">{c.provenance || c.rationale || "—"}</td>
                              </tr>
                            ))
                          ) : (
                            <tr>
                              <td colSpan={6} className="p-3 text-center text-zinc-500 font-sans">
                                No acceptance criteria recorded.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Evidence Ingestion & Review Card */}
                  <div className="p-5 rounded-lg bg-zinc-900/40 border border-zinc-800 space-y-4" data-testid="card-evidence-review">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <FlaskConical className="w-4 h-4 text-blue-400" />
                        <h3 className="text-xs font-semibold uppercase font-mono text-zinc-200">
                          Validation Evidence & Provenance
                        </h3>
                      </div>
                      <button
                        onClick={() => setShowSubmitEvidenceModal(true)}
                        className="px-2.5 py-1 text-xs font-semibold rounded bg-blue-600/80 hover:bg-blue-600 text-white transition flex items-center gap-1"
                        data-testid="btn-add-evidence-inline"
                      >
                        + Ingest Evidence
                      </button>
                    </div>

                    {/* Masquerade Protection Notice */}
                    <div className="p-2.5 rounded bg-zinc-950 border border-blue-900/30 text-[11px] text-zinc-400 flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4 text-blue-400 shrink-0" />
                      <span>
                        Anti-Masquerading Guardrail: CAE and numerical simulation data cannot be falsely flagged as
                        physically validated. Missing provenance fails closed.
                      </span>
                    </div>

                    {/* Evidence List */}
                    {selectedPlan.evidence_items && selectedPlan.evidence_items.length > 0 ? (
                      <div className="space-y-3" data-testid="list-evidence-items">
                        {selectedPlan.evidence_items.map((ev: any) => (
                          <div
                            key={ev.id}
                            className="p-3.5 rounded-lg bg-zinc-950/70 border border-zinc-800 text-xs font-mono space-y-2"
                            data-testid={`evidence-item-${ev.id}`}
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-white">{ev.source_identifier}</span>
                                <span className="px-1.5 py-0.2 rounded text-[10px] bg-zinc-800 text-zinc-300">
                                  {ev.evidence_source_type}
                                </span>
                                {ev.is_physically_validated ? (
                                  <span className="px-1.5 py-0.2 rounded text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-500/40 font-bold">
                                    PHYSICAL
                                  </span>
                                ) : (
                                  <span className="px-1.5 py-0.2 rounded text-[10px] bg-zinc-800 text-zinc-400">
                                    SYNTHETIC / CAE
                                  </span>
                                )}
                              </div>
                              <div className="flex items-center gap-2">
                                <span
                                  className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${
                                    ev.integrity_stage === "SOURCE_IDENTITY_VERIFIED" || ev.integrity_stage === "EVIDENCE_ACCEPTED"
                                      ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                                      : "bg-amber-950 text-amber-300 border border-amber-500/40"
                                  }`}
                                  data-testid={`badge-integrity-stage-${ev.id}`}
                                >
                                  {ev.integrity_stage || "SOURCE_CLAIMED"}
                                </span>
                                <span
                                  className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${
                                    ev.source_verification_status === "VERIFIED"
                                      ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                                      : ev.source_verification_status === "REJECTED" || ev.source_verification_status === "REVOKED"
                                      ? "bg-rose-950 text-rose-300 border border-rose-500/40"
                                      : "bg-zinc-800 text-zinc-400 border border-zinc-700"
                                  }`}
                                  data-testid={`badge-source-status-${ev.id}`}
                                >
                                  {ev.source_verification_status || "UNVERIFIED"}
                                </span>
                                <span
                                  className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                    ev.review_status === "ACCEPTED"
                                      ? "bg-emerald-950 text-emerald-300 border border-emerald-500/40"
                                      : ev.review_status === "REJECTED"
                                      ? "bg-rose-950 text-rose-300 border border-rose-500/40"
                                      : "bg-amber-950 text-amber-300 border border-amber-500/40"
                                  }`}
                                  data-testid={`badge-review-status-${ev.id}`}
                                >
                                  {ev.review_status}
                                </span>
                                {ev.source_verification_status === "VERIFIED" ? (
                                  <button
                                    onClick={() => handleRevokeEvidenceSource(ev.id)}
                                    disabled={validationLoading}
                                    className="px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-700 hover:bg-rose-900 text-[10px]"
                                    data-testid={`btn-revoke-source-${ev.id}`}
                                  >
                                    Revoke
                                  </button>
                                ) : (
                                  <button
                                    onClick={() => {
                                      setVerifyingEvidenceId(ev.id);
                                      setShowVerifySourceModal(true);
                                    }}
                                    disabled={validationLoading}
                                    className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-600 hover:bg-emerald-900 text-[10px]"
                                    data-testid={`btn-open-verify-source-${ev.id}`}
                                  >
                                    Verify Source
                                  </button>
                                )}
                              </div>
                            </div>

                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px] text-zinc-400 pt-1 border-t border-zinc-900">
                              <div>
                                Observed: <span className="text-white font-bold">{ev.observed_value ?? "—"}</span> {ev.unit}
                              </div>
                              <div>
                                Interval: <span className="text-zinc-300">{ev.observed_interval ? `[${ev.observed_interval[0]}, ${ev.observed_interval[1]}]` : "—"}</span>
                              </div>
                              <div className="truncate" title={ev.integrity_hash || ""}>
                                Hash: <span className="text-zinc-500">{ev.integrity_hash ? `${ev.integrity_hash.slice(0, 10)}...` : "—"}</span>
                              </div>
                              <div className="text-right">
                                {ev.review_status === "PENDING_REVIEW" && (
                                  <div className="flex items-center justify-end gap-1.5">
                                    <button
                                      onClick={() => handleReviewEvidence(selectedPlan.id, ev.id, "ACCEPTED")}
                                      className="px-2 py-0.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white text-[10px]"
                                      data-testid={`btn-evidence-accept-${ev.id}`}
                                    >
                                      Accept
                                    </button>
                                    <button
                                      onClick={() => handleReviewEvidence(selectedPlan.id, ev.id, "REJECTED")}
                                      className="px-2 py-0.5 rounded bg-rose-800 hover:bg-rose-700 text-white text-[10px]"
                                      data-testid={`btn-evidence-reject-${ev.id}`}
                                    >
                                      Reject
                                    </button>
                                  </div>
                                )}
                              </div>
                            </div>

                            {ev.physical_limitations && (
                              <div className="text-[10px] text-zinc-500 font-sans">
                                Limitation: {ev.physical_limitations}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-zinc-500 font-sans">
                        No validation evidence items recorded yet. Ingest empirical telemetry or dyno runs above.
                      </p>
                    )}
                  </div>

                  {/* Gap Closure Assessment Card */}
                  <div className="p-5 rounded-lg bg-zinc-900/40 border border-zinc-800 space-y-4" data-testid="card-gap-closure">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        <h3 className="text-xs font-semibold uppercase font-mono text-zinc-200">
                          Evidence Gap Closure Assessment
                        </h3>
                      </div>
                      <button
                        onClick={() => handleEvaluateClosure(selectedPlan.id)}
                        disabled={closureLoading}
                        className="px-3 py-1 text-xs font-semibold rounded bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-1.5 disabled:opacity-50"
                        data-testid="btn-evaluate-closure"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${closureLoading ? "animate-spin" : ""}`} />
                        Evaluate Gap Closure
                      </button>
                    </div>

                    {/* Verdict Banner */}
                    {closureAssessment && (
                      <div className="space-y-3">
                        <div
                          className={`p-4 rounded-lg border text-xs font-mono space-y-2 ${
                            closureAssessment.closure_verdict.startsWith("CLOSED")
                              ? "bg-emerald-950/60 border-emerald-500/50 text-emerald-200"
                              : "bg-amber-950/60 border-amber-500/50 text-amber-200"
                          }`}
                          data-testid="banner-closure-verdict"
                        >
                          <div className="flex items-center justify-between font-bold">
                            <span className="text-sm tracking-wide" data-testid="text-closure-verdict">
                              VERDICT: {closureAssessment.closure_verdict}
                            </span>
                            <span className="text-[10px] text-zinc-400">
                              Criteria Met: {closureAssessment.criteria_met ? "YES" : "NO"}
                            </span>
                          </div>
                          <p className="text-xs text-zinc-300 font-sans">{closureAssessment.closure_summary}</p>
                          <div className="text-[10px] text-zinc-400 pt-1 border-t border-zinc-800">
                            Closure Hash: {closureAssessment.closure_hash}
                          </div>
                        </div>

                        {/* Finite Sample Scope Notice */}
                        <div
                          className="p-3 rounded bg-zinc-950 border border-zinc-800 text-[11px] text-zinc-400 space-y-1 font-sans"
                          data-testid="box-finite-sample-notice"
                        >
                          <div className="font-bold font-mono text-amber-400 text-xs">
                            FINITE SAMPLE SCOPE LIMITATION
                          </div>
                          <p>{closureAssessment.finite_sample_notice || "Empirical test runs narrow localized tolerance intervals without certifying the full infinite operational envelope."}</p>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Decision Robustness Reassessment & Delta Card */}
                  <div className="p-5 rounded-lg bg-zinc-900/40 border border-zinc-800 space-y-4" data-testid="card-decision-reassessment">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-amber-400" />
                        <h3 className="text-xs font-semibold uppercase font-mono text-zinc-200">
                          Decision Robustness Reassessment & Delta
                        </h3>
                      </div>
                      <button
                        onClick={() => handleExecuteReassessment(selectedPlan.id)}
                        disabled={reassessmentLoading}
                        className="px-3 py-1.5 text-xs font-semibold rounded bg-amber-500 hover:bg-amber-400 text-black font-bold transition flex items-center gap-1.5 disabled:opacity-50"
                        data-testid="btn-execute-reassessment"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${reassessmentLoading ? "animate-spin" : ""}`} />
                        Execute Reassessment
                      </button>
                    </div>

                    {reassessmentResult && (
                      <div className="space-y-4">
                        {/* Reversal Resolution Status Badge */}
                        <div className="flex items-center justify-between p-3 rounded-lg bg-zinc-950 border border-zinc-800">
                          <span className="text-xs font-mono uppercase text-zinc-400">Reversal Resolution Status:</span>
                          <span
                            className={`px-2.5 py-1 rounded text-xs font-mono font-bold border ${
                              reassessmentResult.reversal_status === "REVERSAL_RESOLVED"
                                ? "bg-emerald-950 border-emerald-500 text-emerald-300"
                                : reassessmentResult.reversal_status === "REVERSAL_PERSISTS"
                                ? "bg-rose-950 border-rose-500 text-rose-300"
                                : "bg-zinc-800 border-zinc-700 text-zinc-300"
                            }`}
                            data-testid="badge-reversal-resolution"
                          >
                            {reassessmentResult.reversal_status}
                          </span>
                        </div>

                        {/* Delta Comparison Grid */}
                        {reassessmentResult.reassessment_delta && (
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono text-xs" data-testid="grid-reassessment-delta">
                            <div className="p-3 rounded bg-zinc-950 border border-zinc-800">
                              <span className="text-[10px] text-zinc-500 block uppercase">Classification Before</span>
                              <span className="text-zinc-400 font-bold">
                                {reassessmentResult.reassessment_delta.classification_before}
                              </span>
                            </div>
                            <div className="p-3 rounded bg-zinc-950 border border-amber-500/40">
                              <span className="text-[10px] text-amber-400 block uppercase font-bold">Classification After</span>
                              <span className="text-emerald-400 font-bold">
                                {reassessmentResult.reassessment_delta.classification_after}
                              </span>
                            </div>
                            <div className="p-3 rounded bg-zinc-950 border border-zinc-800">
                              <span className="text-[10px] text-zinc-500 block uppercase">Reversals Before / After</span>
                              <span className="text-white">
                                {reassessmentResult.reassessment_delta.reversals_before_count} →{" "}
                                <span className="font-bold text-emerald-400">
                                  {reassessmentResult.reassessment_delta.reversals_after_count}
                                </span>
                              </span>
                            </div>
                            <div className="p-3 rounded bg-zinc-950 border border-zinc-800">
                              <span className="text-[10px] text-zinc-500 block uppercase">Boundaries Before / After</span>
                              <span className="text-white">
                                {reassessmentResult.reassessment_delta.boundaries_before_count} →{" "}
                                <span className="font-bold text-emerald-400">
                                  {reassessmentResult.reassessment_delta.boundaries_after_count}
                                </span>
                              </span>
                            </div>
                          </div>
                        )}

                        {/* Coverage Statement */}
                        <div className="p-3 rounded bg-zinc-950/70 border border-zinc-800 text-xs text-zinc-300 font-sans">
                          {reassessmentResult.envelope_coverage_statement}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Historical Decision Reassessments Audit Trail */}
                  {historicalReassessments.length > 0 && (
                    <div className="space-y-3 pt-4 border-t border-zinc-800" data-testid="list-reassessment-history">
                      <div className="flex items-center justify-between">
                        <h4 className="text-xs font-semibold uppercase font-mono text-zinc-300 flex items-center gap-2">
                          <History className="w-4 h-4 text-amber-400" />
                          Reassessment Audit History ({historicalReassessments.length})
                        </h4>
                        <span className="text-[10px] font-mono text-zinc-500">Immutable ledger</span>
                      </div>

                      <div className="space-y-2">
                        {historicalReassessments.map((r, idx) => (
                          <div
                            key={idx}
                            className={`p-3 rounded-lg border text-xs font-mono flex flex-col md:flex-row md:items-center justify-between gap-2 ${
                              r.is_active
                                ? "bg-zinc-900/80 border-amber-500/40 text-white"
                                : "bg-zinc-950/40 border-zinc-800 text-zinc-400"
                            }`}
                          >
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-bold">{r.reversal_status}</span>
                                {r.is_active ? (
                                  <span className="px-1.5 py-0.2 rounded text-[9px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                                    ACTIVE
                                  </span>
                                ) : (
                                  <span className="px-1.5 py-0.2 rounded text-[9px] bg-zinc-800 text-zinc-500">
                                    SUPERSEDED
                                  </span>
                                )}
                              </div>
                              <div className="text-[11px] text-zinc-400 mt-0.5">{r.envelope_coverage_statement}</div>
                            </div>
                            <div className="text-right text-[10px] text-zinc-500">
                              <div>Hash: {r.reassessment_hash ? `${r.reassessment_hash.slice(0, 16)}...` : ""}</div>
                              <div>{r.created_at ? new Date(r.created_at).toLocaleString() : ""}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="p-8 text-center rounded-lg bg-zinc-900/20 border border-zinc-800 text-zinc-500 text-xs">
                  No validation plan selected. Click &quot;New Validation Plan&quot; or select an existing plan above.
                </div>
              )}

              {/* Modal: New Validation Plan */}
              {showNewPlanModal && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                  <div
                    className="w-full max-w-lg rounded-xl border border-zinc-700 bg-zinc-900 text-zinc-100 p-6 shadow-2xl space-y-4"
                    data-testid="modal-new-plan"
                  >
                    <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
                      <h3 className="text-sm font-bold text-white flex items-center gap-2">
                        <ClipboardList className="w-4 h-4 text-amber-400" />
                        Create Engineering Validation Plan
                      </h3>
                      <button
                        onClick={() => setShowNewPlanModal(false)}
                        className="text-zinc-500 hover:text-zinc-300 text-sm"
                      >
                        ✕
                      </button>
                    </div>

                    <div className="space-y-3 text-xs">
                      <div>
                        <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">
                          Target Parameter
                        </label>
                        <input
                          type="text"
                          value={newPlanParam}
                          onChange={(e) => setNewPlanParam(e.target.value)}
                          className="w-full px-3 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-mono"
                          data-testid="input-new-plan-param"
                        />
                      </div>

                      <div>
                        <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">
                          Validation Method
                        </label>
                        <select
                          value={newPlanMethod}
                          onChange={(e) => setNewPlanMethod(e.target.value)}
                          className="w-full px-3 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-mono"
                          data-testid="select-new-plan-method"
                        >
                          <option value="RIG_TEST_4_POST">RIG_TEST_4_POST (4-Post Rig)</option>
                          <option value="DAMPER_DYNO_FORCE_VELOCITY">DAMPER_DYNO_FORCE_VELOCITY (Damper Dyno)</option>
                          <option value="PHYSICAL_TEST_TRACK">PHYSICAL_TEST_TRACK (Proving Ground)</option>
                          <option value="LAB_COMPONENT_DYNOMETER">LAB_COMPONENT_DYNOMETER (Component Dyno)</option>
                          <option value="KINEMATICS_COMPLIANCE_RIG">KINEMATICS_COMPLIANCE_RIG (K&C Rig)</option>
                        </select>
                      </div>

                      <div>
                        <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">
                          Validation Objective
                        </label>
                        <textarea
                          rows={2}
                          value={newPlanObjective}
                          onChange={(e) => setNewPlanObjective(e.target.value)}
                          className="w-full px-3 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-sans"
                          data-testid="input-new-plan-objective"
                        />
                      </div>

                      <div className="grid grid-cols-3 gap-2">
                        <div>
                          <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">Target</label>
                          <input
                            type="number"
                            value={newPlanTargetValue}
                            onChange={(e) => setNewPlanTargetValue(Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-mono"
                            data-testid="input-new-plan-target"
                          />
                        </div>
                        <div>
                          <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">Tol Min</label>
                          <input
                            type="number"
                            value={newPlanToleranceLow}
                            onChange={(e) => setNewPlanToleranceLow(Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-mono"
                            data-testid="input-new-plan-tol-min"
                          />
                        </div>
                        <div>
                          <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">Tol Max</label>
                          <input
                            type="number"
                            value={newPlanToleranceHigh}
                            onChange={(e) => setNewPlanToleranceHigh(Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-mono"
                            data-testid="input-new-plan-tol-max"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center justify-end gap-2 pt-3 border-t border-zinc-800">
                      <button
                        onClick={() => setShowNewPlanModal(false)}
                        className="px-3 py-1.5 text-xs text-zinc-400 hover:text-white"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleCreateValidationPlan}
                        disabled={validationLoading}
                        className="px-3.5 py-1.5 text-xs font-semibold rounded bg-amber-500 hover:bg-amber-400 text-black font-bold"
                        data-testid="btn-submit-new-plan"
                      >
                        Create Plan
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Modal: Submit Validation Evidence */}
              {showSubmitEvidenceModal && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                  <div
                    className="w-full max-w-lg rounded-xl border border-zinc-700 bg-zinc-900 text-zinc-100 p-6 shadow-2xl space-y-4"
                    data-testid="modal-submit-evidence"
                  >
                    <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
                      <h3 className="text-sm font-bold text-white flex items-center gap-2">
                        <FlaskConical className="w-4 h-4 text-blue-400" />
                        Ingest Observed Validation Evidence
                      </h3>
                      <button
                        onClick={() => setShowSubmitEvidenceModal(false)}
                        className="text-zinc-500 hover:text-zinc-300 text-sm"
                      >
                        ✕
                      </button>
                    </div>

                    <div className="space-y-3 text-xs">
                      <div>
                        <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">
                          Source Identifier
                        </label>
                        <input
                          type="text"
                          value={evidenceSourceId}
                          onChange={(e) => setEvidenceSourceId(e.target.value)}
                          className="w-full px-3 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-mono"
                          data-testid="input-evidence-source-id"
                        />
                      </div>

                      <div className="grid grid-cols-3 gap-2">
                        <div>
                          <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">Observed Mean</label>
                          <input
                            type="number"
                            value={evidenceObservedVal}
                            onChange={(e) => setEvidenceObservedVal(Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-mono"
                            data-testid="input-evidence-val"
                          />
                        </div>
                        <div>
                          <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">Interval Min</label>
                          <input
                            type="number"
                            value={evidenceLowBound}
                            onChange={(e) => setEvidenceLowBound(Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-mono"
                            data-testid="input-evidence-low"
                          />
                        </div>
                        <div>
                          <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">Interval Max</label>
                          <input
                            type="number"
                            value={evidenceHighBound}
                            onChange={(e) => setEvidenceHighBound(Number(e.target.value))}
                            className="w-full px-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-mono"
                            data-testid="input-evidence-high"
                          />
                        </div>
                      </div>

                      <div className="flex items-center gap-2 pt-2">
                        <input
                          type="checkbox"
                          id="chk-phys"
                          checked={isPhysicallyValidated}
                          onChange={(e) => setIsPhysicallyValidated(e.target.checked)}
                          className="rounded border-zinc-700 bg-zinc-950 text-emerald-500"
                          data-testid="chk-physically-validated"
                        />
                        <label htmlFor="chk-phys" className="text-zinc-300 font-mono text-[11px]">
                          Empirically / Physically Validated Measurement (Non-Simulated)
                        </label>
                      </div>

                      <div>
                        <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">
                          Physical Limitations / Scope Notes
                        </label>
                        <input
                          type="text"
                          value={evidenceLimitation}
                          onChange={(e) => setEvidenceLimitation(e.target.value)}
                          className="w-full px-3 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-sans"
                          data-testid="input-evidence-limitation"
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-end gap-2 pt-3 border-t border-zinc-800">
                      <button
                        onClick={() => setShowSubmitEvidenceModal(false)}
                        className="px-3 py-1.5 text-xs text-zinc-400 hover:text-white"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => selectedPlan && handleSubmitEvidence(selectedPlan.id)}
                        disabled={validationLoading}
                        className="px-3.5 py-1.5 text-xs font-semibold rounded bg-blue-600 hover:bg-blue-500 text-white font-bold"
                        data-testid="btn-submit-evidence"
                      >
                        Submit Evidence
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Tab 10: Decision Dossiers & Closure Governance (Phase 6.7) */}
          {activeTab === "dossiers" && (
            <div className="space-y-6" data-testid="container-decision-dossiers">
              {/* Governance & Decision Separation Policy Banner */}
              <div
                className="p-4 rounded-lg bg-zinc-900/80 border border-amber-500/40 text-xs space-y-2"
                data-testid="governance-separation-notice-v2"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 font-bold text-amber-400 uppercase font-mono tracking-wider">
                    <Scale className="w-4 h-4 text-amber-400" />
                    Governance & Decision Separation Policy (Phase 6.7)
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className="px-2 py-0.5 rounded text-[10px] font-mono bg-zinc-800 text-zinc-300 border border-zinc-700"
                      data-testid="badge-dossier-safety-inferred"
                    >
                      deployment_safety_inferred = false
                    </span>
                    <span
                      className="px-2 py-0.5 rounded text-[10px] font-mono bg-rose-950/70 text-rose-300 border border-rose-500/40"
                      data-testid="badge-dossier-deployment-auth"
                    >
                      Deployment: NOT_ESTABLISHED
                    </span>
                  </div>
                </div>
                <p className="text-zinc-300 font-sans leading-relaxed">
                  Strict Separation Invariant: Source verification != Criteria evaluation != Gap closure != Dossier approval != Deployment authorization.
                  Satisfying epistemic evidence thresholds establishes scientific defensibility for a specific engineering decision, strictly decoupled from operational deployment safety certification.
                </p>
              </div>

              {/* Dossier Query & Compilation Bar */}
              <div className="flex flex-col md:flex-row md:items-center justify-between p-4 rounded-lg bg-zinc-900/50 border border-zinc-800 gap-3">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono uppercase text-zinc-400">Decision ID:</span>
                  <input
                    type="text"
                    value={validationDecisionId}
                    onChange={(e) => setValidationDecisionId(e.target.value)}
                    className="px-3 py-1.5 text-xs bg-zinc-950 border border-zinc-700 rounded text-white font-mono w-44"
                    placeholder="e.g. DEC-12"
                    data-testid="input-dossier-decision-id"
                  />
                  <button
                    onClick={() => fetchDossiers(validationDecisionId)}
                    disabled={dossierLoading}
                    className="px-3 py-1.5 text-xs font-semibold rounded bg-amber-500 hover:bg-amber-400 text-black transition flex items-center gap-1.5 disabled:opacity-50"
                    data-testid="btn-fetch-dossiers"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${dossierLoading ? "animate-spin" : ""}`} />
                    Load Dossiers
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      setCompilePlanId(selectedPlan?.id || "");
                      setCompileClosureId(closureAssessment?.id || "");
                      setCompileReassessmentId(reassessmentResult?.id || "");
                      setShowCompileModal(true);
                    }}
                    className="px-3 py-1.5 text-xs font-semibold rounded bg-zinc-800 hover:bg-zinc-700 text-white border border-zinc-700 transition flex items-center gap-1.5"
                    data-testid="btn-open-compile-dossier"
                  >
                    <FileCheck2 className="w-3.5 h-3.5 text-amber-400" />
                    Compile Decision Dossier
                  </button>
                </div>
              </div>

              {/* Error Alert */}
              {dossierError && (
                <div className="p-3 rounded-lg bg-rose-950/60 border border-rose-500/50 text-rose-200 text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
                  <span>{dossierError}</span>
                </div>
              )}

              {/* Dossier Selection Pills */}
              {dossiers.length > 0 && (
                <div className="flex items-center gap-2 overflow-x-auto pb-1" data-testid="dossier-selector-list">
                  {dossiers.map((d) => (
                    <button
                      key={d.id}
                      onClick={() => setSelectedDossier(d)}
                      className={`px-3 py-1.5 text-xs font-mono rounded border transition flex items-center gap-2 ${
                        selectedDossier?.id === d.id
                          ? "bg-amber-500/10 border-amber-500 text-amber-300"
                          : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                      }`}
                      data-testid={`btn-select-dossier-${d.dossier_number}`}
                    >
                      <span className="font-bold">{d.dossier_number}</span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                        {d.governance_state}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {/* Active Dossier View */}
              {selectedDossier ? (
                <div className="space-y-6" data-testid="card-decision-dossier">
                  {/* Header & Governance State */}
                  <div className="p-5 rounded-lg bg-zinc-900/60 border border-zinc-800 space-y-4">
                    <div className="flex flex-col md:flex-row md:items-center justify-between pb-3 border-b border-zinc-800 gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold font-mono text-white" data-testid="dossier-number">
                            {selectedDossier.dossier_number}
                          </span>
                          <span className="text-xs px-2 py-0.5 rounded font-mono font-bold bg-amber-500/20 text-amber-400 border border-amber-500/40" data-testid="dossier-version">
                            v{selectedDossier.dossier_version}
                          </span>
                          <span
                            className="text-xs px-2.5 py-0.5 rounded font-mono font-bold bg-zinc-800 text-zinc-200 border border-zinc-700"
                            data-testid="dossier-governance-state"
                          >
                            {selectedDossier.governance_state}
                          </span>
                          {selectedDossier.is_active ? (
                            <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-emerald-950 text-emerald-400 border border-emerald-500/40">
                              ACTIVE
                            </span>
                          ) : (
                            <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-zinc-800 text-zinc-400">
                              SUPERSEDED
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-zinc-300 mt-1 font-sans">{selectedDossier.engineering_question}</p>
                      </div>

                      {/* Governance Transition Action Buttons */}
                      <div className="flex items-center gap-2 flex-wrap" data-testid="dossier-governance-controls">
                        {selectedDossier.governance_state === "DRAFT" && (
                          <button
                            onClick={() => handleAdvanceDossierGovernance(selectedDossier.id, "ADMIT_EVIDENCE")}
                            disabled={dossierLoading}
                            className="px-2.5 py-1 text-xs font-semibold rounded bg-zinc-800 hover:bg-zinc-700 text-white border border-zinc-700 transition"
                            data-testid="btn-dossier-admit-evidence"
                          >
                            Admit Evidence
                          </button>
                        )}
                        {selectedDossier.governance_state === "IN_REVIEW" && (
                          <button
                            onClick={() => handleAdvanceDossierGovernance(selectedDossier.id, "EVALUATE_CRITERIA")}
                            disabled={dossierLoading}
                            className="px-2.5 py-1 text-xs font-semibold rounded bg-blue-700 hover:bg-blue-600 text-white transition"
                            data-testid="btn-dossier-evaluate-criteria"
                          >
                            Evaluate Criteria
                          </button>
                        )}
                        {selectedDossier.governance_state === "EVIDENCE_ACCEPTED" && (
                          <button
                            onClick={() => handleAdvanceDossierGovernance(selectedDossier.id, "REVIEW_CONCLUSION")}
                            disabled={dossierLoading}
                            className="px-2.5 py-1 text-xs font-semibold rounded bg-amber-600 hover:bg-amber-500 text-black font-bold transition"
                            data-testid="btn-dossier-review-conclusion"
                          >
                            Review Conclusion
                          </button>
                        )}
                        {selectedDossier.governance_state === "CONCLUSION_REVIEWED" && (
                          <button
                            onClick={() => handleAdvanceDossierGovernance(selectedDossier.id, "APPROVE_DECISION")}
                            disabled={dossierLoading}
                            className="px-2.5 py-1 text-xs font-semibold rounded bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-1 font-bold"
                            data-testid="btn-dossier-approve-decision"
                          >
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Approve Decision
                          </button>
                        )}
                        {selectedDossier.governance_state === "DECISION_APPROVED" && selectedDossier.is_active && (
                          <button
                            onClick={() => handleSupersedeDossier(selectedDossier.id)}
                            disabled={dossierLoading}
                            className="px-2.5 py-1 text-xs font-semibold rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition"
                            data-testid="btn-dossier-supersede"
                          >
                            Supersede Dossier
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Metadata & Lineage Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs font-mono">
                      <div>
                        <span className="text-zinc-500 block text-[10px] uppercase">Decision Type</span>
                        <span className="text-white font-bold">{selectedDossier.decision_type}</span>
                      </div>
                      <div>
                        <span className="text-zinc-500 block text-[10px] uppercase">Parent Dossier</span>
                        <span className="text-zinc-400">{selectedDossier.parent_dossier_id ? `${selectedDossier.parent_dossier_id.slice(0, 12)}...` : "None (Root v1)"}</span>
                      </div>
                      <div>
                        <span className="text-zinc-500 block text-[10px] uppercase">Dossier Content Hash</span>
                        <span className="text-amber-400 truncate block font-bold" title={selectedDossier.dossier_content_hash} data-testid="dossier-content-hash">
                          {selectedDossier.dossier_content_hash.slice(0, 16)}...
                        </span>
                      </div>
                      <div>
                        <span className="text-zinc-500 block text-[10px] uppercase">Plan Hash</span>
                        <span className="text-zinc-400 truncate block" title={selectedDossier.plan_hash} data-testid="dossier-plan-hash">
                          {selectedDossier.plan_hash.slice(0, 16)}...
                        </span>
                      </div>
                    </div>

                    {/* Sub-Stage Gate Status Badges */}
                    <div className="pt-2 border-t border-zinc-800 grid grid-cols-2 md:grid-cols-5 gap-2 text-center text-[10px] font-mono">
                      <div className="p-2 rounded bg-zinc-950 border border-zinc-800">
                        <span className="text-zinc-500 block uppercase">Admissibility</span>
                        <span className="text-white font-bold">{selectedDossier.admissibility_status}</span>
                      </div>
                      <div className="p-2 rounded bg-zinc-950 border border-zinc-800">
                        <span className="text-zinc-500 block uppercase">Criteria Satisfaction</span>
                        <span className="text-white font-bold">{selectedDossier.criteria_satisfaction_status}</span>
                      </div>
                      <div className="p-2 rounded bg-zinc-950 border border-zinc-800">
                        <span className="text-zinc-500 block uppercase">Closure</span>
                        <span className="text-white font-bold">{selectedDossier.closure_status}</span>
                      </div>
                      <div className="p-2 rounded bg-zinc-950 border border-zinc-800">
                        <span className="text-zinc-500 block uppercase">Conclusion Review</span>
                        <span className="text-white font-bold">{selectedDossier.conclusion_review_status}</span>
                      </div>
                      <div className="p-2 rounded bg-zinc-950 border border-zinc-800">
                        <span className="text-zinc-500 block uppercase">Decision Approval</span>
                        <span className="text-emerald-400 font-bold">{selectedDossier.decision_approval_status}</span>
                      </div>
                    </div>
                  </div>

                  {/* Before / After Robustness Delta Card */}
                  {selectedDossier.before_after_comparison && (
                    <div className="p-5 rounded-lg bg-zinc-900/40 border border-zinc-800 space-y-3" data-testid="section-dossier-comparison">
                      <div className="flex items-center gap-2">
                        <TrendingUp className="w-4 h-4 text-amber-400" />
                        <h3 className="text-xs font-semibold uppercase font-mono text-zinc-200">
                          Before / After Decision Robustness Delta
                        </h3>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono text-xs" data-testid="grid-dossier-delta">
                        <div className="p-3 rounded bg-zinc-950 border border-zinc-800">
                          <span className="text-[10px] text-zinc-500 block uppercase">Baseline State</span>
                          <span className="text-zinc-400 font-bold">{selectedDossier.before_after_comparison.baseline_robustness_state || "—"}</span>
                        </div>
                        <div className="p-3 rounded bg-zinc-950 border border-amber-500/40">
                          <span className="text-[10px] text-amber-400 block uppercase font-bold">Reassessed State</span>
                          <span className="text-emerald-400 font-bold">{selectedDossier.before_after_comparison.reassessed_robustness_state || "—"}</span>
                        </div>
                        <div className="p-3 rounded bg-zinc-950 border border-zinc-800">
                          <span className="text-[10px] text-zinc-500 block uppercase">Reversals Count</span>
                          <span className="text-white">
                            {selectedDossier.before_after_comparison.baseline_reversals_count ?? "—"} →{" "}
                            <span className="font-bold text-emerald-400">{selectedDossier.before_after_comparison.reassessed_reversals_count ?? "—"}</span>
                          </span>
                        </div>
                        <div className="p-3 rounded bg-zinc-950 border border-zinc-800">
                          <span className="text-[10px] text-zinc-500 block uppercase">Closure Verdict</span>
                          <span className="text-emerald-400 font-bold">{selectedDossier.before_after_comparison.closure_verdict || "—"}</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Contradictory Evidence & Unresolved Assumptions Card */}
                  <div className="p-5 rounded-lg bg-zinc-900/40 border border-zinc-800 space-y-4" data-testid="section-dossier-contradictions">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-400" />
                      <h3 className="text-xs font-semibold uppercase font-mono text-zinc-200">
                        Contradictory Evidence & Unresolved Assumptions
                      </h3>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                      <div className="p-3.5 rounded bg-zinc-950 border border-zinc-800 space-y-2">
                        <span className="text-[10px] text-zinc-400 block uppercase font-bold">
                          Contradictory Evidence Summary
                        </span>
                        {selectedDossier.contradictory_evidence_summary &&
                        selectedDossier.contradictory_evidence_summary.items &&
                        selectedDossier.contradictory_evidence_summary.items.length > 0 ? (
                          <div className="space-y-1 text-rose-300">
                            {selectedDossier.contradictory_evidence_summary.items.map((item: any, idx: number) => (
                              <div key={idx} className="p-2 rounded bg-rose-950/40 border border-rose-500/30">
                                {JSON.stringify(item)}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-zinc-500 font-sans text-xs">No contradictory evidence records observed.</p>
                        )}
                      </div>

                      <div className="p-3.5 rounded bg-zinc-950 border border-zinc-800 space-y-2">
                        <span className="text-[10px] text-zinc-400 block uppercase font-bold">
                          Unresolved Assumptions ({selectedDossier.unresolved_assumptions ? selectedDossier.unresolved_assumptions.length : 0})
                        </span>
                        {selectedDossier.unresolved_assumptions && selectedDossier.unresolved_assumptions.length > 0 ? (
                          <div className="space-y-1">
                            {selectedDossier.unresolved_assumptions.map((u: any, idx: number) => (
                              <div key={idx} className="p-2 rounded bg-zinc-900 text-zinc-300 text-[11px]">
                                {u.assumption || JSON.stringify(u)}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-zinc-500 font-sans text-xs">No unresolved epistemic assumptions.</p>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Review Audit Trail Table */}
                  <div className="p-5 rounded-lg bg-zinc-900/40 border border-zinc-800 space-y-3" data-testid="section-dossier-audit">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <History className="w-4 h-4 text-amber-400" />
                        <h3 className="text-xs font-semibold uppercase font-mono text-zinc-200">
                          Review Audit Trail ({selectedDossier.review_audit_trail ? selectedDossier.review_audit_trail.length : 0})
                        </h3>
                      </div>
                      <span className="text-[10px] font-mono text-zinc-500">Tamper-evident governance ledger</span>
                    </div>

                    <div className="overflow-x-auto">
                      <table className="w-full text-xs text-left font-mono border border-zinc-800 rounded" data-testid="table-dossier-audit-trail">
                        <thead className="bg-zinc-950 text-zinc-400 text-[10px] uppercase">
                          <tr>
                            <th className="p-2.5">Action</th>
                            <th className="p-2.5">Reviewer</th>
                            <th className="p-2.5">Role</th>
                            <th className="p-2.5">Timestamp</th>
                            <th className="p-2.5">Rationale</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-zinc-800">
                          {selectedDossier.review_audit_trail && selectedDossier.review_audit_trail.length > 0 ? (
                            selectedDossier.review_audit_trail.map((entry: any, idx: number) => (
                              <tr key={idx} className="hover:bg-zinc-800/30">
                                <td className="p-2.5 text-amber-300 font-bold">{entry.action_type}</td>
                                <td className="p-2.5 text-white">{entry.reviewer_identity || entry.reviewer_user_id || "—"}</td>
                                <td className="p-2.5 text-zinc-400">{entry.reviewer_role}</td>
                                <td className="p-2.5 text-zinc-500">{entry.timestamp ? new Date(entry.timestamp).toLocaleString() : "—"}</td>
                                <td className="p-2.5 text-zinc-300 font-sans">{entry.rationale || "—"}</td>
                              </tr>
                            ))
                          ) : (
                            <tr>
                              <td colSpan={5} className="p-3 text-center text-zinc-500 font-sans">
                                No governance review actions recorded.
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-8 text-center rounded-lg bg-zinc-900/20 border border-zinc-800 text-zinc-500 text-xs">
                  No decision dossier selected. Click &quot;Compile Decision Dossier&quot; or select an existing dossier above.
                </div>
              )}

              {/* Modal: Compile Decision Dossier */}
              {showCompileModal && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                  <div
                    className="w-full max-w-lg rounded-xl border border-zinc-700 bg-zinc-900 text-zinc-100 p-6 shadow-2xl space-y-4"
                    data-testid="modal-compile-dossier"
                  >
                    <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
                      <h3 className="text-sm font-bold text-white flex items-center gap-2">
                        <FileCheck2 className="w-4 h-4 text-amber-400" />
                        Compile Engineering Decision Dossier
                      </h3>
                      <button
                        onClick={() => setShowCompileModal(false)}
                        className="text-zinc-500 hover:text-zinc-300 text-sm"
                      >
                        ✕
                      </button>
                    </div>

                    <div className="space-y-3 text-xs">
                      <div>
                        <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">
                          Engineering Question
                        </label>
                        <textarea
                          rows={2}
                          value={compileQuestion}
                          onChange={(e) => setCompileQuestion(e.target.value)}
                          className="w-full px-3 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-sans"
                          data-testid="input-compile-question"
                        />
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">Plan ID (UUID)</label>
                          <input
                            type="text"
                            value={compilePlanId}
                            onChange={(e) => setCompilePlanId(e.target.value)}
                            className="w-full px-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-mono"
                            placeholder="Plan Record UUID"
                            data-testid="input-compile-plan-id"
                          />
                        </div>
                        <div>
                          <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">Closure ID (UUID)</label>
                          <input
                            type="text"
                            value={compileClosureId}
                            onChange={(e) => setCompileClosureId(e.target.value)}
                            className="w-full px-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-mono"
                            placeholder="Closure Record UUID"
                            data-testid="input-compile-closure-id"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">
                          Reassessment ID (UUID)
                        </label>
                        <input
                          type="text"
                          value={compileReassessmentId}
                          onChange={(e) => setCompileReassessmentId(e.target.value)}
                          className="w-full px-2.5 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-mono"
                          placeholder="Reassessment Record UUID"
                          data-testid="input-compile-reassessment-id"
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-end gap-2 pt-3 border-t border-zinc-800">
                      <button
                        onClick={() => setShowCompileModal(false)}
                        className="px-3 py-1.5 text-xs text-zinc-400 hover:text-white"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleCompileDossier}
                        disabled={dossierLoading}
                        className="px-3.5 py-1.5 text-xs font-semibold rounded bg-amber-500 hover:bg-amber-400 text-black font-bold"
                        data-testid="btn-submit-compile-dossier"
                      >
                        Compile Dossier
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Modal: Verify Evidence Source */}
              {showVerifySourceModal && (
                <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                  <div
                    className="w-full max-w-lg rounded-xl border border-zinc-700 bg-zinc-900 text-zinc-100 p-6 shadow-2xl space-y-4"
                    data-testid="modal-verify-source"
                  >
                    <div className="flex items-center justify-between pb-3 border-b border-zinc-800">
                      <h3 className="text-sm font-bold text-white flex items-center gap-2">
                        <ShieldCheck className="w-4 h-4 text-emerald-400" />
                        Verify Evidence Source Authenticity
                      </h3>
                      <button
                        onClick={() => setShowVerifySourceModal(false)}
                        className="text-zinc-500 hover:text-zinc-300 text-sm"
                      >
                        ✕
                      </button>
                    </div>

                    <div className="space-y-3 text-xs">
                      <div>
                        <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">
                          Verification Method
                        </label>
                        <select
                          value={verifyMethod}
                          onChange={(e) => setVerifyMethod(e.target.value)}
                          className="w-full px-3 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-mono"
                          data-testid="select-verify-method"
                        >
                          <option value="AUTHORIZED_CUSTODIAN_REVIEW">AUTHORIZED_CUSTODIAN_REVIEW</option>
                          <option value="TRUSTED_REGISTRY_CHECK">TRUSTED_REGISTRY_CHECK</option>
                          <option value="AUTHENTICATED_SUPPLIER_ATTESTATION">AUTHENTICATED_SUPPLIER_ATTESTATION</option>
                          <option value="CRYPTOGRAPHIC_SIGNATURE">CRYPTOGRAPHIC_SIGNATURE</option>
                        </select>
                      </div>

                      <div>
                        <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">
                          Verifier Identity
                        </label>
                        <input
                          type="text"
                          value={verifierIdentity}
                          onChange={(e) => setVerifierIdentity(e.target.value)}
                          className="w-full px-3 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-mono"
                          data-testid="input-verifier-identity"
                        />
                      </div>

                      <div>
                        <label className="block text-zinc-400 uppercase font-mono text-[10px] mb-1">
                          Verification Audit Notes
                        </label>
                        <textarea
                          rows={2}
                          value={verificationNotes}
                          onChange={(e) => setVerificationNotes(e.target.value)}
                          className="w-full px-3 py-1.5 bg-zinc-950 border border-zinc-800 rounded text-white font-sans"
                          data-testid="input-verification-notes"
                        />
                      </div>
                    </div>

                    <div className="flex items-center justify-end gap-2 pt-3 border-t border-zinc-800">
                      <button
                        onClick={() => setShowVerifySourceModal(false)}
                        className="px-3 py-1.5 text-xs text-zinc-400 hover:text-white"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => verifyingEvidenceId && handleVerifyEvidenceSource(verifyingEvidenceId)}
                        disabled={validationLoading}
                        className="px-3.5 py-1.5 text-xs font-semibold rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold"
                        data-testid="btn-submit-verify-source"
                      >
                        Verify Source
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
