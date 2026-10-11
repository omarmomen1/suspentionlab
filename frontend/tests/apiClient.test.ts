import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  SimulationApi,
  TelemetryApi,
  VnApi,
  EnterpriseApi,
  ReportsApi,
} from "../lib/api_client";
import * as apiModule from "../lib/api";

describe("Canonical TypeScript API Client SDK", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("SimulationApi.simulateQuarterCar calls correct endpoint and headers", async () => {
    const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce({
      time: [0, 0.01],
      z_s: [0, 0.002],
    });

    const payload = {
      m_s: 300,
      m_u: 45,
      k_s: 35000,
      k_t: 220000,
      c: 2500,
      speed_kmh: 120,
    };

    const res = await SimulationApi.simulateQuarterCar(payload);

    expect(spy).toHaveBeenCalledWith(
      "/api/v1/simulate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(payload),
      })
    );
    expect(res.z_s).toHaveLength(2);
  });

  it("TelemetryApi.decimateTrace calls /api/v1/telemetry/decimate", async () => {
    const mockDecResponse = {
      channel_name: "speed",
      original_points: 1000,
      decimated_points: 100,
      lod_level: "OVERVIEW",
      timestamps: [0, 0.1],
      values: [100, 105],
      events: [],
    };

    const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockDecResponse);

    const payload = {
      timestamps: [0, 0.01, 0.02],
      values: [100, 102, 105],
      channel_name: "speed",
      target_points: 100,
    };

    const res = await TelemetryApi.decimateTrace(payload);

    expect(spy).toHaveBeenCalledWith(
      "/api/v1/telemetry/decimate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(payload),
      })
    );
    expect(res.lod_level).toBe("OVERVIEW");
  });

  it("VnApi.runVnSuite requests /api/v1/vnv/run with optional model filter", async () => {
    const mockSuite = {
      summary: { total: 18, passed: 18, failed: 0, all_passed: true },
      cases: [],
    };

    const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockSuite);

    const res = await VnApi.runVnSuite("quarter_car");

    expect(spy).toHaveBeenCalledWith("/api/v1/vnv/run?model=quarter_car");
    expect(res.summary.all_passed).toBe(true);
  });

  it("EnterpriseApi.getActiveSessions requests /api/v1/auth/sessions", async () => {
    const mockSessions = {
      sessions: [
        {
          jti: "jti-1",
          ip_address: "127.0.0.1",
          user_agent: "Mozilla/5.0",
          device_type: "Desktop",
          created_at: "2026-09-03T12:00:00Z",
          expires_at: "2026-09-10T12:00:00Z",
          is_current: true,
        },
      ],
    };

    const spy = vi.spyOn(apiModule, "apiJson").mockResolvedValueOnce(mockSessions);

    const res = await EnterpriseApi.getActiveSessions();

    expect(spy).toHaveBeenCalledWith("/api/v1/auth/sessions");
    expect(res.sessions).toHaveLength(1);
    expect(res.sessions[0].is_current).toBe(true);
  });
});
