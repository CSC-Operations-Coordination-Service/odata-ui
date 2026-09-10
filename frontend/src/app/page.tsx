"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { EmptyState, ErrorBox, Spinner, StatusDot } from "@/components/ui";

export default function DashboardPage() {
  const endpoints = useQuery({ queryKey: ["endpoints"], queryFn: api.listEndpoints });
  const queries = useQuery({ queryKey: ["queries"], queryFn: () => api.listQueries() });
  const history = useQuery({ queryKey: ["history"], queryFn: () => api.listHistory(8) });

  if (endpoints.isLoading) return <Spinner />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">OData Explorer</h1>
        <p className="text-sm" style={{ color: "var(--muted)" }}>
          Query your configured OData interfaces without hand-crafting URLs or fetching
          tokens.
        </p>
      </div>

      <ErrorBox error={endpoints.error} />

      {endpoints.data?.length === 0 ? (
        <EmptyState
          title="Start by registering an endpoint"
          hint="Give the app a base URL and its credentials once; after that you can query it from the browser."
          action={
            <Link href="/endpoints/new" className="btn btn-primary mt-2">
              New endpoint
            </Link>
          }
        />
      ) : (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
              Endpoints
            </h2>
            <Link href="/endpoints" className="text-xs hover:underline" style={{ color: "var(--accent)" }}>
              Manage →
            </Link>
          </div>
          <div className="stagger grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {endpoints.data?.map((endpoint) => (
              <Link
                key={endpoint.id}
                href={`/query?endpoint=${endpoint.id}`}
                className="card card-interactive rise-in block p-4"
              >
                <div className="flex items-center gap-2">
                  <StatusDot endpoint={endpoint} />
                  <span className="text-sm font-medium">{endpoint.name}</span>
                  <span className="badge ml-auto">{endpoint.odata_version}</span>
                </div>
                <p className="mono mt-2 truncate text-xs" style={{ color: "var(--muted)" }}>
                  {endpoint.base_url}
                </p>
              </Link>
            ))}
          </div>
        </section>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
              Templates
            </h2>
            <Link href="/queries" className="text-xs hover:underline" style={{ color: "var(--accent)" }}>
              All →
            </Link>
          </div>
          <div className="card divide-y" style={{ borderColor: "var(--border)" }}>
            {queries.data?.slice(0, 6).map((template) => (
              <div
                key={template.id}
                className="row-hover flex items-center gap-2 px-3 py-2 text-sm"
              >
                <span className="truncate">{template.name}</span>
                {template.is_builtin && <span className="badge ml-auto shrink-0">built-in</span>}
              </div>
            ))}
          </div>
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
              Recent runs
            </h2>
            <Link href="/history" className="text-xs hover:underline" style={{ color: "var(--accent)" }}>
              All →
            </Link>
          </div>
          <div className="card divide-y" style={{ borderColor: "var(--border)" }}>
            {history.data?.length === 0 && (
              <p className="px-3 py-4 text-sm" style={{ color: "var(--muted)" }}>
                No queries run yet.
              </p>
            )}
            {history.data?.map((run) => (
              <div
                key={run.id}
                className="row-hover flex items-center gap-2 px-3 py-2 text-xs"
              >
                <span
                  style={{
                    color: run.error || (run.status_code ?? 0) >= 400 ? "#d1242f" : "#1a7f37",
                  }}
                >
                  {run.status_code ?? "err"}
                </span>
                <span className="mono flex-1 truncate" style={{ color: "var(--muted)" }} title={run.url}>
                  {run.url}
                </span>
                <span className="shrink-0">{run.result_count ?? "—"} rows</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
