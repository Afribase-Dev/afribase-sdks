import crossFetch from 'cross-fetch';

const _fetch = typeof globalThis !== 'undefined' && globalThis.fetch ? globalThis.fetch : crossFetch;

export interface FetchOptions {
  method?: string;
  headers?: Record<string, string>;
  body?: any;
}

export async function resolveFetch(customFetch?: typeof fetch): Promise<typeof fetch> {
  if (customFetch) return customFetch;
  return _fetch as typeof fetch;
}

export async function fetchWithAuth(
  url: string,
  options: FetchOptions & { apiKey: string; accessToken?: string | null; customFetch?: typeof fetch },
): Promise<Response> {
  const fetchFn = await resolveFetch(options.customFetch);
  const headers: Record<string, string> = {
    'apikey': options.apiKey,
    ...options.headers,
  };

  if (options.accessToken) {
    headers['Authorization'] = `Bearer ${options.accessToken}`;
  } else {
    headers['Authorization'] = `Bearer ${options.apiKey}`;
  }

  return fetchFn(url, {
    method: options.method || 'GET',
    headers,
    body: options.body,
  });
}

export async function handleResponse<T = any>(response: Response): Promise<{ data: T | null; error: any }> {
  if (!response.ok) {
    let errorBody: any;
    try {
      // Read body as text first — can only consume once
      const text = await response.text();
      try {
        errorBody = JSON.parse(text);
      } catch {
        errorBody = { message: text || `Request failed with status ${response.status}` };
      }
    } catch {
      errorBody = { message: `Request failed with status ${response.status}` };
    }
    return {
      data: null,
      error: {
        message: errorBody.message || errorBody.msg || `Request failed with status ${response.status}`,
        status: response.status,
        ...errorBody,
      },
    };
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return { data: null as any, error: null };
  }

  try {
    const text = await response.text();
    if (!text) return { data: null as any, error: null };
    const data = JSON.parse(text);
    return { data, error: null };
  } catch {
    return { data: null, error: null };
  }
}
