import os

def patch_profiles():
    filepath = "d:/project/src/suspensionlab/backend/api/routes/profiles.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if "from sqlalchemy import func" not in content:
        content = content.replace("from sqlalchemy.future import select", "from sqlalchemy.future import select\nfrom sqlalchemy import func")
        
    # Soft delete in delete_profile
    content = content.replace("await db.delete(profile)", "profile.deleted_at = func.now()")
    
    # Filter deleted_at in list_profiles
    content = content.replace("if vehicle_type:", "query = query.where(VehicleProfile.deleted_at.is_(None))\n    if vehicle_type:")
    
    # Filter deleted_at in get_profile and delete_profile
    # We can just replace the query building
    content = content.replace(
        "VehicleProfile.team_id == user[\"team_id\"],", 
        "VehicleProfile.team_id == user[\"team_id\"],\n            VehicleProfile.deleted_at.is_(None),"
    )
    content = content.replace(
        "VehicleProfile.user_id == user[\"user_id\"],", 
        "VehicleProfile.user_id == user[\"user_id\"],\n            VehicleProfile.deleted_at.is_(None),"
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("profiles.py patched")

def patch_jobs():
    filepath = "d:/project/src/suspensionlab/backend/api/routes/jobs.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # In get_job_status
    content = content.replace(
        "JobRecord.user_id == user_uuid",
        "JobRecord.user_id == user_uuid,\n            JobRecord.deleted_at.is_(None)"
    )
    
    # In stream_job_status
    content = content.replace(
        "JobRecord.id == job_uuid, JobRecord.user_id == user_uuid",
        "JobRecord.id == job_uuid, JobRecord.user_id == user_uuid, JobRecord.deleted_at.is_(None)"
    )

    # In list_jobs
    content = content.replace(
        "query = select(JobRecord).where(JobRecord.user_id == user[\"user_id\"])",
        "query = select(JobRecord).where(JobRecord.user_id == user[\"user_id\"], JobRecord.deleted_at.is_(None))"
    )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("jobs.py patched")

if __name__ == "__main__":
    patch_profiles()
    patch_jobs()
