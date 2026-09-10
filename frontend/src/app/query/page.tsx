"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, downloadExport } from "@/lib/api";
import { emptySpec, type QueryResponse, type QuerySpec } from "@/lib/types";
import { QueryBuilder } from "@/components/QueryBuilder";
import { ResultsView } from "@/components/ResultsView";
import { UrlPreview } from "@/components/UrlPreview";
import { SaveQueryDialog } from "@/components/SaveQueryDialog";
import { EmptyState, ErrorBox, Spinner, StatusDot } from "@/components/ui";

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

function Workspace() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const endpoints = useQuery({ queryKey: ["endpoints"], queryFn: api.listEndpoints });

  const [endpointId, setEndpointId] = useState<number | null>(null);
  const [mode, setMode] = useState<"builder" | "raw">("builder");
  const [spec, setSpec] = useState<QuerySpec>(emptySpec());
  const [rawQuery, setRawQuery] = useState("");
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [showSave, setShowSave] = useState(false);

  // Pick up ?endpoint= / ?run= (from the endpoints list, templates or history).
  useEffect(() => {
    const fromUrl = Number(searchParams.get("endpoint"));
    if (Number.isFinite(fromUrl) && fromUrl > 0) setEndpointId(fromUrl);
  }, [searchParams]);

  useEffect(() => {
    if (endpointId === null && endpoints.data?.length) setEndpointId(endpoints.data[0].id);
  }, [endpoints.data, endpointId]);

  const endpoint = useMemo(
    () => endpoints.data?.find((item) => item.id === endpointId),
    [endpoints.data, endpointId],
  );

  // Restore a spec handed over from another page.
  useEffect(() => {
    const stashed = sessionStorage.getItem("odata-ui:spec");
    if (!stashed) return;
    sessionStorage.removeItem("odata-ui:spec");
    try {
      const parsed = JSON.parse(stashed) as { spec: QuerySpec; endpoint_id?: number };
      setSpec({ ...emptySpec(), ...parsed.spec });
      if (parsed.spec.raw_query) {
        setMode("raw");
        setRawQuery(parsed.spec.raw_query);
      }
      if (parsed.endpoint_id) setEndpointId(parsed.endpoint_id);
    } catch {
      /* ignore a malformed stash */
    }
  }, []);

  // Default the entity set to the endpoint's own default when switching endpoints.
  useEffect(() => {
    if (endpoint && !spec.entity_set) {
      setSpec((current) => ({
        ...current,
        entity_set: endpoint.default_entity_set,
        top: current.top ?? endpoint.default_page_size,
      }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [endpoint?.id]);

  const metadata = useQuery({
    queryKey: ["metadata", endpointId],
    queryFn: () => api.getMetadata(endpointId as number),
    enabled: Boolean(endpointId),
  });

  const entitySetInfo = useMemo(
    () => metadata.data?.entity_sets.find((item) => item.name === spec.entity_set),
    [metadata.data, spec.entity_set],
  );

  // The spec that is actually sent: raw mode swaps the builder output for a raw string.
  const effectiveSpec: QuerySpec = useMemo(
    () =>
      mode === "raw"
        ? { ...emptySpec(), entity_set: spec.entity_set, entity_id: spec.entity_id, raw_query: rawQuery }
        : { ...spec, raw_query: null },
    [mode, spec, rawQuery],
  );

  const debouncedSpec = useDebounced(effectiveSpec, 300);

  const preview = useQuery({
    queryKey: ["preview", endpointId, debouncedSpec],
    queryFn: () => api.previewQuery(endpointId as number, debouncedSpec),
    enabled: Boolean(endpointId),
  });

  const run = useMutation({
    mutationFn: (nextSpec: QuerySpec) => api.runQuery(endpointId as number, nextSpec),
    onSuccess: (data) => {
      setResult(data);
      queryClient.invalidateQueries({ queryKey: ["history"] });
    },
  });

  const save = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.createQuery(payload),
    onSuccess: () => {
      setShowSave(false);
      queryClient.invalidateQueries({ queryKey: ["queries"] });
    },
  });

  const exportRows = useMutation({
    mutationFn: (format: "csv" | "json") =>
      downloadExport(endpointId as number, effectiveSpec, format),
  });

  const goToPage = (nextSkip: number) => {
    const paged = { ...effectiveSpec, skip: nextSkip || null };
    setSpec((current) => ({ ...current, skip: nextSkip || null }));
    run.mutate(paged);
  };

  if (endpoints.isLoading) return <Spinner />;
  if (endpoints.data?.length === 0) {
    return (
      <EmptyState
        title="No endpoints registered"
        hint="Add an OData service first — then you can query it from here."
        action={
          <Link href="/endpoints/new" className="btn btn-primary mt-2">
            New endpoint
          </Link>
        }
      />
    );
  }

  const previewError =
    preview.error instanceof ApiError && preview.error.status === 400
      ? preview.error.message
      : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[14rem]">
          <label className="label">Endpoint</label>
          <select
            className="select"
            value={endpointId ?? ""}
            onChange={(event) => {
              setEndpointId(Number(event.target.value));
              setSpec((current) => ({ ...current, entity_set: "", skip: null }));
              setResult(null);
            }}
          >
            {endpoints.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>

        <div className="min-w-[12rem]">
          <label className="label">Entity set</label>
          <input
            className="input mono"
            list="entity-sets"
            value={spec.entity_set ?? ""}
            onChange={(event) =>
              setSpec((current) => ({ ...current, entity_set: event.target.value }))
            }
          />
          <datalist id="entity-sets">
            {metadata.data?.entity_sets.map((item) => (
              <option key={item.name} value={item.name} />
            ))}
          </datalist>
        </div>

        {endpoint && (
          <div className="flex items-center gap-2 pb-2 text-xs" style={{ color: "var(--muted)" }}>
            <StatusDot endpoint={endpoint} />
            <span className="badge">{endpoint.odata_version}</span>
            {metadata.isLoading && <span>reading $metadata…</span>}
            {metadata.data?.error && (
              <span title={metadata.data.error}>
                $metadata unavailable — type field names by hand
              </span>
            )}
          </div>
        )}

        <div className="ml-auto flex gap-2 pb-0.5">
          <button
            className="btn"
            onClick={() => setShowSave(true)}
            disabled={!endpointId}
          >
            Save as template
          </button>
          <button
            className="btn btn-primary"
            onClick={() => run.mutate(effectiveSpec)}
            disabled={!endpointId || run.isPending}
          >
            {run.isPending ? "Running…" : "Run query"}
          </button>
        </div>
      </div>

      <UrlPreview url={preview.data?.url ?? ""} error={previewError} />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,30rem)_minmax(0,1fr)]">
        <div className="card p-4">
          <div className="mb-3 flex overflow-hidden rounded-md border" style={{ borderColor: "var(--border)" }}>
            {(["builder", "raw"] as const).map((tab) => (
              <button
                key={tab}
                className="flex-1 px-3 py-1.5 text-xs font-medium capitalize"
                style={{
                  background: mode === tab ? "var(--accent)" : "transparent",
                  color: mode === tab ? "#fff" : "var(--muted)",
                  transition:
                    "background-color 0.24s var(--ease), color 0.24s var(--ease)",
                }}
                onClick={() => setMode(tab)}
              >
                {tab === "raw" ? "Raw query" : "Builder"}
              </button>
            ))}
          </div>

          {mode === "builder" ? (
            <div key="builder" className="fade-in">
              <QueryBuilder spec={spec} onChange={setSpec} entitySet={entitySetInfo} />
            </div>
          ) : (
            <div key="raw" className="fade-in space-y-3">
              <div>
                <label className="label">Entity id (optional)</label>
                <input
                  className="input mono"
                  value={spec.entity_id ?? ""}
                  placeholder="GUID or key"
                  onChange={(event) =>
                    setSpec((current) => ({ ...current, entity_id: event.target.value || null }))
                  }
                />
              </div>
              <div>
                <label className="label">Query string</label>
                <textarea
                  className="textarea h-48 text-xs"
                  value={rawQuery}
                  placeholder="$filter=contains(Name,'S1A')&$top=20&$orderby=PublicationDate desc"
                  onChange={(event) => setRawQuery(event.target.value)}
                />
                <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
                  Sent as typed, after the entity set. Values are not escaped for you here.
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="space-y-3">
          <ErrorBox error={run.error || exportRows.error} />
          {run.isPending && <Spinner label="Querying the service…" />}
          {result && !run.isPending && (
            <ResultsView
              result={result}
              skip={spec.skip ?? 0}
              pageSize={spec.top ?? endpoint?.default_page_size ?? 50}
              onPage={goToPage}
              onExport={(format) => exportRows.mutate(format)}
              exporting={exportRows.isPending}
            />
          )}
          {!result && !run.isPending && !run.error && (
            <EmptyState
              title="No results yet"
              hint="Build a query on the left and press Run. The URL above is exactly what will be requested."
            />
          )}
        </div>
      </div>

      {showSave && endpointId && (
        <SaveQueryDialog
          spec={effectiveSpec}
          rawQuery={rawQuery}
          mode={mode}
          entitySet={spec.entity_set ?? ""}
          endpointId={endpointId}
          onSave={(payload) => save.mutate(payload)}
          onClose={() => setShowSave(false)}
          saving={save.isPending}
          error={save.error}
        />
      )}
    </div>
  );
}

export default function QueryPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Workspace />
    </Suspense>
  );
}
