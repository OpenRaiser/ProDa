/**
 * Stable row identity for editable tables.
 *
 * Why: using array index as the React key means deleting or adding rows
 * changes the keys of everything that follows, remounting inputs mid-edit
 * and losing focus. We tag every row with a `__rid__` string when it
 * enters the UI; the tag survives object spreads and round-trips through
 * our table component, then gets stripped before persistence.
 */

let _counter = 0;

export function makeRid(): string {
  _counter += 1;
  return `rid-${Date.now().toString(36)}-${_counter.toString(36)}`;
}

export type RowWithRid<T> = T & { __rid__: string };

export function withRid<T extends Record<string, unknown>>(
  rows: readonly T[] | undefined | null
): RowWithRid<T>[] {
  if (!rows) return [];
  return rows.map((r) => {
    if (r && typeof r === "object" && "__rid__" in r) {
      return r as RowWithRid<T>;
    }
    return { ...(r as object), __rid__: makeRid() } as RowWithRid<T>;
  });
}

export function stripRid<T extends Record<string, unknown>>(
  rows: readonly T[]
): Omit<T, "__rid__">[] {
  return rows.map((r) => {
    if (!r || typeof r !== "object") return r as Omit<T, "__rid__">;
    const copy = { ...(r as object) } as Record<string, unknown>;
    delete copy.__rid__;
    return copy as Omit<T, "__rid__">;
  });
}

function getRid(row: unknown): string | undefined {
  if (row && typeof row === "object" && "__rid__" in row) {
    const v = (row as Record<string, unknown>).__rid__;
    return typeof v === "string" ? v : undefined;
  }
  return undefined;
}

/**
 * Reconcile an edit to a filtered subset back into the full list while
 * preserving the original order. Handles edits (by matching `__rid__`),
 * deletions (rows missing from `nextFiltered`), and additions (new rows
 * in `nextFiltered` that weren't in `prevFiltered`). Non-filtered rows
 * stay untouched.
 */
export function reconcileFiltered<T extends Record<string, unknown>>(
  originals: readonly T[],
  prevFiltered: readonly T[],
  nextFiltered: readonly T[]
): T[] {
  const prevKeys = new Set<string>();
  for (const r of prevFiltered) {
    const k = getRid(r);
    if (k) prevKeys.add(k);
  }
  const nextByKey = new Map<string, T>();
  const orphanNext: T[] = [];
  for (const r of nextFiltered) {
    const k = getRid(r);
    if (k) nextByKey.set(k, r);
    else orphanNext.push(r); // rows without a rid → treat as brand-new additions
  }

  const result: T[] = [];
  for (const row of originals) {
    const key = getRid(row);
    if (key && prevKeys.has(key)) {
      const updated = nextByKey.get(key);
      if (updated !== undefined) {
        result.push(updated);
        nextByKey.delete(key);
      }
      // else: deleted
    } else {
      result.push(row);
    }
  }
  // Append leftover new rows (preserved in nextFiltered insertion order)
  for (const r of nextFiltered) {
    const k = getRid(r);
    if (k && nextByKey.has(k)) {
      result.push(nextByKey.get(k)!);
      nextByKey.delete(k);
    }
  }
  for (const r of orphanNext) result.push(r);
  return result;
}
