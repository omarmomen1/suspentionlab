import os
import zipfile
from pathlib import Path

def create_audit_zip(source_dir, output_path):
    print(f"Creating zip file at {output_path}...")
    
    exclude_dirs = {
        '.git', 
        'node_modules', 
        'build', 
        '.pytest_cache', 
        '__pycache__', 
        '.agents',
        'wheelhouse',
        '.next'
    }
    exclude_extensions = {'.zip', '.pyd', '.whl', '.so', '.dll'}
    
    source_path = Path(source_dir)
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.next')]
            
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix in exclude_extensions:
                    continue
                rel_path = file_path.relative_to(source_path)
                zipf.write(file_path, rel_path)
                
    print(f"Successfully created {output_path}")

if __name__ == "__main__":
    source = r"d:\project"
    dest = r"C:\Users\omaar\Downloads\suspensionlab_audit.zip"
    create_audit_zip(source, dest)
