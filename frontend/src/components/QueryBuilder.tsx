"use client";

import type { Clause, ClauseOp, EntitySetInfo, QuerySpec, ValueType } from "@/lib/types";
import { Field } from "./ui";

const OPS: { value: ClauseOp; label: string; unary?: boolean }[] = [
  { value: "eq", label: "equals" },
  { value: "ne", label: "not equals" },
  { value: "contains", label: "contains" },
  { value: "startswith", label: "starts with" },
  { value: "endswith", label: "ends with" },
  { value: "gt", label: ">" },
  { value: "ge", label: "≥" },
  { value: "lt", label: "<" },
  { value: "le", label: "≤" },
  { value: "in", label: "in (comma list)" },
  { value: "isnull", label: "is null", unary: true },
  { value: "isnotnull", label: "is not null", unary: true },
];

const VALUE_TYPES: ValueType[] = ["string", "number", "boolean", "guid", "datetime"];

/** Map an EDM type onto the value type our builder uses. */
function inferValueType(edmType: string): ValueType {
  const type = edmType.toLowerCase();
  if (type.includes("guid")) return "guid";
  if (type.includes("date") || type.includes("time")) return "datetime";
  if (type.includes("bool")) return "boolean";
  if (
    ["int", "double", "decimal", "single", "byte", "float"].some((n) => type.includes(n))
  ) {
    return "number";
  }
  return "string";
}

function FieldPicker({
  value,
  onChange,
  entitySet,
  placeholder = "Property",
  listId,
}: {
  value: string;
  onChange: (field: string, valueType?: ValueType) => void;
  entitySet?: EntitySetInfo;
  placeholder?: string;
  listId: string;
}) {
  const properties = entitySet?.properties ?? [];
  return (
    <>
      <input
        className="input mono"
        list={properties.length ? listId : undefined}
        value={value}
        placeholder={placeholder}
        onChange={(event) => {
          const next = event.target.value;
          const match = properties.find((property) => property.name === next);
          onChange(next, match ? inferValueType(match.type) : undefined);
        }}
      />
      {properties.length > 0 && (
        <datalist id={listId}>
          {properties.map((property) => (
            <option key={property.name} value={property.name}>
              {property.type}
              {property.is_key ? " (key)" : ""}
            </option>
          ))}
          {(entitySet?.navigation_properties ?? []).map((nav) => (
            <option key={nav} value={nav} />
          ))}
        </datalist>
      )}
    </>
  );
}

