import { test, expect } from '@playwright/test';

test.describe('Evaluator #1 Personal Acceptance Test (Zero Dev Context)', () => {
  const publicUrl = "https://many-wombats-take.loca.lt";
  const userEmail = "evaluator1@formula-student-racing.org";
  const userPassword = "ylF*8kX2MU0d#Z73";

  test('independent discovery workflow through public HTTPS tunnel', async ({ browser }) => {
    test.setTimeout(90000);

    // Fresh, completely clean browser context with bypass header for localtunnel
    const context = await browser.newContext({
      extraHTTPHeaders: {
        'bypass-tunnel-reminder': 'true',
      },
      viewport: { width: 1280, height: 900 },
    });
    const page = await context.newPage();

    console.log(`[Evaluator #1] Accessing public HTTPS entrypoint: ${publicUrl}/auth/login`);
    await page.goto(`${publicUrl}/auth/login`);

    // 1. Discover Login Screen
    await expect(page.locator('h1', { hasText: 'Welcome back' })).toBeVisible({ timeout: 20000 });
    console.log('[Evaluator #1] Successfully loaded login page via public tunnel.');

    // 2. Authenticate
    await page.fill('#login-email', userEmail);
    await page.fill('#login-password', userPassword);
    await page.click('button[type="submit"]');

    // 3. Arrive at Evaluation Landing
    await page.waitForURL('**/evaluation', { timeout: 20000 });
    await expect(page.locator('h1', { hasText: 'SuspensionLab PRO' })).toBeVisible({ timeout: 15000 });
    await expect(page.locator('text=7-Day Engineering Evaluation')).toBeVisible();
    await expect(page.locator('text=SLP-FS-EV-01').first()).toBeVisible();
    console.log('[Evaluator #1] Landed on Evaluation Workspace. Preloaded vehicle SLP-FS-EV-01 confirmed.');

    // 4. Discover Question
    await expect(page.locator('text=Why is front tire-load variation increasing during aggressive corner entry?').first()).toBeVisible();
    console.log('[Evaluator #1] Discovered engineering question.');

    // 5. Click Primary CTA: START ENGINEERING INVESTIGATION
    const startBtn = page.locator('button', { hasText: 'START ENGINEERING INVESTIGATION' });
    await expect(startBtn).toBeVisible();
    await startBtn.click();

    // 6. Discover Evidence & Root Cause
    await expect(page.locator('text=1. WHAT IS HAPPENING?')).toBeVisible();
    await expect(page.locator('text=2. EVIDENCE (SYNTHETIC EVALUATION DATA)')).toBeVisible();
    await expect(page.getByText('480 N', { exact: true })).toBeVisible();
    await expect(page.locator('text=3. WHY? (PHYSICAL ROOT CAUSE)')).toBeVisible();
    await expect(page.locator('text=4. WHAT SHOULD WE TEST?')).toBeVisible();
    console.log('[Evaluator #1] Discovered 4 pillars of investigation with 480 N peak variation evidence.');

    // 7. Compare Setups (Tab 2)
    const vehicleTab = page.locator('button', { hasText: '2. Vehicle & Setups' });
    await vehicleTab.click();
    await expect(page.locator('text=Multi-Setup Comparative Analysis')).toBeVisible();
    await expect(page.getByText('Front Spring Rate (k_s)')).toBeVisible();
    console.log('[Evaluator #1] Discovered Setup A vs B vs C comparison.');

    // 8. Run Experiment (Tab 3)
    const experimentTab = page.locator('button', { hasText: '3. Hypothesis Experiments' });
    await experimentTab.click();
    const runExpBtn = page.locator('button', { hasText: 'Run Prepared Experiment' });
    await expect(runExpBtn).toBeVisible();
    await runExpBtn.click();

    await expect(page.locator('text=What Improved').first()).toBeVisible({ timeout: 20000 });
    await expect(page.locator('text=What Got Worse').first()).toBeVisible();
    await expect(page.locator('text=Reproducibility SHA-256').first()).toBeVisible();
    await expect(runExpBtn).toBeEnabled({ timeout: 20000 });
    console.log('[Evaluator #1] Executed experiment. Discovered trade-offs and reproducibility hash.');

    // 9. Run Pareto Optimizer (Tab 4)
    const optTab = page.locator('button', { hasText: '4. Multi-Objective Pareto Optimizer' });
    await optTab.click();
    const runOptBtn = page.locator('button', { hasText: 'Execute Pareto Optimizer' });
    await expect(runOptBtn).toBeVisible();
    await runOptBtn.click();

    await expect(page.locator('text=Pareto Frontier (Non-Dominated Optimal Setups)')).toBeVisible({ timeout: 30000 });
    await expect(page.locator('text=Recommended Best Compromise Point')).toBeVisible();
    await expect(runOptBtn).toBeEnabled({ timeout: 30000 });
    console.log('[Evaluator #1] Discovered live non-dominated Pareto frontier and recommended knee point.');

    // 10. Create Decision (Tab 5)
    const decTab = page.locator('button', { hasText: '5. Decision Workflow Demo' });
    await decTab.click();
    const createDecBtn = page.locator('button', { hasText: 'Create Formal Engineering Decision' });
    await expect(createDecBtn).toBeVisible();
    await createDecBtn.click();

    await expect(page.locator('text=Audit-Defensible Decision Generated:').first()).toBeVisible({ timeout: 15000 });
    await expect(page.locator('text=SHA-256 Provenance Hash:').first()).toBeVisible();
    console.log('[Evaluator #1] Generated formal decision record with SHA-256 provenance hash.');

    // 11. Submit Customer Discovery Feedback
    const valuableInput = page.getByPlaceholder(/Real-time Pareto frontier/i);
    await valuableInput.fill('Evaluator #1: Seamless transition from Turn 4 telemetry evidence to Pareto compromise point.');
    const preventedInput = page.getByPlaceholder(/custom CSV telemetry/i);
    await preventedInput.fill('Evaluator #1: Ready for live vehicle data import.');
    const submitBtn = page.locator('button', { hasText: 'Submit Engineering Feedback' });
    await submitBtn.click();
    await expect(page.getByText('Feedback saved to organization')).toBeVisible({ timeout: 15000 });
    console.log('[Evaluator #1] Submitted customer feedback successfully. Acceptance test complete!');

    await context.close();
  });
});
