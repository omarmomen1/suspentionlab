import os
import shutil

project_dir = r"C:\Users\omaar\Downloads\project"

# 1. Delete streamlit_app directory
streamlit_dir = os.path.join(project_dir, r"src\suspensionlab\frontend\streamlit_app")
if os.path.exists(streamlit_dir):
    shutil.rmtree(streamlit_dir)

# 2. Fix auth_routes.py syntax
auth_path = os.path.join(project_dir, r"src\suspensionlab\backend\api\routes\auth_routes.py")
with open(auth_path, "r", encoding="utf-8") as f:
    auth_content = f.read()

# Fix the import interleaving
bad_import = """from suspensionlab.backend.security.jwt_utils import (
from suspensionlab.shared.models import PlanTier
    hash_password, verify_password, create_access_token, create_refresh_token, decode_access_token
)"""
good_import = """from suspensionlab.backend.security.jwt_utils import (
    hash_password, verify_password, create_access_token, create_refresh_token, decode_access_token
)
from suspensionlab.shared.models import PlanTier"""
auth_content = auth_content.replace(bad_import, good_import)

# Fix the AuthResponse forward reference
if "class AuthResponse(BaseModel):" in auth_content:
    import re
    # Match the AuthResponse class correctly
    auth_resp_match = re.search(r"class AuthResponse\(BaseModel\):.*?    tier: str\n", auth_content, flags=re.DOTALL)
    if auth_resp_match:
        auth_content = auth_content.replace(auth_resp_match.group(0), "")
        # Inject it before RefreshRequest
        auth_content = auth_content.replace("class RefreshRequest(BaseModel):", auth_resp_match.group(0) + "\nclass RefreshRequest(BaseModel):")

with open(auth_path, "w", encoding="utf-8") as f:
    f.write(auth_content)

# 3. Clean up .env files
root_env = os.path.join(project_dir, ".env")
if os.path.exists(root_env):
    os.remove(root_env) # remove it entirely to prevent bundling

frontend_env = os.path.join(project_dir, r"frontend\.env")
if os.path.exists(frontend_env):
    os.remove(frontend_env)

frontend_env_local_example = os.path.join(project_dir, r"frontend\.env.local.example")
if os.path.exists(frontend_env_local_example):
    with open(frontend_env_local_example, "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace("susplab_admin_2026", "")
    with open(frontend_env_local_example, "w", encoding="utf-8") as f:
        f.write(content)

# 4. Fix AuthContext.tsx
auth_ctx_path = os.path.join(project_dir, r"frontend\contexts\AuthContext.tsx")
if os.path.exists(auth_ctx_path):
    with open(auth_ctx_path, "r", encoding="utf-8") as f:
        auth_ctx_content = f.read()
    auth_ctx_content = auth_ctx_content.replace('const apiKey = process.env.NEXT_PUBLIC_API_KEY ?? "susplab_admin_2026";', 'const apiKey = process.env.NEXT_PUBLIC_API_KEY ?? "";')
    with open(auth_ctx_path, "w", encoding="utf-8") as f:
        f.write(auth_ctx_content)

# 5. Fix README.md and Helm Chart references
readme_path = os.path.join(project_dir, "README.md")
if os.path.exists(readme_path):
    with open(readme_path, "r", encoding="utf-8") as f:
        readme_content = f.read()
    readme_content = readme_content.replace("Streamlit -> FastAPI", "Next.js -> FastAPI")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)

print("All audit feedback addressed.")
