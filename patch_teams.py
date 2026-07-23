import os
import re

filepath = "d:/project/src/suspensionlab/backend/api/routes/teams_routes.py"

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix N+1 in get_team
if "selectinload" not in content:
    content = content.replace("from sqlalchemy import select", "from sqlalchemy import select\nfrom sqlalchemy.orm import selectinload")

old_get_team = """    team_result = await db.execute(select(Team).where(Team.id == user["team_id"]))
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")

    members_result = await db.execute(select(User).where(User.team_id == team.id))
    members = members_result.scalars().all()"""

new_get_team = """    team_result = await db.execute(
        select(Team)
        .options(selectinload(Team.members))
        .where(Team.id == user["team_id"])
    )
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")
    members = team.members"""

content = content.replace(old_get_team, new_get_team)

# Remove plan overwriting
content = content.replace("    target_user.plan = PlanTier.ENTERPRISE\n", "")
content = content.replace("    target_user.plan = PlanTier.FREE\n", "")

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("teams_routes.py patched")
