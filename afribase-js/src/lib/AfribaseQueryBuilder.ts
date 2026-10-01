import { fetchWithAuth, handleResponse } from './fetch';
import type { PostgrestResponse, PostgrestSingleResponse } from './types';

/**
 * AfribaseQueryBuilder — a PostgREST-compatible query builder with
 * full filter/modifier support matching the supabase-js API.
 */
export class AfribaseQueryBuilder<T = any> {
  private _url: string;
  private _apiKey: string;
  private _accessToken: string | null;
  private _customFetch?: typeof fetch;

  private _query: URLSearchParams;
  private _headers: Record<string, string>;
  private _method: string | null = null;
  private _body: any = undefined;
  private _isSingle = false;
  private _isMaybeSingle = false;
  private _isHead = false;
  private _countType: 'exact' | 'planned' | 'estimated' | null = null;

  constructor(
    url: string,
    options: {
      apiKey: string;
      accessToken: string | null;
      customFetch?: typeof fetch;
    },
  ) {
    this._url = url;
    this._apiKey = options.apiKey;
    this._accessToken = options.accessToken;
    this._customFetch = options.customFetch;
    this._query = new URLSearchParams();
    this._headers = {
      'Content-Type': 'application/json',
      'Prefer': 'return=representation',
    };
  }

  // ─────────────────────────────────────────────────────────────────────
  // CRUD Operations
  // ─────────────────────────────────────────────────────────────────────

  /**
   * Perform a SELECT query.
   */
  select(columns: string = '*', options?: { count?: 'exact' | 'planned' | 'estimated'; head?: boolean }): this {
    this._method = 'GET';
    this._query.set('select', columns);
    if (options?.count) {
      this._countType = options.count;
      this._headers['Prefer'] = `count=${options.count}`;
    }
    if (options?.head) {
      this._isHead = true;
      this._method = 'HEAD';
    }
    return this;
  }

  /**
   * Perform an INSERT.
   */
  insert(values: Partial<T> | Partial<T>[], options?: { count?: 'exact' | 'planned' | 'estimated'; defaultToNull?: boolean }): this {
    this._method = 'POST';
    this._body = values;
    const prefer = ['return=representation'];
    if (options?.count) {
      this._countType = options.count;
      prefer.push(`count=${options.count}`);
    }
    if (options?.defaultToNull === false) prefer.push('missing=default');
    this._headers['Prefer'] = prefer.join(',');
    return this;
  }

  /**
   * Perform an UPSERT (insert or update on conflict).
   */
  upsert(values: Partial<T> | Partial<T>[], options?: {
    onConflict?: string;
    ignoreDuplicates?: boolean;
    count?: 'exact' | 'planned' | 'estimated';
    defaultToNull?: boolean;
  }): this {
    this._method = 'POST';
    this._body = values;
    const prefer = ['return=representation', 'resolution=merge-duplicates'];
    if (options?.ignoreDuplicates) {
      prefer[1] = 'resolution=ignore-duplicates';
    }
    if (options?.count) {
      this._countType = options.count;
      prefer.push(`count=${options.count}`);
    }
    if (options?.defaultToNull === false) prefer.push('missing=default');
    if (options?.onConflict) this._query.set('on_conflict', options.onConflict);
    this._headers['Prefer'] = prefer.join(',');
    return this;
  }

  /**
   * Perform an UPDATE (must be combined with filters).
   */
  update(values: Partial<T>, options?: { count?: 'exact' | 'planned' | 'estimated' }): this {
    this._method = 'PATCH';
    this._body = values;
    const prefer = ['return=representation'];
    if (options?.count) {
      this._countType = options.count;
      prefer.push(`count=${options.count}`);
    }
    this._headers['Prefer'] = prefer.join(',');
    return this;
  }

  /**
   * Perform a DELETE (must be combined with filters).
   */
  delete(options?: { count?: 'exact' | 'planned' | 'estimated' }): this {
    this._method = 'DELETE';
    const prefer = ['return=representation'];
    if (options?.count) {
      this._countType = options.count;
      prefer.push(`count=${options.count}`);
    }
    this._headers['Prefer'] = prefer.join(',');
    return this;
  }

  // ─────────────────────────────────────────────────────────────────────
  // Filters
  // ─────────────────────────────────────────────────────────────────────

  eq(column: string, value: any): this {
    this._query.append(column, `eq.${value}`);
    return this;
  }

  neq(column: string, value: any): this {
    this._query.append(column, `neq.${value}`);
    return this;
  }

  gt(column: string, value: any): this {
    this._query.append(column, `gt.${value}`);
    return this;
  }

