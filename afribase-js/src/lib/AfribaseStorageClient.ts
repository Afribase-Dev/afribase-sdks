import { fetchWithAuth, handleResponse } from './fetch';
import type {
  CreateSignedUrlResponse,
  SignedUrlOptions,
  StorageBucket,
  StorageObject,
  TransformOptions,
  UploadOptions,
} from './types';

/**
 * AfribaseStorageClient — upload, download, list, and manage files
 * in Afribase Storage buckets.
 */
export class AfribaseStorageClient {
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
   * Get a reference to a specific bucket for file operations.
   */
  from(bucketId: string): StorageFileApi {
    return new StorageFileApi(
      this.url,
      bucketId,
      this.apiKey,
      this.getAccessToken,
      this.customFetch,
    );
  }

  // ─────────────────────────────────────────────────────────────────────
  // Bucket Management
  // ─────────────────────────────────────────────────────────────────────

  /**
   * List all buckets.
   */
  async listBuckets(): Promise<{ data: StorageBucket[] | null; error: any }> {
    const resp = await fetchWithAuth(`${this.url}/bucket`, {
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });
    return handleResponse(resp);
  }

  /**
   * Get a bucket by ID.
   */
  async getBucket(id: string): Promise<{ data: StorageBucket | null; error: any }> {
    const resp = await fetchWithAuth(`${this.url}/bucket/${id}`, {
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });
    return handleResponse(resp);
  }

