"use client";

import { useMemo, useState } from "react";
import type { QueryResponse } from "@/lib/types";

function renderCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function ResultsView({
  result,
  onPage,
  pageSize,
  skip,
  onExport,
  exporting,
}: {
  result: QueryResponse;
  onPage?: (nextSkip: number) => void;
  pageSize: number;
  skip: number;
  onExport?: (format: "csv" | "json") => void;
  exporting?: boolean;
}) {
  const [view, setView] = useState<"table" | "json">("table");
  const [sort, setSort] = useState<{ column: string; direction: 1 | -1 } | null>(null);

  const rows = useMemo(() => {
    if (!sort) return result.rows;
    // Sorts the current page only; server-side ordering is $orderby's job.
    return [...result.rows].sort((a, b) => {
      const left = renderCell(a[sort.column]);
      const right = renderCell(b[sort.column]);
      const leftNumber = Number(left);
      const rightNumber = Number(right);
      if (left !== "" && right !== "" && !Number.isNaN(leftNumber) && !Number.isNaN(rightNumber)) {
        return (leftNumber - rightNumber) * sort.direction;
      }
      return left.localeCompare(right) * sort.direction;
    });
  }, [result.rows, sort]);

  const from = skip + 1;
  const to = skip + result.count;

  return (
    <div className="card fade-in">
      <div
        className="flex flex-wrap items-center gap-3 border-b px-3 py-2 text-xs"
        style={{ borderColor: "var(--border)", color: "var(--muted)" }}
      >
        <span>
          <strong style={{ color: "var(--fg)" }}>{result.count}</strong> row
          {result.count === 1 ? "" : "s"}
          {result.count > 0 && ` (${from}–${to})`}
          {result.total_count !== null && ` of ${result.total_count}`}
        </span>
        <span>HTTP {result.status_code}</span>
        <span>{result.duration_ms} ms</span>

        <div className="ml-auto flex items-center gap-2">
          {onExport && (
            <>
              <button
                className="btn btn-sm"
                onClick={() => onExport("csv")}
                disabled={exporting || result.count === 0}
              >
                CSV
              </button>
              <button
                className="btn btn-sm"
                onClick={() => onExport("json")}
                disabled={exporting || result.count === 0}
              >
                JSON
              </button>
            </>
          )}
          <div className="flex overflow-hidden rounded-md border" style={{ borderColor: "var(--border)" }}>
            {(["table", "json"] as const).map((mode) => (
              <button
                key={mode}
                className="px-2 py-1 text-xs capitalize"
                style={{
                  background: view === mode ? "var(--accent)" : "transparent",
                  color: view === mode ? "#fff" : "var(--muted)",
                  transition:
                    "background-color 0.2s var(--ease), color 0.2s var(--ease)",
                }}
                onClick={() => setView(mode)}
              >
                {mode}
              </button>
            ))}
          </div>
        </div>
      </div>

      {result.count === 0 ? (
        <p className="px-3 py-8 text-center text-sm" style={{ color: "var(--muted)" }}>
          The query ran successfully but matched nothing.
        </p>
      ) : view === "json" ? (
        <pre className="mono max-h-[60vh] overflow-auto p-3 text-xs">
          {JSON.stringify(result.rows, null, 2)}
        </pre>
      ) : (
        <div className="max-h-[60vh] overflow-auto">
          <table className="w-full border-collapse text-xs">
            <thead className="sticky top-0 z-10">
              <tr style={{ background: "var(--surface)" }}>
                {result.columns.map((column) => (
                  <th
                    key={column}
                    className="mono cursor-pointer whitespace-nowrap border-b px-2.5 py-2 text-left font-semibold"
                    style={{ borderColor: "var(--border)" }}
                    onClick={() =>
                      setSort((current) =>
                        current?.column === column
                          ? { column, direction: current.direction === 1 ? -1 : 1 }
                          : { column, direction: 1 },
                      )
                    }
                  >
                    {column}
                    {sort?.column === column ? (sort.direction === 1 ? " ▲" : " ▼") : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index} className="row-hover align-top">
                  {result.columns.map((column) => {
                    const text = renderCell(row[column]);
                    return (
                      <td
                        key={column}
                        className="mono max-w-[28rem] truncate border-b px-2.5 py-1.5"
                        style={{ borderColor: "var(--border)" }}
                        title={text}
                      >
                        {text}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {onPage && (
        <div
          className="flex items-center justify-between border-t px-3 py-2 text-xs"
          style={{ borderColor: "var(--border)", color: "var(--muted)" }}
        >
          <button
            className="btn btn-sm"
            disabled={skip <= 0}
            onClick={() => onPage(Math.max(0, skip - pageSize))}
          >
            ← Previous
          </button>
          <span>
            Page {Math.floor(skip / Math.max(pageSize, 1)) + 1}
          </span>
          <button
            className="btn btn-sm"
            disabled={result.count < pageSize && !result.has_next}
            onClick={() => onPage(skip + pageSize)}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
