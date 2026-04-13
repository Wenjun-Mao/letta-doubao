"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/agent-studio", label: "Agent Studio" },
  { href: "/test-center", label: "Test Center" },
  { href: "/api-docs", label: "API Docs" },
];

function isActivePath(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function TopNav() {
  const pathname = usePathname() || "/";

  return (
    <nav className="nav" aria-label="ADE navigation">
      {NAV_ITEMS.map((item) => {
        const active = isActivePath(pathname, item.href);
        return (
          <Link className={active ? "nav-link nav-link-active" : "nav-link"} key={item.href} href={item.href}>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}