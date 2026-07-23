"use client";
import { useEffect, useState } from "react";

export default function ShortcutHint() {
  const [key, setKey] = useState("⌘K");

  useEffect(() => {
    setTimeout(() => {
      if (navigator.platform.toLowerCase().includes("win")) {
        setKey("Ctrl K");
      } else {
        setKey("⌘K");
      }
    }, 0);
  }, []);

  return (
    <span 
      className="hidden md:inline-flex items-center justify-center rounded border border-gray-700 bg-[rgba(255,255,255,0.05)] px-1.5 py-0.5 font-mono text-[10px] text-gray-400 cursor-pointer hover:text-white transition-colors"
      onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))}
    >
      {key}
    </span>
  );
}
