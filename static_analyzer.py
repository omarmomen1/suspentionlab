import ast
import os
import sys

def analyze_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
        
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        print(f"[{filepath}] SYNTAX ERROR: {e}")
        return False
        
    # Check for unhandled top-level function exceptions in FastAPI routes
    if "api/routes" in filepath:
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                # Is there a try/except block?
                has_try = any(isinstance(n, ast.Try) for n in node.body)
                if not has_try:
                    print(f"[{filepath}] WARNING: Route {node.name} lacks top-level try/except block.")
                    
    # Check for bare excepts
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                if handler.type is None:
                    print(f"[{filepath}] WARNING: Bare 'except:' clause found line {handler.lineno}.")
                    
    # Check for print statements (should use logging in backend)
    if "backend" in filepath:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "print":
                    print(f"[{filepath}] WARNING: 'print' used instead of logger on line {node.lineno}.")
                    
    return True

def main():
    root_dir = "src"
    all_good = True
    for dirpath, _, filenames in os.walk(root_dir):
        for file in filenames:
            if file.endswith(".py"):
                path = os.path.join(dirpath, file)
                if not analyze_file(path):
                    all_good = False
                    
    ui_dir = "ui"
    for dirpath, _, filenames in os.walk(ui_dir):
        for file in filenames:
            if file.endswith(".py"):
                path = os.path.join(dirpath, file)
                if not analyze_file(path):
                    all_good = False
                    
    if all_good:
        print("STATIC ANALYSIS COMPLETE: 0 ERRORS FOUND.")
    else:
        print("STATIC ANALYSIS COMPLETE: ERRORS DETECTED.")
        
if __name__ == "__main__":
    main()
