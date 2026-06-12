import sys
import re

file_path = r'c:\Users\omaar\Downloads\project\frontend\app\quarter-car\page.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Import
content = content.replace(
    'import { useAuth } from "../../contexts/AuthContext";\n\nconst Plot',
    'import { useAuth } from "../../contexts/AuthContext";\nimport SuspensionRig3D from "../../components/SuspensionRig3D";\n\nconst Plot'
)

# 2. State
state_target = '  const [results,   setResults]   = useState<Record<string, unknown> | null>(null);\n  const [activeTab, setActiveTab] = useState(0);\n  const [toast,     setToast]     = useState<Toast | null>(null);'
state_replace = '''  const [results,   setResults]   = useState<Record<string, unknown> | null>(null);
  const [activeTab, setActiveTab] = useState(0);
  const [toast,     setToast]     = useState<Toast | null>(null);
  
  const [frameIndex, setFrameIndex] = useState(0);
  
  useEffect(() => {
    if (!results || results.error) return;
    const times = results.time as number[];
    if (!times) return;
    let interval: NodeJS.Timeout;
    const animate = () => {
      setFrameIndex(prev => (prev + 1) % times.length);
    };
    interval = setInterval(animate, 20); // 50fps
    return () => clearInterval(interval);
  }, [results]);'''
content = content.replace(state_target, state_replace)

# 3. PSD
psd_pattern = r'  // ————————————————— Derived: PSD from acceleration time series \(Welch-style via FFT\) —————.*?  }, \[results\]\);'
psd_replace = '''  // ————————————————— Derived: PSD from acceleration time series (Welch-style via FFT) —————
  const psdData = useMemo(() => {
    if (!results || results.error) return null;
    if (!results.psd_freqs || !results.psd_values) return null;
    return {
      freqs: results.psd_freqs as number[],
      psd: results.psd_values as number[]
    };
  }, [results]);'''
content = re.sub(psd_pattern, psd_replace, content, flags=re.DOTALL)

# 4. Rig
rig_target = '''              </div>
            </div>
          )}'''
rig_replace = '''              </div>
            </div>
          )}

          {/* 3D Viewport Split */}
          {hasResults && r && (
            <div className="h-64 shrink-0 bg-[#0d0d0f] border border-[#1e1e1e] rounded-xl overflow-hidden relative">
               <div className="absolute top-2 left-3 z-10 text-[10px] font-mono text-gray-500 uppercase tracking-widest">
                 Live Telemetry
               </div>
               <SuspensionRig3D zs={r.z_s[frameIndex] ?? 0} zu_fl={r.z_u[frameIndex] ?? 0} zu_fr={r.z_u[frameIndex] ?? 0} zu_rl={r.z_u[frameIndex] ?? 0} zu_rr={r.z_u[frameIndex] ?? 0} />
            </div>
          )}'''
content = content.replace(rig_target, rig_replace)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done!')
