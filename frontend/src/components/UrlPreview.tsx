"use client";

import { CopyButton } from "./ui";

export function UrlPreview({ url, error }: { url: string; error?: string | null }) {
  return (
    <div
      className="card flex items-start gap-2 px-3 py-2"
      style={error ? { borderColor: "color-mix(in srgb, #d1242f 45%, var(--border))" } : undefined}
    >
      <span
        className="mono shrink-0 pt-0.5 text-xs font-semibold"
        style={{ color: "var(--muted)" }}
      >
        GET
      </span>
      <code
        className="mono flex-1 break-all text-xs leading-relaxed"
        style={{ color: error ? "#d1242f" : "var(--fg)" }}
      >
        {error || url || "…"}
      </code>
      <CopyButton value={url} />
    </div>
  );
}
