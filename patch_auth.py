import os

filepath = "d:/project/src/suspensionlab/backend/security/auth.py"

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

patch_code = """
            effective_plan = user.plan
            if user.team_id:
                from suspensionlab.backend.database.models.team import Team
                team_res = await db.execute(select(Team).where(Team.id == user.team_id))
                team = team_res.scalar_one_or_none()
                if team:
                    effective_plan = team.plan
"""

content = content.replace(
    '            return {\n                "user_id": str(user.id),\n                "plan":    user.plan,',
    patch_code + '            return {\n                "user_id": str(user.id),\n                "plan":    effective_plan,'
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("auth.py patched")
