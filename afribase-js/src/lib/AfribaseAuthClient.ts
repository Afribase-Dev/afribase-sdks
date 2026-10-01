import { fetchWithAuth, handleResponse } from './fetch';
import type {
  AuthChangeCallback,
  AuthChangeEvent,
  ResetPasswordCredentials,
  Session,
  SignInWithOAuthCredentials,
  SignInWithOtpCredentials,
  SignInWithPasswordCredentials,
  SignUpCredentials,
  Subscription,
  User,
  UserAttributes,
  VerifyOtpParams,
} from './types';

const STORAGE_KEY = 'afribase.auth.token';

/**
 * AfribaseAuthClient handles authentication state, token refresh,
 * OAuth sign-in, OTP, anonymous auth, and auth state change listeners.
 */
export class AfribaseAuthClient {
  private url: string;
  private apiKey: string;
  private currentSession: Session | null = null;
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;
  private listeners: Map<string, AuthChangeCallback> = new Map();
  private autoRefresh: boolean;
  private persistSession: boolean;
  private customFetch?: typeof fetch;
  private listenerIdCounter = 0;

  constructor(options: {
    url: string;
    apiKey: string;
    autoRefreshToken?: boolean;
    persistSession?: boolean;
    customFetch?: typeof fetch;
  }) {
    this.url = options.url.replace(/\/$/, '');
    this.apiKey = options.apiKey;
    this.autoRefresh = options.autoRefreshToken ?? true;
    this.persistSession = options.persistSession ?? true;
    this.customFetch = options.customFetch;
  }

  // ─────────────────────────────────────────────────────────────────────
  // Session Management
  // ─────────────────────────────────────────────────────────────────────

  /**
   * Initialize the auth client — restores persisted session and emits INITIAL_SESSION.
   * Call this once after creating the client.
   */
  async initialize(): Promise<{ data: { session: Session | null }; error: any }> {
    try {
      const stored = this._getStoredSession();
      if (stored) {
        if (this._isSessionExpired(stored)) {
          // Try to refresh
          const { data, error } = await this._refreshSession(stored.refresh_token);
          if (!error && data) {
            this._setSession(data);
            this._notifyListeners('INITIAL_SESSION', data);
            return { data: { session: data }, error: null };
          }
          // Refresh failed — clear
          this._removeSession();
          this._notifyListeners('INITIAL_SESSION', null);
          return { data: { session: null }, error: null };
        }
        this._setSession(stored);
        this._notifyListeners('INITIAL_SESSION', stored);
        return { data: { session: stored }, error: null };
      }
      this._notifyListeners('INITIAL_SESSION', null);
      return { data: { session: null }, error: null };
    } catch (err: any) {
      return { data: { session: null }, error: err };
    }
  }

  /**
   * Returns the current session if it exists.
   */
  async getSession(): Promise<{ data: { session: Session | null }; error: null }> {
    return { data: { session: this.currentSession }, error: null };
  }

  /**
   * Returns the user associated with the given JWT, or the current session user.
   *
   * When called with a `jwt` argument the token is sent directly to the auth
   * server and the stored session is never read — safe for server-side usage
   * where a single client instance services many users.
   *
   * @param jwt - Optional JWT to validate. If omitted, uses the current session.
   */
  async getUser(jwt?: string): Promise<{ data: { user: User | null }; error: any }> {
    const token = jwt ?? this.currentSession?.access_token;
    if (!token) {
      return { data: { user: null }, error: { message: 'Not authenticated' } };
    }

    const resp = await fetchWithAuth(`${this.url}/user`, {
      apiKey: this.apiKey,
      accessToken: token,
      customFetch: this.customFetch,
    });
    const result = await handleResponse<User>(resp);
    // Only update the stored session when we used the stored token,
    // not when a caller-supplied jwt was used (server-side path).
    if (!jwt && result.data && this.currentSession) {
      this.currentSession.user = result.data;
    }
    return { data: { user: result.data }, error: result.error };
  }

