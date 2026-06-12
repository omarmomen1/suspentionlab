import os
import re

PROJECT_DIR = r"C:\Users\omaar\Downloads\project"
files_to_update = [
    r"src\suspensionlab\backend\api\routes\auth_routes.py",
    r"src\suspensionlab\backend\api\routes\billing_routes.py",
    r"src\suspensionlab\backend\api\routes\api_key_routes.py",
    r"src\suspensionlab\backend\api\routes\audit_routes.py",
    r"src\suspensionlab\backend\api\routes\teams_routes.py",
    r"src\suspensionlab\backend\database\models\user.py",
    r"src\suspensionlab\backend\security\auth.py",
    r"src\suspensionlab\backend\services\quota.py",
    r"src\suspensionlab\backend\api\main.py",
    r"create_user.py"
]

for file_path in files_to_update:
    path = os.path.join(PROJECT_DIR, file_path)
    if not os.path.exists(path):
        print(f"Not found: {path}")
        continue
    
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "PlanTier" not in content:
        if "from suspensionlab.shared.models import" in content:
            content = re.sub(
                r'from suspensionlab\.shared\.models import ([^\n]+)\n',
                r'from suspensionlab.shared.models import \1, PlanTier\n',
                content,
                count=1
            )
        else:
            # Fallback
            lines = content.split('\n')
            import_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("import") or line.startswith("from"):
                    import_idx = i
            lines.insert(import_idx + 1, "from suspensionlab.shared.models import PlanTier")
            content = "\n".join(lines)
            
    content = content.replace('"FREE"', "PlanTier.FREE")
    content = content.replace('"PRO"', "PlanTier.PRO")
    content = content.replace('"ENTERPRISE"', "PlanTier.ENTERPRISE")
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

print("Replaced magic strings successfully.")
