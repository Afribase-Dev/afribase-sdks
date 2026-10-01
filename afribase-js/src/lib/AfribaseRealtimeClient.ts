import type {
  RealtimeChannelEvent,
  RealtimeChannelOptions,
  RealtimeListenTypes,
  RealtimePostgresChangesPayload,
  RealtimePresenceState,
  PresenceEntry,
} from './types';

// ─────────────────────────────────────────────────────────────────────────────
// WebSocket Abstraction — works in both browser and Node.js
// ─────────────────────────────────────────────────────────────────────────────

type WS = {
  send(data: string): void;
  close(): void;
  readyState: number;
  onopen: ((ev: any) => void) | null;
  onmessage: ((ev: { data: any }) => void) | null;
  onclose: ((ev: any) => void) | null;
  onerror: ((ev: any) => void) | null;
};

type WSConstructor = new (url: string, protocols?: string | string[]) => WS;

function getWebSocketImpl(): WSConstructor {
  if (typeof WebSocket !== 'undefined') return WebSocket as any;
  // Node.js — try to load 'ws' dynamically
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const ws = (globalThis as any).require?.('ws') ?? (new Function('return require("ws")'))();
    return ws;
  } catch {
    throw new Error(
      'WebSocket is not available. In Node.js, install the "ws" package: npm install ws'
    );
  }
}

const WS_OPEN = 1;

// ─────────────────────────────────────────────────────────────────────────────
// Realtime Channel
// ─────────────────────────────────────────────────────────────────────────────

interface ChannelBinding {
  type: RealtimeListenTypes;
  filter?: {
    event?: string;
    schema?: string;
    table?: string;
    filter?: string;
  };
  callback: (payload: any) => void;
}

export type ChannelStatus = 'SUBSCRIBED' | 'TIMED_OUT' | 'CLOSED' | 'CHANNEL_ERROR';

/**
 * A Realtime Channel — subscribe to postgres_changes, broadcast, and presence events.
 */
export class RealtimeChannel {
  private bindings: ChannelBinding[] = [];
  private presenceState: RealtimePresenceState = {};
  private presenceKey: string;
  private _status: ChannelStatus = 'CLOSED';

  /** @internal */
  readonly topic: string;

  constructor(
    topic: string,
    private params: RealtimeChannelOptions,
    private sendMessage: (msg: any) => void,
    private removeChannel: (topic: string) => void,
  ) {
    this.topic = topic;
    this.presenceKey = params.config?.presence?.key || '';
  }

  /**
   * Listen for events on this channel.
   *
   * @example
   * channel.on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'messages' }, (payload) => { ... })
   * channel.on('broadcast', { event: 'cursor-pos' }, (payload) => { ... })
   * channel.on('presence', { event: 'sync' }, () => { ... })
   */
  on(
    type: 'postgres_changes',
    filter: { event: RealtimeChannelEvent; schema: string; table?: string; filter?: string },
    callback: (payload: RealtimePostgresChangesPayload) => void,
  ): this;
  on(
    type: 'broadcast',
    filter: { event: string },
    callback: (payload: { type: string; event: string; payload: any }) => void,
  ): this;
  on(
    type: 'presence',
    filter: { event: 'sync' | 'join' | 'leave' },
    callback: (payload: any) => void,
  ): this;
  on(type: RealtimeListenTypes, filter: any, callback: (payload: any) => void): this {
    this.bindings.push({ type, filter, callback });
    return this;
  }

  /**
   * Subscribe to the channel — starts receiving events.
   */
  subscribe(callback?: (status: ChannelStatus, err?: Error) => void): this {
    // Build the join message
    const joinConfig: any = { topic: this.topic };

    // Attach postgres_changes configs
    const pgBindings = this.bindings.filter((b) => b.type === 'postgres_changes');
    if (pgBindings.length > 0) {
      joinConfig.postgres_changes = pgBindings.map((b) => ({
        event: b.filter?.event || '*',
        schema: b.filter?.schema || 'public',
        table: b.filter?.table || '*',
        filter: b.filter?.filter,
      }));
    }

    // Attach broadcast configs
    if (this.params.config?.broadcast) {
      joinConfig.broadcast = this.params.config.broadcast;
    }

    // Attach presence configs
    if (this.params.config?.presence) {
      joinConfig.presence = this.params.config.presence;
    }

    this.sendMessage({
      topic: this.topic,
      event: 'phx_join',
      payload: joinConfig,
      ref: null,
    });

    this._status = 'SUBSCRIBED';
    if (callback) {
      setTimeout(() => callback('SUBSCRIBED'), 0);
    }

    return this;
  }