  // ─────────────────────────────────────────────────────────────────────
  // Sign Up / Sign In
  // ─────────────────────────────────────────────────────────────────────

  /**
   * Create a new user with email/phone and password.
   */
  async signUp(credentials: SignUpCredentials): Promise<{ data: { user: User | null; session: Session | null }; error: any }> {
    const body: Record<string, any> = { password: credentials.password };
    if (credentials.email) body.email = credentials.email;
    if (credentials.phone) body.phone = credentials.phone;
    if (credentials.options?.data) body.data = credentials.options.data;
    if (credentials.options?.captchaToken) body.gotcha = credentials.options.captchaToken;

    const resp = await fetchWithAuth(`${this.url}/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      apiKey: this.apiKey,
      customFetch: this.customFetch,
    });

    const result = await handleResponse<any>(resp);
    if (result.error) return { data: { user: null, session: null }, error: result.error };

    const data = result.data;
    if (data.access_token) {
      const session = this._makeSession(data);
      this._setSession(session);
      this._notifyListeners('SIGNED_IN', session);
      return { data: { user: session.user, session }, error: null };
    }

    // Email confirmation required — no session yet
    return { data: { user: data, session: null }, error: null };
  }

  /**
   * Sign in with email/phone and password.
   */
  async signInWithPassword(credentials: SignInWithPasswordCredentials): Promise<{ data: { user: User; session: Session }; error: any }> {
    const body: Record<string, any> = { password: credentials.password };
    if (credentials.email) body.email = credentials.email;
    if (credentials.phone) body.phone = credentials.phone;
    if (credentials.options?.captchaToken) body.gotcha = credentials.options.captchaToken;

    const resp = await fetchWithAuth(`${this.url}/token?grant_type=password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      apiKey: this.apiKey,
      customFetch: this.customFetch,
    });

    const result = await handleResponse<any>(resp);
    if (result.error) return { data: { user: null as any, session: null as any }, error: result.error };

