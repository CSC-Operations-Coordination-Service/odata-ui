import type {
  Endpoint,
  EndpointInput,
  ImportedEndpoint,
  MetadataResult,
  ProbeResult,
  QueryPreview,
  QueryResponse,
  QueryRun,
  QuerySpec,
  SavedQuery,
} from "./types";

// An explicitly empty value - or "/" - means "same origin": the UI and the API sit
// behind one host, so requests go out as relative paths. That keeps the built image
// free of any environment-specific hostname. Only an unset variable falls back.
const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const API_BASE = configuredApiUrl.replace(/\/+$/, "");

/** An error carrying whatever the OData service itself said, so the UI can show it. */
export class ApiError extends Error {
  status: number;
  upstreamStatus?: number | null;
  upstreamBody?: string;
  url?: string;
  missing?: string[];

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let detail: unknown;
  try {
    detail = (await response.json())?.detail;
  } catch {
    detail = await response.text().catch(() => "");
  }

  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    const error = new ApiError(
      (d.message as string) || `Request failed (${response.status}).`,
      response.status,
    );
    error.upstreamStatus = (d.upstream_status as number) ?? null;
    error.upstreamBody = (d.upstream_body as string) ?? "";
    error.url = d.url as string;
    if (Array.isArray(d.missing)) error.missing = d.missing as string[];
    return error;
  }

  if (Array.isArray(detail)) {
    // FastAPI validation errors.
    const messages = detail
      .map((item: Record<string, unknown>) => {
        const loc = Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "";
        return loc ? `${loc}: ${item.msg}` : String(item.msg);
      })
      .join("; ");
    return new ApiError(messages || `Request failed (${response.status}).`, response.status);
  }

  return new ApiError(
    (detail as string) || `Request failed (${response.status}).`,
    response.status,
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
  } catch (cause) {
    throw new ApiError(
      `Cannot reach the backend at ${API_BASE || "the same origin as this page"}. Is it running?`,
      0,
    );
  }
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const json = (body: unknown) => ({ body: JSON.stringify(body) });

export const api = {
  listEndpoints: () => request<Endpoint[]>("/api/endpoints"),
  getEndpoint: (id: number) => request<Endpoint>(`/api/endpoints/${id}`),
  createEndpoint: (payload: EndpointInput) =>
    request<Endpoint>("/api/endpoints", { method: "POST", ...json(payload) }),
  updateEndpoint: (id: number, payload: EndpointInput) =>
    request<Endpoint>(`/api/endpoints/${id}`, { method: "PATCH", ...json(payload) }),
  deleteEndpoint: (id: number) =>
    request<void>(`/api/endpoints/${id}`, { method: "DELETE" }),
  probeEndpoint: (id: number) =>
    request<ProbeResult>(`/api/endpoints/${id}/probe`, { method: "POST" }),
  getMetadata: (id: number, refresh = false) =>
    request<MetadataResult>(`/api/endpoints/${id}/metadata?refresh=${refresh}`),
  importEndpoints: (content: string, overwrite: boolean) =>
    request<{ imported: ImportedEndpoint[] }>("/api/endpoints/import", {
      method: "POST",
      ...json({ content, overwrite }),
    }),

  previewQuery: (endpointId: number, spec: QuerySpec) =>
    request<QueryPreview>("/api/query/preview", {
      method: "POST",
      ...json({ endpoint_id: endpointId, spec }),
    }),
  runQuery: (endpointId: number, spec: QuerySpec) =>
    request<QueryResponse>("/api/query/run", {
      method: "POST",
      ...json({ endpoint_id: endpointId, spec }),
    }),
  exportUrl: (format: "csv" | "json") => `${API_BASE}/api/query/export?format=${format}`,

  listQueries: (endpointId?: number | null) =>
    request<SavedQuery[]>(
      endpointId ? `/api/queries?endpoint_id=${endpointId}` : "/api/queries",
    ),
  getQuery: (id: number) => request<SavedQuery>(`/api/queries/${id}`),
  createQuery: (payload: Record<string, unknown>) =>
    request<SavedQuery>("/api/queries", { method: "POST", ...json(payload) }),
  updateQuery: (id: number, payload: Record<string, unknown>) =>
    request<SavedQuery>(`/api/queries/${id}`, { method: "PATCH", ...json(payload) }),
  deleteQuery: (id: number) => request<void>(`/api/queries/${id}`, { method: "DELETE" }),
  previewSavedQuery: (id: number, body: Record<string, unknown>) =>
    request<QueryPreview>(`/api/queries/${id}/preview`, { method: "POST", ...json(body) }),
  runSavedQuery: (id: number, body: Record<string, unknown>) =>
    request<QueryResponse>(`/api/queries/${id}/run`, { method: "POST", ...json(body) }),

  listHistory: (limit = 100) => request<QueryRun[]>(`/api/history?limit=${limit}`),
  clearHistory: () => request<void>("/api/history", { method: "DELETE" }),
};

/** Trigger a browser download of the export endpoint's response. */
export async function downloadExport(
  endpointId: number,
  spec: QuerySpec,
  format: "csv" | "json",
) {
  const response = await fetch(api.exportUrl(format), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ endpoint_id: endpointId, spec }),
  });
  if (!response.ok) throw await toApiError(response);

  const disposition = response.headers.get("content-disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = match?.[1] || `export.${format}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
