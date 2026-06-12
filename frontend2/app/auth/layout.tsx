import type { Metadata } from "next";
import "../globals.css";

export const metadata: Metadata = {
  title: "Sign In — SuspensionLab Pro",
};

/** Auth pages get a full-screen centered layout with no nav bar. */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-black flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-3">
            <svg viewBox="0 0 24 24" fill="none" height="20" width="20" className="text-ansys-yellow">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
            </svg>
            <span className="text-white font-bold text-lg tracking-tight">SuspensionLab</span>
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}
