import { test, expect } from '@playwright/test';

test.describe('SuspensionLab PRO - Top Panel & Expandable Status Bar Verification', () => {
  const email = "owner@suspensionlab.pro";
  const password = "FormulaStudent2026!";

  test('verifies clean executive navbar and expandable status bar without scrollbar', async ({ page }) => {
    test.setTimeout(90000);

    // 1. Authenticate or navigate directly
    await page.goto('/auth/login');
    if (await page.locator('#login-email').isVisible()) {
      await page.fill('#login-email', email);
      await page.fill('#login-password', password);
      await page.click('button[type="submit"]');
      await page.waitForTimeout(1500);
    }

    // 2. Navigate to /quarter-car
    await page.goto('/quarter-car');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    // 3. Verify Top Navbar Cleanliness & Lack of Childish Numbering
    const navText = await page.locator('header nav').innerText();
    console.log('[E2E] Navbar contents:', navText.replace(/\n/g, ' '));

    // Ensure no childish numbering prefixes
    expect(navText).not.toContain('1. Setup');
    expect(navText).not.toContain('2. Experiment');
    expect(navText).not.toContain('3. Analyze');
    expect(navText).not.toContain('4. Compare');
    expect(navText).not.toContain('5. Optimize');

    // Ensure executive tabs are present
    expect(navText).toContain('Setup');
    expect(navText).toContain('Experiment');
    expect(navText).toContain('Analyze');
    expect(navText).toContain('Compare');
    expect(navText).toContain('Optimize');
    expect(navText).toContain('Validation');
    expect(navText).toContain('Report');

    // 4. Verify Status Bar Collapsed State & ZERO Horizontal Scrollbar
    const statusBar = page.locator('#workspace-status-bar');
    await expect(statusBar).toBeVisible();

    const isHorizontalOverflowing = await statusBar.evaluate((el) => {
      return el.scrollWidth > el.clientWidth;
    });
    console.log(`[E2E] Status bar horizontal overflow: ${isHorizontalOverflowing}`);
    expect(isHorizontalOverflowing).toBe(false);

    // Capture collapsed screenshot
    await page.screenshot({
      path: 'C:/Users/omaar/.gemini/antigravity/brain/37981109-7efd-4d1e-a49c-e4a1c1274b9d/scratch/navbar_collapsed.png',
      clip: { x: 0, y: 0, width: 1440, height: 380 }
    });
    console.log('[E2E] Collapsed screenshot saved to scratch/navbar_collapsed.png');

    // 5. Test "Analyze" Dropdown
    const analyzeDropdownBtn = page.locator('#analyze-solvers-dropdown-btn');
    await analyzeDropdownBtn.click();
    await page.waitForTimeout(400);

    // Verify dropdown items
    const dropdownHandling = page.locator('#solvers-dropdown a:has-text("Handling Dynamics")');
    await expect(dropdownHandling).toBeVisible();

    await page.screenshot({
      path: 'C:/Users/omaar/.gemini/antigravity/brain/37981109-7efd-4d1e-a49c-e4a1c1274b9d/scratch/navbar_analyze_dropdown.png',
      clip: { x: 0, y: 0, width: 1440, height: 480 }
    });
    console.log('[E2E] Dropdown screenshot saved to scratch/navbar_analyze_dropdown.png');

    // Click outside to dismiss dropdown
    await page.mouse.click(20, 20);
    await page.waitForTimeout(300);

    // 6. Expand the Workspace Status Bar Panel
    const detailsToggle = page.locator('#status-bar-expand-toggle');
    await expect(detailsToggle).toBeVisible();
    await detailsToggle.click();
    await page.waitForTimeout(500);

    // Verify 4-Column Matrix Drawer is displayed
    const expandedDrawer = page.locator('#workspace-status-drawer');
    await expect(expandedDrawer).toBeVisible();

    expect(await expandedDrawer.locator('text=Active Vehicle').first().isVisible()).toBe(true);
    expect(await expandedDrawer.locator('text=Active Setup').first().isVisible()).toBe(true);
    expect(await expandedDrawer.locator('text=Circuit & Tires').first().isVisible()).toBe(true);
    expect(await expandedDrawer.locator('text=Governance & Solver').first().isVisible()).toBe(true);

    // Capture expanded drawer screenshot
    await page.screenshot({
      path: 'C:/Users/omaar/.gemini/antigravity/brain/37981109-7efd-4d1e-a49c-e4a1c1274b9d/scratch/navbar_expanded.png',
      clip: { x: 0, y: 0, width: 1440, height: 580 }
    });
    console.log('[E2E] Expanded panel screenshot saved to scratch/navbar_expanded.png');

    // 7. Test Collapse Button inside drawer
    const collapseBtn = expandedDrawer.locator('button:has-text("Collapse Panel")');
    await expect(collapseBtn).toBeVisible();
    await collapseBtn.click();
    await page.waitForTimeout(500);

    // Verify drawer is no longer visible
    await expect(expandedDrawer).not.toBeVisible();
    console.log('[E2E] Workspace status bar successfully collapsed back!');

    console.log('[E2E] ALL NAVBAR & STATUS BAR CHECKS PASSED PERFECTLY!');
  });
});
