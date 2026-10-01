/// Afribase Realtime Client for Dart/Flutter.
///
/// WebSocket-based realtime subscriptions with support for:
/// - Postgres Changes (INSERT, UPDATE, DELETE, *)
/// - Broadcast messages
/// - Presence (sync, join, leave)
library;

import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';

/// Callback for realtime messages.
typedef RealtimeCallback = void Function(Map<String, dynamic> payload);

/// Callback for subscription status.
typedef SubscribeCallback = void Function(String status, Object? error);

/// A binding entry for a channel listener.
class _ChannelBinding {
  final String type;
  final String event;
  final String? schema;
  final String? table;
  final String? filter;
  final RealtimeCallback? callback;

  const _ChannelBinding({
    required this.type,
    required this.event,
    this.schema,
    this.table,
    this.filter,
    this.callback,
  });
}

/// A single realtime channel supporting postgres_changes, broadcast, and presence.
///
/// ```dart
/// final channel = client.channel('room1');
/// channel.onPostgresChanges(
///   event: 'INSERT',
///   schema: 'public',
///   table: 'messages',
///   callback: (payload) => print(payload),
/// );
/// channel.onBroadcast('typing', (payload) => print(payload));
/// channel.subscribe();
/// ```
class RealtimeChannel {
  final String name;
  final AfribaseRealtimeClient _client;
  final List<_ChannelBinding> _bindings = [];
  bool _subscribed = false;

  RealtimeChannel({required this.name, required AfribaseRealtimeClient client})
      : _client = client;

  /// Whether this channel is currently subscribed.
  bool get isSubscribed => _subscribed;

  /// Listen for Postgres row-level changes.
  RealtimeChannel onPostgresChanges({
    required String event,
    String schema = 'public',
    String? table,
    String? filter,
    RealtimeCallback? callback,
  }) {
    _bindings.add(_ChannelBinding(
      type: 'postgres_changes',
      event: event,
      schema: schema,
      table: table,
      filter: filter,
      callback: callback,
    ));
    return this;
  }

  /// Listen for broadcast messages.
  RealtimeChannel onBroadcast(String event, RealtimeCallback callback) {
    _bindings.add(_ChannelBinding(
      type: 'broadcast',
      event: event,
      callback: callback,
    ));
    return this;
  }

  /// Listen for presence sync events.
  RealtimeChannel onPresenceSync(RealtimeCallback callback) {
    _bindings.add(_ChannelBinding(
      type: 'presence',
      event: 'sync',
      callback: callback,
    ));
    return this;
  }

  /// Listen for presence join events.
  RealtimeChannel onPresenceJoin(RealtimeCallback callback) {
    _bindings.add(_ChannelBinding(
      type: 'presence',
      event: 'join',
      callback: callback,
    ));
    return this;
  }

  /// Listen for presence leave events.
  RealtimeChannel onPresenceLeave(RealtimeCallback callback) {
    _bindings.add(_ChannelBinding(
      type: 'presence',
      event: 'leave',
      callback: callback,
    ));
    return this;
  }

  /// Subscribe to this channel's events.
  RealtimeChannel subscribe([SubscribeCallback? callback]) {
    _subscribed = true;
    _client._subscribeChannel(this);
    callback?.call('SUBSCRIBED', null);
    return this;
  }

  /// Unsubscribe from this channel.
  void unsubscribe() {
    _subscribed = false;
    _client._unsubscribeChannel(this);
  }

  /// Send a broadcast message to the channel.
  void sendBroadcast(String event, Map<String, dynamic> payload) {
    _client._send(name, {
      'type': 'broadcast',
      'event': event,
      'payload': payload,
    });
  }

  /// Track presence for this channel.
  void track(Map<String, dynamic> payload) {
    _client._send(name, {
      'type': 'presence',
      'event': 'track',
      'payload': payload,
    });
  }

  /// Remove presence tracking.
  void untrack() {
    _client._send(name, {
      'type': 'presence',
      'event': 'untrack',
    });
  }

