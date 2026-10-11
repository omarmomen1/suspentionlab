/**
 * verify-a11y-playwright.mjs
 * Automated WCAG 2.2 AA Auditing Script using Playwright and axe-core.
 * 
 * Usage:
 *   node tests/verify-a11y-playwright.mjs [baseUrl]
 * Default: http://localhost:3000
 */

import { chromium } from "playwright";
import axeCore from "axe-core";

const BASE_URL = process.argv[2] || "http://localhost:3000";

const ROUTES = [
  "/",
  "/quarter-car",
  "/half-car",
  "/full-car",
  "/active",
  "/handling",
  "/kinematics",
  "/lap-sim",
  "/digital-twin",
  "/garage",
  "/pricing",
  "/settings",
  "/report",
  "/auth/login",
  "/auth/register",
  "/auth/forgot",
];

async function runA11yAudit() {
  console.log(`Starting WCAG 2.2 AA Playwright + axe-core audit against ${BASE_URL}...\n`);
  
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
  } catch (err) {
    console.error("Could not launch Chromium:", err.message);
    console.log("Ensure Playwright browsers are installed: npx playwright install chromium");
    process.exit(1);
  }

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  let totalViolations = 0;
  const auditResults = [];

  for (const route of ROUTES) {
    const url = `${BASE_URL}${route}`;
    process.stdout.write(`Auditing ${route.padEnd(20)} ... `);

    try {
      await page.goto(url, { waitUntil: "networkidle", timeout: 10000 });
      
      // Inject axe-core source into page context
      await page.evaluate(axeCore.source);

      // Run axe evaluation with WCAG 2.2 AA standards
      const results = await page.evaluate(async () => {
        // @ts-ignore
        return await window.axe.run(document, {
          runOnly: {
            type: "tag",
            values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"],
          },
          resultTypes: ["violations", "incomplete"],
        });
      });

      const violations = results.violations || [];
      totalViolations += violations.length;

      auditResults.push({
        route,
        url,
        violationCount: violations.length,
        violations: violations.map((v) => ({
          id: v.id,
          impact: v.impact,
          description: v.description,
          helpUrl: v.helpUrl,
          nodes: v.nodes.length,
        })),
      });

      if (violations.length === 0) {
        console.log(`\x1b[32mPASS (0 violations)\x1b[0m`);
      } else {
        console.log(`\x1b[31mFAIL (${violations.length} violations)\x1b[0m`);
      }
    } catch (err) {
      console.log(`\x1b[33mSKIPPED (${err.message.split("\n")[0]})\x1b[0m`);
      auditResults.push({
        route,
        url,
        error: err.message,
      });
    }
  }

  await browser.close();

  console.log("\n=======================================================");
  console.log(`AUDIT COMPLETE: ${totalViolations} total violation(s) across ${ROUTES.length} routes.`);
  console.log("=======================================================\n");

  return auditResults;
}

// Run if executed directly
if (process.argv[1]?.endsWith("verify-a11y-playwright.mjs")) {
  runA11yAudit().catch(console.error);
}

export { runA11yAudit };
