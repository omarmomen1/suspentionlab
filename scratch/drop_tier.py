import os
import re

files_to_update = {
    "src/suspensionlab/backend/database/models/user.py": [
        (r"^\s*tier\s*=\s*Column.*?\n", "")
    ],
    "src/suspensionlab/backend/api/main.py": [
        (r"\s*tier=PlanTier\.FREE,", ""),
        (r"\s*tier=PlanTier\.ENTERPRISE,", ""),
        (r'"tier": user\.get\("tier", PlanTier\.FREE\)', '"plan": user.get("plan", PlanTier.FREE)')
    ],
    "src/suspensionlab/backend/security/auth.py": [
        (r'\s*"tier":\s*user\.plan,', ""),
        (r'\s*"tier":\s*PlanTier\.ENTERPRISE,', "")
    ],
    "src/suspensionlab/backend/api/routes/auth_routes.py": [
        (r"\s*tier=PlanTier\.PRO,", ""),
        (r"^\s*user\.tier\s*=\s*PlanTier\.FREE.*?\n", "")
    ],
    "src/suspensionlab/backend/api/routes/billing_routes.py": [
        (r"^\s*user\.tier\s*=\s*user\.plan.*?\n", ""),
        (r"^\s*user\.tier\s*=\s*PlanTier\.FREE.*?\n", "")
    ],
    "src/suspensionlab/backend/api/routes/teams_routes.py": [
        (r"^\s*target_user\.tier\s*=\s*PlanTier\.ENTERPRISE.*?\n", ""),
        (r"^\s*target_user\.tier\s*=\s*PlanTier\.FREE.*?\n", "")
    ],
    "src/suspensionlab/backend/billing/webhooks.py": [
        (r"^\s*db_user\.tier\s*=\s*plan.*?\n", "")
    ],
    "src/suspensionlab/backend/api/routes/simulate/monte_carlo.py": [
        (r'tier = getattr\(request\.state, "tier", "FREE"\)', 'tier = getattr(request.state, "plan", "FREE")')
    ],
    "src/suspensionlab/backend/api/routes/simulate/sweep.py": [
        (r'tier = getattr\(request\.state, "tier", "FREE"\)', 'tier = getattr(request.state, "plan", "FREE")')
    ]
}

base_dir = r"C:\Users\omaar\Downloads\project"

for rel_path, rules in files_to_update.items():
    path = os.path.join(base_dir, rel_path)
    if not os.path.exists(path):
        continue
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    for pattern, repl in rules:
        content = re.sub(pattern, repl, content, flags=re.MULTILINE)
        
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

print("Removed all tier references.")
