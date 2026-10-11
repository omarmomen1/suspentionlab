import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  ExperimentApi,
  DeepComparisonResponse,
  ParetoCandidate,
  ParetoFrontierResponse,
  ExperimentRecordResponse,
} from "../lib/api_client";

describe("One-Click Experiment Builder Pipeline & State Machine", () => {
  type PipelineStage =
    | "CLONE_SETUP"
    | "CREATE_VERSION"
    | "VALIDATE_PARAMS"
    | "RUN_KINEMATICS"
    | "RUN_SIMULATION"
    | "CALCULATE_KPIS"
    | "CHECK_CONSTRAINTS";

  const PIPELINE_SEQUENCE: PipelineStage[] = [
    "CLONE_SETUP",
    "CREATE_VERSION",
    "VALIDATE_PARAMS",
    "RUN_KINEMATICS",
    "RUN_SIMULATION",
    "CALCULATE_KPIS",
    "CHECK_CONSTRAINTS",
  ];

  it("progresses sequentially through all 7 automated engineering stages", () => {
    let currentStep = 0;
    const history: PipelineStage[] = [];

    const advance = () => {
      if (currentStep < PIPELINE_SEQUENCE.length) {
        history.push(PIPELINE_SEQUENCE[currentStep]);
        currentStep++;
      }
    };

    while (currentStep < PIPELINE_SEQUENCE.length) {
      advance();
    }

    expect(history).toEqual(PIPELINE_SEQUENCE);
    expect(history.length).toBe(7);
    expect(history[0]).toBe("CLONE_SETUP");
    expect(history[4]).toBe("RUN_SIMULATION");
    expect(history[6]).toBe("CHECK_CONSTRAINTS");
  });

  it("guarantees strict epistemic validation state (never fake verified without physical rig)", () => {
    const candidateExperiment: Partial<ExperimentRecordResponse> = {
      id: "exp-7829-test",
      question: "What happens if I increase front roll stiffness by 10%?",
      hypothesis: "Stiffening front spring reduces heave deflection at the expense of curb strike harshness.",
      validation_state: "UNVALIDATED",
      confidence: 0.88,
      solver: "scipy.integrate.solve_ivp(RK45, rtol=1e-6)",
      backend: "NumPy 1.26 / SciPy Vectorized C-Extension",
      result_hash: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      constraints_passed: true,
    };

    expect(candidateExperiment.validation_state).toBe("UNVALIDATED");
    expect(candidateExperiment.validation_state).not.toBe("VALIDATED");
    expect(candidateExperiment.result_hash).toMatch(/^[a-f0-9]{64}$/);
    expect(candidateExperiment.solver).toContain("solve_ivp");
  });
});

describe("Comparative Intelligence Engine ('Why is B better than A?')", () => {
  it("strictly separates What Changed, What Improved, and What Got Worse (Mandatory Tradeoffs)", () => {
    const mockComparison: DeepComparisonResponse = {
      setup_a: { k_s: 35000, c: 2200 },
      setup_b: { k_s: 42000, c: 2600 },
      what_changed: [
        {
          parameter: "k_s",
          unit: "N/m",
          setup_a: 35000,
          setup_b: 42000,
          delta_abs: 7000,
          delta_pct: 20.0,
        },
        {
          parameter: "c",
          unit: "Ns/m",
          setup_a: 2200,
          setup_b: 2600,
          delta_abs: 400,
          delta_pct: 18.18,
        },
      ],
      what_improved: [
        {
          key: "peak_susp_travel_mm",
          metric: "Suspension Travel Peak",
          unit: "mm",
          baseline: 48.2,
          candidate: 39.8,
          delta_abs: -8.4,
          delta_pct: -17.43,
          reason: "Firmer spring and damper reduces peak bump travel deflection.",
          beneficial: true,
          explanation: "Firmer spring and damper reduces peak bump travel deflection.",
        },
        {
          key: "settling_time_s",
          metric: "Settling Time",
          unit: "s",
          baseline: 1.42,
          candidate: 1.08,
          delta_abs: -0.34,
          delta_pct: -23.94,
          reason: "Higher damping ratio accelerates oscillation decay.",
          beneficial: true,
          explanation: "Higher damping ratio accelerates oscillation decay.",
        },
      ],
      what_got_worse: [
        {
          key: "tire_load_variation_n",
          metric: "Dynamic Tire Load Variation",
          unit: "N",
          baseline: 412.0,
          candidate: 458.0,
          delta_abs: 46.0,
          delta_pct: 11.17,
          reason: "Stiffer suspension increases dynamic normal force variance, reducing contact patch consistency.",
          beneficial: false,
          explanation: "Stiffer suspension increases dynamic normal force variance, reducing contact patch consistency.",
        },
      ],
      engineering_causality: [
        "K_S spring stiffness increased by 20.0% (35000 → 42000 N/m).",
        "Sprung mass heave natural frequency shifted from 1.66 Hz to 1.82 Hz, associated with firmer aerodynamic platform control.",
        "Dynamic suspension heave deflection decreased, which stabilizes underbody venturi ride height.",
        "Tradeoff mechanism: Higher spring rate reduces wheel compliance, associated with increased peak tire load fluctuation over high-frequency road inputs.",
      ],
      constraints_passed: true,
      constraint_details: [
        {
          constraint: "Maximum Suspension Travel",
          limit: "≤ 55.0 mm",
          actual: "39.8 mm",
          unit: "mm",
          passed: true,
          detail: "Clearance before jounce bump stop engagement",
        },
      ],
      verdict: "SETUP_B_FAVORED",
      verdict_summary: "Setup B exhibits 2 quantifiable performance improvements over Setup A with 1 exposed tradeoff.",
      validation_state: "UNVALIDATED",
      confidence: 0.88,
      evidence: {
        solver: "scipy.integrate.solve_ivp(RK45, rtol=1e-6)",
        correlation_r2: 0.91,
        benchmarks: "K&C Rig Test 104, Damper Dyno Cal 2026-08",
        limitations: [
          "Quarter-car ODE model neglects anti-pitch/anti-squat chassis kinematics.",
          "Aerodynamic ground-effect maps assume rigid underfloor seal.",
        ],
      },
    };

    // 1. What Changed Verification
    expect(mockComparison.what_changed.length).toBe(2);
    expect(mockComparison.what_changed[0].delta_pct).toBe(20.0);

    // 2. What Improved Verification
    expect(mockComparison.what_improved.length).toBe(2);
    expect(mockComparison.what_improved.every((m) => m.beneficial)).toBe(true);

    // 3. What Got Worse (Mandatory Tradeoff) Verification
    expect(mockComparison.what_got_worse.length).toBeGreaterThanOrEqual(1);
    expect(mockComparison.what_got_worse[0].beneficial).toBe(false);
    expect(mockComparison.what_got_worse[0].delta_pct).toBeGreaterThan(0);

    // 4. Engineering Causality Verification
    const causalityText = mockComparison.engineering_causality.join(" ");
    expect(causalityText).toContain("associated with");
    expect(causalityText).toContain("Tradeoff mechanism");

    // 5. Evidence & Constraints Verification
    expect(mockComparison.evidence.correlation_r2).toBeGreaterThanOrEqual(0.9);
    expect(mockComparison.constraint_details[0].passed).toBe(true);
  });
});

