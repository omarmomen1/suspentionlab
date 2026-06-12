import sys

with open('frontend2/app/full-car/page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Add import for CAEExport if missing
if 'import CAEExport' not in content:
    idx = content.find('import PlanGate')
    content = content[:idx] + 'import CAEExport from "../../components/CAEExport";\n' + content[idx:]

# Find the messed up toolbar section
start_marker = '<div className="flex items-center justify-between shrink-0 pb-3 border-b border-[#1e1e1e]">'
start_idx = content.find(start_marker)

# Find the start of the next main div after toolbar
end_marker = '<div className="flex flex-1 gap-4 overflow-hidden min-h-0">'
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    correct_toolbar = '''<div className="flex items-center justify-between shrink-0 pb-3 border-b border-[#1e1e1e]">
        <div className="flex flex-col">
          <span className="text-[9px] font-bold tracking-[0.25em] text-ansys-yellow uppercase">7-DOF Pitch, Roll, Heave</span>
          <h1 className="text-2xl font-semibold tracking-tight text-white leading-tight">Full Car</h1>
        </div>

        <div className="flex items-center gap-2">
          <SimHistory onRestore={(p) => { setParams(prev => ({ ...prev, ...p })); showToast("Restored from history", "success"); }} />
          <button onClick={saveProfile} disabled={isSaving} className="px-3 py-1.5 bg-[#141416] border border-[#252525] hover:bg-[#1e1e20] rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-40">
            <Save size={13} className="text-ansys-yellow" /> Save Setup
          </button>
          <CAEExport params={params} vehicleType="FULL_CAR" />
          <PDFExport captureId="sim-report" fileName={`FCar_${params.m_s}`} />
          <DataExport results={results} fileName={`FCar_${params.m_s}`} />

          <button id="btn-run" onClick={runSimulation} disabled={isRunning}
            className={`px-5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${isRunning ? "bg-[#222] text-gray-500 cursor-not-allowed" : "bg-ansys-yellow text-black hover:brightness-110 shadow-[0_0_20px_rgba(242,169,0,0.2)]"}`}>
            {isRunning ? <><div className="w-3 h-3 border border-gray-600 border-t-gray-300 rounded-full animate-spin" />Solving…</> : <><Play size={13} fill="currentColor" /> Run Solver</>}
          </button>
        </div>
      </div>

      '''
    content = content[:start_idx] + correct_toolbar + content[end_idx:]

with open('frontend2/app/full-car/page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
