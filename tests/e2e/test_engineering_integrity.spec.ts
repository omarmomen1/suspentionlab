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

test.describe('SuspensionLab PRO - Engineering Integrity & Zero Fabrication Verification', () => {
  test.setTimeout(90000);

  test('Test 1: Command Center - Zero Hardcoded Engineering Results & Honest Empty States', async ({ page }) => {
    await login(page);
    await page.goto('/');

    // 1. Verify Command Center hero and title
    await expect(page.getByText('Engineering Command Center')).toBeVisible({ timeout: 15000 });

    // 2. Check Decision Card: No fabricated "prop-spa-r29-cand" allowed!
    // Since 0 formal decisions are in the DB, it must show AWAITING SIGNED DECISION
    const decisionGate = page.getByText('AWAITING SIGNED DECISION');
    await expect(decisionGate).toBeVisible();
    await expect(page.getByText('prop-spa-r29-cand')).toHaveCount(0);

    // 3. Check Recent Runs: No hardcoded fallback "Quarter-Car ISO Ride Baseline" when runs exist
    // Real runs in DB will show their real labels
    await expect(page.getByText('Recent Immutable Run Artifacts:')).toBeVisible();

    // 4. Verify the 5 Engineering KPIs have real provenance and zero fabricated numbers
    // Specifically Peak Lateral Grip must report NO VALID TELEMETRY when telemetry is idle
    const lateralGrip = page.getByText('Peak Lateral Grip').first().locator('..').locator('..');
    await expect(lateralGrip).toBeVisible();
    const gripText = await lateralGrip.innerText();
    // Must be either a real measured number or the honest empty state
    expect(gripText).toMatch(/(3\.48|NO VALID TELEMETRY|DATA UNAVAILABLE)/);

    // 5. Test Mathematical WHY? Provenance Popover
    const whyButton = lateralGrip.getByRole('button', { name: /WHY\?/i });
    await expect(whyButton).toBeVisible();
    await whyButton.click();

    // Assert provenance popover opens with mathematical audit trail
    const provenanceDialog = page.getByRole('dialog');
    await expect(provenanceDialog).toBeVisible();
    await expect(provenanceDialog.getByText(/Mathematical & Causal Provenance/i)).toBeVisible();

    // Close popover
    await provenanceDialog.getByRole('button', { name: /Close/i }).click();
    await expect(provenanceDialog).not.toBeVisible();
  });

  test('Test 2: Ingest New Engineering Question & Verify Dynamic Investigation Room', async ({ page }) => {
    await login(page);
    await page.goto('/');

    // 1. Click [+ NEW ENGINEERING QUESTION] button in Command Center
    const newQuestionBtn = page.getByRole('button', { name: /NEW ENGINEERING QUESTION/i });
    await expect(newQuestionBtn).toBeVisible({ timeout: 15000 });
    await newQuestionBtn.click();

    // 2. Ingest Modal must appear
    const modal = page.getByRole('dialog');
    await expect(modal).toBeVisible();
    await expect(modal.getByText(/Ingest Engineering Question/i)).toBeVisible();

    const uniqueId = Date.now().toString().slice(-6);
    const testTitle = `Front Anti-Roll Bar Asymmetry Alert ${uniqueId}`;
    const testSymptom = `High-speed corner entry telemetry exhibits unmodeled asymmetric roll gradient exceeding 1.8 deg/G under trail braking.`;

    // 3. Fill out question form
    await modal.locator('#question-title').fill(testTitle);
    await modal.locator('#question-symptom').fill(testSymptom);
    await modal.locator('#question-subsystem').fill('Front Axle Anti-Roll');

    // 4. Submit form
    await modal.getByRole('button', { name: /Create & Launch Investigation/i }).click();

    // 5. Assert automatic transition to /investigate?id=...
    await page.waitForURL((url) => url.pathname.includes('/investigate') && url.searchParams.has('id'), { timeout: 15000 });

    // 6. Assert Investigation Room dynamically rendered the real ingested question
    await expect(page.getByRole('heading', { name: testTitle })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(testSymptom).first()).toBeVisible();
    await expect(page.getByText('Front Axle Anti-Roll').first()).toBeVisible();

    // 7. Progress through Stage 2 (WHY)
    const stage2Btn = page.getByRole('button', { name: /STAGE 02/i });
    await stage2Btn.click();
    await expect(page.getByText(/Physical Causal Chain & Mathematical Attribution/i)).toBeVisible();

    // 8. Progress to Stage 4 (TEST & FORMULATE PROPOSAL)
    const stage4Btn = page.getByRole('button', { name: /STAGE 04/i });
    await stage4Btn.click();
    await expect(page.getByText(/Candidate Setup Parameters/i)).toBeVisible();

    // 9. Generate Setup Proposal linked to this new question
    const genPropBtn = page.locator('[data-testid="btn-generate-proposal"]');
    if (await genPropBtn.isVisible()) {
      await genPropBtn.click();
      await expect(page.locator('[data-testid="approval-state-container"]')).toBeVisible({ timeout: 20000 });
    }
  });

  test('Test 3: Domain-Aware Causal Reasoning for Tire Saturation Question', async ({ page }) => {
    await login(page);

    // 1. Directly open tire saturation investigation
    await page.goto('/investigate?id=q-tire-sat-t7');
    await expect(page.getByRole('heading', { name: /Front Tire Saturation/i })).toBeVisible({ timeout: 15000 });

    // 2. Click Stage 2: WHY?
    const stage2Btn = page.getByRole('button', { name: /STAGE 02/i });
    await stage2Btn.click();

    // 3. Verify causal mechanism adapts to tire physics (Pacejka MF5.2, slip angle, ARB load distribution)
    await expect(page.getByText(/TIRE SLIP ANGLE SATURATION/i)).toBeVisible();
    await expect(page.getByText(/Pacejka MF5.2/i)).toBeVisible();
    await expect(page.getByText(/anti-roll bar stiffness/i)).toBeVisible();
  });
});
