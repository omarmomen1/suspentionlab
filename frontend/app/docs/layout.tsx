import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Documentation & Solver Reference | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
