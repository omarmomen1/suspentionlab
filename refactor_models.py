import os
import re

def patch_file(filepath, patch_func):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    new_content = patch_func(content)
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Patched {filepath}")
    else:
        print(f"No changes in {filepath}")

def patch_user(content):
    if "from sqlalchemy.orm import relationship" not in content:
        content = content.replace("from sqlalchemy.orm import synonym", "from sqlalchemy.orm import synonym, relationship")
    
    content = re.sub(r'lemon_customer_id\s*=\s*Column\(String\(255\), nullable=True\)', 'billing_customer_id    = Column(String(255), nullable=True)', content)
    content = re.sub(r'lemon_subscription_id\s*=\s*Column\(String\(255\), nullable=True\)', 'billing_subscription_id = Column(String(255), nullable=True)', content)
    content = re.sub(r'stripe_customer_id\s*=\s*synonym\("lemon_customer_id"\)\s*', '', content)
    content = re.sub(r'stripe_subscription_id\s*=\s*synonym\("lemon_subscription_id"\)\s*', '', content)
    content = content.replace('"lemon_customer_id"', '"billing_customer_id"')
    content = content.replace('ix_users_lemon_cust', 'ix_users_billing_cust')
    
    if "deleted_at" not in content:
        content = content.replace("created_at             = Column(DateTime(timezone=True), server_default=func.now())", 
                                  "deleted_at             = Column(DateTime(timezone=True), nullable=True)\n    created_at             = Column(DateTime(timezone=True), server_default=func.now())")

    if "team = relationship" not in content:
        content += """
    # Relationships
    team = relationship("Team", back_populates="members")
    jobs = relationship("JobRecord", back_populates="user")
    profiles = relationship("VehicleProfile", back_populates="user")
    sessions = relationship("SimSession", back_populates="owner")
"""
    return content

def patch_team(content):
    if "from sqlalchemy.orm import relationship" not in content:
        content = content.replace("from sqlalchemy.dialects.postgresql import UUID", "from sqlalchemy.dialects.postgresql import UUID\nfrom sqlalchemy.orm import relationship")
    
    if "deleted_at" not in content:
        content = content.replace("created_at = Column(DateTime(timezone=True), server_default=func.now())",
                                  "deleted_at = Column(DateTime(timezone=True), nullable=True)\n    created_at = Column(DateTime(timezone=True), server_default=func.now())")
    
    if "members = relationship" not in content:
        content += """
    # Relationships
    members = relationship("User", back_populates="team")
    jobs = relationship("JobRecord", back_populates="team")
    profiles = relationship("VehicleProfile", back_populates="team")
    sessions = relationship("SimSession", back_populates="team")
"""
    return content

def patch_job(content):
    if "from sqlalchemy.orm import relationship" not in content:
        content = content.replace("from suspensionlab.backend.database.core import Base", "from suspensionlab.backend.database.core import Base\nfrom sqlalchemy.orm import relationship")
        content = content.replace("from sqlalchemy import Column", "from sqlalchemy import Column, Enum, CheckConstraint")
        
    if "deleted_at" not in content:
        content = content.replace("started_at = Column(DateTime, default=datetime.utcnow)",
                                  "deleted_at = Column(DateTime(timezone=True), nullable=True)\n    started_at = Column(DateTime, default=datetime.utcnow)")
        
    content = content.replace('ondelete="CASCADE"', 'ondelete="SET NULL"')
    
    if "user = relationship" not in content:
        content += """
    # Relationships
    user = relationship("User", back_populates="jobs")
    team = relationship("Team", back_populates="jobs")
    session = relationship("SimSession", back_populates="jobs")
"""
    return content

def patch_profile(content):
    if "from sqlalchemy.orm import relationship" not in content:
        content = content.replace("from suspensionlab.backend.database.core import Base", "from suspensionlab.backend.database.core import Base\nfrom sqlalchemy.orm import relationship")

    if "deleted_at" not in content:
        content = content.replace("created_at = Column(DateTime, default=datetime.utcnow)",
                                  "deleted_at = Column(DateTime(timezone=True), nullable=True)\n    created_at = Column(DateTime, default=datetime.utcnow)")
        
    content = content.replace('ondelete="CASCADE"', 'ondelete="SET NULL"')
    
    if "user = relationship" not in content:
        content += """
    # Relationships
    user = relationship("User", back_populates="profiles")
    team = relationship("Team", back_populates="profiles")
"""
    return content

