const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function capture() {
  const screenshotsDir = path.resolve(__dirname, '..', '_audit_export', 'screenshots');
  if (!fs.existsSync(screenshotsDir)) {
    fs.mkdirSync(screenshotsDir, { recursive: true });
  }

  console.log('1. Authenticating via API to get authentic PRO JWT session...');
  const loginRes = await fetch('https://suspensionlab-api.vercel.app/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'testuser@suspensionlab.com', password: 'SuspensionLab2026!#' })
  });
  if (!loginRes.ok) {
    throw new Error(`Login API failed with status ${loginRes.status}`);
  }
  const authData = await loginRes.json();
  const token = authData.token;
  const user = {
    user_id: authData.user_id,
    email: authData.email,
    name: authData.name,
    plan: authData.plan,
    onboarding_complete: authData.onboarding_complete,
  };
  console.log(`Authenticated as ${user.email} (${user.plan})`);

  console.log('2. Launching browser with msedge channel...');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }
  });

  // Inject verified PRO credentials on every page load
  await context.addInitScript(({ token, user }) => {
    try {
      localStorage.setItem('sl_token', token);
      localStorage.setItem('sl_user', JSON.stringify(user));
    } catch (e) {}
  }, { token, user });

  await context.addCookies([
    {
      name: 'sl_token',
      value: token,
      domain: 'suspensionlab-studio.vercel.app',
      path: '/',
      httpOnly: false,
      secure: true,
      sameSite: 'Lax',
    }
  ]);

  const page = await context.newPage();

  // --------------------------------------------------------------------------
  // Screenshot 1 & 2: Lap Sim Top & Bottom
  // --------------------------------------------------------------------------
  console.log('3. Navigating to /lap-sim...');
  await page.goto('https://suspensionlab-studio.vercel.app/lap-sim', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForTimeout(4000);

  // If simulation button is present, trigger it and wait for results
  const runBtn = await page.$('#run-lap-sim-btn, button:has-text("Run Lap Simulation"), button:has-text("Simulate Lap")');
  if (runBtn) {
    try {
      console.log('Clicking Run Lap Simulation...');
      await runBtn.click();
      await page.waitForTimeout(5000);
    } catch (e) {
      console.log('Lap sim button click note:', e.message);
    }
  }

  // Wait for Plotly charts to render
  console.log('Waiting for Plotly charts to render...');
  await page.waitForSelector('.plotly-graph-div, div.js-plotly-plot', { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(2500);

  // Top view: scrollTop = 0
  console.log('Capturing 01_lap_sim_top.png (scrollTop = 0)...');
  await page.evaluate(() => {
    const el = document.querySelector('main div.overflow-y-auto');
    if (el) el.scrollTop = 0;
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(1500);
  const p1 = path.join(screenshotsDir, '01_lap_sim_top.png');
  await page.screenshot({ path: p1 });
  console.log('Saved:', p1);

  // Bottom view: inner container scrolled to bottom
  console.log('Capturing 02_lap_sim_bottom.png (scrollTop = 9999)...');
  await page.evaluate(() => {
    const el = document.querySelector('main div.overflow-y-auto');
    if (el) el.scrollTop = 9999;
  });
  await page.waitForTimeout(3000);
  const p2 = path.join(screenshotsDir, '02_lap_sim_bottom.png');
  await page.screenshot({ path: p2 });
  console.log('Saved:', p2);

  // --------------------------------------------------------------------------
  // Screenshot 3: Correlation
  // --------------------------------------------------------------------------
  console.log('4. Navigating to /correlation...');
  await page.goto('https://suspensionlab-studio.vercel.app/correlation', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForTimeout(4000);

  // Wait for correlation chart SVG elements to render
  console.log('Waiting for correlation charts...');
  await page.waitForSelector('svg, div[data-testid="correlation-chart"]', { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(2500);
  const p3 = path.join(screenshotsDir, '03_correlation.png');
  await page.screenshot({ path: p3 });
  console.log('Saved:', p3);

  // --------------------------------------------------------------------------
  // Screenshot 4: AI Engineer
  // --------------------------------------------------------------------------
  console.log('5. Navigating to /ai-engineer...');
  await page.goto('https://suspensionlab-studio.vercel.app/ai-engineer', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForTimeout(3000);

  const query = 'Solve front understeer while protecting front ride height at Spa-Francorchamps';
  console.log(`Submitting AI Engineer query: "${query}"...`);

  await page.evaluate((text) => {
    const ta = document.querySelector('textarea');
    if (ta) {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      setter.call(ta, text);
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      ta.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }, query);
  await page.waitForTimeout(1000);

  await page.evaluate(() => {
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('Run Engineering Analysis'));
    if (btn) btn.click();
  });

  console.log('Waiting for live solver response...');
  await page.waitForFunction(() => {
    const text = document.body.innerText || '';
    return text.includes('Front LLTD') || text.includes('Min Front Dynamic Ride Height');
  }, { timeout: 35000 });
  await page.waitForTimeout(2500);

  // Scroll main-content container to display Grounded Statement, deltas, and evidence
  await page.evaluate(() => {
    const mc = document.getElementById('main-content');
    if (mc) mc.scrollTop = 1000;
  });
  await page.waitForTimeout(1500);

  const p4 = path.join(screenshotsDir, '04_ai_engineer.png');
  await page.screenshot({ path: p4 });
  console.log('Saved:', p4);

  await browser.close();
  console.log('All 4 audit screenshots successfully captured!');
}

capture().catch((err) => {
  console.error('Capture error:', err);
  process.exit(1);
});
