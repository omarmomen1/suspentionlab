import { describe, it, expect } from "vitest";
import {
  parseSLTPBinaryFrame,
  TelemetrySequenceTracker,
  ChannelId,
  QualityCode,
  GripStatusCode,
  MAGIC_HEADER,
} from "../lib/telemetry/telemetryClient";

describe("SLTP Binary Telemetry Protocol Parser", () => {
  it("should successfully parse a valid SLTP v1 binary frame", () => {
    // Construct valid binary buffer matching Python SLTPFrame.pack()
    const orgStr = "org-test";
    const sessStr = "sess-100hz";
    const orgBytes = new TextEncoder().encode(orgStr);
    const sessBytes = new TextEncoder().encode(sessStr);

    const buffer = new ArrayBuffer(100);
    const view = new DataView(buffer);

    // Magic: "SLT1"
    view.setUint8(0, 0x53);
    view.setUint8(1, 0x4c);
    view.setUint8(2, 0x54);
    view.setUint8(3, 0x31);

    // Sequence (42), Timestamp (1.234)
    view.setUint32(4, 42, false);
    view.setFloat64(8, 1.234, false);

    // Org ID
    let offset = 16;
    view.setUint8(offset++, orgBytes.length);
    new Uint8Array(buffer, offset, orgBytes.length).set(orgBytes);
    offset += orgBytes.length;

    // Sess ID
    view.setUint8(offset++, sessBytes.length);
    new Uint8Array(buffer, offset, sessBytes.length).set(sessBytes);
    offset += sessBytes.length;

    // Sample count: 2
    view.setUint16(offset, 2, false);
    offset += 2;

    // Sample 1: SPEED_MS = 32.5 m/s, GOOD
    view.setUint16(offset, ChannelId.SPEED_MS, false);
    view.setFloat32(offset + 2, 32.5, false);
    view.setUint8(offset + 6, QualityCode.GOOD);
    offset += 7;

    // Sample 2: LAT_G = 1.45 g, GOOD
    view.setUint16(offset, ChannelId.LAT_G, false);
    view.setFloat32(offset + 2, 1.45, false);
    view.setUint8(offset + 6, QualityCode.GOOD);
    offset += 7;

    // Digital Twin: has_twin = 1, tMax = 1.80, aLat = 1.45, div = 19.4%, OPTIMAL = 1
    view.setUint8(offset++, 1);
    view.setFloat32(offset, 1.80, false);
    offset += 4;
    view.setFloat32(offset, 1.45, false);
    offset += 4;
    view.setFloat32(offset, 19.4, false);
    offset += 4;
    view.setUint8(offset++, GripStatusCode.OPTIMAL);

    const parsed = parseSLTPBinaryFrame(buffer);
    expect(parsed.sequenceNumber).toBe(42);
    expect(parsed.timestamp).toBeCloseTo(1.234, 3);
    expect(parsed.orgId).toBe("org-test");
    expect(parsed.sessionId).toBe("sess-100hz");
    expect(parsed.speedMs).toBeCloseTo(32.5, 2);
    expect(parsed.latG).toBeCloseTo(1.45, 2);
    expect(parsed.twin).toBeDefined();
    expect(parsed.twin?.theoreticalMaxLatG).toBeCloseTo(1.80, 2);
    expect(parsed.twin?.actualLatG).toBeCloseTo(1.45, 2);
    expect(parsed.twin?.gripStatus).toBe(GripStatusCode.OPTIMAL);
  });

  it("should throw an error on invalid magic header", () => {
    const buffer = new ArrayBuffer(30);
    const view = new DataView(buffer);
    view.setUint8(0, 0x46); // "F"
    view.setUint8(1, 0x41); // "A"
    view.setUint8(2, 0x4b); // "K"
    view.setUint8(3, 0x45); // "E"

    expect(() => parseSLTPBinaryFrame(buffer)).toThrow("Invalid SLTP magic");
  });

  it("should throw an error on undersized frame buffer", () => {
    const buffer = new ArrayBuffer(10);
    expect(() => parseSLTPBinaryFrame(buffer)).toThrow("Frame buffer too small");
  });
});

describe("TelemetrySequenceTracker Loss & Order Handling", () => {
  it("should track sequential frames with zero packet loss", () => {
    const tracker = new TelemetrySequenceTracker();
    tracker.processSequence(1);
    tracker.processSequence(2);
    tracker.processSequence(3);

    expect(tracker.totalReceived).toBe(3);
    expect(tracker.droppedPackets).toBe(0);
    expect(tracker.duplicatePackets).toBe(0);
    expect(tracker.outOfOrderPackets).toBe(0);
    expect(tracker.getLossRatePct()).toBe(0);
  });

  it("should detect dropped packets when sequence gaps occur", () => {
    const tracker = new TelemetrySequenceTracker();
    tracker.processSequence(1);
    tracker.processSequence(2);
    // Gap: jumps to 6 (dropped 3, 4, 5 -> 3 drops)
    tracker.processSequence(6);

    expect(tracker.totalReceived).toBe(3);
    expect(tracker.droppedPackets).toBe(3);
    // 3 drops out of 6 expected = 50% loss
    expect(tracker.getLossRatePct()).toBe(50.0);
  });

  it("should detect duplicate and out-of-order packets", () => {
    const tracker = new TelemetrySequenceTracker();
    tracker.processSequence(10);
    tracker.processSequence(11);
    // Duplicate 10
    tracker.processSequence(10);
    expect(tracker.duplicatePackets).toBe(1);

    // Out-of-order 9 (lower than 11, not seen before)
    tracker.processSequence(9);
    expect(tracker.outOfOrderPackets).toBe(1);
  });
});
