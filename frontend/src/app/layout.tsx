import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { NavLinks } from "@/components/NavLinks";
import { SpaceBackdrop } from "@/components/SpaceBackdrop";
import { PageTransition } from "@/components/PageTransition";

export const metadata: Metadata = {
  title: "OData Explorer",
  description: "Query configured OData interfaces from the browser.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SpaceBackdrop />
        <Providers>
          <div className="min-h-screen">
            <header
              className="sticky top-0 z-20 border-b backdrop-blur-md"
              style={{
                borderColor: "var(--border)",
                background: "color-mix(in srgb, var(--bg) 78%, transparent)",
              }}
            >
              <div className="mx-auto flex max-w-[1600px] items-center gap-6 px-5 py-3">
                <Link
                  href="/"
                  className="group flex items-center gap-2 text-sm font-semibold tracking-tight"
                >
                  <IsoMark />
                  OData Explorer
                </Link>
                <NavLinks />
              </div>
            </header>
            <main className="mx-auto max-w-[1600px] px-5 py-6">
              <PageTransition>{children}</PageTransition>
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}

/** A small isometric cube, echoing the backdrop, that lifts on hover. */
function IsoMark() {
  return (
    <svg
      width="18"
      height="20"
      viewBox="-16 -2 32 36"
      aria-hidden="true"
      className="transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:rotate-6"
      style={{ transformOrigin: "center" }}
    >
      <path d="M-14,8 L0,16 L0,30 L-14,22 Z" fill="var(--accent)" fillOpacity="0.45" />
      <path d="M14,8 L0,16 L0,30 L14,22 Z" fill="var(--accent)" fillOpacity="0.25" />
      <path d="M0,0 L14,8 L0,16 L-14,8 Z" fill="var(--accent)" fillOpacity="0.85" />
    </svg>
  );
}
