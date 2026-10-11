import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  BlindEngineeringApi,
  BlindCalibrationApi,
  BlindSessionDTO,
  VisibleContextDTO,
  BlindSubmissionDTO,
} from "../lib/api_client";
import * as apiModule from "../lib/api";

describe("BlindEngineeringApi & Information Firewall Frontend Unit Tests", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("API Surface & Boundary Integrity", () => {
    it("BlindEngineeringApi strictly omits any hidden outcome retrieval or mutation methods", () => {
      const methodNames = Object.getOwnPropertyNames(BlindEngineeringApi).filter(
        (m) =>
          typeof (BlindEngineeringApi as any)[m] === "function" &&
          m !== "prototype" &&
          m !== "name" &&
          m !== "length"
      );

      // Verify legitimate lifecycle methods exist
      expect(methodNames).toContain("createSession");
      expect(methodNames).toContain("getSession");
      expect(methodNames).toContain("getVisibleContext");
      expect(methodNames).toContain("armSession");
      expect(methodNames).toContain("activateSession");
      expect(methodNames).toContain("submitPrediction");
      expect(methodNames).toContain("lockSubmission");
      expect(methodNames).toContain("prepareReveal");
      expect(methodNames).toContain("abortSession");

      // Verify strictly NO hidden outcome methods exist
      for (const name of methodNames) {
        const lower = name.toLowerCase();
        expect(lower).not.toContain("hiddenoutcome");
        expect(lower).not.toContain("getoutcome");
        expect(lower).not.toContain("revealoutcome");
        expect(lower).not.toContain("fetchwithheld");
      }
    });

    it("getSession retrieves safe DTO with withheld flag and without outcome payload", async () => {
      const mockSession: BlindSessionDTO = {
        id: "sess-uuid-1",
        status: "BLIND_ACTIVE",
        name: "Aero Sensitivity Blind Evaluation",
        root_entity_type: "EngineeringDecision",
        root_entity_id: "DEC-12",
        visibility_summary: {
          hidden_outcome_withheld: true,
          visible_relationships_count: 5,
        },
        has_submission: false,
        session_hash: "abcd1234ef5678",
        created_at: "2026-10-08T00:00:00Z",
      };

      vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockSession);

      const res = await BlindEngineeringApi.getSession("sess-uuid-1");
      expect(res.id).toBe("sess-uuid-1");
      expect(res.status).toBe("BLIND_ACTIVE");
      expect(res.visibility_summary.hidden_outcome_withheld).toBe(true);

      // Verify no hidden outcome payload is attached
      expect((res as any).hidden_outcome_id).toBeUndefined();
      expect((res as any).hidden_outcome_values).toBeUndefined();
      expect((res as any).validation_evidence).toBeUndefined();
    });

    it("getVisibleContext retrieves allowlisted context without outcome leakage", async () => {
      const mockContext: VisibleContextDTO = {
        session_id: "sess-uuid-1",
        status: "BLIND_ACTIVE",
        root_entity: {
          entity_type: "EngineeringDecision",
          entity_id: "DEC-12",
          question: "Front spring rate optimization",
        },
        visible_entities: [
          {
            entity_type: "Investigation",
            entity_id: "INV-91",
            symptom: "Front axle grip saturation",
          },
        ],
        visible_edges: [
          {
            source_type: "EngineeringDecision",
            source_id: "DEC-12",
            relationship: "FORMULATED_FROM",
            target_type: "Investigation",
            target_id: "INV-91",
          },
        ],
        visible_context_hash: "hash123",
        accessed_at: "2026-10-08T00:00:00Z",
      };

      vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockContext);

      const res = await BlindEngineeringApi.getVisibleContext("sess-uuid-1");
      expect(res.session_id).toBe("sess-uuid-1");
      expect(res.root_entity.entity_id).toBe("DEC-12");
      expect(res.visible_entities.length).toBe(1);

      // Verify forbidden outcome fields are not present
      expect((res.root_entity as any).selected_option).toBeUndefined();
      expect((res.root_entity as any).validation_evidence).toBeUndefined();
    });

    it("lockSubmission sends prediction payload and returns sealed submission record", async () => {
      const mockSubmission: BlindSubmissionDTO = {
        id: "sub-123",
        session_id: "sess-uuid-1",
        submitted_by_user_id: "user-456",
        submission_hash: "subhash-999",
        submitted_at: "2026-10-08T00:00:00Z",
        status: "LOCKED",
      };

      vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockSubmission);

      const prediction = { prediction: "Setup-B front roll stiffness +12%" };
      const res = await BlindEngineeringApi.lockSubmission("sess-uuid-1", prediction);

      expect(res.id).toBe("sub-123");
      expect(res.status).toBe("LOCKED");
      expect(res.submission_hash).toBe("subhash-999");
    });

    it("submits versioned engineering prediction contract with schema_version 1", async () => {
      const mockSubmission: BlindSubmissionDTO = {
        id: "sub-v1",
        session_id: "sess-uuid-1",
        submitted_by_user_id: "user-456",
        submission_hash: "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
        submitted_at: "2026-10-08T00:00:00Z",
        status: "LOCKED",
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockSubmission);

      const contractPayload = {
        schema_version: "1" as const,
        prediction_type: "ENGINEERING_DECISION" as const,
        target: {
          entity_type: "EngineeringDecision",
          entity_id: "DEC-12",
          metric: "bar_rate",
        },
        selected_candidate_id: "SETUP-B",
        confidence: 0.95,
        rationale: "Provides roll stiffness headroom",
        assumptions: ["Dry track conditions", "Nominal tire pressures"],
      };

      const res = await BlindEngineeringApi.submitPrediction("sess-uuid-1", contractPayload);
      expect(res.status).toBe("LOCKED");
      expect(spy).toHaveBeenCalledWith(
        "/api/v1/blind-sessions/sess-uuid-1/submit",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ submission_payload: contractPayload }),
        })
      );
    });

    it("submits versioned quantitative prediction contract with units and finite value", async () => {
      const mockSubmission: BlindSubmissionDTO = {
        id: "sub-quant",
        session_id: "sess-uuid-1",
        submitted_by_user_id: "user-456",
        submission_hash: "quant-hash-123",
        submitted_at: "2026-10-08T00:00:00Z",
        status: "LOCKED",
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockSubmission);

      const quantPayload = {
        schema_version: "1" as const,
        prediction_type: "QUANTITATIVE" as const,
        target: {
          entity_type: "EngineeringDecision",
          entity_id: "DEC-12",
          metric: "front_roll_stiffness",
        },
        predicted_value: 1400.0,
        unit: "N/m",
        confidence: 0.9,
      };

      const res = await BlindEngineeringApi.lockSubmission("sess-uuid-1", quantPayload);
      expect(res.status).toBe("LOCKED");
      expect(spy).toHaveBeenCalledWith(
        "/api/v1/blind-sessions/sess-uuid-1/lock",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ submission_payload: quantPayload }),
        })
      );
    });

    it("revealSession triggers controlled reveal and returns comparison result", async () => {
      const mockComp = {
        id: "comp-123",
        session_id: "sess-uuid-1",
        submission_id: "sub-123",
        outcome_identity: {
          entity_type: "EngineeringDecision",
          entity_id: "DEC-12",
          artifact_hash: "out-hash-456",
        },
        prediction_schema_version: "1",
        comparison_policy_version: "1",
        comparison_type: "QUANTITATIVE",
        verdict: "METRICS_ONLY",
        comparison_metrics: {
          predicted_value: 1400.0,
          actual_value: 1350.0,
          signed_error: 50.0,
          absolute_error: 50.0,
          relative_error: 0.037037,
        },
        interpretation: "Raw quantitative error metrics computed: signed error = +50 N/m.",
        comparison_hash: "comphash-789",
        computed_at: "2026-10-08T00:00:00Z",
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockComp);

      const res = await BlindEngineeringApi.revealSession("sess-uuid-1");
      expect(res.id).toBe("comp-123");
      expect(res.verdict).toBe("METRICS_ONLY");
      expect(res.comparison_policy_version).toBe("1");
      expect(res.comparison_metrics.signed_error).toBe(50.0);
      expect(spy).toHaveBeenCalledWith(
        "/api/v1/blind-sessions/sess-uuid-1/reveal",
        expect.objectContaining({
          method: "POST",
        })
      );
    });

    it("getComparison retrieves revealed comparison with explainable interpretation and hashes", async () => {
      const mockComp = {
        id: "comp-999",
        session_id: "sess-uuid-1",
        submission_id: "sub-123",
        outcome_identity: {
          entity_type: "EngineeringDecision",
          entity_id: "DEC-12",
          artifact_hash: "out-hash-456",
        },
        prediction_schema_version: "1",
        comparison_policy_version: "1",
        comparison_type: "ENGINEERING_DECISION",
        verdict: "SUPPORTED",
        comparison_metrics: {
          selected_candidate_id: "SETUP-B",
          authoritative_choice: "SETUP-B",
          supported: true,
        },
        interpretation: "Selected engineering candidate 'SETUP-B' is supported by authoritative outcome 'SETUP-B'.",
        comparison_hash: "comphash-abc",
        computed_at: "2026-10-08T00:00:00Z",
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockComp);

      const res = await BlindEngineeringApi.getComparison("sess-uuid-1");
      expect(res.verdict).toBe("SUPPORTED");
      expect(res.comparison_hash).toBe("comphash-abc");
      expect(spy).toHaveBeenCalledWith("/api/v1/blind-sessions/sess-uuid-1/comparison");
    });

    it("getReveal retrieves authoritative revealed outcome snapshot", async () => {
      const mockReveal = {
        session_id: "sess-uuid-1",
        status: "COMPLETED",
        outcome_entity_type: "EngineeringDecision",
        outcome_entity_id: "DEC-12",
        outcome_identity: {
          entity_type: "EngineeringDecision",
          entity_id: "DEC-12",
          canonical_id: "DEC-12",
          artifact_hash: "out-hash-456",
          reveal_policy_version: "1",
          comparison_policy_version: "1",
        },
        outcome_hash: "out-hash-456",
        revealed_at: "2026-10-08T00:00:00Z",
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockReveal);

      const res = await BlindEngineeringApi.getReveal("sess-uuid-1");
      expect(res.status).toBe("COMPLETED");
      expect(res.outcome_hash).toBe("out-hash-456");
      expect(spy).toHaveBeenCalledWith("/api/v1/blind-sessions/sess-uuid-1/reveal");
    });
  });

  describe("BlindCalibrationApi & Longitudinal Track Record (Phase 5.4)", () => {
    it("BlindCalibrationApi retrieves user calibration summary with separated accuracy and coverage", async () => {
      const mockSummary = {
        calibration_policy_version: "1",
        calibration_policy_hash: "pol-hash-123",
        aggregate_hash: "agg-hash-456",
        cohort_definition: { scope: "USER", user_id: "u-1" },
        outcome_statistics: {
          total_completed_evaluations: 10,
          comparable_evaluations: 9,
          uncomparable_evaluations: 1,
          metrics_only_evaluations: 0,
          binary_evaluated_count: 8,
          correct_outcomes: 6,
          incorrect_outcomes: 2,
          observed_accuracy: 0.75,
          observed_accuracy_ci: [0.4093, 0.9285],
          comparison_coverage: 0.9,
          excluded_counts: {
            NOT_ELIGIBLE_UNCOMPARABLE: 1,
            NOT_ELIGIBLE_METRICS_ONLY: 0,
            NOT_ELIGIBLE_SEMANTICS_UNSPECIFIED: 4,
          },
          cohort_breakdown: {},
        },
        brier_score: {
          brier_score: 0.125,
          eligible_sample_size: 4,
          status: "AVAILABLE",
          excluded_count: 6,
          excluded_reasons: { NOT_ELIGIBLE_SEMANTICS_UNSPECIFIED: 4, NOT_ELIGIBLE_UNCOMPARABLE: 1 },
          interpretation: "Binary Brier score computed over 4 eligible observations.",
        },
        calibration_curve_summary: {
          status: "INSUFFICIENT_SAMPLE",
          status_message: "Sample size (4) below threshold (5).",
          total_eligible_samples: 4,
        },
        source_comparisons_count: 10,
        source_comparison_ids: ["c1", "c2"],
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockSummary);

      const res = await BlindCalibrationApi.getMySummary({ prediction_type: "CATEGORICAL" });
      expect(res.calibration_policy_version).toBe("1");
      expect(res.outcome_statistics.observed_accuracy).toBe(0.75);
      expect(res.outcome_statistics.comparison_coverage).toBe(0.9);
      expect(res.outcome_statistics.uncomparable_evaluations).toBe(1);
      expect(res.brier_score.brier_score).toBe(0.125);
      expect(spy).toHaveBeenCalledWith("/api/v1/blind-calibration/me?prediction_type=CATEGORICAL");
    });

    it("BlindCalibrationApi retrieves 5-bin calibration curve with Wilson intervals", async () => {
      const mockCurve = {
        status: "AVAILABLE",
        status_message: "Reliability curve evaluated over 10 eligible observations.",
        total_eligible_samples: 10,
        excluded_observations_count: 2,
        bins: [
          {
            bin_index: 0,
            range: [0.0, 0.2],
            label: "[0.0, 0.2)",
            sample_count: 2,
            positive_count: 0,
            mean_forecast_probability: 0.1,
            observed_frequency: 0.0,
            uncertainty_interval: [0.0, 0.658],
            is_empty: false,
          },
          {
            bin_index: 1,
            range: [0.2, 0.4],
            label: "[0.2, 0.4)",
            sample_count: 0,
            positive_count: 0,
            mean_forecast_probability: null,
            observed_frequency: null,
            uncertainty_interval: null,
            is_empty: true,
          },
        ],
        policy_version: "1",
        binning_method: "EQUAL_WIDTH_5_BINS",
        uncertainty_method: "WILSON_SCORE",
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockCurve);

      const res = await BlindCalibrationApi.getMyCurve();
      expect(res.status).toBe("AVAILABLE");
      expect(res.bins.length).toBe(2);
      expect(res.bins[0].observed_frequency).toBe(0.0);
      expect(res.bins[1].is_empty).toBe(true);
      expect(spy).toHaveBeenCalledWith("/api/v1/blind-calibration/me/curve");
    });

    it("BlindCalibrationApi retrieves longitudinal history with full provenance", async () => {
      const mockHistory = {
        calibration_policy_version: "1",
        total_count: 1,
        limit: 20,
        offset: 0,
        evaluations: [
          {
            comparison_id: "comp-1",
            comparison_hash: "hash-c1",
            comparison_policy_version: "1",
            comparison_type: "CATEGORICAL",
            verdict: "CORRECT",
            interpretation: "Exact match",
            comparison_metrics: { match: true },
            computed_at: "2026-10-09T00:00:00Z",
            session_id: "sess-1",
            session_name: "Session 1",
            session_status: "REVEALED",
            root_entity_type: "EngineeringDecision",
            root_entity_id: "DEC-1",
            revealed_at: "2026-10-09T00:00:00Z",
            submission_id: "sub-1",
            submission_hash: "hash-s1",
            submitted_at: "2026-10-08T00:00:00Z",
            prediction_payload: { confidence: 0.9, confidence_semantics: "PROBABILITY_PREDICTION_CORRECT" },
            outcome_identity: { id: "OPT-1" },
            eligibility: { eligible_for_accuracy: true, eligible_for_binary_calibration: true },
          },
        ],
      };

      const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockHistory);

      const res = await BlindCalibrationApi.getMyHistory({ limit: 20, offset: 0 });
      expect(res.total_count).toBe(1);
      expect(res.evaluations[0].comparison_id).toBe("comp-1");
      expect(res.evaluations[0].verdict).toBe("CORRECT");
      expect(spy).toHaveBeenCalledWith("/api/v1/blind-calibration/me/history?limit=20&offset=0");
    });

    it("BlindCalibrationApi strictly omits public leaderboard and ranking endpoints", () => {
      const methodNames = Object.getOwnPropertyNames(BlindCalibrationApi);
      for (const name of methodNames) {
        const lower = name.toLowerCase();
        expect(lower).not.toContain("leaderboard");
        expect(lower).not.toContain("ranking");
        expect(lower).not.toContain("allusers");
        expect(lower).not.toContain("public");
      }
    });
  });
});
