import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";
import { Archivo, Inter, JetBrains_Mono } from "next/font/google";
import { Suspense } from "react";
import NavItem from "../components/NavItem";
import GlobalSearchTrigger from "../components/GlobalSearchTrigger";
import { AuthProvider } from "../contexts/AuthContext";
import UserMenu from "../components/UserMenu";
import CommandPalette from "../components/CommandPalette";
import MobileNav from "../components/MobileNav";
import PromptModalHost from "../components/sim/ModalHost";
import NavigationProgressBar from "../components/NavigationProgressBar";
import Navbar from "../components/Navbar";

// V2 type system. Archivo for headings (variable width axis is not requested, so the
// standard Archivo face is the fallback for "Archivo Expanded"), Inter for UI text,
// JetBrains Mono strictly for numeric telemetry and KPI readouts.
const archivo = Archivo({ subsets: ["latin"], variable: "--font-archivo", display: "swap" });
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const jetbrainsMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains-mono", display: "swap" });

export const metadata: Metadata = {
  title:       "SuspensionLab Pro | Engineering Simulation",
  description: "Enterprise-grade vehicle dynamics simulation environment.",
};

import { WorkspaceProvider } from "../contexts/WorkspaceContext";
import WorkspaceStatusBar from "../components/WorkspaceStatusBar";

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${archivo.variable} ${inter.variable} ${jetbrainsMono.variable}`}>
      <body suppressHydrationWarning className="font-sans bg-black text-gray-100 antialiased selection:bg-ansys-yellow selection:text-black flex flex-col h-screen overflow-hidden">
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
                <a href="mailto:support@suspensionlab.io" className="hover:text-gray-300 transition-colors">Contact</a>
              </footer>
            </WorkspaceProvider>
          </AuthProvider>
      </body>
    </html>
  );
}
