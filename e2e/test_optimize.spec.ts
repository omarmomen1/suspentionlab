import { test, expect } from '@playwright/test';

test.describe('SuspensionLab PRO - Optimize Page Fix Verification', () => {
  const email = "owner@suspensionlab.pro";
  const password = "FormulaStudent2026!";

  test('verifies single status bar and successful Run Batch Candidate Optimization execution', async ({ page }) => {
    test.setTimeout(90000);

    // 1. Log in
    await page.goto('/auth/login');
    if (await page.locator('#login-email').isVisible()) {
      await page.fill('#login-email', email);
      await page.fill('#login-password', password);
      await page.click('button[type="submit"]');
      await page.waitForTimeout(1000);
    }

    // 2. Navigate to /optimize
    console.log('[E2E] Navigating to /optimize...');
    await page.goto('/optimize');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1500);

    // 3. Verify exactly ONE status bar on the page (no duplicate stacked status bars)
    const statusBars = page.locator('#workspace-status-bar');
    const statusBarCount = await statusBars.count();
    console.log(`[E2E] Status bar count on /optimize: ${statusBarCount}`);
    expect(statusBarCount).toBe(1);

    // Screenshot top area showing clean single status bar
    await page.screenshot({
      path: 'C:/Users/omaar/.gemini/antigravity/brain/37981109-7efd-4d1e-a49c-e4a1c1274b9d/scratch/optimize_no_duplicate_bar.png',
      clip: { x: 0, y: 0, width: 1440, height: 420 }
    });

    // 4. Click "Run Batch Candidate Optimization"
    const optimizeBtn = page.locator('#run-batch-optimize-btn');
    await expect(optimizeBtn).toBeVisible();
    console.log('[E2E] Clicking Run Batch Candidate Optimization...');
    await optimizeBtn.click();

    // 5. Verify results appear and success badge is visible
    const successBadge = page.locator('text=Pareto Frontier generated');
    await expect(successBadge).toBeVisible({ timeout: 20000 });
    console.log('[E2E] Pareto Frontier generated success badge is visible!');

    // 6. Verify the 3 Archetype Cards are visible and populated
    const resultsContainer = page.locator('#pareto-results');
    await expect(resultsContainer).toBeVisible();

    const bestCompromiseCard = resultsContainer.locator('span:has-text("Best Compromise")');
    const maxGripCard = resultsContainer.locator('text=MAXIMUM GRIP ARCHETYPE');
    const maxComfortCard = resultsContainer.locator('text=MAXIMUM COMFORT ARCHETYPE');

    await expect(bestCompromiseCard).toBeVisible();
    await expect(maxGripCard).toBeVisible();
    await expect(maxComfortCard).toBeVisible();
    console.log('[E2E] All 3 Archetype Compromise cards are rendered and populated!');

    // 7. Verify scatter plot container is visible
    const plotHeading = page.locator('text=Pareto Frontier: Ride Comfort vs Grip Consistency');
    await expect(plotHeading).toBeVisible();

    // Scroll down to results and take screenshot
    await resultsContainer.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    await page.screenshot({
      path: 'C:/Users/omaar/.gemini/antigravity/brain/37981109-7efd-4d1e-a49c-e4a1c1274b9d/scratch/optimize_verified_results.png',
      clip: { x: 0, y: 300, width: 1440, height: 700 }
    });

    console.log('[E2E] OPTIMIZATION RUN VERIFIED LIVE IN BROWSER!');
  });
});
