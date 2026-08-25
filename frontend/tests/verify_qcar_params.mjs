/**
 * Direct-execution verification of lib/qcarParams.ts logic.
 * Bypasses the vitest runner (currently broken by a Node 24 / vitest-worker
 * environment issue) while still exercising the exact same assertions as
 * tests/useQuarterCarSimulation.test.ts.
 * Run: node tests/verify_qcar_params.mjs   (Node >=22.6 type stripping)
 */
import assert from "node:assert/strict";
import { validateQCarParams, buildQCarPayload, DEFAULT_QCAR_PARAMS } from "../lib/qcarParams.ts";

const VALID = {
  m_s: 300, m_u: 35, k_s: 25000, c: 2050,
  k_t: 200000, MR: 0.85, c_t: 0,
  road_profile: "step", amplitude: 0.05, frequency: 2,
  duration: 5, iso_class: "B", speed_mps: 20,
  damper_curve_v: null, damper_curve_f: null,
};

let passed = 0;
function check(name, fn) {
  try { fn(); passed++; console.log(`  ok - ${name}`); }
  catch (e) { console.error(`  FAIL - ${name}: ${e.message}`); process.exitCode = 1; }
}

check("accepts physically valid parameters", () => {
  assert.equal(validateQCarParams(VALID), null);
});
check("rejects non-positive sprung mass", () => {
  assert.match(validateQCarParams({ ...VALID, m_s: 0 }), /Sprung Mass/);
  assert.match(validateQCarParams({ ...VALID, m_s: -10 }), /Sprung Mass/);
});
check("rejects non-positive unsprung mass", () => {
  assert.match(validateQCarParams({ ...VALID, m_u: 0 }), /Unsprung Mass/);
});
check("rejects non-positive spring rate", () => {
  assert.match(validateQCarParams({ ...VALID, k_s: -1 }), /Spring Rate/);
});
check("rejects non-positive tire stiffness", () => {
  assert.match(validateQCarParams({ ...VALID, k_t: 0 }), /Tire Stiffness/);
});
check("rejects negative damping but accepts zero", () => {
  assert.match(validateQCarParams({ ...VALID, c: -1 }), /Damping/);
  assert.equal(validateQCarParams({ ...VALID, c: 0 }), null);
});
check("buildQCarPayload splits params + profile sections", () => {
  const payload = buildQCarPayload(VALID);
  assert.equal(payload.params.m_s, 300);
  assert.equal(payload.params.k_s, 25000);
  assert.equal(payload.params.MR, 0.85);
  assert.equal(payload.profile.profile_type, "step");
  assert.equal(payload.profile.iso_class, "B");
  assert.equal(payload.profile.speed_mps, 20);
});
check("passes damper LUT curves through when present", () => {
  const withLut = { ...VALID, damper_curve_v: [0, 0.1, 0.5], damper_curve_f: [0, 500, 2000] };
  const payload = buildQCarPayload(withLut);
  assert.deepEqual(payload.params.damper_curve_v, [0, 0.1, 0.5]);
  assert.deepEqual(payload.params.damper_curve_f, [0, 500, 2000]);
});
check("produces a JSON-serialisable object", () => {
  JSON.stringify(buildQCarPayload(VALID));
});
check("defaults are themselves valid", () => {
  assert.equal(validateQCarParams(DEFAULT_QCAR_PARAMS), null);
});

console.log(`\n${passed}/8 checks passed`);