  /**
   * Send a broadcast message to all subscribers.
   */
  send(payload: { type: 'broadcast'; event: string; payload: any }): this {
    this.sendMessage({
      topic: this.topic,
      event: payload.event,
      payload: payload.payload,
      ref: null,
    });
    return this;
  }

  /**
   * Track presence for the current user.
   */
  track(payload: Record<string, any>): this {
    this.sendMessage({
      topic: this.topic,
      event: 'presence',
      payload: { type: 'track', ...payload, key: this.presenceKey },
      ref: null,
    });
    return this;
  }

  /**
   * Untrack presence for the current user.
   */
  untrack(): this {
    this.sendMessage({
      topic: this.topic,
      event: 'presence',
      payload: { type: 'untrack', key: this.presenceKey },
      ref: null,
    });
    return this;
  }

  /**
   * Get current presence state.
   */
  presenceState_(): RealtimePresenceState {
    return { ...this.presenceState };
  }

  /**
   * Unsubscribe from this channel.
   */
  unsubscribe(): void {
    this.sendMessage({
      topic: this.topic,
      event: 'phx_leave',
      payload: {},
      ref: null,
    });
    this._status = 'CLOSED';
    this.removeChannel(this.topic);
  }

  get status(): ChannelStatus {
    return this._status;
  }

