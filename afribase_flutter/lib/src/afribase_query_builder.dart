/// Afribase PostgREST Query Builder for Dart/Flutter.
///
/// Provides a fluent API for building and executing PostgREST queries.
library;

import 'dart:convert';
import 'package:http/http.dart' as http;
import 'types.dart';
import 'http_helper.dart';

/// A fluent PostgREST query builder.
///
/// ```dart
/// final result = await client.from('posts')
///     .select('id, title, author')
///     .eq('published', true)
///     .order('created_at', ascending: false)
///     .limit(10)
///     .execute();
/// ```
class AfribaseQueryBuilder {
  final String _url;
  final String _apiKey;
  final String _table;
  final Map<String, String> _headers;
  final String? _accessToken;

  String _method = 'GET';
  dynamic _body;
  final List<String> _queryParts = [];
  final Map<String, String> _extraHeaders = {};
  bool _isSingle = false;
  bool _isMaybeSingle = false;
  bool _isCsv = false;

  AfribaseQueryBuilder({
    required String url,
    required String apiKey,
    required String table,
    Map<String, String> headers = const {},
    String? accessToken,
  })  : _url = url,
        _apiKey = apiKey,
        _table = table,
        _headers = headers,
        _accessToken = accessToken;

  // ─── CRUD ──────────────────────────────────────────────────────────

  /// Select columns to return.
  AfribaseQueryBuilder select([String columns = '*', String? count]) {
    _method = 'GET';
    _queryParts.add('select=$columns');
    if (count != null) {
      _extraHeaders['Prefer'] = 'count=$count';
    }
    return this;
  }

  /// Insert one or more rows.
  AfribaseQueryBuilder insert(dynamic values, {bool upsert = false}) {
    _method = 'POST';
    _body = values;
    if (upsert) {
      _extraHeaders['Prefer'] = 'resolution=merge-duplicates,return=representation';
    } else {
      _extraHeaders['Prefer'] = 'return=representation';
    }
    return this;
  }

  /// Upsert one or more rows.
  AfribaseQueryBuilder upsert(dynamic values,
      {String? onConflict, bool ignoreDuplicates = false}) {
    _method = 'POST';
    _body = values;
    var prefer = 'resolution=merge-duplicates,return=representation';
    if (ignoreDuplicates) {
      prefer = 'resolution=ignore-duplicates,return=representation';
    }
    _extraHeaders['Prefer'] = prefer;
    if (onConflict != null) _queryParts.add('on_conflict=$onConflict');
    return this;
  }

  /// Update matching rows.
  AfribaseQueryBuilder update(Map<String, dynamic> values) {
    _method = 'PATCH';
    _body = values;
    _extraHeaders['Prefer'] = 'return=representation';
    return this;
  }

  /// Delete matching rows.
  AfribaseQueryBuilder delete() {
    _method = 'DELETE';
    _extraHeaders['Prefer'] = 'return=representation';
    return this;
  }

  // ─── Filters ───────────────────────────────────────────────────────

  /// Equal.
  AfribaseQueryBuilder eq(String column, dynamic value) {
    _queryParts.add('$column=eq.$value');
    return this;
  }

  /// Not equal.
  AfribaseQueryBuilder neq(String column, dynamic value) {
    _queryParts.add('$column=neq.$value');
    return this;
  }

  /// Greater than.
  AfribaseQueryBuilder gt(String column, dynamic value) {
    _queryParts.add('$column=gt.$value');
    return this;
  }

  /// Greater than or equal.
  AfribaseQueryBuilder gte(String column, dynamic value) {
    _queryParts.add('$column=gte.$value');
    return this;
  }

  /// Less than.
  AfribaseQueryBuilder lt(String column, dynamic value) {
    _queryParts.add('$column=lt.$value');
    return this;
  }

  /// Less than or equal.
  AfribaseQueryBuilder lte(String column, dynamic value) {
    _queryParts.add('$column=lte.$value');
    return this;
  }

  /// Pattern match (LIKE).
  AfribaseQueryBuilder like(String column, String pattern) {
    _queryParts.add('$column=like.$pattern');
    return this;
  }

  /// Case-insensitive pattern match (ILIKE).
  AfribaseQueryBuilder ilike(String column, String pattern) {
    _queryParts.add('$column=ilike.$pattern');
    return this;
  }

