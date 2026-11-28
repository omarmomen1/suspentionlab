"use client";

import React, { useState } from "react";
import { HelpCircle, Info } from "lucide-react";
import ProvenancePopover, { ProvenanceData } from "./ProvenancePopover";

interface WhyButtonProps {
  title: string;
  provenance?: ProvenanceData | null;
  size?: "xs" | "sm" | "md";
  variant?: "ghost" | "badge" | "outline";
  className?: string;
}

export default function WhyButton({
  title,
  provenance,
  size = "xs",
  variant = "badge",
  className = "",
}: WhyButtonProps) {
  const [isOpen, setIsOpen] = useState(false);

  const sizeClasses = {
    xs: "px-1.5 py-0.5 text-xs gap-1",
    sm: "px-2 py-1 text-xs gap-1",
    md: "px-2.5 py-1.5 text-xs gap-1.5",
  }[size];

  const variantClasses = {
    badge: "bg-white/10 hover:bg-white/20 text-gray-300 hover:text-white border border-white/15",
    outline: "bg-transparent hover:bg-white/5 text-gray-400 hover:text-signal border border-white/10 hover:border-signal/40",
    ghost: "bg-transparent hover:bg-white/10 text-gray-400 hover:text-white",
  }[variant];

  return (
    <>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen(true);
        }}
        className={`inline-flex items-center rounded-md font-mono font-bold uppercase transition-all shrink-0 cursor-pointer ${sizeClasses} ${variantClasses} ${className}`}
        title={`Click to inspect mathematical provenance for ${title}`}
      >
        <HelpCircle size={size === "xs" ? 10 : 12} className="text-signal" />
        <span>WHY?</span>
      </button>

      <ProvenancePopover
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        title={title}
        data={provenance}
      />
    </>
  );
}
