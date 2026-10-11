"use client";
import { useCallback, useEffect, useState } from "react";
import { Loader2, Plus, Trash2, Zap, CheckCircle2 } from "lucide-react";
import { useAuth } from "../contexts/AuthContext";

/**
 * Webhook endpoint management (Tier C2).
 *
 * Lets customers pipe job.completed / job.failed events into their own
 * pipelines. Deliveries are HMAC-SHA256 signed; the signing secret is shown
 * exactly once at creation.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface WebhookEndpoint {
  id: string;
  url: string;
  events: string[];
  description: string | null;
  is_active: boolean;
  secret_masked: string | null;
}

export default function WebhooksCard() {
  const { fetchWithAuth } = useAuth();
  const [endpoints, setEndpoints] = useState<WebhookEndpoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState("");
  const [newSecret, setNewSecret] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [testedId, setTestedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWithAuth("/api/v1/webhooks");
      if (res.ok) setEndpoints((await res.json()).endpoints ?? []);
    } catch {
      setError("Network error while loading webhooks.");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!url.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetchWithAuth("/api/v1/webhooks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), events: ["job.completed", "job.failed"] }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.detail ?? `HTTP ${res.status}`);
      setNewSecret(body.secret);
      setUrl("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create webhook.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    setBusy(true);
    try {
      await fetchWithAuth(`/api/v1/webhooks/${id}`, { method: "DELETE" });
      await load();
    } finally {
      setBusy(false);
    }
  };

  const sendTest = async (id: string) => {
    setBusy(true);
    try {
      const res = await fetchWithAuth(`/api/v1/webhooks/${id}/test`, {
        method: "POST",
      });
      const body = await res.json().catch(() => ({}));
      setTestedId(id);
      setError(body.delivered ? null : "Test delivery failed — check the receiver URL is reachable.");
      setTimeout(() => setTestedId(null), 3000);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <p className="text-xs text-gray-500 mb-4">
        Receive HMAC-signed <code className="text-gray-400">job.completed</code> /{" "}
        <code className="text-gray-400">job.failed</code> events the moment simulations finish —
        verify signatures with <code className="text-gray-400">X-SL-Signature</code>.
      </p>

      {/* Secret shown once */}
      {newSecret && (
        <div className="mb-4 p-4 bg-emerald-950/30 border border-emerald-900/40 rounded-xl">
          <div className="flex items-center gap-1.5 mb-2">
            <CheckCircle2 size={13} className="text-emerald-500" />
            <p className="text-xs font-semibold text-emerald-400">Signing secret — copy it now. It won&apos;t be shown again.</p>
          </div>
          <p className="font-mono text-xs text-gray-300 break-all">{newSecret}</p>
          <button onClick={() => setNewSecret(null)} className="mt-2 text-[10px] text-gray-600 hover:text-gray-400">
            I&apos;ve copied the secret
          </button>
        </div>
      )}

      {error && <p role="alert" className="text-red-400 text-sm mb-3">{error}</p>}

      {/* Create form */}
      <div className="flex gap-2 mb-5">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://your-pipeline.example.com/hooks/suspensionlab"
          aria-label="Webhook receiver URL"
          className="flex-1 bg-[#0d0d0f] border border-[#252525] rounded-xl px-3 py-2 text-sm text-white
            placeholder:text-gray-700 focus:outline-none focus:border-ansys-yellow/60 transition-all"
        />
        <button onClick={create} disabled={busy || !url.trim()}
          className="px-4 py-2 bg-ansys-yellow text-black text-xs font-bold rounded-xl
            hover:brightness-110 transition-all disabled:opacity-40 flex items-center gap-1.5">
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
          Add
        </button>
      </div>

      {/* Endpoint list */}
      {loading ? (
        <div className="flex items-center justify-center py-6">
          <Loader2 size={20} className="animate-spin text-gray-600" />
        </div>
      ) : endpoints.length === 0 ? (
        <p className="text-sm text-gray-600 text-center py-4">No webhook endpoints yet.</p>
      ) : (
        <ul className="space-y-2">
          {endpoints.map((ep) => (
            <li key={ep.id}
              className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-xl border border-[#252525] bg-[#0d0d0f]">
              <div className="min-w-0">
                <p className="text-sm text-white truncate">{ep.url}</p>
                <p className="text-[10px] text-gray-600">
                  {ep.events.join(", ")} · {ep.is_active ? "active" : "inactive"}
                </p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button onClick={() => sendTest(ep.id)} disabled={busy}
                  title="Send signed test event"
                  className="p-2 text-gray-500 hover:text-ansys-yellow transition-colors disabled:opacity-40">
                  {testedId === ep.id ? <CheckCircle2 size={14} className="text-emerald-500" /> : <Zap size={14} />}
                </button>
                <button onClick={() => remove(ep.id)} disabled={busy}
                  title="Delete endpoint"
                  className="p-2 text-gray-500 hover:text-red-400 transition-colors disabled:opacity-40">
                  <Trash2 size={14} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
