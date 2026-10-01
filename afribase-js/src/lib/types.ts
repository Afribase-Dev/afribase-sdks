// ─────────────────────────────────────────────────────────────────────────────
// Core Types
// ─────────────────────────────────────────────────────────────────────────────

export interface AfribaseClientOptions {
  /**
   * The base URL of your Afribase project (e.g. https://your-project.useafribase.app)
   */
  baseUrl: string;

  /**
   * The anonymous/public API key for your project
   */
  anonKey: string;

  /**
   * Custom auth URL override
   */
  authUrl?: string;

  /**
   * Custom REST API URL override
   */
  restUrl?: string;

  /**
   * Custom realtime URL override
   */
  realtimeUrl?: string;

  /**
   * Custom storage URL override
   */
  storageUrl?: string;

  /**
   * Custom functions URL override
   */
  functionsUrl?: string;

  /**
   * Auto-refresh token when it's about to expire
   * @default true
   */
  autoRefreshToken?: boolean;

  /**
   * Persist the session to storage (localStorage in browser) and keep it in
   * memory between calls.
   *
   * Set to `false` for server-side usage (Next.js API routes, Express handlers,
   * etc.) where a single client instance serves many users. In stateless mode,
   * `signInWithPassword` and `signUp` do not store the resulting session — call
   * `getUser(jwt)` with the token from the incoming request's Authorization
   * header instead.
   *
   * @default true
   */
  persistSession?: boolean;

  /**
   * Custom fetch implementation
   */
  fetch?: typeof fetch;
}

// ─────────────────────────────────────────────────────────────────────────────
// Auth Types
// ─────────────────────────────────────────────────────────────────────────────

export interface Session {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  expires_at?: number;
  token_type: string;
  user: User;
}

export interface User {
  id: string;
  email?: string;
  phone?: string;
  app_metadata: Record<string, any>;
  user_metadata: Record<string, any>;
  aud: string;
  created_at: string;
  updated_at?: string;
  is_anonymous?: boolean;
  role?: string;
  confirmed_at?: string;
  last_sign_in_at?: string;
  identities?: UserIdentity[];
  factors?: Factor[];
}

export interface UserIdentity {
  id: string;
  user_id: string;
  identity_data: Record<string, any>;
  provider: string;
  created_at: string;
  updated_at: string;
}

export interface Factor {
  id: string;
  friendly_name?: string;
  factor_type: 'totp' | 'phone' | 'webauthn';
  status: 'verified' | 'unverified';
  created_at: string;
  updated_at: string;
}

export interface SignUpCredentials {
  email?: string;
  phone?: string;
  password: string;
  options?: {
    data?: Record<string, any>;
    emailRedirectTo?: string;
    captchaToken?: string;
  };
}

export interface SignInWithPasswordCredentials {
  email?: string;
  phone?: string;
  password: string;
  options?: {
    captchaToken?: string;
  };
}

export interface SignInWithOAuthCredentials {
  provider: OAuthProvider;
  options?: {
    redirectTo?: string;
    scopes?: string;
    queryParams?: Record<string, string>;
  };
}

export interface SignInWithOtpCredentials {
  email?: string;
  phone?: string;
  options?: {
    emailRedirectTo?: string;
    shouldCreateUser?: boolean;
    data?: Record<string, any>;
    captchaToken?: string;
  };
}

export interface VerifyOtpParams {
  email?: string;
  phone?: string;
  token: string;
  type: 'sms' | 'email' | 'signup' | 'magiclink' | 'recovery';
}

export interface ResetPasswordCredentials {
  email: string;
  options?: {
    redirectTo?: string;
    captchaToken?: string;
  };
}

export interface UserAttributes {
  email?: string;
  phone?: string;
  password?: string;
  data?: Record<string, any>;
}

