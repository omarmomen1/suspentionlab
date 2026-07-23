import os
import re

directory = r'd:\project\src\suspensionlab\backend\api\routes'

for root, _, files in os.walk(directory):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # Replace user["property"] -> user.property
            # Also handle user.get("property") -> getattr(user, "property", None)
            
            content = re.sub(r'user\[\"([a-zA-Z0-9_]+)\"\]', r'user.\1', content)
            
            # For user.get("team_id") we want user.team_id (since we know the schema)
            content = re.sub(r'user\.get\(\"([a-zA-Z0-9_]+)\"\)', r'user.\1', content)
            
            with open(path, 'w', encoding='utf-8') as file:
                file.write(content)
