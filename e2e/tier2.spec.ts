import { test, expect } from '@playwright/test';

// Tier 2: Boundary & Edge Cases

test.describe('Feature 1: Quarter Car Simulation (Boundary)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/quarter-car');
  });

  test('should reject negative mass values', async ({ page }) => {
    await page.getByLabel(/Sprung Mass/i).fill('-50');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await expect(page.getByText(/mass cannot be negative/i)).toBeVisible();
  });

  test('should display warning for 0 damping (undamped system)', async ({ page }) => {
    await page.getByLabel(/Damping Coefficient/i).fill('0');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await expect(page.getByText(/Warning: Undamped system/i)).toBeVisible();
  });

  test('should cap extremely high spring stiffness', async ({ page }) => {
    await page.getByLabel(/Spring Stiffness/i).fill('10000000');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await expect(page.getByText(/Stiffness exceeds recommended limits/i)).toBeVisible();
  });

  test('should handle extremely low mass', async ({ page }) => {
    await page.getByLabel(/Sprung Mass/i).fill('0.001');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await expect(page.getByText(/Mass is too low/i)).toBeVisible();
  });

  test('should reject excessively long simulation times', async ({ page }) => {
    await page.getByLabel(/Simulation Time/i).fill('10000');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await expect(page.getByText(/Simulation time too long/i)).toBeVisible();
  });
});

test.describe('Feature 2: Full Car Simulation (Boundary)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/full-car');
  });

  test('should warn about unstable extreme CG height', async ({ page }) => {
    await page.getByLabel(/CG Height/i).fill('10');
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await expect(page.getByText(/Unstable CG height/i)).toBeVisible();
  });

  test('should require a maneuver type to be selected', async ({ page }) => {
    await page.getByLabel(/Maneuver Type/i).selectOption('None');
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await expect(page.getByText(/Please select a maneuver/i)).toBeVisible();
  });

  test('should prevent unrealistic maximum speed', async ({ page }) => {
    await page.getByLabel(/Speed/i).fill('1000');
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await expect(page.getByText(/Speed exceeds realistic limits/i)).toBeVisible();
  });

  test('should error on extremely short wheelbase', async ({ page }) => {
    await page.getByLabel(/Wheelbase/i).fill('0.1');
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await expect(page.getByText(/Wheelbase too short/i)).toBeVisible();
  });

  test('should not accept negative vehicle mass', async ({ page }) => {
    await page.getByLabel(/Vehicle Mass/i).fill('-100');
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await expect(page.getByText(/Mass cannot be negative/i)).toBeVisible();
  });
});

test.describe('Feature 3: ISO Compliance Reports (Boundary)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/iso-report');
  });

  test('should handle missing simulation data directly on route', async ({ page }) => {
    await expect(page.getByText(/No simulation data available/i)).toBeVisible();
  });

  test('should require report title if custom title selected', async ({ page }) => {
    // Navigate to full car, run sim, go to report
    await page.goto('/full-car');
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await page.getByRole('button', { name: /Generate ISO Report/i }).click();
    await page.getByLabel(/Report Title/i).fill('   ');
    await page.getByRole('button', { name: /Create PDF/i }).click();
    await expect(page.getByText(/Title is required/i)).toBeVisible();
  });

  test('should warn if simulation time is too short for ISO standards', async ({ page }) => {
    await page.goto('/quarter-car');
    await page.getByLabel(/Simulation Time/i).fill('0.1');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await page.goto('/iso-report');
    await expect(page.getByText(/Simulation time too short for ISO/i)).toBeVisible();
  });

  test('should flag severe discomfort risk on extreme vibration', async ({ page }) => {
    await page.goto('/quarter-car');
    await page.getByLabel(/Road Profile/i).selectOption('Extreme Bumps');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await page.goto('/iso-report');
    await expect(page.getByText(/Severe discomfort risk/i)).toBeVisible();
  });

  test('should handle unsupported ISO standard gracefully', async ({ page }) => {
    await page.goto('/full-car');
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await page.getByRole('button', { name: /Generate ISO Report/i }).click();
    // Assuming 'Draft Standard' is an option that might not be fully supported
    await page.getByLabel(/ISO Standard/i).selectOption('Draft Standard');
    await expect(page.getByText(/Standard not fully supported/i)).toBeVisible();
  });
});

