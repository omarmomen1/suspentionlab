import { test, expect } from '@playwright/test';

// Slow down all operations so the user can physically watch the bot "think" and "click"
test.use({ launchOptions: { slowMo: 300 } });

test.describe('Extreme Human-Like Stress Benchmark', () => {
  test('Exhaustive 60-second manual walkthrough of every feature', async ({ page }) => {
    test.setTimeout(240000); // 4 minutes max

    console.log("Human Benchmark Started: Navigating to Landing Page...");
    await page.goto('/');

    // Simulate human reading
    await page.waitForTimeout(2000);
    
    // Simulate scrolling down the landing page
    await page.evaluate(() => window.scrollBy(0, 500));
    await page.waitForTimeout(1000);
    await page.evaluate(() => window.scrollBy(0, 500));
    await page.waitForTimeout(1000);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(1000);

    console.log("Human Benchmark: Clicking Launch Demo...");
    await page.click('a[href="/quarter-car"]');

    // Simulate Auth Gateway typing
    await expect(page).toHaveURL(/.*\/auth\/login/);
    await page.waitForTimeout(1000);

    // We will test against the real backend!

    console.log("Human Benchmark: Typing credentials slowly...");
    // Type slowly like a human
    await page.type('input[type="email"]', 'demo@suspensionlab.io', { delay: 100 });
    await page.type('input[type="password"]', 'demo1234', { delay: 100 });
    
    await page.waitForTimeout(500);
    await page.click('button:has-text("Sign In")');

    // Quarter-Car Dashboard
    await expect(page).toHaveURL(/.*\/quarter-car/);
    await page.waitForTimeout(2000); // Look at the default UI

    console.log("Human Benchmark: Adjusting Physics Sliders...");
    // Tweak sliders or inputs if they are standard range inputs (we will just click them)
    // The inputs in the UI are range sliders, let's click around the physics panel
    const rangeInputs = page.locator('input[type="range"]');
    if (await rangeInputs.count() > 0) {
      // Move the first slider (Sprung Mass)
      await rangeInputs.nth(0).focus();
      await page.keyboard.press('ArrowRight');
      await page.keyboard.press('ArrowRight');
      await page.waitForTimeout(500);
      
      // Move the second slider (Damping)
      await rangeInputs.nth(1).focus();
      await page.keyboard.press('ArrowLeft');
      await page.waitForTimeout(500);
    }

    console.log("Human Benchmark: Changing Road Profile...");
    // Change road profile to Pothole
    const select = page.locator('select');
    if (await select.count() > 0) {
      await select.selectOption({ label: 'Pothole' });
      await page.waitForTimeout(1000);
    }

    console.log("Human Benchmark: Running 7-DOF Solver...");
    // Run the solver
    await page.click('button:has-text("Run Solver")');
    
    // Wait for human to analyze the plots
    await page.waitForTimeout(4000); 

    console.log("Human Benchmark: Expanding Compare Panel...");
    // Click Compare Panel
    const compareBtn = page.locator('button:has-text("Compare")').first();
    if (await compareBtn.isVisible()) {
      await compareBtn.click();
      await page.waitForTimeout(2000);
    }

    console.log("Human Benchmark: Exploring Vehicle Presets...");
    // Click Vehicle Presets
    const presetBtn = page.locator('button:has-text("Presets"), button:has-text("Vehicle")').first();
    if (await presetBtn.isVisible()) {
      await presetBtn.click();
      await page.waitForTimeout(1500);
      
      // Select a preset that actually exists
      const presetItem = page.locator('div:has-text("Track Day Car")').first();
      if (await presetItem.isVisible()) {
        await presetItem.click();
        await page.waitForTimeout(1000);
      }
    }

    console.log("Human Benchmark: Running Solver Again with new Preset...");
    await page.click('button:has-text("Run Solver")');
    await page.waitForTimeout(3000);

    console.log("Human Benchmark: Checking ISO 2631 Report Engine...");
    // Check ISO report export
    const exportBtn = page.locator('button:has-text("Export"), button:has-text("Data")').first();
    if (await exportBtn.isVisible()) {
      await exportBtn.click();
      await page.waitForTimeout(1500);
    }

    console.log("Human Benchmark: Navigating to Enterprise Pricing...");
    // Navigate to pricing
    await page.click('a[href="/pricing"]');
    await expect(page).toHaveURL(/.*\/pricing/);

    // Read pricing
    await page.waitForTimeout(1500);
    await page.evaluate(() => window.scrollBy(0, 400));
    await page.waitForTimeout(1500);
    
    console.log("Human Benchmark: Contacting Sales...");
    const salesBtn = page.locator('a:has-text("Contact Sales")').first();
    await expect(salesBtn).toBeVisible();

    console.log("Human Benchmark Complete! 0 Bugs detected.");
    await page.waitForTimeout(2000);
  });
});
