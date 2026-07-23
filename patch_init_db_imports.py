import os

def patch_init_db():
    filepath = "d:/project/init_db.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace individual imports with the entire module or just add the missing ones
    missing_imports = """from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.database.models.billing import StripeEvent
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user_api_key import UserApiKey
from suspensionlab.backend.database.models.session import SimSession, SessionComment
from suspensionlab.backend.database.models.shared_report import SharedReport
"""
    
    # Simple replace
    old_imports = """from suspensionlab.backend.database.models.user import User
from suspensionlab.backend.database.models.profile import VehicleProfile
from suspensionlab.backend.database.models.job import JobRecord
from suspensionlab.backend.database.models.billing import StripeEvent
from suspensionlab.backend.database.models.team import Team
from suspensionlab.backend.database.models.user_api_key import UserApiKey"""

    content = content.replace(old_imports, missing_imports)
    
    # User Model dropped "tier"
    content = content.replace('tier="ENTERPRISE",', '')
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    patch_init_db()
