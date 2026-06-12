import os

project_dir = r"C:\Users\omaar\Downloads\project"

# 1. Update jwt_utils.py
jwt_path = os.path.join(project_dir, r"src\suspensionlab\backend\security\jwt_utils.py")
with open(jwt_path, "r", encoding="utf-8") as f:
    content = f.read()

old_expire = "ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days"
new_expire = """ACCESS_TOKEN_EXPIRE_MINUTES = 15  # 15 minutes
REFRESH_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days"""
content = content.replace(old_expire, new_expire)

old_helpers = """def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)"""

new_helpers = """def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)"""
content = content.replace(old_helpers, new_helpers)

with open(jwt_path, "w", encoding="utf-8") as f:
    f.write(content)

# 2. Update auth_routes.py
auth_routes_path = os.path.join(project_dir, r"src\suspensionlab\backend\api\routes\auth_routes.py")
with open(auth_routes_path, "r", encoding="utf-8") as f:
    auth_content = f.read()

old_import = "    hash_password, verify_password, create_access_token"
new_import = "    hash_password, verify_password, create_access_token, create_refresh_token, decode_access_token"
auth_content = auth_content.replace(old_import, new_import)

old_schema = """class AuthResponse(BaseModel):
    token: str
    user_id: str"""
new_schema = """class AuthResponse(BaseModel):
    token: str
    refresh_token: str
    user_id: str"""
auth_content = auth_content.replace(old_schema, new_schema)

old_reg_token = """    token = create_access_token({"sub": str(user.id), "email": user.email, "plan": user.plan})
    return AuthResponse(
        token=token,
        user_id=str(user.id),"""
new_reg_token = """    token = create_access_token({"sub": str(user.id), "email": user.email, "plan": user.plan})
    r_token = create_refresh_token({"sub": str(user.id), "email": user.email})
    return AuthResponse(
        token=token,
        refresh_token=r_token,
        user_id=str(user.id),"""
auth_content = auth_content.replace(old_reg_token, new_reg_token)

old_log_token = """    token = create_access_token({"sub": str(user.id), "email": user.email, "plan": user.plan})
    return AuthResponse(
        token=token,
        user_id=str(user.id),"""
new_log_token = """    token = create_access_token({"sub": str(user.id), "email": user.email, "plan": user.plan})
    r_token = create_refresh_token({"sub": str(user.id), "email": user.email})
    return AuthResponse(
        token=token,
        refresh_token=r_token,
        user_id=str(user.id),"""
auth_content = auth_content.replace(old_log_token, new_log_token)

# Add refresh endpoint
refresh_endpoint = """class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/refresh", response_model=AuthResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db_dependency)):
    payload = decode_access_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token.")
        
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
        
    access_token = create_access_token({"sub": str(user.id), "email": user.email, "plan": user.plan})
    new_refresh_token = create_refresh_token({"sub": str(user.id), "email": user.email})
    
    return AuthResponse(
        token=access_token,
        refresh_token=new_refresh_token,
        user_id=str(user.id),
        email=user.email,
        name=user.name or "",
        plan=user.plan,
        onboarding_complete=user.onboarding_complete,
    )

"""
auth_content = auth_content.replace("class RegisterRequest(BaseModel):", refresh_endpoint + "class RegisterRequest(BaseModel):")

with open(auth_routes_path, "w", encoding="utf-8") as f:
    f.write(auth_content)

print("JWT refactored.")
