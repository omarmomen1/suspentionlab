import { test, expect } from '@playwright/test';

test.describe('SuspensionLab PRO - Exhaustive User Journey', () => {
  test('Complete E2E workflow from Landing to Login, Simulation, and Pricing', async ({ page }) => {
    test.setTimeout(60000); // 60 seconds timeout for exhaustive test

    // 1. Verify Landing Page
    await page.goto('/');
    await expect(page.locator('a[href="/quarter-car"]').first()).toBeVisible();
    await page.click('a[href="/quarter-car"]');

    // 2. Verify Authentication Redirect & Login
    await expect(page).toHaveURL(/.*\/auth\/login/);
    await expect(page.locator('text=Welcome back')).toBeVisible();
    
    // Mock the backend login API to always succeed with an Enterprise user
    await page.route('**/auth/login', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ 
        token: "mock_token", 
        user_id: "123", 
        email: "demo@suspensionlab.io", 
        name: "Demo", 
        plan: "ENTERPRISE", 
        onboarding_complete: true 
      })
    }));
    
    // Use the dev quick-fill button to populate credentials, or type them
    const devFill = page.locator('button:has-text("[DEV] Fill demo credentials")');
    if (await devFill.isVisible()) {
      await devFill.click();
    } else {
      await page.fill('input[type="email"]', 'demo@company.com');
      await page.fill('input[type="password"]', 'demo1234');
    }
    await page.click('button:has-text("Sign In")');

    // 3. Verify Quarter-Car Engineering Dashboard
    await expect(page).toHaveURL(/.*\/quarter-car/);
    
    // The sidebar/header has parameters, but we'll just check for the primary CTA

    // 4. Run the 7-DOF Solver
    const runButton = page.locator('button:has-text("Run Solver")');
    await expect(runButton).toBeEnabled();
    await runButton.click();

    // 5. Navigate to other features (Pricing / Enterprise Checkout)
    await page.click('text=Pricing');
    await expect(page).toHaveURL(/.*\/pricing/);
    await expect(page.locator('text=Enterprise').first()).toBeVisible();

    // Verify subscription button exists
    const subscribeBtn = page.locator('a:has-text("Contact Sales")').first();
    await expect(subscribeBtn).toBeVisible();
  });
});
