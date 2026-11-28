import type { Metadata } from "next";
import Link from "next/link";
import { ShieldCheck, Lock, Globe, FileCheck, Server, Mail } from "lucide-react";

export const metadata: Metadata = {
  title: "Trust & Security — SuspensionLab PRO",
  description:
    "SuspensionLab PRO security posture, data residency options, and compliance controls for procurement and security reviews.",
};

/**
 * Public trust page (Tier C1).
 *
 * The controls listed here mirror GET /api/v1/trust — each names the module
 * that enforces it. This page exists because OEM procurement stalls at
 * security review without it.
 */

const CONTROLS: { icon: typeof Lock; name: string; evidence: string }[] = [
  { icon: Lock,      name: "Encryption everywhere",   evidence: "TLS 1.2/1.3 with HSTS in transit; encrypted volumes at rest; boot-time secret-strength validation." },
  { icon: ShieldCheck, name: "Strong authentication", evidence: "OIDC (PKCE) SSO, Argon2 password hashing, rotating JWT signing keys, SCIM 2.0 provisioning." },
  { icon: FileCheck, name: "Authorization & audit",   evidence: "Seat-based RBAC (Owner/Admin/Engineer/Crew/Viewer), immutable audit logs, SHA-256-hashed engineering artifacts." },
  { icon: Server,    name: "Compute governance",      evidence: "Bounded compute pools, per-plan quotas and concurrency caps, monthly usage metering." },
];

const REGIONS = [
  { id: "eu-central", label: "EU Central", detail: "Frankfurt region — GDPR-aligned processing for European teams." },
  { id: "us-east",    label: "US East",    detail: "N. Virginia region — for US-based programs." },
];

export default function TrustPage() {
  return (
    <main className="min-h-screen bg-[#0a0a0b] text-white">
      {/* Hero */}
      <section className="max-w-4xl mx-auto px-6 pt-28 pb-16">
        <span className="text-xs font-bold tracking-[0.25em] text-signal uppercase">Enterprise readiness</span>
        <h1 className="text-4xl md:text-5xl font-bold mt-3 leading-tight">
          Trust & Security at<br />SuspensionLab PRO
        </h1>
        <p className="text-gray-400 mt-5 max-w-2xl text-sm leading-relaxed">
          Everything on this page is implemented in the product — every control
          names the module that enforces it, and the machine-readable posture is
          available at{" "}
          <code className="text-signal/90 text-xs">GET /api/v1/trust</code>{" "}
          for your automated vendor review.
        </p>
      </section>

      {/* Controls */}
      <section className="max-w-4xl mx-auto px-6 pb-16">
        <h2 className="text-xl font-semibold mb-6">Security controls</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {CONTROLS.map((c) => {
            const Icon = c.icon;
            return (
              <div key={c.name} className="rounded-2xl border border-[#1e1e1e] bg-[#111113] p-5">
                <Icon size={18} className="text-signal mb-3" />
                <h3 className="text-sm font-semibold">{c.name}</h3>
                <p className="text-xs text-zinc-400 mt-2 leading-relaxed">{c.evidence}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Data residency */}
      <section className="max-w-4xl mx-auto px-6 pb-16">
        <div className="flex items-center gap-2 mb-2">
          <Globe size={16} className="text-signal" />
          <h2 className="text-xl font-semibold">Data residency</h2>
        </div>
        <p className="text-xs text-zinc-400 mb-6 max-w-2xl">
          Enterprise teams choose where their data lives. Each region runs an
          isolated stack with its own database and storage; selection is recorded
          per team and audited.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {REGIONS.map((r) => (
            <div key={r.id} className="rounded-2xl border border-[#1e1e1e] bg-[#111113] p-5">
              <p className="text-sm font-semibold">{r.label}</p>
              <p className="text-xs text-zinc-400 mt-2">{r.detail}</p>
              <p className="text-xs font-mono text-zinc-300 mt-3">{r.id}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Reporting + CTA */}
      <section className="max-w-4xl mx-auto px-6 pb-24">
        <div className="rounded-2xl border border-[#1e1e1e] bg-[#111113] p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold">Responsible disclosure</h2>
            <p className="text-xs text-zinc-400 mt-1 flex items-center gap-1.5">
              <Mail size={12} /> security@suspensionlab.com — we respond within one business day.
            </p>
          </div>
          <Link href="/pricing"
            className="shrink-0 px-5 py-2.5 bg-signal text-carbon text-xs font-bold rounded-xl hover:brightness-110 transition-all">
            View plans
          </Link>
        </div>
      </section>
    </main>
  );
}
