/// Internal HTTP helper for the Afribase Dart SDK.
library;

import 'dart:convert';
import 'package:http/http.dart' as http;

/// Standard headers for Afribase API requests.
Map<String, String> buildHeaders({
  required String apiKey,
  String? accessToken,
  Map<String, String>? extra,
  String contentType = 'application/json',
}) {
  final headers = <String, String>{
    'apikey': apiKey,
    'Content-Type': contentType,
    'Authorization': 'Bearer ${accessToken ?? apiKey}',
  };
  if (extra != null) headers.addAll(extra);
  return headers;
}

/// Parses a JSON response body.
dynamic parseResponseBody(http.Response response) {
  if (response.body.isEmpty) return null;
  try {
    return jsonDecode(response.body);
  } catch (_) {
    return response.body;
  }
}
