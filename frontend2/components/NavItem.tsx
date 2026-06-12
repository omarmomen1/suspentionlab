"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItemProps {
  href: string;
  label: string;
}

/**
 * Client component so we can use usePathname() for active route highlighting.
 * The parent layout stays a server component — only this leaf is a client component.
 */
export default function NavItem({ href, label }: NavItemProps) {
  const pathname = usePathname();
  // Highlight exact match OR any sub-path (e.g. /quarter-car/settings)
  const isActive = pathname === href || pathname.startsWith(href + "/");

  return (
    <Link
      href={href}
      className={`relative text-xs font-normal tracking-wide transition-colors duration-200 group ${
        isActive ? "text-white" : "text-gray-500 hover:text-gray-200"
      }`}
    >
      {label}
      {/* Active indicator line */}
      <span
        className={`absolute -bottom-1 left-0 h-px w-full bg-ansys-yellow transition-all duration-200 ${
          isActive ? "opacity-100" : "opacity-0 group-hover:opacity-30"
        }`}
      />
    </Link>
  );
}
