import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Setup Comparison | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
