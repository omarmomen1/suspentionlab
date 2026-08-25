"use client";
import { useEffect, useState } from "react";
import { Search } from "lucide-react";

export default function GlobalSearchTrigger() {
  const [key, setKey] = useState("?K");

  useEffect(() => {
    setTimeout(() => {
      if (navigator.platform.toLowerCase().includes("win")) {
        setKey("Ctrl K");
      } else {
        setKey("?K");
      }
    }, 0);
  }, []);

  // WCAG 4.1.2: interactive element must be a real <button>, keyboard operable
  return (
    <button
      type="button"
      aria-label={`Open global search (${key})`}
      className="flex items-center space-x-1 hover:text-white cursor-pointer transition-colors"
      onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))}
    >
      <Search size={14} />
      <span className="hidden md:inline-flex items-center justify-center rounded border border-gray-700 bg-[rgba(255,255,255,0.05)] px-1.5 py-0.5 font-mono text-[10px] text-gray-400 cursor-pointer hover:text-white transition-colors">
        {key}
      </span>
    </button>
  );
}
