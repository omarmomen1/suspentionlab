import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle2, XCircle, Zap, Globe, Cpu, Banknote, ArrowRight } from "lucide-react";

export const metadata: Metadata = {
  title: "The Modern Alternative to MSC Adams for Suspension Kinematics | SuspensionLab",
  description:
    "Looking for an alternative to MSC Adams or MATLAB for vehicle dynamics? SuspensionLab runs instantly in your browser on Mac, PC, or phone with $0 setup cost and a built-in AI Race Engineer.",
  openGraph: {
    title: "The Modern Alternative to MSC Adams — SuspensionLab",
    description: "Cloud-native suspension simulation. No 20GB downloads, no licensing servers.",
  },
};

export default function CompareAdamsPage() {
  const comparisonData = [
    {
      feature: "Setup Cost & Licensing",
      adams: "$10,000+ per seat / Annual",
      us: "Start Free, $49/mo Pro",
      winner: "us",
    },
    {
      feature: "Installation",
      adams: "20GB+ Download, License Servers",
      us: "Instant. Runs in Chrome/Safari",
      winner: "us",
    },
    {
      feature: "Platform Support",
      adams: "Windows Only",
      us: "Mac, Windows, Linux, iOS, Android",
      winner: "us",
    },
    {
      feature: "Learning Curve",
      adams: "Weeks of training required",
      us: "Minutes. Built for modern engineers",
      winner: "us",
    },
    {
      feature: "Simulation Speed",
      adams: "Can be slow on local machines",
      us: "Instant cloud parallel processing",
      winner: "us",
    },
    {
      feature: "AI Integration",
      adams: "None",
      us: "Built-in Gemini AI Race Engineer",
      winner: "us",
    },
    {
      feature: "Collaboration",
      adams: "Emailing proprietary files",
      us: "One-click shareable web links",
      winner: "us",
    },
  ];

  return (
    <div className="min-h-screen bg-[#050505] text-white selection:bg-[#f2a900] selection:text-black">
      {/* Navbar */}
      <nav className="border-b border-white/10 sticky top-0 bg-[#050505]/80 backdrop-blur-md z-50">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/" className="font-bold text-xl tracking-tight flex items-center gap-2">
            <span className="text-[#f2a900]">Suspension</span>Lab
          </Link>
          <div className="flex gap-4">
            <Link href="/" className="text-sm font-medium text-gray-300 hover:text-white transition-colors py-2">
              Back to Home
            </Link>
            <Link
              href="/"
              className="px-5 py-2 rounded-lg bg-white text-black text-sm font-bold hover:bg-gray-200 transition-all"
            >
              Start Free
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <header className="relative pt-32 pb-20 overflow-hidden">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-[#f2a900]/20 blur-[120px] rounded-full pointer-events-none" />
        
        <div className="max-w-4xl mx-auto px-6 text-center relative z-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[#f2a900]/30 bg-[#f2a900]/10 text-[#f2a900] text-xs font-semibold uppercase tracking-wider mb-8">
            <Zap size={14} />
            The Next Generation of CAE
          </div>
          <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight mb-8 leading-[1.1]">
            The Modern Alternative to <span className="text-gray-400">Legacy Desktop CAE</span>
          </h1>
          <p className="text-xl text-gray-400 mb-10 max-w-2xl mx-auto leading-relaxed">
            Stop fighting with legacy 90s software interfaces, 20GB downloads, and archaic license servers. 
            Experience cloud-native suspension simulation that runs instantly on any device.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href="/"
              className="w-full sm:w-auto px-8 py-4 rounded-xl bg-[#f2a900] text-black font-bold text-lg hover:brightness-110 transition-all flex items-center justify-center gap-2 shadow-[0_0_40px_rgba(242,169,0,0.3)]"
            >
              Try SuspensionLab Free <ArrowRight size={18} />
            </Link>
          </div>
        </div>
      </header>

      {/* Value Props */}
      <section className="py-24 bg-[#0a0a0a]">
        <div className="max-w-6xl mx-auto px-6">
          <div className="grid md:grid-cols-3 gap-8">
            <div className="p-8 rounded-2xl border border-white/10 bg-[#111] hover:border-[#f2a900]/50 transition-colors">
              <Banknote className="text-[#f2a900] mb-4" size={32} />
              <h3 className="text-xl font-bold mb-3">$0 Setup Cost</h3>
              <p className="text-gray-400 leading-relaxed">
                Legacy dynamics software costs tens of thousands of dollars per seat. We built SuspensionLab for modern engineering teams: zero implementation fees, clear monthly SaaS pricing.
              </p>
            </div>
            <div className="p-8 rounded-2xl border border-white/10 bg-[#111] hover:border-[#f2a900]/50 transition-colors">
              <Globe className="text-[#f2a900] mb-4" size={32} />
              <h3 className="text-xl font-bold mb-3">Runs on Mac & Phone</h3>
              <p className="text-gray-400 leading-relaxed">
                Tethered to a heavy Windows workstation? Not anymore. Since physics are computed instantly in the cloud, you can run complex full-car simulations on a MacBook or even an iPad trackside.
              </p>
            </div>
            <div className="p-8 rounded-2xl border border-white/10 bg-[#111] hover:border-[#f2a900]/50 transition-colors">
              <Cpu className="text-[#f2a900] mb-4" size={32} />
              <h3 className="text-xl font-bold mb-3">AI Race Engineer</h3>
              <p className="text-gray-400 leading-relaxed">
                The world&apos;s first simulation tool with an integrated AI. Type &quot;the car understeers on corner exit&quot;, and our AI runs 20+ physics variations to recommend exactly which spring to change.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Comparison Table */}
      <section className="py-24">
        <div className="max-w-5xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-5xl font-bold mb-4">How we compare</h2>
            <p className="text-xl text-gray-400">Head-to-head against legacy desktop software.</p>
          </div>

          <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#111]">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-[#1a1a1a]">
                  <th className="p-6 font-semibold text-gray-400 border-b border-white/10 w-1/3">Feature</th>
                  <th className="p-6 font-bold text-gray-500 border-b border-white/10 w-1/3 border-l border-white/5">Legacy Desktop Software</th>
                  <th className="p-6 font-bold text-white border-b border-white/10 w-1/3 border-l border-white/5 bg-[#f2a900]/10">SuspensionLab Pro</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10">
                {comparisonData.map((row, idx) => (
                  <tr key={idx} className="hover:bg-white/[0.02] transition-colors">
                    <td className="p-6 font-medium text-gray-300">{row.feature}</td>
                    <td className="p-6 text-gray-500 border-l border-white/5 flex items-center gap-3">
                      <XCircle size={16} className="shrink-0 text-red-500/50" />
                      {row.adams}
                    </td>
                    <td className="p-6 font-semibold text-white border-l border-white/5 bg-[#f2a900]/5 flex items-center gap-3">
                      <CheckCircle2 size={16} className="shrink-0 text-[#f2a900]" />
                      {row.us}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-32 bg-gradient-to-b from-[#050505] to-[#111] border-t border-white/10">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <h2 className="text-4xl md:text-5xl font-bold mb-8">Ready to upgrade your engineering stack?</h2>
          <p className="text-xl text-gray-400 mb-10">
            Join the teams that are moving away from legacy desktop software to the cloud-native future.
          </p>
          <Link
            href="/"
            className="inline-flex items-center justify-center gap-2 px-10 py-5 rounded-2xl bg-white text-black font-bold text-lg hover:bg-gray-200 transition-all shadow-xl"
          >
            Start Your Free Simulation <ArrowRight size={20} />
          </Link>
        </div>
      </section>
    </div>
  );
}
