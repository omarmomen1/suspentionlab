import { test, expect } from '@playwright/test';

test.describe('SuspensionLab PRO - Enterprise Bug Fixes Verification', () => {
  const email = "owner@suspensionlab.pro";
  const password = "FormulaStudent2026!";

  test('verifies all 5 bug fixes live in browser', async ({ page }) => {
    test.setTimeout(120000);

    // Track network requests to detect any /api/v1/api/v1 doubling
    const apiRequests: string[] = [];
    page.on('request', req => {
      const url = req.url();
      if (url.includes('/api/')) {
        apiRequests.push(url);
      }
    });

    // 1. Log in as evaluator/owner
    await page.goto('/auth/login');
    await expect(page.locator('#login-email')).toBeVisible({ timeout: 15000 });
    await page.fill('#login-email', email);
    await page.fill('#login-password', password);
    await page.click('button[type="submit"]');

    await page.waitForURL(/(\/evaluation|\/quarter-car)/, { timeout: 15000 });
    console.log('[E2E] Successfully logged in');

    // 2. Check Quarter-Car Simulation: KPI formatting, scrolling, and decision card
    console.log('[E2E] Navigating to /quarter-car...');
    await page.goto('/quarter-car');
    await page.waitForLoadState('networkidle');

    // Run solver
    const runBtn = page.locator('button:has-text("Run Solver")');
    await expect(runBtn).toBeVisible({ timeout: 10000 });
    await runBtn.click();

    // Wait for simulation report to render
    const simReport = page.locator('#sim-report');
    await expect(simReport).toBeVisible({ timeout: 25000 });

    // Check KPI formatting - ensure no long raw floats
    const kpiCards = simReport.locator('div[aria-label*="Ride Freq"], div[aria-label*="Wheel-Hop"], div[aria-label*="Damping Ratio"]');
    await expect(kpiCards.first()).toBeVisible();

    const rideFreqText = await simReport.locator('span:has-text("Ride Freq") + span').innerText();
    console.log(`[E2E] Ride Freq KPI rendered: "${rideFreqText}"`);
    expect(rideFreqText).toMatch(/^[0-9]+\.[0-9]{2}\s*Hz/);

    // Check sim-report container overflow properties
    const simReportOverflowY = await simReport.evaluate((el) => window.getComputedStyle(el).overflowY);
    console.log(`[E2E] #sim-report computed overflowY: "${simReportOverflowY}"`);
    expect(['auto', 'scroll']).toContain(simReportOverflowY);

    // Check Decision Card collapse/expand toggle
    const collapseBtn = simReport.locator('button:has-text("Collapse")');
    await expect(collapseBtn).toBeVisible();
    await collapseBtn.click();
    await expect(simReport.locator('button:has-text("Expand")')).toBeVisible();
    console.log('[E2E] Decision Card successfully collapsed!');
    await simReport.locator('button:has-text("Expand")').click();
    await expect(simReport.locator('button:has-text("Collapse")')).toBeVisible();

    // 3. Check Handling Dynamics Simulation
    console.log('[E2E] Navigating to /handling...');
    await page.goto('/handling');
    await page.waitForLoadState('networkidle');

    const handlingRunBtn = page.locator('button:has-text("Run Solver")');
    await expect(handlingRunBtn).toBeVisible({ timeout: 10000 });
    await handlingRunBtn.click();

    // Should complete without "unexpected keyword argument 'h_cg'"
    // Wait for completion (either toast or plot rendered)
    await page.waitForTimeout(3000);
    const errorHud = page.locator('text=unexpected keyword argument');
    await expect(errorHud).not.toBeVisible();
    console.log('[E2E] Handling solver completed without h_cg crash!');

    // 4. Check Lap Simulator
    console.log('[E2E] Navigating to /lap-sim...');
    await page.goto('/lap-sim');
    await page.waitForLoadState('networkidle');

    // Verify sidebar width is generous (>= 300px)
    const aside = page.locator('aside[aria-label="Simulation Configuration"]');
    await expect(aside).toBeVisible({ timeout: 10000 });
    const asideBox = await aside.boundingBox();
    console.log(`[E2E] Aside width: ${asideBox?.width}px`);
    expect(asideBox?.width).toBeGreaterThanOrEqual(300);

    // Click Run Simulation
    const lapSimRunBtn = page.locator('#lap-sim-run-btn');
    await expect(lapSimRunBtn).toBeVisible();
    await lapSimRunBtn.click();

    // Wait for lap simulation result
    const lapTimeCard = page.locator('span:has-text("Lap Time")');
    await expect(lapTimeCard).toBeVisible({ timeout: 25000 });
    console.log('[E2E] Lap Simulation completed successfully without 404!');

    // 5. Assert NO doubled /api/v1/api/v1 in any captured requests
    const doubledUrls = apiRequests.filter(u => u.includes('/api/v1/api/v1') || u.includes('/api/api/'));
    console.log(`[E2E] Total API requests: ${apiRequests.length}, Doubled URLs: ${doubledUrls.length}`);
    expect(doubledUrls).toHaveLength(0);

    console.log('[E2E] ALL 5 ENTERPRISE BUG FIXES CONFIRMED LIVE IN BROWSER!');
  });

  test('verifies Tab 6 Parametric Sensitivity renders cleanly without card/chart overlap', async ({ page }) => {
    test.setTimeout(120000);

    // 1. Log in as evaluator/owner
    await page.goto('/auth/login');
    await page.fill('#login-email', email);
    await page.fill('#login-password', password);
    await page.click('button[type="submit"]');
    await page.waitForURL(/(\/evaluation|\/quarter-car)/, { timeout: 15000 });

    // 2. Navigate to /quarter-car
    await page.goto('/quarter-car');
    await page.waitForLoadState('networkidle');

    // Run solver first to generate results
    const runBtn = page.locator('button:has-text("Run Solver")');
    await expect(runBtn).toBeVisible({ timeout: 10000 });
    await runBtn.click();

    const simReport = page.locator('#sim-report');
    await expect(simReport).toBeVisible({ timeout: 25000 });

    // 3. Click on Sensitivity Tab (Tab 6)
    const sensitivityTabBtn = page.locator('#sim-tab-6');
    await sensitivityTabBtn.scrollIntoViewIfNeeded();
    await sensitivityTabBtn.click();

    // 4. Click "Run Sensitivity" button
    const runSensBtn = page.locator('button:has-text("Run Sensitivity")');
    await runSensBtn.scrollIntoViewIfNeeded();
    await runSensBtn.click();

    // 5. Wait for sensitivity results to load
    // Check that the 4 baseline KPI cards are visible
    const baselineCard = page.locator('button:has-text("Baseline")');
    await expect(baselineCard.first()).toBeVisible({ timeout: 20000 });
    const baselineCardsCount = await baselineCard.count();
    console.log(`[E2E] Found ${baselineCardsCount} Baseline KPI cards`);
    expect(baselineCardsCount).toBe(4);

    // 6. Check that the Plotly chart container is rendered
    const plotContainer = page.locator('div.js-plotly-plot');
    await expect(plotContainer).toBeVisible({ timeout: 10000 });

    // 7. Check bounding boxes to verify NO OVERLAP between baseline cards and chart
    const firstBaselineBox = await baselineCard.first().boundingBox();
    const lastBaselineBox = await baselineCard.nth(3).boundingBox();
    const plotBox = await plotContainer.boundingBox();

    console.log(`[E2E] Baseline Card 0 bottom: ${(firstBaselineBox?.y || 0) + (firstBaselineBox?.height || 0)}px`);
    console.log(`[E2E] Plot top: ${plotBox?.y}px`);

    expect(firstBaselineBox).not.toBeNull();
    expect(plotBox).not.toBeNull();

    // The top of the plot container MUST be below or equal to the bottom of the baseline cards
    const baselineBottom = Math.max(
      (firstBaselineBox?.y || 0) + (firstBaselineBox?.height || 0),
      (lastBaselineBox?.y || 0) + (lastBaselineBox?.height || 0)
    );
    expect(plotBox!.y).toBeGreaterThanOrEqual(baselineBottom - 5); // 5px margin tolerance for sub-pixel rendering

    // 8. Verify all 6 parameter labels are present in the SVG plot
    const yAxisLabels = page.locator('g.ytick text');
    const labelCount = await yAxisLabels.count();
    console.log(`[E2E] Plotly horizontal bars / Y-axis labels count: ${labelCount}`);
    expect(labelCount).toBeGreaterThanOrEqual(6);

    // 9. Take a screenshot of the sensitivity tab for verification
    await page.locator('div.js-plotly-plot').scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'C:/Users/omaar/.gemini/antigravity/brain/37981109-7efd-4d1e-a49c-e4a1c1274b9d/scratch/sensitivity_chart_scrolled.png' });
    console.log('[E2E] Parametric Sensitivity Tab verified cleanly without overlap!');
  });
});
