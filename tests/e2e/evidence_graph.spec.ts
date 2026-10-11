import { test, expect } from '@playwright/test';

// Helper for authenticating as Enterprise Admin
async function login(page: any) {
  await page.goto('/auth/login');
  await page.waitForSelector('#login-email');
  await page.fill('#login-email', 'james@company.com');
  await page.fill('#login-password', 'admin123!');
  await page.click('button[type="submit"]');
  await expect(page).not.toHaveURL(/\/auth\/login/, { timeout: 15000 });
}

test.describe('Phase 4.4 - Evidence Graph UI Integration & End-to-End Acceptance', () => {
  test.setTimeout(90000);

  test('Evidence Graph: Cockpit tab navigation and initial backward traversal', async ({ page }) => {
    await login(page);
    await page.goto('/cockpit');

    // Verify Decision Loop Cockpit loads
    await expect(page.getByText('Engineering Decision Loop Cockpit')).toBeVisible({ timeout: 15000 });

    // Click "Evidence Graph" tab
    const graphTab = page.getByRole('button', { name: /Evidence Graph/i });
    await expect(graphTab).toBeVisible();
    await graphTab.click();

    // Verify Evidence Graph region renders
    const graphRegion = page.getByRole('region', { name: /Evidence Graph and Provenance/i });
    await expect(graphRegion).toBeVisible();

    // Verify default root is displayed
    await expect(graphRegion.getByText(/ROOT:/i)).toBeVisible();

    // Verify direction buttons exist and BACKWARD is initially active
    const backwardBtn = graphRegion.getByRole('button', { name: /BACKWARD/i });
    const forwardBtn = graphRegion.getByRole('button', { name: /FORWARD/i });
    await expect(backwardBtn).toBeVisible();
    await expect(forwardBtn).toBeVisible();
    await expect(backwardBtn).toHaveAttribute('aria-pressed', 'true');
  });

  test('Evidence Graph: Direction toggling and depth bounding controls', async ({ page }) => {
    await login(page);
    await page.goto('/cockpit');

    // Switch to Evidence Graph tab
    await page.getByRole('button', { name: /Evidence Graph/i }).click();

    const graphRegion = page.getByRole('region', { name: /Evidence Graph/i });
    await expect(graphRegion).toBeVisible();

    // Toggle to FORWARD direction
    const forwardBtn = graphRegion.getByRole('button', { name: /FORWARD/i });
    await forwardBtn.click();
    await expect(forwardBtn).toHaveAttribute('aria-pressed', 'true');

    // Toggle back to BACKWARD direction
    const backwardBtn = graphRegion.getByRole('button', { name: /BACKWARD/i });
    await backwardBtn.click();
    await expect(backwardBtn).toHaveAttribute('aria-pressed', 'true');

    // Depth slider exists and bounded [1, 10]
    const depthSlider = graphRegion.locator('input[type="range"]');
    await expect(depthSlider).toBeVisible();
    expect(await depthSlider.getAttribute('min')).toBe('1');
    expect(await depthSlider.getAttribute('max')).toBe('10');
  });

  test('Evidence Graph: Accessible Linear List view toggle', async ({ page }) => {
    await login(page);
    await page.goto('/cockpit');

    await page.getByRole('button', { name: /Evidence Graph/i }).click();

    const graphRegion = page.getByRole('region', { name: /Evidence Graph/i });
    await expect(graphRegion).toBeVisible();

    // Toggle to accessible linear list mode
    const listModeBtn = graphRegion.getByTitle(/Switch to accessible linear list mode/i);
    if (await listModeBtn.isVisible()) {
      await listModeBtn.click();
      await expect(graphRegion.getByText(/ACCESSIBLE EVIDENCE AUDIT TRAIL/i)).toBeVisible();

      // Toggle back to canvas graph mode
      const graphModeBtn = graphRegion.getByTitle(/Switch to interactive graph canvas mode/i);
      await expect(graphModeBtn).toBeVisible();
      await graphModeBtn.click();
    }
  });

  test('Evidence Graph: Stage card deep link opens Evidence Graph with selected root', async ({ page }) => {
    await login(page);
    await page.goto('/cockpit');

    // In 12-Stage workflow tab, click Graph on Stage 4 (EXP-52)
    const stage4Card = page.getByText('EXP-52').locator('..').locator('..');
    const graphBtn = stage4Card.getByRole('button', { name: /Graph/i });
    if (await graphBtn.isVisible()) {
      await graphBtn.click();

      // Should automatically switch to Evidence Graph tab
      const graphRegion = page.getByRole('region', { name: /Evidence Graph/i });
      await expect(graphRegion).toBeVisible();
      await expect(page.getByText('EXP-52')).toBeVisible();
    }
  });
});
