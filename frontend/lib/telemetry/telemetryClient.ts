/**
 * frontend/lib/telemetry/telemetryClient.ts
 * =========================================
 * High-performance binary SLTP v1 telemetry parser, sequence tracker,
 * loss handler, and real-time streaming hook.
 */

export const MAGIC_HEADER = "SLT1";

export enum ChannelId {
  UNKNOWN = 0,
  SPEED_MS = 1,
  LAT_G = 2,
  LONG_G = 3,
  VERT_G = 4,
  STEER_RAD = 5,
  SUSP_TRAVEL_FL = 6,
  SUSP_TRAVEL_FR = 7,
  SUSP_TRAVEL_RL = 8,
  SUSP_TRAVEL_RR = 9,
  BRAKE_PRESS_F = 10,
  THROTTLE_POS = 11,
  ENGINE_RPM = 12,
  YAW_RATE = 13,
}

export enum QualityCode {
  GOOD = 0,
  DEGRADED = 1,
  BAD = 2,
  OUT_OF_RANGE = 3,
}

export enum GripStatusCode {
  UNKNOWN = 0,
  OPTIMAL = 1,
  UNDER_UTILISING = 2,
  EXCEEDING_LIMIT = 3,
}

export const GRIP_STATUS_LABELS: Record<GripStatusCode, string> = {
  [GripStatusCode.UNKNOWN]: "Calibrating",
  [GripStatusCode.OPTIMAL]: "Optimal Traction Limit",
  [GripStatusCode.UNDER_UTILISING]: "Under-utilising Available Grip",
  [GripStatusCode.EXCEEDING_LIMIT]: "Exceeding Steady-State Limit (Sliding)",
};

export interface ChannelSample {
  channelId: ChannelId;
  value: number;
  quality: QualityCode;
}

export interface DigitalTwinState {
  theoreticalMaxLatG: number;
  actualLatG: number;
  divergencePct: number;
  gripStatus: GripStatusCode;
  gripStatusLabel: string;
}

export interface ParsedTelemetryFrame {
  sequenceNumber: number;
  timestamp: number;
  orgId: string;
  sessionId: string;
  samples: Map<ChannelId, number>;
  twin?: DigitalTwinState;
  speedMs: number;
  latG: number;
  longG: number;
  steerRad: number;
  suspTravelFL: number;
  suspTravelFR: number;
  suspTravelRL: number;
  suspTravelRR: number;
  brakePressF: number;
  throttlePos: number;
  engineRpm: number;
}

/**
 * Parses binary SLTP v1 frame from ArrayBuffer using DataView.
 */
