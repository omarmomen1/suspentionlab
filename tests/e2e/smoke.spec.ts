import { test, expect, Page } from '@playwright/test';

/**
 * smoke.spec.ts (Wave 6, prompt section 3)
 * E2E smoke gate: sign-in, desktop + 390px mobile nav, and the core solver
 * routes (/kinematics, /quarter-car, /lap-sim, /cae, /investigate) plus
 * /report PDF export. Runs in the existing e2e-playwright CI job.
 */

const SMOKE_ROUTES = [
  '/kinematics',
  '/quarter-car',
  '/lap-sim',
  '/cae',
  '/investigate',
] as const;

async function loginAsEnterpriseAdmin(page: Page) {
  await page.goto('/auth/login');
  await page.waitForSelector('#login-email');
  await page.fill('#login-email', 'james@company.com');
  await page.fill('#login-password', 'admin123!');
  await page.getByRole('button', { name: /sign in|log in/i }).click();
  await expect(page).not.toHaveURL(/\/auth\/login/, { timeout: 15000 });
}

async function expectPageHealthy(page: Page, route: string) {
  const response = await page.goto(route);
  expect(response?.status(), `${route} should return 200`).toBe(200);
  // No Next.js error overlay / error boundary
  await expect(page.locator('#__next-build-watcher')).toHaveCount(0);
  await expect(page.getByText(/application error|something went wrong/i)).toHaveCount(0);
  // Page has meaningful content
  await expect(page.locator('main, [role="main"], body').first()).toBeVisible();
}

test.describe('E2E Smoke Gate', () => {
  test('sign-in flow authenticates and lands off the login page', async ({ page }) => {
    await loginAsEnterpriseAdmin(page);
  });

  test('desktop nav renders and core solver routes load', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginAsEnterpriseAdmin(page);
    // Desktop navbar is visible at this width
    const nav = page.locator('nav').first();
    await expect(nav).toBeVisible();
    for (const route of SMOKE_ROUTES) {
      await expectPageHealthy(page, route);
    }
  });

  test('mobile (390px) nav drawer opens and routes load', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loginAsEnterpriseAdmin(page);
    await page.goto('/');
    // Open the mobile drawer via the hamburger (Menu icon button)
    const menuButton = page.getByRole('button', { name: /menu|open navigation|navigation/i }).first();
    await menuButton.click();
    // Drawer should expose at least one navigation link
    const drawerLink = page.locator('a[href="/kinematics"]').first();
    await expect(drawerLink).toBeVisible({ timeout: 5000 });
    // Escape closes the drawer
    await page.keyboard.press('Escape');
    // Core route still loads at mobile width
    await expectPageHealthy(page, '/quarter-car');
  });

  test('/report produces a valid non-empty PDF export', async ({ page }) => {
    await loginAsEnterpriseAdmin(page);
    await page.goto('/report');
    const downloadButton = page.getByRole('button', { name: /download|export.*pdf|pdf/i }).first();
    await expect(downloadButton).toBeVisible({ timeout: 15000 });
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 60000 }),
      downloadButton.click(),
    ]);
    const path = await download.path();
    expect(path).toBeTruthy();
    const fs = await import('fs');
    const size = fs.statSync(path!).size;
    expect(size, 'exported PDF must be non-empty').toBeGreaterThan(0);
    // A real PDF starts with %PDF
    const head = Buffer.alloc(4);
    const fd = fs.openSync(path!, 'r');
    fs.readSync(fd, head, 0, 4, 0);
    fs.closeSync(fd);
    expect(head.toString('latin1')).toBe('%PDF');
  });
});
