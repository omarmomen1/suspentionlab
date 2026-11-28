import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Engineering Memory | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
