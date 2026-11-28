"use client";

import React from "react";
import Link from "next/link";
import { Check, Zap, Shield, Building2, ArrowRight, ExternalLink } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";

const PLANS = [
  {
    name: "Starter",
    planKey: "FREE",
    price: "Free",
    billing: "forever",
    description: "3D Kinematics & Quarter-Car Preview. Free account required.",
    color: "border-[#252525]",
    badge: null,
    features: [
      "3D Kinematics & Quarter-Car Preview",
      "5 saved configurations",
      "Transmissibility & Bode plots",
      "ISO 2631-1 comfort analysis",
      "Community support",
      "Requires a free account (signed-out solves are rejected)",
    ],
    cta: "Get Started Free",
    ctaHref: "/quarter-car",
    ctaStyle: "bg-[#1e1e20] border border-[#333] text-white hover:bg-[#2a2a2c]",
    icon: Zap,
  },
  {
    name: "Pro Engineer",
    planKey: "PRO",
    price: "$79",
    billing: "/ month",
    description: "Full-Car, Damper LUTs, Telemetry Correlation, Setup Optimizer & PDF Reports.",
    color: "border-signal",
    badge: "Most Popular",
    features: [
      "Everything in Starter",
      "Full-Car (7-DOF) & Half-Car (4-DOF)",
      "Damper LUTs & nonlinear curves",
      "Telemetry Correlation",
      "Setup Optimizer & AI Auto-Tune",
      "PDF Reports & unlimited configs",
      "Priority email support",
    ],
    cta: "Activate License Key →",
    ctaHref: "/settings#billing",
    ctaStyle: "bg-signal text-carbon font-bold border border-signal hover:bg-[#d6f56e]",
    icon: Shield,
  },
  {
    name: "Race Team & Consultancy Pass",
    planKey: "ENTERPRISE",
    price: "$499",
    billing: "/ year",
    description: "Up to 10 Seats, Engineering Memory, Shared Reports & FMI Co-Sim.",
    color: "border-[#252525]",
    badge: null,
    features: [
      "Everything in Pro Engineer",
      "Up to 10 team seats",
      "Engineering Memory",
      "Shared Reports",
      "FMI Co-Sim (FMU / Simulink / ADAMS)",
      "Audit logs & REST API access",
      "Direct team invoicing & SLA support",
    ],
    cta: "Activate Team Pass",
    ctaHref: "/settings#billing",
    ctaStyle: "bg-[#1e1e20] border border-[#333] text-white hover:bg-[#2a2a2c]",
    icon: Building2,
  },
];

const FAQS = [
  {
    q: "Can I switch plans later?",
    a: "Yes — upgrade anytime using a Gumroad license key or a direct team key. When you upgrade, you get instant access to all unlocked studio modules.",
  },
  {
    q: "What physics models are included in each tier?",
    a: "Starter includes 3D Kinematics & Quarter-Car Preview. Pro Engineer ($79/month) unlocks Full-Car (7-DOF), Damper LUTs, Telemetry Correlation, Setup Optimizer, and PDF Reports. Race Team & Consultancy Pass ($499/year) adds up to 10 seats, Engineering Memory, Shared Reports, and FMI Co-Sim.",
  },
  {
    q: "How do I activate my license after purchasing?",
    a: "After checkout on Gumroad (or direct team invoicing), copy your license key and paste it in Settings → Billing (/settings#billing) for instant activation.",
  },
  {
    q: "Do you offer direct invoicing for Formula Student / FSAE or OEM teams?",
    a: "Yes. Teams can purchase the Race Team & Consultancy Pass directly or request a direct invoice and SLPRO team license key by contacting our engineering team.",
  },
];

