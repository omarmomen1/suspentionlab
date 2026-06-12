import sys

def add_share_session(filepath, vehicle_type):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Add imports
    imports = f'import ShareSession from "../../components/ShareSession";\nimport {{ useCollaboration }} from "../../hooks/useCollaboration";\n'
    if 'import ShareSession' not in content:
        idx = content.find('import PlanGate')
        content = content[:idx] + imports + content[idx:]

    # Add hook inside the component
    if 'useCollaboration(' not in content:
        comp_marker = 'const searchParams = useSearchParams();'
        idx = content.find(comp_marker)
        if idx != -1:
            hook_str = f'''const searchParams = useSearchParams();
  const sessionId = searchParams.get("session");
  '''
            content = content[:idx] + hook_str + content[idx + len(comp_marker):]

        state_marker = 'const [params, setParams] = useState({'
        idx = content.find(state_marker)
        if idx != -1:
            end_state = content.find('});', idx) + 3
            hook_call = f'''\n  const {{ isConnected, activeUsers }} = useCollaboration(sessionId, params, setParams);\n'''
            content = content[:end_state] + hook_call + content[end_state:]

    # Add ShareSession button in the toolbar before PDFExport
    btn_str = f'<ShareSession currentParams={{params}} vehicleType="{vehicle_type}" />\n          '
    if '<ShareSession' not in content:
        pdf_marker = '<PDFExport '
        idx = content.find(pdf_marker)
        if idx != -1:
            content = content[:idx] + btn_str + content[idx:]

    # Add connection badge
    badge_str = '''
        {isConnected && (
          <div className="fixed bottom-4 left-4 z-50 flex items-center gap-2 px-3 py-1.5 bg-[#0a1f12] border border-emerald-800/50 rounded-full text-emerald-300 text-xs font-medium shadow-lg">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
            Live Session ({activeUsers} connected)
          </div>
        )}
'''
    if 'Live Session' not in content:
        toast_marker = '{toast && ('
        idx = content.find(toast_marker)
        if idx != -1:
            content = content[:idx] + badge_str + content[idx:]

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

add_share_session('frontend2/app/quarter-car/page.tsx', 'QUARTER_CAR')
add_share_session('frontend2/app/full-car/page.tsx', 'FULL_CAR')