  gte(column: string, value: any): this {
    this._query.append(column, `gte.${value}`);
    return this;
  }

  lt(column: string, value: any): this {
    this._query.append(column, `lt.${value}`);
    return this;
  }

  lte(column: string, value: any): this {
    this._query.append(column, `lte.${value}`);
    return this;
  }

  like(column: string, pattern: string): this {
    this._query.append(column, `like.${pattern}`);
    return this;
  }

  ilike(column: string, pattern: string): this {
    this._query.append(column, `ilike.${pattern}`);
    return this;
  }

  is(column: string, value: 'null' | 'true' | 'false' | null | boolean): this {
    this._query.append(column, `is.${value}`);
    return this;
  }

  in(column: string, values: any[]): this {
    const cleanedValues = values.map((v) =>
      typeof v === 'string' ? `"${v}"` : v,
    );
    this._query.append(column, `in.(${cleanedValues.join(',')})`);
    return this;
  }

  contains(column: string, value: any): this {
    if (Array.isArray(value)) {
      this._query.append(column, `cs.{${value.join(',')}}`);
    } else if (typeof value === 'object') {
      this._query.append(column, `cs.${JSON.stringify(value)}`);
    } else {
      this._query.append(column, `cs.${value}`);
    }
    return this;
  }

  containedBy(column: string, value: any): this {
    if (Array.isArray(value)) {
      this._query.append(column, `cd.{${value.join(',')}}`);
    } else if (typeof value === 'object') {
      this._query.append(column, `cd.${JSON.stringify(value)}`);
    } else {
      this._query.append(column, `cd.${value}`);
    }
    return this;
  }

  /**
   * Full text search using to_tsquery.
   */
  textSearch(column: string, query: string, options?: { type?: 'plain' | 'phrase' | 'websearch'; config?: string }): this {
    let op = 'fts';
    if (options?.type === 'plain') op = 'plfts';
    else if (options?.type === 'phrase') op = 'phfts';
    else if (options?.type === 'websearch') op = 'wfts';
    const configStr = options?.config ? `(${options.config})` : '';
    this._query.append(column, `${op}${configStr}.${query}`);
    return this;
  }

  /**
   * Negate a filter.
   */
  not(column: string, operator: string, value: any): this {
    this._query.append(column, `not.${operator}.${value}`);
    return this;
  }

  /**
   * Combine filters with OR.
   */
  or(filters: string, options?: { foreignTable?: string }): this {
    const key = options?.foreignTable ? `${options.foreignTable}.or` : 'or';
    this._query.append(key, `(${filters})`);
    return this;
  }

  /**
   * Generic filter — any PostgREST operator.
   */
  filter(column: string, operator: string, value: any): this {
    this._query.append(column, `${operator}.${value}`);
    return this;
  }

  /**
   * Match multiple column values (shorthand for multiple .eq).
   */
  match(query: Record<string, any>): this {
    for (const [key, value] of Object.entries(query)) {
      this._query.append(key, `eq.${value}`);
    }
    return this;
  }

  // ─────────────────────────────────────────────────────────────────────
  // Modifiers
  // ─────────────────────────────────────────────────────────────────────

  /**
   * Order results.
   */
  order(column: string, options?: { ascending?: boolean; nullsFirst?: boolean; foreignTable?: string }): this {
    const direction = options?.ascending === false ? 'desc' : 'asc';
    const nulls = options?.nullsFirst ? '.nullsfirst' : '.nullslast';
    const key = options?.foreignTable ? `${options.foreignTable}.order` : 'order';
    this._query.append(key, `${column}.${direction}${nulls}`);
    return this;
  }

  /**
   * Limit the number of results.
   */
  limit(count: number, options?: { foreignTable?: string }): this {
    const key = options?.foreignTable ? `${options.foreignTable}.limit` : 'limit';
    this._query.set(key, String(count));
    return this;
  }

  /**
   * Paginate with offset.
   */
  range(from: number, to: number, options?: { foreignTable?: string }): this {
    const key = options?.foreignTable ? `${options.foreignTable}.offset` : 'offset';
    this._query.set(key, String(from));
    const limitKey = options?.foreignTable ? `${options.foreignTable}.limit` : 'limit';
    this._query.set(limitKey, String(to - from + 1));
    this._headers['Range'] = `${from}-${to}`;
    this._headers['Range-Unit'] = 'items';
    return this;
  }

  /**
   * Return a single row (throws if 0 or 2+ rows).
   */
  single(): this {
    this._isSingle = true;
    this._headers['Accept'] = 'application/vnd.pgrst.object+json';
    return this;
  }

