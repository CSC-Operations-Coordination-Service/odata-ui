export type AuthMethod = "none" | "basic" | "static_token" | "oauth2";
export type ODataVersion = "v3" | "v4";
export type GrantType = "password" | "client_credentials";

export interface Endpoint {
  id: number;
  name: string;
  description: string;
  tags: string;
  base_url: string;
  entity_location: string;
  default_entity_set: string;
  odata_version: ODataVersion;
  verify_ssl: boolean;
  timeout: number;
  default_page_size: number;
  auth_method: AuthMethod;
  token_field_header: string;
  client_username: string;
  token_url: string;
  client_id: string;
  scope: string;
  grant_type: GrantType;
  has_client_password: boolean;
  has_client_secret: boolean;
  has_static_token: boolean;
  has_oauth_basic_credential: boolean;
  last_probe_at: string | null;
  last_probe_status: number | null;
  last_probe_latency_ms: number | null;
  last_probe_error: string | null;
  created_at: string;
  updated_at: string;
}

export type EndpointInput = Partial<
  Omit<
    Endpoint,
    | "id"
    | "created_at"
    | "updated_at"
    | "last_probe_at"
    | "last_probe_status"
    | "last_probe_latency_ms"
    | "last_probe_error"
    | "has_client_password"
    | "has_client_secret"
    | "has_static_token"
    | "has_oauth_basic_credential"
  >
> & {
  client_password?: string;
  client_secret?: string;
  static_token?: string;
  oauth_basic_credential?: string;
};

export interface ProbeResult {
  ok: boolean;
  status_code: number | null;
  latency_ms: number | null;
  url: string;
  error: string | null;
  detail: string | null;
}

export interface PropertyInfo {
  name: string;
  type: string;
  nullable: boolean;
  is_key: boolean;
}

export interface EntitySetInfo {
  name: string;
  entity_type: string;
  properties: PropertyInfo[];
  navigation_properties: string[];
  keys: string[];
}

export interface MetadataResult {
  entity_sets: EntitySetInfo[];
  url: string;
  error: string | null;
}

export type ClauseOp =
  | "eq" | "ne" | "gt" | "ge" | "lt" | "le"
  | "contains" | "startswith" | "endswith"
  | "in" | "isnull" | "isnotnull";

export type ValueType =
  | "string" | "number" | "boolean" | "guid" | "datetime" | "null" | "raw";

export interface Clause {
  field: string;
  op: ClauseOp;
  value: string | number | boolean | null;
  value_type: ValueType;
}

export interface OrderBy {
  field: string;
  direction: "asc" | "desc";
}

export interface QuerySpec {
  entity_set?: string;
  entity_id?: string | null;
  entity_id_type?: string | null;
  clauses: Clause[];
  clause_logic: "and" | "or";
  raw_filter?: string | null;
  select: string[];
  expand: string[];
  orderby: OrderBy[];
  top?: number | null;
  skip?: number | null;
  count: boolean;
  custom_suffix: string;
  raw_query?: string | null;
}

export interface QueryPreview {
  url: string;
  filter: string;
}

export interface QueryResponse {
  url: string;
  status_code: number;
  duration_ms: number;
  count: number;
  total_count: number | null;
  has_next: boolean;
  rows: Record<string, unknown>[];
  columns: string[];
}

export interface QueryParam {
  name: string;
  label: string;
  type: ValueType;
  default: unknown;
  required: boolean;
  help: string;
}

export interface SavedQuery {
  id: number;
  name: string;
  description: string;
  tags: string;
  is_builtin: boolean;
  endpoint_id: number | null;
  entity_set: string;
  mode: "builder" | "raw";
  spec: QuerySpec;
  raw_query: string;
  params: QueryParam[];
  created_at: string;
  updated_at: string;
}

export interface QueryRun {
  id: number;
  endpoint_id: number | null;
  endpoint_name: string;
  saved_query_id: number | null;
  saved_query_name: string;
  url: string;
  status_code: number | null;
  duration_ms: number | null;
  result_count: number | null;
  error: string | null;
  spec: QuerySpec;
  created_at: string;
}

export interface ImportedEndpoint {
  name: string;
  action: string;
  reason: string;
}

export const emptySpec = (): QuerySpec => ({
  entity_set: "",
  entity_id: null,
  clauses: [],
  clause_logic: "and",
  raw_filter: null,
  select: [],
  expand: [],
  orderby: [],
  top: 50,
  skip: null,
  count: true,
  custom_suffix: "",
  raw_query: null,
});
