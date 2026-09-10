"use client";

import type { QueryParam } from "@/lib/types";
import { Field } from "./ui";

/** Maps a parameter's declared type onto a sensible HTML input. */
function inputProps(type: QueryParam["type"]) {
  switch (type) {
    case "number":
      return { type: "number" };
    case "datetime":
      return { type: "datetime-local" };
    default:
      return { type: "text" };
  }
}

export function ParamForm({
  params,
  values,
  onChange,
}: {
  params: QueryParam[];
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
}) {
  if (params.length === 0) {
    return (
      <p className="text-xs" style={{ color: "var(--muted)" }}>
        This template takes no parameters.
      </p>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {params.map((param) => (
        <Field
          key={param.name}
          label={`${param.label || param.name}${param.required ? " *" : ""}`}
          hint={param.help}
        >
          {param.type === "boolean" ? (
            <select
              className="select"
              value={values[param.name] ?? ""}
              onChange={(event) =>
                onChange({ ...values, [param.name]: event.target.value })
              }
            >
              <option value="">—</option>
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          ) : (
            <input
              className="input mono"
              {...inputProps(param.type)}
              value={values[param.name] ?? ""}
              placeholder={
                param.default !== null && param.default !== undefined
                  ? String(param.default)
                  : ""
              }
              onChange={(event) =>
                onChange({ ...values, [param.name]: event.target.value })
              }
            />
          )}
        </Field>
      ))}
    </div>
  );
}
