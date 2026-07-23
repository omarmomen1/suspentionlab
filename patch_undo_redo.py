import os
import re

dashboards = [
    "frontend/app/full-car/page.tsx",
    "frontend/app/half-car/page.tsx",
    "frontend/app/active/page.tsx",
    "frontend/app/durability/page.tsx",
    "frontend/app/handling/page.tsx",
    "frontend/app/kinematics/page.tsx",
    "frontend/app/nvh/page.tsx",
    "frontend/app/sensitivity/page.tsx"
]

base_dir = r"d:\project"

lucide_pattern = re.compile(r'import\s+\{([^}]+)\}\s+from\s+"lucide-react";', re.MULTILINE)
useState_pattern = re.compile(r'const\s+\[params,\s*setParams\]\s*=\s*useState\(\{')
toolbar_pattern = re.compile(r'(<SimHistory[^>]*/>|(<button[^>]*>\s*<Save[^>]*/>[^<]*</button>))', re.IGNORECASE)

undo_ui_snippet = """          {/* Undo/Redo/Reset Controls */}
          <div className="flex items-center bg-[#141416] border border-[#252525] rounded-lg overflow-hidden mr-2">
            <button onClick={undo} disabled={!canUndo} title="Undo (Ctrl+Z)"
              className="px-2.5 py-1.5 hover:bg-[#1e1e20] text-gray-400 disabled:opacity-30 disabled:hover:bg-transparent transition-colors">
              <Undo2 size={14} />
            </button>
            <button onClick={redo} disabled={!canRedo} title="Redo (Ctrl+Y)"
              className="px-2.5 py-1.5 hover:bg-[#1e1e20] text-gray-400 border-l border-[#252525] disabled:opacity-30 disabled:hover:bg-transparent transition-colors">
              <Redo2 size={14} />
            </button>
            <button onClick={reset} title="Reset to Defaults"
              className="px-2.5 py-1.5 hover:bg-[#1e1e20] text-red-400/80 hover:text-red-400 border-l border-[#252525] transition-colors">
              <RotateCcw size={14} />
            </button>
          </div>\n"""

for dash in dashboards:
    file_path = os.path.join(base_dir, dash)
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        continue
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update lucide-react imports
    match = lucide_pattern.search(content)
    if match:
        imports = match.group(1)
        if "Undo2" not in imports:
            new_imports = imports.strip() + ", Undo2, Redo2, RotateCcw"
            new_import_stmt = f'import {{\n  {new_imports}\n}} from "lucide-react";'
            content = content[:match.start()] + new_import_stmt + content[match.end():]
    
    # 2. Add useUndoRedo import
    if "useUndoRedo" not in content:
        # insert after the lucide-react import
        match = lucide_pattern.search(content) # search again since we modified it
        if match:
            # We assume hook is at "../../hooks/useUndoRedo" based on quarter-car
            content = content[:match.end()] + '\nimport { useUndoRedo } from "../../hooks/useUndoRedo";' + content[match.end():]

    # 3. Replace useState with useUndoRedo
    if "const [params, setParams, { undo, redo, reset, canUndo, canRedo }] = useUndoRedo({" not in content:
        content = useState_pattern.sub(r'const [params, setParams, { undo, redo, reset, canUndo, canRedo }] = useUndoRedo({', content)
    
    # 4. Inject Toolbar controls
    if "Undo/Redo/Reset Controls" not in content:
        # Find SimHistory or Save button to insert before
        match = toolbar_pattern.search(content)
        if match:
            # insert before the matched element
            content = content[:match.start()] + undo_ui_snippet + content[match.start():]

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"Patched {dash}")
