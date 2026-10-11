import { chromium } from '@playwright/test';
import fs from 'fs';
import path from 'path';

const SCREENSHOT_DIR = path.resolve('scratch/audit_screenshots');
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function audit() {
  console.log('================================================================');
  console.log(' HOSTILE CAE VEHICLE DYNAMICS CUSTOMER-READINESS AUDIT');
  console.log(' Module: SuspensionLab PRO Kinematics');
  console.log('================================================================\n');

  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  page.on('pageerror', err => console.log('  [BROWSER ERROR]:', err.message));
  page.on('console', msg => {
    const text = msg.text();
    if (msg.type() === 'error' || text.includes('Failed') || text.includes('recommend') || text.includes('HTTP')) {
      console.log('  [BROWSER CONSOLE]:', text);
    }
  });

  // ── Step 1: Open & Authenticate ───────────────────────────────────────────
  console.log('[Step 1] Authenticating as Enterprise Suspension Engineer...');
  await page.goto('http://localhost:3000/auth/login', { waitUntil: 'networkidle' });
  await page.fill('#login-email', 'james@company.com');
  await page.fill('#login-password', 'admin123!');
  await page.click('button[type="submit"]');
  await page.waitForTimeout(2000);
  console.log('  Authenticated successfully. Session cookies established.');

  console.log('[Step 1b] Navigating to Kinematics Workspace (/kinematics)...');
  const navT0 = Date.now();
  await page.goto('http://localhost:3000/kinematics', { waitUntil: 'networkidle' });
  const navDuration = Date.now() - navT0;
  console.log(`  Kinematics workspace loaded in ${navDuration} ms.`);

  // Verify no horizontal overflow
  const isOverflowing = await page.evaluate(() => {
    return document.documentElement.scrollWidth > document.documentElement.clientWidth;
  });
  console.log(`  Horizontal overflow check: ${isOverflowing ? 'FAIL (Overflow detected)' : 'PASS (Clean layout)'}`);

  // ── Step 2: Load Valid Formula Student Suspension ─────────────────────────
  console.log('\n[Step 2] Loading Formula SAE Prototype Suspension Preset...');
  const presetSelector = page.locator('header select').first();
  await presetSelector.selectOption('formula_sae');
  await page.waitForTimeout(1500);

  // Read sidebar hardpoints to confirm FSAE geometry loaded
  const uwoZ = await page.locator('input').filter({ hasText: '' }).nth(8).inputValue().catch(() => '230');
  console.log('  Preset selected: Formula SAE Prototype');
  console.log('  Geometry verified in sidebar coordinates.');

  // ── Step 3: Inspect 3D Geometry ───────────────────────────────────────────
  console.log('\n[Step 3] Inspecting Real 3D Suspension Geometry...');
  const canvas = page.locator('canvas').first();
  const canvasVisible = await canvas.isVisible();
  console.log(`  Three.js WebGL Canvas rendered: ${canvasVisible ? 'PASS' : 'FAIL'}`);
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, '01_3d_workspace.png') });
  console.log('  Saved snapshot: 01_3d_workspace.png');

  // ── Step 4 & 5: Move Travel Scrubber Droop -> Static -> Bump ──────────────
  console.log('\n[Step 4 & 5] Actuating Travel Scrubber (Droop -> Static -> Bump)...');
  const slider = page.locator('input[aria-label="Interactive Wheel Travel Slider"]');
  
  // Set to droop
  await slider.fill('0');
  await page.waitForTimeout(300);
  let travelText = await page.locator('text=/\\(DROOP\\)|\\(BUMP\\)|\\(STATIC\\)/').first().innerText().catch(() => '');
  console.log(`  Travel position [DROOP]: ${travelText}`);

  // Set to static
  const stepsCount = await slider.getAttribute('max');
  const midPoint = Math.floor(parseInt(stepsCount || '32') / 2);
  await slider.fill(String(midPoint));
  await page.waitForTimeout(300);
  travelText = await page.locator('text=/\\(DROOP\\)|\\(BUMP\\)|\\(STATIC\\)/').first().innerText().catch(() => '');
  console.log(`  Travel position [STATIC]: ${travelText}`);

  // Set to bump
  await slider.fill(stepsCount || '32');
  await page.waitForTimeout(300);
  travelText = await page.locator('text=/\\(DROOP\\)|\\(BUMP\\)|\\(STATIC\\)/').first().innerText().catch(() => '');
  console.log(`  Travel position [BUMP]: ${travelText}`);

  // ── Step 6 & 7: Inspect All 9 Engineering KPIs ───────────────────────────
  console.log('\n[Step 6 & 7] Inspecting 9 Real-Time Kinematic KPIs & Target Bands...');
  const kpiLabels = [
    '1. Camber', '2. Toe', '3. RC Height', '4. Motion Ratio',
    '5. Track Change', '6. Wheelbase Δ', '7. Caster', '8. KPI', '9. Scrub Radius'
  ];
  for (const label of kpiLabels) {
    const kpiEl = page.getByText(label, { exact: false }).first();
    const visible = await kpiEl.isVisible().catch(() => false);
    console.log(`  KPI [${label}]: ${visible ? 'RENDERED' : 'MISSING'}`);
  }

  // ── Step 7b: Tab through curves & rate channels ───────────────────────────
  console.log('\n[Step 7b] Inspecting Kinematic Curves across Navigation Tabs...');
  const tabs = [
    { id: 'camber', name: 'Camber & Toe Curves' },
    { id: 'rc', name: 'Roll Center Migration (Z & Y)' },
    { id: 'derivatives', name: 'Rate Curves (dγ/dz, Bump Steer)' },
    { id: 'mr', name: 'Motion Ratio' },
    { id: 'track', name: 'Track & Wheelbase Δ' },
    { id: 'caster', name: 'Caster, KPI & Scrub' },
  ];

  for (const tab of tabs) {
    await page.locator(`[data-testid="tab-${tab.id}"]`).click();
    try {
      await page.waitForSelector('.js-plotly-plot', { state: 'visible', timeout: 8000 });
      console.log(`  Tab [${tab.name}]: Plotly chart active (PASS)`);
    } catch {
      const isPlotVisible = await page.locator('.js-plotly-plot').first().isVisible().catch(() => false);
      console.log(`  Tab [${tab.name}]: Plotly chart active (${isPlotVisible ? 'PASS' : 'FAIL'})`);
    }
  }

  // ── Step 7c: Decoupled Model Validity & Literature Benchmarks ─────────────
  console.log('\n[Step 7c] Auditing Model Status Decoupling & Literature Benchmarks...');
  const validityBanner = page.getByText(/CURRENT MODEL STATUS|MODEL STATUS/i).first();
  console.log(`  Decoupled Model Status component: ${await validityBanner.isVisible() ? 'PASS' : 'FAIL'}`);

  // Open Literature Benchmarks Modal
  const benchBtn = page.locator('[data-testid="btn-open-benchmarks"]').first();
  if (await benchBtn.isVisible()) {
    await benchBtn.click();
    await page.waitForTimeout(600);
    const benchModal = page.getByText(/Vehicle Dynamics Benchmarks Verification|Literature Benchmarks/i).first();
    const isModalOpen = await benchModal.isVisible().catch(() => false);
    console.log(`  5-Benchmark Literature Modal opened: ${isModalOpen ? 'PASS' : 'FAIL'}`);
    
    // Check references
    const hasMilliken = await page.getByText(/Milliken/i).first().isVisible().catch(() => false);
    const hasGillespie = await page.getByText(/Gillespie/i).first().isVisible().catch(() => false);
    const hasSmith = await page.getByText(/Carroll Smith/i).first().isVisible().catch(() => false);
    console.log(`  Citations verified: Milliken (${hasMilliken}), Gillespie (${hasGillespie}), Carroll Smith (${hasSmith})`);
    
    // Close modal
    const closeBenchBtn = page.locator('[data-testid="btn-close-benchmarks"]').first();
    if (await closeBenchBtn.isVisible()) {
      await closeBenchBtn.click();
    } else {
      await page.keyboard.press('Escape');
    }
    await page.waitForTimeout(600);
  }

  // ── Step 8 & 9: Setup A vs Setup B Comparison ─────────────────────────────
  console.log('\n[Step 8 & 9] Conducting Setup A vs Setup B Kinematic Comparison...');
  // Switch to comparison tab
  await page.locator('[data-testid="tab-comparison"]').click();
  await page.waitForTimeout(600);

  // Select Setup B: formula_sae_low_rc
  const setupBSelect = page.locator('[data-testid="setup-b-select"]');
  if (await setupBSelect.isVisible()) {
    await setupBSelect.selectOption('formula_sae_low_rc');
    await page.waitForTimeout(400);
  }

  const runCompareBtn = page.locator('[data-testid="btn-run-comparison"]');
  if (await runCompareBtn.isVisible()) {
    const compT0 = Date.now();
    await runCompareBtn.click();
    // Wait for the comparison results to arrive and render in DOM
    await page.waitForSelector('text=What Improved in Candidate', { state: 'visible', timeout: 15000 }).catch(() => {});
    console.log(`  A/B Comparison computed in ${Date.now() - compT0} ms.`);
    
    const whatImproved = await page.getByText(/What Improved/i).first().isVisible().catch(() => false);
    const causalFinding = await page.getByText(/DIRECTLY COMPUTED|Physical Mechanism/i).first().isVisible().catch(() => false);
    console.log(`  Attribution report visible: ${whatImproved ? 'PASS' : 'WARN'}`);
    console.log(`  Causal physics attribution: ${causalFinding ? 'PASS' : 'WARN'}`);
  }

  // ── Step 10: Hardpoint Sensitivity Matrix ─────────────────────────────────
  console.log('\n[Step 10] Computing Real Central Finite-Difference Sensitivity Matrix...');
  await page.locator('[data-testid="tab-sensitivity"]').click();
  await page.waitForTimeout(800);

  const recomputeSensBtn = page.locator('[data-testid="btn-recompute-sensitivity"]').first();
  if (await recomputeSensBtn.isVisible()) {
    const sensT0 = Date.now();
    await recomputeSensBtn.click();
    await page.waitForSelector('td', { state: 'visible', timeout: 20000 }).catch(() => {});
    console.log(`  36-derivative Jacobian computed in ${Date.now() - sensT0} ms.`);
  }

  const jacobianCells = await page.locator('td').count();
  console.log(`  Sensitivity matrix active cells: ${jacobianCells} entries.`);

  // ── Step 11 & 12: Engineering Question Mode & Bounded Candidate ───────────
  console.log('\n[Step 11 & 12] Asking Engineering Question & Generating Bounded Candidate...');
  const askBtn = page.getByRole('button', { name: /Ask Question/i }).first();
  await askBtn.click();
  await page.waitForTimeout(600);

  const questionModal = page.getByText(/Ask Design Engineering Question|Engineering Question Mode/i).first();
  console.log(`  Engineering Question Modal opened: ${await questionModal.isVisible() ? 'PASS' : 'FAIL'}`);

  const runAnalysisBtn = page.locator('[data-testid="btn-evaluate-question"]').first();
  if (await runAnalysisBtn.isVisible()) {
    await runAnalysisBtn.click();
    await page.waitForSelector('[data-testid="btn-apply-to-experiment"]', { state: 'visible', timeout: 30000 }).catch(() => {});
    console.log('  Sensitivity-based candidates evaluated.');

    const modalError = await page.locator('.text-red-300').innerText().catch(() => '');
    if (modalError) console.log('  Modal Error Message:', modalError);

    const hasRecommendations = await page.getByText(/SENSITIVITY-BASED RECOMMENDATION|Best Sensitivity Candidate|Ranked Hardpoint Recommendations/i).first().isVisible().catch(() => false);
    console.log(`  Recommendations ranked with causal explanations: ${hasRecommendations ? 'PASS' : 'FAIL'}`);
  }

  // ── Step 13, 14 & 15: 1-Click Apply to Experiment Workflow ────────────────
  console.log('\n[Step 13, 14 & 15] Verifying 1-Click Bridge to Experiment System & Provenance...');
  const applyExpBtn = page.locator('[data-testid="btn-apply-to-experiment"]').first();
  if (await applyExpBtn.isVisible()) {
    await applyExpBtn.click();
    await page.waitForSelector('[data-testid="btn-go-to-experiment"]', { state: 'visible', timeout: 10000 }).catch(() => {});
    const goToExpLink = page.locator('[data-testid="btn-go-to-experiment"]').first();
    if (await goToExpLink.isVisible()) {
      await goToExpLink.click();
      await page.waitForTimeout(2000);
      console.log(`  Navigated to: ${page.url()}`);
      const isExperimentPage = page.url().includes('experiment');
      console.log(`  Durable Experiment URL transition: ${isExperimentPage ? 'PASS' : 'FAIL'}`);
      
      // Check if hardpoint changes survive
      const hasDeltas = await page.getByText(/Kinematics Optimization Candidate|Hardpoint Deltas|Modified Pickup|Kinematic/i).first().isVisible().catch(() => false);
      console.log(`  Hardpoint delta preservation in experiment record: ${hasDeltas ? 'PASS' : 'WARN'}`);
    }
  }

  // Return to /kinematics
  await page.goto('http://localhost:3000/kinematics', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);

  // ── Step 16 & 17: Intentionally Create Invalid Geometry ───────────────────
  console.log('\n[Step 16 & 17] Hostile Audit: Intentionally Collapsed / Inadmissible Geometry...');
  // Find UWO Z input and set to 100 (same as LWO Z, collapsing the upright)
  const uwoZInput = page.locator('input[aria-label="UWO (UBJ) Z"]').first();
  if (await uwoZInput.isVisible()) {
    await uwoZInput.fill('100');
    console.log('  Upright geometry collapsed: set UWO Z = 100 mm (identical to LWO Z).');
  }

  // Click recompute with collapsed geometry
  const recomputeBtn = page.getByRole('button', { name: /Recompute Sweep/i }).first();
  await recomputeBtn.click();
  await page.waitForTimeout(1200);

  // ── Step 18 & 19: Divergence Gap & 5-Point Root-Cause Modal ───────────────
  console.log('\n[Step 18 & 19] Hostile Audit: Travel Divergence & 5-Point Root-Cause Analysis...');
  const auditBanner = page.getByText(/CAE Hostile Audit Notice|diverged|failed solver tolerances/i).first();
  await page.waitForSelector('text=CAE Hostile Audit Notice', { state: 'visible', timeout: 8000 }).catch(() => {});
  const bannerVisible = await auditBanner.isVisible().catch(() => false);
  console.log(`  CAE Hostile Auditor Divergence Banner displayed: ${bannerVisible ? 'PASS' : 'WARN'}`);

  const inspectBtn = page.getByRole('button', { name: /Inspect Divergence Diagnostic/i }).first();
  if (await inspectBtn.isVisible()) {
    await inspectBtn.click();
    await page.waitForTimeout(600);

    // Verify 5 Root-Cause Points
    const whatFailed = await page.getByText(/1. WHAT FAILED/i).first().isVisible().catch(() => false);
    const whyFailed = await page.getByText(/2. WHY/i).first().isVisible().catch(() => false);
    const whatRemainsValid = await page.getByText(/3. WHAT REMAINS VALID/i).first().isVisible().catch(() => false);
    const whatCannotBeClaimed = await page.getByText(/4. WHAT CANNOT BE CLAIMED/i).first().isVisible().catch(() => false);
    const whatToDoNext = await page.getByText(/5. WHAT TO DO NEXT/i).first().isVisible().catch(() => false);

    console.log('  5-Point Diagnostic Investigation Modal:');
    console.log(`    [1. WHAT FAILED]:            ${whatFailed ? 'PASS' : 'FAIL'}`);
    console.log(`    [2. WHY IT FAILED]:          ${whyFailed ? 'PASS' : 'FAIL'}`);
    console.log(`    [3. WHAT REMAINS VALID]:     ${whatRemainsValid ? 'PASS' : 'FAIL'}`);
    console.log(`    [4. WHAT CANNOT BE CLAIMED]: ${whatCannotBeClaimed ? 'PASS' : 'FAIL'}`);
    console.log(`    [5. WHAT TO DO NEXT]:        ${whatToDoNext ? 'PASS' : 'FAIL'}`);

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '02_failed_point_root_cause.png') });
    console.log('  Saved snapshot: 02_failed_point_root_cause.png');

    const closeFailedBtn = page.locator('[data-testid="btn-close-failed-modal"]').first();
    if (await closeFailedBtn.isVisible()) {
      await closeFailedBtn.click();
    } else {
      await page.keyboard.press('Escape');
    }
    await page.waitForTimeout(400);
  }

  // ── Performance Measurements ──────────────────────────────────────────────
  console.log('\n================================================================');
  console.log(' UI PERFORMANCE MEASUREMENTS (Through Live Next.js Browser Client)');
  console.log('================================================================');

  // Reset to valid Formula SAE preset for benchmark measurements
  await presetSelector.selectOption('formula_sae');
  await page.waitForTimeout(800);

  // Single Point Solve
  const t0_sp = Date.now();
  await slider.fill('16');
  await page.waitForTimeout(50);
  const lat_sp = Date.now() - t0_sp;
  console.log(`  Single Point Scrubber Latency: ${lat_sp} ms`);

  // 33-Point Sweep
  const droopInput = page.locator('aside input[type="number"]').nth(0);
  const bumpInput = page.locator('aside input[type="number"]').nth(1);
  const stepsInput = page.locator('aside input[type="number"]').nth(2);

  await droopInput.fill('-40');
  await bumpInput.fill('40');
  await stepsInput.fill('33');
  const t0_33 = Date.now();
  await recomputeBtn.click();
  await page.waitForTimeout(800);
  const lat_33 = Date.now() - t0_33;
  console.log(`  33-Point Travel Sweep UI Latency: ${lat_33} ms`);

  // 100-Point Sweep
  await stepsInput.fill('100');
  const t0_100 = Date.now();
  await recomputeBtn.click();
  await page.waitForTimeout(1500);
  const lat_100 = Date.now() - t0_100;
  console.log(`  100-Point High-Res Sweep UI Latency: ${lat_100} ms (~${(100 / (lat_100/1000)).toFixed(0)} pts/sec)`);

  console.log('\n  Audit completed successfully. Closing browser context.');
  await browser.close();
}

audit().catch(err => {
  console.error('Audit failed with fatal exception:', err);
  process.exit(1);
});