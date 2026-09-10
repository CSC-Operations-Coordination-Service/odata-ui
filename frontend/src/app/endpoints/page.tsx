"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import type { Endpoint, ImportedEndpoint } from "@/lib/types";
import { ConfirmButton, EmptyState, ErrorBox, Spinner, StatusDot } from "@/components/ui";

function ProbeCell({ endpoint }: { endpoint: Endpoint }) {
  const queryClient = useQueryClient();
  const probe = useMutation({
    mutationFn: () => api.probeEndpoint(endpoint.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["endpoints"] }),
  });

  return (
    <div className="flex items-center gap-2">
      <button
        className="btn btn-sm"
        onClick={() => probe.mutate()}
        disabled={probe.isPending}
      >
        {probe.isPending ? "Testing…" : "Test"}
      </button>
      <span className="text-xs" style={{ color: "var(--muted)" }}>
        {probe.data
          ? probe.data.ok
            ? `OK · ${probe.data.latency_ms} ms`
            : probe.data.error
          : endpoint.last_probe_at
            ? endpoint.last_probe_error
              ? endpoint.last_probe_error
              : `OK · ${endpoint.last_probe_latency_ms} ms`
            : "never tested"}
      </span>
    </div>
  );
}

function ImportPanel({ onDone }: { onDone: () => void }) {
  const [content, setContent] = useState("");
  const [overwrite, setOverwrite] = useState(false);
  const [result, setResult] = useState<ImportedEndpoint[] | null>(null);

  const doImport = useMutation({
    mutationFn: () => api.importEndpoints(content, overwrite),
    onSuccess: (data) => {
      setResult(data.imported);
      onDone();
    },
  });

  return (
    <div className="card scale-in space-y-3 p-4">
      <div>
        <h2 className="text-sm font-semibold">Import from a maas-collector credential file</h2>
        <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
          Paste a JSON document with an <span className="mono">interfaces</span> list. The
          legacy <span className="mono">odata_product_url</span> and{" "}
          <span className="mono">odata_version</span> aliases are understood.
        </p>
      </div>
      <textarea
        className="textarea h-40 text-xs"
        value={content}
        onChange={(event) => setContent(event.target.value)}
        placeholder='{"interfaces": [{"name": "prip", "odata_product_url": "https://…", "auth_method": "OAuth", …}]}'
      />
      <div className="flex items-center gap-3">
        <button
          className="btn btn-primary"
          disabled={!content.trim() || doImport.isPending}
          onClick={() => doImport.mutate()}
        >
          {doImport.isPending ? "Importing…" : "Import"}
        </button>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={overwrite}
            onChange={(event) => setOverwrite(event.target.checked)}
          />
          Overwrite existing names
        </label>
      </div>
      <ErrorBox error={doImport.error} />
      {result && (
        <ul className="space-y-1 text-xs">
          {result.map((item) => (
            <li key={item.name} className="flex gap-2">
              <span className="mono">{item.name}</span>
              <span style={{ color: "var(--muted)" }}>
                {item.action}
                {item.reason ? ` — ${item.reason}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function EndpointsPage() {
  const queryClient = useQueryClient();
  const [showImport, setShowImport] = useState(false);
  const endpoints = useQuery({ queryKey: ["endpoints"], queryFn: api.listEndpoints });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteEndpoint(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["endpoints"] }),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Endpoints</h1>
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            OData services this app can query.
          </p>
        </div>
        <div className="flex gap-2">
          <button className="btn" onClick={() => setShowImport((value) => !value)}>
            {showImport ? "Hide import" : "Import…"}
          </button>
          <Link href="/endpoints/new" className="btn btn-primary">
            New endpoint
          </Link>
        </div>
      </div>

      {showImport && (
        <ImportPanel
          onDone={() => queryClient.invalidateQueries({ queryKey: ["endpoints"] })}
        />
      )}

      <ErrorBox error={endpoints.error} />
      {endpoints.isLoading && <Spinner />}

      {endpoints.data?.length === 0 && (
        <EmptyState
          title="No endpoints yet"
          hint="Register an OData service to start querying it, or import a maas-collector credential file."
          action={
            <Link href="/endpoints/new" className="btn btn-primary mt-2">
              New endpoint
            </Link>
          }
        />
      )}

      <div className="stagger grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {endpoints.data?.map((endpoint) => (
          <div
            key={endpoint.id}
            className="card card-interactive rise-in flex flex-col gap-3 p-4"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <StatusDot endpoint={endpoint} />
                  <Link
                    href={`/endpoints/${endpoint.id}`}
                    className="truncate text-sm font-semibold hover:underline"
                  >
                    {endpoint.name}
                  </Link>
                </div>
                <p className="mono mt-1 truncate text-xs" style={{ color: "var(--muted)" }}>
                  {endpoint.base_url}
                  {endpoint.entity_location}
                  {endpoint.default_entity_set}
                </p>
              </div>
              <span className="badge shrink-0">{endpoint.odata_version}</span>
            </div>

            {endpoint.description && (
              <p className="text-xs" style={{ color: "var(--muted)" }}>
                {endpoint.description}
              </p>
            )}

            <div className="flex flex-wrap gap-1.5">
              <span className="badge">
                {endpoint.auth_method === "none" ? "no auth" : endpoint.auth_method}
              </span>
              {!endpoint.verify_ssl && <span className="badge">TLS unverified</span>}
              {endpoint.tags
                .split(",")
                .map((tag) => tag.trim())
                .filter(Boolean)
                .map((tag) => (
                  <span key={tag} className="badge">
                    {tag}
                  </span>
                ))}
            </div>

            <ProbeCell endpoint={endpoint} />

            <div className="mt-auto flex items-center gap-2 pt-1">
              <Link href={`/query?endpoint=${endpoint.id}`} className="btn btn-sm btn-primary">
                Query
              </Link>
              <Link href={`/endpoints/${endpoint.id}`} className="btn btn-sm">
                Edit
              </Link>
              <ConfirmButton onConfirm={() => remove.mutate(endpoint.id)}>
                Delete
              </ConfirmButton>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
