import { ImageResponse } from "@vercel/og";
import { NextRequest } from "next/server";

export const runtime = "edge";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const token = searchParams.get("token");

    if (!token) {
      return new ImageResponse(<div style={{ background: "black", color: "white" }}>Invalid Token</div>, { width: 1200, height: 630 });
    }

    const res = await fetch(`${API_BASE}/reports/${token}`);
    if (!res.ok) {
      return new ImageResponse(<div style={{ background: "black", color: "white" }}>Report Not Found</div>, { width: 1200, height: 630 });
    }

    const report = await res.json();
    const r = report?.result;

    const comfort = r?.comfort_rating || (r?.lapTime != null ? `Lap: ${r.lapTime.toFixed(3)}s` : "Simulation Result");
    const title = report?.title || "Suspension Analysis";

    return new ImageResponse(
      (
        <div
          style={{
            background: "#080808",
            width: "100%",
            height: "100%",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: "sans-serif",
            border: "12px solid #1a1a1a",
          }}
        >
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              background: "#111",
              padding: "40px 80px",
              borderRadius: "24px",
              border: "2px solid #222",
            }}
          >
            <h2 style={{ fontSize: 32, color: "#f2a900", margin: 0, textTransform: "uppercase", letterSpacing: "2px" }}>
              SuspensionLab Report
            </h2>
            <h1 style={{ fontSize: 72, color: "white", margin: "20px 0 40px 0", textAlign: "center", fontWeight: "bold" }}>
              {title}
            </h1>
            
            <div style={{ display: "flex", gap: "40px" }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                <span style={{ fontSize: 24, color: "#888", marginBottom: "8px" }}>Comfort Rating</span>
                <span style={{ fontSize: 48, color: "#fff", fontWeight: "bold" }}>{comfort}</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                <span style={{ fontSize: 24, color: "#888", marginBottom: "8px" }}>Peak Body Accel</span>
                <span style={{ fontSize: 48, color: "#fff", fontWeight: "bold" }}>
                  {typeof r?.rms_body_accel === "number" ? r.rms_body_accel.toFixed(2) : "—"} m/s²
                </span>
              </div>
            </div>
          </div>
          
          <div style={{ position: "absolute", bottom: 40, fontSize: 24, color: "#666" }}>
            Generated with SuspensionLab.io
          </div>
        </div>
      ),
      {
        width: 1200,
        height: 630,
      }
    );
  } catch (e: unknown) {
    console.log(`${(e as Error).message}`);
    return new Response(`Failed to generate the image`, {
      status: 500,
    });
  }
}