  /** @internal — called by the RealtimeClient when a message arrives */
  _handleMessage(msg: { event: string; payload: any }): void {
    // Postgres Changes
    if (msg.payload?.type === 'postgres_changes') {
      const pgPayload = msg.payload as RealtimePostgresChangesPayload;
      for (const binding of this.bindings) {
        if (binding.type !== 'postgres_changes') continue;
        const f = binding.filter;
        if (f?.schema && f.schema !== pgPayload.schema) continue;
        if (f?.table && f.table !== pgPayload.table) continue;
        if (f?.event && f.event !== '*' && f.event !== pgPayload.eventType) continue;
        binding.callback(pgPayload);
      }
      return;
    }

    // Presence
    if (msg.payload?.type === 'presence_state' || msg.payload?.type === 'presence_diff') {
      if (msg.payload.type === 'presence_state') {
        this.presenceState = msg.payload.state || {};
      } else if (msg.payload.type === 'presence_diff') {
        const { joins, leaves } = msg.payload;
        if (joins) {
          for (const [key, val] of Object.entries(joins as Record<string, { metas: PresenceEntry[] }>)) {
            this.presenceState[key] = val.metas;
          }
        }
        if (leaves) {
          for (const key of Object.keys(leaves)) {
            delete this.presenceState[key];
          }
        }
      }
      for (const binding of this.bindings) {
        if (binding.type !== 'presence') continue;
        if (binding.filter?.event === 'sync' || binding.filter?.event === msg.payload.type) {
          binding.callback({
            type: msg.payload.type,
            presenceState: this.presenceState,
            joins: msg.payload.joins,
            leaves: msg.payload.leaves,
          });
        }
      }
      return;
    }

    // Broadcast
    for (const binding of this.bindings) {
      if (binding.type !== 'broadcast') continue;
      if (binding.filter?.event === msg.event || binding.filter?.event === '*') {
        binding.callback({ type: 'broadcast', event: msg.event, payload: msg.payload });
      }
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Realtime Client
// ─────────────────────────────────────────────────────────────────────────────

export interface RealtimeClientOptions {
  url: string;
  apiKey: string;
  accessToken?: string | null;
}

/**
 * AfribaseRealtimeClient — manages the WebSocket connection to the
 * Supabase-compatible Realtime service and multiplexes channels.
 */
export class AfribaseRealtimeClient {
  private url: string;
  private apiKey: string;
  private accessToken: string | null;
  private ws: WS | null = null;
  private channels: Map<string, RealtimeChannel> = new Map();
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectBaseDelay = 1000;
  private connected = false;

  constructor(options: RealtimeClientOptions) {
    // Convert http(s) to ws(s)
    this.url = options.url
      .replace(/^http/, 'ws')
      .replace(/\/$/, '') + '/realtime/v1/websocket';
    this.apiKey = options.apiKey;
    this.accessToken = options.accessToken ?? null;
  }

  /**
   * Set the access token (called by AfribaseClient when auth state changes).
   */
  setAuth(token: string | null): void {
    this.accessToken = token;
    // If connected, send an auth update
    if (this.ws && this.ws.readyState === WS_OPEN) {
      this._send({
        topic: 'phoenix',
        event: 'access_token',
        payload: { access_token: token },
        ref: null,
      });
    }
  }

  /**
   * Create a channel for a given topic.
   */
  channel(topic: string, options: RealtimeChannelOptions = {}): RealtimeChannel {
    const normalizedTopic = topic.startsWith('realtime:') ? topic : `realtime:${topic}`;

    if (this.channels.has(normalizedTopic)) {
      return this.channels.get(normalizedTopic)!;
    }

    const ch = new RealtimeChannel(
      normalizedTopic,
      options,
      (msg) => this._send(msg),
      (t) => this.channels.delete(t),
    );
    this.channels.set(normalizedTopic, ch);

    // Auto-connect on first channel
    if (!this.ws) {
      this._connect();
    }

    return ch;
  }

  /**
   * Remove all channels and disconnect.
   */
  removeAllChannels(): void {
    for (const ch of this.channels.values()) {
      ch.unsubscribe();
    }
    this.channels.clear();
    this._disconnect();
  }

  /**
   * Disconnect the WebSocket.
   */
  disconnect(): void {
    this._disconnect();
  }

  // ─────────────────────────────────────────────────────────────────────
  // Private
  // ─────────────────────────────────────────────────────────────────────

  private _connect(): void {
    if (this.ws) return;

    try {
      const WSImpl = getWebSocketImpl();
      const params = new URLSearchParams({
        apikey: this.apiKey,
        vsn: '1.0.0',
      });
      if (this.accessToken) {
        params.set('token', this.accessToken);
      }
      this.ws = new WSImpl(`${this.url}?${params.toString()}`);
    } catch (err) {
      this._scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.connected = true;
      this.reconnectAttempts = 0;
      this._startHeartbeat();
      // Re-subscribe all channels
      for (const ch of this.channels.values()) {
        if (ch.status === 'CLOSED') {
          ch.subscribe();
        }
      }
    };

    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(typeof ev.data === 'string' ? ev.data : ev.data.toString());
        this._handleMessage(msg);
      } catch {
        // Ignore malformed messages
      }
    };

    this.ws.onclose = () => {
      this.connected = false;
      this._stopHeartbeat();
      this.ws = null;
      if (this.channels.size > 0) {
        this._scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // onclose will fire after onerror
    };
  }

  private _disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this._stopHeartbeat();
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
    this.connected = false;
  }

  private _send(msg: any): void {
    if (this.ws && this.ws.readyState === WS_OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  private _handleMessage(msg: { topic: string; event: string; payload: any; ref: any }): void {
    // Heartbeat reply
    if (msg.topic === 'phoenix' && msg.event === 'phx_reply') return;

    // Route to channel
    const ch = this.channels.get(msg.topic);
    if (ch) {
      ch._handleMessage(msg);
    }
  }

  private _startHeartbeat(): void {
    this._stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this._send({ topic: 'phoenix', event: 'heartbeat', payload: {}, ref: null });
    }, 30000);
  }

  private _stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private _scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;

    const delay = Math.min(
      this.reconnectBaseDelay * Math.pow(2, this.reconnectAttempts),
      30000,
    );
    this.reconnectAttempts++;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this._connect();
    }, delay);
  }
}