  /**
   * Return at most one row (returns null if 0 rows).
   */
  maybeSingle(): this {
    this._isMaybeSingle = true;
    this._headers['Accept'] = 'application/vnd.pgrst.object+json';
    return this;
  }

  /**
   * Return as CSV.
   */
  csv(): this {
    this._headers['Accept'] = 'text/csv';
    return this;
  }

  /**
   * Return a GeoJSON response.
   */
  geojson(): this {
    this._headers['Accept'] = 'application/geo+json';
    return this;
  }

  /**
   * Limit the fields returned (PostgREST explain).
   */
  explain(options?: { analyze?: boolean; verbose?: boolean; settings?: boolean; buffers?: boolean; format?: 'json' | 'text' }): this {
    const parts = ['application/vnd.pgrst.plan'];
    if (options?.analyze) parts.push('analyze');
    if (options?.verbose) parts.push('verbose');
    if (options?.settings) parts.push('settings');
    if (options?.buffers) parts.push('buffers');
    if (options?.format) parts.push(options.format);
    this._headers['Accept'] = parts.join('+');
    return this;
  }

  // ─────────────────────────────────────────────────────────────────────
  // Execute
  // ─────────────────────────────────────────────────────────────────────

  /**
   * Execute the query and return the results.
   */
  async then<TResult1 = PostgrestResponse<T[]>, TResult2 = never>(
    onfulfilled?: ((value: PostgrestResponse<T[]>) => TResult1 | PromiseLike<TResult1>) | undefined | null,
    onrejected?: ((reason: any) => TResult2 | PromiseLike<TResult2>) | undefined | null,
  ): Promise<TResult1 | TResult2> {
    let res: PostgrestResponse<T[]>;
    try {
      res = await this._execute();
    } catch (err) {
      if (onrejected) return Promise.resolve(onrejected(err));
      throw err;
    }
    if (onfulfilled) return Promise.resolve(onfulfilled(res));
    return res as any;
  }

