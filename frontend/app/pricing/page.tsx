"use client";

import React from "react";
import Link from "next/link";
import { Check, Zap, Shield, Building2, ArrowRight } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";

const PLANS = [
  {
    name: "Starter",
    planKey: "FREE",
    price: "Free",
    billing: "forever",
    description: "For individual engineers exploring vehicle dynamics.",
    color: "border-[#252525]",
    badge: null,
    features: [
      "Quarter Car (2-DOF) simulator",
      "5 saved configurations",
      "Transmissibility & Bode plots",
      "ISO 2631-1 comfort analysis",
      "Community support",
    ],
    cta: "Get Started Free",
    ctaHref: "/quarter-car",
    ctaStyle: "bg-[#1e1e20] border border-[#333] text-white hover:bg-[#2a2a2c]",
    icon: Zap,
  },
  {
    name: "Pro",
    planKey: "PRO",
    price: "$49",
    billing: "per month",
    description: "For suspension engineers who need the full toolkit.",
    color: "border-ansys-yellow shadow-[0_0_40px_rgba(242,169,0,0.08)]",
    badge: "Most Popular",
    features: [
      "Everything in Starter",
      "Half Car (4-DOF) & Full Car (7-DOF)",
      "AI Auto-Tune optimizer",
      "Handling dynamics & kinematics",
      "Active suspension comparison",
      "Unlimited saved configurations",
      "NVH & Acoustics module",
      "PDF export & reporting",
      "Priority email support",
    ],
    cta: "Upgrade to Pro",
    ctaHref: "/settings#billing",
    ctaStyle: "bg-ansys-yellow text-black font-bold hover:brightness-110 shadow-[0_0_20px_rgba(242,169,0,0.25)]",
    icon: Shield,
  },
  {
    name: "Enterprise",
    planKey: "ENTERPRISE",
    price: "Custom",
    billing: "contact us",
    description: "For OEM teams that need scale, compliance, and integrations.",
    color: "border-[#252525]",
    badge: null,
    features: [
      "Everything in Pro",
      "SSO / SAML authentication",
      "Dedicated cloud deployment",
      "REST API access",
      "Custom road profile import",
      "Audit logs & compliance",
      "SLA-backed uptime",
      "Dedicated customer success",
      "Volume seat licensing",
    ],
    cta: "Contact Sales",
    ctaHref: "mailto:support@suspensionlab.pro",
    ctaStyle: "bg-[#1e1e20] border border-[#333] text-white hover:bg-[#2a2a2c]",
    icon: Building2,
  },
];

const FAQS = [
  {
    q: "Can I switch plans later?",
    a: "Yes — upgrade or downgrade anytime. When you upgrade, you get instant access to all features. When you downgrade, your saved configs are preserved but locked until you re-upgrade.",
  },
  {
    q: "What physics models are included in each plan?",
    a: "Starter includes the 2-DOF quarter car model. Pro adds 4-DOF half car, 7-DOF full car, handling dynamics, active suspension, and the kinematics module. All models use the same RK45 ODE solver.",
  },
  {
    q: "Is there an annual discount?",
    a: "Yes — paying annually saves 20% compared to monthly. Toggle billing to annual on the checkout page.",
  },
  {
    q: "Do you offer academic or startup discounts?",
    a: "Yes. Students and researchers get 50% off Pro with a verified .edu email. Early-stage startups (< 2 years old, < 10 employees) get 30% off. Contact us to apply.",
  },
];

