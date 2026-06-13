import type { Metadata } from "next";
import { notFound } from "next/navigation";
import dynamic from "next/dynamic";

// Dynamically import to handle SSR
const ReportClient = dynamic(() => import("./ReportClient"), { ssr: false });

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
    },
  };
}

export default async function ReportPage({ params }: { params: { token: string } }) {
  const report = await getReport(params.token);
  if (!report) return notFound();
  return <ReportClient report={report} />;
}