def patch_session(content):
    if "deleted_at" not in content:
        content = content.replace("created_at = Column(DateTime, default=datetime.utcnow)",
                                  "deleted_at = Column(DateTime(timezone=True), nullable=True)\n    created_at = Column(DateTime, default=datetime.utcnow)")
    
    content = content.replace('ondelete="CASCADE"', 'ondelete="SET NULL"')
    
    if "owner = relationship" not in content:
        content = content.replace("class SimSession(Base):", "class SimSession(Base):\n    # Relationships\n    owner = relationship('User', back_populates='sessions')\n    team = relationship('Team', back_populates='sessions')\n    jobs = relationship('JobRecord', back_populates='session')\n    comments = relationship('SessionComment', back_populates='session')\n")
        
    if "session = relationship" not in content:
        content = content.replace("class SessionComment(Base):", "class SessionComment(Base):\n    # Relationships\n    session = relationship('SimSession', back_populates='comments')\n    author = relationship('User')\n")
    
    if "Index(\"ix_session_comments_author_id\", \"author_id\")" not in content:
        content = content.replace("__tablename__ = \"session_comments\"", "__tablename__ = \"session_comments\"\n    __table_args__ = (Index(\"ix_session_comments_author_id\", \"author_id\"),)")
        content = content.replace("from sqlalchemy import Column", "from sqlalchemy import Column, Index")
    return content

def patch_user_session(content):
    if "Index(\"ix_user_sessions_expires_at\", \"expires_at\")" not in content:
        content = content.replace("__tablename__ = \"user_sessions\"", "__tablename__ = \"user_sessions\"\n    __table_args__ = (Index(\"ix_user_sessions_expires_at\", \"expires_at\"),)")
        content = content.replace("from sqlalchemy import Column", "from sqlalchemy import Column, Index")
    return content

def patch_shared_report(content):
    if "from sqlalchemy import Column, String, DateTime, JSON, Boolean" in content:
        content = content.replace("from sqlalchemy import Column, String, DateTime, JSON, Boolean", "from sqlalchemy import Column, String, DateTime, JSON, Boolean, Integer")
    
    if "JSON_TYPE" not in content:
        content = content.replace("from sqlalchemy.dialects.postgresql import UUID as PG_UUID", "from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB\n\nJSON_TYPE = JSON().with_variant(JSONB, 'postgresql')")
        content = content.replace("params = Column(JSON, nullable=False)", "params = Column(JSON_TYPE, nullable=False)")
        content = content.replace("result = Column(JSON, nullable=False)", "result = Column(JSON_TYPE, nullable=False)")
    
    if "view_count = Column(String, default=\"0\")" in content:
        content = content.replace("view_count = Column(String, default=\"0\")  # stored as string for SQLite compat", "view_count = Column(Integer, default=0)")

    if "deleted_at" not in content:
        content = content.replace("created_at = Column(DateTime, default=datetime.utcnow, nullable=False)",
                                  "deleted_at = Column(DateTime(timezone=True), nullable=True)\n    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)")
    return content

def patch_billing(content):
    content = content.replace("event_id = Column(String, primary_key=True, index=True)", "event_id = Column(String, primary_key=True)")
    if "JSON_TYPE" not in content:
        content = content.replace("from suspensionlab.backend.database.core import Base", "from sqlalchemy.dialects.postgresql import JSONB\nfrom suspensionlab.backend.database.core import Base\n\nJSON_TYPE = JSON().with_variant(JSONB, 'postgresql')")
        content = content.replace("payload = Column(JSON)", "payload = Column(JSON_TYPE)")
    return content

def main():
    base = "d:/project/src/suspensionlab/backend/database/models"
    patch_file(os.path.join(base, "user.py"), patch_user)
    patch_file(os.path.join(base, "team.py"), patch_team)
    patch_file(os.path.join(base, "job.py"), patch_job)
    patch_file(os.path.join(base, "profile.py"), patch_profile)
    patch_file(os.path.join(base, "session.py"), patch_session)
    patch_file(os.path.join(base, "user_session.py"), patch_user_session)
    patch_file(os.path.join(base, "shared_report.py"), patch_shared_report)
    patch_file(os.path.join(base, "billing.py"), patch_billing)

if __name__ == "__main__":
    main()
