import os

def patch_job():
    filepath = "d:/project/src/suspensionlab/backend/database/models/job.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = content.replace(
        'CheckConstraint("status IN (\'PENDING\', \'RUNNING\', \'COMPLETED\', \'FAILED\', \'CANCELED\')")',
        'CheckConstraint("status IN (\'PENDING\', \'RUNNING\', \'COMPLETED\', \'FAILED\', \'CANCELED\')", name="chk_job_status")'
    )
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def patch_profile():
    filepath = "d:/project/src/suspensionlab/backend/database/models/profile.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = content.replace(
        'CheckConstraint("vehicle_type IN (\'QUARTER_CAR\', \'HALF_CAR\', \'FULL_CAR\')")',
        'CheckConstraint("vehicle_type IN (\'QUARTER_CAR\', \'HALF_CAR\', \'FULL_CAR\')", name="chk_vehicle_type")'
    )
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    patch_job()
    patch_profile()
