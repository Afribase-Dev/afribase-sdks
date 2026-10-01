import type { AfribaseQueryBuilder } from './AfribaseQueryBuilder';

/**
 * Functional-Fluent Query Operations for Afribase.
 * This enables tree-shakable, modular query building.
 */

export type QueryOp<T = any> = (builder: AfribaseQueryBuilder<T>) => AfribaseQueryBuilder<T>;

/**
 * The 'db' orchestrator allows piping multiple operations.
 */
export async function db<T = any>(
    builder: AfribaseQueryBuilder<T>,
    ...ops: QueryOp<T>[]
): Promise<any> {
    let current = builder;
    for (const op of ops) {
        current = op(current);
    }
    return current; // It's a PromiseLike
}

// ─── Operations ─────────────────────────────────────────────────────────────

export const select = (columns: string = '*', options?: { count?: 'exact' | 'planned' | 'estimated'; head?: boolean }): QueryOp =>
    (b) => b.select(columns, options);

export const insert = <T>(values: Partial<T> | Partial<T>[], options?: { count?: 'exact' | 'planned' | 'estimated'; defaultToNull?: boolean }): QueryOp<T> =>
    (b) => b.insert(values, options);

export const update = <T>(values: Partial<T>, options?: { count?: 'exact' | 'planned' | 'estimated' }): QueryOp<T> =>
    (b) => b.update(values, options);

export const upsert = <T>(values: Partial<T> | Partial<T>[], options?: { onConflict?: string; ignoreDuplicates?: boolean; count?: 'exact' | 'planned' | 'estimated'; defaultToNull?: boolean }): QueryOp<T> =>
    (b) => b.upsert(values, options);

export const del = (options?: { count?: 'exact' | 'planned' | 'estimated' }): QueryOp =>
    (b) => b.delete(options);

// ─── Filters ────────────────────────────────────────────────────────────────

export const eq = (column: string, value: any): QueryOp => (b) => b.eq(column, value);
export const neq = (column: string, value: any): QueryOp => (b) => b.neq(column, value);
export const gt = (column: string, value: any): QueryOp => (b) => b.gt(column, value);
export const gte = (column: string, value: any): QueryOp => (b) => b.gte(column, value);
export const lt = (column: string, value: any): QueryOp => (b) => b.lt(column, value);
export const lte = (column: string, value: any): QueryOp => (b) => b.lte(column, value);
export const like = (column: string, pattern: string): QueryOp => (b) => b.like(column, pattern);
export const ilike = (column: string, pattern: string): QueryOp => (b) => b.ilike(column, pattern);
export const is = (column: string, value: 'null' | 'true' | 'false' | null | boolean): QueryOp => (b) => b.is(column, value);
export const isIn = (column: string, values: any[]): QueryOp => (b) => b.in(column, values);
export const contains = (column: string, value: any): QueryOp => (b) => b.contains(column, value);
export const containedBy = (column: string, value: any): QueryOp => (b) => b.containedBy(column, value);
export const textSearch = (column: string, query: string, options?: { type?: 'plain' | 'phrase' | 'websearch'; config?: string }): QueryOp =>
    (b) => b.textSearch(column, query, options);

export const not = (column: string, operator: string, value: any): QueryOp => (b) => b.not(column, operator, value);
export const or = (filters: string, options?: { foreignTable?: string }): QueryOp => (b) => b.or(filters, options);
export const match = (query: Record<string, any>): QueryOp => (b) => b.match(query);

// ─── Modifiers ──────────────────────────────────────────────────────────────

export const order = (column: string, options?: { ascending?: boolean; nullsFirst?: boolean; foreignTable?: string }): QueryOp =>
    (b) => b.order(column, options);

export const limit = (count: number, options?: { foreignTable?: string }): QueryOp =>
    (b) => b.limit(count, options);

export const range = (from: number, to: number, options?: { foreignTable?: string }): QueryOp =>
    (b) => b.range(from, to, options);

export const single = (): QueryOp => (b) => b.single();
export const maybeSingle = (): QueryOp => (b) => b.maybeSingle();
export const csv = (): QueryOp => (b) => b.csv();
export const geojson = (): QueryOp => (b) => b.geojson();
export const explain = (options?: { analyze?: boolean; verbose?: boolean; settings?: boolean; buffers?: boolean; format?: 'json' | 'text' }): QueryOp =>
    (b) => b.explain(options);
