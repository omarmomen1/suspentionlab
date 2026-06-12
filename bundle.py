import os

# Configuration
PROJECT_DIR = r"C:\Users\omaar\Downloads\project"
OUTPUT_FILE = os.path.join(PROJECT_DIR, "claude_audit_bundle.txt")

IGNORED_DIRS = {'.git', 'node_modules', '__pycache__', '.next', 'dist', 'build', '.venv', 'venv'}
ALLOWED_EXTENSIONS = {'.py', '.tsx', '.ts', '.css', '.json', '.md', '.toml'}

with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
    outfile.write("================================================================================\n")
    outfile.write("PROJECT STRUCTURE AND SOURCE CODE BUNDLE\n")
    outfile.write("================================================================================\n\n")
    
    for root, dirs, files in os.walk(PROJECT_DIR):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            # Special case for Dockerfile etc if needed, but we focus on extensions
            if ext in ALLOWED_EXTENSIONS or file == 'Dockerfile':
                path = os.path.join(root, file)
                rel_path = os.path.relpath(path, PROJECT_DIR)
                
                # Skip package-lock.json to avoid massive unhelpful files
                if "package-lock.json" in file:
                    continue
                    
                try:
                    with open(path, 'r', encoding='utf-8') as infile:
                        content = infile.read()
                        outfile.write(f"\n\n{'='*80}\n")
                        outfile.write(f"FILE: {rel_path}\n")
                        outfile.write(f"{'='*80}\n\n")
                        outfile.write(content)
                        outfile.write("\n")
                except Exception as e:
                    pass

print(f"Bundle generated successfully at: {OUTPUT_FILE}")
