/// Afribase Client — main entry point for the Afribase Dart/Flutter SDK.
///
/// ```dart
/// import 'package:afribase/afribase.dart';
///
/// final client = AfribaseClient('https://your-project.useafribase.app', 'your-anon-key');
///
/// // Auth
/// final res = await client.auth.signUp(email: 'a@b.com', password: 'secret');
///
/// // Database
/// final data = await client.from('todos').select('*').eq('done', false).execute();
///
/// // Storage
/// await client.storage.from('avatars').upload('me.png', fileBytes);
///
/// // Edge Functions
/// final result = await client.functions.invoke('hello', body: {'name': 'world'});
///
/// // Realtime
/// final channel = client.channel('room1');
/// channel.onBroadcast('msg', (p) => print(p));
/// channel.subscribe();
/// ```
library;

import 'afribase_auth_client.dart';
import 'afribase_email_client.dart';
import 'afribase_functions_client.dart';
import 'afribase_query_builder.dart';
import 'afribase_realtime_client.dart';
import 'afribase_storage_client.dart';

/// Extract the project slug from the base URL for use in the email API path.
String _extractSlug(String url) {
  try {
    final uri = Uri.parse(url);
    // Path-based: /p/:slug/...
    final pathMatch = RegExp(r'^/p/([^/]+)').firstMatch(uri.path);
    if (pathMatch != null) return pathMatch.group(1)!;
    // Subdomain: slug.useafribase.app
    final parts = (uri.host).split('.');
    if (parts.length >= 3) return parts.first;
  } catch (_) {}
  return '_';
}

/// The main Afribase client.
class AfribaseClient {
  final String _url;
  final String _key;
  final Map<String, String> _headers;

  AfribaseAuthClient? _auth;
  AfribaseStorageClient? _storage;
  AfribaseFunctionsClient? _functions;
  AfribaseRealtimeClient? _realtime;
  AfribaseEmailClient? _email;

  /// Create an Afribase client.
  ///
  /// [afribaseUrl] — Your project URL (e.g. `https://xyz.useafribase.app`).
  /// [afribaseKey] — Your project anon/public API key.
  /// [headers] — Optional extra headers included in every request.
  AfribaseClient(
    String afribaseUrl,
    String afribaseKey, {
    Map<String, String> headers = const {},
  })  : _url = afribaseUrl.endsWith('/') 
            ? afribaseUrl.substring(0, afribaseUrl.length - 1) 
            : afribaseUrl,
        _key = afribaseKey,
        _headers = headers;

  // ─── Service accessors ─────────────────────────────────────────────

  /// Auth client (sign-up, sign-in, tokens, OAuth, OTP, …).
  AfribaseAuthClient get auth {
    _auth ??= AfribaseAuthClient(
      url: '$_url/auth/v1',
      apiKey: _key,
      headers: _headers,
    );
    return _auth!;
  }

  /// Storage client (buckets, upload, download, signed URLs, …).
  AfribaseStorageClient get storage {
    _storage ??= AfribaseStorageClient(
      url: '$_url/storage/v1',
      apiKey: _key,
      headers: _headers,
      accessToken: auth.accessToken,
    );
    return _storage!;
  }

  /// Edge Functions client (invoke remote functions).
  AfribaseFunctionsClient get functions {
    _functions ??= AfribaseFunctionsClient(
      url: '$_url/functions/v1',
      apiKey: _key,
      headers: _headers,
      accessToken: auth.accessToken,
    );
    return _functions!;
  }

  /// Email client — send transactional emails using your project's configured SMTP.
  ///
  /// Example:
  /// ```dart
  /// await client.email.send(
  ///   to: 'user@example.com',
  ///   templateId: 'welcome',
  ///   templateVars: {'name': 'John', 'plan': 'Pro'},
  /// );
  /// ```
  AfribaseEmailClient get email {
    _email ??= AfribaseEmailClient(
      url: '$_url/email/v1',
      slug: _extractSlug(_url),
      apiKey: _key,
      headers: _headers,
      accessToken: auth.accessToken,
    );
    return _email!;
  }

  /// Low-level realtime client. Prefer [channel] instead.
  AfribaseRealtimeClient get realtime {
    _realtime ??= AfribaseRealtimeClient(
      url: _url,
      apiKey: _key,
      accessToken: auth.accessToken,
    );
    return _realtime!;
  }

  // ─── Query builder ─────────────────────────────────────────────────

  /// Return a query builder for [table] (PostgREST).
  AfribaseQueryBuilder from(String table) {
    return AfribaseQueryBuilder(
      url: '$_url/rest/v1',
      apiKey: _key,
      table: table,
      headers: _headers,
      accessToken: auth.accessToken,
    );
  }

  /// Call a Postgres function via RPC.
  AfribaseRpcBuilder rpc(String fn, [Map<String, dynamic>? params]) {
    return AfribaseRpcBuilder(
      url: '$_url/rest/v1',
      apiKey: _key,
      fn: fn,
      params: params ?? {},
      headers: _headers,
      accessToken: auth.accessToken,
    );
  }

  // ─── Realtime helpers ──────────────────────────────────────────────

  /// Create (or get) a realtime channel.
  RealtimeChannel channel(String name) => realtime.channel(name);

  /// Remove a specific realtime channel.
  void removeChannel(RealtimeChannel channel) =>
      realtime.removeChannel(channel);

  /// Remove all realtime channels and disconnect.
  void removeAllChannels() => realtime.removeAllChannels();

  // ─── Cleanup ───────────────────────────────────────────────────────

  /// Clean up resources (disconnect realtime, etc.).
  void dispose() {
    _realtime?.removeAllChannels();
  }
}
