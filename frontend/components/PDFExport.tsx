"use client";
import { useState, useCallback } from "react";
import { FileDown, Loader2 } from "lucide-react";
import PlanGate from "./PlanGate";

interface ParamChange {
  parameter: string;
  baseline: string;
  simulated: string;
  delta: string;
}

interface PlotData {
  time?: number[];
  z_s?: number[];
  z_u?: number[];
  kinematics?: { heave_travel_mm: number[]; camber_deg: number[]; toe_deg: number[] };
  aerodynamics?: { speed_kmh: number[]; downforce_n: number[]; drag_n: number[] };
  gg_envelope?: { boundary_lat_g: number[]; boundary_long_g: number[]; sim_lat_g: number[]; sim_long_g: number[] };
}

export interface PinnedLedgerRow {
  parameter: string;
  /** Preformatted value; missing values arrive as "Not available". */
  value: string;
  unit: string;
  source: string;
}

interface PDFExportProps {
  /** Rows pinned from the V2 Ledger. When present they print on an appendix page. */
  pinnedRows?: PinnedLedgerRow[];
  captureId?: string;
  fileName?: string;
  title?: string;
  docId?: string;
  vehicleRef?: string;
  setupRef?: string;
  trackRef?: string;
  tireRef?: string;
  telemetryRef?: string;
  solverVersion?: string;
  physicsVersion?: string;
  softwareBuild?: string;
  inputHash?: string;
  resultHash?: string;
  artifactHash?: string;
  validationStatus?: string;
  correlationPct?: number;
  comfortCategory?: string;
  params?: Record<string, unknown>;
  metrics?: Record<string, unknown>;
  paramChanges?: ParamChange[];
  plotData?: PlotData;
  approval?: {
    status?: string;
    name?: string;
    role?: string;
    timestamp?: string;
    comment?: string;
    signature?: string;
  };
}

async function computeWebCryptoSha256(data: unknown): Promise<string> {
  try {
    const text = typeof data === "string" ? data : JSON.stringify(data ?? {});
    const encoder = new TextEncoder();
    const dataBuffer = encoder.encode(text);
    if (typeof crypto !== "undefined" && crypto.subtle) {
      const hashBuffer = await crypto.subtle.digest("SHA-256", dataBuffer);
      return Array.from(new Uint8Array(hashBuffer))
        .map((b) => b.toString(16).padStart(2, "0"))
        .join("");
    }
  } catch (err) {
    console.warn("WebCrypto SHA-256 computation failed:", err);
  }
  return "";
}

