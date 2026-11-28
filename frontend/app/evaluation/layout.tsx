import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "7-Day Engineering Evaluation | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
