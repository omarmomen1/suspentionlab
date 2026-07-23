import os
import shutil

def main():
    staging_dir = '_zip_staging'
    out_zip = 'C:/Users/omaar/Downloads/SuspensionLab_v1'
    
    # Ensure clean staging directory
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)
    os.makedirs(staging_dir)
    
    # Specific items to package for audit
    includes = [
        'src',
        'benchmark_mc.py',
        'validate_rk4.py',
        'requirements.txt',
        'project_summary.md',
        'README.md'
    ]
    
    for item in includes:
        if os.path.exists(item):
            if os.path.isdir(item):
                shutil.copytree(item, os.path.join(staging_dir, item))
            else:
                shutil.copy2(item, staging_dir)
                
    # Create the zip archive
    shutil.make_archive(out_zip, 'zip', staging_dir)
    print(f"Successfully packaged project to {out_zip}.zip")
    
    # Cleanup staging area
    shutil.rmtree(staging_dir)

if __name__ == '__main__':
    main()