export default function PricingPage() {
  const { user } = useAuth();
  const currentPlanKey = (user?.plan || "FREE").toUpperCase();
  const gumroadProUrl = process.env.NEXT_PUBLIC_GUMROAD_PRO_URL?.trim() || "";
  const gumroadTeamUrl = process.env.NEXT_PUBLIC_GUMROAD_TEAM_URL?.trim() || "";

  return (
    <div className="min-h-full bg-black pt-[44px]">
      <div className="max-w-6xl mx-auto px-6 py-20">

        {/* Header */}
        <div className="text-center mb-16">
          <span className="text-xs font-bold tracking-[0.25em] text-signal uppercase">Pricing & Plans</span>
          <h1 className="text-5xl font-semibold tracking-tight text-white mt-3 mb-4">
            Simple, transparent engineering tiers
          </h1>
          <p className="text-zinc-400 text-lg max-w-xl mx-auto">
            Every tier includes the core physics engine. Upgrade for full-car dynamics, damper LUTs, telemetry correlation, and team collaboration.
          </p>
        </div>

        {/* Plans grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-20">
          {PLANS.map((plan) => {
            const Icon = plan.icon;
            const isCurrentPlan = user && plan.planKey === currentPlanKey;
            const isEnterpriseUser = user && currentPlanKey === "ENTERPRISE";

            let ctaText = plan.cta;
            let ctaHref = plan.ctaHref;
            let ctaStyle = plan.ctaStyle;

            if (isCurrentPlan) {
              ctaText = "Current Plan — Launch Simulator";
              ctaHref = "/quarter-car";
              ctaStyle = "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold hover:bg-emerald-500/30";
            } else if (isEnterpriseUser) {
              ctaText = "Included in Team Pass";
              ctaHref = "/quarter-car";
              ctaStyle = "bg-white/10 text-white border border-white/20 hover:bg-white/20";
            } else if (!user && plan.planKey === "FREE") {
              ctaText = "Get Started Free";
              ctaHref = "/auth/register";
            }

            const showProGumroad =
              !isCurrentPlan && !isEnterpriseUser && plan.planKey === "PRO" && Boolean(gumroadProUrl);
            const showTeamGumroad =
              !isCurrentPlan && plan.planKey === "ENTERPRISE" && Boolean(gumroadTeamUrl);

            return (
              <div
                key={plan.name}
                className={`relative bg-[#0d0d0f] border ${isCurrentPlan ? "border-emerald-500/50 shadow-[0_0_30px_rgba(16,185,129,0.15)]" : plan.color} rounded-2xl p-8 flex flex-col`}
              >
                {isCurrentPlan ? (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="px-3 py-1 bg-emerald-500 text-black text-xs font-bold uppercase tracking-wider rounded-full">
                      Your Active Plan
                    </span>
                  </div>
                ) : plan.badge && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="px-3 py-1 bg-signal text-carbon text-xs font-bold uppercase tracking-wider rounded-full">
                      {plan.badge}
                    </span>
                  </div>
                )}

                <div className="mb-6">
                  <div className="flex items-center gap-2 mb-3">
                    <Icon size={16} className={isCurrentPlan ? "text-emerald-400" : "text-signal"} />
                    <span className="text-xs font-bold text-zinc-400 uppercase tracking-widest">{plan.name}</span>
                  </div>
                  <div className="flex items-end gap-1.5 mb-2">
                    <span className="text-4xl font-bold text-white">{plan.price}</span>
                    {plan.price !== "Free" && plan.price !== "Custom" && (
                      <span className="text-zinc-300 text-sm mb-1">{plan.billing}</span>
                    )}
                  </div>
                  <p className="text-sm text-zinc-400">{plan.description}</p>
                </div>

                <ul className="space-y-3 mb-8 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5">
                      <Check size={14} className="text-emerald-500 mt-0.5 shrink-0" />
                      <span className="text-sm text-gray-300">{f}</span>
                    </li>
                  ))}
                </ul>

                {showProGumroad ? (
                  <div className="space-y-2.5">
                    <a
                      href={gumroadProUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`w-full py-3 rounded-xl text-sm transition-all flex items-center justify-center gap-2 ${plan.ctaStyle}`}
                    >
                      Buy on Gumroad ($79) <ExternalLink size={14} />
                    </a>
                    <Link
                      href="/settings#billing"
                      className="w-full py-2.5 rounded-xl text-xs font-semibold text-gray-300 bg-[#161618] border border-[#2a2a2e] hover:text-white hover:border-[#3c3c42] transition-all flex items-center justify-center gap-1.5"
                    >
                      Activate License Key →
                    </Link>
                  </div>
                ) : showTeamGumroad ? (
                  <div className="space-y-2.5">
                    <a
                      href={gumroadTeamUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`w-full py-3 rounded-xl text-sm transition-all flex items-center justify-center gap-2 ${plan.ctaStyle}`}
                    >
                      Buy Team Pass ($499/yr) <ExternalLink size={14} />
                    </a>
                    <Link
                      href="/settings#billing"
                      className="w-full py-2.5 rounded-xl text-xs font-semibold text-gray-300 bg-[#161618] border border-[#2a2a2e] hover:text-white hover:border-[#3c3c42] transition-all flex items-center justify-center gap-1.5"
                    >
                      Activate License Key →
                    </Link>
                  </div>
                ) : (
                  <Link
                    href={ctaHref}
                    className={`w-full py-3 rounded-xl text-sm transition-all flex items-center justify-center gap-2 ${ctaStyle}`}
                  >
                    {ctaText} <ArrowRight size={14} />
                  </Link>
                )}

                {plan.planKey === "ENTERPRISE" && (
                  <div className="mt-4 p-3 rounded-xl bg-purple-950/30 border border-purple-500/20 text-xs text-purple-200 text-center leading-relaxed">
                    <span className="font-semibold text-purple-300">University Formula Student (FSAE / Formula Bharat / FSG) teams:</span> Use code <span className="font-mono font-bold text-signal">FSAE50</span> at checkout for 50% academic sponsorship ($249/yr).
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* FAQ */}
        <div className="max-w-2xl mx-auto">
          <h2 className="text-2xl font-semibold text-white text-center mb-10">Frequently asked questions</h2>
          <div className="space-y-6">
            {FAQS.map((faq) => (
              <div key={faq.q} className="border-b border-[#1e1e1e] pb-6">
                <h3 className="text-sm font-semibold text-white mb-2">{faq.q}</h3>
                <p className="text-sm text-zinc-400 leading-relaxed">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Bottom CTA */}
        <div className="mt-20 text-center bg-[#0d0d0f] border border-[#1e1e1e] rounded-2xl p-12">
          <h2 className="text-3xl font-semibold text-white mb-3">Still have questions?</h2>
          <p className="text-zinc-400 mb-8">Our team of engineers is happy to walk you through the right plan for your use case.</p>
          <Link href="mailto:support@suspensionlab.io"
            className="inline-flex items-center gap-2 px-6 py-3 bg-signal text-carbon border border-signal font-bold rounded-xl
              hover:bg-[#d6f56e] transition-colors">
            Talk to an Engineer <ArrowRight size={16} />
          </Link>
        </div>

        {/* Legal links */}
        <div className="mt-12 text-center">
          <p className="text-xs text-zinc-300">
            By subscribing you agree to our{" "}
            <a href="/legal/terms" className="text-zinc-400 hover:text-white underline transition-colors">Terms of Service</a>
            {" "}and{" "}
            <a href="/legal/privacy" className="text-zinc-400 hover:text-white underline transition-colors">Privacy Policy</a>.
            Instant license key delivery via Gumroad or direct team invoicing.
          </p>
        </div>

      </div>
    </div>
  );
}
