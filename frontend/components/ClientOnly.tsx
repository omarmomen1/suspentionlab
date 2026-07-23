'use client';
import { useEffect, useState } from 'react';
export default function ClientOnly({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setTimeout(() => setMounted(true), 0); }, []);
  if (!mounted) return <div className="w-full h-full min-h-[50px] animate-pulse bg-white/5 rounded-lg" />;
  return <>{children}</>;
}
