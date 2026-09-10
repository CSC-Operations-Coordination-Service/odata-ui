"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-sm" style={{ color: "var(--muted)" }}>
      <span
        className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
        aria-hidden
      />
      {label}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="card fade-in flex flex-col items-center gap-2 px-6 py-12 text-center">
      <p className="text-sm font-medium">{title}</p>
      {hint && (
        <p className="max-w-md text-sm" style={{ color: "var(--muted)" }}>
          {hint}
        </p>
      )}
      {action}
    </div>
  );
}

/** Renders an API failure, including what the OData service itself replied. */
export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const apiError = error instanceof ApiError ? error : null;
  const message = error instanceof Error ? error.message : String(error);

  return (
    <div
      className="scale-in rounded-md border px-3 py-2.5 text-sm"
      style={{
        borderColor: "color-mix(in srgb, #d1242f 40%, var(--border))",
        background: "color-mix(in srgb, #d1242f 8%, transparent)",
      }}
    >
      <p className="font-medium" style={{ color: "#d1242f" }}>
        {message}
      </p>
      {apiError?.missing?.length ? (
        <p className="mt-1" style={{ color: "var(--muted)" }}>
          Missing parameter{apiError.missing.length > 1 ? "s" : ""}:{" "}
          {apiError.missing.join(", ")}
        </p>
      ) : null}
      {apiError?.upstreamStatus ? (
        <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
          Service replied HTTP {apiError.upstreamStatus}
        </p>
      ) : null}
      {apiError?.upstreamBody ? (
        <pre
          className="mono mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded border p-2 text-xs"
          style={{ borderColor: "var(--border)", color: "var(--muted)" }}
        >
          {apiError.upstreamBody}
        </pre>
      ) : null}
    </div>
  );
}

export function CopyButton({ value, className = "" }: { value: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1400);
    return () => clearTimeout(timer);
  }, [copied]);

  return (
    <button
      type="button"
      className={`btn btn-sm ${className}`}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
        } catch {
          /* clipboard unavailable (insecure origin) - ignore */
        }
      }}
      disabled={!value}
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export function StatusDot({ endpoint }: { endpoint: { last_probe_status: number | null; last_probe_error: string | null } }) {
  const ok = endpoint.last_probe_status !== null && endpoint.last_probe_status < 400 && !endpoint.last_probe_error;
  const untested = endpoint.last_probe_status === null && !endpoint.last_probe_error;
  const color = untested ? "var(--muted)" : ok ? "#1a7f37" : "#d1242f";
  const title = untested
    ? "Never tested"
    : ok
      ? `OK (HTTP ${endpoint.last_probe_status})`
      : endpoint.last_probe_error || `HTTP ${endpoint.last_probe_status}`;
  return (
    <span
      title={title}
      className={`inline-block h-2 w-2 shrink-0 rounded-full${ok ? " status-pulse" : ""}`}
      style={{ background: color, ["--pulse" as string]: color }}
    />
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      {children}
      {hint && (
        <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
          {hint}
        </p>
      )}
    </div>
  );
}

export function ConfirmButton({
  onConfirm,
  children,
  confirmLabel = "Sure?",
  className = "btn btn-sm btn-danger",
}: {
  onConfirm: () => void;
  children: React.ReactNode;
  confirmLabel?: string;
  className?: string;
}) {
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const timer = setTimeout(() => setArmed(false), 3000);
    return () => clearTimeout(timer);
  }, [armed]);

  return (
    <button
      type="button"
      className={className}
      onClick={() => (armed ? onConfirm() : setArmed(true))}
    >
      {armed ? confirmLabel : children}
    </button>
  );
}
