import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Telemetry Correlation | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
