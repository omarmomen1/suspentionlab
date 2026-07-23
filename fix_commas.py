import os
import re

dashboards = [
    "frontend/app/full-car/page.tsx",
    "frontend/app/half-car/page.tsx",
    "frontend/app/active/page.tsx",
    "frontend/app/durability/page.tsx",
    "frontend/app/handling/page.tsx",
    "frontend/app/kinematics/page.tsx",
    "frontend/app/nvh/page.tsx",
    "frontend/app/sensitivity/page.tsx"
]

base_dir = r"d:\project"

for dash in dashboards:
    file_path = os.path.join(base_dir, dash)
    if not os.path.exists(file_path):
        continue
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace ',,' with ','
    content = content.replace(",, Undo2", ", Undo2")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"Fixed commas in {dash}")
