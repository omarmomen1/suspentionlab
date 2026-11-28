import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Setup Engineering & Decisions | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