export default function PricingPage() {
  const { user } = useAuth();
  const currentPlanKey = (user?.plan || "FREE").toUpperCase();

  return (
    <div className="min-h-full bg-black pt-[44px]">
      <div className="max-w-6xl mx-auto px-6 py-20">

        {/* Header */}
        <div className="text-center mb-16">
          <span className="text-[10px] font-bold tracking-[0.25em] text-ansys-yellow uppercase">Pricing & Plans</span>
          <h1 className="text-5xl font-semibold tracking-tight text-white mt-3 mb-4">
            Simple, transparent engineering tiers
          </h1>
          <p className="text-gray-500 text-lg max-w-xl mx-auto">
            Every tier includes the core physics engine. Upgrade for multi-body DOF solvers, AI optimizers, and enterprise team governance.
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
              ctaText = "Included in Enterprise";
              ctaHref = "/quarter-car";
              ctaStyle = "bg-white/10 text-white border border-white/20 hover:bg-white/20";
            } else if (!user) {
              if (plan.planKey === "FREE") {
                ctaText = "Get Started Free";
                ctaHref = "/auth/register";
              } else if (plan.planKey === "PRO") {
                ctaText = "Get Started with Pro";
                ctaHref = "/auth/register";
              }
            }

            return (
              <div
                key={plan.name}
                className={`relative bg-[#0d0d0f] border ${isCurrentPlan ? "border-emerald-500/50 shadow-[0_0_30px_rgba(16,185,129,0.15)]" : plan.color} rounded-2xl p-8 flex flex-col`}
              >
                {isCurrentPlan ? (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="px-3 py-1 bg-emerald-500 text-black text-[10px] font-bold uppercase tracking-wider rounded-full">
                      Your Active Plan
                    </span>
                  </div>
                ) : plan.badge && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="px-3 py-1 bg-ansys-yellow text-black text-[10px] font-bold uppercase tracking-wider rounded-full">
                      {plan.badge}
                    </span>
                  </div>
                )}

                <div className="mb-6">
                  <div className="flex items-center gap-2 mb-3">
                    <Icon size={16} className={isCurrentPlan ? "text-emerald-400" : "text-ansys-yellow"} />
                    <span className="text-xs font-bold text-gray-500 uppercase tracking-widest">{plan.name}</span>
                  </div>
                  <div className="flex items-end gap-1.5 mb-2">
                    <span className="text-4xl font-bold text-white">{plan.price}</span>
                    {plan.price !== "Free" && plan.price !== "Custom" && (
                      <span className="text-gray-600 text-sm mb-1">{plan.billing}</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-500">{plan.description}</p>
                </div>

                <ul className="space-y-3 mb-8 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2.5">
                      <Check size={14} className="text-emerald-500 mt-0.5 shrink-0" />
                      <span className="text-sm text-gray-300">{f}</span>
                    </li>
                  ))}
                </ul>

                <Link
                  href={ctaHref}
                  className={`w-full py-3 rounded-xl text-sm transition-all flex items-center justify-center gap-2 ${ctaStyle}`}
                >
                  {ctaText} <ArrowRight size={14} />
                </Link>
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
                <p className="text-sm text-gray-500 leading-relaxed">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Bottom CTA */}
        <div className="mt-20 text-center bg-[#0d0d0f] border border-[#1e1e1e] rounded-2xl p-12">
          <h2 className="text-3xl font-semibold text-white mb-3">Still have questions?</h2>
          <p className="text-gray-500 mb-8">Our team of engineers is happy to walk you through the right plan for your use case.</p>
          <Link href="mailto:suspenlabsupp@outlook.com"
            className="inline-flex items-center gap-2 px-6 py-3 bg-ansys-yellow text-black font-bold rounded-xl
              hover:brightness-110 transition-all shadow-[0_0_20px_rgba(242,169,0,0.2)]">
            Talk to an Engineer <ArrowRight size={16} />
          </Link>
        </div>

        {/* Legal links */}
        <div className="mt-12 text-center">
          <p className="text-xs text-gray-600">
            By subscribing you agree to our{" "}
            <a href="/legal/terms" className="text-gray-500 hover:text-white underline transition-colors">Terms of Service</a>
            {" "}and{" "}
            <a href="/legal/privacy" className="text-gray-500 hover:text-white underline transition-colors">Privacy Policy</a>.
            Billing is handled securely by Lemon Squeezy.
          </p>
        </div>

      </div>
    </div>
  );
}
