import type { Metadata } from "next";
import "./globals.css";
import { Inter } from "next/font/google";
import Link from "next/link";
import { Suspense } from "react";
import NavItem from "../components/NavItem";
import GlobalSearchTrigger from "../components/GlobalSearchTrigger";
import { AuthProvider } from "../contexts/AuthContext";
import UserMenu from "../components/UserMenu";
import CommandPalette from "../components/CommandPalette";
import MobileNav from "../components/MobileNav";
import PromptModalHost from "../components/sim/ModalHost";
import NavigationProgressBar from "../components/NavigationProgressBar";

const inter = Inter({ subsets: ["latin"] });

import Navbar from "../components/Navbar";

export const metadata: Metadata = {
  title:       "SuspensionLab Pro | Engineering Simulation",
  description: "Enterprise-grade vehicle dynamics simulation environment.",
};

import { WorkspaceProvider } from "../contexts/WorkspaceContext";
import WorkspaceStatusBar from "../components/WorkspaceStatusBar";

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body suppressHydrationWarning className={`${inter.className} bg-black text-gray-100 antialiased selection:bg-ansys-yellow selection:text-black flex flex-col h-screen overflow-hidden`}>
          <AuthProvider>
            <WorkspaceProvider>
              {/* WCAG 2.4.1 Bypass Blocks: Skip to main content link */}
              <a
                href="#main-content"
                className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:px-4 focus:py-2 focus:bg-ansys-yellow focus:text-black focus:font-bold focus:rounded-lg focus:shadow-xl focus:ring-2 focus:ring-white"
              >
                Skip to main content
              </a>
              <Suspense fallback={null}>
                <NavigationProgressBar />
              </Suspense>
              <CommandPalette />
              <PromptModalHost />
              <header role="banner" className="shrink-0">
                <Navbar />
                <aside aria-label="Workspace Status Bar" className="pt-[52px]">
                  <WorkspaceStatusBar />
                </aside>
              </header>

              {/* Main Content Area */}
              <main
                id="main-content"
                tabIndex={-1}
                className="flex-1 overflow-y-auto bg-black custom-scrollbar relative focus:outline-none"
              >
                <div className="relative z-10 w-full min-h-full">
                  {children}
                </div>
              </main>
              <footer role="contentinfo" aria-label="Site Footer" className="border-t border-[#1a1a1a] py-4 px-6 flex flex-wrap items-center justify-center gap-4 text-[11px] text-gray-400 shrink-0">
                <span>© {new Date().getFullYear()} SuspensionLab. All rights reserved.</span>
                <Link href="/legal/terms" className="hover:text-gray-300 transition-colors">Terms of Service</Link>
                <Link href="/legal/privacy" className="hover:text-gray-300 transition-colors">Privacy Policy</Link>
                <a href="/contact" className="hover:text-gray-300 transition-colors">Contact</a>
              </footer>
            </WorkspaceProvider>
          </AuthProvider>
      </body>
    </html>
  );
}
