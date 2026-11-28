import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Workspace Onboarding | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
