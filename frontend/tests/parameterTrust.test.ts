import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  ParameterTrustApi,
  ValidationPlanningApi,
  DecisionDossierApi,
  ParameterTrustResponseDTO,
  ParameterTrustExplanationResponseDTO,
  ParameterTrustHistoryResponseDTO,
  ParameterTrustEvidenceDTO,
  DecisionExposureAssessmentResponseDTO,
  ValidationPlanResponseDTO,
  ClosureAssessmentResponseDTO,
  DecisionReassessmentResponseDTO,
  EngineeringDecisionDossierResponseDTO,
  SourceVerificationResponseDTO,
  TrustedSourceRegistryResponseDTO,
} from "../lib/api_client";
import * as apiModule from "../lib/api";

describe("ParameterTrustApi & Trust Map Frontend Unit Tests", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("API Surface & Read-Only Contract", () => {
    it("ParameterTrustApi ONLY exposes read-only GET queries (strictly no mutations)", () => {
      const methodNames = Object.getOwnPropertyNames(ParameterTrustApi).filter(
        (m) =>
          typeof (ParameterTrustApi as any)[m] === "function" &&
          m !== "prototype" &&
          m !== "name" &&
          m !== "length"
      );

      // Verify legitimate query methods exist
      expect(methodNames).toContain("getParameterTrust");
      expect(methodNames).toContain("getParameterEvidence");
      expect(methodNames).toContain("explainParameterTrust");
      expect(methodNames).toContain("getParameterTrustHistory");

      // Verify strictly NO mutation methods exist
      const forbiddenMutationPrefixes = [
        "create",
        "insert",
        "update",
        "delete",
        "post",
        "put",
        "patch",
        "mutate",
        "declare",
        "set",
      ];
      for (const name of methodNames) {
        for (const forbidden of forbiddenMutationPrefixes) {
          expect(name.toLowerCase().startsWith(forbidden)).toBe(false);
        }
      }
    });

    it("getParameterTrust fetches authoritative trust posture via GET", async () => {
      const mockTrust: ParameterTrustResponseDTO = {
        parameter_identity: {
          entity_type: "SetupCandidate",
          entity_id: "SETUP-P3L-CAND-01",
          parameter_name: "front_spring_rate",
          parameter_path: "changed_parameters.front_spring_rate.candidate",
        },
        value_reference: {
          value: 85000.0,
          value_identity: "abcd1234",
          unit: "N/m",
          source_entity: "SetupCandidate:SETUP-P3L-CAND-01",
        },
        unit: "N/m",
        current_trust_state: "VALIDATED",
        policy_version: "TRUST_POLICY_V1",
        scope: {
          vehicle_id: "CAR-2026-07",
          setup_id: "SETUP-P3L-CAND-01",
          operating_regime: "High-Speed Lateral Cornering",
        },
        supporting_evidence: [
          {
            evidence_type: "BlindValidation",
            evidence_id: "VAL-31",
            artifact_hash: "hash1234",
            relationship: "VALIDATED_BY",
            timestamp: "2026-10-08T00:00:00Z",
          },
        ],
        validation_coverage: "VALIDATED",
        recency: {
          evidence_timestamp: "2026-10-08T00:00:00Z",
          validation_timestamp: "2026-10-08T00:00:00Z",
          source_version: "v1",
          latest_supporting_validation: "VAL-31",
          age_days: 0.1,
        },
        conflicts: [],
        explanation: {
          state: "VALIDATED",
          reasons: [
            "Authoritative validation record 'VAL-31' passed holdout gate.",
            "Authoritative source provenance confirmed as 'optimization'.",
          ],
          supporting_evidence: [],
          conflicts: [],
          scope: {},
          limitations: [],
        },
        assessment_hash: "deterministic_assessment_hash_12345",
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockTrust);

      const res = await ParameterTrustApi.getParameterTrust(
        "SetupCandidate",
        "SETUP-P3L-CAND-01",
        "front_spring_rate"
      );

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/SetupCandidate/SETUP-P3L-CAND-01/front_spring_rate"
      );
      expect(res.current_trust_state).toBe("VALIDATED");
      expect(res.value_reference.value).toBe(85000.0);
      expect(res.unit).toBe("N/m");
      expect(res.assessment_hash).toBe("deterministic_assessment_hash_12345");
      expect(res.validation_coverage).toBe("VALIDATED");
    });

    it("getParameterEvidence queries /evidence via GET", async () => {
      const mockEvidence: ParameterTrustEvidenceDTO[] = [
        {
          id: "ev-1",
          evidence_type: "BlindValidation",
          evidence_id: "VAL-31",
          artifact_hash: "hash_val_31",
          relationship: "VALIDATED_BY",
          evidence_timestamp: "2026-10-08T00:00:00Z",
          metadata: { gate_verdict: "PASSED", holdout_r2: 0.88 },
        },
      ];

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockEvidence);

      const res = await ParameterTrustApi.getParameterEvidence(
        "SetupCandidate",
        "SETUP-P3L-CAND-01",
        "front_spring_rate"
      );

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/SetupCandidate/SETUP-P3L-CAND-01/front_spring_rate/evidence"
      );
      expect(res).toHaveLength(1);
      expect(res[0].evidence_id).toBe("VAL-31");
      expect(res[0].relationship).toBe("VALIDATED_BY");
    });

    it("explainParameterTrust queries /explain via GET", async () => {
      const mockExplain: ParameterTrustExplanationResponseDTO = {
        parameter_identity: {
          entity_type: "SetupCandidate",
          entity_id: "SETUP-P3L-CAND-01",
          parameter_name: "front_spring_rate",
          parameter_path: "changed_parameters.front_spring_rate.candidate",
        },
        trust_state: "VALIDATED",
        policy_version: "TRUST_POLICY_V1",
        assessment_hash: "assess_hash_abc",
        explanation: {
          state: "VALIDATED",
          reasons: ["Validation passed holdout criteria."],
          supporting_evidence: [],
          conflicts: [],
          scope: { vehicle_id: "CAR-2026-07" },
          limitations: ["Valid within defined operating regime."],
        },
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockExplain);

      const res = await ParameterTrustApi.explainParameterTrust(
        "SetupCandidate",
        "SETUP-P3L-CAND-01",
        "front_spring_rate"
      );

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/SetupCandidate/SETUP-P3L-CAND-01/front_spring_rate/explain"
      );
      expect(res.trust_state).toBe("VALIDATED");
      expect(res.explanation.reasons).toContain("Validation passed holdout criteria.");
    });

    it("getParameterTrustHistory queries /history via GET and receives ordered history", async () => {
      const mockHist: ParameterTrustHistoryResponseDTO = {
        parameter_identity: {
          entity_type: "SetupCandidate",
          entity_id: "SETUP-P3L-CAND-01",
          parameter_name: "front_spring_rate",
          parameter_path: "changed_parameters.front_spring_rate.candidate",
        },
        history: [
          {
            id: "hist-2",
            trust_state: "VALIDATED",
            validation_coverage: "VALIDATED",
            policy_version: "TRUST_POLICY_V1",
            assessment_hash: "hash-new",
            value_identity: "val-id",
            supporting_evidence_hashes: ["h1"],
            explanation: {},
            conflicts: [],
            recency_metadata: {},
            created_at: "2026-10-08T01:00:00Z",
          },
          {
            id: "hist-1",
            trust_state: "SUPPORTED",
            validation_coverage: "NO_VALIDATION",
            policy_version: "TRUST_POLICY_V1",
            assessment_hash: "hash-old",
            value_identity: "val-id",
            supporting_evidence_hashes: [],
            explanation: {},
            conflicts: [],
            recency_metadata: {},
            created_at: "2026-10-08T00:00:00Z",
          },
        ],
        total: 2,
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockHist);

      const res = await ParameterTrustApi.getParameterTrustHistory(
        "SetupCandidate",
        "SETUP-P3L-CAND-01",
        "front_spring_rate"
      );

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/SetupCandidate/SETUP-P3L-CAND-01/front_spring_rate/history"
      );
      expect(res.history).toHaveLength(2);
      expect(res.history[0].trust_state).toBe("VALIDATED");
      expect(res.history[1].trust_state).toBe("SUPPORTED");
    });

    it("ingestEntity calls /ingest/entity with expected payload", async () => {
      const mockSummary = {
        batch_id: "batch-1",
        batch_hash: "hash-batch-1",
        policy_version: "TRUST_POLICY_V1",
        recency_policy_version: "TRUST_RECENCY_POLICY_V1",
        discovered_entities: 1,
        discovered_parameters: 2,
        new_profiles: 2,
        refreshed_assessments: 0,
        unchanged_assessments: 0,
        linked_evidence_count: 3,
        conflicts_found: 0,
        skipped_entities: [],
        errors: [],
        profiles: [],
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockSummary);

      const res = await ParameterTrustApi.ingestEntity("SetupCandidate", "SETUP-01", true);

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/ingest/entity",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ entity_type: "SetupCandidate", entity_id: "SETUP-01", force_reassess: true }),
        })
      );
      expect(res.discovered_parameters).toBe(2);
      expect(res.batch_hash).toBe("hash-batch-1");
    });

    it("ingestBatch calls /ingest/batch with expected payload", async () => {
      const mockSummary = {
        batch_id: "batch-2",
        batch_hash: "hash-batch-2",
        policy_version: "TRUST_POLICY_V1",
        recency_policy_version: "TRUST_RECENCY_POLICY_V1",
        discovered_entities: 2,
        discovered_parameters: 5,
        new_profiles: 5,
        refreshed_assessments: 0,
        unchanged_assessments: 0,
        linked_evidence_count: 4,
        conflicts_found: 0,
        skipped_entities: [],
        errors: [],
        profiles: [],
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockSummary);

      const res = await ParameterTrustApi.ingestBatch({
        entities: [
          { entity_type: "SetupCandidate", entity_id: "SETUP-01" },
          { entity_type: "SimulationRun", entity_id: "RUN-01" },
        ],
      });

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/ingest/batch",
        expect.objectContaining({
          method: "POST",
        })
      );
      expect(res.discovered_entities).toBe(2);
    });

    it("analyzeSweep calls /sweep/analyze with candidates and returns metrics", async () => {
      const mockSweep = {
        parameter_name: "front_spring_rate",
        policy_version: "TRUST_POLICY_V1",
        canonical_unit: "N/m",
        sweep_hash: "sweep-hash-1",
        total_observations: 3,
        comparable_count: 3,
        excluded_count: 0,
        summary_metrics: {
          min: 80000,
          max: 90000,
          delta: 10000,
          mean: 85000,
          spread: 10000,
          unit: "N/m",
        },
        validation_coverage_breakdown: { VALIDATED: 2, NO_VALIDATION: 1 },
        trust_state_breakdown: { VALIDATED: 2, PROVISIONAL: 1 },
        evidence_gaps: {
          unvalidated_candidates: ["SetupCandidate:SETUP-03"],
          validated_candidates: ["SetupCandidate:SETUP-01", "SetupCandidate:SETUP-02"],
          coverage_pct: 66.7,
        },
        observations: [],
        excluded_observations: [],
        conflicts: [],
        outcome_associations: [],
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockSweep);

      const res = await ParameterTrustApi.analyzeSweep({
        parameter_name: "front_spring_rate",
        candidates: [
          { entity_type: "SetupCandidate", entity_id: "SETUP-01" },
          { entity_type: "SetupCandidate", entity_id: "SETUP-02" },
        ],
      });

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/sweep/analyze",
        expect.objectContaining({
          method: "POST",
        })
      );
      expect(res.summary_metrics.delta).toBe(10000);
      expect(res.evidence_gaps.coverage_pct).toBe(66.7);
    });

    it("compareFleet calls /fleet/compare and preserves cohort metrics and outlier distinction", async () => {
      const mockFleet = {
        fleet_id: "FLEET-GT3-2026",
        parameter_name: "front_spring_rate",
        policy_version: "FLEET_TRUST_POLICY_V1",
        canonical_unit: "N/m",
        report_hash: "fleet-report-hash-1",
        cohort_size: 4,
        comparable_count: 4,
        excluded_count: 0,
        missing_count: 0,
        summary_metrics: {
          min: 80000,
          max: 120000,
          delta: 40000,
          spread: 40000,
          mean: 92500,
          median: 85000,
          unit: "N/m",
          sample_count: 4,
          missing_count: 0,
          excluded_count: 0,
        },
        comparable_instances: [
          { vehicle_ref: "VEH-01", normalized_value: 80000, trust_state: "VALIDATED" },
          { vehicle_ref: "VEH-02", normalized_value: 85000, trust_state: "VALIDATED" },
          { vehicle_ref: "VEH-03", normalized_value: 85000, trust_state: "PROVISIONAL" },
          { vehicle_ref: "VEH-04", normalized_value: 120000, trust_state: "VALIDATED" },
        ],
        excluded_instances: [],
        missing_instances: [],
        conflicts: [],
        outliers: [
          {
            vehicle_ref: "VEH-04",
            value: 120000,
            outlier_type: "STATISTICAL_OUTLIER",
            note: "Value is statistically outside cohort IQR boundaries. Statistical outlier does not constitute an engineering defect.",
          },
        ],
        validation_coverage_breakdown: { VALIDATED: 3, NO_VALIDATION: 1 },
        trust_state_breakdown: { VALIDATED: 3, PROVISIONAL: 1 },
        provenance_distribution: { optimization: 4 },
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockFleet);

      const res = await ParameterTrustApi.compareFleet({
        fleet_id: "FLEET-GT3-2026",
        parameter_name: "front_spring_rate",
        members: [
          { entity_type: "VehicleProfile", entity_id: "VEH-01" },
          { entity_type: "VehicleProfile", entity_id: "VEH-02" },
          { entity_type: "VehicleProfile", entity_id: "VEH-03" },
          { entity_type: "VehicleProfile", entity_id: "VEH-04" },
        ],
      });

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/fleet/compare",
        expect.objectContaining({
          method: "POST",
        })
      );
      expect(res.cohort_size).toBe(4);
      expect(res.comparable_count).toBe(4);
      expect(res.outliers).toHaveLength(1);
      expect(res.outliers[0].outlier_type).toBe("STATISTICAL_OUTLIER");
    });

    it("getAssemblyImpact verifies decoupling of direct trust from propagated assembly impact", async () => {
      const mockImpact = {
        vehicle_id: "VEH-01",
        parameter_name: "front_spring_rate",
        assembly_name: "SUSPENSION",
        component_name: "front_spring",
        policy_version: "SENSITIVITY_PROPAGATION_POLICY_V1",
        impact_hash: "impact-hash-xyz",
        can_propagate: true,
        dependency_path: ["VEH-01", "SUSPENSION", "front_spring", "front_spring_rate"],
        direct_trust_assessment: {
          trust_state: "PROVISIONAL",
          validation_coverage: "NO_VALIDATION",
          conflicts_count: 0,
        },
        sensitivity_evidence: {
          status: "AVAILABLE",
          source_type: "SimulationRun",
          source_id: "RUN-100",
          method: "finite_difference_bdf",
          downstream_metrics: [
            { metric: "rms_body_accel_wk", elasticity: 0.32, unit: "ratio" },
          ],
        },
        impact_assessment: {
          impact_classification: "HIGH_IMPACT_EVIDENCE_GAP",
          impact_summary: "High downstream sensitivity with unvalidated parameter.",
          downstream_metrics: [
            { metric: "rms_body_accel_wk", elasticity: 0.32, unit: "ratio" },
          ],
          evidence_gaps: ["NO_PHYSICAL_VALIDATION: Parameter lacks physical holdout validation evidence."],
        },
        lineage_note: "Direct trust state is decoupled from propagated assembly impact.",
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockImpact);

      const res = await ParameterTrustApi.getAssemblyImpact("VEH-01", "front_spring_rate");

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/assembly/impact?vehicle_id=VEH-01&parameter_name=front_spring_rate"
      );
      expect(res.can_propagate).toBe(true);
      expect(res.direct_trust_assessment?.trust_state).toBe("PROVISIONAL");
      expect(res.impact_assessment?.impact_classification).toBe("HIGH_IMPACT_EVIDENCE_GAP");
    });

    it("getSensitivityEvidence represents missing sensitivity as SENSITIVITY_UNAVAILABLE (never zero)", async () => {
      const mockSensUnavailable = {
        status: "SENSITIVITY_UNAVAILABLE",
        input_parameter: "unknown_custom_damping",
        warning: "Authoritative sensitivity evidence is unavailable for parameter 'unknown_custom_damping'. Missing sensitivity is never interpreted as zero.",
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockSensUnavailable);

      const res = await ParameterTrustApi.getSensitivityEvidence("unknown_custom_damping");

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/sensitivity/evidence?parameter_name=unknown_custom_damping"
      );
      expect(res.status).toBe("SENSITIVITY_UNAVAILABLE");
      expect(res.warning).toContain("never interpreted as zero");
    });

    it("assessDecisionExposure queries decision exposure with strict governance separation", async () => {
      const mockDecisionExposure: DecisionExposureAssessmentResponseDTO = {
        decision_id: "DEC-12",
        decision_type: "EngineeringDecision",
        exposure_classification: "HIGH_EXPOSURE",
        exposure_summary: "Decision is exposed to 1 high-sensitivity unvalidated parameters.",
        policy_version: "DECISION_TRUST_POLICY_V1",
        input_snapshot_hash: "snap_hash_1234",
        assessment_hash: "assess_hash_5678",
        governance_separation_notice: "Strict Governance Separation: Parameter trust and exposure quantification are decoupled from human approval and deployment safety.",
        created_at: "2026-10-12T00:00:00Z",
        parameter_dependencies: [
          {
            decision_id: "DEC-12",
            decision_type: "EngineeringDecision",
            parameter_name: "front_spring_rate",
            entity_type: "SetupCandidate",
            entity_id: "SETUP-P3L-CAND-01",
            dependency_nature: "QUANTITATIVELY_SENSITIVE",
            kpi_metrics: ["heave_stiffness_n_per_m"],
            sensitivity_status: "HIGH_SENSITIVITY",
            elasticity: 0.32,
            source_artifact_hashes: [],
            source_evidence_ids: [],
            operating_conditions: {},
            direct_profile: {
              trust_state: "PROVISIONAL",
              validation_coverage: "NO_VALIDATION",
              conflicts: [],
              recency_metadata: {},
            },
          },
        ],
        evidence_gaps: [
          {
            parameter_name: "front_spring_rate",
            decision_id: "DEC-12",
            severity: "CRITICAL",
            reason: "Parameter has high sensitivity with no validation.",
            supporting_sources: [],
            contradicting_sources: [],
            relevant_operating_conditions: {},
            candidate_experiment_type: "RIG_TEST_4_POST",
            expected_information_gain: "Validate dynamic corner stiffness",
            unresolved_assumptions: [],
            recommendation_disclaimer: "Candidate experiment suggestion for engineering review.",
          },
        ],
        actionable_recommendations: [
          {
            target_parameter: "front_spring_rate",
            severity: "CRITICAL",
            candidate_experiment_type: "RIG_TEST_4_POST",
            expected_information_gain: "Validate dynamic corner stiffness",
            unresolved_assumptions: [],
            notice: "Candidate experiment suggestion for engineering review.",
          },
        ],
        governance_separation: {
          parameter_trust_states: { front_spring_rate: "PROVISIONAL" },
          sensitivity_impacts: { front_spring_rate: "HIGH_SENSITIVITY" },
          evidence_completeness: { total_parameters: 1, unvalidated: 1 },
          decision_exposure: "HIGH_EXPOSURE",
          approval_authorization: {
            decision_status: "PENDING",
            is_human_approved: false,
          },
          deployment_safety: {
            deployment_safety_inferred: false,
            deployment_authorization: "NOT_ESTABLISHED",
            notice: "Validation passing does not imply deployment safety.",
          },
        },
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockDecisionExposure);

      const res = await ParameterTrustApi.assessDecisionExposure({
        decision_id: "DEC-12",
        decision_type: "EngineeringDecision",
        force_reassess: false,
        persist_record: true,
      });

      expect(spy).toHaveBeenCalledWith("/api/v1/parameter-trust/decision/assess", {
        method: "POST",
        body: JSON.stringify({
          decision_id: "DEC-12",
          decision_type: "EngineeringDecision",
          force_reassess: false,
          persist_record: true,
        }),
      });
      expect(res.decision_id).toBe("DEC-12");
      expect(res.exposure_classification).toBe("HIGH_EXPOSURE");
      expect(res.governance_separation.deployment_safety.deployment_authorization).toBe("NOT_ESTABLISHED");
      expect(res.governance_separation.deployment_safety.deployment_safety_inferred).toBe(false);
      expect(res.evidence_gaps).toHaveLength(1);
      expect(res.evidence_gaps[0].candidate_experiment_type).toBe("RIG_TEST_4_POST");
    });

    it("getDecisionHistory, getDecisionDependencies, getDecisionGaps, and reassessDecisionExposure query correct routes", async () => {
      const mockHistory = {
        decision_id: "DEC-12",
        decision_type: "EngineeringDecision",
        history: [],
        total_assessments: 0,
      };
      const mockDeps = {
        decision_id: "DEC-12",
        decision_type: "EngineeringDecision",
        dependencies: [],
        total_dependencies: 0,
      };
      const mockGaps = {
        decision_id: "DEC-12",
        decision_type: "EngineeringDecision",
        exposure_classification: "LOW_EXPOSURE",
        evidence_gaps: [],
        actionable_recommendations: [],
      };
      const mockReassess = {
        decision_id: "DEC-12",
        decision_type: "EngineeringDecision",
        exposure_classification: "LOW_EXPOSURE",
        differential: {
          previous_assessment_id: "prev-id-1",
          rationale: "Updated validation results received",
        },
      };

      const spy = vi.spyOn(apiModule, "apiJson")
        .mockResolvedValueOnce(mockHistory)
        .mockResolvedValueOnce(mockDeps)
        .mockResolvedValueOnce(mockGaps)
        .mockResolvedValueOnce(mockReassess);

      const histRes = await ParameterTrustApi.getDecisionHistory("DEC-12");
      expect(histRes.decision_id).toBe("DEC-12");

      const depsRes = await ParameterTrustApi.getDecisionDependencies("DEC-12");
      expect(depsRes.decision_id).toBe("DEC-12");

      const gapsRes = await ParameterTrustApi.getDecisionGaps("DEC-12");
      expect(gapsRes.decision_id).toBe("DEC-12");

      const reassessRes = await ParameterTrustApi.reassessDecisionExposure({
        decision_id: "DEC-12",
        decision_type: "EngineeringDecision",
      });
      expect(reassessRes.differential?.rationale).toBe("Updated validation results received");
    });

    it("preflightDecisionRobustness and runDecisionRobustness query correct routes with governance separation", async () => {
      const mockPreflight = {
        decision_id: "DEC-12",
        decision_type: "EngineeringDecision",
        is_ready: true,
        validation_errors: [],
        warnings: [],
        matched_parameters_count: 2,
        missing_evidence_parameters: [],
        recomputable_kpis: [{ kpi: "ride_frequency_hz", model: "QUARTER_CAR_MODAL", unit: "Hz" }],
        policy_version: "ROBUSTNESS_POLICY_V1",
      };

      const mockRobustness = {
        decision_id: "DEC-12",
        decision_type: "EngineeringDecision",
        policy_version: "ROBUSTNESS_POLICY_V1",
        analysis_hash: "hash_robust_123",
        input_snapshot_hash: "hash_snapshot_456",
        robustness_classification: "VULNERABLE_TO_REVERSAL",
        robustness_summary: "Reversal demonstrated under corner stiffness variations.",
        selected_option: "Option A",
        target_kpi: "ride_frequency_hz",
        evaluated_envelope: {},
        evaluated_scenarios_count: 8,
        reversals_count: 1,
        reversal_scenarios: [
          {
            scenario_id: "SCEN-CORNER-01",
            parameter_values: { front_spring_rate: 70000.0 },
            original_selection: "Option A",
            scenario_winner: "Option B",
            target_kpi: "ride_frequency_hz",
            is_ranking_reversal: true,
            threshold_breach: false,
            nature: "RANKING_REVERSAL",
          },
        ],
        boundary_crossings: [
          {
            scenario_id: "SCEN-BISECT-01",
            crossing_type: "BISECTION_APPROXIMATED",
            critical_parameter: "front_spring_rate",
            nominal_value: 85000.0,
            boundary_value: 74200.0,
            parameter_shift_pct: -12.7,
            target_kpi: "ride_frequency_hz",
            description: "Boundary crossing flips winner from Option A to Option B.",
          },
        ],
        dominant_uncertainties: [
          {
            parameter_name: "front_spring_rate",
            impact_score: 0.15,
            elasticity: 0.45,
            relative_uncertainty_span_pct: 15.0,
            reversals_participated: 1,
            unit: "N/m",
          },
        ],
        voi_prioritizations: [
          {
            parameter_name: "front_spring_rate",
            priority_level: "HIGH",
            urgency: "CRITICAL",
            recommended_experiment: "RIG_TEST_4_POST",
            current_trust_state: "PROVISIONAL",
            elasticity: 0.45,
            justification: "Critical reversal driver requiring experimental stiffness verification.",
          },
        ],
        solver_failures: [],
        governance_separation_notice: "DECISION ROBUSTNESS ANALYSIS IS AN ANALYTICAL UNCERTAINTY QUANTIFICATION ONLY.",
        deployment_safety_inferred: false,
        deployment_authorization: "NOT_ESTABLISHED",
        is_active: true,
      };

      const spy = vi.spyOn(apiModule, "apiJson")
        .mockResolvedValueOnce(mockPreflight)
        .mockResolvedValueOnce(mockRobustness);

      const preflightRes = await ParameterTrustApi.preflightDecisionRobustness({
        decision_id: "DEC-12",
      });
      expect(preflightRes.decision_id).toBe("DEC-12");
      expect(preflightRes.is_ready).toBe(true);
      expect(preflightRes.recomputable_kpis).toHaveLength(1);

      const robustnessRes = await ParameterTrustApi.runDecisionRobustness({
        decision_id: "DEC-12",
        persist_record: true,
      });
      expect(robustnessRes.decision_id).toBe("DEC-12");
      expect(robustnessRes.robustness_classification).toBe("VULNERABLE_TO_REVERSAL");
      expect(robustnessRes.deployment_safety_inferred).toBe(false);
      expect(robustnessRes.deployment_authorization).toBe("NOT_ESTABLISHED");
      expect(robustnessRes.reversals_count).toBe(1);
      expect(robustnessRes.boundary_crossings).toHaveLength(1);
      expect(robustnessRes.voi_prioritizations[0].recommended_experiment).toBe("RIG_TEST_4_POST");
    });

    it("getDecisionBoundaries, getDecisionVOI, and getDecisionRobustnessHistory query correct endpoints", async () => {
      const mockBounds = { decision_id: "DEC-12", boundary_crossings: [], total: 0 };
      const mockVOI = { decision_id: "DEC-12", voi_prioritizations: [], total: 0 };
      const mockHistory = { decision_id: "DEC-12", history: [], total: 0 };

      const spy = vi.spyOn(apiModule, "apiJson")
        .mockResolvedValueOnce(mockBounds)
        .mockResolvedValueOnce(mockVOI)
        .mockResolvedValueOnce(mockHistory);

      const boundsRes = await ParameterTrustApi.getDecisionBoundaries("DEC-12");
      expect(boundsRes.decision_id).toBe("DEC-12");

      const voiRes = await ParameterTrustApi.getDecisionVOI("DEC-12");
      expect(voiRes.decision_id).toBe("DEC-12");

      const histRes = await ParameterTrustApi.getDecisionRobustnessHistory("DEC-12");
      expect(histRes.decision_id).toBe("DEC-12");
    });

    it("ValidationPlanningApi manages plan lifecycle, evidence, closure, and reassessment", async () => {
      const mockPlan: ValidationPlanResponseDTO = {
        id: "plan-uuid-1",
        plan_id: "VAL-PLAN-001",
        decision_id: "DEC-12",
        parameter_name: "front_spring_rate",
        validation_method: "RIG_TEST_4_POST",
        status: "DRAFT",
        plan_version: 1,
        unit: "N/mm",
        is_active: true,
        deployment_safety_inferred: false,
        deployment_authorization: "NOT_ESTABLISHED",
        acceptance_criteria: [
          {
            metric_name: "spring_rate_tolerance",
            target_value: 80.0,
            tolerance_band: [76.0, 84.0],
            unit: "N/mm",
            status: "PROPOSED",
          },
        ],
      };

      const mockAuthorizedPlan: ValidationPlanResponseDTO = {
        ...mockPlan,
        status: "AUTHORIZED",
        acceptance_criteria: [
          {
            metric_name: "spring_rate_tolerance",
            target_value: 80.0,
            tolerance_band: [76.0, 84.0],
            unit: "N/mm",
            status: "AUTHORIZED",
          },
        ],
      };

      const mockEvidence = {
        id: "ev-uuid-1",
        plan_id: "plan-uuid-1",
        evidence_source_type: "PHYSICAL_RIG_MEASUREMENT",
        source_identifier: "TEST-RIG-001",
        parameter_name: "front_spring_rate",
        observed_value: 80.4,
        observed_interval: [78.5, 82.3],
        unit: "N/mm",
        is_physically_validated: true,
        review_status: "PENDING_REVIEW",
      };

      const mockClosure: ClosureAssessmentResponseDTO = {
        id: "closure-uuid-1",
        plan_id: "plan-uuid-1",
        decision_id: "DEC-12",
        parameter_name: "front_spring_rate",
        closure_verdict: "CLOSED_WITH_SUPPORTING_EVIDENCE",
        criteria_met: true,
        criteria_evaluated: [
          {
            metric_name: "spring_rate_tolerance",
            target_value: 80.0,
            measured_value: 80.4,
            passed: true,
            status: "SATISFIED",
          },
        ],
        requires_robustness_reassessment: true,
        closure_summary: "Observed 4-post rig measurement satisfies authorized tolerance band.",
        closure_hash: "closurehash123",
        governance_separation_notice: "VALIDATION EVIDENCE GAP CLOSURE DOES NOT AUTHORIZE DEPLOYMENT.",
        finite_sample_notice: "Finite empirical test runs do not certify full infinite operational envelope.",
        deployment_safety_inferred: false,
        deployment_authorization: "NOT_ESTABLISHED",
        is_active: true,
      };

      const mockReassessment: DecisionReassessmentResponseDTO = {
        id: "reassess-uuid-1",
        decision_id: "DEC-12",
        plan_id: "plan-uuid-1",
        closure_id: "closure-uuid-1",
        reversal_status: "REVERSAL_RESOLVED",
        reassessment_delta: {
          classification_before: "VULNERABLE_TO_REVERSAL",
          classification_after: "ROBUST_WITHIN_CREDIBLE_RANGE",
          reversals_before_count: 1,
          reversals_after_count: 0,
          reversal_status: "REVERSAL_RESOLVED",
          parameter_uncertainty_updated: "front_spring_rate",
          boundaries_before_count: 2,
          boundaries_after_count: 0,
          gap_closure_verdict: "CLOSED_WITH_SUPPORTING_EVIDENCE",
        },
        envelope_coverage_statement: "Empirical physical measurements narrow tolerance interval to [78.5, 82.3] N/mm.",
        governance_separation_notice: "DECISION REASSESSMENT DOES NOT ESTABLISH DEPLOYMENT SAFETY.",
        deployment_safety_inferred: false,
        deployment_authorization: "NOT_ESTABLISHED",
        reassessment_hash: "reassesshash123",
        is_active: true,
      };

      const spy = vi.spyOn(apiModule, "apiJson")
        .mockResolvedValueOnce(mockPlan) // createValidationPlan
        .mockResolvedValueOnce(mockAuthorizedPlan) // transitionValidationPlan
        .mockResolvedValueOnce(mockEvidence) // submitValidationEvidence
        .mockResolvedValueOnce(mockClosure) // evaluateEvidenceClosure
        .mockResolvedValueOnce(mockReassessment); // reassessDecision

      // 1. Create Plan
      const created = await ValidationPlanningApi.createValidationPlan({
        decision_id: "DEC-12",
        parameter_name: "front_spring_rate",
        validation_method: "RIG_TEST_4_POST",
      });
      expect(created.plan_id).toBe("VAL-PLAN-001");
      expect(created.status).toBe("DRAFT");
      expect(created.deployment_safety_inferred).toBe(false);
      expect(created.deployment_authorization).toBe("NOT_ESTABLISHED");

      // 2. Authorize Plan
      const authorized = await ValidationPlanningApi.transitionValidationPlan("plan-uuid-1", {
        target_status: "AUTHORIZED",
      });
      expect(authorized.status).toBe("AUTHORIZED");
      expect(authorized.acceptance_criteria![0].status).toBe("AUTHORIZED");

      // 3. Submit Evidence
      const evidence = await ValidationPlanningApi.submitValidationEvidence("plan-uuid-1", {
        source_identifier: "TEST-RIG-001",
        evidence_source_type: "PHYSICAL_RIG_MEASUREMENT",
        observed_value: 80.4,
        is_physically_validated: true,
      });
      expect(evidence.source_identifier).toBe("TEST-RIG-001");
      expect(evidence.is_physically_validated).toBe(true);

      // 4. Evaluate Closure
      const closure = await ValidationPlanningApi.evaluateEvidenceClosure("plan-uuid-1");
      expect(closure.closure_verdict).toBe("CLOSED_WITH_SUPPORTING_EVIDENCE");
      expect(closure.criteria_met).toBe(true);
      expect(closure.deployment_safety_inferred).toBe(false);
      expect(closure.deployment_authorization).toBe("NOT_ESTABLISHED");
      expect(closure.finite_sample_notice).toBeDefined();

      // 5. Reassess Decision
      const reassessment = await ValidationPlanningApi.reassessDecision("plan-uuid-1");
      expect(reassessment.reversal_status).toBe("REVERSAL_RESOLVED");
      expect(reassessment.reassessment_delta?.classification_before).toBe("VULNERABLE_TO_REVERSAL");
      expect(reassessment.reassessment_delta?.classification_after).toBe("ROBUST_WITHIN_CREDIBLE_RANGE");
      expect(reassessment.reassessment_delta?.reversals_after_count).toBe(0);
      expect(reassessment.deployment_safety_inferred).toBe(false);
      expect(reassessment.deployment_authorization).toBe("NOT_ESTABLISHED");
    });
  });

  describe("Phase 6.7 Decision Dossiers, Source Verification & Closure Governance", () => {
    it("verifyEvidenceSource calls verify-source endpoint with verifier details and returns verified status", async () => {
      const mockVerification: SourceVerificationResponseDTO = {
        id: "sv-uuid-1",
        evidence_item_id: "ev-uuid-1",
        verification_method: "AUTHORIZED_CUSTODIAN_REVIEW",
        verification_status: "VERIFIED",
        verifier_identity: "Lead Validation Auditor",
        verifier_role: "SYSTEM_AUDITOR",
        verifier_user_id: "auditor-01",
        verification_timestamp: "2026-10-20T05:00:00Z",
        artifact_hash: "artifacthash123",
        supporting_references: { calibration_cert: "CERT-2026-99" },
        scope: { test_rig: "RIG-4P-A" },
        verification_notes: "Source calibration certificate and raw telemetry records verified.",
        verification_hash: "vhash123",
        is_revoked: false,
        revocation_reason: null,
        created_at: "2026-10-20T05:00:00Z",
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockVerification);

      const res = await DecisionDossierApi.verifyEvidenceSource("ev-uuid-1", {
        verification_method: "AUTHORIZED_CUSTODIAN_REVIEW",
        verifier_identity: "Lead Validation Auditor",
        verification_notes: "Source calibration certificate and raw telemetry records verified.",
      });

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/validation/evidence/ev-uuid-1/verify-source",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            verification_method: "AUTHORIZED_CUSTODIAN_REVIEW",
            verifier_identity: "Lead Validation Auditor",
            verification_notes: "Source calibration certificate and raw telemetry records verified.",
          }),
        })
      );
      expect(res.id).toBe("sv-uuid-1");
      expect(res.verification_status).toBe("VERIFIED");
      expect(res.is_revoked).toBe(false);
    });

    it("revokeEvidenceSource cascades revocation and returns REVOKED status", async () => {
      const mockRevoked: SourceVerificationResponseDTO = {
        id: "sv-uuid-1",
        evidence_item_id: "ev-uuid-1",
        verification_method: "AUTHORIZED_CUSTODIAN_REVIEW",
        verification_status: "REVOKED",
        verifier_identity: "Lead Validation Auditor",
        verifier_role: "SYSTEM_AUDITOR",
        verifier_user_id: "auditor-01",
        verification_timestamp: "2026-10-20T05:00:00Z",
        artifact_hash: "artifacthash123",
        supporting_references: {},
        scope: {},
        verification_notes: "Revoked due to calibration dispute.",
        verification_hash: "vhash123",
        is_revoked: true,
        revocation_reason: "Disputed sensor calibration.",
        created_at: "2026-10-20T05:00:00Z",
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockRevoked);

      const res = await DecisionDossierApi.revokeEvidenceSource("ev-uuid-1", {
        reason: "Disputed sensor calibration.",
      });

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/validation/evidence/ev-uuid-1/revoke-source",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ reason: "Disputed sensor calibration." }),
        })
      );
      expect(res.verification_status).toBe("REVOKED");
      expect(res.is_revoked).toBe(true);
      expect(res.revocation_reason).toBe("Disputed sensor calibration.");
    });

    it("compileDecisionDossier creates deterministic dossier with strict non-elevation guarantees", async () => {
      const mockDossier: EngineeringDecisionDossierResponseDTO = {
        id: "dossier-uuid-1",
        dossier_number: "DOS-DEC-12-001",
        decision_id: "DEC-12",
        decision_type: "EngineeringDecision",
        engineering_question: "Is front spring stiffness robust against reversal under measured bump loads?",
        dossier_version: 1,
        parent_dossier_id: null,
        plan_id: "plan-uuid-1",
        plan_version: 1,
        plan_hash: "planhash123",
        sealed_acceptance_criteria: [
          { metric_name: "spring_rate_tolerance", target_value: 80.0, status: "AUTHORIZED" },
        ],
        exposure_assessment_id: "exp-uuid-1",
        exposure_hash: "exphash123",
        baseline_robustness_analysis_id: "rob-base-1",
        baseline_robustness_hash: "robbasehash123",
        closure_id: "closure-uuid-1",
        closure_hash: "closurehash123",
        reassessment_id: "reassess-uuid-1",
        reassessment_hash: "reassesshash123",
        reassessed_robustness_analysis_id: "rob-reassess-1",
        reassessed_robustness_hash: "robreassesshash123",
        evidence_item_ids: ["ev-uuid-1"],
        source_verification_ids: ["sv-uuid-1"],
        evidence_lineage_summary: { total_evidence_items: 1, verified_sources: 1 },
        contradictory_evidence_summary: { contradictory_count: 0, items: [] },
        unresolved_assumptions: [],
        before_after_comparison: {
          baseline_robustness_state: "VULNERABLE_TO_REVERSAL",
          reassessed_robustness_state: "ROBUST_WITHIN_CREDIBLE_RANGE",
          baseline_reversals_count: 1,
          reassessed_reversals_count: 0,
          closure_verdict: "CLOSED_WITH_SUPPORTING_EVIDENCE",
        },
        governance_state: "DRAFT",
        admissibility_status: "PENDING_ADMISSIBILITY",
        criteria_satisfaction_status: "PENDING_EVALUATION",
        closure_status: "PENDING_CLOSURE",
        conclusion_review_status: "PENDING_REVIEW",
        decision_approval_status: "PENDING_APPROVAL",
        governance_separation_notice:
          "STRICT NON-ELEVATION POLICY: Dossier approval != Deployment authorization != Operational safety certification. " +
          "Engineering decision closure establishes epistemic bounding based on admissible evidence; deployment safety must be established through independent system-level safety cases.",
        deployment_authorization_status: "NOT_ESTABLISHED",
        deployment_safety_inferred: false,
        review_audit_trail: [
          {
            action_type: "COMPILE_DOSSIER",
            reviewer_identity: "Automated Evidence Compiler",
            reviewer_role: "SYSTEM",
            timestamp: "2026-10-20T05:00:00Z",
            rationale: "Compiled initial engineering decision dossier for DEC-12.",
          },
        ],
        dossier_content_hash: "deterministicdossierhash1234567890abcdef",
        is_active: true,
        superseded_by: null,
        created_at: "2026-10-20T05:00:00Z",
        updated_at: "2026-10-20T05:00:00Z",
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockDossier);

      const res = await DecisionDossierApi.compileDecisionDossier({
        decision_id: "DEC-12",
        plan_id: "plan-uuid-1",
        closure_id: "closure-uuid-1",
        reassessment_id: "reassess-uuid-1",
        engineering_question: "Is front spring stiffness robust against reversal under measured bump loads?",
      });

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/validation/dossiers/compile",
        expect.objectContaining({ method: "POST" })
      );
      expect(res.dossier_number).toBe("DOS-DEC-12-001");
      expect(res.governance_state).toBe("DRAFT");
      expect(res.dossier_content_hash).toBe("deterministicdossierhash1234567890abcdef");
      expect(res.deployment_safety_inferred).toBe(false);
      expect(res.deployment_authorization_status).toBe("NOT_ESTABLISHED");
      expect(res.governance_separation_notice).toContain("STRICT NON-ELEVATION POLICY");
      expect(res.governance_separation_notice).toContain("deployment safety must be established through independent system-level safety cases");
    });

    it("advanceDossierGovernance advances state through sequential authorized gates and enforces safety separation", async () => {
      const mockApprovedDossier: EngineeringDecisionDossierResponseDTO = {
        id: "dossier-uuid-1",
        dossier_number: "DOS-DEC-12-001",
        decision_id: "DEC-12",
        decision_type: "EngineeringDecision",
        engineering_question: "Is front spring stiffness robust against reversal under measured bump loads?",
        dossier_version: 1,
        parent_dossier_id: null,
        plan_id: "plan-uuid-1",
        plan_version: 1,
        plan_hash: "planhash123",
        sealed_acceptance_criteria: [],
        closure_id: "closure-uuid-1",
        closure_hash: "closurehash123",
        reassessment_id: "reassess-uuid-1",
        reassessment_hash: "reassesshash123",
        evidence_item_ids: ["ev-uuid-1"],
        source_verification_ids: ["sv-uuid-1"],
        evidence_lineage_summary: {},
        contradictory_evidence_summary: { items: [] },
        unresolved_assumptions: [],
        before_after_comparison: {},
        governance_state: "DECISION_APPROVED",
        admissibility_status: "EVIDENCE_ADMITTED",
        criteria_satisfaction_status: "CRITERIA_SATISFIED",
        closure_status: "GAP_CLOSED",
        conclusion_review_status: "CONCLUSION_ACCEPTED",
        decision_approval_status: "DECISION_FORMALLY_APPROVED",
        governance_separation_notice: "STRICT NON-ELEVATION POLICY: Dossier approval != Deployment authorization.",
        deployment_authorization_status: "NOT_ESTABLISHED",
        deployment_safety_inferred: false,
        review_audit_trail: [
          { action_type: "APPROVE_DECISION", reviewer_role: "LEAD_ENGINEER", timestamp: "2026-10-20T05:10:00Z" },
        ],
        dossier_content_hash: "hashapproved123",
        is_active: true,
        superseded_by: null,
        created_at: "2026-10-20T05:00:00Z",
        updated_at: "2026-10-20T05:10:00Z",
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockApprovedDossier);

      const res = await DecisionDossierApi.advanceDossierGovernance("dossier-uuid-1", {
        action_type: "APPROVE_DECISION",
        rationale: "Approved by Lead Chassis Engineer after conclusion review.",
      });

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/validation/dossiers/dossier-uuid-1/governance-transition",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            action_type: "APPROVE_DECISION",
            rationale: "Approved by Lead Chassis Engineer after conclusion review.",
          }),
        })
      );
      expect(res.governance_state).toBe("DECISION_APPROVED");
      expect(res.decision_approval_status).toBe("DECISION_FORMALLY_APPROVED");
      // Critical check: Even upon final approval, safety is NOT inferred
      expect(res.deployment_safety_inferred).toBe(false);
      expect(res.deployment_authorization_status).toBe("NOT_ESTABLISHED");
    });

    it("supersedeDossier creates version 2, links parent, and preserves immutable lineage", async () => {
      const mockSupersededV2: EngineeringDecisionDossierResponseDTO = {
        id: "dossier-uuid-2",
        dossier_number: "DOS-DEC-12-001",
        decision_id: "DEC-12",
        decision_type: "EngineeringDecision",
        engineering_question: "Is front spring stiffness robust against reversal under measured bump loads?",
        dossier_version: 2,
        parent_dossier_id: "dossier-uuid-1",
        plan_id: "plan-uuid-2",
        plan_version: 2,
        plan_hash: "planhash456",
        sealed_acceptance_criteria: [],
        closure_id: "closure-uuid-2",
        closure_hash: "closurehash456",
        reassessment_id: "reassess-uuid-2",
        reassessment_hash: "reassesshash456",
        evidence_item_ids: ["ev-uuid-2"],
        source_verification_ids: ["sv-uuid-2"],
        evidence_lineage_summary: {},
        contradictory_evidence_summary: { items: [] },
        unresolved_assumptions: [],
        before_after_comparison: {},
        governance_state: "DRAFT",
        admissibility_status: "PENDING_ADMISSIBILITY",
        criteria_satisfaction_status: "PENDING_EVALUATION",
        closure_status: "PENDING_CLOSURE",
        conclusion_review_status: "PENDING_REVIEW",
        decision_approval_status: "PENDING_APPROVAL",
        governance_separation_notice: "STRICT NON-ELEVATION POLICY",
        deployment_authorization_status: "NOT_ESTABLISHED",
        deployment_safety_inferred: false,
        review_audit_trail: [
          {
            action_type: "SUPERSEDE_DOSSIER",
            reviewer_role: "SYSTEM",
            timestamp: "2026-10-20T05:20:00Z",
            rationale: "Superseded with updated empirical evidence and reassessment cycle.",
          },
        ],
        dossier_content_hash: "hashv2content789",
        is_active: true,
        superseded_by: null,
        created_at: "2026-10-20T05:20:00Z",
        updated_at: "2026-10-20T05:20:00Z",
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockSupersededV2);

      const res = await DecisionDossierApi.supersedeDossier("dossier-uuid-1", {
        reason: "Superseded with updated empirical evidence and reassessment cycle.",
      });

      expect(spy).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/validation/dossiers/dossier-uuid-1/supersede",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            reason: "Superseded with updated empirical evidence and reassessment cycle.",
          }),
        })
      );
      expect(res.dossier_version).toBe(2);
      expect(res.parent_dossier_id).toBe("dossier-uuid-1");
      expect(res.is_active).toBe(true);
      expect(res.deployment_safety_inferred).toBe(false);
      expect(res.deployment_authorization_status).toBe("NOT_ESTABLISHED");
    });

    it("registerTrustedSource and listTrustedSources manages authoritative trusted registries", async () => {
      const mockSource: TrustedSourceRegistryResponseDTO = {
        id: "source-reg-1",
        source_identifier: "FACILITY-DYNO-CHASSIS-01",
        source_name: "Chassis Dyno Test Facility 01",
        source_type: "AUTHORITATIVE_LAB_FACILITY",
        is_authorized: true,
        certificate_ref: "ISO-17025-CAL-2026",
        public_key_pem: null,
        valid_from: "2026-01-01T00:00:00Z",
        valid_until: "2027-01-01T00:00:00Z",
        created_at: "2026-10-20T05:00:00Z",
      };

      const spyRegister = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockSource);
      const registered = await DecisionDossierApi.registerTrustedSource({
        source_identifier: "FACILITY-DYNO-CHASSIS-01",
        source_name: "Chassis Dyno Test Facility 01",
        source_type: "AUTHORITATIVE_LAB_FACILITY",
        certificate_ref: "ISO-17025-CAL-2026",
      });

      expect(spyRegister).toHaveBeenCalledWith(
        "/api/v1/parameter-trust/validation/registries/trusted-sources",
        expect.objectContaining({ method: "POST" })
      );
      expect(registered.source_identifier).toBe("FACILITY-DYNO-CHASSIS-01");
      expect(registered.is_authorized).toBe(true);

      const spyList = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce([mockSource]);
      const list = await DecisionDossierApi.listTrustedSources();
      expect(spyList).toHaveBeenCalledWith("/api/v1/parameter-trust/validation/registries/trusted-sources");
      expect(list).toHaveLength(1);
      expect(list[0].certificate_ref).toBe("ISO-17025-CAL-2026");
    });
  });
});
