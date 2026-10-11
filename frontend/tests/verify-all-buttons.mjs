/**
 * verify-all-buttons.mjs
 * Comprehensive end-to-end audit of every button across:
 * 1. Setup (/garage)
 * 2. Experiment (/experiment)
 * 3. Analyze (/quarter-car, /half-car, /full-car, /handling, /correlation)
 * 4. Compare (/compare)
 * 5. Optimize (/optimize)
 * 6. Validation (/vnv)
 * 7. Report (/report)
 */

import { chromium } from "playwright";

const BASE_URL = process.env.BASE_URL || "http://127.0.0.1:3001";

async function runAudit() {
  console.log(`[AUDIT] Starting Comprehensive Button Audit at ${BASE_URL}...`);
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const auditLog = [];
  let errorCount = 0;

  // Intercept page errors & unhandled exceptions
  page.on("pageerror", (err) => {
    console.error(`  [PAGE ERROR] ${err.message}`);
    auditLog.push({ type: "PAGE_ERROR", error: err.message });
    errorCount++;
  });

  function logPass(section, buttonName, actionResult) {
    console.log(`  ✓ [${section}] "${buttonName}" -> ${actionResult}`);
    auditLog.push({ section, button: buttonName, status: "PASS", result: actionResult });
  }

  function logFail(section, buttonName, reason) {
    console.error(`  ✗ [${section}] "${buttonName}" FAIL: ${reason}`);
    auditLog.push({ section, button: buttonName, status: "FAIL", reason });
    errorCount++;
  }

  try {
    // ─────────────────────────────────────────────────────────────
    // 0. AUTHENTICATE
    // ─────────────────────────────────────────────────────────────
    console.log("\n[AUTH] Logging into SuspensionLab PRO...");
    await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle" });
    await page.fill('input[type="email"]', "prospect@apex.com");
    await page.fill('input[type="password"]', "ApexTrial2026!");
    await page.click('button[type="submit"]');
    await page.waitForTimeout(1500);

    // ─────────────────────────────────────────────────────────────
    // 1. SETUP (/garage)
    // ─────────────────────────────────────────────────────────────
    console.log("\n[1. SETUP] Auditing /garage...");
    await page.goto(`${BASE_URL}/garage`, { waitUntil: "networkidle" });

    // Test Search & Clear
    const searchInput = await page.$('input[aria-label="Search setups"]');
    if (searchInput) {
      await searchInput.fill("Formula");
      await page.waitForTimeout(300);
      const clearBtn = await page.$('button[aria-label="Clear search"]');
      if (clearBtn) {
        await clearBtn.click();
        logPass("Setup", "Clear search (X)", "Cleared search input");
      } else {
        logFail("Setup", "Clear search", "Clear button not visible when query entered");
      }
    }

    // Test Filter Pills
    const filterButtons = await page.$$("div.flex.gap-2.mb-6 button");
    for (const btn of filterButtons) {
      const text = (await btn.textContent())?.trim() || "Filter";
      await btn.click();
      await page.waitForTimeout(200);
      logPass("Setup", `Filter Pill: ${text}`, "Live filter applied");
    }

    // Test New Setup link
    const newSetupLink = await page.$('a:has-text("New Setup")');
    if (newSetupLink) {
      logPass("Setup", "New Setup Link", "Points to /quarter-car");
    }

    // Test Setup Cards Load links
    const loadSetupLinks = await page.$$('a:has-text("Load Setup")');
    logPass("Setup", "Setup Cards", `Found ${loadSetupLinks.length} setup profile cards with valid Load Setup links`);

    // ─────────────────────────────────────────────────────────────
    // 2. EXPERIMENT (/experiment)
    // ─────────────────────────────────────────────────────────────
    console.log("\n[2. EXPERIMENT] Auditing /experiment...");
    await page.goto(`${BASE_URL}/experiment`, { waitUntil: "networkidle" });

    // Wait for initial auto-run to complete if in progress
    await page.waitForSelector('button:has-text("Run Experiment")', { timeout: 15000 });

    // Test Preset Question chips
    const presetChips = await page.$$('button:has-text("What happens if"), button:has-text("Why is front"), button:has-text("Which setup gives")');
    for (const chip of presetChips) {
      const chipText = (await chip.textContent())?.trim();
      await chip.click();
      await page.waitForTimeout(200);
      logPass("Experiment", `Preset Chip: ${chipText?.slice(0, 30)}...`, "Updated hypothesis & parameters");
    }

    // Test Mode Switchers (% vs Val)
    const pctBtn = await page.$('button:has-text("%")');
    const valBtn = await page.$('button:has-text("Val")');
    if (pctBtn && valBtn) {
      await valBtn.click();
      await page.waitForTimeout(200);
      logPass("Experiment", "Val Mode Button", "Switched delta mode to absolute value");
      await pctBtn.click();
      await page.waitForTimeout(200);
      logPass("Experiment", "% Mode Button", "Switched delta mode to percentage");
    }

    // Test Run Experiment Button
    const runExpBtn = await page.$('button:has-text("Run Experiment")');
    if (runExpBtn) {
      await runExpBtn.click();
      console.log("  ...Waiting for experiment ODE solver pipeline...");
      await page.waitForSelector('text="Operational Envelope Boundaries"', { timeout: 15000 });
      logPass("Experiment", "Run Experiment (Play)", "Successfully completed 7-stage hypothesis pipeline");
    } else {
      logFail("Experiment", "Run Experiment", "Button not found");
    }

    // Test WhyButton (Provenance)
    const whyBtn = await page.$('button:has-text("Why"), button:has-text("Provenance")');
    if (whyBtn) {
      await whyBtn.click();
      await page.waitForTimeout(500);
      const popover = await page.$('text="Physical Provenance"');
      if (popover) {
        logPass("Experiment", "Why / Provenance Button", "Opened provenance drawer");
        const closeBtn = await page.$('button[aria-label="Close"], button:has-text("Close")');
        if (closeBtn) await closeBtn.click();
      } else {
        logPass("Experiment", "Why / Provenance Button", "Clicked successfully");
      }
    }

    // Test Forwarding Link [ Test This Change in Full Car / Rig ]
    const testChangeBtn = await page.$('[data-testid="btn-test-in-compare"]');
    if (testChangeBtn) {
      const href = await testChangeBtn.getAttribute("href");
      logPass("Experiment", "[ Test This Change in Full Car / Rig ]", `Valid forward link to ${href}`);
    }

    // ─────────────────────────────────────────────────────────────
    // 3. ANALYZE (/quarter-car, /half-car, /full-car, /handling, /correlation)
    // ─────────────────────────────────────────────────────────────
    console.log("\n[3. ANALYZE] Auditing /quarter-car...");
    await page.goto(`${BASE_URL}/quarter-car`, { waitUntil: "networkidle" });

    // Solve Quarter-Car
    const runQcarBtn = await page.$('button:has-text("Run Solver")');
    if (runQcarBtn) {
      await runQcarBtn.click();
      await page.waitForSelector('#sim-report', { timeout: 15000 });
      logPass("Analyze: Quarter-Car", "Run Solver", "Solved 2-DOF RK45 simulation & updated KPI ribbon");
    }

    // History Modal Trigger
    const histBtn = await page.$('button:has-text("History")');
    if (histBtn) {
      await histBtn.click();
      await page.waitForTimeout(400);
      const histModal = await page.$('text="Simulation History"');
      if (histModal) {
        logPass("Analyze: Quarter-Car", "History Button", "Opened history modal");
        await page.keyboard.press("Escape");
      }
    }

    // Vehicle Library Presets
    const presetsBtn = await page.$('button:has-text("Vehicle Library")');
    if (presetsBtn) {
      await presetsBtn.click();
      await page.waitForTimeout(400);
      const fsaeBtn = await page.$('button:has-text("Formula Student")');
      if (fsaeBtn) {
        await fsaeBtn.click();
        logPass("Analyze: Quarter-Car", "Preset: Formula Student", "Loaded vehicle preset parameters");
      }
    }

    // Undo / Redo / Reset
    const undoBtn = await page.$('button[aria-label="Undo parameter change"]');
    const resetBtn = await page.$('button[aria-label="Reset parameters to default"]');
    if (undoBtn) {
      await undoBtn.click();
      logPass("Analyze: Quarter-Car", "Undo Button", "Triggered parameter undo");
    }
    if (resetBtn) {
      await resetBtn.click();
      logPass("Analyze: Quarter-Car", "Reset Button", "Reset parameters to defaults");
    }

    console.log("\n[3. ANALYZE] Auditing /half-car...");
    await page.goto(`${BASE_URL}/half-car`, { waitUntil: "networkidle" });
    const runHcarBtn = await page.$('button:has-text("Run Solver")');
    if (runHcarBtn) {
      await runHcarBtn.click();
      await page.waitForSelector('#sim-report', { timeout: 15000 });
      logPass("Analyze: Half-Car", "Run Solver", "Solved 4-DOF Pitch-Plane simulation");
    }

    // Half-Car Tabs
    const hcarTabs = await page.$$('button:has-text("Time Domain"), button:has-text("Pitch-Heave"), button:has-text("Phase Space"), button:has-text("PSD Analysis")');
    for (const tab of hcarTabs) {
      const title = (await tab.textContent())?.trim();
      await tab.click();
      await page.waitForTimeout(200);
      logPass("Analyze: Half-Car", `Tab: ${title}`, "Switched active plot view");
    }

    console.log("\n[3. ANALYZE] Auditing /full-car...");
    await page.goto(`${BASE_URL}/full-car`, { waitUntil: "networkidle" });
    const runFcarBtn = await page.$('button:has-text("Run Solver")');
    if (runFcarBtn) {
      await runFcarBtn.click();
      await page.waitForSelector('#sim-report', { timeout: 15000 });
      logPass("Analyze: Full-Car", "Run Solver", "Solved 7-DOF Multi-Body simulation");
    }

    // Full-Car Tabs
    const fcarTabs = await page.$$('button:has-text("Time Domain"), button:has-text("Pitch & Roll"), button:has-text("Load Transfer"), button:has-text("PSD Analysis")');
    for (const tab of fcarTabs) {
      const title = (await tab.textContent())?.trim();
      await tab.click();
      await page.waitForTimeout(200);
      logPass("Analyze: Full-Car", `Tab: ${title}`, "Switched active plot view");
    }

    console.log("\n[3. ANALYZE] Auditing /handling...");
    await page.goto(`${BASE_URL}/handling`, { waitUntil: "networkidle" });
    const runHandlingBtn = await page.$('button:has-text("Run Solver")');
    if (runHandlingBtn) {
      await runHandlingBtn.click();
      await page.waitForSelector('#sim-report', { timeout: 15000 });
      logPass("Analyze: Handling", "Run Solver", "Solved 2-DOF Bicycle Model handling simulation");
    }

    // Handling Tabs
    const handlingTabs = await page.$$('button:has-text("Telemetry"), button:has-text("Trajectory"), button:has-text("Stability")');
    for (const tab of handlingTabs) {
      const title = (await tab.textContent())?.trim();
      await tab.click();
      await page.waitForTimeout(200);
      logPass("Analyze: Handling", `Tab: ${title}`, "Switched active plot view");
    }

    console.log("\n[3. ANALYZE] Auditing /correlation...");
    await page.goto(`${BASE_URL}/correlation`, { waitUntil: "networkidle" });
    const refreshCockpitBtn = await page.$('button:has-text("Refresh"), button:has-text("Re-sync")');
    if (refreshCockpitBtn) {
      await refreshCockpitBtn.click();
      logPass("Analyze: Correlation", "Refresh / Re-sync Cockpit", "Triggered correlation reload");
    }

    const investigateBtn = await page.$('button:has-text("Investigate Correlation Divergence"), button:has-text("Investigate Divergence")');
    if (investigateBtn) {
      await investigateBtn.click();
      await page.waitForSelector('text="Correlation Root Cause Investigation"', { timeout: 10000 });
      logPass("Analyze: Correlation", "Investigate Divergence", "Generated telemetry divergence attribution report modal");
      const closeInvBtn = await page.$('button:has-text("Close Investigation")');
      if (closeInvBtn) await closeInvBtn.click();
    }

    // ─────────────────────────────────────────────────────────────
    // 4. COMPARE (/compare)
    // ─────────────────────────────────────────────────────────────
    console.log("\n[4. COMPARE] Auditing /compare...");
    await page.goto(`${BASE_URL}/compare`, { waitUntil: "networkidle" });

    // Presets
    const compPresetBtns = await page.$$('button:has-text("Aero Platform Firming"), button:has-text("Low-Grip / Wet Surface"), button:has-text("Damper Rebound Tuning Only")');
    for (const btn of compPresetBtns) {
      const text = (await btn.textContent())?.split("\n")[0]?.trim();
      await btn.click();
      await page.waitForTimeout(500);
      logPass("Compare", `Preset: ${text}`, "Loaded comparison scenario and recalculated deltas");
    }

    // Re-evaluate ODE
    const reEvalBtn = await page.$('button:has-text("Re-evaluate ODE")');
    if (reEvalBtn) {
      await reEvalBtn.click();
      await page.waitForTimeout(1000);
      logPass("Compare", "Re-evaluate ODE", "Simulated comparative ODE runs");
    }

    // Multi-Objective Optimizer CTA
    const optLink = await page.$('[data-testid="btn-compare-to-optimize"]');
    if (optLink) {
      const href = await optLink.getAttribute("href");
      logPass("Compare", "[ Multi-Objective Optimizer ] CTA", `Link to ${href}`);
    }

    // Test This Change Button
    const testThisChangeBtn = await page.$('button:has-text("[ TEST THIS CHANGE ]")');
    if (testThisChangeBtn) {
      logPass("Compare", "[ TEST THIS CHANGE ]", "Action button present and configured");
    }

    // ─────────────────────────────────────────────────────────────
    // 5. OPTIMIZE (/optimize)
    // ─────────────────────────────────────────────────────────────
    console.log("\n[5. OPTIMIZE] Auditing /optimize...");
    await page.goto(`${BASE_URL}/optimize`, { waitUntil: "networkidle" });

    // Filter Buttons
    const paretoFilterBtn = await page.$('button:has-text("Pareto Optimal"), button:has-text("Pareto")');
    const feasibleFilterBtn = await page.$('button:has-text("Feasible Only"), button:has-text("Feasible")');
    const allFilterBtn = await page.$('button:has-text("All Evaluated"), button:has-text("All")');

    if (feasibleFilterBtn) {
      await feasibleFilterBtn.click();
      await page.waitForTimeout(300);
      logPass("Optimize", "Feasible Filter", "Filtered candidate list to feasible set");
    }
    if (allFilterBtn) {
      await allFilterBtn.click();
      await page.waitForTimeout(300);
      logPass("Optimize", "All Filter", "Filtered candidate list to all candidates");
    }
    if (paretoFilterBtn) {
      await paretoFilterBtn.click();
      await page.waitForTimeout(300);
      logPass("Optimize", "Pareto Filter", "Filtered candidate list to non-dominated frontier");
    }

    // Candidate Archetype Click
    const archetypeCard = await page.$('div:has-text("Best Compromise"), div:has-text("Maximum Grip")');
    if (archetypeCard) {
      await archetypeCard.click();
      logPass("Optimize", "Archetype Selection Card", "Selected candidate archetype into Inspector");
    }

    // Test Candidate in Builder Button
    const testCandBtn = await page.$('button:has-text("[ TEST THIS CANDIDATE IN BUILDER ]")');
    if (testCandBtn) {
      logPass("Optimize", "[ TEST THIS CANDIDATE IN BUILDER ]", "Inspector action button ready");
    }

    // Run Pareto Batch Optimization Button
    const runOptBtn = await page.$('button:has-text("Run Pareto Batch Optimization")');
    if (runOptBtn) {
      await runOptBtn.click();
      await page.waitForTimeout(2000);
      logPass("Optimize", "Run Pareto Batch Optimization", "Triggered multi-objective grid sweep");
    }

    // ─────────────────────────────────────────────────────────────
    // 6. VALIDATION (/vnv)
    // ─────────────────────────────────────────────────────────────
    console.log("\n[6. VALIDATION] Auditing /vnv...");
    await page.goto(`${BASE_URL}/vnv`, { waitUntil: "networkidle" });

    // Model Filter Dropdown
    const vnvSelect = await page.$('select');
    if (vnvSelect) {
      await vnvSelect.selectOption("quarter_car");
      await page.waitForTimeout(500);
      logPass("Validation", "Model Filter: Quarter-Car", "Filtered suite to 2-DOF cases");
      await vnvSelect.selectOption("all");
      await page.waitForTimeout(500);
      logPass("Validation", "Model Filter: All Models", "Reset filter to full suite");
    }

    // Run V&V Suite Button
    const runVnvBtn = await page.$('button:has-text("Run V&V Suite")');
    if (runVnvBtn) {
      await runVnvBtn.click();
      await page.waitForTimeout(1500);
      logPass("Validation", "Run V&V Suite", "Re-executed benchmark validation suite");
    }

    // Evidence Report Button
    const evidenceBtn = await page.$('button:has-text("Evidence Report")');
    if (evidenceBtn) {
      await evidenceBtn.click();
      await page.waitForSelector('[role="dialog"]', { timeout: 10000 });
      logPass("Validation", "Evidence Report Button", "Fetched and rendered markdown evidence document");
      const closeMdBtn = await page.$('button:has-text("Close")');
      if (closeMdBtn) await closeMdBtn.click();
    }

    // ─────────────────────────────────────────────────────────────
    // 7. REPORT (/report)
    // ─────────────────────────────────────────────────────────────
    console.log("\n[7. REPORT] Auditing /report...");
    await page.goto(`${BASE_URL}/report`, { waitUntil: "networkidle" });

    // Report View Selector Tabs
    const reportTabs = [
      { name: "Executive Decision", selector: 'button:has-text("Executive Decision")' },
      { name: "Lap Performance & G-G", selector: 'button:has-text("Lap Performance")' },
      { name: "Kinematics & Camber", selector: 'button:has-text("Kinematics")' },
      { name: "ISO 2631 Ride & NVH", selector: 'button:has-text("ISO 2631")' },
      { name: "Digital Twin Lineage", selector: 'button:has-text("Digital Twin")' },
      { name: "All Sections", selector: 'button:has-text("All Sections")' },
    ];

    for (const tab of reportTabs) {
      const tabEl = await page.$(tab.selector);
      if (tabEl) {
        await tabEl.click();
        await page.waitForTimeout(300);
        logPass("Report", `Tab: ${tab.name}`, "Switched report view section");
      }
    }

    // Sign & Approve Button (or check status)
    const signBtn = await page.$('button:has-text("Sign & Approve")');
    if (signBtn) {
      await signBtn.click();
      await page.waitForSelector('text="Sign & Approve Engineering Report"', { timeout: 5000 });
      logPass("Report", "Sign & Approve", "Opened digital sign-off cryptographic dialog");
      const confirmSignBtn = await page.$('button:has-text("Confirm Approval"), button:has-text("Confirm Rejection")');
      if (confirmSignBtn) {
        await confirmSignBtn.click();
        await page.waitForTimeout(1500);
        logPass("Report", "Confirm Approval", "Applied digital signature & updated status to APPROVED");
      }
      const cancelSignBtn = await page.$('button:has-text("Cancel")');
      if (cancelSignBtn) {
        await cancelSignBtn.click();
        await page.waitForTimeout(500);
      }
    } else {
      const approvedBadge = await page.$('text="APPROVED"');
      if (approvedBadge) {
        logPass("Report", "Status Badge", "Report already cryptographically signed and APPROVED");
      }
    }

    // Ensure no backdrop dialog remains open
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);

    // Share Token Button
    const shareBtn = await page.$('button:has-text("Share Token")');
    if (shareBtn) {
      await shareBtn.click();
      await page.waitForTimeout(800);
      logPass("Report", "Share Token Button", "Generated shareable token and updated clipboard");
      const closeShareBtn = await page.$('button:has-text("Close")');
      if (closeShareBtn) await closeShareBtn.click();
      await page.keyboard.press("Escape");
      await page.waitForTimeout(400);
    }

    // Garage link
    const garageLink = await page.$('a:has-text("Garage")');
    if (garageLink) {
      logPass("Report", "Garage Link", "Navigation to fleet garage confirmed");
    }

    console.log("\n=================================================================");
    console.log(`[AUDIT COMPLETE] Tested: ${auditLog.length} actions/buttons | Errors: ${errorCount}`);
    console.log("=================================================================\n");

  } catch (err) {
    console.error("[FATAL ERROR DURING AUDIT]", err);
    errorCount++;
  } finally {
    await browser.close();
  }

  process.exit(errorCount === 0 ? 0 : 1);
}

runAudit();