  private async _execute(): Promise<PostgrestResponse<any>> {
    const method = this._method || 'GET';
    const queryString = this._query.toString();
    const requestUrl = queryString ? `${this._url}?${queryString}` : this._url;

    const resp = await fetchWithAuth(requestUrl, {
      method,
      headers: this._headers,
      body: this._body ? JSON.stringify(this._body) : undefined,
      apiKey: this._apiKey,
      accessToken: this._accessToken,
      customFetch: this._customFetch,
    });

    // Parse count from Content-Range header
    let count: number | null = null;
    if (this._countType) {
      const contentRange = resp.headers.get('content-range');
      if (contentRange) {
        const match = contentRange.match(/\/(\d+)/);
        if (match) count = parseInt(match[1], 10);
      }
    }

    if (!resp.ok) {
      let errorBody: any;
      try {
        const text = await resp.text();
        try {
          errorBody = JSON.parse(text);
        } catch {
          errorBody = { message: text || `Request failed with status ${resp.status}` };
        }
      } catch {
        errorBody = { message: `Request failed with status ${resp.status}` };
      }
      return {
        data: null,
        error: {
          message: errorBody.message || `Request failed with status ${resp.status}`,
          details: errorBody.details || '',
          hint: errorBody.hint || '',
          code: errorBody.code || String(resp.status),
        },
        count,
        status: resp.status,
        statusText: resp.statusText,
      };
    }

    // HEAD request — no body
    if (this._isHead || method === 'HEAD') {
      return { data: null, error: null, count, status: resp.status, statusText: resp.statusText };
    }

    // 204 No Content
    if (resp.status === 204) {
      return { data: null, error: null, count, status: resp.status, statusText: resp.statusText };
    }

    let data: any;
    const contentType = resp.headers.get('content-type') || '';
    if (contentType.includes('text/csv') || contentType.includes('geo+json') || contentType.includes('pgrst.plan')) {
      data = await resp.text();
    } else {
      data = await resp.json();
    }

    // Handle maybeSingle — if result is 406 (0 rows with object accept), return null
    if (this._isMaybeSingle && (resp.status === 406 || data === null)) {
      return { data: null, error: null, count, status: 200, statusText: 'OK' };
    }

    return { data, error: null, count, status: resp.status, statusText: resp.statusText };
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// RPC Builder
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Call a Postgres function (RPC).
 */
export class AfribaseRpcBuilder<T = any> {
  private _url: string;
  private _apiKey: string;
  private _accessToken: string | null;
  private _customFetch?: typeof fetch;
  private _params: Record<string, any>;
  private _query: URLSearchParams;
  private _headers: Record<string, string>;
  private _isSingle = false;
  private _countType: 'exact' | 'planned' | 'estimated' | null = null;
  private _method: 'GET' | 'POST';

  constructor(
    url: string,
    fnName: string,
    params: Record<string, any>,
    options: {
      apiKey: string;
      accessToken: string | null;
      customFetch?: typeof fetch;
      head?: boolean;
      count?: 'exact' | 'planned' | 'estimated';
      get?: boolean;
    },
  ) {
    this._url = `${url}/rpc/${fnName}`;
    this._apiKey = options.apiKey;
    this._accessToken = options.accessToken;
    this._customFetch = options.customFetch;
    this._params = params;
    this._query = new URLSearchParams();
    this._headers = {
      'Content-Type': 'application/json',
      'Prefer': 'return=representation',
    };
    this._method = options.get ? 'GET' : 'POST';

    if (options.count) {
      this._countType = options.count;
      this._headers['Prefer'] = `count=${options.count}`;
    }

    // For GET, pass params as query string
    if (this._method === 'GET' && params) {
      for (const [key, value] of Object.entries(params)) {
        this._query.set(key, String(value));
      }
    }
  }

  single(): this {
    this._isSingle = true;
    this._headers['Accept'] = 'application/vnd.pgrst.object+json';
    return this;
  }

  maybeSingle(): this {
    this._headers['Accept'] = 'application/vnd.pgrst.object+json';
    return this;
  }

  select(columns: string = '*'): this {
    this._query.set('select', columns);
    return this;
  }

  order(column: string, options?: { ascending?: boolean }): this {
    const direction = options?.ascending === false ? 'desc' : 'asc';
    this._query.append('order', `${column}.${direction}`);
    return this;
  }

  limit(count: number): this {
    this._query.set('limit', String(count));
    return this;
  }

  range(from: number, to: number): this {
    this._query.set('offset', String(from));
    this._query.set('limit', String(to - from + 1));
    this._headers['Range'] = `${from}-${to}`;
    this._headers['Range-Unit'] = 'items';
    return this;
  }

  eq(column: string, value: any): this {
    this._query.append(column, `eq.${value}`);
    return this;
  }

  filter(column: string, operator: string, value: any): this {
    this._query.append(column, `${operator}.${value}`);
    return this;
  }

  async then<TResult1 = PostgrestResponse<T>, TResult2 = never>(
    onfulfilled?: ((value: PostgrestResponse<T>) => TResult1 | PromiseLike<TResult1>) | undefined | null,
    onrejected?: ((reason: any) => TResult2 | PromiseLike<TResult2>) | undefined | null,
  ): Promise<TResult1 | TResult2> {
    let res: PostgrestResponse<T>;
    try {
      res = await this._execute();
    } catch (err) {
      if (onrejected) return Promise.resolve(onrejected(err));
      throw err;
    }
    if (onfulfilled) return Promise.resolve(onfulfilled(res));
    return res as any;
  }

  private async _execute(): Promise<PostgrestResponse<any>> {
    const queryString = this._query.toString();
    const requestUrl = queryString ? `${this._url}?${queryString}` : this._url;

    const resp = await fetchWithAuth(requestUrl, {
      method: this._method,
      headers: this._headers,
      body: this._method === 'POST' ? JSON.stringify(this._params) : undefined,
      apiKey: this._apiKey,
      accessToken: this._accessToken,
      customFetch: this._customFetch,
    });

    let count: number | null = null;
    if (this._countType) {
      const contentRange = resp.headers.get('content-range');
      if (contentRange) {
        const match = contentRange.match(/\/(\d+)/);
        if (match) count = parseInt(match[1], 10);
      }
    }

    if (!resp.ok) {
      let errorBody: any;
      try {
        const text = await resp.text();
        try {
          errorBody = JSON.parse(text);
        } catch {
          errorBody = { message: text || `RPC failed with status ${resp.status}` };
        }
      } catch {
        errorBody = { message: `RPC failed with status ${resp.status}` };
      }
      return {
        data: null,
        error: {
          message: errorBody.message || `RPC failed with status ${resp.status}`,
          details: errorBody.details || '',
          hint: errorBody.hint || '',
          code: errorBody.code || String(resp.status),
        },
        count,
        status: resp.status,
        statusText: resp.statusText,
      };
    }

    if (resp.status === 204) {
      return { data: null, error: null, count, status: 204, statusText: 'No Content' };
    }

    const data = await resp.json();
    return { data, error: null, count, status: resp.status, statusText: resp.statusText };
  }
}
