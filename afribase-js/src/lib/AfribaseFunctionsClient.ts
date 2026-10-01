import { fetchWithAuth, handleResponse } from './fetch';
import type { FunctionInvokeOptions } from './types';

/**
 * AfribaseFunctionsClient — invoke Afribase Edge Functions.
 */
export class AfribaseFunctionsClient {
  private url: string;
  private apiKey: string;
  private getAccessToken: () => string | null;
  private customFetch?: typeof fetch;

  constructor(options: {
    url: string;
    apiKey: string;
    getAccessToken: () => string | null;
    customFetch?: typeof fetch;
  }) {
    this.url = options.url.replace(/\/$/, '');
    this.apiKey = options.apiKey;
    this.getAccessToken = options.getAccessToken;
    this.customFetch = options.customFetch;
  }

  /**
   * Invoke an edge function by name.
   *
   * @example
   * const { data, error } = await client.functions.invoke('hello-world', {
   *   body: { name: 'Afribase' },
   * });
   */
  async invoke<T = any>(
    functionName: string,
    options?: FunctionInvokeOptions,
  ): Promise<{ data: T | null; error: any }> {
    const method = options?.method || 'POST';
    const headers: Record<string, string> = {
      ...options?.headers,
    };

    let body: any = undefined;
    if (options?.body !== undefined) {
      if (
        typeof options.body === 'string' ||
        options.body instanceof Blob ||
        options.body instanceof ArrayBuffer ||
        options.body instanceof FormData
      ) {
        body = options.body;
      } else {
        headers['Content-Type'] = headers['Content-Type'] || 'application/json';
        body = JSON.stringify(options.body);
      }
    }

    if (options?.region) {
      headers['x-region'] = options.region;
    }

    const resp = await fetchWithAuth(`${this.url}/${functionName}`, {
      method,
      headers,
      body,
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });

    // Check if the response is JSON or not
    const contentType = resp.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return handleResponse<T>(resp);
    }

    // Non-JSON response — return as text
    if (!resp.ok) {
      const text = await resp.text();
      return {
        data: null,
        error: { message: text, status: resp.status },
      };
    }

    // Return the raw response body as data
    const text = await resp.text();
    return { data: text as any, error: null };
  }
}
