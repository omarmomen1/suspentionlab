import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Engineering Decision Timeline | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
