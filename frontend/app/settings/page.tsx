"use client";
import { useState, useEffect } from "react";
import { useAuth } from "../../contexts/AuthContext";
import Link from "next/link";
import {
  User, CreditCard, Key, Shield, ExternalLink, Copy, CheckCircle2,
  Trash2, Plus, AlertTriangle, Loader2, Users, Building2, Laptop, Smartphone, Globe, RefreshCw
} from "lucide-react";
import { EnterpriseApi, UserSession } from "../../lib/api_client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const PLAN_BADGES: Record<string, { label: string; color: string }> = {
  FREE:       { label: "Free",       color: "text-gray-400 bg-[#1e1e1e]"          },
  PRO:        { label: "Pro",        color: "text-ansys-yellow bg-ansys-yellow/10" },
  ENTERPRISE: { label: "Enterprise", color: "text-purple-400 bg-purple-900/20"     },
};

import { type LucideIcon } from "lucide-react";
import TeamSettings from "../../components/TeamSettings";
import WebhooksCard from "../../components/WebhooksCard";
import { Zap } from "lucide-react";

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
  const { user, logout, authHeader, fetchWithAuth } = useAuth();
  const [activeTab, setActiveTab]    = useState<"account" | "billing" | "api-keys" | "webhooks" | "team" | "security" | "enterprise">("account");
  const [apiKeys,   setApiKeys]      = useState<ApiKey[]>([]);
  const [newKeyName, setNewKeyName]  = useState("");
  const [newKeyValue, setNewKeyValue] = useState<string | null>(null);
  const [copied,    setCopied]       = useState(false);
  const [loadingKeys, setLoadingKeys] = useState(false);
  const [creatingKey, setCreatingKey] = useState(false);

  // Active Sessions State
  const [sessions, setSessions] = useState<UserSession[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [revokingJti, setRevokingJti] = useState<string | null>(null);

  // Enterprise SCIM State
  const [scimStatus, setScimStatus] = useState<any>(null);

  const plan    = user?.plan ?? "FREE";
  const badge   = PLAN_BADGES[plan] ?? { label: "Unknown", color: "text-gray-500 bg-[#1e1e1e]" };
  const canKeys = plan !== "FREE";
  const isEnterprise = plan === "ENTERPRISE" || user?.user_id === "admin-001";

  // Fetch API keys when tab opens
  useEffect(() => {
    if (activeTab !== "api-keys" || !canKeys) return;
    setTimeout(() => {
      setLoadingKeys(true);
      fetchWithAuth("/api/v1/api-keys/")
        .then((r) => r.json())
        .then((d) => setApiKeys(Array.isArray(d) ? d : []))
        .catch((e) => console.error("Failed to load API keys", e))
        .finally(() => setLoadingKeys(false));
    }, 0);
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadSessions = async () => {
    setLoadingSessions(true);
    try {
      const res = await EnterpriseApi.getActiveSessions();
      setSessions(res.sessions || []);
    } catch (e) {
      console.error("Failed to load sessions", e);
    } finally {
      setLoadingSessions(false);
    }
  };

  useEffect(() => {
    if (activeTab === "security") {
      loadSessions();
    } else if (activeTab === "enterprise") {
      EnterpriseApi.getScimStatus().then(setScimStatus).catch(() => {});
    }
  }, [activeTab]);

  const createKey = async () => {
    if (!newKeyName.trim()) return;
    setCreatingKey(true);
    try {
      const r = await fetchWithAuth("/api/v1/api-keys/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newKeyName.trim() }),
      });
      const data = await r.json();
      if (r.ok && data.key) {
        setNewKeyValue(data.key);
        setApiKeys((prev) => [data, ...prev]);
        setNewKeyName("");
      }
    } catch (e) {
      console.error("Failed to create key", e);
    } finally {
      setCreatingKey(false);
    }
  };

  const revokeKey = async (id: string) => {
    try {
      await fetchWithAuth(`/api/v1/api-keys/${id}`, { method: "DELETE" });
      setApiKeys((prev) => prev.filter((k) => k.id !== id));
    } catch (e) {
      console.error("Failed to revoke key", e);
    }
  };

  const copyKey = (val: string) => {
    navigator.clipboard.writeText(val);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const [gumroadKey, setGumroadKey] = useState("");
  const [activatingLicense, setActivatingLicense] = useState(false);
  const [licenseMessage, setLicenseMessage] = useState<{type: "error"|"success", text: string} | null>(null);

  const activateLicense = async () => {
    if (!gumroadKey.trim()) return;
    setActivatingLicense(true);
    setLicenseMessage(null);
    try {
      const r = await fetch(`${API_BASE}/api/v1/billing/verify-license`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ license_key: gumroadKey.trim() }),
      });
      const data = await r.json();
      if (r.ok) {
        setLicenseMessage({ type: "success", text: "PRO unlocked successfully! Refreshing..." });
        setTimeout(() => window.location.reload(), 2000);
      } else {
        setLicenseMessage({ type: "error", text: data.detail || "Invalid license key." });
      }
    } catch {
      setLicenseMessage({ type: "error", text: "Failed to contact server." });
    } finally {
      setActivatingLicense(false);
    }
  };

  const TABS = [
    { id: "account",  label: "Account",  icon: User      },
    { id: "team",     label: "Workspace",icon: Users     },
    { id: "billing",  label: "Billing",  icon: CreditCard },
    { id: "api-keys", label: "API Keys", icon: Key       },
    { id: "webhooks", label: "Webhooks", icon: Zap       },
    { id: "security", label: "Security & Sessions", icon: Shield },
    { id: "enterprise", label: "Enterprise & SCIM", icon: Building2 },
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
                  {plan === "FREE" && (
                    <div className="mt-4 pt-4 border-t border-[#1e1e1e]">
                      <p className="text-sm font-semibold text-white mb-2">Activate PRO</p>
                      <p className="text-xs text-gray-500 mb-4">
                        Purchased a license on Gumroad? Enter your license key here to unlock PRO features instantly.
                      </p>
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={gumroadKey}
                          onChange={(e) => setGumroadKey(e.target.value)}
                          placeholder="e.g. XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX"
                          className="flex-1 bg-[#0d0d0f] border border-[#252525] rounded-xl px-3 py-2 text-sm text-white placeholder:text-gray-700 focus:outline-none focus:border-ansys-yellow/60 transition-all font-mono"
                        />
                        <button
                          onClick={activateLicense}
                          disabled={activatingLicense || !gumroadKey.trim()}
                          className="px-4 py-2 bg-ansys-yellow text-black text-xs font-bold rounded-xl hover:brightness-110 transition-all disabled:opacity-40 flex items-center gap-1.5"
                        >
                          {activatingLicense ? <Loader2 size={12} className="animate-spin" /> : <Key size={12} />}
                          Verify Key
                        </button>
                      </div>
                      {licenseMessage && (
                        <p className={`mt-2 text-xs ${licenseMessage.type === "error" ? "text-red-400" : "text-emerald-400"}`}>
                          {licenseMessage.text}
                        </p>
                      )}
                      
                      <div className="mt-4">
                        <a href="https://gumroad.com/l/suspensionlab-pro" target="_blank" rel="noreferrer"
                          className="text-xs text-ansys-yellow hover:underline">
                          Don&apos;t have a license? Buy on Gumroad &rarr;
                        </a>
                      </div>
                    </div>
                  )}
                </SectionCard>
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

            {/* Webhooks tab (Tier C2) */}
            {activeTab === "webhooks" && (
              <SectionCard title="Webhooks" icon={Zap}>
                <WebhooksCard />
              </SectionCard>
            )}

            {/* Security & Sessions tab */}
            {activeTab === "security" && (
              <SectionCard title="Security & Active Sessions" icon={Shield}>
                <div className="space-y-6">
                  <div className="flex items-start gap-3 p-4 bg-amber-950/20 border border-amber-900/30 rounded-xl">
                    <AlertTriangle size={16} className="text-amber-500 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-semibold text-amber-400">Password reset</p>
                      <p className="text-xs text-gray-400 max-w-sm">
                        To reset password or manage cryptographic credentials, contact{" "}
                        <a href="mailto:suspenlabsupp@outlook.com" className="text-ansys-yellow hover:underline">suspenlabsupp@outlook.com</a>.
                      </p>
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <p className="text-xs font-bold text-white uppercase tracking-wider">Active Device Sessions</p>
                        <p className="text-[11px] text-gray-500">Cryptographically tracked JWT sessions with remote revocation</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={loadSessions}
                          disabled={loadingSessions}
                          className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white"
                          title="Refresh sessions"
                        >
                          <RefreshCw size={13} className={loadingSessions ? "animate-spin" : ""} />
                        </button>
                        {sessions.length > 1 && (
                          <button
                            onClick={async () => {
                              try {
                                await EnterpriseApi.revokeAllOtherSessions();
                                await loadSessions();
                              } catch (err) {
                                console.error(err);
                              }
                            }}
                            className="px-2.5 py-1 rounded-lg bg-red-950/40 border border-red-500/30 text-red-400 hover:bg-red-950/60 text-xs font-mono font-semibold"
                          >
                            Revoke All Other Sessions
                          </button>
                        )}
                      </div>
                    </div>

                    {loadingSessions ? (
                      <div className="py-6 flex items-center justify-center">
                        <Loader2 size={20} className="animate-spin text-ansys-yellow" />
                      </div>
                    ) : sessions.length === 0 ? (
                      <div className="p-4 rounded-xl bg-[#0d0d0f] border border-[#1e1e1e] text-xs text-gray-400 flex items-center justify-between">
                        <div className="flex items-center gap-2.5">
                          <Laptop size={16} className="text-ansys-yellow" />
                          <div>
                            <div className="font-semibold text-white">Current Browser Session</div>
                            <div className="text-[10px] text-gray-500 font-mono">Authenticated via HTTP-only session cookie</div>
                          </div>
                        </div>
                        <span className="px-2 py-0.5 rounded bg-emerald-950/50 border border-emerald-500/30 text-emerald-400 text-[10px] font-mono">
                          ACTIVE
                        </span>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {sessions.map((sess) => {
                          const isMobile = sess.device_type?.toLowerCase().includes("mobile") || sess.user_agent?.toLowerCase().includes("mobile");
                          const DevIcon = isMobile ? Smartphone : Laptop;
                          return (
                            <div
                              key={sess.jti}
                              className="flex items-center justify-between p-3 rounded-xl bg-[#0d0d0f] border border-[#1e1e1e] hover:border-white/10 transition-colors text-xs"
                            >
                              <div className="flex items-center gap-3 min-w-0">
                                <DevIcon size={18} className="text-ansys-yellow shrink-0" />
                                <div className="min-w-0">
                                  <div className="font-semibold text-white flex items-center gap-2">
                                    <span className="truncate">{sess.user_agent || "Web Browser"}</span>
                                    {sess.is_current && (
                                      <span className="px-1.5 py-0.2 rounded bg-emerald-950 border border-emerald-500/30 text-emerald-400 text-[9px] font-mono">
                                        THIS DEVICE
                                      </span>
                                    )}
                                  </div>
                                  <div className="text-[10px] text-gray-500 font-mono flex items-center gap-3 mt-0.5">
                                    <span>IP: {sess.ip_address || "127.0.0.1"}</span>
                                    <span>Expires: {new Date(sess.expires_at).toLocaleDateString()}</span>
                                  </div>
                                </div>
                              </div>

                              <button
                                onClick={async () => {
                                  setRevokingJti(sess.jti);
                                  try {
                                    await EnterpriseApi.revokeSession(sess.jti);
                                    setSessions((prev) => prev.filter((s) => s.jti !== sess.jti));
                                  } catch (err) {
                                    console.error("Revoke session error", err);
                                  } finally {
                                    setRevokingJti(null);
                                  }
                                }}
                                disabled={revokingJti === sess.jti}
                                className="px-2.5 py-1 rounded bg-white/5 hover:bg-red-950/40 hover:text-red-400 border border-white/10 hover:border-red-500/30 text-gray-400 text-[11px] transition-colors shrink-0 flex items-center gap-1"
                              >
                                {revokingJti === sess.jti ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                                Revoke
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  <div className="pt-4 border-t border-[#1e1e1e]">
                    <button
                      onClick={logout}
                      className="px-3 py-1.5 rounded-lg border border-red-500/30 text-red-500 hover:bg-red-950/20 text-xs transition-colors"
                    >
                      Sign out of all sessions
                    </button>
                  </div>
                </div>
              </SectionCard>
            )}

            {/* Enterprise & SCIM Tab */}
            {activeTab === "enterprise" && (
              <SectionCard title="Enterprise Directory & SCIM Provisioning" icon={Building2}>
                <div className="space-y-6">
                  {!isEnterprise ? (
                    <div className="text-center py-6">
                      <Building2 size={32} className="mx-auto text-gray-700 mb-3" />
                      <p className="text-sm text-gray-400 mb-2 font-semibold">Enterprise Directory Integration</p>
                      <p className="text-xs text-gray-500 mb-4 max-w-md mx-auto">
                        Automated user lifecycle management via SCIM 2.0 and SAML/SSO authentication requires the Enterprise plan.
                      </p>
                      <Link
                        href="/pricing"
                        className="px-4 py-2 bg-ansys-yellow text-black text-xs font-bold rounded-xl hover:brightness-110 inline-block"
                      >
                        Upgrade to Enterprise
                      </Link>
                    </div>
                  ) : (
                    <>
                      {/* SCIM Provisioning Card */}
                      <div className="p-4 rounded-xl bg-[#0d0d0f] border border-[#1e1e1e] space-y-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 text-white font-bold text-sm">
                            <CheckCircle2 size={16} className="text-emerald-400" />
                            SCIM 2.0 User Provisioning
                          </div>
                          <span className="px-2 py-0.5 rounded bg-emerald-950/50 border border-emerald-500/30 text-emerald-400 text-[10px] font-mono font-bold">
                            ENABLED
                          </span>
                        </div>
                        <p className="text-xs text-gray-400">
                          Configure your IdP (Okta, Microsoft Entra ID, PingFederate) to automatically provision and de-provision engineering team members.
                        </p>
                        <div className="p-2.5 rounded-lg bg-black/60 border border-white/5 font-mono text-xs text-gray-300">
                          <span className="text-gray-500">SCIM Endpoint:</span>{" "}
                          <code className="text-ansys-yellow">https://suspensionlab.pro/api/v1/scim/v2</code>
                        </div>
                      </div>

                      {/* SAML / SSO Card */}
                      <div className="p-4 rounded-xl bg-[#0d0d0f] border border-[#1e1e1e] space-y-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 text-white font-bold text-sm">
                            <Shield size={16} className="text-purple-400" />
                            SAML 2.0 Single Sign-On (SSO)
                          </div>
                          <span className="px-2 py-0.5 rounded bg-purple-950/50 border border-purple-500/30 text-purple-400 text-[10px] font-mono font-bold">
                            READY
                          </span>
                        </div>
                        <p className="text-xs text-gray-400">
                          Enforce mandatory SSO authentication for all engineers in your organization.
                        </p>
                        <div className="space-y-1.5 font-mono text-xs">
                          <div className="p-2 rounded bg-black/40 border border-white/5 text-gray-400">
                            <span className="text-gray-500">ACS URL:</span>{" "}
                            <code className="text-white">https://suspensionlab.pro/api/v1/saml/acs</code>
                          </div>
                          <div className="p-2 rounded bg-black/40 border border-white/5 text-gray-400">
                            <span className="text-gray-500">Entity ID:</span>{" "}
                            <code className="text-white">https://suspensionlab.pro/saml/metadata</code>
                          </div>
                        </div>
                      </div>

                      <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] text-[11px] text-gray-400 flex items-center justify-between">
                        <span>Tamper-evident cryptographic audit logs are active for all directory events.</span>
                        <Link href="/audit" className="text-ansys-yellow hover:underline flex items-center gap-1 font-mono">
                          View Audit Logs <ExternalLink size={11} />
                        </Link>
                      </div>
                    </>
                  )}
                </div>
              </SectionCard>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

