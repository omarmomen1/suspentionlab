import os
import re

directory = r'd:\project\src\suspensionlab\backend\api\routes'

for root, _, files in os.walk(directory):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            content = re.sub(r'user\.get\(\"plan\",\s*\"FREE\"\)', 'user.plan', content)
            
            with open(path, 'w', encoding='utf-8') as file:
                file.write(content)
