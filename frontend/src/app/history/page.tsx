"use client";

import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { QueryRun } from "@/lib/types";
import { ConfirmButton, CopyButton, EmptyState, ErrorBox, Spinner } from "@/components/ui";

function when(iso: string): string {
  const date = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  return date.toLocaleString();
}

export default function HistoryPage() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const history = useQuery({ queryKey: ["history"], queryFn: () => api.listHistory(200) });

  const clear = useMutation({
    mutationFn: () => api.clearHistory(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["history"] }),
  });

  /** Hand the spec to the workspace through sessionStorage, then navigate. */
  const reopen = (run: QueryRun) => {
    sessionStorage.setItem(
      "odata-ui:spec",
      JSON.stringify({ spec: run.spec, endpoint_id: run.endpoint_id }),
    );
    router.push(`/query?endpoint=${run.endpoint_id ?? ""}`);
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">History</h1>
          <p className="text-sm" style={{ color: "var(--muted)" }}>
            Every query this app has run.
          </p>
        </div>
        {history.data && history.data.length > 0 && (
          <ConfirmButton onConfirm={() => clear.mutate()} className="btn btn-danger">
            Clear history
          </ConfirmButton>
        )}
      </div>

      <ErrorBox error={history.error || clear.error} />
      {history.isLoading && <Spinner />}

      {history.data?.length === 0 && (
        <EmptyState title="Nothing here yet" hint="Runs will show up as you query." />
      )}

      {history.data && history.data.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr style={{ color: "var(--muted)" }}>
                {["When", "Endpoint", "Template", "Status", "Rows", "URL", ""].map((header) => (
                  <th
                    key={header}
                    className="whitespace-nowrap border-b px-3 py-2 text-left font-semibold"
                    style={{ borderColor: "var(--border)" }}
                  >
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.data.map((run) => {
                const failed = Boolean(run.error) || (run.status_code ?? 0) >= 400;
                return (
                  <tr key={run.id} className="row-hover">
                    <td className="whitespace-nowrap border-b px-3 py-2" style={{ borderColor: "var(--border)" }}>
                      {when(run.created_at)}
                    </td>
                    <td className="whitespace-nowrap border-b px-3 py-2" style={{ borderColor: "var(--border)" }}>
                      {run.endpoint_name}
                    </td>
                    <td className="whitespace-nowrap border-b px-3 py-2" style={{ borderColor: "var(--border)" }}>
                      {run.saved_query_name || <span style={{ color: "var(--muted)" }}>ad-hoc</span>}
                    </td>
                    <td
                      className="whitespace-nowrap border-b px-3 py-2"
                      style={{ borderColor: "var(--border)", color: failed ? "#d1242f" : "#1a7f37" }}
                      title={run.error ?? ""}
                    >
                      {run.status_code ?? "err"}
                      {run.duration_ms !== null && (
                        <span className="ml-1.5" style={{ color: "var(--muted)" }}>
                          {run.duration_ms} ms
                        </span>
                      )}
                    </td>
                    <td className="border-b px-3 py-2" style={{ borderColor: "var(--border)" }}>
                      {run.result_count ?? "—"}
                    </td>
                    <td
                      className="mono max-w-[34rem] truncate border-b px-3 py-2"
                      style={{ borderColor: "var(--border)", color: "var(--muted)" }}
                      title={run.url}
                    >
                      {run.url}
                    </td>
                    <td className="whitespace-nowrap border-b px-3 py-2" style={{ borderColor: "var(--border)" }}>
                      <div className="flex gap-1.5">
                        <CopyButton value={run.url} />
                        <button
                          className="btn btn-sm"
                          onClick={() => reopen(run)}
                          disabled={!run.endpoint_id}
                        >
                          Reopen
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
