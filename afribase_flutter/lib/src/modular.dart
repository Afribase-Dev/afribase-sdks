import 'afribase_query_builder.dart';
import 'afribase_client.dart';

/// Afribase Modular Query Engine (Dart Edition).
/// This enables the 'Functional-Fluent' pattern for Flutter.

typedef QueryOp = AfribaseQueryBuilder Function(AfribaseQueryBuilder builder);

extension AfribaseClientModular on AfribaseClient {
  /// The 'db' orchestrator allows piping multiple operations.
  Future<dynamic> db(String table, List<QueryOp> ops) async {
    AfribaseQueryBuilder builder = from(table);
    for (final op in ops) {
      builder = op(builder);
    }
    return builder.execute();
  }
}

// ─── Operations ─────────────────────────────────────────────────────────────

QueryOp select([String columns = '*']) =>
    (b) => b.select(columns);
QueryOp insert(dynamic values) =>
    (b) => b.insert(values);
QueryOp update(Map<String, dynamic> values) =>
    (b) => b.update(values);
QueryOp upsert(dynamic values, {String? onConflict}) =>
    (b) => b.upsert(values, onConflict: onConflict);
QueryOp delete() =>
    (b) => b.delete();

// ─── Filters ────────────────────────────────────────────────────────────────

QueryOp eq(String column, dynamic value) =>
    (b) => b.eq(column, value);
QueryOp neq(String column, dynamic value) =>
    (b) => b.neq(column, value);
QueryOp gt(String column, dynamic value) =>
    (b) => b.gt(column, value);
QueryOp gte(String column, dynamic value) =>
    (b) => b.gte(column, value);
QueryOp lt(String column, dynamic value) =>
    (b) => b.lt(column, value);
QueryOp lte(String column, dynamic value) =>
    (b) => b.lte(column, value);
QueryOp like(String column, String pattern) =>
    (b) => b.like(column, pattern);
QueryOp ilike(String column, String pattern) =>
    (b) => b.ilike(column, pattern);
QueryOp isIn(String column, List<dynamic> values) =>
    (b) => b.inFilter(column, values);
QueryOp match(Map<String, dynamic> query) =>
    (b) => b.match(query);

// ─── Modifiers ──────────────────────────────────────────────────────────────

QueryOp order(
  String column, {
  bool ascending = true,
  bool nullsFirst = false,
}) =>
    (b) => b.order(column, ascending: ascending, nullsFirst: nullsFirst);

QueryOp limit(int count) =>
    (b) => b.limit(count);
QueryOp single() =>
    (b) => b.single();
QueryOp maybeSingle() =>
    (b) => b.maybeSingle();
