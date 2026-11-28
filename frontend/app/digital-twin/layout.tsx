import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Digital Twin Diagnostics | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
