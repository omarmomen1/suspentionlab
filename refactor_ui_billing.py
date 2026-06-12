import os

project_dir = r"C:\Users\omaar\Downloads\project"

# 1. Update billing_routes.py
billing_path = os.path.join(project_dir, r"src\suspensionlab\backend\api\routes\billing_routes.py")
with open(billing_path, "r", encoding="utf-8") as f:
    billing_content = f.read()

old_webhook = """    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        result = await db.execute(select(User).where(User.stripe_customer_id == sub["customer"]))
        user = result.scalar_one_or_none()
        if user:
            user.plan = PlanTier.FREE
            user.tier = PlanTier.FREE
            await db.commit()"""

new_webhook = """    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        result = await db.execute(select(User).where(User.stripe_customer_id == sub["customer"]))
        user = result.scalar_one_or_none()
        if user:
            # 14-day grace period
            user.plan = PlanTier.PAST_DUE
            user.tier = PlanTier.PAST_DUE
            await db.commit()"""
billing_content = billing_content.replace(old_webhook, new_webhook)

with open(billing_path, "w", encoding="utf-8") as f:
    f.write(billing_content)


# 2. Update teams_routes.py
teams_path = os.path.join(project_dir, r"src\suspensionlab\backend\api\routes\teams_routes.py")
with open(teams_path, "r", encoding="utf-8") as f:
    teams_content = f.read()

analytics_route = """
@router.get("/analytics")
async def get_team_analytics(
    user: dict = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db_dependency),
):
    if not user.get("team_id"):
        raise HTTPException(status_code=400, detail="You are not in a team.")

    from sqlalchemy import func
    from suspensionlab.backend.database.models.job import JobRecord
    
    # Get all team members
    members_result = await db.execute(select(User.id).where(User.team_id == user["team_id"]))
    member_ids = members_result.scalars().all()
    
    # Aggregate jobs for the team
    if not member_ids:
        return {"total_jobs": 0, "status_breakdown": {}}
        
    jobs_result = await db.execute(
        select(JobRecord.status, func.count(JobRecord.id))
        .where(JobRecord.user_id.in_(member_ids))
        .group_by(JobRecord.status)
    )
    
    status_breakdown = {}
    total_jobs = 0
    for status, count in jobs_result.all():
        status_breakdown[status] = count
        total_jobs += count
        
    return {
        "total_jobs": total_jobs,
        "status_breakdown": status_breakdown,
        "quota_limit": 1000,
        "quota_used": total_jobs
    }
"""
if "def get_team_analytics" not in teams_content:
    teams_content += analytics_route

with open(teams_path, "w", encoding="utf-8") as f:
    f.write(teams_content)

# 3. Update TeamSettings.tsx
team_settings_path = os.path.join(project_dir, r"frontend\components\TeamSettings.tsx")
new_team_settings = """import React, { useState, useEffect } from "react";
import { useAuth } from "../hooks/useAuth";

export default function TeamSettings() {
  const { user, token } = useAuth();
  const [team, setTeam] = useState<any>(null);
  const [analytics, setAnalytics] = useState<any>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [teamName, setTeamName] = useState("");

  const fetchTeam = async () => {
    if (!token) return;
    const res = await fetch("http://localhost:8000/api/v1/teams/", {
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
    const res = await fetch("http://localhost:8000/api/v1/teams/analytics", {
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
    await fetch("http://localhost:8000/api/v1/teams/", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ name: teamName })
    });
    fetchTeam();
  };

  const handleInvite = async () => {
    await fetch("http://localhost:8000/api/v1/teams/invite", {
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
"""

with open(team_settings_path, "w", encoding="utf-8") as f:
    f.write(new_team_settings)

print("Commercial UI and Analytics refactored.")
