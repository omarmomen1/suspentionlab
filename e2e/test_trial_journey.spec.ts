import { test, expect } from '@playwright/test';

test.describe('SuspensionLab PRO - Formula Student Evaluation Garage E2E', () => {
  const mockTrialData = {
    trial_id: "trial-fs-ev-test",
    status: "ACTIVE",
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
    days_remaining: 7,
    simulation_run_limit: 50,
    simulation_run_count: 1,
    vehicle_project_limit: 1,
    vehicle_project_count: 1,
    telemetry_storage_limit_bytes: 52428800,
    telemetry_storage_used_bytes: 1048576,
    day_number: 1,
    day_label: "Day 1 of 7",
    evaluation_title: "Formula Student Evaluation Garage",
    contact_email: "evaluator@apex-motorsport.com"
  };

  const mockSetups = [
    {
      id: "prof-01",
      name: "Setup A — Baseline",
      params: { m_s: 50.0, m_u: 10.5, k_s: 35000.0, c: 1800.0, k_arb_f: 4500.0, k_arb_r: 3800.0, ride_height_mm: 28.0 },
      kpis: { rms_body_accel: 0.952, tire_load_variation_rms: 210.4, settling_time_s: 0.28 },
      description: "Balanced baseline setup. Moderate front/rear roll distribution and damping."
    },
    {
      id: "prof-02",
      name: "Setup B — High Roll Stiffness",
      params: { m_s: 50.0, m_u: 10.5, k_s: 42000.0, c: 2200.0, k_arb_f: 6500.0, k_arb_r: 3800.0, ride_height_mm: 27.0 },
      kpis: { rms_body_accel: 1.084, tire_load_variation_rms: 248.8, settling_time_s: 0.24 },
      description: "Aggressive front roll couple (+44% front ARB, +20% spring rate)."
    },
    {
      id: "prof-03",
      name: "Setup C — Soft Rear",
      params: { m_s: 50.0, m_u: 10.5, k_s: 35000.0, c: 1800.0, k_arb_f: 4500.0, k_arb_r: 2200.0, ride_height_mm: 29.0 },
      kpis: { rms_body_accel: 0.924, tire_load_variation_rms: 198.2, settling_time_s: 0.34 },
      description: "Compliant rear axle (-42% rear ARB, softer rear damping)."
    }
  ];

  const mockTelemetryChannels = Array.from({ length: 101 }, (_, i) => {
    const t = Number((i * 0.05).toFixed(2));
    return {
      time: t,
      vehicle_speed_kmh: Number((78.0 - (i > 30 ? 36.0 : 0)).toFixed(1)),
      lateral_accel_g: Number((i > 25 ? 1.85 : 0.2).toFixed(2)),
      longitudinal_accel_g: Number((i > 15 && i < 45 ? -1.20 : 0).toFixed(2)),
      steering_angle_deg: Number((i > 20 ? 58.0 : 0).toFixed(1)),
      susp_travel_fl_mm: Number((i > 25 ? 24.5 : 12.0).toFixed(1)),
      susp_travel_fr_mm: Number((i > 25 ? 6.2 : 12.0).toFixed(1)),
      damper_velocity_fl_mms: Number((i > 20 && i < 40 ? 185.0 : 20.0).toFixed(1)),
      damper_velocity_fr_mms: Number((i > 20 && i < 40 ? -165.0 : 15.0).toFixed(1)),
      wheel_speed_fl_rpm: 820.0,
      wheel_speed_fr_rpm: 785.0,
      tire_load_fl_n: Number((i > 25 ? 1280.0 : 720.0).toFixed(1)),
      tire_load_fr_n: Number((i > 25 ? 280.0 : 720.0).toFixed(1)),
      yaw_rate_degs: 42.0
    };
  });

  const mockWorkspaceData = {
    trial: mockTrialData,
    checklist: {
      items: {
        investigate_question: true,
        run_experiment: true,
        compare_setups: true,
        run_optimization: true,
        create_decision: true,
        try_own_question: true,
      },
      completed_count: 6,
      total_count: 6,
      is_all_completed: true,
      feedback_submitted: false,
    },
    feedback_submitted: false,
    evaluation_labels: {
      dataset: "EVALUATION DATASET",
      telemetry: "SYNTHETIC EVALUATION DATA",
      demonstration: "PREPARED DEMONSTRATION"
    },
    vehicle: {
      id: "twin-fs-01",
      car_ref: "SLP-FS-EV-01",
      setup_ref: "Setup A — Baseline",
      track_ref: "FS-Michigan-Autocross",
      base_params: {
        m_s: 50.0,
        m_u: 10.5,
        k_s: 35000.0,
        c: 1800.0,
        k_t: 110000.0,
        MR: 0.92,
        k_arb_f: 4500.0,
        k_arb_r: 3800.0,
        ride_height_mm: 28.0
      }
    },
    setups: mockSetups,
    telemetry_session: {
      id: "sess-fs-01",
      name: "FS-Michigan-Autocross-FP1",
      summary: {
        track: "FS-Michigan-Autocross",
        driver: "Evaluation Dynamics Engineer",
        session: "FP1",
        lap_time_s: 52.45,
        peak_lat_g: 1.85,
        peak_long_g: 1.20,
        sample_rate_hz: 20,
        health_status: "VALIDATED"
      }
    },
    telemetry_dataset: {
      dataset_name: "FS-Michigan-Autocross-Turn4-Entry",
      dataset_type: "EVALUATION DATASET",
      is_synthetic: true,
      evaluation_label: "SYNTHETIC EVALUATION DATA",
      vehicle_ref: "SLP-FS-EV-01",
      corner: "Turn 4 Autocross Hairpin Entry",
      duration_s: 5.0,
      sample_rate_hz: 20,
      total_samples: 101,
      peak_metrics: {
        entry_speed_kmh: 78.0,
        apex_speed_kmh: 42.0,
        peak_lat_g: 1.85,
        peak_braking_g: 1.20,
        peak_fl_tire_load_n: 1280.0,
        peak_tire_load_variation_n: 480.0,
        max_damper_velocity_mms: 185.0
      },
      channels: mockTelemetryChannels
    },
    engineering_question: {
      id: "q-fs-01",
      title: "Why is front tire-load variation increasing during aggressive corner entry?",
      question_text: "During the 78 km/h trail-braking entry into Turn 4, transient front outside tire load variation spikes by 480 N (RMS variation > 280 N), causing momentary micro-slip before steady-state roll equilibrium is achieved. Evaluate whether increasing front roll stiffness exacerbates load transfer harshness or if damper tuning can mitigate the transient fluctuation.",
      severity: "CRITICAL",
      status: "INVESTIGATING",
      context: {
        corner: "Michigan Autocross Turn 4 Entry",
        entry_speed_kmh: 78.0,
        target_settle_s: 0.28
      }
    },
    investigation: {
      what_is_happening: {
        summary: "High-frequency front tire-load fluctuation during corner entry",
        description: "During trail-braking turn-in into Turn 4 (78 -> 42 km/h), the front outside tire normal load spikes from 650 N static to 1,280 N peak, accompanied by high-frequency oscillation of 480 N peak-to-peak amplitude.",
        severity: "CRITICAL"
      },
      evidence: {
        telemetry_source: "SYNTHETIC EVALUATION DATA (Session: FS-Michigan-Autocross-FP1)",
        peak_tire_load_variation_n: 480.0,
        max_damper_velocity_mms: 185.0,
        lateral_accel_rate_gs: 3.2,
        transient_settle_delay_s: 0.44,
        target_settle_s: 0.28,
        channels_inspected: ["tire_load_fl_n", "damper_vel_fl_mms", "lat_accel_g", "steering_angle_deg"]
      },
      why: {
        root_cause: "Excessive initial front roll couple distribution under rapid lateral transfer",
        explanation: "With front roll stiffness at 4,500 N/m and stiff rebound damping (1,800 Ns/m), 72% of the dynamic roll moment is resisted by the front axle during the first 250ms of steer input."
      },
      what_should_we_test: [
        "1. Execute Hero Experiment: Increase front roll stiffness by 10% to verify whether increased roll resistance exacerbates or stabilizes tire load variation.",
        "2. Compare Setup A vs Setup B in the Vehicle & Setups Matrix.",
        "3. Run Pareto Multi-Objective Optimization to balance chassis heave acceleration vs tire load variation.",
        "4. Create an audit-defensible Engineering Decision with cryptographic provenance."
      ]
    },
    baseline_simulation: {
      id: "run-fs-01",
      label: "RUN-FS-BASE",
      title: "FS EV Baseline Simulation",
      kpis: {
        rms_body_accel: 0.952,
        peak_body_accel: 2.45,
        settling_time_s: 0.28,
        tire_load_variation_rms: 210.4,
        suspension_travel_utilization_pct: 58.2
      }
    },
    experiment_history: [
      {
        id: "exp-fs-01",
        simulation_run_id: "RUN-FS-BASE",
        created_at: new Date().toISOString(),
        hypothesis: "Increase front roll stiffness by 10% to evaluate roll angle control vs tire load variation tradeoff.",
        improvements: [
          { label: "Roll Angle Attenuation", delta_pct: -6.4, unit: "deg", reason: "Higher front roll couple resists chassis roll moment" }
        ],
        regressions: [
          { label: "Tire Load Variation (Front Outer)", delta_pct: 7.8, unit: "N", reason: "Stiffer roll resistance accelerates dynamic load transfer across front axle" }
        ],
        reproducibility_hash: "9e1c4a56b820df3108c9027814ab",
        candidate_metrics: {
          rms_body_accel: 1.025,
          settling_time_s: 0.29
        }
      }
    ]
  };

  test('Formula Student Evaluation Garage: full 10-minute guided engineer workflow', async ({ page }) => {
    // 1. Mock /auth/me for authenticated trial user
    await page.route('**/auth/me', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: "user-trial-fs",
          email: "evaluator@apex-motorsport.com",
          name: "Alex Evaluator",
          plan: "TRIAL",
          is_trial: true,
          trial_status: "ACTIVE",
          trial_days_remaining: 7,
          redirect_url: "/evaluation",
          onboarding_complete: true,
          created_at: new Date().toISOString(),
          permissions: ["simulation:run", "simulation:read", "vehicle:read"]
        })
      });
    });

    // 2. Mock trial status endpoint
    await page.route('**/trials/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockTrialData)
      });
    });

    // 3. Mock evaluation workspace endpoint
    await page.route('**/trials/workspace', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockWorkspaceData)
      });
    });

    // 4. Mock simulation run endpoint
    await page.route('**/trials/simulate', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: "COMPLETED",
          simulation_type: "QUARTER_CAR",
          kpis: {
            rms_body_accel: 0.942,
            peak_body_accel: 2.41,
            settling_time_s: 0.27,
            tire_load_variation_rms: 208.5,
            suspension_travel_utilization_pct: 57.0
          },
          params: { m_s: 50.0, c: 1800.0, k_s: 35000.0 },
          quota: { runs_used: 2, runs_limit: 50, runs_remaining: 48 }
        })
      });
    });

    // 5. Mock Pareto optimization endpoint
    await page.route('**/trials/optimize', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: "COMPLETED",
          evaluation_label: "PREPARED DEMONSTRATION",
          vehicle_ref: "SLP-FS-EV-01",
          pareto_result: {
            frontier: [
              {
                pareto_rank: 0,
                params: { k_s: 30000.0, c: 1600.0 },
                objectives: { rms_body_accel: 0.892, tire_load_variation: 194.5 },
                feasible: true
              },
              {
                pareto_rank: 0,
                params: { k_s: 35000.0, c: 1800.0 },
                objectives: { rms_body_accel: 0.952, tire_load_variation: 210.4 },
                feasible: true
              }
            ],
            best_compromise: {
              pareto_rank: 0,
              params: { k_s: 35000.0, c: 1650.0 },
              objectives: { rms_body_accel: 0.914, tire_load_variation: 201.2 },
              feasible: true
            }
          },
          quota: { runs_used: 3, runs_limit: 50 }
        })
      });
    });

    // 6. Mock Decision endpoint
    await page.route('**/trials/decision', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          decision_id: "DEC-FS-9A1B2C",
          status: "RECOMMENDED",
          question: "Why is front tire-load variation increasing during aggressive corner entry?",
          reason: "Rebound damping reduction from 1,800 to 1,650 Ns/m attenuates contact patch spike by 14.2%.",
          provenance_hash: "a4c8109bfde01823abce",
          evaluation_label: "PREPARED DEMONSTRATION"
        })
      });
    });

    // 7. Mock Custom Question endpoint
    await page.route('**/trials/questions', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: "q-custom-01",
          question_id: "Q-USER-123456",
          title: "Custom cornering heave stability test",
          status: "INVESTIGATING"
        })
      });
    });

    // Mock product analytics event endpoint
    await page.route('**/trials/events', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: "RECORDED", event: "mock_event" })
      });
    });

    // Mock customer discovery feedback endpoint
    await page.route('**/trials/feedback', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: "SAVED",
          trial_id: "trial-fs-ev-test",
          feedback: {
            most_valuable_part: "Immediate correlation between Turn 4 telemetry spike and Pareto trade-off curve.",
            prevented_more_use: "Wanted custom CSV telemetry import."
          }
        })
      });
    });

    // Navigate to evaluation workspace
    await page.goto('/evaluation');

    // ── Verify Landing Screen Header & Evaluation Badges ──
    await expect(page.locator('text=Evaluation Workspace')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('EVALUATION DATASET').first()).toBeVisible();
    await expect(page.getByText('SYNTHETIC EVALUATION DATA').first()).toBeVisible();
    await expect(page.locator('text=SLP-FS-EV-01').first()).toBeVisible();

    // ── 1. Verify Landing Screen Title, Subtitle, and Trial Status ──
    await expect(page.locator('h1', { hasText: 'SuspensionLab PRO' })).toBeVisible();
    await expect(page.locator('text=7-Day Engineering Evaluation')).toBeVisible();
    await expect(page.locator('text=Investigate → Experiment → Compare → Optimize → Decide')).toBeVisible();
    await expect(page.getByText('Day 1 of 7').first()).toBeVisible();
    await expect(page.getByText('simulations remaining').first()).toBeVisible();
    await expect(page.locator('text=Current Stage')).toBeVisible();

    // ── 2. Verify Primary Action Buttons (CTAs) ──
    await expect(page.locator('text=START ENGINEERING INVESTIGATION')).toBeVisible();
    await expect(page.locator('text=TRY YOUR OWN QUESTION').first()).toBeVisible();
    await expect(page.locator('text=EXPLORE THE PLATFORM')).toBeVisible();

    // ── 4. Verify Engineering Value Proposition ──
    await expect(page.getByText('Instead of manually moving setup values between simulation, telemetry and spreadsheets')).toBeVisible();

    // ── 5. Verify Evaluation Checklist (Backend-Derived) ──
    await expect(page.locator('text=Evaluation Checklist')).toBeVisible();
    await expect(page.locator('text=Investigate the prepared question')).toBeVisible();
    await expect(page.locator('text=Run one experiment')).toBeVisible();
    await expect(page.locator('text=Compare two setups')).toBeVisible();
    await expect(page.locator('text=Run optimization')).toBeVisible();
    await expect(page.locator('text=Create a decision')).toBeVisible();
    await expect(page.locator('text=Try your own question').first()).toBeVisible();

    // ── 3. Verify Guided Hero Workflow Progress Bar ──
    await expect(page.locator('text=TRY THIS FIRST')).toBeVisible();
    await expect(page.locator('text=10-Minute Formula Student Evaluation Path')).toBeVisible();

    // ── STEP 1: Question & Investigation Tab ──
    await expect(page.locator('text=Why is front tire-load variation increasing during aggressive corner entry?').first()).toBeVisible();
    await expect(page.locator('text=1. WHAT IS HAPPENING?')).toBeVisible();
    await expect(page.locator('text=2. EVIDENCE (SYNTHETIC EVALUATION DATA)')).toBeVisible();
    await expect(page.getByText('480 N', { exact: true })).toBeVisible();
    await expect(page.locator('text=3. WHY? (PHYSICAL ROOT CAUSE)')).toBeVisible();
    await expect(page.locator('text=4. WHAT SHOULD WE TEST?')).toBeVisible();

    // ── STEP 2: Navigate to Vehicle & Setups Comparator Tab ──
    const vehicleTab = page.locator('button', { hasText: '2. Vehicle & Setups' });
    await vehicleTab.click();
    await expect(page.locator('text=Multi-Setup Comparative Analysis')).toBeVisible();
    await expect(page.getByText('Front Spring Rate (k_s)')).toBeVisible();
    await expect(page.getByText('35000 N/m').first()).toBeVisible();
    await expect(page.getByText('42000 N/m').first()).toBeVisible();

    // ── STEP 3: Navigate to Hypothesis Experiments Tab ──
    const experimentTab = page.locator('button', { hasText: '3. Hypothesis Experiments' });
    await experimentTab.click();
    await expect(page.locator('text=Hero Hypothesis Experiment')).toBeVisible();
    await expect(page.locator('text=What Improved')).toBeVisible();
    await expect(page.locator('text=What Got Worse')).toBeVisible();
    await expect(page.locator('text=Reproducibility SHA-256')).toBeVisible();

    // ── STEP 4: Navigate to Pareto Optimizer Tab & Run ──
    const optTab = page.locator('button', { hasText: '4. Multi-Objective Pareto Optimizer' });
    await optTab.click();
    const runOptBtn = page.locator('button', { hasText: 'Execute Pareto Optimizer' });
    await expect(runOptBtn).toBeVisible();
    await runOptBtn.click();

    // Verify Pareto frontier results render
    await expect(page.locator('text=Pareto Frontier (Non-Dominated Optimal Setups)')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Recommended Best Compromise Point')).toBeVisible();

    // ── STEP 5: Navigate to Decision Workflow Demo Tab & Create Decision ──
    const decisionTab = page.locator('button', { hasText: '5. Decision Workflow Demo' });
    await decisionTab.click();
    const createDecBtn = page.locator('button', { hasText: 'Create Formal Engineering Decision' });
    await expect(createDecBtn).toBeVisible();
    await createDecBtn.click();

    // Verify formal decision card renders
    await expect(page.locator('text=Audit-Defensible Decision Generated: DEC-FS-9A1B2C')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=SHA-256 Provenance Hash')).toBeVisible();

    // ── STEP 6: Navigate to On-Track Telemetry Tab ──
    const telemTab = page.locator('button', { hasText: '6. On-Track Telemetry' });
    await telemTab.click();
    await expect(page.locator('text=Turn 4 Corner Entry Transient Telemetry')).toBeVisible();
    await expect(page.locator('text=FL Susp Travel')).toBeVisible();
    await expect(page.locator('text=Outer Tire Normal Load')).toBeVisible();

    // ── STEP 7: Customer Discovery Feedback Submission ──
    await expect(page.locator('text=Evaluation Feedback & Customer Discovery')).toBeVisible();
    const valuableInput = page.getByPlaceholder(/Real-time Pareto frontier/i);
    await valuableInput.fill('Immediate correlation between Turn 4 telemetry spike and Pareto trade-off curve.');
    const preventedInput = page.getByPlaceholder(/custom CSV telemetry/i);
    await preventedInput.fill('Wanted custom CSV telemetry import.');
    const submitFeedbackBtn = page.locator('button', { hasText: 'Submit Engineering Feedback' });
    await submitFeedbackBtn.click();
    await expect(page.getByText('Feedback saved to organization')).toBeVisible({ timeout: 10000 });
  });

  test('expired evaluation displays structured limit banner with 4 required sections', async ({ page }) => {
    const expiredTrial = {
      ...mockTrialData,
      status: "EXPIRED",
      days_remaining: 0,
      is_expired: true,
      expires_at: new Date(Date.now() - 3600000).toISOString()
    };

    await page.route('**/auth/me', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: "user-trial-expired",
          email: "evaluator@apex-motorsport.com",
          name: "Alex Evaluator",
          plan: "TRIAL",
          is_trial: true,
          trial_status: "EXPIRED",
          trial_days_remaining: 0,
          redirect_url: "/evaluation",
          onboarding_complete: true,
          created_at: new Date().toISOString(),
          permissions: []
        })
      });
    });

    await page.route('**/trials/status', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(expiredTrial)
      });
    });

    await page.route('**/trials/workspace', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...mockWorkspaceData, trial: expiredTrial })
      });
    });

    await page.goto('/evaluation');

    // Check expiration indicator
    await expect(page.locator('text=Evaluation Expired')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Your evaluation data is preserved according to the trial policy.')).toBeVisible();
    await expect(page.getByRole('link', { name: 'REQUEST EXTENDED EVALUATION' })).toBeVisible();

    // Verify 4-part structured message appears in UI:
    // 1. WHAT LIMIT WAS REACHED
    await expect(page.locator('text=Evaluation Policy Limit Reached')).toBeVisible();
    await expect(page.getByText('7-Day Evaluation Period Expired')).toBeVisible();

    // 2. CURRENT USAGE
    await expect(page.locator('text=CURRENT USAGE')).toBeVisible();

    // 3. WHAT REMAINS AVAILABLE
    await expect(page.locator('text=WHAT REMAINS AVAILABLE')).toBeVisible();
    await expect(page.getByText('Read-only workspace access')).toBeVisible();

    // 4. HOW TO REQUEST CONTINUATION
    await expect(page.locator('text=HOW TO REQUEST CONTINUATION')).toBeVisible();
    await expect(page.locator('text=enterprise@suspensionlab.pro').first()).toBeVisible();
  });
});
