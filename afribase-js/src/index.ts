import { AfribaseAuthClient } from './lib/AfribaseAuthClient';
import { AfribaseRealtimeClient, RealtimeChannel } from './lib/AfribaseRealtimeClient';
import { AfribaseStorageClient } from './lib/AfribaseStorageClient';
import { AfribaseFunctionsClient } from './lib/AfribaseFunctionsClient';
import { AfribaseEmailClient } from './lib/AfribaseEmailClient';
import { AfribaseQueryBuilder, AfribaseRpcBuilder } from './lib/AfribaseQueryBuilder';
import type { AfribaseClientOptions, RealtimeChannelOptions } from './lib/types';

/** Extract the project slug from a full project URL for use in the email API path. */
function extractSlug(url: string): string {
  try {
    const u = new URL(url);
    // Path-based: /p/:slug/...
    const pathMatch = u.pathname.match(/^\/p\/([^/]+)/);
    if (pathMatch) return pathMatch[1];
    // Subdomain: slug.useafribase.app
    const parts = u.hostname.split('.');
    if (parts.length >= 3) return parts[0];
  } catch { /* ignore */ }
  // Fallback: relay on middleware subdomain resolution
  return '_';
}

// ─────────────────────────────────────────────────────────────────────────────
// Re-export all types
// ─────────────────────────────────────────────────────────────────────────────
export type {
  AfribaseClientOptions,
  Session,
  User,
  UserIdentity,
  Factor,
  SignUpCredentials,
  SignInWithPasswordCredentials,
  SignInWithOAuthCredentials,
  SignInWithOtpCredentials,
  VerifyOtpParams,
  ResetPasswordCredentials,
  UserAttributes,
  OAuthProvider,
  AuthChangeEvent,
  AuthChangeCallback,
  Subscription,
  RealtimeChannelEvent,
  RealtimePostgresChangesPayload,
  RealtimePresenceState,
  PresenceEntry,
  RealtimeListenTypes,
  RealtimeChannelOptions,
  StorageBucket,
  StorageObject,
  UploadOptions,
  TransformOptions,
  SignedUrlOptions,
  CreateSignedUrlResponse,
  FunctionInvokeOptions,
  FunctionInvokeResponse,
  FilterOperator,
  PostgrestError,
  PostgrestResponse,
  PostgrestSingleResponse,
} from './lib/types';
export type { SendEmailOptions, EmailTemplate } from './lib/AfribaseEmailClient';

export { AfribaseAuthClient } from './lib/AfribaseAuthClient';
export { AfribaseRealtimeClient, RealtimeChannel } from './lib/AfribaseRealtimeClient';
export { AfribaseStorageClient, StorageFileApi } from './lib/AfribaseStorageClient';
export { AfribaseFunctionsClient } from './lib/AfribaseFunctionsClient';
export { AfribaseEmailClient } from './lib/AfribaseEmailClient';
export { AfribaseQueryBuilder, AfribaseRpcBuilder } from './lib/AfribaseQueryBuilder';
export * from './lib/modular';

// ─────────────────────────────────────────────────────────────────────────────
// Main Client
// ─────────────────────────────────────────────────────────────────────────────

/**
 * The main Afribase client. Provides access to Auth, Database, Realtime,
 * Storage, and Edge Functions — matching the supabase-js API surface.
 *
 * @example
 * ```ts
 * import { createClient } from '@afribase/afribase-js';
 *
 * const afribase = createClient('https://your-project.useafribase.app', 'your-anon-key');
 *
 * // Auth
 * const { data } = await afribase.auth.signInWithPassword({ email: '...', password: '...' });
 *
 * // Database
 * const { data: rows } = await afribase.from('posts').select('*').eq('published', true);
 *
 * // Realtime
 * afribase.channel('room1')
 *   .on('broadcast', { event: 'message' }, (payload) => console.log(payload))
 *   .subscribe();
 *
 * // Storage
 * const { data: url } = afribase.storage.from('avatars').getPublicUrl('avatar.png');
 *
 * // Functions
 * const { data: result } = await afribase.functions.invoke('my-function', { body: { foo: 'bar' } });
 *
 * // RPC
 * const { data: total } = await afribase.rpc('get_total_count', { table_name: 'users' });
 * ```
 */
export class AfribaseClient {
  /**
   * The auth client for authentication and user management.
   */
  readonly auth: AfribaseAuthClient;

  /**
   * The storage client for file uploads, downloads, and bucket management.
   */
  readonly storage: AfribaseStorageClient;

  /**
   * The functions client for invoking Afribase Edge Functions.
   */
  readonly functions: AfribaseFunctionsClient;

  /**
   * The email client for sending transactional emails using your configured SMTP.
   */
  readonly email: AfribaseEmailClient;

  private readonly realtimeClient: AfribaseRealtimeClient;
  private readonly baseUrl: string;
  private readonly anonKey: string;
  private readonly restUrl: string;
  private readonly customFetch?: typeof fetch;

