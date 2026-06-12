import { test, expect } from '@playwright/test';

// Tier 3: Cross-Feature Interactions

test.describe('Tier 3: Cross-Feature Interactions', () => {
  test('Interaction 1: Quarter Car + ISO Report', async ({ page }) => {
    await page.goto('/quarter-car');
    await page.getByLabel(/Sprung Mass/i).fill('400');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await page.goto('/iso-report');
    await expect(page.getByText(/Quarter Car/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /Generate ISO Report/i })).toBeVisible();
  });

  test('Interaction 2: Full Car + Live Session', async ({ page }) => {
    await page.goto('/full-car');
    await page.getByRole('button', { name: /Start Live Session/i }).click();
    await expect(page.getByText(/Session ID:/i)).toBeVisible();
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await expect(page.getByText(/Running simulation for all/i)).toBeVisible();
  });

  test('Interaction 3: CAE Export during Live Session', async ({ page }) => {
    await page.goto('/quarter-car');
    await page.getByRole('button', { name: /Start Live Session/i }).click();
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await page.getByRole('button', { name: /Export Data/i }).click();
    await page.getByRole('button', { name: /Download/i }).click();
    await expect(page.getByText(/Exporting session data/i)).toBeVisible();
  });

  test('Interaction 4: Quarter Car + CAE Export', async ({ page }) => {
    await page.goto('/quarter-car');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await page.getByRole('button', { name: /Export Data/i }).click();
    await page.getByLabel(/Format/i).selectOption('Adams/Car');
    await expect(page.getByRole('button', { name: /Download/i })).toBeVisible();
  });

  test('Interaction 5: ISO Report during Live Session', async ({ page }) => {
    await page.goto('/full-car');
    await page.getByRole('button', { name: /Start Live Session/i }).click();
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await page.getByRole('button', { name: /Generate ISO Report/i }).click();
    await expect(page.getByText(/Shared Session Report/i)).toBeVisible();
  });
});

// Tier 4: Real-World Scenarios

test.describe('Tier 4: Real-World Scenarios', () => {
  test('Scenario 1: Complete workflow (Quarter Car -> CAE -> ISO)', async ({ page }) => {
    await page.goto('/quarter-car');
    // Run Sim
    await page.getByLabel(/Spring Stiffness/i).fill('25000');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await expect(page.getByTestId('results-chart')).toBeVisible();
    
    // Export CAE
    await page.getByRole('button', { name: /Export Data/i }).click();
    await page.getByLabel(/Format/i).selectOption('CSV');
    await page.getByRole('button', { name: /Download/i }).click();
    
    // Generate ISO
    await page.goto('/iso-report');
    await page.getByRole('button', { name: /Generate ISO Report/i }).click();
    await expect(page.getByText(/ISO 2631 Compliance/i)).toBeVisible();
  });

  test('Scenario 2: Live collaborative tuning of Full car sim', async ({ page }) => {
    await page.goto('/full-car');
    await page.getByRole('button', { name: /Start Live Session/i }).click();
    await expect(page.getByText(/Session ID:/i)).toBeVisible();
    
    // Tune parameter
    await page.getByLabel(/Front Stiffness/i).fill('30000');
    
    // Sim run broadcast
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    await expect(page.getByText(/Running simulation for all/i)).toBeVisible();
    await expect(page.getByTestId('suspension-rig-3d')).toBeVisible();
  });

  test('Scenario 3: Stress testing rapid CAE exports during live session', async ({ page }) => {
    await page.goto('/full-car');
    await page.getByRole('button', { name: /Start Live Session/i }).click();
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    
    // Rapid exports
    await page.getByRole('button', { name: /Export Data/i }).click();
    const downloadBtn = page.getByRole('button', { name: /Download/i });
    await downloadBtn.click();
    await downloadBtn.click();
    await downloadBtn.click();
    
    await expect(page.getByText(/Export queued/i).first()).toBeVisible();
  });

  test('Scenario 4: ISO reports for edge-case full car parameters', async ({ page }) => {
    await page.goto('/full-car');
    // Edge case: Very high speed, rough road (if available) or extreme stiffness
    await page.getByLabel(/Speed/i).fill('200'); 
    await page.getByLabel(/Front Stiffness/i).fill('100000');
    await page.getByRole('button', { name: /Run Full Car Simulation/i }).click();
    
    await page.goto('/iso-report');
    await page.getByRole('button', { name: /Generate ISO Report/i }).click();
    // Check for extreme discomfort or failing standard
    await expect(page.getByText(/Not Compliant/i)).toBeVisible();
  });

  test('Scenario 5: End-to-end suspension tuning lifecycle', async ({ page }) => {
    await page.goto('/quarter-car');
    
    // Initial Sim
    await page.getByLabel(/Spring Stiffness/i).fill('15000');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await expect(page.getByText(/Simulation 1/i)).toBeVisible();
    
    // Tune
    await page.getByLabel(/Spring Stiffness/i).fill('20000');
    await page.getByRole('button', { name: /Run Simulation/i }).click();
    await expect(page.getByText(/Simulation 2/i)).toBeVisible();
    
    // Compare in Report
    await page.goto('/iso-report');
    await page.getByRole('button', { name: /Compare Setups/i }).click();
    await page.getByRole('button', { name: /Generate ISO Report/i }).click();
    await expect(page.getByText(/Baseline vs Proposed/i)).toBeVisible();
  });
});
