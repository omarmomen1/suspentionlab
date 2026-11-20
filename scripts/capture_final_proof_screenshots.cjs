const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function capture() {
  const screenshotsDir = path.resolve(__dirname, '..', '_audit_export', 'screenshots');
  if (!fs.existsSync(screenshotsDir)) {
    fs.mkdirSync(screenshotsDir, { recursive: true });
  }

  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }
  });
  const page = await context.newPage();

  console.log('1. Logging in at /auth/login...');
  await page.goto('https://suspensionlab-studio.vercel.app/auth/login', { waitUntil: 'networkidle', timeout: 45000 });
  await page.fill('#login-email', 'testuser@suspensionlab.com');
  await page.fill('#login-password', 'SuspensionLab2026!#');
  await page.click('button[type="submit"]');
  await page.waitForTimeout(3000);

  // --------------------------------------------------------------------------
  // Screenshot 05: Navbar clean on /lap-sim at 1440x900
  // --------------------------------------------------------------------------
  console.log('2. Navigating to /lap-sim for 05_navbar_clean.png...');
  await page.goto('https://suspensionlab-studio.vercel.app/lap-sim', { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(3000);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(1000);
  const p5 = path.join(screenshotsDir, '05_navbar_clean.png');
  await page.screenshot({ path: p5 });
  console.log('Saved:', p5);

  // --------------------------------------------------------------------------
  // Screenshot 06: Populated Approval Gate Card on /ai-engineer
  // --------------------------------------------------------------------------
  console.log('3. Navigating to /ai-engineer for 06_ai_approval_gate_clean.png...');
  await page.goto('https://suspensionlab-studio.vercel.app/ai-engineer', { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(3000);

  const promptInput = await page.$('textarea, input[placeholder*="Ask"], input[placeholder*="query"], input[type="text"]');
  if (promptInput) {
    await promptInput.fill('Evaluate GT3 touring suspension roll balance and bottoming risk at Spa-Francorchamps.');
    const sendBtn = await page.$('button:has-text("Send"), button:has-text("Ask"), button[type="submit"]');
    if (sendBtn) {
      await sendBtn.click();
      console.log('Submitted query to AI Engineer, waiting for live response...');
      await page.waitForTimeout(8000);
    }
  }

  // Scroll so the Approval Gate card is prominently visible in the viewport
  try {
    const gateLocator = page.locator('text=Mandatory Human Approval Gate').first();
    if (await gateLocator.count() > 0) {
      await gateLocator.scrollIntoViewIfNeeded();
    } else {
      await page.evaluate(() => window.scrollTo(0, 600));
    }
  } catch (e) {
    await page.evaluate(() => window.scrollTo(0, 600));
  }
  await page.waitForTimeout(1000);

  const p6 = path.join(screenshotsDir, '06_ai_approval_gate_clean.png');
  await page.screenshot({ path: p6 });
  console.log('Saved:', p6);

  await browser.close();
  console.log('Final proof screenshots captured successfully!');
}

capture().catch((err) => {
  console.error('Capture error:', err);
  process.exit(1);
});
