import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Steady-State Handling Studio | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
