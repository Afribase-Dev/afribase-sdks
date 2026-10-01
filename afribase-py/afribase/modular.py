"""Afribase Modular Query Engine (Python Edition).
This enables the 'Functional-Fluent' pattern for Python.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union
from ._query_builder import AfribaseQueryBuilder

T = TypeVar("T")
QueryOp = Callable[[AfribaseQueryBuilder], AfribaseQueryBuilder]

def db(builder: AfribaseQueryBuilder, *ops: QueryOp) -> Any:
    """Pipelines multiple operations on a query builder."""
    current = builder
    for op in ops:
        current = op(current)
    return current.execute()

# ─── Operations ─────────────────────────────────────────────────────────────

def select(columns: str = "*") -> QueryOp:
    return lambda b: b.select(columns)

def insert(values: Union[Dict[str, Any], List[Dict[str, Any]]]) -> QueryOp:
    return lambda b: b.insert(values)

def update(values: Dict[str, Any]) -> QueryOp:
    return lambda b: b.update(values)

def upsert(values: Union[Dict[str, Any], List[Dict[str, Any]]], on_conflict: Optional[str] = None) -> QueryOp:
    return lambda b: b.upsert(values, on_conflict=on_conflict)

def delete() -> QueryOp:
    return lambda b: b.delete()

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

def is_(column: str, value: str) -> QueryOp:
    """Python uses is_ to avoid 'is' keyword."""
    return lambda b: b.is_(column, value)

def in_(column: str, values: List[Any]) -> QueryOp:
    """Python uses in_ to avoid 'in' keyword."""
    return lambda b: b.in_(column, values)

def match(query: Dict[str, Any]) -> QueryOp:
    return lambda b: b.match(query)

# ─── Modifiers ──────────────────────────────────────────────────────────────

def order(column: str, ascending: bool = True, nulls_first: bool = False) -> QueryOp:
    return lambda b: b.order(column, ascending=ascending, nulls_first=nulls_first)

def limit(count: int) -> QueryOp:
    return lambda b: b.limit(count)

def single() -> QueryOp:
    return lambda b: b.single()

def maybe_single() -> QueryOp:
    return lambda b: b.maybe_single()
