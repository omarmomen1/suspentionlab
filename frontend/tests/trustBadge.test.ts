/**
 * Wave 6: Trust Badge & solver provenance guards (static source checks).
 */
import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const root = path.resolve(__dirname, "..");
const read = (rel: string) => fs.readFileSync(path.join(root, rel), "utf-8");

describe("Wave 6 Trust Badge & Solver Provenance", () => {
  it("TrustBadge component exists and renders verified provenance fields", () => {
    const src = read("components/TrustBadge.tsx");
    expect(src).toContain("solverVersion");
    expect(src).toContain("runId");
    expect(src).toContain("inputSha256");
    expect(src).toContain("Verified provenance");
    expect(src).toContain('data-testid="trust-badge"');
  });

  it("renders nothing when no provenance fields are present", () => {
    const src = read("components/TrustBadge.tsx");
    expect(src).toMatch(/if \(!sv && !rid && !sha\) return null;/);
  });

  it("is mounted on the kinematics, quarter-car, and report pages", () => {
    for (const rel of ["app/kinematics/page.tsx", "app/quarter-car/page.tsx", "app/report/page.tsx"]) {
      const src = read(rel);
      expect(src, rel).toContain('import TrustBadge from "../../components/TrustBadge"');
      expect(src, rel).toContain("<TrustBadge");
    }
  });

  it("kinematics response type carries the provenance fields", () => {
    const src = read("lib/api_client.ts");
    const block = src.slice(src.indexOf("interface KinematicsSolveResponse"));
    expect(block).toContain("run_id?: string");
    expect(block).toContain("input_sha256?: string");
    expect(block).toContain("solver_version: string");
  });

  it("exported PDF footer carries the provenance badge line", () => {
    const src = read("components/PDFExport.tsx");
    expect(src).toContain("VERIFIED PROVENANCE");
  });
});
