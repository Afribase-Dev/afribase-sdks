/// Afribase Storage Client for Dart/Flutter.
///
/// Manages buckets and file operations (upload, download, signed URLs, etc.).
library;

import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import 'types.dart';
import 'http_helper.dart';

/// API for file operations within a specific storage bucket.
class StorageFileApi {
  final String _url;
  final String _apiKey;
  final String _bucketId;
  final Map<String, String> _headers;
  final String? _accessToken;

  StorageFileApi({
    required String url,
    required String apiKey,
    required String bucketId,
    Map<String, String> headers = const {},
    String? accessToken,
  })  : _url = url,
        _apiKey = apiKey,
        _bucketId = bucketId,
        _headers = headers,
        _accessToken = accessToken;

  Map<String, String> get _authHeaders => buildHeaders(
        apiKey: _apiKey,
        accessToken: _accessToken,
        extra: _headers,
      );

  /// Upload a file.
  Future<Map<String, dynamic>> upload(
    String path,
    Uint8List fileBytes, {
    String? contentType,
    bool upsert = false,
  }) async {
    final uri = Uri.parse('$_url/object/$_bucketId/$path');
    final request = http.MultipartRequest('POST', uri);
    request.headers.addAll(buildHeaders(
      apiKey: _apiKey,
      accessToken: _accessToken,
      extra: _headers,
      contentType: contentType ?? 'application/octet-stream',
    ));
    if (upsert) request.headers['x-upsert'] = 'true';
    request.files.add(http.MultipartFile.fromBytes(
      'file',
      fileBytes,
      filename: path.split('/').last,
    ));

    final streamedResponse = await request.send();
    final response = await http.Response.fromStream(streamedResponse);
    return (parseResponseBody(response) as Map<String, dynamic>?) ?? {};
  }

  /// Update (overwrite) a file.
  Future<Map<String, dynamic>> update(
    String path,
    Uint8List fileBytes, {
    String? contentType,
  }) async {
    final uri = Uri.parse('$_url/object/$_bucketId/$path');
    final request = http.MultipartRequest('PUT', uri);
    request.headers.addAll(buildHeaders(
      apiKey: _apiKey,
      accessToken: _accessToken,
      extra: _headers,
      contentType: contentType ?? 'application/octet-stream',
    ));
    request.files.add(http.MultipartFile.fromBytes(
      'file',
      fileBytes,
      filename: path.split('/').last,
    ));

    final streamedResponse = await request.send();
    final response = await http.Response.fromStream(streamedResponse);
    return (parseResponseBody(response) as Map<String, dynamic>?) ?? {};
  }

  /// Download a file as bytes.
  Future<Uint8List> download(String path,
      {TransformOptions? transform}) async {
    var uri = '$_url/object/$_bucketId/$path';
    if (transform != null) {
      final params = transform.toQueryParams();
      if (params.isNotEmpty) {
        uri = '$_url/render/image/$_bucketId/$path';
        final qs = params.entries.map((e) => '${e.key}=${e.value}').join('&');
        uri = '$uri?$qs';
      }
    }
    final response = await http.get(Uri.parse(uri), headers: _authHeaders);
    return response.bodyBytes;
  }

