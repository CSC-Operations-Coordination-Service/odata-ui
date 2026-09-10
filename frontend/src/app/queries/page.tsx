"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { QueryResponse, SavedQuery } from "@/lib/types";
import { ParamForm } from "@/components/ParamForm";
import { ResultsView } from "@/components/ResultsView";
import { UrlPreview } from "@/components/UrlPreview";
import { ConfirmButton, EmptyState, ErrorBox, Spinner } from "@/components/ui";

function RunPanel({
  template,
  onClose,
}: {
  template: SavedQuery;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const endpoints = useQuery({ queryKey: ["endpoints"], queryFn: api.listEndpoints });
  const [endpointId, setEndpointId] = useState<number | null>(template.endpoint_id);
  const [values, setValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<QueryResponse | null>(null);

  const effectiveEndpointId =
    endpointId ?? template.endpoint_id ?? endpoints.data?.[0]?.id ?? null;

  const body = {
    endpoint_id: effectiveEndpointId,
    params: Object.fromEntries(
      Object.entries(values).filter(([, value]) => value !== ""),
    ),
  };

  const preview = useMutation({
    mutationFn: () => api.previewSavedQuery(template.id, body),
  });

  const run = useMutation({
    mutationFn: () => api.runSavedQuery(template.id, body),
    onSuccess: (data) => {
      setResult(data);
      queryClient.invalidateQueries({ queryKey: ["history"] });
    },
  });

  return (
    <div className="card scale-in space-y-4 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">{template.name}</h2>
          {template.description && (
            <p className="mt-0.5 text-xs" style={{ color: "var(--muted)" }}>
              {template.description}
            </p>
          )}
        </div>
        <button className="btn btn-sm" onClick={onClose}>
          Close
        </button>
      </div>

      {template.endpoint_id === null && (
        <div>
          <label className="label">Run against</label>
          <select
            className="select"
            value={effectiveEndpointId ?? ""}
            onChange={(event) => setEndpointId(Number(event.target.value))}
          >
            {endpoints.data?.map((endpoint) => (
              <option key={endpoint.id} value={endpoint.id}>
                {endpoint.name}
              </option>
            ))}
          </select>
        </div>
      )}

      <ParamForm params={template.params} values={values} onChange={setValues} />

      <div className="flex gap-2">
        <button
          className="btn btn-primary"
          onClick={() => run.mutate()}
          disabled={run.isPending || !effectiveEndpointId}
        >
          {run.isPending ? "Running…" : "Run"}
        </button>
        <button
          className="btn"
          onClick={() => preview.mutate()}
          disabled={preview.isPending || !effectiveEndpointId}
        >
          Show URL
        </button>
      </div>

      {preview.data && <UrlPreview url={preview.data.url} />}
      <ErrorBox error={run.error || preview.error} />
      {result && (
        <ResultsView result={result} skip={0} pageSize={result.count} />
      )}
    </div>
  );
}

function summarise(template: SavedQuery): string {
  if (template.mode === "raw" && template.raw_query) return template.raw_query;
  const spec = template.spec;
  if (spec.entity_id) return `${template.entity_set || "?"}(${spec.entity_id})`;
  if (spec.raw_filter) return spec.raw_filter;
  if (spec.clauses.length) {
    return spec.clauses
      .map((clause) => `${clause.field} ${clause.op} ${clause.value ?? ""}`)
      .join(` ${spec.clause_logic} `);
  }
  return template.entity_set || "—";
}

export default function QueriesPage() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<SavedQuery | null>(null);
  const [search, setSearch] = useState("");

  const queries = useQuery({ queryKey: ["queries"], queryFn: () => api.listQueries() });
  const endpoints = useQuery({ queryKey: ["endpoints"], queryFn: api.listEndpoints });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteQuery(id),
    onSuccess: () => {
      setSelected(null);
      queryClient.invalidateQueries({ queryKey: ["queries"] });
    },
  });

  const { builtin, custom } = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const matching = (queries.data ?? []).filter(
      (template) =>
        !needle ||
        template.name.toLowerCase().includes(needle) ||
        template.description.toLowerCase().includes(needle) ||
        template.tags.toLowerCase().includes(needle),
    );
    return {
      builtin: matching.filter((template) => template.is_builtin),
      custom: matching.filter((template) => !template.is_builtin),
    };
  }, [queries.data, search]);

  const endpointName = (id: number | null) =>
    id === null
      ? "any endpoint"
      : endpoints.data?.find((endpoint) => endpoint.id === id)?.name ?? `#${id}`;

  const card = (template: SavedQuery) => (
    <div key={template.id} className="card card-interactive rise-in flex flex-col gap-2 p-3.5">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-medium">{template.name}</h3>
        <span className="badge shrink-0">{endpointName(template.endpoint_id)}</span>
      </div>
      {template.description && (
        <p className="text-xs" style={{ color: "var(--muted)" }}>
          {template.description}
        </p>
      )}
      <code
        className="mono block truncate rounded border px-2 py-1 text-xs"
        style={{ borderColor: "var(--border)", color: "var(--muted)" }}
        title={summarise(template)}
      >
        {summarise(template)}
      </code>
      <div className="flex flex-wrap gap-1.5">
        {template.params.map((param) => (
          <span key={param.name} className="badge">
            {param.name}: {param.type}
          </span>
        ))}
      </div>
      <div className="mt-auto flex items-center gap-2 pt-1">
        <button className="btn btn-sm btn-primary" onClick={() => setSelected(template)}>
          Run
        </button>
        {!template.is_builtin && (
          <ConfirmButton onConfirm={() => remove.mutate(template.id)}>Delete</ConfirmButton>
        )}
      </div>
    </div>
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Templates</h1>
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            Saved queries with fill-in parameters.
          </p>
        </div>
        <div className="flex gap-2">
          <input
            className="input w-56"
            placeholder="Search templates…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <Link href="/query" className="btn btn-primary">
            New query
          </Link>
        </div>
      </div>

      {selected && <RunPanel template={selected} onClose={() => setSelected(null)} />}

      <ErrorBox error={queries.error || remove.error} />
      {queries.isLoading && <Spinner />}

      {custom.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
            Your templates
          </h2>
          <div className="stagger grid gap-3 md:grid-cols-2 xl:grid-cols-3">{custom.map(card)}</div>
        </section>
      )}

      {builtin.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
            Built-in
          </h2>
          <div className="stagger grid gap-3 md:grid-cols-2 xl:grid-cols-3">{builtin.map(card)}</div>
        </section>
      )}

      {!queries.isLoading && custom.length === 0 && builtin.length === 0 && (
        <EmptyState title="Nothing matches" hint="Try a different search term." />
      )}
    </div>
  );
}
