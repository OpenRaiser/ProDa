import { useMemo, useRef } from "react";
import { Plus, Trash2 } from "lucide-react";
import clsx from "clsx";
import { makeRid } from "@/lib/rowKey";

export interface ColumnDef<T> {
  key: keyof T & string;
  title: string;
  readonly?: boolean;
  width?: string;
  type?: "text" | "textarea";
  placeholder?: string;
  renderValue?: (value: unknown, row: T) => string;
  parseValue?: (input: string) => unknown;
}

interface Props<T extends Record<string, unknown>> {
  columns: ColumnDef<T>[];
  rows: T[];
  onChange: (rows: T[]) => void;
  emptyTemplate?: Partial<T>;
  maxHeight?: string;
  rowKey?: (row: T, index: number) => string;
  showIndex?: boolean;
  addLabel?: string;
}

export function EditableTable<T extends Record<string, unknown>>({
  columns,
  rows,
  onChange,
  emptyTemplate,
  maxHeight = "420px",
  rowKey,
  showIndex = true,
  addLabel = "Add Row",
}: Props<T>) {
  const idBase = useRef(Math.random().toString(36).slice(2, 8));

  const getKey = (r: T, i: number) => {
    if (rowKey) return rowKey(r, i);
    const rid = (r as unknown as { __rid__?: string })?.__rid__;
    if (rid) return rid;
    return `${idBase.current}-${i}`;
  };

  const updateCell = (idx: number, key: string, value: string) => {
    const col = columns.find((c) => c.key === key);
    const parsed = col?.parseValue ? col.parseValue(value) : value;
    const next = rows.slice();
    next[idx] = { ...rows[idx], [key]: parsed } as T;
    onChange(next);
  };

  const deleteRow = (idx: number) => {
    const next = rows.slice();
    next.splice(idx, 1);
    onChange(next);
  };

  const addRow = () => {
    const blank: Record<string, unknown> = {
      __rid__: makeRid(),
      ...(emptyTemplate ?? {}),
    };
    for (const c of columns) if (!(c.key in blank)) blank[c.key] = "";
    onChange([...rows, blank as T]);
  };

  const renderValue = (col: ColumnDef<T>, row: T): string => {
    if (col.renderValue) return col.renderValue(row[col.key], row);
    const v = row[col.key];
    if (v === null || v === undefined) return "";
    if (typeof v === "string") return v;
    if (Array.isArray(v)) return v.join("\n");
    return String(v);
  };

  const totalWidthHint = useMemo(() => {
    const fixed = columns.filter((c) => c.width).reduce((s, c) => s + Number.parseFloat(c.width ?? "0"), 0);
    return fixed;
  }, [columns]);

  return (
    <div className="bg-[var(--vs-bg)] border border-[var(--vs-border)] rounded-sm overflow-hidden">
      <div
        className="overflow-auto"
        style={{ maxHeight }}
      >
        <table className="w-full border-collapse text-[12.5px]">
          <thead className="sticky top-0 bg-[var(--vs-panel)] z-10">
            <tr>
              {showIndex && (
                <th className="px-2 py-[6px] text-left text-[11px] uppercase tracking-wider text-[var(--vs-fg-muted)] border-b border-[var(--vs-border)] w-[44px]">
                  #
                </th>
              )}
              {columns.map((c) => (
                <th
                  key={c.key}
                  className="px-2 py-[6px] text-left text-[11px] uppercase tracking-wider text-[var(--vs-fg-muted)] border-b border-[var(--vs-border)] font-semibold"
                  style={c.width ? { width: c.width } : undefined}
                >
                  {c.title}
                  {c.readonly && (
                    <span className="ml-1 text-[10px] text-[var(--vs-fg-subtle)] lowercase tracking-normal">
                      read-only
                    </span>
                  )}
                </th>
              ))}
              <th className="px-1 py-[6px] text-center border-b border-[var(--vs-border)] w-[36px]"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length + 1 + (showIndex ? 1 : 0)}
                  className="text-center text-[var(--vs-fg-muted)] py-8"
                >
                  <span className="italic">No rows</span>
                </td>
              </tr>
            ) : (
              rows.map((row, i) => (
                <tr
                  key={getKey(row, i)}
                  className={clsx(
                    "group border-b border-[var(--vs-panel)]",
                    "hover:bg-[var(--vs-hover)]"
                  )}
                >
                  {showIndex && (
                    <td className="px-2 py-[2px] text-[var(--vs-fg-subtle)] font-mono align-top pt-[6px] select-none">
                      {i + 1}
                    </td>
                  )}
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className="px-[6px] py-[3px] align-top border-r border-[var(--vs-panel)] last:border-r-0"
                      style={c.width ? { width: c.width } : undefined}
                    >
                      {c.type === "textarea" ? (
                        <textarea
                          value={renderValue(c, row)}
                          readOnly={c.readonly}
                          placeholder={c.placeholder}
                          rows={Math.min(
                            8,
                            Math.max(
                              2,
                              renderValue(c, row).split("\n").length
                            )
                          )}
                          onChange={(e) =>
                            updateCell(i, c.key, e.target.value)
                          }
                          className={clsx(
                            "w-full bg-transparent text-[var(--vs-fg)] font-mono leading-[1.45]",
                            "focus:bg-[var(--vs-bg)] focus:outline focus:outline-1 focus:outline-[var(--vs-accent)]",
                            "placeholder:text-[var(--vs-fg-subtle)] resize-y p-[3px] rounded-sm",
                            c.readonly && "text-[var(--vs-fg-muted)]"
                          )}
                        />
                      ) : (
                        <input
                          value={renderValue(c, row)}
                          readOnly={c.readonly}
                          placeholder={c.placeholder}
                          onChange={(e) =>
                            updateCell(i, c.key, e.target.value)
                          }
                          className={clsx(
                            "w-full bg-transparent text-[var(--vs-fg)] font-mono leading-[1.45]",
                            "focus:bg-[var(--vs-bg)] focus:outline focus:outline-1 focus:outline-[var(--vs-accent)]",
                            "placeholder:text-[var(--vs-fg-subtle)] p-[3px] rounded-sm",
                            c.readonly && "text-[var(--vs-fg-muted)]"
                          )}
                        />
                      )}
                    </td>
                  ))}
                  <td className="px-1 py-[3px] align-top pt-[6px] text-center">
                    <button
                      onClick={() => deleteRow(i)}
                      className="p-1 rounded-sm text-[var(--vs-fg-muted)] hover:text-[#f48771] hover:bg-[var(--vs-border)] opacity-0 group-hover:opacity-100"
                      title="Delete row"
                    >
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="px-2 py-[5px] border-t border-[var(--vs-border)] bg-[var(--vs-sidebar)] flex items-center justify-between">
        <span className="text-[11px] text-[var(--vs-fg-muted)]">
          {rows.length} row{rows.length === 1 ? "" : "s"}
          {totalWidthHint > 0 && " · scroll horizontally if clipped"}
        </span>
        <button
          className="flex items-center gap-1 text-[12px] text-[var(--vs-accent)] hover:underline"
          onClick={addRow}
        >
          <Plus size={13} />
          {addLabel}
        </button>
      </div>
    </div>
  );
}