  /// Dispatch a received message to matching callbacks.
  void _dispatch(Map<String, dynamic> message) {
    final msgType = message['type'] as String? ?? '';
    final msgEvent = message['event'] as String? ?? '';
    for (final binding in _bindings) {
      if (binding.type == msgType &&
          (binding.event == msgEvent || binding.event == '*')) {
        final payload =
            message['payload'] as Map<String, dynamic>? ?? message;
        try {
          binding.callback?.call(payload);
        } catch (_) {
          // Don't let listener errors propagate
        }
      }
    }
  }
}

/// WebSocket-based realtime client for Afribase.
class AfribaseRealtimeClient {
  final String _url;
  final String _apiKey;
  String? _accessToken;
  final Map<String, RealtimeChannel> _channels = {};
  WebSocketChannel? _ws;
  bool _connected = false;
  int _heartbeatRef = 0;

  AfribaseRealtimeClient({
    required String url,
    required String apiKey,
    String? accessToken,
  })  : _url = url.replaceFirst('http://', 'ws://').replaceFirst('https://', 'wss://'),
        _apiKey = apiKey,
        _accessToken = accessToken;

  /// Update the access token.
  void setAuth(String? accessToken) {
    _accessToken = accessToken;
  }

  /// Create or get a realtime channel.
  RealtimeChannel channel(String name) {
    return _channels.putIfAbsent(
        name, () => RealtimeChannel(name: name, client: this));
  }

  /// Remove a specific channel.
  void removeChannel(RealtimeChannel channel) {
    channel.unsubscribe();
    _channels.remove(channel.name);
  }

  /// Remove all channels and disconnect.
  void removeAllChannels() {
    for (final ch in _channels.values) {
      ch._subscribed = false;
    }
    _channels.clear();
    _disconnect();
  }

  // ─── Internal ────────────────────────────────────────────────────

  void _subscribeChannel(RealtimeChannel channel) {
    if (!_connected) _connect();
    _send(channel.name, {
      'type': 'phx_join',
      'topic': 'realtime:${channel.name}',
      'payload': {
        'config': {
          'postgres_changes': channel._bindings
              .where((b) => b.type == 'postgres_changes')
              .map((b) => {
                    'event': b.event,
                    'schema': b.schema ?? 'public',
                    'table': b.table ?? '*',
                    'filter': b.filter,
                  })
              .toList(),
        }
      },
      'ref': '${_heartbeatRef++}',
    });
  }

  void _unsubscribeChannel(RealtimeChannel channel) {
    _send(channel.name, {
      'type': 'phx_leave',
      'topic': 'realtime:${channel.name}',
      'payload': {},
      'ref': '${_heartbeatRef++}',
    });
  }

  void _connect() {
    final token = _accessToken ?? _apiKey;
    final wsUrl =
        '$_url/realtime/v1/websocket?apikey=$_apiKey&vsn=1.0.0&token=$token';

    try {
      _ws = WebSocketChannel.connect(Uri.parse(wsUrl));
      _connected = true;

      _ws!.stream.listen(
        (data) {
          try {
            final msg = jsonDecode(data as String) as Map<String, dynamic>;
            final topic = msg['topic'] as String? ?? '';
            final channelName = topic.replaceFirst('realtime:', '');
            final ch = _channels[channelName];
            if (ch != null) {
              ch._dispatch(
                  msg['payload'] as Map<String, dynamic>? ?? msg);
            }
          } catch (_) {
            // Ignore parse errors
          }
        },
        onError: (_) => _connected = false,
        onDone: () => _connected = false,
      );
    } catch (_) {
      _connected = false;
    }
  }

  void _disconnect() {
    _connected = false;
    try {
      _ws?.sink.close();
    } catch (_) {
      // best-effort
    }
    _ws = null;
  }

  void _send(String channelName, Map<String, dynamic> message) {
    if (_ws == null || !_connected) return;
    try {
      _ws!.sink.add(jsonEncode(message));
    } catch (_) {
      // Silently fail — connection might be lost
    }
  }
}
