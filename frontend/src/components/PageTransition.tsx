"use client";

import { usePathname } from "next/navigation";

/**
 * Replays the enter animation on every route change. The layout itself persists across
 * navigations, so the key is what makes the wrapper remount and the animation restart.
 */
export function PageTransition({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div key={pathname} className="page-enter">
      {children}
    </div>
  );
}
