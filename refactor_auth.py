import os

filepath = r"C:\Users\omaar\Downloads\project\src\suspensionlab\backend\security\auth.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Replace hardcoded master key
old_master_key = """        # 2a. Master admin key (dev/CI only — warn if used in PROD)
        if api_key == "susplab_admin_2026":
            import os
            if os.getenv("ENVIRONMENT", "DEV") == "PROD":"""

new_master_key = """        # 2a. Master admin key (dev/CI only — warn if used in PROD)
        from suspensionlab.backend.config import settings
        import os
        if api_key == settings.admin_api_key:
            if os.getenv("ENVIRONMENT", "DEV") == "PROD":"""
content = content.replace(old_master_key, new_master_key)

# Fix O(n) lookup
old_lookup = """        # 2c. Look up per-user named API key
        from suspensionlab.backend.database.models.user_api_key import UserApiKey
        from suspensionlab.backend.security.jwt_utils import verify_password
        from datetime import datetime, timezone

        key_results = await db.execute(
            select(UserApiKey).where(UserApiKey.is_active == True)
        )
        for named_key in key_results.scalars():
            # Skip expired keys
            if named_key.expires_at and datetime.now(timezone.utc) > named_key.expires_at:
                continue
            if verify_password(api_key, named_key.key_hash):
                # Update last_used
                named_key.last_used = datetime.now(timezone.utc)
                await db.commit()

                user_result = await db.execute(select(User).where(User.id == named_key.user_id))
                user = user_result.scalar_one_or_none()
                if user:
                    request.state.user_id = str(user.id)
                    log_audit_event("LOGIN_SUCCESS", user_id=str(user.id), ip=ip)
                    return {
                        "user_id": str(user.id),
                        "tier":    user.plan,
                        "plan":    user.plan,
                        "email":   user.email,
                        "name":    user.name or "",
                        "onboarding_complete": user.onboarding_complete,
                        "team_id": str(user.team_id) if user.team_id else None,
                    }"""

new_lookup = """        # 2c. Look up per-user named API key (O(1) prefix lookup)
        from suspensionlab.backend.database.models.user_api_key import UserApiKey
        from suspensionlab.backend.security.jwt_utils import verify_password
        from datetime import datetime, timezone
        
        # All valid generated keys start with slk_ and use 12 chars for prefix
        if api_key.startswith("slk_") and len(api_key) > 12:
            prefix = api_key[:12]
            key_results = await db.execute(
                select(UserApiKey).where(UserApiKey.key_prefix == prefix, UserApiKey.is_active == True)
            )
            for named_key in key_results.scalars():
                # Skip expired keys
                if named_key.expires_at and datetime.now(timezone.utc) > named_key.expires_at:
                    continue
                if verify_password(api_key, named_key.key_hash):
                    # Update last_used
                    named_key.last_used = datetime.now(timezone.utc)
                    await db.commit()

                    user_result = await db.execute(select(User).where(User.id == named_key.user_id))
                    user = user_result.scalar_one_or_none()
                    if user:
                        request.state.user_id = str(user.id)
                        log_audit_event("LOGIN_SUCCESS", user_id=str(user.id), ip=ip)
                        return {
                            "user_id": str(user.id),
                            "tier":    user.plan,
                            "plan":    user.plan,
                            "email":   user.email,
                            "name":    user.name or "",
                            "onboarding_complete": user.onboarding_complete,
                            "team_id": str(user.team_id) if user.team_id else None,
                        }"""
content = content.replace(old_lookup, new_lookup)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Auth refactored.")
