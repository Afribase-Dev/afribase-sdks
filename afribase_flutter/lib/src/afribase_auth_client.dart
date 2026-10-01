/// Afribase Auth Client for Dart/Flutter.
///
/// Handles sign-up, sign-in, OAuth, OTP, password reset, session management.
library;

import 'dart:convert';
import 'package:http/http.dart' as http;
import 'types.dart';
import 'http_helper.dart';

/// Callback type for auth state changes.
typedef AuthStateChangeCallback = void Function(
    AuthChangeEvent event, Session? session);

/// Auth client for Afribase.
class AfribaseAuthClient {
  final String _url;
  final String _apiKey;
  final Map<String, String> _headers;

  Session? _currentSession;
  User? _currentUser;
  final List<AuthStateChangeCallback> _listeners = [];

  AfribaseAuthClient({
    required String url,
    required String apiKey,
    Map<String, String> headers = const {},
  })  : _url = url,
        _apiKey = apiKey,
        _headers = headers;

  /// The current access token, or `null` if not signed in.
  String? get accessToken => _currentSession?.accessToken;

  /// The current session.
  Session? get currentSession => _currentSession;

  /// The current user.
  User? get currentUser => _currentUser;

  // ─── Auth methods ────────────────────────────────────────────────

  /// Sign up with email and password.
  Future<AuthResponse> signUp({
    String? email,
    String? phone,
    required String password,
    Map<String, dynamic>? data,
  }) async {
    final body = <String, dynamic>{'password': password};
    if (email != null) body['email'] = email;
    if (phone != null) body['phone'] = phone;
    if (data != null) body['data'] = data;

    final response = await http.post(
      Uri.parse('$_url/signup'),
      headers: buildHeaders(apiKey: _apiKey, extra: _headers),
      body: jsonEncode(body),
    );
    final result = AuthResponse.fromJson(
        parseResponseBody(response) as Map<String, dynamic>? ?? {});
    if (!result.hasError) _setSession(result.session, AuthChangeEvent.signedIn);
    return result;
  }

  /// Sign in with email/phone and password.
  Future<AuthResponse> signInWithPassword({
    String? email,
    String? phone,
    required String password,
  }) async {
    final body = <String, dynamic>{'password': password};
    if (email != null) body['email'] = email;
    if (phone != null) body['phone'] = phone;

    final response = await http.post(
      Uri.parse('$_url/token?grant_type=password'),
      headers: buildHeaders(apiKey: _apiKey, extra: _headers),
      body: jsonEncode(body),
    );
    final result = AuthResponse.fromJson(
        parseResponseBody(response) as Map<String, dynamic>? ?? {});
    if (!result.hasError) _setSession(result.session, AuthChangeEvent.signedIn);
    return result;
  }

  /// Sign in with OAuth provider — returns the redirect URL.
  Future<String> signInWithOAuth({
    required String provider,
    String? redirectTo,
    List<String>? scopes,
  }) async {
    final params = <String, String>{'provider': provider};
    if (redirectTo != null) params['redirect_to'] = redirectTo;
    if (scopes != null) params['scopes'] = scopes.join(' ');

    final uri = Uri.parse('$_url/authorize').replace(queryParameters: params);
    return uri.toString();
  }

  /// Sign in with OTP (magic link / SMS code).
  Future<AuthResponse> signInWithOtp({
    String? email,
    String? phone,
  }) async {
    final body = <String, dynamic>{};
    if (email != null) body['email'] = email;
    if (phone != null) body['phone'] = phone;

    final response = await http.post(
      Uri.parse('$_url/otp'),
      headers: buildHeaders(apiKey: _apiKey, extra: _headers),
      body: jsonEncode(body),
    );
    return AuthResponse.fromJson(
        parseResponseBody(response) as Map<String, dynamic>? ?? {});
  }

  /// Verify an OTP token.
  Future<AuthResponse> verifyOtp({
    String? email,
    String? phone,
    required String token,
    String type = 'sms',
  }) async {
    final body = <String, dynamic>{'token': token, 'type': type};
    if (email != null) body['email'] = email;
    if (phone != null) body['phone'] = phone;

    final response = await http.post(
      Uri.parse('$_url/verify'),
      headers: buildHeaders(apiKey: _apiKey, extra: _headers),
      body: jsonEncode(body),
    );
    final result = AuthResponse.fromJson(
        parseResponseBody(response) as Map<String, dynamic>? ?? {});
    if (!result.hasError) _setSession(result.session, AuthChangeEvent.signedIn);
    return result;
  }

  /// Sign in anonymously.
  Future<AuthResponse> signInAnonymously() async {
    final response = await http.post(
      Uri.parse('$_url/signup'),
      headers: buildHeaders(apiKey: _apiKey, extra: _headers),
      body: jsonEncode({'data': {}}),
    );
    final result = AuthResponse.fromJson(
        parseResponseBody(response) as Map<String, dynamic>? ?? {});
    if (!result.hasError) _setSession(result.session, AuthChangeEvent.signedIn);
    return result;
  }

  /// Send a password reset email.
  Future<void> resetPasswordForEmail(String email,
      {String? redirectTo}) async {
    final body = <String, dynamic>{'email': email};
    if (redirectTo != null) body['redirect_to'] = redirectTo;

    await http.post(
      Uri.parse('$_url/recover'),
      headers: buildHeaders(apiKey: _apiKey, extra: _headers),
      body: jsonEncode(body),
    );
  }

