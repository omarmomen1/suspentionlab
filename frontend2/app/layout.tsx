import type { Metadata } from "next";
import "./globals.css";
import { Inter } from "next/font/google";
import Link from "next/link";
import { Search } from "lucide-react";
import NavItem from "../components/NavItem";
import { AuthProvider } from "../contexts/AuthContext";
import UserMenu from "../components/UserMenu";
import { ErrorBoundary } from "../components/ErrorBoundary";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title:       "SuspensionLab Pro | Engineering Simulation",
  description: "Enterprise-grade vehicle dynamics simulation environment.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body suppressHydrationWarning className={`${inter.className} bg-black text-gray-100 antialiased selection:bg-ansys-yellow selection:text-black flex flex-col h-screen overflow-hidden`}>
        <AuthProvider>
          {/* Apple-Style Top Navigation Bar */}
          <nav className="w-full h-[44px] bg-[rgba(13,13,15,0.92)] backdrop-blur-md border-b border-white/8 flex items-center justify-center fixed top-0 z-50">
            <div className="max-w-[1200px] w-full px-5 flex items-center justify-between">
              {/* Logo */}
              <Link href="/" className="text-gray-300 hover:text-white transition-colors flex items-center gap-2">
                <svg viewBox="0 0 24 24" fill="none" height="16" width="16">
                  <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                    stroke="#f2a900" strokeWidth="2" strokeLinejoin="round" />
                </svg>
                <span className="text-[11px] font-bold text-white tracking-tight hidden sm:block">
                  Suspension<span className="text-ansys-yellow">Lab</span>
                </span>
              </Link>

              {/* Nav links */}
              <div className="hidden md:flex items-center space-x-7">
                <NavItem href="/quarter-car" label="Quarter Car" />
                <NavItem href="/half-car"    label="Half Car"    />
                <NavItem href="/full-car"    label="Full Car"    />
                <NavItem href="/active"      label="Active"      />
                <NavItem href="/handling"    label="Handling"    />
                <NavItem href="/digital-twin" label="Digital Twin" />
                <NavItem href="/sensitivity" label="Sensitivity" />
                <NavItem href="/nvh"         label="NVH"         />
                <NavItem href="/garage"      label="Garage"      />
                <NavItem href="/pricing"     label="Pricing"     />
                <NavItem href="/docs"        label="Docs"        />
              </div>

              {/* Right side — user menu */}
              <div className="flex items-center space-x-4 text-gray-400">
                <Search size={14} className="hover:text-white cursor-pointer transition-colors" />
                <UserMenu />
              </div>
            </div>
          </nav>

          {/* Main Content Area */}
          <main className="flex-1 overflow-y-auto bg-black pt-[44px] custom-scrollbar relative">
            <div className="relative z-10 w-full h-full">
              <ErrorBoundary>
                {children}
              </ErrorBoundary>
            </div>
          </main>
        </AuthProvider>
      </body>
    </html>
  );
}
