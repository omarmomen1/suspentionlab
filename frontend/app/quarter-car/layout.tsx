import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Quarter-Car 2-DOF Studio | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
