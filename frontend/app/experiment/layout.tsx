import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Controlled Experiment Lab | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