export type OAuthProvider =
  | 'apple'
  | 'azure'
  | 'bitbucket'
  | 'discord'
  | 'facebook'
  | 'figma'
  | 'fly'
  | 'github'
  | 'gitlab'
  | 'google'
  | 'kakao'
  | 'keycloak'
  | 'linkedin'
  | 'linkedin_oidc'
  | 'notion'
  | 'slack'
  | 'slack_oidc'
  | 'snapchat'
  | 'spotify'
  | 'twitch'
  | 'twitter'
  | 'workos'
  | 'x'
  | 'zoom';

export type AuthChangeEvent =
  | 'SIGNED_IN'
  | 'SIGNED_OUT'
  | 'TOKEN_REFRESHED'
  | 'USER_UPDATED'
  | 'PASSWORD_RECOVERY'
  | 'INITIAL_SESSION';

export interface AuthChangeCallback {
  (event: AuthChangeEvent, session: Session | null): void;
}

export interface Subscription {
  id: string;
  unsubscribe: () => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Realtime Types
// ─────────────────────────────────────────────────────────────────────────────

export type RealtimeChannelEvent =
  | 'INSERT'
  | 'UPDATE'
  | 'DELETE'
  | '*';

export interface RealtimePostgresChangesPayload<T = any> {
  eventType: 'INSERT' | 'UPDATE' | 'DELETE';
  new: T;
  old: Partial<T>;
  schema: string;
  table: string;
  commit_timestamp: string;
  errors: string[] | null;
}

export interface RealtimePresenceState {
  [key: string]: PresenceEntry[];
}

export interface PresenceEntry {
  presence_ref: string;
  [key: string]: any;
}

export type RealtimeListenTypes =
  | 'postgres_changes'
  | 'broadcast'
  | 'presence';

export interface RealtimeChannelOptions {
  /** Channel config (e.g. for Postgres changes) */
  config?: {
    broadcast?: { self?: boolean; ack?: boolean };
    presence?: { key?: string };
    postgres_changes?: Array<{
      event: RealtimeChannelEvent;
      schema: string;
      table?: string;
      filter?: string;
    }>;
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Storage Types
// ─────────────────────────────────────────────────────────────────────────────

export interface StorageBucket {
  id: string;
  name: string;
  public: boolean;
  file_size_limit?: number;
  allowed_mime_types?: string[];
  created_at: string;
  updated_at: string;
}

export interface StorageObject {
  id: string;
  bucket_id: string;
  name: string;
  mime_type: string;
  size: number;
  etag?: string;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, any>;
}

export interface UploadOptions {
  contentType?: string;
  cacheControl?: string;
  upsert?: boolean;
  duplex?: string;
}

export interface TransformOptions {
  width?: number;
  height?: number;
  resize?: 'cover' | 'contain' | 'fill';
  quality?: number;
  format?: 'origin' | 'avif' | 'webp';
}

export interface SignedUrlOptions {
  download?: string | boolean;
  transform?: TransformOptions;
}

export interface CreateSignedUrlResponse {
  signedUrl: string;
  path: string;
  token: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Functions Types
// ─────────────────────────────────────────────────────────────────────────────

export interface FunctionInvokeOptions {
  body?: any;
  headers?: Record<string, string>;
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  region?: string;
}

export interface FunctionInvokeResponse<T = any> {
  data: T | null;
  error: Error | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Query Builder Types
// ─────────────────────────────────────────────────────────────────────────────

export type FilterOperator =
  | 'eq'
  | 'neq'
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'like'
  | 'ilike'
  | 'is'
  | 'in'
  | 'cs'
  | 'cd'
  | 'sl'
  | 'sr'
  | 'nxl'
  | 'nxr'
  | 'adj'
  | 'ov'
  | 'fts'
  | 'plfts'
  | 'phfts'
  | 'wfts';

export interface PostgrestError {
  message: string;
  details: string;
  hint: string;
  code: string;
}

export interface PostgrestResponse<T> {
  data: T | null;
  error: PostgrestError | null;
  count: number | null;
  status: number;
  statusText: string;
}

export interface PostgrestSingleResponse<T> extends PostgrestResponse<T> {
  data: T;
}
