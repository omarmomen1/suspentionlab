import os

def create_bundle(output_file="suspensionlab_bundle.txt"):
    exclude_dirs = {
        "node_modules", ".next", "venv", ".git", "__pycache__",
        "data", "alembic/versions" # Exclude large data and raw migrations if needed, but let's keep migrations
    }
    exclude_exts = {
        ".pyc", ".ico", ".png", ".jpg", ".jpeg", ".db", ".sqlite", ".db3", ".sqlite3"
    }
    
    # We want to specifically grab src, frontend, tests, alembic, Dockerfiles, tomls, etc.
    target_dirs = ["src", "frontend/app", "frontend/components", "frontend/contexts", "frontend/lib", "alembic"]
    root_files = [
        "pyproject.toml", "package.json", "frontend/package.json",
        "Dockerfile.backend", "Dockerfile.frontend", "docker-compose.yml",
        "railway.toml", ".env.railway.example", "README.md", "alembic.ini"
    ]
    
    with open(output_file, "w", encoding="utf-8") as outfile:
        outfile.write("=================================================================\n")
        outfile.write("SuspensionLab Pro - Full Codebase Bundle\n")
        outfile.write("=================================================================\n\n")
        
        # Write root files
        for fpath in root_files:
            if os.path.exists(fpath):
                outfile.write(f"\n\n--- FILE: {fpath} ---\n")
                try:
                    with open(fpath, "r", encoding="utf-8") as infile:
                        outfile.write(infile.read())
                except Exception as e:
                    outfile.write(f"[Error reading file: {e}]\n")
                    
        # Write directory files
        for d in target_dirs:
            if not os.path.exists(d): continue
            for root, dirs, files in os.walk(d):
                dirs[:] = [dir for dir in dirs if dir not in exclude_dirs]
                for file in files:
                    if any(file.endswith(ext) for ext in exclude_exts):
                        continue
                    fpath = os.path.join(root, file)
                    outfile.write(f"\n\n--- FILE: {fpath.replace(os.sep, '/')} ---\n")
                    try:
                        with open(fpath, "r", encoding="utf-8") as infile:
                            outfile.write(infile.read())
                    except Exception as e:
                        outfile.write(f"[Error reading file: {e}]\n")

if __name__ == "__main__":
    create_bundle()
    print("Bundle created successfully at suspensionlab_bundle.txt")
