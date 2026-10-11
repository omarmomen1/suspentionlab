import { test, expect } from '@playwright/test';

// Helper for authenticating as Enterprise Admin
async function login(page: any) {
  await page.goto('/auth/login');
  await page.waitForSelector('#login-email');
  await page.fill('#login-email', 'james@company.com');
  await page.fill('#login-password', 'admin123!');
  await page.click('button[type="submit"]');
  // Wait for login redirection (Next.js client-side navigation)
  await expect(page).not.toHaveURL(/\/auth\/login/, { timeout: 15000 });
}

test.describe('SuspensionLab PRO - Engineering Decision OS Stateful Workflow', () => {
  test.setTimeout(90000);

  test('Test A: Experiment -> Compare Preserves Durable exp_id & Candidate Setup', async ({ page }) => {
    await login(page);

    // 1. Navigate to Experiment Lab
    await page.goto('/experiment');
    await expect(page.getByRole('heading', { name: /One-Click Experiment Builder/i })).toBeVisible({ timeout: 15000 });

    // 2. Wait for experiment execution to complete and show results
    const testInCompareBtn = page.locator('[data-testid="btn-test-in-compare"]');
    await expect(testInCompareBtn).toBeVisible({ timeout: 20000 });

    const href = await testInCompareBtn.getAttribute('href');
    expect(href).toBeTruthy();
    expect(href).toContain('/compare?exp_id=');
    expect(href).toContain('candidate=');

    // 3. Click Test This Change in Compare
    await testInCompareBtn.click();
    await page.waitForURL((url) => url.pathname.includes('/compare') && url.searchParams.has('exp_id'), { timeout: 10000 });

    // 4. Assert Compare page renders without error and displays durable link banner
    await expect(page.locator('[data-testid="structured-error-card"]')).toHaveCount(0);
    const durableBanner = page.locator('[data-testid="durable-experiment-banner"]');
    await expect(durableBanner).toBeVisible({ timeout: 10000 });
    await expect(durableBanner).toContainText('DURABLE EXPERIMENT LINKED:');

    // 5. Verify forward navigation to Multi-Objective Optimizer exists
    const optBtn = page.locator('[data-testid="btn-compare-to-optimize"]');
    await expect(optBtn).toBeVisible();
    const optHref = await optBtn.getAttribute('href');
    expect(optHref).toContain('/optimize?k_s=');
  });

  test('Test B: Optimize -> Experiment Propagates Cloned Candidate & Provenance', async ({ page }) => {
    await login(page);

    // 1. Navigate to Optimizer
    await page.goto('/optimize');
    await expect(page.getByRole('heading', { name: /Multi-Objective Pareto Optimization/i })).toBeVisible({ timeout: 15000 });

    // 2. Find and click "Test Candidate" button in candidate inspector
    const testCandidateBtn = page.locator('[data-testid="btn-test-candidate-inspector"]');
    await expect(testCandidateBtn).toBeVisible({ timeout: 25000 });
    await testCandidateBtn.click();

    // 3. Assert navigation to /experiment with query parameters
    await page.waitForURL((url) => url.pathname.includes('/experiment') && url.searchParams.has('clone_from'), { timeout: 10000 });

    // 4. Assert cloned candidate visual banner is rendered
    const banner = page.locator('[data-testid="cloned-candidate-banner"]');
    await expect(banner).toBeVisible({ timeout: 10000 });
    await expect(banner).toContainText('CLONED OPTIMIZATION CANDIDATE:');
    await expect(banner).toContainText('PROVENANCE LINKED');

    // 5. Assert experiment executes and button to compare appears
    const testInCompareBtn = page.locator('[data-testid="btn-test-in-compare"]');
    await expect(testInCompareBtn).toBeVisible({ timeout: 25000 });
  });

  test('Test C: Investigation -> Governance Approval Sign-Off with HMAC Signature', async ({ page }) => {
    await login(page);

    // 1. Navigate to Investigation
    await page.goto('/investigate');
    await expect(page.getByRole('heading', { name: /Rear Entry Platform Instability/i })).toBeVisible({ timeout: 15000 });

    // 2. Navigate to Stage 4 (Candidate Setup Experiment & Governance Sign-Off)
    const stage4Tab = page.locator('button:has-text("STAGE 04")');
    await stage4Tab.click();

    // 3. Check for active proposal or generate button
    const noProposalCard = page.locator('[data-testid="no-active-proposal"]');
    const approvalContainer = page.locator('[data-testid="approval-state-container"]');

    // Wait for either the approval container or no-proposal card to load
    await expect(approvalContainer.or(noProposalCard)).toBeVisible({ timeout: 20000 });

    if (await noProposalCard.isVisible()) {
      const genBtn = page.locator('[data-testid="btn-generate-proposal"]');
      await genBtn.click();
      await expect(approvalContainer).toBeVisible({ timeout: 35000 });
    }

    // 4. If currently pending sign-off, execute approval
    const approveBtn = page.locator('[data-testid="btn-approve-signoff"]');
    if (await approveBtn.isVisible()) {
      await approveBtn.click();
    }

    // 5. Verify approved state and cryptographic HMAC signature
    const statusBadge = page.locator('[data-testid="approval-status-badge"]');
    await expect(statusBadge).toContainText('APPROVED FOR TRACK USE', { timeout: 15000 });

    const hmacSig = page.locator('[data-testid="approval-hmac-signature"]');
    await expect(hmacSig).toBeVisible();
    await expect(hmacSig).toContainText('HMAC Sig:');
  });

  test('Test D: Zero Silent Fallback - Rejects Corrupted/Non-Existent Experiment ID', async ({ page }) => {
    await login(page);

    // 1. Navigate to Compare with bogus UUID
    await page.goto('/compare?exp_id=00000000-0000-0000-0000-000000000000');

    // 2. Assert StructuredErrorCard appears with 5-part failure disclosure
    const errorCard = page.locator('[data-testid="structured-error-card"]');
    await expect(errorCard).toBeVisible({ timeout: 10000 });
    await expect(errorCard).toContainText('ZERO SILENT FALLBACK ENFORCED');

    // Check all 5 mandatory failure disclosure sections
    await expect(page.locator('[data-testid="error-what-failed"]')).toContainText('00000000-0000-0000-0000-000000000000');
    await expect(page.locator('[data-testid="error-why"]')).toBeVisible();
    await expect(page.locator('[data-testid="error-what-remains-valid"]')).toBeVisible();
    await expect(page.locator('[data-testid="error-what-cannot-be-claimed"]')).toBeVisible();
    await expect(page.locator('[data-testid="error-next-action"]')).toBeVisible();

    // Verify durable experiment banner is NOT displayed
    await expect(page.locator('[data-testid="durable-experiment-banner"]')).toHaveCount(0);
  });

  test('Test E: Zero Silent Fallback - Rejects Invalid Candidate Parameters on Experiment', async ({ page }) => {
    await login(page);

    // 1. Navigate to Experiment with physical bounds violation (negative spring stiffness)
    await page.goto('/experiment?clone_from=CORRUPT_CANDIDATE&k_s=-99999');

    // 2. Assert StructuredErrorCard appears
    const errorCard = page.locator('[data-testid="structured-error-card"]');
    await expect(errorCard).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="error-what-failed"]')).toContainText('CORRUPT_CANDIDATE');
    await expect(page.locator('[data-testid="error-what-failed"]')).toContainText('-99999');
    await expect(page.locator('[data-testid="error-why"]')).toContainText('1,000 ≤ k_s ≤ 500,000 N/m');
  });

});