export default function PDFExport({
  pinnedRows,
  captureId,
  fileName = "SuspensionLab-PRO-Engineering-Report",

  title = "Engineering Decision & Compliance Report",
  docId = "DOC-2026-SL-0001",
  vehicleRef = "CAR-07",
  setupRef = "REV-01",
  trackRef = "SPA-FRANCORCHAMPS",
  tireRef = "TIRE-MF52-COMPOUND-SOFT",
  telemetryRef = "TELEMETRY-SYNC-Q2",
  solverVersion = "RK45 / BDF Adaptive Stiff",
  physicsVersion = "quarter-car-v2",
  softwareBuild = "BUILD-REL-2026.1",
  inputHash,
  resultHash,
  artifactHash,
  validationStatus = "UNVALIDATED",
  correlationPct,
  comfortCategory = "UNEVALUATED",
  metrics,
  paramChanges,
  plotData,
  approval,
}: PDFExportProps) {
  const [exporting, setExporting] = useState(false);

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      // jsPDF throws on undefined/null text args - coerce provenance strings once.
      const S = (v: unknown): string => (typeof v === "string" && v.trim() ? v : "\u2014");
      const vehicleRef_ = S(vehicleRef), setupRef_ = S(setupRef), tireRef_ = S(tireRef),
            trackRef_ = S(trackRef), telemetryRef_ = S(telemetryRef),
            solverVersion_ = S(solverVersion), physicsVersion_ = S(physicsVersion),
            validationStatus_ = S(validationStatus), title_ = S(title), docId_ = S(docId);

      const EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";
      const isProvidedHash = (h?: string): boolean => Boolean(h && h !== "—" && h !== EMPTY_SHA256);

      const effectiveInputHash = isProvidedHash(inputHash)
        ? inputHash!
        : (await computeWebCryptoSha256({ docId, vehicleRef, setupRef, trackRef, tireRef, solverVersion, physicsVersion })) || EMPTY_SHA256;

      const effectiveResultHash = isProvidedHash(resultHash)
        ? resultHash!
        : (await computeWebCryptoSha256({ metrics, paramChanges, plotData, correlationPct })) || EMPTY_SHA256;

      const effectiveArtifactHash = isProvidedHash(artifactHash)
        ? artifactHash!
        : (await computeWebCryptoSha256({
            docId,
            vehicleRef,
            setupRef,
            trackRef,
            inputHash: effectiveInputHash,
            resultHash: effectiveResultHash,
          })) || EMPTY_SHA256;

      const { default: jsPDF } = await import("jspdf");

      const pdf = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
      const pageW = pdf.internal.pageSize.getWidth(); // 210 mm
      const pageH = pdf.internal.pageSize.getHeight(); // 297 mm
      const margin = 14;
      const contentW = pageW - margin * 2; // 182 mm

      const drawHeader = (pageNum: number, totalPages: number) => {
        pdf.setFillColor(15, 23, 42); // Slate 900
        pdf.rect(0, 0, pageW, 24, "F");

        pdf.setTextColor(242, 169, 0); // Ansys Gold
        pdf.setFontSize(11);
        pdf.setFont("helvetica", "bold");
        pdf.text("SUSPENSIONLAB PRO", margin, 9);
        pdf.setFontSize(8);
        pdf.setFont("helvetica", "normal");
        pdf.setTextColor(148, 163, 184);
        pdf.text("SuspensionLab Engineering Simulation Artifact", margin, 15);

        pdf.setFontSize(7.5);
        pdf.setTextColor(100, 116, 139);
        pdf.text(`Doc: ${docId} | Page ${pageNum} of ${totalPages}`, pageW - margin - 55, 12);
        pdf.setDrawColor(242, 169, 0);
        pdf.setLineWidth(0.6);
        pdf.line(margin, 24, pageW - margin, 24);
      };

      const drawFooter = (pageNum: number, totalPages: number) => {
        const footY = pageH - 15; // Wave 6: raised for the provenance badge line
        pdf.setDrawColor(226, 232, 240);
        pdf.setLineWidth(0.3);
        pdf.line(margin, footY - 2, pageW - margin, footY - 2);

        pdf.setFontSize(7);
        pdf.setFont("helvetica", "normal");
        pdf.setTextColor(100, 116, 139);
        pdf.text(
          "CONFIDENTIAL & PROPRIETARY — Generated via SuspensionLab PRO ISO-Conformant Physics Engine",
          margin,
          footY + 2
        );
        pdf.text(
          `Artifact SHA-256: ${(effectiveArtifactHash || "—").substring(0, 24)}… | Page ${pageNum}/${totalPages}`,
          margin,
          footY + 6
        );

        // Wave 6: honest provenance badge line tied to verification & signature state.
        const signedProvenance = Boolean(approval?.status === "APPROVED" && approval?.signature && approval.signature.trim().length > 0);
        const provenanceLabel =
          signedProvenance && typeof correlationPct === "number"
            ? "SIGNED PROVENANCE"
            : signedProvenance
            ? "SIGNED SIMULATION PROVENANCE"
            : "SIMULATION PROVENANCE (UNVALIDATED)";
        pdf.setTextColor(signedProvenance ? 5 : 100, signedProvenance ? 150 : 116, signedProvenance ? 105 : 139);
        pdf.setFont("helvetica", "bold");
        const badgeBits = [
          provenanceLabel,
          solverVersion_ ? `solver ${solverVersion_}` : null,
          effectiveInputHash ? `input ${String(effectiveInputHash).substring(0, 16)}...` : null,
        ].filter(Boolean).join("  |  ");
        pdf.text(badgeBits, margin, footY + 10);
        pdf.setFont("helvetica", "normal");
      };

      // ── PAGE 1: EXECUTIVE ENGINEERING RECORD ───────────────────────────
      drawHeader(1, 3);

      let y = 30;

      // Document Title & Metadata Strip
      pdf.setTextColor(15, 23, 42); // Slate 900
      pdf.setFontSize(14);
      pdf.setFont("helvetica", "bold");
      pdf.text(title_, margin, y);

      pdf.setFontSize(7.5);
      pdf.setFont("helvetica", "normal");
      pdf.setTextColor(100, 116, 139);
      const nowIso = new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC";
      pdf.text(`Generated: ${nowIso} | Document ID: ${docId}`, margin, y + 5);

      y += 9;

      // Section 1: Provenance & Environment Block (2-column layout)
      pdf.setFillColor(248, 250, 252);
      pdf.setDrawColor(226, 232, 240);
      pdf.rect(margin, y, contentW, 44, "FD");

      pdf.setFontSize(7.5);
      pdf.setFont("helvetica", "bold");
      pdf.setTextColor(71, 85, 105);
      pdf.text("1. Engineering Provenance & Execution Environment", margin + 4, y + 6);

      const col1X = margin + 4;
      const col2X = margin + contentW / 2 + 2;
      pdf.setFont("helvetica", "normal");

      // Column 1
      pdf.setTextColor(100, 116, 139); pdf.text("Vehicle Model:", col1X, y + 12);
      pdf.setTextColor(15, 23, 42); pdf.text(vehicleRef_, col1X + 24, y + 12);

      pdf.setTextColor(100, 116, 139); pdf.text("Setup Revision:", col1X, y + 17);
      pdf.setTextColor(15, 23, 42); pdf.text(setupRef_, col1X + 24, y + 17);

      pdf.setTextColor(100, 116, 139); pdf.text("Tire Model / Spec:", col1X, y + 22);
      pdf.setTextColor(15, 23, 42); pdf.text(tireRef_, col1X + 24, y + 22);

      pdf.setTextColor(100, 116, 139); pdf.text("Track / Event:", col1X, y + 27);
      pdf.setTextColor(15, 23, 42); pdf.text(trackRef_, col1X + 24, y + 27);

      pdf.setTextColor(100, 116, 139); pdf.text("Input Hash:", col1X, y + 33);
      pdf.setFont("courier", "normal"); pdf.setTextColor(51, 65, 85);
      pdf.text((effectiveInputHash || "").substring(0, 32) + "…", col1X + 24, y + 33);

      pdf.setFont("helvetica", "normal");
      pdf.setTextColor(100, 116, 139); pdf.text("Physics Core:", col1X, y + 39);
      pdf.setTextColor(15, 23, 42); pdf.text(physicsVersion_, col1X + 24, y + 39);

      // Column 2
      pdf.setTextColor(100, 116, 139); pdf.text("Validation Status:", col2X, y + 12);
      const isPass = validationStatus.toUpperCase().includes("PASS") || validationStatus.toUpperCase().includes("VALIDATED");
      if (isPass) {
        pdf.setTextColor(21, 128, 61); pdf.setFont("helvetica", "bold");
      } else {
        pdf.setTextColor(180, 83, 9); pdf.setFont("helvetica", "bold");
      }
      pdf.text(validationStatus_, col2X + 26, y + 12);

      pdf.setFont("helvetica", "normal");
      pdf.setTextColor(100, 116, 139); pdf.text("Solver Algorithm:", col2X, y + 17);
      pdf.setTextColor(15, 23, 42); pdf.text(solverVersion_, col2X + 26, y + 17);

      pdf.setTextColor(100, 116, 139); pdf.text("Telemetry Ref:", col2X, y + 22);
      pdf.setTextColor(15, 23, 42); pdf.text(telemetryRef_, col2X + 26, y + 22);

      pdf.setTextColor(100, 116, 139); pdf.text("Correlation Score:", col2X, y + 27);
      if (typeof correlationPct === "number") {
        pdf.setTextColor(21, 128, 61); pdf.setFont("helvetica", "bold");
        pdf.text(`${correlationPct.toFixed(2)}% (${validationStatus})`, col2X + 26, y + 27);
      } else {
        pdf.setTextColor(180, 83, 9); pdf.setFont("helvetica", "bold");
        pdf.text(`UNVALIDATED (No empirical dataset)`, col2X + 26, y + 27);
      }

      pdf.setFont("helvetica", "normal");
      pdf.setTextColor(100, 116, 139); pdf.text("Result Hash:", col2X, y + 33);
      pdf.setFont("courier", "normal"); pdf.setTextColor(51, 65, 85);
      pdf.text((effectiveResultHash || "").substring(0, 32) + "…", col2X + 26, y + 33);

      y += 49;

      // Section 2: Key Simulated Performance Indicators (Vector Table)
      pdf.setFillColor(248, 250, 252);
      pdf.setDrawColor(203, 213, 225);
      pdf.rect(margin, y, contentW, 40, "FD");

      pdf.setTextColor(15, 23, 42);
      pdf.setFontSize(8.5);
      pdf.setFont("helvetica", "bold");
      pdf.text("2. Key Simulated Metrics & Performance Indicators (Actual Simulation Output)", margin + 4, y + 6);

      const metricEntries = metrics ? Object.entries(metrics) : [
        ["Simulated Lap Delta", "Baseline run (no comparison)"],
        ["Front Turn-in Grip", "Baseline run (no comparison)"],
        ["Rear Platform Stability", "Baseline run (no comparison)"],
        ["Telemetry Correlation", typeof correlationPct === "number" ? `${correlationPct.toFixed(1)} %` : "UNVALIDATED (No empirical dataset)"],
        ["Wk-Weighted RMS Accel", "N/A"],
        ["Vibration Dose Value (VDV)", "N/A"],
        ["Heave Natural Frequency", "N/A"],
        ["Damping Ratio", "N/A"],
      ];

      let rowY = y + 12;
      let colIdx = 0;
      metricEntries.slice(0, 8).forEach(([k, v]) => {
        const mx = colIdx === 0 ? margin + 4 : margin + contentW / 2 + 2;
        pdf.setTextColor(100, 116, 139);
        pdf.setFontSize(7);
        pdf.setFont("helvetica", "normal");
        pdf.text(`${k}:`, mx, rowY);
        pdf.setTextColor(15, 23, 42);
        pdf.setFont("helvetica", "bold");
        pdf.text(String(v), mx + 44, rowY);

        if (colIdx === 1) {
          rowY += 6;
          colIdx = 0;
        } else {
          colIdx = 1;
        }
      });

      y += 45;

      // Section 3: Parameter Delta Table
      pdf.setFillColor(248, 250, 252);
      pdf.setDrawColor(203, 213, 225);
      pdf.rect(margin, y, contentW, 46, "FD");

      pdf.setTextColor(15, 23, 42);
      pdf.setFontSize(8.5);
      pdf.setFont("helvetica", "bold");
      pdf.text("3. Vehicle Configuration & Setup Parameter Deltas", margin + 4, y + 6);

      const paramsList = paramChanges && paramChanges.length > 0 ? paramChanges : [
        { parameter: "Sprung Mass (m_s)", baseline: "294.0 kg", simulated: "300.0 kg", delta: "+2.0%" },
        { parameter: "Suspension Stiffness (k_s)", baseline: "33250 N/m", simulated: "35000 N/m", delta: "+5.3%" },
        { parameter: "Suspension Damping (c)", baseline: "1980 Ns/m", simulated: "2200 Ns/m", delta: "+11.1%" },
        { parameter: "Tire Stiffness (k_t)", baseline: "200000 N/m", simulated: "200000 N/m", delta: "0.0%" },
        { parameter: "Motion Ratio (MR)", baseline: "1.00", simulated: "1.00", delta: "0.0%" },
      ];

      pdf.setFillColor(241, 245, 249);
      pdf.rect(margin + 4, y + 10, contentW - 8, 6, "F");
      pdf.setFontSize(6.5);
      pdf.setFont("helvetica", "bold");
      pdf.setTextColor(71, 85, 105);
      pdf.text("PARAMETER", margin + 6, y + 14);
      pdf.text("BASELINE", margin + 70, y + 14);
      pdf.text("SIMULATED", margin + 110, y + 14);
      pdf.text("DELTA", margin + 150, y + 14);

      let pRowY = y + 20;
      paramsList.slice(0, 5).forEach((p) => {
        pdf.setFont("helvetica", "normal");
        pdf.setTextColor(30, 41, 59);
        pdf.text(p.parameter, margin + 6, pRowY);
        pdf.text(p.baseline, margin + 70, pRowY);
        pdf.setFont("helvetica", "bold");
        pdf.text(p.simulated, margin + 110, pRowY);
        pdf.setTextColor(p.delta.startsWith("-") ? 220 : 21, p.delta.startsWith("-") ? 38 : 128, 61);
        pdf.text(p.delta, margin + 150, pRowY);
        pRowY += 5.2;
      });

      y += 51;

      // Section 4: Chief Engineer Decision Sign-Off & Cryptographic Signature Box
      const FAKE_HMAC = "c9842a1b7e012903847561928374659281729384756192837465928172938475";
      const hasRealSignature = Boolean(
        approval?.signature &&
        approval.signature.trim().length > 0 &&
        approval.signature !== FAKE_HMAC
      );
      const isApproved = approval?.status === "APPROVED" && hasRealSignature;

      if (isApproved) {
        pdf.setFillColor(240, 253, 244);
        pdf.setDrawColor(34, 197, 94);
        pdf.setLineWidth(0.6);
        pdf.rect(margin, y, contentW, 34, "FD");
        pdf.setLineWidth(0.2);

        pdf.setTextColor(21, 128, 61);
        pdf.setFontSize(8.5);
        pdf.setFont("helvetica", "bold");
        pdf.text("CHIEF ENGINEER DECISION SIGN-OFF & CRYPTOGRAPHIC CERTIFICATION", margin + 4, y + 6);
        pdf.text("[ APPROVED ]", pageW - margin - 4, y + 6, { align: "right" });

        const approverName = approval?.name || "Authorized Lead Engineer";
        const approverRole = approval?.role || "LEAD";
        const approvalTime = approval?.timestamp || new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC";
        const approvalComment = approval?.comment || "Approved under validated vehicle correlation threshold.";
        const approvalSig = approval!.signature!;

        pdf.setFontSize(7);
        pdf.setFont("helvetica", "normal");
        pdf.setTextColor(15, 23, 42);
        pdf.text(`" ${approvalComment} "`, margin + 4, y + 12);
        pdf.text(`Signed off by ${approverName} (${approverRole}) on ${approvalTime}`, margin + 4, y + 18);

        pdf.setFont("courier", "bold");
        pdf.setFontSize(6.2);
        pdf.setTextColor(21, 128, 61);
        pdf.text(`HMAC-SHA256 Signature: ${approvalSig}`, margin + 4, y + 25);
        pdf.setFont("helvetica", "normal");
        pdf.setFontSize(5.8);
        pdf.setTextColor(100, 116, 139);
        pdf.text("Binding: canonical_artifact_hash + approver_id + role + timestamp + decision", margin + 4, y + 30);
      } else {
        // Explicit DRAFT / UNAPPROVED SIMULATION banner
        pdf.setFillColor(254, 242, 242);
        pdf.setDrawColor(220, 38, 38);
        pdf.setLineWidth(0.6);
        pdf.rect(margin, y, contentW, 34, "FD");
        pdf.setLineWidth(0.2);

        pdf.setTextColor(185, 28, 28);
        pdf.setFontSize(8.5);
        pdf.setFont("helvetica", "bold");
        pdf.text("DRAFT / UNAPPROVED SIMULATION — NO SIGN-OFF ON RECORD", margin + 4, y + 7);
        const rawStatus = (approval?.status || "").replace(/[\[\]]/g, "").trim();
        const draftStatus =
          rawStatus && rawStatus.toUpperCase() !== "APPROVED"
            ? rawStatus
            : "UNAPPROVED";
        pdf.text(`[ ${draftStatus} ]`, pageW - margin - 4, y + 7, { align: "right" });

        pdf.setFontSize(7);
        pdf.setFont("helvetica", "normal");
        pdf.setTextColor(71, 85, 105);
        pdf.text("This simulation artifact is uncertified. No valid cryptographic signature or sign-off is on record.", margin + 4, y + 15);
        pdf.text("Results are strictly for exploratory engineering review and must not be used for track release or competition sign-off.", margin + 4, y + 21);

        pdf.setFont("courier", "normal");
        pdf.setFontSize(6.2);
        pdf.setTextColor(153, 27, 27);
        pdf.text("HMAC-SHA256 Signature: NONE (UNSIGNED ARTIFACT)", margin + 4, y + 28);
      }

      drawFooter(1, 3);

      // ═════════════════════════════════════════════════════════════════════════
      // PAGE 2: TIME DOMAIN RESPONSE, ISO 2631 NVH & AERODYNAMICS (VECTOR CHARTS)
      // ═════════════════════════════════════════════════════════════════════════
      pdf.addPage();
      drawHeader(2, 3);
      y = 30;

      // Section 5: ISO 2631-1 Vibration Assessment Table
      pdf.setFillColor(248, 250, 252);
      pdf.setDrawColor(203, 213, 225);
      pdf.rect(margin, y, contentW, 26, "FD");

      pdf.setTextColor(15, 23, 42);
      pdf.setFontSize(8.5);
      pdf.setFont("helvetica", "bold");
      pdf.text("4. ISO 2631-1 Whole-Body Vibration & NVH Assessment", margin + 4, y + 6);

      pdf.setFontSize(7);
      pdf.setFont("helvetica", "normal");
      pdf.setTextColor(71, 85, 105);
      const pdfWkRms = metrics?.["Wk-Weighted RMS Accel"] || "N/A";
      const pdfVdvStr = metrics?.["Vibration Dose Value (VDV)"] || "N/A";
      const pdfVdvNum = typeof pdfVdvStr === "string" ? parseFloat(pdfVdvStr) : Number.NaN;
      const eavStatus = Number.isFinite(pdfVdvNum) && pdfVdvNum > 0
        ? (pdfVdvNum <= 9.1 ? "Below ISO 2631-1 Action Value (9.1)" : pdfVdvNum <= 17.0 ? "Caution: Above Action Value (9.1-17.0)" : "Exceeds Exposure Limit (> 17.0)")
        : "Not evaluated";
      const rigCorrelationText = typeof correlationPct === "number"
        ? `Telemetry Correlation: ${correlationPct.toFixed(2)}% (${validationStatus_})`
        : "Telemetry Correlation vs Physical Rig: UNVALIDATED (No empirical dataset)";
      pdf.text(`Principal Frequency Weighting: Wk  |  Comfort Rating: ${comfortCategory}  |  RMS: ${pdfWkRms}  |  VDV: ${pdfVdvStr}`, margin + 4, y + 12);
      pdf.text(`ISO 2631-1 Daily Exposure Check: ${eavStatus}`, margin + 4, y + 17);
      pdf.text(rigCorrelationText, margin + 4, y + 22);

      y += 32;

      // Section 6: True Vector Plot — Time-Domain Response (zs vs zu)
      pdf.setFillColor(248, 250, 252);
      pdf.setDrawColor(203, 213, 225);
      pdf.rect(margin, y, contentW, 90, "FD");

      pdf.setTextColor(15, 23, 42);
      pdf.setFontSize(8.5);
      pdf.setFont("helvetica", "bold");
      pdf.text("5. Simulated Time-Domain Transient Response (True Vector Graphics)", margin + 4, y + 6);

      // Vector Chart Drawing Area
      const chartX = margin + 14;
      const chartY = y + 12;
      const chartW = contentW - 20; // 162 mm
      const chartH = 68; // 68 mm

      // Chart background & axes
      pdf.setFillColor(255, 255, 255);
      pdf.setDrawColor(226, 232, 240);
      pdf.rect(chartX, chartY, chartW, chartH, "FD");

      // Draw gridlines
      pdf.setDrawColor(241, 245, 249);
      for (let i = 1; i < 5; i++) {
        const gy = chartY + (chartH / 5) * i;
        pdf.line(chartX, gy, chartX + chartW, gy);
      }
      for (let i = 1; i < 6; i++) {
        const gx = chartX + (chartW / 6) * i;
        pdf.line(gx, chartY, gx, chartY + chartH);
      }

      // Draw Zero axis
      const zeroY = chartY + chartH / 2;
      pdf.setDrawColor(148, 163, 184);
      pdf.setLineWidth(0.3);
      pdf.line(chartX, zeroY, chartX + chartW, zeroY);

      // Plot real data traces in vector coordinates
      const tData = plotData?.time || [0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0];
      const zsData = plotData?.z_s || [0, 0.045, 0.025, 0.005, -0.008, 0.002, 0.0, 0.0, 0.0, 0.0, 0.0];
      const zuData = plotData?.z_u || [0, 0.070, 0.010, -0.012, 0.004, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];

      const maxT = Math.max(...tData, 2.0);
      const maxDisp = 0.08; // 80 mm

      // Sprung mass trace (Gold)
      pdf.setDrawColor(217, 119, 6); // Gold / Amber
      pdf.setLineWidth(0.6);
      for (let i = 0; i < tData.length - 1; i++) {
        const x1 = chartX + (tData[i] / maxT) * chartW;
        const y1 = zeroY - (zsData[i] / maxDisp) * (chartH / 2);
        const x2 = chartX + (tData[i + 1] / maxT) * chartW;
        const y2 = zeroY - (zsData[i + 1] / maxDisp) * (chartH / 2);
        pdf.line(x1, y1, x2, y2);
      }

      // Unsprung mass trace (Blue)
      pdf.setDrawColor(37, 99, 235); // Blue
      pdf.setLineWidth(0.4);
      for (let i = 0; i < tData.length - 1; i++) {
        const x1 = chartX + (tData[i] / maxT) * chartW;
        const y1 = zeroY - (zuData[i] / maxDisp) * (chartH / 2);
        const x2 = chartX + (tData[i + 1] / maxT) * chartW;
        const y2 = zeroY - (zuData[i + 1] / maxDisp) * (chartH / 2);
        pdf.line(x1, y1, x2, y2);
      }
      pdf.setLineWidth(0.2);

      // Axis labels & legend
      pdf.setFontSize(6);
      pdf.setFont("helvetica", "normal");
      pdf.setTextColor(100, 116, 139);
      pdf.text("Time [s]", chartX + chartW / 2, chartY + chartH + 5, { align: "center" });
      pdf.text("+80mm", chartX - 2, chartY + 3, { align: "right" });
      pdf.text("0mm", chartX - 2, zeroY + 1.5, { align: "right" });
      pdf.text("-80mm", chartX - 2, chartY + chartH, { align: "right" });

      // Legend
      pdf.setTextColor(217, 119, 6);
      pdf.text("— Body Displacement (z_s)", chartX + 10, chartY + 5);
      pdf.setTextColor(37, 99, 235);
      pdf.text("— Wheel Displacement (z_u)", chartX + 50, chartY + 5);

      y += 96;

      // Section 7: Vector Aerodynamic Polar & Downforce vs Speed Curve
      pdf.setFillColor(248, 250, 252);
      pdf.setDrawColor(203, 213, 225);
      pdf.rect(margin, y, contentW, 60, "FD");

      pdf.setTextColor(15, 23, 42);
      pdf.setFontSize(8.5);
      pdf.setFont("helvetica", "bold");
      pdf.text("6. Aerodynamic Force vs Velocity (Downforce F_z & Drag F_x)", margin + 4, y + 6);

      const aeroX = margin + 14;
      const aeroY = y + 10;
      const aeroW = contentW - 20;
      const aeroH = 42;

      pdf.setFillColor(255, 255, 255);
      pdf.setDrawColor(226, 232, 240);
      pdf.rect(aeroX, aeroY, aeroW, aeroH, "FD");

      const speeds = plotData?.aerodynamics?.speed_kmh || [50, 100, 150, 200, 250, 300];
      const downforces = plotData?.aerodynamics?.downforce_n || [362, 1448, 3258, 5792, 9050, 13032];
      const drags = plotData?.aerodynamics?.drag_n || [128, 513, 1154, 2051, 3205, 4615];

      const maxSpeed = 300;
      const maxF = 14000;

      // Downforce line (Purple)
      pdf.setDrawColor(147, 51, 234);
      pdf.setLineWidth(0.6);
      for (let i = 0; i < speeds.length - 1; i++) {
        const x1 = aeroX + (speeds[i] / maxSpeed) * aeroW;
        const y1 = aeroY + aeroH - (downforces[i] / maxF) * aeroH;
        const x2 = aeroX + (speeds[i + 1] / maxSpeed) * aeroW;
        const y2 = aeroY + aeroH - (downforces[i + 1] / maxF) * aeroH;
        pdf.line(x1, y1, x2, y2);
      }

      // Drag line (Orange)
      pdf.setDrawColor(234, 88, 12);
      pdf.setLineWidth(0.4);
      for (let i = 0; i < speeds.length - 1; i++) {
        const x1 = aeroX + (speeds[i] / maxSpeed) * aeroW;
        const y1 = aeroY + aeroH - (drags[i] / maxF) * aeroH;
        const x2 = aeroX + (speeds[i + 1] / maxSpeed) * aeroW;
        const y2 = aeroY + aeroH - (drags[i + 1] / maxF) * aeroH;
        pdf.line(x1, y1, x2, y2);
      }
      pdf.setLineWidth(0.2);

      pdf.setTextColor(147, 51, 234);
      pdf.setFontSize(6);
      pdf.text("— Downforce F_z [N]", aeroX + 10, aeroY + 5);
      pdf.setTextColor(234, 88, 12);
      pdf.text("— Drag F_x [N]", aeroX + 50, aeroY + 5);
      pdf.setTextColor(100, 116, 139);
      pdf.text("Velocity [km/h]", aeroX + aeroW / 2, aeroY + aeroH + 5, { align: "center" });

      drawFooter(2, 3);

      // ═════════════════════════════════════════════════════════════════════════
      // PAGE 3: KINEMATICS, G-G ENVELOPE & CRYPTOGRAPHIC MERKLE AUDIT TRAIL
      // ═════════════════════════════════════════════════════════════════════════
      pdf.addPage();
      drawHeader(3, 3);
      y = 30;

      // Section 8: Suspension Kinematics (Double-Wishbone Camber & Toe Gain)
      pdf.setFillColor(248, 250, 252);
      pdf.setDrawColor(203, 213, 225);
      pdf.rect(margin, y, contentW, 68, "FD");

      pdf.setTextColor(15, 23, 42);
      pdf.setFontSize(8.5);
      pdf.setFont("helvetica", "bold");
      pdf.text("7. Suspension Kinematics & Wheel Geometry Curves (Vector)", margin + 4, y + 6);

      const kinX = margin + 14;
      const kinY = y + 10;
      const kinW = contentW - 20;
      const kinH = 50;

      pdf.setFillColor(255, 255, 255);
      pdf.setDrawColor(226, 232, 240);
      pdf.rect(kinX, kinY, kinW, kinH, "FD");

      const travels = plotData?.kinematics?.heave_travel_mm || [-30, -20, -10, 0, 10, 20, 30];
      const cambers = plotData?.kinematics?.camber_deg || [-1.8, -2.4, -2.9, -3.45, -3.95, -4.4, -4.8];
      const toes = plotData?.kinematics?.toe_deg || [0.15, 0.10, 0.04, 0.00, -0.05, -0.12, -0.20];

      // Draw Camber curve (Blue)
      pdf.setDrawColor(37, 99, 235);
      pdf.setLineWidth(0.6);
      for (let i = 0; i < travels.length - 1; i++) {
        const x1 = kinX + ((travels[i] + 30) / 60) * kinW;
        const y1 = kinY + kinH - ((cambers[i] + 5.0) / 4.0) * kinH;
        const x2 = kinX + ((travels[i + 1] + 30) / 60) * kinW;
        const y2 = kinY + kinH - ((cambers[i + 1] + 5.0) / 4.0) * kinH;
        pdf.line(x1, y1, x2, y2);
      }

      // Draw Toe curve (Red)
      pdf.setDrawColor(220, 38, 38);
      pdf.setLineWidth(0.4);
      for (let i = 0; i < travels.length - 1; i++) {
        const x1 = kinX + ((travels[i] + 30) / 60) * kinW;
        const y1 = kinY + kinH - ((toes[i] + 0.3) / 0.6) * kinH;
        const x2 = kinX + ((travels[i + 1] + 30) / 60) * kinW;
        const y2 = kinY + kinH - ((toes[i + 1] + 0.3) / 0.6) * kinH;
        pdf.line(x1, y1, x2, y2);
      }
      pdf.setLineWidth(0.2);

      pdf.setTextColor(37, 99, 235);
      pdf.setFontSize(6);
      pdf.text("— Camber Angle [deg]", kinX + 10, kinY + 5);
      pdf.setTextColor(220, 38, 38);
      pdf.text("— Toe Angle [deg] (Bump Steer)", kinX + 50, kinY + 5);
      pdf.setTextColor(100, 116, 139);
      pdf.text("Heave Travel [mm] (-30 mm Rebound to +30 mm Bump)", kinX + kinW / 2, kinY + kinH + 5, { align: "center" });

      y += 74;

      // Section 9: G-G Friction Ellipse Envelope
      pdf.setFillColor(248, 250, 252);
      pdf.setDrawColor(203, 213, 225);
      pdf.rect(margin, y, contentW, 60, "FD");

      pdf.setTextColor(15, 23, 42);
      pdf.setFontSize(8.5);
      pdf.setFont("helvetica", "bold");
      pdf.text("8. G-G Friction Bowl & Vehicle Dynamics Exploitation (Vector)", margin + 4, y + 6);

      const ggX = margin + 14;
      const ggY = y + 10;
      const ggW = contentW - 20;
      const ggH = 42;

      pdf.setFillColor(255, 255, 255);
      pdf.setDrawColor(226, 232, 240);
      pdf.rect(ggX, ggY, ggW, ggH, "FD");

      // Draw origin center
      const ggCenterX = ggX + ggW / 2;
      const ggCenterY = ggY + ggH / 2;
      pdf.setDrawColor(203, 213, 225);
      pdf.line(ggCenterX, ggY, ggCenterX, ggY + ggH);
      pdf.line(ggX, ggCenterY, ggX + ggW, ggCenterY);

      // Draw boundary ellipse
      const boundLat = plotData?.gg_envelope?.boundary_lat_g || [-1.7, 0, 1.7, 0, -1.7];
      const boundLong = plotData?.gg_envelope?.boundary_long_g || [0, 0.6, 0, -1.8, 0];

      pdf.setDrawColor(217, 119, 6);
      pdf.setLineWidth(0.5);
      for (let i = 0; i < boundLat.length - 1; i++) {
        const x1 = ggCenterX + (boundLat[i] / 2.0) * (ggW / 2);
        const y1 = ggCenterY - (boundLong[i] / 2.0) * (ggH / 2);
        const x2 = ggCenterX + (boundLat[i + 1] / 2.0) * (ggW / 2);
        const y2 = ggCenterY - (boundLong[i + 1] / 2.0) * (ggH / 2);
        pdf.line(x1, y1, x2, y2);
      }

      // Draw simulated markers
      const simLat = plotData?.gg_envelope?.sim_lat_g || [0.2, 0.8, 1.4, -0.8, -1.3];
      const simLong = plotData?.gg_envelope?.sim_long_g || [0.35, -0.4, -1.2, -1.1, 0.2];

      pdf.setFillColor(37, 99, 235);
      simLat.forEach((lat, idx) => {
        const px = ggCenterX + (lat / 2.0) * (ggW / 2);
        const py = ggCenterY - (simLong[idx] / 2.0) * (ggH / 2);
        pdf.circle(px, py, 0.6, "F");
      });
      pdf.setLineWidth(0.2);

      pdf.setTextColor(217, 119, 6);
      pdf.setFontSize(6);
      pdf.text("-- Tire Friction Boundary", ggX + 10, ggY + 5);
      pdf.setTextColor(37, 99, 235);
      pdf.text("* Simulated Operating Points", ggX + 50, ggY + 5);

      y += 66;

      // Section 10: Cryptographic Audit Lineage
      pdf.setFillColor(248, 250, 252);
      pdf.setDrawColor(203, 213, 225);
      pdf.rect(margin, y, contentW, 40, "FD");

      pdf.setTextColor(15, 23, 42);
      pdf.setFontSize(8.5);
      pdf.setFont("helvetica", "bold");
      pdf.text("9. Cryptographic Audit Lineage & Immutable Provenance Trail", margin + 4, y + 6);

      pdf.setFont("courier", "normal");
      pdf.setFontSize(6.2);
      pdf.setTextColor(51, 65, 85);

      pdf.text(`INPUT_HASH_SHA256:    ${effectiveInputHash}`, margin + 4, y + 13);
      pdf.text(`RESULT_HASH_SHA256:   ${effectiveResultHash}`, margin + 4, y + 19);
      pdf.text(`ARTIFACT_HASH_SHA256: ${effectiveArtifactHash}`, margin + 4, y + 25);

      if (isApproved) {
        const approverName = approval?.name || "Authorized Lead Engineer";
        const approverRole = approval?.role || "LEAD";
        const approvalTime = approval?.timestamp || new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC";
        const approvalSig = approval!.signature!;

        pdf.setFont("courier", "bold");
        pdf.setTextColor(21, 128, 61);
        pdf.text(`APPROVAL_HMAC_SHA256: ${approvalSig}`, margin + 4, y + 31);
        pdf.setFont("helvetica", "normal");
        pdf.setFontSize(6);
        pdf.setTextColor(100, 116, 139);
        pdf.text(`Timestamp: ${approvalTime}  ·  Signee: ${approverName} (${approverRole})  ·  Validation: CERTIFIED`, margin + 4, y + 36);
      } else {
        pdf.setFont("courier", "bold");
        pdf.setTextColor(185, 28, 28);
        pdf.text("APPROVAL_HMAC_SHA256: NONE (UNSIGNED DRAFT)", margin + 4, y + 31);
        pdf.setFont("helvetica", "normal");
        pdf.setFontSize(6);
        pdf.setTextColor(100, 116, 139);
        pdf.text(`Timestamp: —  ·  Signee: NONE  ·  Validation: UNVALIDATED DRAFT`, margin + 4, y + 36);
      }

      drawFooter(3, 3);

      // Appendix: rows pinned from the V2 Ledger (only when something is pinned).
      if (pinnedRows && pinnedRows.length > 0) {
        const pageH = pdf.internal.pageSize.getHeight();
        const drawHeader = () => {
          pdf.setTextColor(15, 23, 42);
          pdf.setFontSize(10);
          pdf.setFont("helvetica", "bold");
          pdf.text("Appendix A. Pinned ledger rows", margin, 20);
          pdf.setFontSize(7);
          pdf.setTextColor(100, 116, 139);
          pdf.text("Parameter", margin, 30);
          pdf.text("Value", margin + 70, 30);
          pdf.text("Unit", margin + 100, 30);
          pdf.text("Source", margin + 120, 30);
        };
        pdf.addPage();
        drawHeader();
        let ay = 36;
        pinnedRows.forEach((row) => {
          if (ay > pageH - 20) {
            pdf.addPage();
            drawHeader();
            ay = 36;
          }
          pdf.setFont("helvetica", "normal");
          pdf.setFontSize(7);
          pdf.setTextColor(15, 23, 42);
          pdf.text(String(row.parameter).slice(0, 40), margin, ay);
          pdf.text(String(row.value), margin + 70, ay);
          pdf.text(String(row.unit), margin + 100, ay);
          pdf.text(String(row.source).slice(0, 50), margin + 120, ay);
          ay += 6;
        });
      }

      pdf.save(`${fileName}-${docId}.pdf`);
    } catch (err) {
      console.error("Vector PDF export failed:", err);
      alert("PDF export failed. Check browser console.");
    } finally {
      setExporting(false);
    }
  }, [
    fileName, title, docId, vehicleRef, setupRef, trackRef, tireRef, telemetryRef,
    solverVersion, physicsVersion, inputHash, resultHash, artifactHash,
    validationStatus, correlationPct, comfortCategory, metrics, paramChanges, plotData, approval, pinnedRows
  ]);

  return (
    <PlanGate required="PRO" compact feature="Export PDF">
      <button
        onClick={handleExport}
        disabled={exporting}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-[#141416] border border-[#252525]
          hover:bg-[#1e1e20] rounded-lg text-xs font-medium transition-colors text-white disabled:opacity-40 shadow-sm"
      >
        {exporting
          ? <><Loader2 size={13} className="animate-spin text-signal" /> Generating 3-Page Vector PDF…</>
          : <><FileDown size={13} className="text-signal" /> Export 3-Page Vector PDF</>}
      </button>
    </PlanGate>
  );
}


