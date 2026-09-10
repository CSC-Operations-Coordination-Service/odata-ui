"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/query", label: "Query" },
  { href: "/queries", label: "Templates" },
  { href: "/endpoints", label: "Endpoints" },
  { href: "/history", label: "History" },
];

export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1 text-sm">
      {LINKS.map((link) => {
        const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            className="relative rounded-md px-2.5 py-1"
            style={{
              background: active
                ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                : "transparent",
              color: active ? "var(--accent)" : "var(--muted)",
              transition: "background-color 0.2s var(--ease), color 0.2s var(--ease)",
            }}
            onMouseEnter={(event) => {
              if (!active) event.currentTarget.style.color = "var(--fg)";
            }}
            onMouseLeave={(event) => {
              if (!active) event.currentTarget.style.color = "var(--muted)";
            }}
          >
            {link.label}
            <span
              className="absolute inset-x-2.5 -bottom-[13px] h-[2px] rounded-full"
              style={{
                background: "var(--accent)",
                transform: active ? "scaleX(1)" : "scaleX(0)",
                opacity: active ? 1 : 0,
                transition: "transform 0.28s var(--ease-out), opacity 0.28s var(--ease)",
              }}
            />
          </Link>
        );
      })}
    </nav>
  );
}
