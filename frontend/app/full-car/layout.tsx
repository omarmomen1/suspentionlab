import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Full-Car 7-DOF Studio | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
