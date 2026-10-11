/**
 * verify-production-integration.mjs
 * End-to-end Playwright verification of SuspensionLab Pro production integration:
 * - Global Engineering Workspace
 * - Verification & Validation (V&V) Suite
 * - Setup Comparison & Consequence Diff
 * - Synchronized Multi-Resolution Telemetry
 * - Security & Enterprise Directory Settings
 * - Real Simulation ID Reports
 */

import { chromium } from "playwright";

const BASE_URL = process.env.BASE_URL || "http://localhost:3000";

async function runVerification() {
  console.log(`[E2E] Connecting to SuspensionLab Pro at ${BASE_URL}...`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  let passedTests = 0;
  let failedTests = 0;

  function assert(condition, message) {
    if (condition) {
      console.log(`  ✓ ${message}`);
      passedTests++;
    } else {
      console.error(`  ✗ FAIL: ${message}`);
      failedTests++;
    }
  }

  try {
    // ── Test 1: Global Engineering Workspace StatusBar ───────────────────────
    console.log("\n[TEST 1] Verifying Global Engineering Workspace Status Bar on /");
    await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle", timeout: 15000 });

    const bodyText = await page.textContent("body");
    assert(bodyText.includes("PRODUCTION MODE"), "Workspace Mode badge is visible and in PRODUCTION");
    assert(bodyText.includes("VEHICLE:"), "Active Vehicle provenance displayed in status bar");
    assert(bodyText.includes("SETUP:"), "Active Setup version displayed in status bar");
    assert(bodyText.includes("TRACK:"), "Active Track displayed in status bar");
    assert(bodyText.includes("TIRE:"), "Active Tire specification displayed in status bar");
    assert(bodyText.includes("ACTIVE RUN:"), "Active Simulation Run ID displayed in status bar");
    assert(bodyText.includes("VALIDATED"), "Validation Tier badge (VALIDATED) displayed");

    // ── Test 2: Verification & Validation (V&V) Evidence Page ────────────────
    console.log("\n[TEST 2] Verifying V&V Evidence Suite on /vnv");
    await page.goto(`${BASE_URL}/vnv`, { waitUntil: "networkidle", timeout: 15000 });

    const vnvHeading = await page.textContent("h1");
    assert(vnvHeading.includes("Verification & Validation"), "V&V Page header is present");

    const vnvText = await page.textContent("body");
    assert(vnvText.includes("Total Test Cases"), "Total Test Cases summary card displayed");
    assert(vnvText.includes("Passing Cases"), "Passing Cases summary card displayed");
    assert(vnvText.includes("Benchmark Case Execution Log"), "Benchmark test table rendered");
    assert(vnvText.includes("Run V&V Suite"), "Run V&V Suite execution button rendered");

    // ── Test 3: Setup Diff & Causal Chain on /setup-sensitivity ──────────────
    console.log("\n[TEST 3] Verifying Setup Comparison & Consequence Engine on /setup-sensitivity");
    await page.goto(`${BASE_URL}/setup-sensitivity`, { waitUntil: "networkidle", timeout: 15000 });

    const diffText = await page.textContent("body");
    assert(diffText.includes("Setup Diff (A vs B)"), "Setup Diff tab toggle present");
    assert(diffText.includes("Setup Comparison & Consequence Engine"), "Setup comparison engine header present");
    assert(diffText.includes("Parameter Modifications"), "Parameter deltas table present");
    assert(diffText.includes("Physics Causal Chain (What Changed)"), "Causal chain (what changed) panel present");
    assert(diffText.includes("Baseline (A):") && diffText.includes("Candidate (B):"), "Baseline vs Candidate inputs present");

    // ── Test 4: Synchronized Multi-Resolution Telemetry UI on /digital-twin ───
    console.log("\n[TEST 4] Verifying Synchronized Telemetry UI on /digital-twin");
    await page.goto(`${BASE_URL}/digital-twin`, { waitUntil: "networkidle", timeout: 15000 });

    // Click Synchronized Inspection tab if not already selected
    const syncTabBtn = page.getByRole("button", { name: "Synchronized Inspection" });
    await syncTabBtn.click();
    await page.waitForTimeout(500);

    const dtText = await page.textContent("body");
    assert(dtText.includes("Synchronized Cursor"), "Synchronized crosshair cursor displayed");
    assert(dtText.includes("Corner Phase"), "Dynamic corner phase indicator displayed");
    assert(dtText.includes("Spa Sector 2 Map"), "Track 2D position map rendered");
    assert(dtText.includes("Active Channels"), "Channel selector controls present");
    assert(dtText.includes("Resolution LOD:"), "Multi-resolution LOD level toggles present");

    // ── Test 5: Settings Active Sessions & Enterprise SCIM on /settings ──────
    console.log("\n[TEST 5] Verifying Security & Enterprise Settings on /settings");
    await page.goto(`${BASE_URL}/settings`, { waitUntil: "networkidle", timeout: 15000 });

    const secTabBtn = page.getByRole("button", { name: "Security & Sessions" });
    await secTabBtn.click();
    await page.waitForTimeout(500);

    const secText = await page.textContent("body");
    assert(secText.includes("Active Device Sessions"), "Active Device Sessions list rendered");
    assert(secText.includes("Sign out of all sessions"), "Revoke all sessions button present");

    const entTabBtn = page.getByRole("button", { name: "Enterprise & SCIM" });
    await entTabBtn.click();
    await page.waitForTimeout(500);

    const entText = await page.textContent("body");
    assert(
      entText.includes("Enterprise Directory") || entText.includes("SCIM 2.0"),
      "Enterprise directory & SCIM configuration rendered"
    );

    // ── Test 6: Real Simulation ID Report on /report ──────────────────────────
    console.log("\n[TEST 6] Verifying Real Simulation ID Report on /report");
    await page.goto(`${BASE_URL}/report?run_id=RUN-SPA-0028`, { waitUntil: "networkidle", timeout: 15000 });

    const repText = await page.textContent("body");
    assert(
      repText.includes("RUN-SPA-0028") || repText.includes("Engineering Decision"),
      "Report rendered with active simulation run provenance"
    );

  } catch (err) {
    console.error("Test execution encountered an error:", err);
    failedTests++;
  } finally {
    await browser.close();
  }

  console.log(`\n======================================================`);
  console.log(`[RESULTS] PASSED: ${passedTests} | FAILED: ${failedTests}`);
  console.log(`======================================================\n`);

  if (failedTests > 0) {
    process.exit(1);
  }
}

runVerification();
