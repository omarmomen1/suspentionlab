import os

def patch_job():
    filepath = "d:/project/src/suspensionlab/backend/database/models/job.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if "CheckConstraint('status IN" not in content:
        content = content.replace(
            "status = Column(String, default=\"PENDING\")",
            "status = Column(String, CheckConstraint(\"status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELED')\"), default=\"PENDING\")"
        )
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print("job.py constraints patched")

def patch_profile():
    filepath = "d:/project/src/suspensionlab/backend/database/models/profile.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if "CheckConstraint('vehicle_type IN" not in content:
        if "from sqlalchemy import Column" in content and "CheckConstraint" not in content:
            content = content.replace("from sqlalchemy import Column", "from sqlalchemy import Column, CheckConstraint")
        
        content = content.replace(
            "vehicle_type = Column(String, default=\"QUARTER_CAR\") # e.g. QUARTER_CAR, HALF_CAR, FULL_CAR",
            "vehicle_type = Column(String, CheckConstraint(\"vehicle_type IN ('QUARTER_CAR', 'HALF_CAR', 'FULL_CAR')\"), default=\"QUARTER_CAR\")"
        )
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print("profile.py constraints patched")

if __name__ == "__main__":
    patch_job()
    patch_profile()