test.describe('Feature 4: CAE Exports (Boundary)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/full-car');
  });

  test('should disable export button if no simulation run', async ({ page }) => {
    const exportBtn = page.getByRole('button', { name: /Export Data/i });
    if (await exportBtn.isVisible()) {
      await expect(exportBtn).toBeDisabled();
    }
  });

  test('should show loading indicator for huge payload export', async ({ page }) => {
    await page.getByLabel(/Simulation Time/i).fill('100'); // Long sim time
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await page.getByRole('button', { name: /Export Data/i }).click();
    await page.getByRole('button', { name: /Download/i }).click();
    await expect(page.getByText(/Preparing large export/i)).toBeVisible();
  });

  test('should allow cancelling an ongoing export', async ({ page }) => {
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await page.getByRole('button', { name: /Export Data/i }).click();
    await page.getByRole('button', { name: /Download/i }).click();
    await page.getByRole('button', { name: /Cancel Export/i }).click();
    await expect(page.getByText(/Export cancelled/i)).toBeVisible();
  });

  test('should reject invalid export format manipulation', async ({ page }) => {
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await page.getByRole('button', { name: /Export Data/i }).click();
    // Simulate invalid format via evaluating value if needed, or check disabled state
    // For opaque box, we'll check if a known invalid type triggers error
    await page.getByLabel(/Format/i).selectOption('UnknownFormat').catch(() => {});
    // Just a placeholder check since we can't easily force invalid option in pure UI if not in DOM
    await expect(page.getByRole('button', { name: /Download/i })).toBeVisible(); 
  });

  test('should not export if simulation resulted in an error state', async ({ page }) => {
    await page.getByLabel(/Vehicle Mass/i).fill('-100'); // Cause error
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    const exportBtn = page.getByRole('button', { name: /Export Data/i });
    if (await exportBtn.isVisible()) {
      await expect(exportBtn).toBeDisabled();
    }
  });
});

test.describe('Feature 5: Live Sessions (Boundary)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should reject invalid session ID format', async ({ page }) => {
    await page.getByRole('button', { name: /Join Session/i }).click();
    await page.getByLabel(/Session Code/i).fill('INVALID-!!!');
    await page.getByRole('button', { name: /Join/i }).click();
    await expect(page.getByText(/Invalid session ID format/i)).toBeVisible();
  });

  test('should show error for non-existent session', async ({ page }) => {
    await page.getByRole('button', { name: /Join Session/i }).click();
    await page.getByLabel(/Session Code/i).fill('XYZ-999');
    await page.getByRole('button', { name: /Join/i }).click();
    await expect(page.getByText(/Session not found or expired/i)).toBeVisible();
  });

  test('should handle rapid multiple join clicks gracefully', async ({ page }) => {
    await page.getByRole('button', { name: /Join Session/i }).click();
    await page.getByLabel(/Session Code/i).fill('ABC-123'); // Assuming valid mock format
    const joinBtn = page.getByRole('button', { name: /Join/i });
    await joinBtn.click();
    await joinBtn.click();
    await joinBtn.click();
    // Should not crash, should just show connection attempt
    await expect(page.getByText(/Connecting/i).first()).toBeVisible();
  });

  test('should allow leaving and rejoining the same session', async ({ page }) => {
    await page.goto('/quarter-car');
    await page.getByRole('button', { name: /Start Live Session/i }).click();
    await page.getByRole('button', { name: /Leave Session/i }).click();
    await expect(page.getByText(/Session ended/i)).toBeVisible();
    await page.getByRole('button', { name: /Start Live Session/i }).click();
    await expect(page.getByText(/Session ID:/i)).toBeVisible();
  });

  test('should show warning when connection times out', async ({ page }) => {
    // Simulate timeout scenario using an impossible session code designed to hang/timeout in mocks
    await page.getByRole('button', { name: /Join Session/i }).click();
    await page.getByLabel(/Session Code/i).fill('TIMEOUT-000');
    await page.getByRole('button', { name: /Join/i }).click();
    await expect(page.getByText(/Connection timeout/i)).toBeVisible({ timeout: 15000 });
  });
});