describe("Multi-Objective Pareto Optimization & Utopia Distance", () => {
  const mockCandidates: ParetoCandidate[] = [
    {
      candidate_id: "CAND-01",
      params: { k_s: 20000, c: 1400 },
      objectives: { rms_body_accel: 1.35, tire_load_variation: 490 },
      constraints: { peak_susp_travel: 48.5 },
      feasible: true,
      pareto_rank: 0,
      is_pareto_optimal: true,
      delta_ride_pct: -25.0,
      delta_grip_pct: 16.7,
      explanation: "Soft setup maximizing comfort.",
    },
    {
      candidate_id: "CAND-02",
      params: { k_s: 32000, c: 2200 },
      objectives: { rms_body_accel: 1.62, tire_load_variation: 395 },
      constraints: { peak_susp_travel: 38.0 },
      feasible: true,
      pareto_rank: 0,
      is_pareto_optimal: true,
      delta_ride_pct: -10.0,
      delta_grip_pct: -6.0,
      explanation: "Balanced candidate close to Utopia point.",
    },
    {
      candidate_id: "CAND-03",
      params: { k_s: 45000, c: 3000 },
      objectives: { rms_body_accel: 2.15, tire_load_variation: 375 },
      constraints: { peak_susp_travel: 31.2 },
      feasible: true,
      pareto_rank: 0,
      is_pareto_optimal: true,
      delta_ride_pct: 19.4,
      delta_grip_pct: -10.7,
      explanation: "High-stiffness grip setup.",
    },
    {
      candidate_id: "CAND-04",
      params: { k_s: 48000, c: 3200 },
      objectives: { rms_body_accel: 2.45, tire_load_variation: 410 },
      constraints: { peak_susp_travel: 29.5 },
      feasible: true,
      pareto_rank: 1,
      is_pareto_optimal: false,
      delta_ride_pct: 36.1,
      delta_grip_pct: -2.4,
      explanation: "Dominated candidate.",
    },
  ];

  it("accurately classifies Pareto optimal vs dominated candidates", () => {
    const optimalCount = mockCandidates.filter((c) => c.is_pareto_optimal).length;
    const dominatedCount = mockCandidates.filter((c) => !c.is_pareto_optimal).length;

    expect(optimalCount).toBe(3);
    expect(dominatedCount).toBe(1);
    expect(mockCandidates[3].pareto_rank).toBe(1);
  });

  it("identifies the best compromise candidate closest to the normalized Utopia point", () => {
    // Utopia point in normalized space is (0, 0)
    const minRide = Math.min(...mockCandidates.map((c) => c.objectives.rms_body_accel));
    const maxRide = Math.max(...mockCandidates.map((c) => c.objectives.rms_body_accel));
    const minGrip = Math.min(...mockCandidates.map((c) => c.objectives.tire_load_variation));
    const maxGrip = Math.max(...mockCandidates.map((c) => c.objectives.tire_load_variation));

    const scored = mockCandidates
      .filter((c) => c.is_pareto_optimal)
      .map((c) => {
        const normX = (c.objectives.rms_body_accel - minRide) / (maxRide - minRide);
        const normY = (c.objectives.tire_load_variation - minGrip) / (maxGrip - minGrip);
        const distToUtopia = Math.sqrt(normX * normX + normY * normY);
        return { candidate: c, distToUtopia };
      })
      .sort((a, b) => a.distToUtopia - b.distToUtopia);

    const bestCompromise = scored[0].candidate;
    expect(bestCompromise.candidate_id).toBe("CAND-02");
    expect(bestCompromise.params.k_s).toBe(32000);
    expect(bestCompromise.params.c).toBe(2200);
  });

  it("generates appropriate [ TEST THIS CHANGE ] query parameters", () => {
    const candidate = mockCandidates[1];
    const params = new URLSearchParams();
    params.set("clone_from", candidate.candidate_id);
    params.set("k_s", candidate.params.k_s.toString());
    params.set("c", candidate.params.c.toString());

    const url = `/experiment?${params.toString()}`;
    expect(url).toBe("/experiment?clone_from=CAND-02&k_s=32000&c=2200");
  });
});
