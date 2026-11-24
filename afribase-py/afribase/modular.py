"""Afribase Modular Query Engine (Python Edition).

The 'Functional-Fluent' pattern of the JS SDK's ``modular.ts``::

    db(client.from_("posts"), select("*"), eq("published", True), order("created_at", ascending=False), limit(10))

JS ``del`` / ``is`` / ``isIn`` are ``delete`` / ``is_`` / ``in_`` here.
"""

from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

from ._query_builder import AfribaseQueryBuilder

T = TypeVar("T")
QueryOp = Callable[[AfribaseQueryBuilder], AfribaseQueryBuilder]
Rows = Union[Dict[str, Any], List[Dict[str, Any]]]


def db(builder: AfribaseQueryBuilder, *ops: QueryOp) -> Any:
    """Pipelines multiple operations on a query builder and executes it."""
    current = builder
    for op in ops:
        current = op(current)
    return current.execute()


# ─── Operations ─────────────────────────────────────────────────────────────


def select(columns: str = "*", *, count: Optional[str] = None, head: bool = False) -> QueryOp:
    return lambda b: b.select(columns, count=count, head=head)


def insert(values: Rows, *, count: Optional[str] = None, default_to_null: bool = True) -> QueryOp:
    return lambda b: b.insert(values, count=count, default_to_null=default_to_null)


def update(values: Dict[str, Any], *, count: Optional[str] = None) -> QueryOp:
    return lambda b: b.update(values, count=count)


def upsert(values: Rows, on_conflict: Optional[str] = None, *, ignore_duplicates: bool = False,
           count: Optional[str] = None, default_to_null: bool = True) -> QueryOp:
    return lambda b: b.upsert(values, on_conflict=on_conflict, ignore_duplicates=ignore_duplicates,
                              count=count, default_to_null=default_to_null)


def delete(*, count: Optional[str] = None) -> QueryOp:
    return lambda b: b.delete(count=count)


# ─── Filters ────────────────────────────────────────────────────────────────


def eq(column: str, value: Any) -> QueryOp:
    return lambda b: b.eq(column, value)


def neq(column: str, value: Any) -> QueryOp:
    return lambda b: b.neq(column, value)


def gt(column: str, value: Any) -> QueryOp:
    return lambda b: b.gt(column, value)


def gte(column: str, value: Any) -> QueryOp:
    return lambda b: b.gte(column, value)


def lt(column: str, value: Any) -> QueryOp:
    return lambda b: b.lt(column, value)


def lte(column: str, value: Any) -> QueryOp:
    return lambda b: b.lte(column, value)


def like(column: str, pattern: str) -> QueryOp:
    return lambda b: b.like(column, pattern)


def ilike(column: str, pattern: str) -> QueryOp:
    return lambda b: b.ilike(column, pattern)


def is_(column: str, value: Any) -> QueryOp:
    """Python uses is_ to avoid the 'is' keyword."""
    return lambda b: b.is_(column, value)


def in_(column: str, values: List[Any]) -> QueryOp:
    """Python uses in_ to avoid the 'in' keyword."""
    return lambda b: b.in_(column, values)


def contains(column: str, value: Any) -> QueryOp:
    return lambda b: b.contains(column, value)


def contained_by(column: str, value: Any) -> QueryOp:
    return lambda b: b.contained_by(column, value)


def text_search(column: str, query: str, *, type: Optional[str] = None, config: Optional[str] = None) -> QueryOp:
    return lambda b: b.text_search(column, query, type=type, config=config)


def match(query: Dict[str, Any]) -> QueryOp:
    return lambda b: b.match(query)


def not_(column: str, operator: str, value: Any) -> QueryOp:
    return lambda b: b.not_(column, operator, value)


def or_(filters: str, *, foreign_table: Optional[str] = None) -> QueryOp:
    return lambda b: b.or_(filters, foreign_table=foreign_table)


def filter(column: str, operator: str, value: Any) -> QueryOp:  # noqa: A001 (matches the builder)
    return lambda b: b.filter(column, operator, value)


# ─── Modifiers ──────────────────────────────────────────────────────────────


def order(column: str, ascending: bool = True, nulls_first: bool = False, *,
          foreign_table: Optional[str] = None) -> QueryOp:
    return lambda b: b.order(column, ascending=ascending, nulls_first=nulls_first, foreign_table=foreign_table)


def limit(count: int, *, foreign_table: Optional[str] = None) -> QueryOp:
    return lambda b: b.limit(count, foreign_table=foreign_table)


def range(start: int, end: int, *, foreign_table: Optional[str] = None) -> QueryOp:  # noqa: A001
    return lambda b: b.range(start, end, foreign_table=foreign_table)


def single() -> QueryOp:
    return lambda b: b.single()


def maybe_single() -> QueryOp:
    return lambda b: b.maybe_single()


def csv() -> QueryOp:
    return lambda b: b.csv()


def geojson() -> QueryOp:
    return lambda b: b.geojson()


def explain(**options: Any) -> QueryOp:
    return lambda b: b.explain(**options)
