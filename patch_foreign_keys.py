import os

def patch_user():
    filepath = "d:/project/src/suspensionlab/backend/database/models/user.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = content.replace(
        'team = relationship("Team", back_populates="members")',
        'team = relationship("Team", back_populates="members", foreign_keys="[User.team_id]")'
    )
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def patch_team():
    filepath = "d:/project/src/suspensionlab/backend/database/models/team.py"
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = content.replace(
        'members = relationship("User", back_populates="team")',
        'members = relationship("User", back_populates="team", foreign_keys="[User.team_id]")'
    )
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    patch_user()
    patch_team()
