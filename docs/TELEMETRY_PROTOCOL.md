# SuspensionLab Telemetry Protocol (SLTP v1) Specification

## 1. Scope & Design Goals
The **SuspensionLab Telemetry Protocol (SLTP v1)** provides a high-throughput, low-latency compact binary transport for real-time motorsport data acquisition (DAQ) and cloud-based Digital Twin state synchronization.

Key Requirements:
- Sustained $\ge 100\text{ Hz}$ streaming per channel and vehicle corner.
- Packet footprint under 150 bytes per frame (achieved: ~58–120 bytes).
- Zero-copy native decoding in Python (`struct`) and modern web browsers (`DataView`).
- Strict tenant isolation, quality flags, sequence loss detection, and Digital Twin metrics.

---

## 2. Binary Wire Format Layout (Big-Endian / Network Byte Order)

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                       Magic: "SLT1"                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                     Sequence Number (uint32)                  |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
+                    Timestamp Seconds (float64)                +
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Org ID Length |           Org ID UTF-8 Bytes (varies)        ...
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Sess ID Len   |         Session ID UTF-8 Bytes (varies)      ...
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|      Sample Count (uint16)    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       Channel ID (uint16)     |      Sample Value (float32)   |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  ... Sample Value (cont)      |  Quality (u8) | ... (repeated)|
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Has Twin (u8) | Theoretical Max Lat G (float32)               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Actual Lat G (float32)        | Divergence % (float32)        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Grip Code (u8)|
+-+-+-+-+-+-+-+-+
```

### Frame Header Fields
| Field | Type | Size | Description |
|---|---|---|---|
| `Magic` | char[4] | 4 bytes | Protocol identifier: `0x53, 0x4C, 0x54, 0x31` (`"SLT1"`). |
| `Sequence Number`| uint32 | 4 bytes | Monotonically increasing index from telemetry source. Used for packet drop, duplicate, and jitter detection. |
| `Timestamp` | float64 | 8 bytes | Source timestamp in seconds (IEEE 754 double precision). |
| `Org ID` | varbyte | $1 + N$ bytes | Multi-tenant organization UUID / identifier (max 64 bytes). |
| `Session ID` | varbyte | $1 + M$ bytes | Telemetry session identifier (max 64 bytes). |
| `Sample Count` | uint16 | 2 bytes | Number of channel sample records in this frame. |

### Channel Sample Fields (Repeated per Sample: 7 bytes)
| Field | Type | Size | Description |
|---|---|---|---|
| `Channel ID` | uint16 | 2 bytes | Canonical channel enum (e.g. Speed, Lat G, Damper FL). |
| `Value` | float32 | 4 bytes | Engineering value (IEEE 754 single precision float). |
| `Quality` | uint8 | 1 byte | Quality code bitmask / status. |

### Digital Twin Evaluation Block
| Field | Type | Size | Description |
|---|---|---|---|
| `Has Twin` | uint8 | 1 byte | `1` if physics evaluation is attached; `0` otherwise. |
| `Theoretical Max Lat G` | float32 | 4 bytes | Pacejka multi-body limit at current speed. |
| `Actual Lat G` | float32 | 4 bytes | Measured lateral acceleration. |
| `Divergence %` | float32 | 4 bytes | Percentage divergence between actual G and theoretical maximum. |
| `Grip Status Code` | uint8 | 1 byte | Enum: `0`=Unknown, `1`=Optimal, `2`=Under-utilising, `3`=Exceeding Limit. |

---

## 3. Canonical Channel IDs

| ID | Identifier | Physical Units | Valid Nominal Range |
|---|---|---|---|
| `1` | `SPEED_MS` | $\text{m/s}$ | $[0.0, 125.0]$ |
| `2` | `LAT_G` | $\text{G}$ | $[-6.0, 6.0]$ |
| `3` | `LONG_G` | $\text{G}$ | $[-6.0, 6.0]$ |
| `4` | `VERT_G` | $\text{G}$ | $[-4.0, 8.0]$ |
| `5` | `STEER_RAD` | $\text{rad}$ | $[-12.5, 12.5]$ |
| `6` | `SUSP_TRAVEL_FL` | $\text{mm}$ | $[-50.0, 150.0]$ |
| `7` | `SUSP_TRAVEL_FR` | $\text{mm}$ | $[-50.0, 150.0]$ |
| `8` | `SUSP_TRAVEL_RL` | $\text{mm}$ | $[-50.0, 150.0]$ |
| `9` | `SUSP_TRAVEL_RR` | $\text{mm}$ | $[-50.0, 150.0]$ |
| `10`| `BRAKE_PRESS_F` | $\text{bar}$ | $[0.0, 250.0]$ |
| `11`| `THROTTLE_POS` | $\%$ | $[0.0, 100.0]$ |
| `12`| `ENGINE_RPM` | $\text{rpm}$ | $[0.0, 20000.0]$ |
| `13`| `YAW_RATE` | $\text{deg/s}$ | $[-180.0, 180.0]$ |

---

## 4. Quality Status Codes

| Code | Label | Meaning |
|---|---|---|
| `0` | `GOOD` | Sample within sensor bounds, valid rate of change. |
| `1` | `DEGRADED` | Value noisy, high timestamp jitter ($>15\%$), or interpolation used. |
| `2` | `BAD` | Sensor dropout, NaN, Inf, or dead flatline sensor. |
| `3` | `OUT_OF_RANGE` | Sample value exceeds physical sensor limits. |

---

## 5. Packet Loss & Loss Handling Semantics
Subscribers maintain a sequence state tracker:
- **Normal Packet Arrival**: $\text{seq} = \text{expected\_seq}$. Mark status `LIVE`.
- **Dropped Packets**: If $\text{seq} > \text{expected\_seq}$, drop count increments by $\text{seq} - \text{expected\_seq}$. If packet loss exceeds $2\%$, transition status to `DEGRADED`.
- **Duplicate Packet**: If $\text{seq} \le \text{last\_seq}$ and was previously received, discard sample and increment duplicate counter.
- **Out-of-Order Packet**: If $\text{seq} < \text{last\_seq}$ but not previously seen, handle per reorder buffer policy.
- **Disconnect / Reconnect**: On socket close, mark `DISCONNECTED`, engage exponential backoff retry with jitter, and resume sequence synchronization upon handshake.