  /// Is (null / true / false).
  AfribaseQueryBuilder isFilter(String column, dynamic value) {
    _queryParts.add('$column=is.$value');
    return this;
  }

  /// In a list of values.
  AfribaseQueryBuilder inFilter(String column, List<dynamic> values) {
    final v = values.map((e) => '"$e"').join(',');
    _queryParts.add('$column=in.($v)');
    return this;
  }

  /// Contains (array/JSON).
  AfribaseQueryBuilder contains(String column, dynamic value) {
    final v = value is List ? '{${value.join(",")}}' : jsonEncode(value);
    _queryParts.add('$column=cs.$v');
    return this;
  }

  /// Contained by.
  AfribaseQueryBuilder containedBy(String column, dynamic value) {
    final v = value is List ? '{${value.join(",")}}' : jsonEncode(value);
    _queryParts.add('$column=cd.$v');
    return this;
  }

  /// Range greater than.
  AfribaseQueryBuilder rangeGt(String column, String range) {
    _queryParts.add('$column=sr.$range');
    return this;
  }

  /// Range greater than or equal.
  AfribaseQueryBuilder rangeGte(String column, String range) {
    _queryParts.add('$column=nxl.$range');
    return this;
  }

  /// Range less than.
  AfribaseQueryBuilder rangeLt(String column, String range) {
    _queryParts.add('$column=sl.$range');
    return this;
  }

  /// Range less than or equal.
  AfribaseQueryBuilder rangeLte(String column, String range) {
    _queryParts.add('$column=nxr.$range');
    return this;
  }

  /// Range adjacent.
  AfribaseQueryBuilder rangeAdjacent(String column, String range) {
    _queryParts.add('$column=adj.$range');
    return this;
  }

  /// Overlaps (arrays).
  AfribaseQueryBuilder overlaps(String column, List<dynamic> values) {
    _queryParts.add('$column=ov.{${values.join(",")}}');
    return this;
  }

  /// Full-text search.
  AfribaseQueryBuilder textSearch(String column, String query,
      {String config = '', String? type}) {
    final searchType = type ?? 'fts';
    final configPart = config.isNotEmpty ? '($config)' : '';
    _queryParts.add('$column=$searchType$configPart.$query');
    return this;
  }

  /// Match multiple columns.
  AfribaseQueryBuilder match(Map<String, dynamic> query) {
    for (final entry in query.entries) {
      _queryParts.add('${entry.key}=eq.${entry.value}');
    }
    return this;
  }

  /// Negate a filter.
  AfribaseQueryBuilder not(String column, String operator, dynamic value) {
    _queryParts.add('$column=not.$operator.$value');
    return this;
  }

  /// OR filter.
  AfribaseQueryBuilder or(String filters, {String? referencedTable}) {
    if (referencedTable != null) {
      _queryParts.add('$referencedTable.or=($filters)');
    } else {
      _queryParts.add('or=($filters)');
    }
    return this;
  }

  /// Generic filter.
  AfribaseQueryBuilder filter(
      String column, String operator, dynamic value) {
    _queryParts.add('$column=$operator.$value');
    return this;
  }

  // ─── Modifiers ─────────────────────────────────────────────────────

  /// Order results.
  AfribaseQueryBuilder order(String column,
      {bool ascending = true, bool nullsFirst = false}) {
    final dir = ascending ? 'asc' : 'desc';
    final nulls = nullsFirst ? '.nullsfirst' : '.nullslast';
    _queryParts.add('order=$column.$dir$nulls');
    return this;
  }

  /// Limit number of rows.
  AfribaseQueryBuilder limit(int count) {
    _queryParts.add('limit=$count');
    return this;
  }

  /// Offset + limit (pagination).
  AfribaseQueryBuilder range(int from, int to) {
    _extraHeaders['Range'] = '$from-$to';
    _extraHeaders['Range-Unit'] = 'items';
    return this;
  }

  /// Return a single row (throws if ≠1 result).
  AfribaseQueryBuilder single() {
    _isSingle = true;
    _extraHeaders['Accept'] = 'application/vnd.pgrst.object+json';
    return this;
  }

  /// Return a single row or null (no error if 0 results).
  AfribaseQueryBuilder maybeSingle() {
    _isMaybeSingle = true;
    _extraHeaders['Accept'] = 'application/vnd.pgrst.object+json';
    return this;
  }

