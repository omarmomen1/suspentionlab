import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Half-Car 4-DOF Studio | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
