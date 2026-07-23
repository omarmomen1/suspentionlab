import os
import glob
import re

def fix_imports():
    model_files = glob.glob("d:/project/src/suspensionlab/backend/database/models/*.py")
    
    for filepath in model_files:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # fix the import
        content = content.replace('DateTime(timezone=True)', 'DateTime')
        
        # apply correctly only to columns
        content = re.sub(r'Column\(DateTime(?:,)?', 'Column(DateTime(timezone=True),', content)
        content = re.sub(r'Column\(DateTime\)', 'Column(DateTime(timezone=True))', content)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

if __name__ == "__main__":
    fix_imports()