    const session = this._makeSession(result.data);
    this._setSession(session);
    this._notifyListeners('SIGNED_IN', session);
    return { data: { user: session.user, session }, error: null };
  }

  /**
   * Sign in with a third-party OAuth provider.
   * Returns a URL to redirect the user to.
   */
  async signInWithOAuth(credentials: SignInWithOAuthCredentials): Promise<{ data: { provider: string; url: string }; error: null }> {
    const params = new URLSearchParams();
    if (credentials.options?.redirectTo) params.set('redirect_to', credentials.options.redirectTo);
    if (credentials.options?.scopes) params.set('scopes', credentials.options.scopes);
    if (credentials.options?.queryParams) {
      for (const [k, v] of Object.entries(credentials.options.queryParams)) {
        params.set(k, v);
      }
    }

    const qs = params.toString();
    const url = `${this.url}/authorize?provider=${credentials.provider}${qs ? '&' + qs : ''}`;
    return { data: { provider: credentials.provider, url }, error: null };
  }

  /**
   * Sign in with a one-time password (magic link or SMS OTP).
   */
  async signInWithOtp(credentials: SignInWithOtpCredentials): Promise<{ data: { messageId?: string } | null; error: any }> {
    const body: Record<string, any> = {};
    if (credentials.email) body.email = credentials.email;
    if (credentials.phone) body.phone = credentials.phone;
    if (credentials.options?.data) body.data = credentials.options.data;
    if (credentials.options?.captchaToken) body.gotcha = credentials.options.captchaToken;
    if (credentials.options?.shouldCreateUser !== undefined) body.create_user = credentials.options.shouldCreateUser;

    const resp = await fetchWithAuth(`${this.url}/otp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      apiKey: this.apiKey,
      customFetch: this.customFetch,
    });
    return handleResponse(resp);
  }

  /**
   * Verify an OTP or magic link token.
   */
  async verifyOtp(params: VerifyOtpParams): Promise<{ data: { user: User; session: Session }; error: any }> {
    const body: Record<string, any> = { token: params.token, type: params.type };
    if (params.email) body.email = params.email;
    if (params.phone) body.phone = params.phone;

    const resp = await fetchWithAuth(`${this.url}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      apiKey: this.apiKey,
      customFetch: this.customFetch,
    });

    const result = await handleResponse<any>(resp);
    if (result.error) return { data: { user: null as any, session: null as any }, error: result.error };

    if (result.data?.access_token) {
      const session = this._makeSession(result.data);
      this._setSession(session);
      this._notifyListeners('SIGNED_IN', session);
      return { data: { user: session.user, session }, error: null };
    }

    return { data: result.data, error: null };
  }

  /**
   * Sign in anonymously — creates an anonymous user.
   */
  async signInAnonymously(options?: { data?: Record<string, any>; captchaToken?: string }): Promise<{ data: { user: User; session: Session }; error: any }> {
    const body: Record<string, any> = {};
    if (options?.data) body.data = options.data;
    if (options?.captchaToken) body.gotcha = options.captchaToken;

    const resp = await fetchWithAuth(`${this.url}/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      apiKey: this.apiKey,
      customFetch: this.customFetch,
    });

    const result = await handleResponse<any>(resp);
    if (result.error) return { data: { user: null as any, session: null as any }, error: result.error };

    if (result.data?.access_token) {
      const session = this._makeSession(result.data);
      this._setSession(session);
      this._notifyListeners('SIGNED_IN', session);
      return { data: { user: session.user, session }, error: null };
    }

    return { data: result.data, error: null };
  }

  // ─────────────────────────────────────────────────────────────────────
  // Password Recovery & User Updates
  // ─────────────────────────────────────────────────────────────────────

  /**
   * Sends a password reset email.
   */
  async resetPasswordForEmail(email: string, options?: ResetPasswordCredentials['options']): Promise<{ data: {} | null; error: any }> {
    const body: Record<string, any> = { email };
    if (options?.redirectTo) body.redirect_to = options.redirectTo;
    if (options?.captchaToken) body.gotcha = options.captchaToken;

    const resp = await fetchWithAuth(`${this.url}/recover`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      apiKey: this.apiKey,
      customFetch: this.customFetch,
    });
    return handleResponse(resp);
  }

  /**
   * Update the current user (email, phone, password, metadata).
   */
  async updateUser(attributes: UserAttributes): Promise<{ data: { user: User }; error: any }> {
    if (!this.currentSession?.access_token) {
      return { data: { user: null as any }, error: { message: 'Not authenticated' } };
    }

    const resp = await fetchWithAuth(`${this.url}/user`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(attributes),
      apiKey: this.apiKey,
      accessToken: this.currentSession.access_token,
      customFetch: this.customFetch,
    });

    const result = await handleResponse<User>(resp);
    if (!result.error && result.data && this.currentSession) {
      this.currentSession.user = result.data;
      this._persistSession(this.currentSession);
      this._notifyListeners('USER_UPDATED', this.currentSession);
    }
    return { data: { user: result.data! }, error: result.error };
  }

  // ─────────────────────────────────────────────────────────────────────
  // Account deletion
  // ─────────────────────────────────────────────────────────────────────

  /**
   * Permanently delete a user.
   *
   * GoTrue has no self-service delete — the endpoint is an administrative one
   * — so this needs a client built with the **service key** and must never run
   * in a browser, where that key would be readable by anyone who opened the
   * page. Call it from your own server, after you have decided the person
   * asking is the person being deleted.
   *
   * `shouldSoftDelete` keeps the row and clears the identity instead of
   * removing it. That leaves the email address occupied, so the person cannot
   * sign up again with it; the default is a real delete.
   *
   * Deleting the signed-in user also ends their session here, since it would
   * otherwise keep refreshing a token for somebody who no longer exists.
   */
  async deleteUser(
    userId: string,
    options?: { shouldSoftDelete?: boolean },
  ): Promise<{ data: {} | null; error: any }> {
    const resp = await fetchWithAuth(`${this.url}/admin/users/${encodeURIComponent(userId)}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ should_soft_delete: options?.shouldSoftDelete ?? false }),
      apiKey: this.apiKey,
      customFetch: this.customFetch,
    });

    const result = await handleResponse<{}>(resp);

    if (!result.error && this.currentSession?.user?.id === userId) {
      this._removeSession();
      this._notifyListeners('SIGNED_OUT', null);
    }

    return { data: result.error ? null : {}, error: result.error };
  }

  /**
   * The administrative corner of the auth client, kept in one place so it is
   * obvious at the call site that a service key is involved.
   */
  get admin(): { deleteUser: AfribaseAuthClient['deleteUser'] } {
    return { deleteUser: this.deleteUser.bind(this) };
  }

  // ─────────────────────────────────────────────────────────────────────
  // Sign Out
  // ─────────────────────────────────────────────────────────────────────

  /**
   * Sign out the current user.
   */
  async signOut(): Promise<{ error: any }> {
    if (this.currentSession?.access_token) {
      try {
        await fetchWithAuth(`${this.url}/logout`, {
          method: 'POST',
          apiKey: this.apiKey,
          accessToken: this.currentSession.access_token,
          customFetch: this.customFetch,
        });
      } catch {
        // Ignore — sign out locally regardless
      }
    }
    this._removeSession();
    this._notifyListeners('SIGNED_OUT', null);
    return { error: null };
  }

  // ─────────────────────────────────────────────────────────────────────
  // Auth State Change
  // ─────────────────────────────────────────────────────────────────────

  /**
   * Listen for auth state changes.
   * Returns a subscription object with an unsubscribe method.
   */
  onAuthStateChange(callback: AuthChangeCallback): { data: { subscription: Subscription } } {
    const id = `auth-listener-${++this.listenerIdCounter}`;
    this.listeners.set(id, callback);

    // Emit current state immediately
    setTimeout(() => {
      callback('INITIAL_SESSION', this.currentSession);
    }, 0);

    return {
      data: {
        subscription: {
          id,
          unsubscribe: () => {
            this.listeners.delete(id);
          },
        },
      },
    };
  }

  // ─────────────────────────────────────────────────────────────────────
  // Token Refresh
  // ─────────────────────────────────────────────────────────────────────

  /**
   * Manually refresh the session token.
   */
  async refreshSession(): Promise<{ data: { session: Session | null }; error: any }> {
    if (!this.currentSession?.refresh_token) {
      return { data: { session: null }, error: { message: 'No refresh token' } };
    }
    const { data, error } = await this._refreshSession(this.currentSession.refresh_token);
    if (error) return { data: { session: null }, error };
    if (data) {
      this._setSession(data);
      this._notifyListeners('TOKEN_REFRESHED', data);
    }
    return { data: { session: data }, error: null };
  }

  /**
   * Set the session manually (useful for server-side auth).
   */
  async setSession(params: { access_token: string; refresh_token: string }): Promise<{ data: { session: Session }; error: any }> {
    const resp = await fetchWithAuth(`${this.url}/user`, {
      apiKey: this.apiKey,
      accessToken: params.access_token,
      customFetch: this.customFetch,
    });

    const result = await handleResponse<User>(resp);
    if (result.error) return { data: { session: null as any }, error: result.error };

    const session: Session = {
      access_token: params.access_token,
      refresh_token: params.refresh_token,
      expires_in: 3600,
      expires_at: Math.floor(Date.now() / 1000) + 3600,
      token_type: 'bearer',
      user: result.data!,
    };
    this._setSession(session);
    this._notifyListeners('SIGNED_IN', session);
    return { data: { session }, error: null };
  }

  // ─────────────────────────────────────────────────────────────────────
  // Helpers — Access Token for other clients
  // ─────────────────────────────────────────────────────────────────────

  /** @internal */
  get accessToken(): string | null {
    return this.currentSession?.access_token ?? null;
  }

  // ─────────────────────────────────────────────────────────────────────
  // Private Helpers
  // ─────────────────────────────────────────────────────────────────────

  private _makeSession(data: any): Session {
    const expiresAt = data.expires_at ?? Math.floor(Date.now() / 1000) + (data.expires_in || 3600);
    return {
      access_token: data.access_token,
      refresh_token: data.refresh_token,
      expires_in: data.expires_in || 3600,
      expires_at: expiresAt,
      token_type: data.token_type || 'bearer',
      user: data.user || data,
    };
  }

  private _setSession(session: Session): void {
    // In stateless mode (persistSession:false) we do not store the session
    // in-memory at all — this prevents singleton bleed on server-side usage
    // where a single client instance handles many concurrent users.
    if (this.persistSession) {
      this.currentSession = session;
      this._persistSession(session);
      this._scheduleRefresh(session);
    }
  }

  private _removeSession(): void {
    this.currentSession = null;
    if (this.refreshTimer) {
      clearTimeout(this.refreshTimer);
      this.refreshTimer = null;
    }
    this._clearStoredSession();
  }

  private async _refreshSession(refreshToken: string): Promise<{ data: Session | null; error: any }> {
    const resp = await fetchWithAuth(`${this.url}/token?grant_type=refresh_token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
      apiKey: this.apiKey,
      customFetch: this.customFetch,
    });

    const result = await handleResponse<any>(resp);
    if (result.error) return { data: null, error: result.error };
    return { data: this._makeSession(result.data), error: null };
  }

  private _scheduleRefresh(session: Session): void {
    if (!this.autoRefresh) return;
    if (this.refreshTimer) clearTimeout(this.refreshTimer);

    const expiresAt = session.expires_at ?? Math.floor(Date.now() / 1000) + session.expires_in;
    const now = Math.floor(Date.now() / 1000);
    // Refresh 60 seconds before expiry
    const refreshIn = Math.max((expiresAt - now - 60) * 1000, 1000);

    this.refreshTimer = setTimeout(async () => {
      if (this.currentSession?.refresh_token) {
        const { data, error } = await this._refreshSession(this.currentSession.refresh_token);
        if (!error && data) {
          this._setSession(data);
          this._notifyListeners('TOKEN_REFRESHED', data);
        } else {
          // Refresh failed — sign out
          this._removeSession();
          this._notifyListeners('SIGNED_OUT', null);
        }
      }
    }, refreshIn);
  }

  private _isSessionExpired(session: Session): boolean {
    if (!session.expires_at) return false;
    return Math.floor(Date.now() / 1000) >= session.expires_at;
  }

  private _notifyListeners(event: AuthChangeEvent, session: Session | null): void {
    for (const cb of this.listeners.values()) {
      try {
        cb(event, session);
      } catch {
        // Don't let listener errors crash the auth client
      }
    }
  }

  // Storage helpers (localStorage in browser, no-op in Node)
  private _persistSession(session: Session): void {
    if (!this.persistSession) return;
    try {
      if (typeof globalThis !== 'undefined' && (globalThis as any).localStorage) {
        (globalThis as any).localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
      }
    } catch {
      // Ignore storage errors (SSR, etc.)
    }
  }

  private _getStoredSession(): Session | null {
    if (!this.persistSession) return null;
    try {
      if (typeof globalThis !== 'undefined' && (globalThis as any).localStorage) {
        const raw = (globalThis as any).localStorage.getItem(STORAGE_KEY);
        return raw ? JSON.parse(raw) : null;
      }
    } catch {
      // Ignore
    }
    return null;
  }

  private _clearStoredSession(): void {
    try {
      if (typeof globalThis !== 'undefined' && (globalThis as any).localStorage) {
        (globalThis as any).localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // Ignore
    }
  }
}
