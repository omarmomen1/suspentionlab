import { test, expect } from '@playwright/test';

test.describe('Undo/Redo/Reset functionality', () => {
  test('should allow changing a parameter, undoing it, and redoing it', async ({ page }) => {
    // Mock the /auth/me endpoint to return a logged-in user
    await page.route('**/auth/me', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: "mock_user",
          email: "test@example.com",
          name: "Test User",
          plan: "PRO",
          onboarding_complete: true
        })
      });
    });

    page.on('console', msg => console.log('BROWSER CONSOLE:', msg.text()));
    page.on('pageerror', err => console.error('BROWSER ERROR:', err.message));

    // 1. Go to Quarter Car dashboard
    await page.goto('/quarter-car');
    console.log(page.url());
    await page.screenshot({ path: 'debug_screenshot.png' });
    
    // Wait for the UI to settle
    await page.waitForSelector('text=Quarter Car', { timeout: 5000 }).catch(async () => {
       await page.screenshot({ path: 'timeout_debug_screenshot.png' });
       throw new Error(`Timeout, url is ${page.url()}`);
    });
    
    // Check if the Spring Rate input exists and grab its initial value
    const springRateInput = page.locator('label').filter({ hasText: /^Spring Rate$/ }).locator('..').locator('input[type="number"]');
    
    // Wait for it to be visible
    await expect(springRateInput).toBeVisible();
    
    const initialValue = await springRateInput.inputValue();
    
    // 2. Change the parameter
    await springRateInput.fill('35000');
    // Press tab or enter to blur and trigger onChange if needed
    await springRateInput.press('Tab');
    
    // Ensure value is updated
    await expect(springRateInput).toHaveValue('35000');
    
    // 3. Click Undo
    // The button has title="Undo (Ctrl+Z)"
    const undoButton = page.locator('button[title="Undo (Ctrl+Z)"]');
    await page.screenshot({ path: 'debug_before_undo.png' });
    console.log('Value before undo:', await springRateInput.inputValue());
    console.log('Is button enabled?:', await undoButton.isEnabled());
    await expect(undoButton).toBeEnabled();
    await undoButton.click();
    
    // Verify value rolled back
    await expect(springRateInput).toHaveValue(initialValue);
    
    // 4. Click Redo
    // The button has title="Redo (Ctrl+Y)"
    const redoButton = page.locator('button[title="Redo (Ctrl+Y)"]');
    await expect(redoButton).toBeEnabled();
    await redoButton.click();
    
    // Verify value rolled forward
    await expect(springRateInput).toHaveValue('35000');
    
    // 5. Click Reset
    // The button has title="Reset to Defaults"
    const resetButton = page.locator('button[title="Reset to Defaults"]');
    await expect(resetButton).toBeEnabled();
    await resetButton.click();
    
    // Verify value reset to initial
    await expect(springRateInput).toHaveValue(initialValue);
  });
});
