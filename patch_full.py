import sys
import re

file_path = r'c:\Users\omaar\Downloads\project\frontend\app\full-car\page.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. State
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

# 2. PSD
psd_pattern = r'  const psdRoll = useMemo\(\(\) => \{.*?  \}, \[results\]\);'
psd_replace = '''  const psdRoll = useMemo(() => {
    if (!results || results.error) return null;
    if (!results.psd_freqs || !results.psd_values) return null;
    return {
      freqs: results.psd_freqs as number[],
      psd: results.psd_values as number[]
    };
  }, [results]);'''
content = re.sub(psd_pattern, psd_replace, content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done!')
