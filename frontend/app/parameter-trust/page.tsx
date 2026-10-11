import type { Metadata } from "next";
import { ParameterTrustMap } from "../../components/engineering/ParameterTrustMap";

export const metadata: Metadata = {
  title: "Parameter Trust Map — SuspensionLab PRO",
  description:
    "Authoritative provenance-aware parameter trust layer connecting engineering parameters to supporting evidence and validation history.",
};

export default function ParameterTrustPage() {
  return (
    <main className="min-h-screen bg-[#08090a] text-white pt-20 pb-16 px-4 md:px-8">
      <ParameterTrustMap />
    </main>
  );
}
