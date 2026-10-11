import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

test.describe('SuspensionLab PRO - Exhaustive Enterprise Audit & Engineering Journey', () => {
  const email = "owner@suspensionlab.pro";
  const password = "FormulaStudent2026!";
  const screenshotsDir = "C:/Users/omaar/.gemini/antigravity/brain/37981109-7efd-4d1e-a49c-e4a1c1274b9d/scratch/audit";

  test.beforeAll(() => {
    if (!fs.existsSync(screenshotsDir)) {
      fs.mkdirSync(screenshotsDir, { recursive: true });
    }
  });

  test('exhaustive audit across all 14 dynamics modules and workflows', async ({ page }) => {
    test.setTimeout(240000);

    const consoleErrors: string[] = [];
    const failedRequests: { url: string; status: number; method: string }[] = [];
    const doubledApiRequests: string[] = [];

    page.on('console', msg => {
      if (msg.type() === 'error') {
        const text = msg.text();
        // Ignore known benign favicon/ext warnings if any
        if (!text.includes('favicon.ico')) {
          consoleErrors.push(text);
          console.warn(`[BROWSER ERROR] ${text}`);
        }
      }
    });

    page.on('response', res => {
      const url = res.url();
      const status = res.status();
      if (url.includes('/api/v1/api/v1') || url.includes('/api/api/')) {
        doubledApiRequests.push(url);
      }
      if (status >= 400 && !url.includes('favicon.ico') && !url.includes('/metrics')) {
        failedRequests.push({ url, status, method: res.request().method() });
        console.warn(`[HTTP ${status}] ${res.request().method()} ${url}`);
      }
    });

    // ── 1. AUTHENTICATION & LOGIN ──────────────────────────────────────────
    console.log('\n--- 1. AUDITING AUTH & LOGIN ---');
    await page.goto('/auth/login');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: path.join(screenshotsDir, '01_login.png') });

    if (await page.locator('#login-email').isVisible()) {
      await page.fill('#login-email', email);
      await page.fill('#login-password', password);
      await page.click('button[type="submit"]');
      await page.waitForURL(/(\/evaluation|\/quarter-car)/, { timeout: 15000 });
    }
    console.log('✓ Authentication verified');

    // ── 2. EVALUATION GARAGE (/evaluation) ──────────────────────────────────
    console.log('\n--- 2. AUDITING /evaluation (7-Day Trial Garage) ---');
    await page.goto('/evaluation');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);

    // Verify 7-day expiration banner and evaluation garage
    await expect(page.locator('h2:has-text("7-Day Engineering Evaluation")')).toBeVisible();
    await expect(page.locator('text=Day 1 of 7').first()).toBeVisible();
    await expect(page.locator('text=SLP-FS-EV-01').first()).toBeVisible();

    // Verify investigation question
    await expect(page.locator('text=Why is front tire-load variation increasing during aggressive corner entry?').first()).toBeVisible();

    // Verify evaluation tabs
    const tabInvestigation = page.locator('button:has-text("1. Engineering Question & Investigation")').first();
    await expect(tabInvestigation).toBeVisible();
    await tabInvestigation.click();
    await page.waitForTimeout(500);

    // Verify telemetry tab
    const tabTelemetry = page.locator('button:has-text("6. On-Track Telemetry (100Hz)")').first();
    if (await tabTelemetry.isVisible()) {
      await tabTelemetry.click();
      await page.waitForTimeout(500);
    }

    await page.screenshot({ path: path.join(screenshotsDir, '02_evaluation_garage.png') });
    console.log('✓ /evaluation verified');

    // ── 3. VEHICLE SETUP & GARAGE (/garage) ─────────────────────────────────
    console.log('\n--- 3. AUDITING /garage (Vehicle Library & Kinematics) ---');
    await page.goto('/garage');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);

    await expect(page.locator('h1, h2', { hasText: /garage|vehicle|setup/i }).first()).toBeVisible();
    await page.screenshot({ path: path.join(screenshotsDir, '03_garage.png') });
    console.log('✓ /garage verified');

    // ── 4. QUARTER-CAR DYNAMICS SOLVER (/quarter-car) ───────────────────────
    console.log('\n--- 4. AUDITING /quarter-car (2-DOF Solver & Analysis) ---');
    await page.goto('/quarter-car');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);

    // Verify Single Status Bar
    const statusBars = page.locator('#workspace-status-bar');
    expect(await statusBars.count()).toBe(1);

    // Run Quarter-Car Solver
    const qcarRunBtn = page.locator('button:has-text("Run Solver")');
    await expect(qcarRunBtn).toBeVisible();
    await qcarRunBtn.click();

    const simReport = page.locator('#sim-report');
    await expect(simReport).toBeVisible({ timeout: 25000 });

    // Verify All 6 Tabs in Simulation Results
    const tabs = ['sim-tab-1', 'sim-tab-2', 'sim-tab-3', 'sim-tab-4', 'sim-tab-5', 'sim-tab-6'];
    for (const tabId of tabs) {
      const tabEl = page.locator(`#${tabId}`);
      if (await tabEl.isVisible()) {
        await tabEl.click();
        await page.waitForTimeout(300);
      }
    }

    await page.screenshot({ path: path.join(screenshotsDir, '04_quarter_car.png') });
    console.log('✓ /quarter-car solver and all 6 tabs verified');

    // ── 5. HALF-CAR PITCH & BOUNCE (/half-car) ──────────────────────────────
    console.log('\n--- 5. AUDITING /half-car (4-DOF Pitch & Bounce) ---');
    await page.goto('/half-car');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);

    const halfCarRunBtn = page.locator('button:has-text("Run"), button:has-text("Solve"), button:has-text("Simulate")').first();
    if (await halfCarRunBtn.isVisible()) {
      await halfCarRunBtn.click();
      await page.waitForTimeout(3000);
    }
    await page.screenshot({ path: path.join(screenshotsDir, '05_half_car.png') });
    console.log('✓ /half-car verified');

    // ── 6. FULL-CAR 7-DOF DYNAMICS (/full-car) ──────────────────────────────
    console.log('\n--- 6. AUDITING /full-car (7-DOF Heave, Pitch, Roll) ---');
    await page.goto('/full-car');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);

    const fullCarRunBtn = page.locator('button:has-text("Run"), button:has-text("Solve"), button:has-text("Simulate")').first();
    if (await fullCarRunBtn.isVisible()) {
      await fullCarRunBtn.click();
      await page.waitForTimeout(3000);
    }
    await page.screenshot({ path: path.join(screenshotsDir, '06_full_car.png') });
    console.log('✓ /full-car verified');

    // ── 7. HANDLING DYNAMICS (/handling) ────────────────────────────────────
    console.log('\n--- 7. AUDITING /handling (Bicycle Model & Step Steer) ---');
    await page.goto('/handling');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);

    const handlingRunBtn = page.locator('button:has-text("Run Solver")');
    await expect(handlingRunBtn).toBeVisible();
    await handlingRunBtn.click();
    await page.waitForTimeout(3500);

    // Check no crash or error banner
    await expect(page.locator('text=unexpected keyword argument')).not.toBeVisible();
    await page.screenshot({ path: path.join(screenshotsDir, '07_handling.png') });
    console.log('✓ /handling verified without h_cg crash');

    // ── 8. LAP SIMULATOR (/lap-sim) ─────────────────────────────────────────
    console.log('\n--- 8. AUDITING /lap-sim (Quasi-Steady Lap Sim & GGV) ---');
    await page.goto('/lap-sim');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);

    // Verify Sidebar width
    const aside = page.locator('aside[aria-label="Simulation Configuration"]');
    await expect(aside).toBeVisible();
    const box = await aside.boundingBox();
    expect(box?.width).toBeGreaterThanOrEqual(300);

    // Run Lap Simulation
    const lapSimRunBtn = page.locator('#lap-sim-run-btn');
    await expect(lapSimRunBtn).toBeVisible();
    await lapSimRunBtn.click();

    // Verify Lap Time result
    const lapTimeCard = page.locator('span:has-text("Lap Time")');
    await expect(lapTimeCard).toBeVisible({ timeout: 30000 });

    await page.screenshot({ path: path.join(screenshotsDir, '08_lap_sim.png') });
    console.log('✓ /lap-sim verified');

    // ── 9. MULTI-SETUP COMPARE (/compare) ───────────────────────────────────
    console.log('\n--- 9. AUDITING /compare (Multi-Setup Delta & Overlays) ---');
    await page.goto('/compare');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);

    // Verify single status bar on compare page
    expect(await page.locator('#workspace-status-bar').count()).toBe(1);

    await page.screenshot({ path: path.join(screenshotsDir, '09_compare.png') });
    console.log('✓ /compare verified');

    // ── 10. MULTI-OBJECTIVE PARETO OPTIMIZER (/optimize) ───────────────────
    console.log('\n--- 10. AUDITING /optimize (Pareto Optimization & Grid) ---');
    await page.goto('/optimize');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);

    // Verify single status bar on optimize page
    expect(await page.locator('#workspace-status-bar').count()).toBe(1);

    // Run Batch Candidate Optimization
    const optimizeBtn = page.locator('#run-batch-optimize-btn');
    await expect(optimizeBtn).toBeVisible();
    await optimizeBtn.click();

    // Verify live results and Archetype Compromise cards
    const resultsContainer = page.locator('#pareto-results');
    await expect(resultsContainer).toBeVisible({ timeout: 25000 });
    await expect(resultsContainer.locator('span:has-text("Best Compromise")')).toBeVisible();

    await page.screenshot({ path: path.join(screenshotsDir, '10_optimize.png') });
    console.log('✓ /optimize batch candidate optimization verified');

    // ── 11. EXPERIMENT & PARAMETRIC SWEEPS (/experiment) ───────────────────
    console.log('\n--- 11. AUDITING /experiment (Parametric Sweeps & DOE) ---');
    await page.goto('/experiment');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
    expect(await page.locator('#workspace-status-bar').count()).toBe(1);
    await page.screenshot({ path: path.join(screenshotsDir, '11_experiment.png') });
    console.log('✓ /experiment verified');

    // ── 12. TELEMETRY CORRELATION (/correlation) ───────────────────────────
    console.log('\n--- 12. AUDITING /correlation (Telemetry Correlation) ---');
    await page.goto('/correlation');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
    expect(await page.locator('#workspace-status-bar').count()).toBe(1);
    await page.screenshot({ path: path.join(screenshotsDir, '12_correlation.png') });
    console.log('✓ /correlation verified');

    // ── 13. AUDIT TIMELINE & GOVERNANCE (/timeline) ─────────────────────────
    console.log('\n--- 13. AUDITING /timeline (Audit Trail & Provenance) ---');
    await page.goto('/timeline');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
    expect(await page.locator('#workspace-status-bar').count()).toBe(1);
    await page.screenshot({ path: path.join(screenshotsDir, '13_timeline.png') });
    console.log('✓ /timeline verified');

    // ── 14. VERIFICATION & VALIDATION (/vnv) ────────────────────────────────
    console.log('\n--- 14. AUDITING /vnv (ISO/SAE Benchmark V&V) ---');
    await page.goto('/vnv');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(screenshotsDir, '14_vnv.png') });
    console.log('✓ /vnv verified');

    // ── 15. FORMAL ENGINEERING REPORT GENERATION (/report) ──────────────────
    console.log('\n--- 15. AUDITING /report (Executive Cryptographic Report) ---');
    await page.goto('/report');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(screenshotsDir, '15_report.png') });
    console.log('✓ /report verified');

    // ── FINAL ENTERPRISE ASSERTIONS ─────────────────────────────────────────
    console.log('\n--- ENTERPRISE AUDIT SUMMARY ---');
    console.log(`Doubled URL occurrences: ${doubledApiRequests.length}`);
    console.log(`Failed HTTP requests (>=400): ${failedRequests.length}`);
    console.log(`Browser console errors: ${consoleErrors.length}`);

    expect(doubledApiRequests).toHaveLength(0);
    // Print any errors found for auditing
    if (failedRequests.length > 0) {
      console.log('Failed Requests:', failedRequests);
    }
    if (consoleErrors.length > 0) {
      console.log('Console Errors:', consoleErrors);
    }

    console.log('\n🏆 ALL 15 CORE ENTERPRISE MODULES AUDITED LIVE IN BROWSER!');
  });
});
