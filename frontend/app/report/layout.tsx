import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Engineering Sign-Off Report | SuspensionLab",
};

export default function RouteLayout({ children }: { children: React.ReactNode }) {
  return children;
}