  constructor(baseUrl: string, anonKey: string, options?: Partial<AfribaseClientOptions>) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.anonKey = anonKey;
    this.customFetch = options?.fetch;

    const authUrl = options?.authUrl || `${this.baseUrl}/auth/v1`;
    this.restUrl = options?.restUrl || `${this.baseUrl}/rest/v1`;
    const realtimeUrl = options?.realtimeUrl || this.baseUrl;
    const storageUrl = options?.storageUrl || `${this.baseUrl}/storage/v1`;
    const functionsUrl = options?.functionsUrl || `${this.baseUrl}/functions/v1`;

    // Initialize Auth
    this.auth = new AfribaseAuthClient({
      url: authUrl,
      apiKey: anonKey,
      autoRefreshToken: options?.autoRefreshToken ?? true,
      persistSession: options?.persistSession ?? true,
      customFetch: this.customFetch,
    });

    // Initialize Realtime
    this.realtimeClient = new AfribaseRealtimeClient({
      url: realtimeUrl,
      apiKey: anonKey,
      accessToken: this.auth.accessToken,
    });

    // Initialize Storage
    this.storage = new AfribaseStorageClient({
      url: storageUrl,
      apiKey: anonKey,
      getAccessToken: () => this.auth.accessToken,
      customFetch: this.customFetch,
    });

    // Initialize Functions
    this.functions = new AfribaseFunctionsClient({
      url: functionsUrl,
      apiKey: anonKey,
      getAccessToken: () => this.auth.accessToken,
      customFetch: this.customFetch,
    });

    // Initialize Email
    this.email = new AfribaseEmailClient({
      baseUrl: this.baseUrl,
      slug: extractSlug(this.baseUrl),
      apiKey: anonKey,
      getAccessToken: () => this.auth.accessToken,
      customFetch: this.customFetch,
    });

    // Sync auth state to realtime client
    this.auth.onAuthStateChange((_event, session) => {
      this.realtimeClient.setAuth(session?.access_token ?? null);
    });

    // Auto-initialize auth (restore session)
    this.auth.initialize();
  }

  // ─────────────────────────────────────────────────────────────────────
  // Database (PostgREST)
  // ─────────────────────────────────────────────────────────────────────

  /**
   * Query a table via PostgREST.
   *
   * @example
   * const { data } = await afribase.from('users').select('*').eq('id', 1);
   * const { data } = await afribase.from('posts').select('*, comments(*)').order('created_at', { ascending: false }).limit(10);
   */
  from<T = any>(table: string): AfribaseQueryBuilder<T> {
    return new AfribaseQueryBuilder<T>(`${this.restUrl}/${table}`, {
      apiKey: this.anonKey,
      accessToken: this.auth.accessToken,
      customFetch: this.customFetch,
    });
  }

  /**
   * Call a Postgres function (RPC).
   *
   * @example
   * const { data } = await afribase.rpc('get_top_users', { limit_count: 10 });
   */
  rpc<T = any>(
    fn: string,
    params: Record<string, any> = {},
    options?: { count?: 'exact' | 'planned' | 'estimated'; head?: boolean; get?: boolean },
  ): AfribaseRpcBuilder<T> {
    return new AfribaseRpcBuilder<T>(this.restUrl, fn, params, {
      apiKey: this.anonKey,
      accessToken: this.auth.accessToken,
      customFetch: this.customFetch,
      head: options?.head,
      count: options?.count,
      get: options?.get,
    });
  }

  // ─────────────────────────────────────────────────────────────────────
  // Realtime
  // ─────────────────────────────────────────────────────────────────────

  /**
   * Create a realtime channel.
   *
   * @example
   * const channel = afribase.channel('room:lobby');
   * channel.on('broadcast', { event: 'message' }, (payload) => console.log(payload)).subscribe();
   */
  channel(name: string, options?: RealtimeChannelOptions): RealtimeChannel {
    return this.realtimeClient.channel(name, options);
  }

  /**
   * Remove all realtime channels and disconnect.
   */
  removeAllChannels(): void {
    this.realtimeClient.removeAllChannels();
  }

  /**
   * Get the underlying realtime client.
   */
  get realtime(): AfribaseRealtimeClient {
    return this.realtimeClient;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Factory
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Create a new AfribaseClient instance.
 *
 * @param projectUrlOrRef The project'S API URL or unique project reference/slug.
 * @param anonKey The public anonymous key for your project.
 * @param options Additional configuration options.
 *
 * @example
 * // Using a full URL
 * const afribase = createClient('https://your-project.afribase.dev', 'your-anon-key');
 *
 * // Using a project ref (slug)
 * const afribase = createClient('webtoonie', 'your-anon-key');
 */
export const createClient = (
  projectUrlOrRef: string,
  anonKey: string,
  options?: Partial<AfribaseClientOptions>,
): AfribaseClient => {
  let url = projectUrlOrRef;
  if (!url.startsWith('http')) {
    // If it's just a ref, construct the default subdomain URL
    url = `https://${projectUrlOrRef}.afribase.dev`;
  }
  return new AfribaseClient(url, anonKey, options);
};