export function QueryBuilder({
  spec,
  onChange,
  entitySet,
}: {
  spec: QuerySpec;
  onChange: (spec: QuerySpec) => void;
  entitySet?: EntitySetInfo;
}) {
  const patch = (changes: Partial<QuerySpec>) => onChange({ ...spec, ...changes });

  const setClause = (index: number, changes: Partial<Clause>) => {
    const clauses = spec.clauses.map((clause, position) =>
      position === index ? { ...clause, ...changes } : clause,
    );
    patch({ clauses });
  };

  const addClause = () =>
    patch({
      clauses: [
        ...spec.clauses,
        { field: "", op: "contains", value: "", value_type: "string" },
      ],
    });

  const usingRawFilter = spec.raw_filter !== null && spec.raw_filter !== undefined;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label="Get one entity by id"
          hint="Fills the key predicate, e.g. Products(<id>). Leave empty to search instead."
        >
          <input
            className="input mono"
            value={spec.entity_id ?? ""}
            placeholder="GUID, number or key"
            onChange={(event) => patch({ entity_id: event.target.value || null })}
          />
        </Field>
        {entitySet?.keys.length ? (
          <div className="flex items-end pb-1.5 text-xs" style={{ color: "var(--muted)" }}>
            Key: <span className="mono ml-1">{entitySet.keys.join(", ")}</span>
          </div>
        ) : null}
      </div>

      <fieldset
        disabled={Boolean(spec.entity_id)}
        className={spec.entity_id ? "pointer-events-none opacity-45" : ""}
      >
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--muted)" }}>
            Filter
          </h3>
          <div className="flex items-center gap-2">
            {!usingRawFilter && spec.clauses.length > 1 && (
              <select
                className="select w-auto py-1 text-xs"
                value={spec.clause_logic}
                onChange={(event) =>
                  patch({ clause_logic: event.target.value as "and" | "or" })
                }
              >
                <option value="and">match all (and)</option>
                <option value="or">match any (or)</option>
              </select>
            )}
            <button
              type="button"
              className="btn btn-sm"
              onClick={() =>
                patch({ raw_filter: usingRawFilter ? null : "" })
              }
            >
              {usingRawFilter ? "Use clauses" : "Write $filter by hand"}
            </button>
          </div>
        </div>

        {usingRawFilter ? (
          <textarea
            className="textarea h-20 text-xs"
            value={spec.raw_filter ?? ""}
            placeholder="contains(Name,'S1A') and PublicationDate ge 2024-01-01T00:00:00Z"
            onChange={(event) => patch({ raw_filter: event.target.value })}
          />
        ) : (
          <div className="space-y-2">
            {spec.clauses.map((clause, index) => {
              const unary = OPS.find((op) => op.value === clause.op)?.unary;
              return (
                <div
                  key={index}
                  className="rounded-md border p-2"
                  style={{ borderColor: "var(--border)" }}
                >
                  <div className="flex items-center gap-2">
                    <div className="min-w-0 flex-1">
                      <FieldPicker
                        listId={`clause-fields-${index}`}
                        value={clause.field}
                        entitySet={entitySet}
                        onChange={(field, valueType) =>
                          setClause(index, {
                            field,
                            ...(valueType ? { value_type: valueType } : {}),
                          })
                        }
                      />
                    </div>
                    <button
                      type="button"
                      className="btn btn-sm btn-danger shrink-0"
                      onClick={() =>
                        patch({ clauses: spec.clauses.filter((_, i) => i !== index) })
                      }
                      aria-label="Remove condition"
                    >
                      ✕
                    </button>
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <select
                      className="select w-[8.5rem] shrink-0 px-1.5 text-xs"
                      value={clause.op}
                      onChange={(event) =>
                        setClause(index, { op: event.target.value as ClauseOp })
                      }
                    >
                      {OPS.map((op) => (
                        <option key={op.value} value={op.value}>
                          {op.label}
                        </option>
                      ))}
                    </select>
                    {!unary && (
                      <>
                        <input
                          className="input mono min-w-0 flex-1"
                          value={String(clause.value ?? "")}
                          placeholder="value"
                          onChange={(event) => setClause(index, { value: event.target.value })}
                        />
                        <select
                          className="select w-[6.5rem] shrink-0 px-1.5 text-xs"
                          value={clause.value_type}
                          onChange={(event) =>
                            setClause(index, { value_type: event.target.value as ValueType })
                          }
                        >
                          {VALUE_TYPES.map((type) => (
                            <option key={type} value={type}>
                              {type}
                            </option>
                          ))}
                        </select>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
            <button type="button" className="btn btn-sm" onClick={addClause}>
              + Add condition
            </button>
          </div>
        )}
      </fieldset>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="$select" hint="Comma-separated. Empty returns every property.">
          <input
            className="input mono"
            value={spec.select.join(",")}
            placeholder="Id,Name,PublicationDate"
            onChange={(event) =>
              patch({
                select: event.target.value.split(",").map((s) => s.trim()).filter(Boolean),
              })
            }
          />
        </Field>
        <Field label="$expand" hint="Navigation properties to inline.">
          <input
            className="input mono"
            value={spec.expand.join(",")}
            placeholder="Attributes"
            onChange={(event) =>
              patch({
                expand: event.target.value.split(",").map((s) => s.trim()).filter(Boolean),
              })
            }
          />
        </Field>
      </div>

      <div>
        <label className="label">$orderby</label>
        <div className="space-y-2">
          {spec.orderby.map((order, index) => (
            <div key={index} className="flex items-center gap-2">
              <div className="min-w-[9rem] flex-1">
                <FieldPicker
                  listId={`order-fields-${index}`}
                  value={order.field}
                  entitySet={entitySet}
                  onChange={(field) =>
                    patch({
                      orderby: spec.orderby.map((item, position) =>
                        position === index ? { ...item, field } : item,
                      ),
                    })
                  }
                />
              </div>
              <select
                className="select w-auto"
                value={order.direction}
                onChange={(event) =>
                  patch({
                    orderby: spec.orderby.map((item, position) =>
                      position === index
                        ? { ...item, direction: event.target.value as "asc" | "desc" }
                        : item,
                    ),
                  })
                }
              >
                <option value="asc">ascending</option>
                <option value="desc">descending</option>
              </select>
              <button
                type="button"
                className="btn btn-sm btn-danger"
                onClick={() =>
                  patch({ orderby: spec.orderby.filter((_, i) => i !== index) })
                }
                aria-label="Remove sort"
              >
                ✕
              </button>
            </div>
          ))}
          <button
            type="button"
            className="btn btn-sm"
            onClick={() =>
              patch({ orderby: [...spec.orderby, { field: "", direction: "asc" }] })
            }
          >
            + Add sort
          </button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="$top">
          <input
            className="input"
            type="number"
            min={1}
            value={spec.top ?? ""}
            onChange={(event) =>
              patch({ top: event.target.value ? Number(event.target.value) : null })
            }
          />
        </Field>
        <Field label="$skip">
          <input
            className="input"
            type="number"
            min={0}
            value={spec.skip ?? ""}
            onChange={(event) =>
              patch({ skip: event.target.value ? Number(event.target.value) : null })
            }
          />
        </Field>
        <div className="flex items-end pb-1.5">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={spec.count}
              onChange={(event) => patch({ count: event.target.checked })}
            />
            Ask for total count
          </label>
        </div>
      </div>

      <Field
        label="Custom suffix"
        hint="Appended to the query string verbatim, for options this form does not cover."
      >
        <input
          className="input mono"
          value={spec.custom_suffix}
          placeholder="&$format=json"
          onChange={(event) => patch({ custom_suffix: event.target.value })}
        />
      </Field>
    </div>
  );
}
