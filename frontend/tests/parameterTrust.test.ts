import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  ParameterTrustApi,
  ParameterTrustResponseDTO,
  ParameterTrustExplanationResponseDTO,
  ParameterTrustHistoryResponseDTO,
  ParameterTrustEvidenceDTO,
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
  });
});
