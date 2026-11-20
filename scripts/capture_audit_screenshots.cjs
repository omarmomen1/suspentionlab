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
  // Screenshot 1 & 2: Lap Sim Top & Bottom
  // --------------------------------------------------------------------------
  console.log('2. Navigating to /lap-sim...');
  await page.goto('https://suspensionlab-studio.vercel.app/lap-sim', { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(3000);

  // If there is a simulate button, ensure simulation has run
  const simBtn = await page.$('button:has-text("Simulate Lap"), button:has-text("Run Simulation")');
  if (simBtn) {
    try {
      await simBtn.click();
      await page.waitForTimeout(4000);
    } catch (e) {
      console.log('Sim button click error (ignored):', e.message);
    }
  }

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(1000);
  const p1 = path.join(screenshotsDir, '01_lap_sim_top.png');
  await page.screenshot({ path: p1 });
  console.log('Saved:', p1);

  await page.evaluate(() => window.scrollTo(0, 950));
  await page.waitForTimeout(1000);
  const p2 = path.join(screenshotsDir, '02_lap_sim_bottom.png');
  await page.screenshot({ path: p2 });
  console.log('Saved:', p2);

  // --------------------------------------------------------------------------
  // Screenshot 3: Correlation
  // --------------------------------------------------------------------------
  console.log('3. Navigating to /correlation...');
  await page.goto('https://suspensionlab-studio.vercel.app/correlation', { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(4000);
  const p3 = path.join(screenshotsDir, '03_correlation.png');
  await page.screenshot({ path: p3 });
  console.log('Saved:', p3);

  // --------------------------------------------------------------------------
  // Screenshot 4: AI Engineer
  // --------------------------------------------------------------------------
  console.log('4. Navigating to /ai-engineer...');
  await page.goto('https://suspensionlab-studio.vercel.app/ai-engineer', { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(3000);

  // Look for prompt input textarea or input
  const promptInput = await page.$('textarea, input[placeholder*="Ask"], input[placeholder*="query"], input[type="text"]');
  if (promptInput) {
    await promptInput.fill('Evaluate GT3 touring suspension roll balance and bottoming risk at Spa-Francorchamps.');
    const sendBtn = await page.$('button:has-text("Send"), button:has-text("Ask"), button[type="submit"]');
    if (sendBtn) {
      await sendBtn.click();
      console.log('Sent prompt to AI Engineer, waiting for response...');
      await page.waitForTimeout(7000);
    }
  }

  const p4 = path.join(screenshotsDir, '04_ai_engineer.png');
  await page.screenshot({ path: p4 });
  console.log('Saved:', p4);

  await browser.close();
  console.log('Screenshot capture complete!');
}

capture().catch((err) => {
  console.error('Capture error:', err);
  process.exit(1);
});
