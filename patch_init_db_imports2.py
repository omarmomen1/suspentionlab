import os

def patch_init_db2():
    filepath = "d:/project/init_db.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    missing = """from suspensionlab.backend.database.models.user_session import UserSession
from suspensionlab.backend.database.models.billing import StripeEvent, LemonEvent
"""
    content = content.replace("from suspensionlab.backend.database.models.billing import StripeEvent", missing)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    patch_init_db2()
