import type { Metadata } from "next";
import { notFound } from "next/navigation";
import ReportClient from "./ReportClient";

const RAW_API_BASE = (process.env.BACKEND_URL || "http://127.0.0.1:8000/api/v1").replace(/\/+$/, "");
const API_BASE = RAW_API_BASE.endsWith("/api/v1") ? RAW_API_BASE : `${RAW_API_BASE}/api/v1`;

async function getReport(token: string) {
  try {
    const resp = await fetch(`${API_BASE}/reports/${token}`, {
      next: { revalidate: 60 },
    });
    if (!resp.ok) return null;
    return resp.json();
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: { params: { token: string } }): Promise<Metadata> {
  const report = await getReport(params.token);
  if (!report) return { title: "Report Not Found — SuspensionLab" };
  return {
    title: `${report.title} — SuspensionLab`,
    description: `Suspension simulation analysis. Views: ${report.view_count}`,
    openGraph: {
      title: report.title,
      description: "Professional suspension simulation by SuspensionLab",
      siteName: "SuspensionLab",
      images: [`/api/og?token=${report.token}`],
    },
  };
}

export default async function ReportPage({ params }: { params: { token: string } }) {
  const report = await getReport(params.token);
  if (!report) return notFound();
  return <ReportClient report={report} />;
}
