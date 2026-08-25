/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function TeamSettings() {
  const { token } = useAuth();
  const [team, setTeam] = useState<any>(null);
  const [analytics, setAnalytics] = useState<any>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [teamName, setTeamName] = useState("");

  // P2-UX-04: explicit loading / error / action-feedback states
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const fetchTeam = async () => {
    if (!token) return;
    setLoading(true);
    setLoadError(null);
    try {
      const res = await fetch(`${API_BASE}/teams/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setTeam(await res.json());
        await fetchAnalytics();
      } else if (res.status === 404) {
        setTeam(null); // no team yet — show creation form
      } else {
        setTeam(null);
        setLoadError(`Failed to load team (HTTP ${res.status}).`);
      }
    } catch (e) {
      setTeam(null);
      setLoadError("Network error while loading team.");
    } finally {
      setLoading(false);
    }
  };

  const fetchAnalytics = async () => {
    try {
      const res = await fetch(`${API_BASE}/teams/analytics`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setAnalytics(await res.json());
      }
    } catch {
      // analytics are non-critical — leave panel hidden on failure
    }
  };

  useEffect(() => {
    setTimeout(() => fetchTeam(), 0);
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCreate = async () => {
    if (!teamName.trim()) { setActionError("Please enter a team name."); return; }
    setActionBusy(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const res = await fetch(`${API_BASE}/teams/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name: teamName })
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setActionError(body.detail ?? `Failed to create team (HTTP ${res.status}).`);
      } else {
        setActionSuccess("Team created.");
        setTeamName("");
        await fetchTeam();
      }
    } catch {
      setActionError("Network error while creating team.");
    } finally {
      setActionBusy(false);
    }
  };

  const handleInvite = async () => {
    if (!inviteEmail.trim()) { setActionError("Please enter an email address."); return; }
    setActionBusy(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const res = await fetch(`${API_BASE}/teams/invite`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ email: inviteEmail })
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setActionError(body.detail ?? `Invite failed (HTTP ${res.status}).`);
      } else {
        setActionSuccess(`Invitation sent to ${inviteEmail}.`);
        setInviteEmail("");
        await fetchTeam();
      }
    } catch {
      setActionError("Network error while sending invite.");
    } finally {
      setActionBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="p-6 bg-gray-900 text-white rounded" role="status" aria-live="polite">
        <p className="text-gray-400 animate-pulse">Loading team workspace…</p>
      </div>
    );
  }

  if (!team) {
    return (
      <div className="p-4 bg-gray-900 text-white rounded">
        <h2 className="text-xl mb-4">Create Enterprise Team</h2>
        {loadError && (
          <p role="alert" className="text-red-400 text-sm mb-3">{loadError}</p>
        )}
        {actionError && (
          <p role="alert" className="text-red-400 text-sm mb-3">{actionError}</p>
        )}
        <input
          type="text"
          value={teamName}
          onChange={(e) => setTeamName(e.target.value)}
          placeholder="Team Name"
          className="bg-gray-800 p-2 mr-2 rounded text-white"
        />
        <button
          onClick={handleCreate}
          disabled={actionBusy}
          className="bg-blue-600 px-4 py-2 rounded disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {actionBusy ? "Creating…" : "Create"}
        </button>
      </div>
    );
  }

  return (
    <div className="p-6 bg-gray-900 text-white rounded shadow-lg">
      <h2 className="text-2xl font-bold mb-6">{team.name} Workspace</h2>

      {(actionError || actionSuccess) && (
        <p
          role={actionError ? "alert" : "status"}
          aria-live="polite"
          className={`text-sm mb-4 ${actionError ? "text-red-400" : "text-green-400"}`}
        >
          {actionError ?? actionSuccess}
        </p>
      )}

      <div className="grid grid-cols-2 gap-8">
        <div>
          <h3 className="text-xl mb-4">Members</h3>
          <ul className="mb-4">
            {team.members.map((m: any) => (
              <li key={m.id} className="mb-2 py-2 border-b border-gray-700 flex justify-between">
                <span>{m.email}</span>
                <span className="text-gray-400 text-sm">{m.role}</span>
              </li>
            ))}
          </ul>

          <div className="flex">
            <input
              type="email"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="Invite by email"
              className="bg-gray-800 p-2 mr-2 rounded text-white flex-1"
            />
            <button
              onClick={handleInvite}
              disabled={actionBusy}
              className="bg-green-600 px-4 py-2 rounded disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {actionBusy ? "Sending…" : "Invite"}
            </button>
          </div>
        </div>

        {analytics && (
          <div className="bg-gray-800 p-6 rounded">
            <h3 className="text-xl mb-4">Usage Analytics</h3>
            <div className="text-4xl font-bold mb-2">{analytics.total_jobs}</div>
            <p className="text-gray-400 mb-6">Total simulations run this month</p>

            <h4 className="font-semibold mb-2">Status Breakdown</h4>
            <ul>
              {Object.entries(analytics.status_breakdown).map(([status, count]) => (
                <li key={status} className="flex justify-between mb-1 text-sm">
                  <span>{status}</span>
                  <span>{count as React.ReactNode}</span>
                </li>
              ))}
            </ul>

            <div className="mt-6 pt-6 border-t border-gray-700">
              <div className="flex justify-between text-sm mb-1">
                <span>Quota Utilization</span>
                <span>{((analytics.quota_used / analytics.quota_limit) * 100).toFixed(1)}%</span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2">
                <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${(analytics.quota_used / analytics.quota_limit) * 100}%` }}></div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
