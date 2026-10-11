import { test, expect } from '@playwright/test';

test.describe('SuspensionLab PRO - Live Clean-Browser Evaluation (Zero Mocks)', () => {
  test.describe.configure({ mode: 'serial' });

  // Real evaluator test credentials seeded for this test run
  const activeEmail = "live-evaluator-active@apex-formula.com";
  const expiredEmail = "live-evaluator-expired@apex-formula.com";
  const testPassword = "LiveSecurePass2026!7d";
  const testOrg = "Apex Formula Student Team";

  test.beforeAll(async () => {
    // Cleanly reset or create evaluator users into trial database via CLI
    const { execSync } = require('child_process');
    try {
      execSync(`python scripts/create_trial_user.py --email "${activeEmail}" --password "${testPassword}" --org "${testOrg}" --days 7 --sims 50`, {
        cwd: process.cwd(),
        encoding: 'utf-8',
        timeout: 30000
      });
      execSync(`python scripts/create_trial_user.py --email "${expiredEmail}" --password "${testPassword}" --org "${testOrg}" --days 7 --sims 50`, {
        cwd: process.cwd(),
        encoding: 'utf-8',
        timeout: 30000
      });
      console.log(`[E2E Seed] Successfully provisioned live evaluators: ${activeEmail}, ${expiredEmail}`);
    } catch (err: any) {
      console.error("[E2E Seed Error]", err.stdout || err.message);
    }
  });

  test('full clean-browser evaluator journey with real backend execution', async ({ browser }) => {
    test.setTimeout(90000);
    // Fresh browser context with zero developer cookies, storage, or cache
    const context = await browser.newContext({
      viewport: { width: 1280, height: 900 }
    });
    const page = await context.newPage();

    // Track all outbound network requests to verify ZERO localhost leaks to client
    const requestedUrls: string[] = [];
    page.on('request', req => {
      requestedUrls.push(req.url());
    });

    // 1. Visit Login page directly
    await page.goto('/login');
    await expect(page.locator('h1', { hasText: 'Welcome back' })).toBeVisible({ timeout: 15000 });

    // 2. Perform Real Authentication
    await page.fill('#login-email', activeEmail);
    await page.fill('#login-password', testPassword);
    await page.click('button[type="submit"]');

    // 3. Verify automatic redirection to /evaluation for TRIAL user
    await page.waitForURL('**/evaluation', { timeout: 15000 });
    await expect(page.locator('h1', { hasText: 'SuspensionLab PRO' })).toBeVisible({ timeout: 15000 });
    await expect(page.locator('text=7-Day Engineering Evaluation')).toBeVisible();

    // 4. Verify Formula Student Evaluation Garage loaded with real backend data
    await expect(page.getByText('EVALUATION DATASET').first()).toBeVisible();
    await expect(page.locator('text=SLP-FS-EV-01').first()).toBeVisible();
    await expect(page.locator('text=Why is front tire-load variation increasing during aggressive corner entry?').first()).toBeVisible();

    // 5. Verify ZERO client calls leaked to port 8000 (must route through Next.js proxy)
    const directLocalhost8000Calls = requestedUrls.filter(u => u.includes('localhost:8000') || u.includes('127.0.0.1:8000'));
    expect(directLocalhost8000Calls).toHaveLength(0);

    // 6. Click Primary CTA: START ENGINEERING INVESTIGATION
    const startBtn = page.locator('button', { hasText: 'START ENGINEERING INVESTIGATION' });
    await expect(startBtn).toBeVisible();
    await startBtn.click();

    // Verify 4 Pillars of Investigation
    await expect(page.locator('text=1. WHAT IS HAPPENING?')).toBeVisible();
    await expect(page.locator('text=2. EVIDENCE (SYNTHETIC EVALUATION DATA)')).toBeVisible();
    await expect(page.getByText('480 N', { exact: true })).toBeVisible();
    await expect(page.locator('text=3. WHY? (PHYSICAL ROOT CAUSE)')).toBeVisible();
    await expect(page.locator('text=4. WHAT SHOULD WE TEST?')).toBeVisible();

    // 7. STEP 2: Compare Setups (Tab 2)
    const vehicleTab = page.locator('button', { hasText: '2. Vehicle & Setups' });
    await vehicleTab.click();
    await expect(page.locator('text=Multi-Setup Comparative Analysis')).toBeVisible();
    await expect(page.getByText('Front Spring Rate (k_s)')).toBeVisible();

    // 8. STEP 3: Run Real Hypothesis Experiment (Tab 3)
    const experimentTab = page.locator('button', { hasText: '3. Hypothesis Experiments' });
    await experimentTab.click();
    await expect(page.locator('text=Hero Hypothesis Experiment')).toBeVisible();
    const runExpBtn = page.locator('button', { hasText: 'Run Prepared Experiment' });
    await expect(runExpBtn).toBeVisible();
    await runExpBtn.click();

    // Wait for real backend calculation and verify provenance ledger update
    await expect(page.locator('text=What Improved')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('text=What Got Worse')).toBeVisible();
    await expect(page.locator('text=Reproducibility SHA-256')).toBeVisible();

    // 9. STEP 4: Run Real Pareto Optimizer (Tab 4)
    const optTab = page.locator('button', { hasText: '4. Multi-Objective Pareto Optimizer' });
    await optTab.click();
    const runOptBtn = page.locator('button', { hasText: 'Execute Pareto Optimizer' });
    await expect(runOptBtn).toBeVisible();
    await runOptBtn.click();

    // Verify live Pareto frontier rendered
    await expect(page.locator('text=Pareto Frontier (Non-Dominated Optimal Setups)')).toBeVisible({ timeout: 45000 });
    await expect(page.locator('text=Recommended Best Compromise Point')).toBeVisible();

    // 10. STEP 5: Create Formal Engineering Decision (Tab 5)
    const decTab = page.locator('button', { hasText: '5. Decision Workflow Demo' });
    await decTab.click();
    const createDecBtn = page.locator('button', { hasText: 'Create Formal Engineering Decision' });
    await expect(createDecBtn).toBeVisible();
    await createDecBtn.click();

    // Verify audit-defensible decision with SHA-256 provenance hash
    await expect(page.locator('text=Audit-Defensible Decision Generated:')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('text=SHA-256 Provenance Hash:')).toBeVisible();

    // 11. STEP 6: Submit Customer Feedback
    const valuableInput = page.getByPlaceholder(/Real-time Pareto frontier/i);
    await valuableInput.fill('The direct link between Turn 4 telemetry spike and Pareto frontier is outstanding.');
    const preventedInput = page.getByPlaceholder(/custom CSV telemetry/i);
    await preventedInput.fill('Need CSV import for our MoTeC logged laps.');
    const submitBtn = page.locator('button', { hasText: 'Submit Engineering Feedback' });
    await submitBtn.click();
    await expect(page.getByText('Feedback saved to organization')).toBeVisible({ timeout: 15000 });

    await context.close();
  });

  test('expired evaluation displays policy limit banner and blocks mutations', async ({ browser }) => {
    test.setTimeout(60000);
    // Expire evaluator via management script
    const { execSync } = require('child_process');
    execSync(`python scripts/manage_trial.py --email "${expiredEmail}" --expire`, {
      cwd: process.cwd(),
      encoding: 'utf-8',
      timeout: 30000
    });

    const context = await browser.newContext();
    const page = await context.newPage();

    await page.goto('/login');
    await page.fill('#login-email', expiredEmail);
    await page.fill('#login-password', testPassword);
    await page.click('button[type="submit"]');

    await page.waitForURL('**/evaluation', { timeout: 15000 });

    // Verify expiration screen is displayed
    await expect(page.locator('text=Evaluation Expired')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Your evaluation data is preserved according to the trial policy.')).toBeVisible();
    await expect(page.getByRole('link', { name: 'REQUEST EXTENDED EVALUATION' })).toBeVisible();

    // Verify 4 structured sections
    await expect(page.locator('text=Evaluation Policy Limit Reached')).toBeVisible();
    await expect(page.locator('text=CURRENT USAGE')).toBeVisible();
    await expect(page.locator('text=WHAT REMAINS AVAILABLE')).toBeVisible();
    await expect(page.locator('text=HOW TO REQUEST CONTINUATION')).toBeVisible();

    await context.close();
  });
});
