import os

project_dir = r"C:\Users\omaar\Downloads\project"

# Fix monte_carlo.py
mc_path = os.path.join(project_dir, r"src\suspensionlab\backend\api\routes\simulate\monte_carlo.py")
with open(mc_path, "r", encoding="utf-8") as f:
    mc_content = f.read()

bad_mc = """    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")

    job_id = str(uuid.uuid4())"""

good_mc = """    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
        
    from suspensionlab.backend.services.quota import assert_can_run_job
    tier = getattr(request.state, "tier", "FREE")
    await assert_can_run_job(db, user_id, tier)

    job_id = str(uuid.uuid4())"""

mc_content = mc_content.replace(bad_mc, good_mc)
with open(mc_path, "w", encoding="utf-8") as f:
    f.write(mc_content)

# Fix sweep.py
sw_path = os.path.join(project_dir, r"src\suspensionlab\backend\api\routes\simulate\sweep.py")
with open(sw_path, "r", encoding="utf-8") as f:
    sw_content = f.read()

bad_sw = """    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")

    job_id = str(uuid.uuid4())"""

good_sw = """    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required.")
        
    from suspensionlab.backend.services.quota import assert_can_run_job
    tier = getattr(request.state, "tier", "FREE")
    await assert_can_run_job(db, user_id, tier)

    job_id = str(uuid.uuid4())"""

sw_content = sw_content.replace(bad_sw, good_sw)
with open(sw_path, "w", encoding="utf-8") as f:
    f.write(sw_content)

print("Performance and Scalability successfully patched.")