  /// Update the current user's attributes.
  Future<AuthResponse> updateUser(Map<String, dynamic> attributes) async {
    final response = await http.put(
      Uri.parse('$_url/user'),
      headers: buildHeaders(
          apiKey: _apiKey, accessToken: accessToken, extra: _headers),
      body: jsonEncode(attributes),
    );
    final result = AuthResponse.fromJson(
        parseResponseBody(response) as Map<String, dynamic>? ?? {});
    if (!result.hasError) {
      _currentUser = result.user ?? _currentUser;
      _notifyListeners(AuthChangeEvent.userUpdated, _currentSession);
    }
    return result;
  }

  /// Get the current session from the server.
  Future<Session?> getSession() async {
    if (_currentSession == null) return null;
    final response = await http.get(
      Uri.parse('$_url/user'),
      headers: buildHeaders(
          apiKey: _apiKey, accessToken: accessToken, extra: _headers),
    );
    if (response.statusCode == 200) {
      final data = parseResponseBody(response) as Map<String, dynamic>?;
      if (data != null) {
        _currentUser = User.fromJson(data);
      }
    }
    return _currentSession;
  }

  /// Get the current user from the server.
  Future<User?> getUser() async {
    if (accessToken == null) return null;
    final response = await http.get(
      Uri.parse('$_url/user'),
      headers: buildHeaders(
          apiKey: _apiKey, accessToken: accessToken, extra: _headers),
    );
    if (response.statusCode == 200) {
      final data = parseResponseBody(response) as Map<String, dynamic>?;
      if (data != null) {
        _currentUser = User.fromJson(data);
        return _currentUser;
      }
    }
    return null;
  }

  /// Set the session manually (e.g. from stored tokens).
  void setSession(String accessToken, String refreshToken) {
    _currentSession = Session(
      accessToken: accessToken,
      refreshToken: refreshToken,
    );
    _notifyListeners(AuthChangeEvent.signedIn, _currentSession);
  }

  /// Permanently deletes a user.
  ///
  /// GoTrue has no self-service delete — this is an administrative endpoint —
  /// so the client must be built with the **service key**. That key must never
  /// ship inside a mobile app, where anyone can read it out of the bundle:
  /// call this from your own backend and have the app ask that instead.
  ///
  /// [shouldSoftDelete] keeps the row and clears the identity rather than
  /// removing it, which leaves the email address occupied so the person cannot
  /// sign up again with it. The default is a real delete.
  ///
  /// Deleting the signed-in user also ends the session held here, which would
  /// otherwise keep refreshing a token for somebody who no longer exists.
  Future<void> deleteUser(String userId, {bool shouldSoftDelete = false}) async {
    final response = await http.delete(
      Uri.parse('$_url/admin/users/$userId'),
      headers: buildHeaders(apiKey: _apiKey, accessToken: _apiKey, extra: _headers),
      body: jsonEncode({'should_soft_delete': shouldSoftDelete}),
    );

    if (response.statusCode >= 400) {
      throw Exception(
        'Could not delete the user (${response.statusCode}): ${response.body}',
      );
    }

    if (_currentUser?.id == userId) {
      _currentSession = null;
      _currentUser = null;
      _notifyListeners(AuthChangeEvent.signedOut, null);
    }
  }

  /// Sign out the current user.
  Future<void> signOut() async {
    if (accessToken != null) {
      try {
        await http.post(
          Uri.parse('$_url/logout'),
          headers: buildHeaders(
              apiKey: _apiKey, accessToken: accessToken, extra: _headers),
        );
      } catch (_) {
        // Best-effort server logout
      }
    }
    _currentSession = null;
    _currentUser = null;
    _notifyListeners(AuthChangeEvent.signedOut, null);
  }

  /// Refresh the current session.
  Future<AuthResponse> refreshSession() async {
    if (_currentSession?.refreshToken == null) {
      return const AuthResponse(error: 'No refresh token available');
    }
    final response = await http.post(
      Uri.parse('$_url/token?grant_type=refresh_token'),
      headers: buildHeaders(apiKey: _apiKey, extra: _headers),
      body: jsonEncode({'refresh_token': _currentSession!.refreshToken}),
    );
    final result = AuthResponse.fromJson(
        parseResponseBody(response) as Map<String, dynamic>? ?? {});
    if (!result.hasError) {
      _setSession(result.session, AuthChangeEvent.tokenRefreshed);
    }
    return result;
  }

  /// Register a listener for auth state changes.
  /// Returns a function to unsubscribe.
  void Function() onAuthStateChange(AuthStateChangeCallback callback) {
    _listeners.add(callback);
    // Emit initial state
    if (_currentSession != null) {
      callback(AuthChangeEvent.initialSession, _currentSession);
    }
    return () => _listeners.remove(callback);
  }

  // ─── Internal ────────────────────────────────────────────────────

  void _setSession(Session? session, AuthChangeEvent event) {
    _currentSession = session;
    _currentUser = session?.user ?? _currentUser;
    _notifyListeners(event, session);
  }

  void _notifyListeners(AuthChangeEvent event, Session? session) {
    for (final cb in _listeners) {
      try {
        cb(event, session);
      } catch (_) {
        // Don't let listener errors propagate
      }
    }
  }
}
