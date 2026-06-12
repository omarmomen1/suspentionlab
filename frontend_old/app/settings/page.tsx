"use client";
import { useState, useEffect } from "react";
import { useAuth } from "../../contexts/AuthContext";
import Link from "next/link";
import {
  User, CreditCard, Key, Shield, ExternalLink, Copy, CheckCircle2,
  Trash2, Plus, AlertTriangle, Loader2, Users,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const PLAN_BADGES: Record<string, { label: string; color: string }> = {
  FREE:       { label: "Free",       color: "text-gray-400 bg-[#1e1e1e]"          },
  PRO:        { label: "Pro",        color: "text-ansys-yellow bg-ansys-yellow/10" },
  ENTERPRISE: { label: "Enterprise", color: "text-purple-400 bg-purple-900/20"     },
};

import { type LucideIcon } from "lucide-react";
import TeamSettings from "../../components/TeamSettings";

function SectionCard({ title, icon: Icon, children }: {
  title: string; icon: LucideIcon; children: React.ReactNode;
}) {
  return (
    <div className="bg-[#111113] border border-[#1e1e1e] rounded-2xl overflow-hidden">
      <div className="flex items-center gap-2.5 px-6 py-4 border-b border-[#1e1e1e]">
        <Icon size={15} className="text-ansys-yellow" />
        <h2 className="text-sm font-semibold text-white">{title}</h2>
      </div>
      <div className="p-6">{children}</div>
    </div>
  );
}

interface ApiKey { id: string; name: string; key_prefix: string; created_at: string; last_used: string | null; }

export default function SettingsPage() {
  const { user, logout, authHeader } = useAuth();
  const [activeTab, setActiveTab]    = useState<"account" | "billing" | "api-keys" | "team" | "security">("account");
  const [apiKeys,   setApiKeys]      = useState<ApiKey[]>([]);
  const [newKeyName, setNewKeyName]  = useState("");
  const [newKeyValue, setNewKeyValue] = useState<string | null>(null);
  const [copied,    setCopied]       = useState(false);
  const [loadingKeys, setLoadingKeys] = useState(false);
  const [creatingKey, setCreatingKey] = useState(false);
  const [portalLoading, setPortalLoading] = useState(false);

  const plan    = user?.plan ?? "FREE";
  const badge   = PLAN_BADGES[plan];
  const canKeys = plan !== "FREE";

  // Fetch API keys when tab opens
  useEffect(() => {
    if (activeTab !== "api-keys" || !canKeys) return;
    setLoadingKeys(true);
    fetch(`${API_BASE}/api-keys`, { headers: authHeader() })
      .then((r) => r.json())
      .then((d) => setApiKeys(Array.isArray(d) ? d : []))
      .finally(() => setLoadingKeys(false));
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  const createKey = async () => {
    if (!newKeyName.trim()) return;
    setCreatingKey(true);
    try {
      const r = await fetch(`${API_BASE}/api-keys`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ name: newKeyName }),
      });
      const data = await r.json();
      if (r.ok && data.key) {
        setNewKeyValue(data.key);
        setApiKeys((prev) => [data, ...prev]);
        setNewKeyName("");
      }
    } finally {
      setCreatingKey(false);
    }
  };

  const revokeKey = async (id: string) => {
    await fetch(`${API_BASE}/api-keys/${id}`, { method: "DELETE", headers: authHeader() });
    setApiKeys((prev) => prev.filter((k) => k.id !== id));
  };

  const copyKey = (val: string) => {
    navigator.clipboard.writeText(val);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const openBillingPortal = async () => {
    setPortalLoading(true);
    try {
      const r    = await fetch(`${API_BASE}/billing/portal`, { method: "POST", headers: authHeader() });
      const data = await r.json();
      if (data.portal_url) window.location.href = data.portal_url;
    } finally {
      setPortalLoading(false);
    }
  };

  const TABS = [
    { id: "account",  label: "Account",  icon: User      },
    { id: "team",     label: "Workspace",icon: Users     },
    { id: "billing",  label: "Billing",  icon: CreditCard },
    { id: "api-keys", label: "API Keys", icon: Key       },
    { id: "security", label: "Security", icon: Shield    },
  ] as const;

  return (
    <div className="min-h-full bg-black pt-[44px]">
      <div className="max-w-4xl mx-auto px-6 py-12">
        <div className="mb-8">
          <span className="text-[10px] font-bold tracking-[0.2em] text-ansys-yellow uppercase">Account</span>
          <h1 className="text-3xl font-semibold text-white mt-1">Settings</h1>
        </div>

        <div className="flex gap-8">
          {/* Sidebar tabs */}
          <div className="w-44 shrink-0 space-y-1">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              return (
                <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm transition-colors ${
                    activeTab === tab.id
                      ? "bg-ansys-yellow/10 text-ansys-yellow font-semibold"
                      : "text-gray-500 hover:text-gray-300 hover:bg-[#111113]"
                  }`}>
                  <Icon size={14} /> {tab.label}
                </button>
              );
            })}
            <div className="pt-4 border-t border-[#1e1e1e] mt-4">
              <button onClick={logout}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm
                  text-red-500 hover:bg-red-950/20 transition-colors">
                Sign Out
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 space-y-5">

            {/* Account tab */}
            {activeTab === "account" && (
              <SectionCard title="Profile" icon={User}>
                <div className="space-y-4">
                  <div>
                    <p className="text-xs text-gray-500 mb-0.5">Name</p>
                    <p className="text-sm text-white font-medium">{user?.name || "—"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500 mb-0.5">Email</p>
                    <p className="text-sm text-white font-medium">{user?.email || "—"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500 mb-0.5">Current Plan</p>
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold ${badge.color}`}>
                      {badge.label}
                    </span>
                  </div>
                </div>
              </SectionCard>
            )}

            {/* Team tab */}
            {activeTab === "team" && <TeamSettings />}

            {/* Billing tab */}
            {activeTab === "billing" && (
              <>
                <SectionCard title="Current Plan" icon={CreditCard}>
                  <div className="flex items-center justify-between mb-5">
                    <div>
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold ${badge.color} mb-2`}>
                        {badge.label}
                      </span>
                      <p className="text-sm text-gray-400">
                        {plan === "FREE"
                          ? "You are on the free plan. Upgrade to unlock all models and AI Auto-Tune."
                          : plan === "PRO"
                          ? "You have full access to all Pro features."
                          : "Enterprise plan — full access + team features."}
                      </p>
                    </div>
                    {plan !== "ENTERPRISE" && (
                      <Link href="/pricing"
                        className="px-4 py-2 bg-ansys-yellow text-black text-xs font-bold rounded-xl
                          hover:brightness-110 transition-all shrink-0">
                        Upgrade
                      </Link>
                    )}
                  </div>
                  {plan !== "FREE" && (
                    <button onClick={openBillingPortal} disabled={portalLoading}
                      className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors">
                      {portalLoading ? <Loader2 size={14} className="animate-spin" /> : <ExternalLink size={14} />}
                      Manage subscription & invoices in Stripe
                    </button>
                  )}
                </SectionCard>

                {plan === "FREE" && (
                  <div className="grid grid-cols-2 gap-4">
                    {[
                      { plan: "pro", label: "Pro", price: "$49/mo", color: "border-ansys-yellow/30 hover:border-ansys-yellow/60" },
                      { plan: "enterprise", label: "Enterprise", price: "$300/mo", color: "border-purple-500/30 hover:border-purple-500/60" },
                    ].map((p) => (
                      <a key={p.plan} href={`${API_BASE}/billing/checkout`}
                        onClick={async (e) => {
                          e.preventDefault();
                          const r = await fetch(`${API_BASE}/billing/checkout`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json", ...authHeader() },
                            body: JSON.stringify({ plan: p.plan }),
                          });
                          const d = await r.json();
                          if (d.checkout_url) window.location.href = d.checkout_url;
                        }}
                        className={`bg-[#0d0d0f] border ${p.color} rounded-xl p-4 cursor-pointer
                          transition-colors block`}>
                        <p className="text-sm font-bold text-white">{p.label}</p>
                        <p className="text-xs text-gray-500 mb-3">{p.price}</p>
                        <p className="text-[10px] text-gray-600">Click to start 14-day trial →</p>
                      </a>
                    ))}
                  </div>
                )}
              </>
            )}

            {/* API Keys tab */}
            {activeTab === "api-keys" && (
              <SectionCard title="API Keys" icon={Key}>
                {!canKeys ? (
                  <div className="text-center py-6">
                    <Key size={32} className="mx-auto text-gray-700 mb-3" />
                    <p className="text-sm text-gray-500 mb-4">API key access requires the Pro or Enterprise plan.</p>
                    <Link href="/pricing"
                      className="px-4 py-2 bg-ansys-yellow text-black text-xs font-bold rounded-xl hover:brightness-110">
                      Upgrade to Pro
                    </Link>
                  </div>
                ) : (
                  <>
                    {/* New key shown once */}
                    {newKeyValue && (
                      <div className="mb-4 p-4 bg-emerald-950/30 border border-emerald-900/40 rounded-xl">
                        <div className="flex items-center gap-1.5 mb-2">
                          <CheckCircle2 size={13} className="text-emerald-500" />
                          <p className="text-xs font-semibold text-emerald-400">Key created — copy it now. It won&apos;t be shown again.</p>
                        </div>
                        <div className="flex items-center gap-2 bg-black/50 rounded-lg px-3 py-2 font-mono text-xs text-gray-300 border border-white/5">
                          <span className="flex-1 truncate">{newKeyValue}</span>
                          <button onClick={() => copyKey(newKeyValue)}
                            className="text-gray-600 hover:text-white transition-colors shrink-0">
                            {copied ? <CheckCircle2 size={13} className="text-emerald-500" /> : <Copy size={13} />}
                          </button>
                        </div>
                        <button onClick={() => setNewKeyValue(null)}
                          className="mt-2 text-[10px] text-gray-600 hover:text-gray-400">
                          I&apos;ve copied the key
                        </button>
                      </div>
                    )}

                    {/* Create form */}
                    <div className="flex gap-2 mb-5">
                      <input type="text" value={newKeyName} onChange={(e) => setNewKeyName(e.target.value)}
                        placeholder="Key name (e.g. Python Script, CI Pipeline)"
                        className="flex-1 bg-[#0d0d0f] border border-[#252525] rounded-xl px-3 py-2 text-sm text-white
                          placeholder:text-gray-700 focus:outline-none focus:border-ansys-yellow/60 transition-all" />
                      <button onClick={createKey} disabled={creatingKey || !newKeyName.trim()}
                        className="px-4 py-2 bg-ansys-yellow text-black text-xs font-bold rounded-xl
                          hover:brightness-110 transition-all disabled:opacity-40 flex items-center gap-1.5">
                        {creatingKey ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                        Create
                      </button>
                    </div>

                    {/* Key list */}
                    {loadingKeys ? (
                      <div className="flex items-center justify-center py-6">
                        <Loader2 size={20} className="animate-spin text-gray-600" />
                      </div>
                    ) : apiKeys.length === 0 ? (
                      <p className="text-sm text-gray-600 text-center py-4">No API keys yet.</p>
                    ) : (
                      <div className="space-y-2">
                        {apiKeys.map((k) => (
                          <div key={k.id} className="flex items-center justify-between gap-3 px-3 py-2.5
                            bg-[#0d0d0f] border border-[#1e1e1e] rounded-xl">
                            <div className="min-w-0">
                              <p className="text-xs font-semibold text-white">{k.name}</p>
                              <p className="text-[10px] text-gray-600 font-mono mt-0.5">{k.key_prefix}••••••••</p>
                            </div>
                            <div className="flex items-center gap-3 shrink-0">
                              <p className="text-[10px] text-gray-700">
                                {k.last_used
                                  ? `Used ${new Date(k.last_used).toLocaleDateString("en-GB")}`
                                  : "Never used"}
                              </p>
                              <button onClick={() => revokeKey(k.id)}
                                className="text-gray-600 hover:text-red-400 transition-colors">
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="mt-4 p-3 bg-[#0d0d0f] border border-[#1e1e1e] rounded-xl">
                      <p className="text-[10px] text-gray-600 leading-relaxed">
                        Use keys in your requests with the <code className="text-gray-400">X-API-Key</code> header.
                        {" "}API docs available at{" "}
                        <a href={`${API_BASE}/docs`} target="_blank" className="text-ansys-yellow hover:underline">
                          {API_BASE}/docs <ExternalLink size={9} className="inline" />
                        </a>
                      </p>
                    </div>
                  </>
                )}
              </SectionCard>
            )}

            {/* Security tab */}
            {activeTab === "security" && (
              <SectionCard title="Security" icon={Shield}>
                <div className="space-y-4">
                  <div className="flex items-start gap-3 p-4 bg-amber-950/20 border border-amber-900/30 rounded-xl">
                    <AlertTriangle size={16} className="text-amber-500 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-semibold text-amber-400">Password reset</p>
                      <p className="text-xs text-gray-600 mt-0.5">
                        Password reset via email is coming soon. To change your password now, contact{" "}
                        <a href="mailto:support@suspensionlab.io" className="text-ansys-yellow">support@suspensionlab.io</a>.
                      </p>
                    </div>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Active sessions</p>
                    <p className="text-sm text-white">1 active session (this device)</p>
                    <button onClick={logout}
                      className="mt-2 text-xs text-red-500 hover:text-red-400 transition-colors">
                      Sign out of all sessions
                    </button>
                  </div>
                </div>
              </SectionCard>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
