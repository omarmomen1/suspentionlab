import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Solver Interoperability | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