  /// Return CSV instead of JSON.
  AfribaseQueryBuilder csv() {
    _isCsv = true;
    _extraHeaders['Accept'] = 'text/csv';
    return this;
  }

  // ─── Execute ───────────────────────────────────────────────────────

  /// Execute the query and return a [PostgrestResponse].
  Future<PostgrestResponse<dynamic>> execute() async {
    final queryString = _queryParts.isNotEmpty ? '?${_queryParts.join('&')}' : '';
    final uri = Uri.parse('$_url/$_table$queryString');

    final headers = buildHeaders(
      apiKey: _apiKey,
      accessToken: _accessToken,
      extra: {..._headers, ..._extraHeaders},
    );

    http.Response response;
    switch (_method) {
      case 'POST':
        response = await http.post(uri,
            headers: headers, body: jsonEncode(_body));
        break;
      case 'PATCH':
        response = await http.patch(uri,
            headers: headers, body: jsonEncode(_body));
        break;
      case 'DELETE':
        response = await http.delete(uri, headers: headers);
        break;
      default:
        response = await http.get(uri, headers: headers);
    }

    // Parse response
    final statusCode = response.statusCode;
    if (statusCode >= 400) {
      final errBody = parseResponseBody(response);
      PostgrestError? error;
      if (errBody is Map<String, dynamic>) {
        error = PostgrestError.fromJson(errBody);
      } else {
        error = PostgrestError(message: response.body);
      }
      return PostgrestResponse(error: error, statusCode: statusCode);
    }

    dynamic data;
    if (_isCsv) {
      data = response.body;
    } else {
      data = parseResponseBody(response);
      // When maybeSingle() was called and PostgREST returns 406 (no rows),
      // return null instead of throwing.
      if (_isMaybeSingle && statusCode == 406) {
        data = null;
      }
      // When single() was called, data is already an object (not a list)
      // thanks to the Accept header, but we assert it here for safety.
      if (_isSingle && data is List) {
        data = data.isNotEmpty ? data.first : null;
      }
    }

    // Parse count header
    int? count;
    final contentRange = response.headers['content-range'];
    if (contentRange != null) {
      final parts = contentRange.split('/');
      if (parts.length == 2) {
        count = int.tryParse(parts[1]);
      }
    }

    return PostgrestResponse(data: data, count: count, statusCode: statusCode);
  }
}

/// RPC (Postgres function) builder.
class AfribaseRpcBuilder {
  final String _url;
  final String _apiKey;
  final String _fn;
  final Map<String, dynamic> _params;
  final Map<String, String> _headers;
  final String? _accessToken;

  final List<String> _queryParts = [];
  bool _isSingle = false;

  AfribaseRpcBuilder({
    required String url,
    required String apiKey,
    required String fn,
    required Map<String, dynamic> params,
    Map<String, String> headers = const {},
    String? accessToken,
  })  : _url = url,
        _apiKey = apiKey,
        _fn = fn,
        _params = params,
        _headers = headers,
        _accessToken = accessToken;

  /// Return a single object.
  AfribaseRpcBuilder single() {
    _isSingle = true;
    return this;
  }

  /// Execute the RPC call.
  Future<PostgrestResponse<dynamic>> execute() async {
    final queryString =
        _queryParts.isNotEmpty ? '?${_queryParts.join('&')}' : '';
    final uri = Uri.parse('$_url/rpc/$_fn$queryString');

    final extraHeaders = <String, String>{};
    if (_isSingle) {
      extraHeaders['Accept'] = 'application/vnd.pgrst.object+json';
    }

    final headers = buildHeaders(
      apiKey: _apiKey,
      accessToken: _accessToken,
      extra: {..._headers, ...extraHeaders},
    );

    final response = await http.post(
      uri,
      headers: headers,
      body: jsonEncode(_params),
    );

    final statusCode = response.statusCode;
    if (statusCode >= 400) {
      final errBody = parseResponseBody(response);
      PostgrestError? error;
      if (errBody is Map<String, dynamic>) {
        error = PostgrestError.fromJson(errBody);
      } else {
        error = PostgrestError(message: response.body);
      }
      return PostgrestResponse(error: error, statusCode: statusCode);
    }

    return PostgrestResponse(
      data: parseResponseBody(response),
      statusCode: statusCode,
    );
  }
}
