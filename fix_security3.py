import os

project_dir = r"C:\Users\omaar\Downloads\project"

# 1. Update auth.py
auth_path = os.path.join(project_dir, r"src\suspensionlab\backend\security\auth.py")
with open(auth_path, "r", encoding="utf-8") as f:
    auth_content = f.read()

bad_auth = """        payload = decode_access_token(token)
        if payload:
            user_id = payload.get("sub")"""

good_auth = """        payload = decode_access_token(token)
        if payload:
            if payload.get("type") != "access":
                from suspensionlab.backend.core.errors import AuthenticationError
                raise AuthenticationError("Invalid token type. Only access tokens are allowed here.")
            user_id = payload.get("sub")"""

auth_content = auth_content.replace(bad_auth, good_auth)
with open(auth_path, "w", encoding="utf-8") as f:
    f.write(auth_content)


# 2. Update jwt_utils.py
jwt_path = os.path.join(project_dir, r"src\suspensionlab\backend\security\jwt_utils.py")
with open(jwt_path, "r", encoding="utf-8") as f:
    jwt_content = f.read()

bad_jwt = """import os
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

# ─── Config ──────────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "susplab-secret-change-in-production-please")"""

good_jwt = """import os
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from suspensionlab.backend.config import get_env_or_fail

# ─── Config ──────────────────────────────────────────────────────────────────

SECRET_KEY = get_env_or_fail("JWT_SECRET_KEY")"""

jwt_content = jwt_content.replace(bad_jwt, good_jwt)
with open(jwt_path, "w", encoding="utf-8") as f:
    f.write(jwt_content)

print("Security successfully patched.")