  /**
   * Create a new bucket.
   */
  async createBucket(id: string, options?: {
    public?: boolean;
    fileSizeLimit?: number;
    allowedMimeTypes?: string[];
  }): Promise<{ data: { name: string } | null; error: any }> {
    const resp = await fetchWithAuth(`${this.url}/bucket`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id,
        name: id,
        public: options?.public ?? false,
        file_size_limit: options?.fileSizeLimit,
        allowed_mime_types: options?.allowedMimeTypes,
      }),
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });
    return handleResponse(resp);
  }

  /**
   * Update a bucket.
   */
  async updateBucket(id: string, options: {
    public?: boolean;
    fileSizeLimit?: number;
    allowedMimeTypes?: string[];
  }): Promise<{ data: { message: string } | null; error: any }> {
    const resp = await fetchWithAuth(`${this.url}/bucket/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        public: options.public,
        file_size_limit: options.fileSizeLimit,
        allowed_mime_types: options.allowedMimeTypes,
      }),
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });
    return handleResponse(resp);
  }

  /**
   * Delete a bucket (must be empty).
   */
  async deleteBucket(id: string): Promise<{ data: { message: string } | null; error: any }> {
    const resp = await fetchWithAuth(`${this.url}/bucket/${id}`, {
      method: 'DELETE',
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });
    return handleResponse(resp);
  }

  /**
   * Empty a bucket (remove all files).
   */
  async emptyBucket(id: string): Promise<{ data: { message: string } | null; error: any }> {
    const resp = await fetchWithAuth(`${this.url}/bucket/${id}/empty`, {
      method: 'POST',
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });
    return handleResponse(resp);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Storage File API — operations on a specific bucket
// ─────────────────────────────────────────────────────────────────────────────

export class StorageFileApi {
  constructor(
    private storageUrl: string,
    private bucketId: string,
    private apiKey: string,
    private getAccessToken: () => string | null,
    private customFetch?: typeof fetch,
  ) {}

  /**
   * Upload a file to the bucket.
   */
  async upload(
    path: string,
    fileBody: Blob | ArrayBuffer | ReadableStream | string | Buffer,
    options?: UploadOptions,
  ): Promise<{ data: { path: string; id?: string; fullPath?: string } | null; error: any }> {
    const contentType = options?.contentType || 'application/octet-stream';
    const headers: Record<string, string> = {
      'Content-Type': contentType,
    };
    if (options?.cacheControl) headers['Cache-Control'] = options.cacheControl;
    if (options?.upsert) headers['x-upsert'] = 'true';

    const resp = await fetchWithAuth(
      `${this.storageUrl}/object/${this.bucketId}/${path}`,
      {
        method: 'POST',
        headers,
        body: fileBody as any,
        apiKey: this.apiKey,
        accessToken: this.getAccessToken(),
        customFetch: this.customFetch,
      },
    );
    const result = await handleResponse<any>(resp);
    if (result.error) return { data: null, error: result.error };
    return {
      data: {
        path,
        id: result.data?.id ?? result.data?.Key,
        fullPath: `${this.bucketId}/${path}`,
      },
      error: null,
    };
  }

  /**
   * Update (replace) an existing file.
   */
  async update(
    path: string,
    fileBody: Blob | ArrayBuffer | ReadableStream | string | Buffer,
    options?: UploadOptions,
  ): Promise<{ data: { path: string; id?: string; fullPath?: string } | null; error: any }> {
    const contentType = options?.contentType || 'application/octet-stream';
    const headers: Record<string, string> = {
      'Content-Type': contentType,
      'x-upsert': 'true',
    };
    if (options?.cacheControl) headers['Cache-Control'] = options.cacheControl;

    const resp = await fetchWithAuth(
      `${this.storageUrl}/object/${this.bucketId}/${path}`,
      {
        method: 'POST',
        headers,
        body: fileBody as any,
        apiKey: this.apiKey,
        accessToken: this.getAccessToken(),
        customFetch: this.customFetch,
      },
    );
    const result = await handleResponse<any>(resp);
    if (result.error) return { data: null, error: result.error };
    return {
      data: {
        path,
        id: result.data?.id ?? result.data?.Key,
        fullPath: `${this.bucketId}/${path}`,
      },
      error: null,
    };
  }

  /**
   * Download a file from the bucket.
   */
  async download(
    path: string,
    options?: { transform?: TransformOptions },
  ): Promise<{ data: Blob | null; error: any }> {
    const params = new URLSearchParams();
    if (options?.transform) {
      if (options.transform.width) params.set('width', String(options.transform.width));
      if (options.transform.height) params.set('height', String(options.transform.height));
      if (options.transform.resize) params.set('resize', options.transform.resize);
      if (options.transform.quality) params.set('quality', String(options.transform.quality));
      if (options.transform.format) params.set('format', options.transform.format);
    }
    const qs = params.toString();
    const url = `${this.storageUrl}/object/${this.bucketId}/${path}${qs ? '?' + qs : ''}`;

    const fetchFn = this.customFetch || (globalThis.fetch ?? (await import('cross-fetch')).default);
    const headers: Record<string, string> = {
      'apikey': this.apiKey,
    };
    const token = this.getAccessToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    else headers['Authorization'] = `Bearer ${this.apiKey}`;

    const resp = await fetchFn(url, { headers });
    if (!resp.ok) {
      let errorBody: any;
      try {
        errorBody = await resp.json();
      } catch {
        errorBody = { message: `Download failed with status ${resp.status}` };
      }
      return { data: null, error: errorBody };
    }

    const blob = await resp.blob();
    return { data: blob, error: null };
  }

  /**
   * List objects in the bucket.
   */
  async list(
    path?: string,
    options?: { limit?: number; offset?: number; sortBy?: { column: string; order: 'asc' | 'desc' } },
  ): Promise<{ data: StorageObject[] | null; error: any }> {
    const body: Record<string, any> = {
      prefix: path || '',
    };
    if (options?.limit) body.limit = options.limit;
    if (options?.offset) body.offset = options.offset;
    if (options?.sortBy) body.sortBy = options.sortBy;

    const resp = await fetchWithAuth(`${this.storageUrl}/object/list/${this.bucketId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });
    return handleResponse(resp);
  }

  /**
   * Move a file to a new path within the same bucket.
   */
  async move(
    fromPath: string,
    toPath: string,
  ): Promise<{ data: { message: string } | null; error: any }> {
    const resp = await fetchWithAuth(`${this.storageUrl}/object/move`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bucketId: this.bucketId,
        sourceKey: fromPath,
        destinationKey: toPath,
      }),
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });
    return handleResponse(resp);
  }

  /**
   * Copy a file to a new path within the same bucket.
   */
  async copy(
    fromPath: string,
    toPath: string,
  ): Promise<{ data: { path: string } | null; error: any }> {
    const resp = await fetchWithAuth(`${this.storageUrl}/object/copy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bucketId: this.bucketId,
        sourceKey: fromPath,
        destinationKey: toPath,
      }),
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });
    return handleResponse(resp);
  }

  /**
   * Remove one or more files from the bucket.
   */
  async remove(paths: string[]): Promise<{ data: StorageObject[] | null; error: any }> {
    const resp = await fetchWithAuth(`${this.storageUrl}/object/${this.bucketId}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prefixes: paths }),
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });
    return handleResponse(resp);
  }

  /**
   * Create a signed URL for temporary access to a private file.
   */
  async createSignedUrl(
    path: string,
    expiresIn: number,
    options?: SignedUrlOptions,
  ): Promise<{ data: CreateSignedUrlResponse | null; error: any }> {
    const body: Record<string, any> = {
      expiresIn,
    };
    if (options?.download) {
      body.download = typeof options.download === 'string' ? options.download : true;
    }
    if (options?.transform) body.transform = options.transform;

    const resp = await fetchWithAuth(`${this.storageUrl}/object/sign/${this.bucketId}/${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });

    const result = await handleResponse<any>(resp);
    if (result.error) return { data: null, error: result.error };

    const signedUrl = result.data?.signedURL || result.data?.signedUrl;
    return {
      data: {
        signedUrl: signedUrl?.startsWith('http')
          ? signedUrl
          : `${this.storageUrl}${signedUrl}`,
        path,
        token: result.data?.token || '',
      },
      error: null,
    };
  }

  /**
   * Create signed URLs for multiple files.
   */
  async createSignedUrls(
    paths: string[],
    expiresIn: number,
  ): Promise<{ data: CreateSignedUrlResponse[] | null; error: any }> {
    const resp = await fetchWithAuth(`${this.storageUrl}/object/sign/${this.bucketId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expiresIn, paths }),
      apiKey: this.apiKey,
      accessToken: this.getAccessToken(),
      customFetch: this.customFetch,
    });

    const result = await handleResponse<any[]>(resp);
    if (result.error) return { data: null, error: result.error };

    const urls = (result.data || []).map((item: any) => ({
      signedUrl: item.signedURL?.startsWith('http')
        ? item.signedURL
        : `${this.storageUrl}${item.signedURL}`,
      path: item.path,
      token: item.token || '',
    }));
    return { data: urls, error: null };
  }

  /**
   * Get the public URL for a file in a public bucket.
   */
  getPublicUrl(
    path: string,
    options?: { download?: string | boolean; transform?: TransformOptions },
  ): { data: { publicUrl: string } } {
    const params = new URLSearchParams();
    if (options?.download) {
      params.set('download', typeof options.download === 'string' ? options.download : '');
    }
    if (options?.transform) {
      if (options.transform.width) params.set('width', String(options.transform.width));
      if (options.transform.height) params.set('height', String(options.transform.height));
      if (options.transform.resize) params.set('resize', options.transform.resize);
      if (options.transform.quality) params.set('quality', String(options.transform.quality));
      if (options.transform.format) params.set('format', options.transform.format);
    }
    const qs = params.toString();
    const publicUrl = `${this.storageUrl}/object/public/${this.bucketId}/${path}${qs ? '?' + qs : ''}`;
    return { data: { publicUrl } };
  }
}
