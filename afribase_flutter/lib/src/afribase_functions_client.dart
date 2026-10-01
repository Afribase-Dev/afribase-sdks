/// Afribase Edge Functions Client for Dart/Flutter.
///
/// Invoke remote edge functions deployed on Afribase.
library;

import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import 'http_helper.dart';

/// Response from an edge function invocation.
class FunctionResponse {
  final dynamic data;
  final String? error;
  final int statusCode;

  const FunctionResponse({
    this.data,
    this.error,
    this.statusCode = 200,
  });

  bool get hasError => error != null;
}

/// Client for invoking Afribase edge functions.
class AfribaseFunctionsClient {
  final String _url;
  final String _apiKey;
  final Map<String, String> _headers;
  final String? _accessToken;

  AfribaseFunctionsClient({
    required String url,
    required String apiKey,
    Map<String, String> headers = const {},
    String? accessToken,
  })  : _url = url,
        _apiKey = apiKey,
        _headers = headers,
        _accessToken = accessToken;

  /// Invoke an edge function.
  ///
  /// [name] — the function name.
  /// [body] — the request body (Map, String, or Uint8List).
  /// [headers] — additional headers.
  /// [method] — HTTP method (default POST).
  Future<FunctionResponse> invoke(
    String name, {
    dynamic body,
    Map<String, String>? headers,
    String method = 'POST',
  }) async {
    final uri = Uri.parse('$_url/$name');

    // Determine content type and encode body
    String contentType = 'application/json';
    dynamic encodedBody;

    if (body is Uint8List) {
      contentType = 'application/octet-stream';
      encodedBody = body;
    } else if (body is String) {
      contentType = 'text/plain';
      encodedBody = body;
    } else if (body is Map) {
      contentType = 'application/json';
      encodedBody = jsonEncode(body);
    } else if (body != null) {
      contentType = 'application/json';
      encodedBody = jsonEncode(body);
    }

    final requestHeaders = buildHeaders(
      apiKey: _apiKey,
      accessToken: _accessToken,
      extra: {..._headers, if (headers != null) ...headers},
      contentType: contentType,
    );

    http.Response response;
    switch (method.toUpperCase()) {
      case 'GET':
        response = await http.get(uri, headers: requestHeaders);
        break;
      case 'PUT':
        response =
            await http.put(uri, headers: requestHeaders, body: encodedBody);
        break;
      case 'DELETE':
        response = await http.delete(uri, headers: requestHeaders);
        break;
      case 'PATCH':
        response =
            await http.patch(uri, headers: requestHeaders, body: encodedBody);
        break;
      default:
        response =
            await http.post(uri, headers: requestHeaders, body: encodedBody);
    }

    if (response.statusCode >= 400) {
      return FunctionResponse(
        error: response.body,
        statusCode: response.statusCode,
      );
    }

    // Parse response based on content type
    final respContentType = response.headers['content-type'] ?? '';
    dynamic data;
    if (respContentType.contains('application/json')) {
      data = parseResponseBody(response);
    } else if (respContentType.contains('application/octet-stream')) {
      data = response.bodyBytes;
    } else {
      data = response.body;
    }

    return FunctionResponse(data: data, statusCode: response.statusCode);
  }
}
