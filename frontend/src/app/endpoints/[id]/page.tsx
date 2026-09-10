"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { EndpointInput } from "@/lib/types";
import { EndpointForm } from "@/components/EndpointForm";
import { ConfirmButton, ErrorBox, Spinner } from "@/components/ui";

export default function EditEndpointPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const router = useRouter();
  const queryClient = useQueryClient();

  const endpoint = useQuery({
    queryKey: ["endpoint", id],
    queryFn: () => api.getEndpoint(id),
    enabled: Number.isFinite(id),
  });

  const update = useMutation({
    mutationFn: (payload: EndpointInput) => api.updateEndpoint(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["endpoints"] });
      queryClient.invalidateQueries({ queryKey: ["endpoint", id] });
      queryClient.invalidateQueries({ queryKey: ["metadata", id] });
    },
  });

  const probe = useMutation({
    mutationFn: () => api.probeEndpoint(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["endpoint", id] }),
  });

  const remove = useMutation({
    mutationFn: () => api.deleteEndpoint(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["endpoints"] });
      router.push("/endpoints");
    },
  });

  if (endpoint.isLoading) return <Spinner />;
  if (endpoint.error) return <ErrorBox error={endpoint.error} />;
  if (!endpoint.data) return null;

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <Link
            href="/endpoints"
            className="text-xs hover:underline"
            style={{ color: "var(--muted)" }}
          >
            ← Endpoints
          </Link>
          <h1 className="mt-1 text-lg font-semibold">{endpoint.data.name}</h1>
        </div>
        <Link href={`/query?endpoint=${id}`} className="btn btn-primary">
          Query this endpoint
        </Link>
      </div>

      {probe.data && (
        <div
          className="card px-3 py-2 text-sm"
          style={{ color: probe.data.ok ? "#1a7f37" : "#d1242f" }}
        >
          {probe.data.ok
            ? `Connection OK — HTTP ${probe.data.status_code} in ${probe.data.latency_ms} ms. ${probe.data.detail}`
            : `Connection failed — ${probe.data.error}`}
          <p className="mono mt-1 break-all text-xs" style={{ color: "var(--muted)" }}>
            {probe.data.url}
          </p>
        </div>
      )}

      <EndpointForm
        endpoint={endpoint.data}
        onSubmit={(payload) => update.mutate(payload)}
        submitting={update.isPending}
        error={update.error || probe.error || remove.error}
        submitLabel={update.isSuccess ? "Saved" : "Save changes"}
        extraActions={
          <>
            <button
              type="button"
              className="btn"
              onClick={() => probe.mutate()}
              disabled={probe.isPending}
            >
              {probe.isPending ? "Testing…" : "Test connection"}
            </button>
            <ConfirmButton
              onConfirm={() => remove.mutate()}
              className="btn btn-danger ml-auto"
            >
              Delete endpoint
            </ConfirmButton>
          </>
        }
      />
    </div>
  );
}
