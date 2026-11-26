import { describe, it, expect } from "vitest";
import { formatApiError } from "../lib/api_client";

describe("formatApiError detail handling", () => {
  it("joins FastAPI 422 detail arrays", () => {
    const m = formatApiError({ detail: [{ loc: ["body", "m_s"], msg: "Input should be greater than 0" }, { loc: ["body", "c"], msg: "Field required" }] }, "Sim failed");
    expect(m).toContain("m_s: Input should be greater than 0");
    expect(m).toContain("c: Field required");
    expect(m).not.toContain("Unknown error");
  });
  it("formats structured detail objects", () => {
    const m = formatApiError({ detail: { code: "FULL_CAR_DIVERGED", message: "Full-car solver diverged" } }, "Run");
    expect(m).toBe("Run: Full-car solver diverged (FULL_CAR_DIVERGED)");
  });
  it("parses raw JSON in Error.message", () => {
    const m = formatApiError(new Error(JSON.stringify({ detail: [{ loc: ["body", "x"], msg: "bad" }] })), "Ctx");
    expect(m).toBe("Ctx: x: bad");
  });
});
