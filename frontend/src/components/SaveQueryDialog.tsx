"use client";

import { useState } from "react";
import type { QuerySpec, ValueType } from "@/lib/types";
import { ErrorBox, Field } from "./ui";

const PLACEHOLDER_RE = /\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g;

export function findPlaceholders(spec: QuerySpec, rawQuery: string): string[] {
  const haystack = JSON.stringify(spec) + rawQuery;
  const names: string[] = [];
  for (const match of haystack.matchAll(PLACEHOLDER_RE)) {
    if (!names.includes(match[1])) names.push(match[1]);
  }
  return names;
}

const VALUE_TYPES: ValueType[] = ["string", "number", "boolean", "guid", "datetime"];

export function SaveQueryDialog({
  spec,
  rawQuery,
  mode,
  entitySet,
  endpointId,
  onSave,
  onClose,
  saving,
  error,
}: {
  spec: QuerySpec;
  rawQuery: string;
  mode: "builder" | "raw";
  entitySet: string;
  endpointId: number;
  onSave: (payload: Record<string, unknown>) => void;
  onClose: () => void;
  saving?: boolean;
  error?: unknown;
}) {
  const placeholders = findPlaceholders(spec, rawQuery);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [shared, setShared] = useState(placeholders.length > 0);
  const [types, setTypes] = useState<Record<string, ValueType>>(
    Object.fromEntries(placeholders.map((item) => [item, "string" as ValueType])),
  );

  return (
    <div className="fade-in fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/45 p-4 pt-16 backdrop-blur-sm">
      <div className="card scale-in w-full max-w-lg space-y-4 p-5">
        <div>
          <h2 className="text-sm font-semibold">Save as template</h2>
          <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
            Use <span className="mono">{"{{name}}"}</span> anywhere in the query to turn a
            value into a parameter you fill in at run time.
          </p>
        </div>

        <Field label="Name">
          <input
            className="input"
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Products by name fragment"
          />
        </Field>
        <Field label="Description">
          <input
            className="input"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <Field label="Tags" hint="Comma-separated.">
          <input
            className="input"
            value={tags}
            onChange={(event) => setTags(event.target.value)}
          />
        </Field>

        {placeholders.length > 0 && (
          <div>
            <label className="label">Parameters found</label>
            <div className="space-y-2">
              {placeholders.map((placeholder) => (
                <div key={placeholder} className="flex items-center gap-2">
                  <span className="mono flex-1 text-xs">{placeholder}</span>
                  <select
                    className="select w-auto text-xs"
                    value={types[placeholder]}
                    onChange={(event) =>
                      setTypes((current) => ({
                        ...current,
                        [placeholder]: event.target.value as ValueType,
                      }))
                    }
                  >
                    {VALUE_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </div>
        )}

        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={shared}
            onChange={(event) => setShared(event.target.checked)}
          />
          <span>
            Reusable across endpoints
            <span className="block text-xs" style={{ color: "var(--muted)" }}>
              Otherwise it stays tied to this endpoint.
            </span>
          </span>
        </label>

        <ErrorBox error={error} />

        <div className="flex justify-end gap-2">
          <button className="btn" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            disabled={!name.trim() || saving}
            onClick={() =>
              onSave({
                name: name.trim(),
                description,
                tags,
                endpoint_id: shared ? null : endpointId,
                entity_set: entitySet,
                mode,
                spec,
                raw_query: rawQuery,
                params: placeholders.map((placeholder) => ({
                  name: placeholder,
                  label: placeholder.replace(/_/g, " "),
                  type: types[placeholder],
                  required: true,
                })),
              })
            }
          >
            {saving ? "Saving…" : "Save template"}
          </button>
        </div>
      </div>
    </div>
  );
}
