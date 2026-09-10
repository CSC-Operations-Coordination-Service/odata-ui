"use client";

import { useState } from "react";
import type { Endpoint, EndpointInput } from "@/lib/types";
import { ErrorBox, Field } from "./ui";

const SECRET_KEYS = [
  "client_password",
  "client_secret",
  "static_token",
  "oauth_basic_credential",
] as const;

type SecretKey = (typeof SECRET_KEYS)[number];

const emptyDraft = (): EndpointInput => ({
  name: "",
  description: "",
  tags: "",
  base_url: "",
  entity_location: "/odata/v1/",
  default_entity_set: "Products",
  odata_version: "v4",
  verify_ssl: true,
  timeout: 60,
  default_page_size: 100,
  auth_method: "none",
  token_field_header: "Authorization",
  client_username: "",
  token_url: "",
  client_id: "",
  scope: "",
  grant_type: "password",
});

function toDraft(endpoint: Endpoint): EndpointInput {
  const { ...rest } = endpoint;
  const draft: Record<string, unknown> = {};
  for (const key of Object.keys(emptyDraft())) {
    draft[key] = (rest as Record<string, unknown>)[key];
  }
  return draft as EndpointInput;
}

export function EndpointForm({
  endpoint,
  onSubmit,
  submitting,
  error,
  submitLabel = "Save",
  extraActions,
}: {
  endpoint?: Endpoint;
  onSubmit: (payload: EndpointInput) => void;
  submitting?: boolean;
  error?: unknown;
  submitLabel?: string;
  extraActions?: React.ReactNode;
}) {
  const [draft, setDraft] = useState<EndpointInput>(
    endpoint ? toDraft(endpoint) : emptyDraft(),
  );
  // Secrets are write-only: the form only holds values the user has just typed.
  const [secrets, setSecrets] = useState<Partial<Record<SecretKey, string>>>({});
  const [editingSecret, setEditingSecret] = useState<Partial<Record<SecretKey, boolean>>>({});

  const set = <K extends keyof EndpointInput>(key: K, value: EndpointInput[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));

  const has = (key: SecretKey) =>
    endpoint ? (endpoint[`has_${key}` as keyof Endpoint] as boolean) : false;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    // Only send secrets the user actually touched, so the rest keep their stored value.
    onSubmit({ ...draft, ...secrets });
  };

  const authMethod = draft.auth_method ?? "none";

  const secretField = (key: SecretKey, label: string, hint?: string) => {
    const stored = has(key);
    const editing = editingSecret[key] || !stored;
    return (
      <Field label={label} hint={hint}>
        {editing ? (
          <div className="flex gap-2">
            <input
              className="input mono"
              type="password"
              autoComplete="new-password"
              placeholder={stored ? "Enter a new value" : ""}
              value={secrets[key] ?? ""}
              onChange={(event) =>
                setSecrets((current) => ({ ...current, [key]: event.target.value }))
              }
            />
            {stored && (
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => {
                  setEditingSecret((current) => ({ ...current, [key]: false }));
                  setSecrets((current) => {
                    const next = { ...current };
                    delete next[key];
                    return next;
                  });
                }}
              >
                Keep
              </button>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span className="mono flex-1 text-sm" style={{ color: "var(--muted)" }}>
              ••••••••••  (set)
            </span>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => setEditingSecret((current) => ({ ...current, [key]: true }))}
            >
              Replace
            </button>
            <button
              type="button"
              className="btn btn-sm btn-danger"
              onClick={() => {
                setSecrets((current) => ({ ...current, [key]: "" }));
                setEditingSecret((current) => ({ ...current, [key]: false }));
              }}
            >
              Clear
            </button>
          </div>
        )}
      </Field>
    );
  };

  return (
    <form onSubmit={submit} className="space-y-5">
      <section className="card p-4">
        <h2 className="mb-3 text-sm font-semibold">Identity</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" hint="Equivalent to a maas-collector interface_name.">
            <input
              className="input"
              required
              value={draft.name ?? ""}
              onChange={(event) => set("name", event.target.value)}
              placeholder="prip-s1"
            />
          </Field>
          <Field label="Tags" hint="Comma-separated, for filtering.">
            <input
              className="input"
              value={draft.tags ?? ""}
              onChange={(event) => set("tags", event.target.value)}
              placeholder="prip,sentinel-1"
            />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Description">
              <input
                className="input"
                value={draft.description ?? ""}
                onChange={(event) => set("description", event.target.value)}
              />
            </Field>
          </div>
        </div>
      </section>

      <section className="card p-4">
        <h2 className="mb-3 text-sm font-semibold">Service</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field label="Base URL" hint="Scheme and host, without the OData path.">
              <input
                className="input mono"
                required
                value={draft.base_url ?? ""}
                onChange={(event) => set("base_url", event.target.value)}
                placeholder="https://prip.example.org"
              />
            </Field>
          </div>
          <Field label="Entity location" hint="Path between the host and the entity set.">
            <input
              className="input mono"
              value={draft.entity_location ?? ""}
              onChange={(event) => set("entity_location", event.target.value)}
              placeholder="/odata/v1/"
            />
          </Field>
          <Field label="Default entity set">
            <input
              className="input mono"
              value={draft.default_entity_set ?? ""}
              onChange={(event) => set("default_entity_set", event.target.value)}
              placeholder="Products"
            />
          </Field>
          <Field label="OData version">
            <select
              className="select"
              value={draft.odata_version ?? "v4"}
              onChange={(event) =>
                set("odata_version", event.target.value as EndpointInput["odata_version"])
              }
            >
              <option value="v4">v4</option>
              <option value="v3">v3</option>
            </select>
          </Field>
          <Field label="Page size" hint="Default $top for new queries.">
            <input
              className="input"
              type="number"
              min={1}
              max={5000}
              value={draft.default_page_size ?? 100}
              onChange={(event) => set("default_page_size", Number(event.target.value))}
            />
          </Field>
          <Field label="Timeout (seconds)">
            <input
              className="input"
              type="number"
              min={1}
              max={600}
              value={draft.timeout ?? 60}
              onChange={(event) => set("timeout", Number(event.target.value))}
            />
          </Field>
          <div className="flex items-end">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft.verify_ssl ?? true}
                onChange={(event) => set("verify_ssl", event.target.checked)}
              />
              Verify TLS certificates
            </label>
          </div>
        </div>
      </section>

      <section className="card p-4">
        <h2 className="mb-3 text-sm font-semibold">Authentication</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Method">
            <select
              className="select"
              value={authMethod}
              onChange={(event) =>
                set("auth_method", event.target.value as EndpointInput["auth_method"])
              }
            >
              <option value="none">None</option>
              <option value="basic">Basic</option>
              <option value="static_token">Static token</option>
              <option value="oauth2">OAuth2</option>
            </select>
          </Field>

          {authMethod !== "none" && (
            <Field
              label="Header name"
              hint="Where the credential is sent. Usually Authorization."
            >
              <input
                className="input mono"
                value={draft.token_field_header ?? ""}
                onChange={(event) => set("token_field_header", event.target.value)}
              />
            </Field>
          )}

          {authMethod === "basic" && (
            <>
              <Field label="Username">
                <input
                  className="input"
                  value={draft.client_username ?? ""}
                  onChange={(event) => set("client_username", event.target.value)}
                />
              </Field>
              {secretField("client_password", "Password")}
            </>
          )}

          {authMethod === "static_token" &&
            secretField(
              "static_token",
              "Token",
              "Stored and sent verbatim - include the 'Bearer ' prefix if the service expects it.",
            )}

          {authMethod === "oauth2" && (
            <>
              <div className="sm:col-span-2">
                <Field label="Token URL">
                  <input
                    className="input mono"
                    value={draft.token_url ?? ""}
                    onChange={(event) => set("token_url", event.target.value)}
                    placeholder="https://auth.example.org/realms/x/protocol/openid-connect/token"
                  />
                </Field>
              </div>
              <Field label="Grant type">
                <select
                  className="select"
                  value={draft.grant_type ?? "password"}
                  onChange={(event) =>
                    set("grant_type", event.target.value as EndpointInput["grant_type"])
                  }
                >
                  <option value="password">password</option>
                  <option value="client_credentials">client_credentials</option>
                </select>
              </Field>
              <Field label="Client id">
                <input
                  className="input mono"
                  value={draft.client_id ?? ""}
                  onChange={(event) => set("client_id", event.target.value)}
                />
              </Field>
              {secretField("client_secret", "Client secret")}
              <Field label="Scope" hint="Optional.">
                <input
                  className="input mono"
                  value={draft.scope ?? ""}
                  onChange={(event) => set("scope", event.target.value)}
                />
              </Field>
              {draft.grant_type !== "client_credentials" && (
                <>
                  <Field label="Username">
                    <input
                      className="input"
                      value={draft.client_username ?? ""}
                      onChange={(event) => set("client_username", event.target.value)}
                    />
                  </Field>
                  {secretField("client_password", "Password")}
                </>
              )}
              {secretField(
                "oauth_basic_credential",
                "Basic credential for the token request",
                "Optional. Pre-encoded base64 of client_id:client_secret, sent as an Authorization header on the token call.",
              )}
            </>
          )}
        </div>
      </section>

      <ErrorBox error={error} />

      <div className="flex items-center gap-2">
        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? "Saving…" : submitLabel}
        </button>
        {extraActions}
      </div>
    </form>
  );
}