export function parseSLTPBinaryFrame(buffer: ArrayBuffer): ParsedTelemetryFrame {
  const view = new DataView(buffer);
  if (view.byteLength < 20) {
    throw new Error(`Frame buffer too small: ${view.byteLength} bytes`);
  }

  // Check Magic
  const magic = String.fromCharCode(
    view.getUint8(0),
    view.getUint8(1),
    view.getUint8(2),
    view.getUint8(3)
  );
  if (magic !== MAGIC_HEADER) {
    throw new Error(`Invalid SLTP magic: ${magic}`);
  }

  let offset = 4;
  const sequenceNumber = view.getUint32(offset, false);
  offset += 4;
  const timestamp = view.getFloat64(offset, false);
  offset += 8;

  const orgLen = view.getUint8(offset);
  offset += 1;
  const orgBytes = new Uint8Array(buffer, offset, orgLen);
  const orgId = new TextDecoder().decode(orgBytes);
  offset += orgLen;

  const sessLen = view.getUint8(offset);
  offset += 1;
  const sessBytes = new Uint8Array(buffer, offset, sessLen);
  const sessionId = new TextDecoder().decode(sessBytes);
  offset += sessLen;

  const sampleCount = view.getUint16(offset, false);
  offset += 2;

  const samples = new Map<ChannelId, number>();

  for (let i = 0; i < sampleCount; i++) {
    if (offset + 7 > view.byteLength) break;
    const cid = view.getUint16(offset, false);
    const val = view.getFloat32(offset + 2, false);
    const _quality = view.getUint8(offset + 6);
    offset += 7;
    samples.set(cid, val);
  }

  let twin: DigitalTwinState | undefined;
  if (offset < view.byteLength) {
    const hasTwin = view.getUint8(offset);
    offset += 1;
    if (hasTwin === 1 && offset + 13 <= view.byteLength) {
      const tMax = view.getFloat32(offset, false);
      const aLat = view.getFloat32(offset + 4, false);
      const divPct = view.getFloat32(offset + 8, false);
      const gCode = view.getUint8(offset + 12) as GripStatusCode;
      offset += 13;

      twin = {
        theoreticalMaxLatG: Number(tMax.toFixed(3)),
        actualLatG: Number(aLat.toFixed(3)),
        divergencePct: Number(divPct.toFixed(1)),
        gripStatus: gCode,
        gripStatusLabel: GRIP_STATUS_LABELS[gCode] || "Optimal",
      };
    }
  }

  return {
    sequenceNumber,
    timestamp,
    orgId,
    sessionId,
    samples,
    twin,
    speedMs: samples.get(ChannelId.SPEED_MS) ?? 0,
    latG: samples.get(ChannelId.LAT_G) ?? 0,
    longG: samples.get(ChannelId.LONG_G) ?? 0,
    steerRad: samples.get(ChannelId.STEER_RAD) ?? 0,
    suspTravelFL: samples.get(ChannelId.SUSP_TRAVEL_FL) ?? 0,
    suspTravelFR: samples.get(ChannelId.SUSP_TRAVEL_FR) ?? 0,
    suspTravelRL: samples.get(ChannelId.SUSP_TRAVEL_RL) ?? 0,
    suspTravelRR: samples.get(ChannelId.SUSP_TRAVEL_RR) ?? 0,
    brakePressF: samples.get(ChannelId.BRAKE_PRESS_F) ?? 0,
    throttlePos: samples.get(ChannelId.THROTTLE_POS) ?? 0,
    engineRpm: samples.get(ChannelId.ENGINE_RPM) ?? 0,
  };
}

export type StreamStatus = "LIVE" | "DEGRADED" | "DISCONNECTED";

export interface StreamMetrics {
  rateHz: number;
  latencyMs: number;
  sequenceNumber: number;
  droppedPackets: number;
  duplicatePackets: number;
  outOfOrderPackets: number;
  lossRatePct: number;
}

export class TelemetrySequenceTracker {
  lastSequence: number = 0;
  expectedSequence: number = 1;
  totalReceived: number = 0;
  droppedPackets: number = 0;
  duplicatePackets: number = 0;
  outOfOrderPackets: number = 0;
  seenSequences: Set<number> = new Set();

  processSequence(seq: number): void {
    this.totalReceived += 1;

    if (this.lastSequence > 0) {
      if (this.seenSequences.has(seq)) {
        this.duplicatePackets += 1;
        return;
      }
      if (seq < this.lastSequence) {
        this.outOfOrderPackets += 1;
      } else if (seq > this.lastSequence + 1) {
        const gap = seq - (this.lastSequence + 1);
        this.droppedPackets += gap;
      }
    }

    this.seenSequences.add(seq);
    if (this.seenSequences.size > 2000) {
      const minKeep = seq - 1000;
      for (const s of this.seenSequences) {
        if (s < minKeep) this.seenSequences.delete(s);
      }
    }

    if (seq > this.lastSequence) {
      this.lastSequence = seq;
    }
    this.expectedSequence = this.lastSequence + 1;
  }

  getLossRatePct(): number {
    const totalExpected = this.totalReceived + this.droppedPackets;
    if (totalExpected === 0) return 0;
    return Number(((this.droppedPackets / totalExpected) * 100).toFixed(2));
  }
}
