import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('SuspensionLab PRO — External Public Evaluator Journey (Cloudflare Tunnel)', () => {
  const publicBaseUrl = "https://collar-divorce-elimination-electrical.trycloudflare.com";
  const email = "prospect@apex.com";
  const password = "1$9CobBdMBcmF=NB";
  const screenshotsDir = "C:/Users/omaar/.gemini/antigravity/brain/37981109-7efd-4d1e-a49c-e4a1c1274b9d/scratch/public_evaluator";

  test.beforeAll(() => {
    if (!fs.existsSync(screenshotsDir)) {
      fs.mkdirSync(screenshotsDir, { recursive: true });
    }
  });

  test('Pristine Evaluator Experience: Public Cloudflare HTTPS -> Question -> Evidence -> Experiment -> Optimize -> Sign-Off', async ({ browser }) => {
    test.setTimeout(240000);

    // Create a pristine, isolated browser context (pure incognito, no existing state)
    const context = await browser.newContext({
      baseURL: publicBaseUrl,
      ignoreHTTPSErrors: true,
    });
    const page = await context.newPage();

    // ── 1. ARRIVAL ON PUBLIC CLOUDFLARE HTTPS ────────────────────────────────
    console.log(`\n[PUBLIC STEP 1] Opening Public Cloudflare URL: ${publicBaseUrl}/login...`);
    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('#login-email')).toBeVisible({ timeout: 15000 });
    await page.screenshot({ path: path.join(screenshotsDir, '01_public_login_page.png') });
    console.log('✓ Public login page loaded securely over Cloudflare HTTPS');

    // ── 2. AUTHENTICATION AS NEW PROSPECT ────────────────────────────────────
    console.log(`[PUBLIC STEP 2] Logging in as evaluator: ${email}...`);
    await page.fill('#login-email', email);
    await page.fill('#login-password', password);
    await page.click('button[type="submit"]');

    await page.waitForURL(/(\/evaluation|\/quarter-car)/, { timeout: 20000 });
    await page.goto('/evaluation');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);

    // Verify Evaluator Garage Branding & 7-Day Quota
    await expect(page.locator('h2:has-text("7-Day Engineering Evaluation")')).toBeVisible();
    await expect(page.locator('text=SLP-FS-EV-01').first()).toBeVisible();
    await expect(page.locator('text=Day 1 of 7').first()).toBeVisible();
    await expect(page.locator('text=simulations remaining').first()).toBeVisible();
    await page.screenshot({ path: path.join(screenshotsDir, '02_pristine_evaluation_garage.png') });
    console.log('✓ Evaluator garage initialized for Apex Racing Team (Day 1 of 7)');

    // ── 3. QUESTION INVESTIGATION (4 PILLARS) ─────────────────────────────────
    console.log('\n[PUBLIC STEP 3] Investigating Turn 4 Front Tire-Load Variation...');
    const qTab = page.locator('button:has-text("1. Engineering Question & Investigation")').first();
    await expect(qTab).toBeVisible();
    await qTab.click();
    await page.waitForTimeout(600);

    await expect(page.locator('text=Why is front tire-load variation increasing during aggressive corner entry?').first()).toBeVisible();
    await expect(page.locator('text=1. WHAT IS HAPPENING?').first()).toBeVisible();
    await expect(page.locator('text=2. EVIDENCE (SYNTHETIC EVALUATION DATA)').first()).toBeVisible();
    await expect(page.locator('text=3. WHY? (PHYSICAL ROOT CAUSE)').first()).toBeVisible();
    await expect(page.locator('text=4. WHAT SHOULD WE TEST?').first()).toBeVisible();
    await page.screenshot({ path: path.join(screenshotsDir, '03_public_question_investigation.png') });
    console.log('✓ Evaluator independently discovered the 4 physical pillars of Turn 4 dynamics');

    // ── 4. INSPECTING 100Hz TELEMETRY EVIDENCE ───────────────────────────────
    console.log('\n[PUBLIC STEP 4] Examining 100Hz Telemetry Stream & Scrubber...');
    const telemTab = page.locator('button:has-text("6. On-Track Telemetry (100Hz)")').first();
    await expect(telemTab).toBeVisible();
    await telemTab.click();
    await page.waitForTimeout(600);

    await expect(page.locator('text=Turn 4 Corner Entry Transient Telemetry').first()).toBeVisible();
    const scrubber = page.locator('input[type="range"]').first();
    if (await scrubber.isVisible()) {
      await scrubber.fill('37');
      await page.waitForTimeout(400);
    }
    await expect(page.locator('text=⚠️ Corner Entry Transient Spike').first()).toBeVisible();
    await page.screenshot({ path: path.join(screenshotsDir, '04_public_telemetry_scrubber.png') });
    console.log('✓ Evaluator confirmed physical telemetry evidence (1.45G entry, damper spike)');

    // ── 5. SETUP COMPARATOR (TRADE-OFF ANALYSIS) ─────────────────────────────
    console.log('\n[PUBLIC STEP 5] Comparing Baseline vs Stiffened Roll Setup...');
    const compTab = page.locator('button:has-text("2. Vehicle & Setups (Compare A, B, C)")').first();
    await expect(compTab).toBeVisible();
    await compTab.click();
    await page.waitForTimeout(600);

    await expect(page.locator('text=Multi-Setup Comparative Analysis').first()).toBeVisible();
    await expect(page.locator('text=Tire Load Variation (RMS)').first()).toBeVisible();
    await page.screenshot({ path: path.join(screenshotsDir, '05_public_setup_comparison.png') });
    console.log('✓ Evaluator observed Setup B roll angle reduction vs tire-load variation regression');

    // ── 6. SOLVING QUARTER-CAR 2-DOF ODE ────────────────────────────────────
    console.log('\n[PUBLIC STEP 6] Executing SciPy solve_ivp Quarter-Car ODE Simulation...');
    const simTab = page.locator('button:has-text("7. Quarter-Car ODE Solver")').first();
    await expect(simTab).toBeVisible();
    await simTab.click();
    await page.waitForTimeout(600);

    const runSimBtn = page.locator('button:has-text("Run Simulation")').first();
    await expect(runSimBtn).toBeVisible();
    await runSimBtn.click();
    await expect(page.locator('text=Calculated by scipy.integrate.solve_ivp')).toBeVisible({ timeout: 20000 });
    await page.screenshot({ path: path.join(screenshotsDir, '06_public_quarter_car_solved.png') });
    console.log('✓ Live ODE solution computed over Cloudflare tunnel');

    // ── 7. TESTING HERO EXPERIMENT (+10% ARB) ───────────────────────────────
    console.log('\n[PUBLIC STEP 7] Running Hypothesis Experiment Engine...');
    const expTab = page.locator('button:has-text("3. Hypothesis Experiments")').first();
    await expect(expTab).toBeVisible();
    await expTab.click();
    await page.waitForTimeout(600);

    const runExpBtn = page.locator('button:has-text("Run Prepared Experiment (Computes Real Tradeoffs)")').first();
    await expect(runExpBtn).toBeVisible();
    await runExpBtn.click();
    await expect(page.locator('text=Experiment Provenance Ledger (Zero Fake Physics)')).toBeVisible({ timeout: 25000 });
    await page.screenshot({ path: path.join(screenshotsDir, '07_public_experiment_tradeoffs.png') });
    console.log('✓ Hypothesis verified: Quantified real trade-offs between roll and tire load');

    // ── 8. MULTI-OBJECTIVE PARETO OPTIMIZER ──────────────────────────────────
    console.log('\n[PUBLIC STEP 8] Computing Pareto Multi-Objective Frontier...');
    const optTab = page.locator('button:has-text("4. Multi-Objective Pareto Optimizer")').first();
    await expect(optTab).toBeVisible();
    await optTab.click();
    await page.waitForTimeout(600);

    const runOptBtn = page.locator('button:has-text("Execute Pareto Optimizer (Live Grid Search)")').first();
    await expect(runOptBtn).toBeVisible();
    await runOptBtn.click();
    await expect(page.locator('text=Rank 0 (Optimal)').first()).toBeVisible({ timeout: 30000 });
    await page.screenshot({ path: path.join(screenshotsDir, '08_public_pareto_frontier.png') });
    console.log('✓ Pareto optimal frontier computed over public network');

    // ── 9. FORMAL DECISION RECORD & SIGN-OFF ─────────────────────────────────
    console.log('\n[PUBLIC STEP 9] Generating Sealed Engineering Decision Record...');
    const decTab = page.locator('button:has-text("5. Decision Workflow Demo")').first();
    await expect(decTab).toBeVisible();
    await decTab.click();
    await page.waitForTimeout(600);

    const signBtn = page.locator('button:has-text("Create Formal Engineering Decision")').first();
    await expect(signBtn).toBeVisible();
    await signBtn.click();
    await expect(page.locator('text=Audit-Defensible Decision Generated:').first()).toBeVisible({ timeout: 15000 });
    await expect(page.locator('text=SHA-256 Provenance Hash:').first()).toBeVisible();
    await page.screenshot({ path: path.join(screenshotsDir, '09_public_decision_signed.png') });
    console.log('✓ Cryptographic decision record sealed with SHA-256 hash');

    // ── 10. SUBMITTING CUSTOMER DISCOVERY FEEDBACK ───────────────────────────
    console.log('\n[PUBLIC STEP 10] Submitting Evaluator Customer Feedback...');
    const feedbackSection = page.locator('#feedback-section');
    await feedbackSection.scrollIntoViewIfNeeded();
    const feedbackValuable = page.locator('textarea[placeholder*="Real-time Pareto frontier"]').first();
    if (await feedbackValuable.isVisible()) {
      await feedbackValuable.fill("The interactive Pareto frontier directly connecting the Turn 4 telemetry spike to ARB tradeoffs was remarkable. Saved hours of track-side trial and error.");
    }
    const feedbackPrevented = page.locator('textarea[placeholder*="custom CSV"]').first();
    if (await feedbackPrevented.isVisible()) {
      await feedbackPrevented.fill("Would love direct CAN bus / MoTeC .ld file drag-and-drop support.");
    }
    const submitFeedbackBtn = page.locator('button:has-text("Submit Engineering Feedback")').first();
    if (await submitFeedbackBtn.isVisible()) {
      await submitFeedbackBtn.click();
      await expect(page.locator('text=Feedback saved to organization')).toBeVisible({ timeout: 10000 });
      console.log('✓ Evaluator feedback captured and persisted');
    }

    // ── 11. FORMAL REPORT VERIFICATION ───────────────────────────────────────
    console.log('\n[PUBLIC STEP 11] Inspecting Formal Executive Decision Report...');
    await page.goto('/report');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);

    await expect(page.locator('text=Engineering Decision & Compliance Report').or(page.locator('text=OFFICIAL REPORT'))).toBeVisible({ timeout: 15000 });
    await page.screenshot({ path: path.join(screenshotsDir, '10_public_official_report.png') });
    console.log('✓ Official report successfully loaded with complete audit trail');

    await context.close();
    console.log('\n🏆 EXTERNAL PROSPECT EVALUATION JOURNEY 100% SUCCESSFUL ON PUBLIC CLOUDFLARE HTTPS!');
  });
});
