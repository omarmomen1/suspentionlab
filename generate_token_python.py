import os
import sys
import jwt

secret = os.getenv("JWT_SECRET") or os.getenv("JWT_SECRET_KEY")
if not secret or len(secret) < 32:
    print("CRITICAL: JWT_SECRET or JWT_SECRET_KEY environment variable is required and must be >= 32 characters.", file=sys.stderr)
    sys.exit(1)

encoded_jwt = jwt.encode({"user_id": "test"}, secret.encode("utf-8"), algorithm="HS256", headers={"kid": "v1"})
print(encoded_jwt)
