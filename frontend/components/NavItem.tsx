"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItemProps {
  href: string;
  label: string;
}

export default function NavItem({ href, label }: NavItemProps) {
  const pathname = usePathname();
  const isActive = pathname === href || pathname.startsWith(href + "/");

  return (
    <Link
      href={href}
      prefetch={true}
      aria-current={isActive ? "page" : undefined}
      className={`relative text-xs font-normal tracking-wide transition-all duration-150 group whitespace-nowrap px-1.5 py-0.5 rounded ${
        isActive ? "text-white font-medium" : "text-gray-400 hover:text-gray-200"
      }`}
    >
      {label}
      <span
        className={`absolute -bottom-1 left-0 h-px w-full bg-ansys-yellow transition-all duration-200 ${
          isActive ? "opacity-100 scale-x-100" : "opacity-0 scale-x-50 group-hover:opacity-40 group-hover:scale-x-100"
        }`}
      />
    </Link>
  );
}

