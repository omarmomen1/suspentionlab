import React, { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function TeamSettings() {
  const { user, token } = useAuth();
  const [team, setTeam] = useState<any>(null);
  const [analytics, setAnalytics] = useState<any>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [teamName, setTeamName] = useState("");

  const fetchTeam = async () => {
    if (!token) return;
    const res = await fetch(`${API_BASE}/api/v1/teams/`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (res.ok) {
      setTeam(await res.json());
      fetchAnalytics();
    } else {
      setTeam(null);
    }
  };

  const fetchAnalytics = async () => {
    const res = await fetch(`${API_BASE}/api/v1/teams/analytics`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (res.ok) {
      setAnalytics(await res.json());
    }
  };

  useEffect(() => {
    fetchTeam();
  }, [token]);

  const handleCreate = async () => {
    await fetch(`${API_BASE}/api/v1/teams/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ name: teamName })
    });
    fetchTeam();
  };

  const handleInvite = async () => {
    await fetch(`${API_BASE}/api/v1/teams/invite`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ email: inviteEmail })
    });
    setInviteEmail("");
    fetchTeam();
  };

  if (!team) {
    return (
      <div className="p-4 bg-gray-900 text-white rounded">
        <h2 className="text-xl mb-4">Create Enterprise Team</h2>
        <input 
          type="text" 
          value={teamName} 
          onChange={(e) => setTeamName(e.target.value)}
          placeholder="Team Name"
          className="bg-gray-800 p-2 mr-2 rounded text-white"
        />
        <button onClick={handleCreate} className="bg-blue-600 px-4 py-2 rounded">Create</button>
      </div>
    );
  }

  return (
    <div className="p-6 bg-gray-900 text-white rounded shadow-lg">
      <h2 className="text-2xl font-bold mb-6">{team.name} Workspace</h2>
      
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
            <button onClick={handleInvite} className="bg-green-600 px-4 py-2 rounded">Invite</button>
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
