import os
import glob

def patch_datetime():
    model_files = glob.glob("d:/project/src/suspensionlab/backend/database/models/*.py")
    
    for filepath in model_files:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'func' not in content and 'datetime.utcnow' in content:
            content = "from sqlalchemy.sql import func\n" + content
            
        content = content.replace('default=datetime.utcnow, onupdate=datetime.utcnow', 'server_default=func.now(), onupdate=func.now()')
        content = content.replace('default=datetime.utcnow', 'server_default=func.now()')
        content = content.replace('DateTime', 'DateTime(timezone=True)')
        
        # fix duplicate timezone declarations if any
        content = content.replace('DateTime(timezone=True)(timezone=True)', 'DateTime(timezone=True)')

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

if __name__ == "__main__":
    patch_datetime()
