/// Afribase Email Client — send transactional emails from your app.
library;

import 'dart:convert';
import 'package:http/http.dart' as http;
import 'http_helper.dart';

/// Represents a custom email template saved in the Afribase dashboard.
class EmailTemplate {
  final String id;
  final String name;
  final String? description;
  final String subject;
  final String html;
  final String createdAt;
  final String updatedAt;

  const EmailTemplate({
    required this.id,
    required this.name,
    this.description,
    required this.subject,
    required this.html,
    required this.createdAt,
    required this.updatedAt,
  });

  factory EmailTemplate.fromJson(Map<String, dynamic> json) => EmailTemplate(
        id: json['id'] as String,
        name: json['name'] as String,
        description: json['description'] as String?,
        subject: json['subject'] as String,
        html: json['html'] as String,
        createdAt: json['created_at'] as String,
        updatedAt: json['updated_at'] as String,
      );
}

/// Response from an email send or template list call.
class EmailResponse<T> {
  final T? data;
  final String? error;
  final int statusCode;

  const EmailResponse({this.data, this.error, required this.statusCode});

  bool get hasError => error != null;
}

/// Client for sending transactional emails using your project's configured SMTP.
///
/// Access via [AfribaseClient.email].
///
/// Example:
/// ```dart
/// // With a saved template
/// await client.email.send(
///   to: 'user@example.com',
///   templateId: 'welcome',
///   templateVars: {'name': 'John', 'plan': 'Pro'},
/// );
///
/// // Raw send
/// await client.email.send(
///   to: 'user@example.com',
///   subject: 'Hello from MyApp',
///   html: '<h1>Hello John!</h1>',
/// );
/// ```
class AfribaseEmailClient {
  final String _url;
  final String _slug;
  final String _apiKey;
  final Map<String, String> _headers;
  final String? _accessToken;

  AfribaseEmailClient({
    required String url,
    required String slug,
    required String apiKey,
    Map<String, String> headers = const {},
    String? accessToken,
  })  : _url = url.endsWith('/') ? url.substring(0, url.length - 1) : url,
        _slug = slug,
        _apiKey = apiKey,
        _headers = headers,
        _accessToken = accessToken;

  /// Send a transactional email.
  ///
  /// Supply either [templateId] (a saved template) or [subject] + [html] for a raw send.
  ///
  /// [templateVars] are substituted as `{{ .Key }}` inside the template.
  Future<EmailResponse<Map<String, dynamic>>> send({
    required String to,
    String? templateId,
    Map<String, String>? templateVars,
    String? subject,
    String? html,
    String? from,
    String? fromName,
  }) async {
    final body = <String, dynamic>{'to': to};
    if (templateId != null) body['template_id'] = templateId;
    if (templateVars != null) body['template_vars'] = templateVars;
    if (subject != null) body['subject'] = subject;
    if (html != null) body['html'] = html;
    if (from != null) body['from'] = from;
    if (fromName != null) body['from_name'] = fromName;

    final uri = Uri.parse('$_url/$_slug/send');
    final headers = buildHeaders(
      apiKey: _apiKey,
      accessToken: _accessToken,
      extra: _headers,
      contentType: 'application/json',
    );

    final response = await http.post(uri, headers: headers, body: jsonEncode(body));

    if (response.statusCode >= 400) {
      return EmailResponse(error: response.body, statusCode: response.statusCode);
    }
    return EmailResponse(
      data: jsonDecode(response.body) as Map<String, dynamic>,
      statusCode: response.statusCode,
    );
  }

  /// List all custom email templates saved for this project in the dashboard.
  Future<EmailResponse<List<EmailTemplate>>> listTemplates() async {
    final uri = Uri.parse('$_url/$_slug/templates');
    final headers = buildHeaders(
      apiKey: _apiKey,
      accessToken: _accessToken,
      extra: _headers,
    );

    final response = await http.get(uri, headers: headers);

    if (response.statusCode >= 400) {
      return EmailResponse(error: response.body, statusCode: response.statusCode);
    }
    final list = (jsonDecode(response.body) as List)
        .map((e) => EmailTemplate.fromJson(e as Map<String, dynamic>))
        .toList();
    return EmailResponse(data: list, statusCode: response.statusCode);
  }
}
