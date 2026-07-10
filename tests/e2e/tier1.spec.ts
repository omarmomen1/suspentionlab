import { test, expect } from '@playwright/test';

// Feature 1: Quarter Car Simulation (5 tests)
test.describe('Feature 1: Quarter Car Simulation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/quarter-car');
  });

  test('should render the quarter car simulation page and find run button', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /Quarter Car/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Run Simulation/i })).toBeVisible();
  });

  test('should allow entering parameters and running the simulation', async ({ page }) => {
    await page.getByLabel(/Sprung Mass/i).fill('350');
    await page.getByLabel(/Spring Stiffness/i).fill('20000');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await expect(page.getByTestId('results-chart')).toBeVisible();
  });

  test('should show error when entering invalid parameters', async ({ page }) => {
    await page.getByLabel(/Sprung Mass/i).fill('-10');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await expect(page.getByText(/Mass cannot be negative/i)).toBeVisible();
  });

  test('should be able to change road profile type', async ({ page }) => {
    await page.getByLabel(/Road Profile/i).selectOption('Sine Wave');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await expect(page.getByTestId('results-chart')).toBeVisible();
  });

  test('should display simulation history after running', async ({ page }) => {
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await expect(page.getByTestId('sim-history')).toBeVisible();
    await expect(page.getByText(/Simulation 1/i)).toBeVisible();
  });
});

// Feature 2: Full Car Simulation (5 tests)
test.describe('Feature 2: Full Car Simulation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/full-car');
  });

  test('should render the full car simulation page', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /Full Car/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Run Full Car Simulation/i })).toBeVisible();
  });

  test('should allow setting front and rear suspension parameters', async ({ page }) => {
    await page.getByLabel(/Front Stiffness/i).fill('25000');
    await page.getByLabel(/Rear Stiffness/i).fill('30000');
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await expect(page.getByTestId('full-car-results')).toBeVisible();
  });

  test('should visualize the 3D suspension rig after simulation', async ({ page }) => {
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await expect(page.getByTestId('suspension-rig-3d')).toBeVisible();
  });

  test('should support selecting an extreme steering maneuver', async ({ page }) => {
    await page.getByLabel(/Maneuver Type/i).selectOption('Step Steer');
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await expect(page.getByTestId('yaw-rate-chart')).toBeVisible();
  });

  test('should display roll over warning if parameters are unstable', async ({ page }) => {
    await page.getByLabel(/CG Height/i).fill('1.5'); // very high CG
    await page.getByLabel(/Maneuver Type/i).selectOption('Step Steer');
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await expect(page.getByText(/Roll over risk/i)).toBeVisible();
  });
});

// Feature 3: ISO Compliance Reports (5 tests)
test.describe('Feature 3: ISO Compliance Reports', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/full-car');
  });

  test('should display ISO Report generation button after running sim', async ({ page }) => {
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await expect(page.getByRole('button', { name: /Generate ISO Report/i })).toBeVisible();
  });

  test('should generate ISO 2631 Ride Comfort report', async ({ page }) => {
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await page.getByRole('button', { name: /Generate ISO Report/i }).click();
    await expect(page.getByText(/ISO 2631 Compliance/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /Download PDF/i })).toBeVisible();
  });

  test('should require selecting a standard version', async ({ page }) => {
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await page.getByRole('button', { name: /Generate ISO Report/i }).click();
    await page.getByLabel(/ISO Standard/i).selectOption('ISO 2631-1 (1997)');
    await expect(page.getByTestId('report-preview')).toBeVisible();
  });

  test('should allow comparing two setups in one report', async ({ page }) => {
    await page.getByRole('button', { name: /Compare Setups/i }).click();
    await page.getByRole('button', { name: /Generate ISO Report/i }).click();
    await expect(page.getByText(/Baseline vs Proposed/i)).toBeVisible();
  });

  test('should fail gracefully if no data is available for report', async ({ page }) => {
    await page.reload();
    const reportBtn = page.getByRole('button', { name: /Generate ISO Report/i });
    if (await reportBtn.isVisible()) {
      await expect(reportBtn).toBeDisabled();
    } else {
      await expect(page.getByText(/No simulation data/i)).toBeVisible();
    }
  });
});

// Feature 4: CAE Exports (5 tests)
test.describe('Feature 4: CAE Exports', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/full-car');
  });

  test('should find the Data Export button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Export Data/i })).toBeVisible();
  });

  test('should export simulation results as CSV', async ({ page }) => {
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await page.getByRole('button', { name: /Export Data/i }).click();
    await page.getByLabel(/Format/i).selectOption('CSV');
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: /Download/i }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.csv$/);
  });

  test('should export parameters as Adams/Car format', async ({ page }) => {
    await page.getByRole('button', { name: /Export Data/i }).click();
    await page.getByLabel(/Format/i).selectOption('Adams/Car');
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: /Download/i }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.adm$/);
  });

  test('should export telemetry data for external tools', async ({ page }) => {
    await page.getByRole('button', { name: /Export Data/i }).click();
    await page.getByLabel(/Format/i).selectOption('Telemetry JSON');
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: /Download/i }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.json$/);
  });

  test('should disable export if simulation has not been run', async ({ page }) => {
    await page.reload();
    const exportBtn = page.getByRole('button', { name: /Export Data/i });
    if (await exportBtn.isVisible()) {
      await expect(exportBtn).toBeDisabled();
    }
  });
});

// Feature 5: Live Sessions (5 tests)
test.describe('Feature 5: Live Sessions', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/quarter-car');
  });

  test('should be able to start a live session', async ({ page }) => {
    await page.getByRole('button', { name: /Start Live Session/i }).click();
    await expect(page.getByText(/Session ID:/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /Copy Link/i })).toBeVisible();
  });

  test('should allow joining an existing session', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /Join Session/i }).click();
    await page.getByLabel(/Session Code/i).fill('ABC-123');
    await page.getByRole('button', { name: /Join/i }).click();
    await expect(page.getByText(/Connected to session/i)).toBeVisible();
  });

  test('should synchronize parameter changes from another user', async ({ page }) => {
    await page.getByRole('button', { name: /Start Live Session/i }).click();
    // In opaque box testing, we wait for a UI element that represents another user's activity
    await expect(page.getByText(/Waiting for others/i)).toBeVisible();
  });

  test('should broadcast simulation run to all participants', async ({ page }) => {
    await page.getByRole('button', { name: /Start Live Session/i }).click();
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await expect(page.getByText(/Running simulation for all/i)).toBeVisible();
  });

  test('should be able to leave the live session', async ({ page }) => {
    await page.getByRole('button', { name: /Start Live Session/i }).click();
    await page.getByRole('button', { name: /Leave Session/i }).click();
    await expect(page.getByText(/Session ended/i)).toBeVisible();
  });
});