  /// List files in a folder.
  Future<List<StorageObject>> list({
    String? path,
    int? limit,
    int? offset,
    String? sortBy,
    String? order,
    String? search,
  }) async {
    final body = <String, dynamic>{};
    if (path != null) body['prefix'] = path;
    if (limit != null) body['limit'] = limit;
    if (offset != null) body['offset'] = offset;
    if (search != null) body['search'] = search;
    if (sortBy != null) {
      body['sortBy'] = {
        'column': sortBy,
        'order': order ?? 'asc',
      };
    }

    final response = await http.post(
      Uri.parse('$_url/object/list/$_bucketId'),
      headers: _authHeaders,
      body: jsonEncode(body),
    );
    final data = parseResponseBody(response);
    if (data is List) {
      return data
          .map((e) => StorageObject.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  /// Remove files.
  Future<List<Map<String, dynamic>>> remove(List<String> paths) async {
    final response = await http.delete(
      Uri.parse('$_url/object/$_bucketId'),
      headers: _authHeaders,
      body: jsonEncode({'prefixes': paths}),
    );
    final data = parseResponseBody(response);
    if (data is List) {
      return data.cast<Map<String, dynamic>>();
    }
    return [];
  }

  /// Move a file.
  Future<Map<String, dynamic>> move(
      String fromPath, String toPath) async {
    final response = await http.post(
      Uri.parse('$_url/object/move'),
      headers: _authHeaders,
      body: jsonEncode({
        'bucketId': _bucketId,
        'sourceKey': fromPath,
        'destinationKey': toPath,
      }),
    );
    return (parseResponseBody(response) as Map<String, dynamic>?) ?? {};
  }

  /// Copy a file.
  Future<Map<String, dynamic>> copy(
      String fromPath, String toPath) async {
    final response = await http.post(
      Uri.parse('$_url/object/copy'),
      headers: _authHeaders,
      body: jsonEncode({
        'bucketId': _bucketId,
        'sourceKey': fromPath,
        'destinationKey': toPath,
      }),
    );
    return (parseResponseBody(response) as Map<String, dynamic>?) ?? {};
  }

  /// Create a signed URL for temporary access.
  Future<String> createSignedUrl(String path, {int expiresIn = 3600}) async {
    final response = await http.post(
      Uri.parse('$_url/object/sign/$_bucketId/$path'),
      headers: _authHeaders,
      body: jsonEncode({'expiresIn': expiresIn}),
    );
    final data = parseResponseBody(response) as Map<String, dynamic>?;
    return data?['signedURL'] as String? ?? '';
  }

  /// Create signed URLs for multiple files.
  Future<List<String>> createSignedUrls(List<String> paths,
      {int expiresIn = 3600}) async {
    final response = await http.post(
      Uri.parse('$_url/object/sign/$_bucketId'),
      headers: _authHeaders,
      body: jsonEncode({'expiresIn': expiresIn, 'paths': paths}),
    );
    final data = parseResponseBody(response);
    if (data is List) {
      return data
          .map((e) =>
              (e as Map<String, dynamic>)['signedURL'] as String? ?? '')
          .toList();
    }
    return [];
  }

  /// Get the public URL for a file (bucket must be public).
  String getPublicUrl(String path, {TransformOptions? transform}) {
    var url = '$_url/object/public/$_bucketId/$path';
    if (transform != null) {
      final params = transform.toQueryParams();
      if (params.isNotEmpty) {
        url = '$_url/render/image/public/$_bucketId/$path';
        final qs = params.entries.map((e) => '${e.key}=${e.value}').join('&');
        url = '$url?$qs';
      }
    }
    return url;
  }
}

/// Afribase Storage client — manages buckets and provides file APIs.
class AfribaseStorageClient {
  final String _url;
  final String _apiKey;
  final Map<String, String> _headers;
  final String? _accessToken;

  AfribaseStorageClient({
    required String url,
    required String apiKey,
    Map<String, String> headers = const {},
    String? accessToken,
  })  : _url = url,
        _apiKey = apiKey,
        _headers = headers,
        _accessToken = accessToken;

  Map<String, String> get _authHeaders => buildHeaders(
        apiKey: _apiKey,
        accessToken: _accessToken,
        extra: _headers,
      );

  /// Get a [StorageFileApi] for the specified bucket.
  StorageFileApi from(String bucketId) => StorageFileApi(
        url: _url,
        apiKey: _apiKey,
        bucketId: bucketId,
        headers: _headers,
        accessToken: _accessToken,
      );

  /// List all buckets.
  Future<List<StorageBucket>> listBuckets() async {
    final response = await http.get(
      Uri.parse('$_url/bucket'),
      headers: _authHeaders,
    );
    final data = parseResponseBody(response);
    if (data is List) {
      return data
          .map((e) => StorageBucket.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  /// Get a bucket by ID.
  Future<StorageBucket> getBucket(String id) async {
    final response = await http.get(
      Uri.parse('$_url/bucket/$id'),
      headers: _authHeaders,
    );
    return StorageBucket.fromJson(
        (parseResponseBody(response) as Map<String, dynamic>?) ?? {});
  }

  /// Create a new bucket.
  Future<Map<String, dynamic>> createBucket(
    String id, {
    bool public = false,
    int? fileSizeLimit,
    List<String>? allowedMimeTypes,
  }) async {
    final body = <String, dynamic>{'id': id, 'name': id, 'public': public};
    if (fileSizeLimit != null) body['file_size_limit'] = fileSizeLimit;
    if (allowedMimeTypes != null) body['allowed_mime_types'] = allowedMimeTypes;

    final response = await http.post(
      Uri.parse('$_url/bucket'),
      headers: _authHeaders,
      body: jsonEncode(body),
    );
    return (parseResponseBody(response) as Map<String, dynamic>?) ?? {};
  }

  /// Update a bucket.
  Future<Map<String, dynamic>> updateBucket(
    String id, {
    bool? public,
    int? fileSizeLimit,
    List<String>? allowedMimeTypes,
  }) async {
    final body = <String, dynamic>{};
    if (public != null) body['public'] = public;
    if (fileSizeLimit != null) body['file_size_limit'] = fileSizeLimit;
    if (allowedMimeTypes != null) body['allowed_mime_types'] = allowedMimeTypes;

    final response = await http.put(
      Uri.parse('$_url/bucket/$id'),
      headers: _authHeaders,
      body: jsonEncode(body),
    );
    return (parseResponseBody(response) as Map<String, dynamic>?) ?? {};
  }

  /// Delete a bucket (must be empty).
  Future<Map<String, dynamic>> deleteBucket(String id) async {
    final response = await http.delete(
      Uri.parse('$_url/bucket/$id'),
      headers: _authHeaders,
    );
    return (parseResponseBody(response) as Map<String, dynamic>?) ?? {};
  }

  /// Empty a bucket (remove all files).
  Future<Map<String, dynamic>> emptyBucket(String id) async {
    final response = await http.post(
      Uri.parse('$_url/bucket/$id/empty'),
      headers: _authHeaders,
    );
    return (parseResponseBody(response) as Map<String, dynamic>?) ?? {};
  }
}
